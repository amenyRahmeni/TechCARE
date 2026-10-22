from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from appointments.models import Appointment, Invoice, Technician
from maintenance.models import PC, MaintenanceRule, Recommendation
from .forms import AccountForm, AdminPCForm, RuleForm

User = get_user_model()


def staff_required(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied("Cet espace est réservé aux administrateurs.")
        return view(request, *args, **kwargs)
    return never_cache(login_required(guarded))


def audit(actor, obj, action, text):
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[obj], action_flag=action, change_message=text, single_object=True)


def page(request, queryset, **context):
    params = request.GET.copy()
    params.pop("page", None)
    return {"page_obj": Paginator(queryset, 12).get_page(request.GET.get("page")), "page_query": params.urlencode(), **context}


def role_queryset(role):
    users = User.objects.all()
    if role == "admin":
        return users.filter(is_staff=True)
    if role == "technician":
        return users.filter(is_staff=False, technician_profile__isnull=False)
    if role == "client":
        return users.filter(is_staff=False, technician_profile__isnull=True)
    return users


@staff_required
def dashboard(request):
    today = timezone.localdate()
    first = today.replace(day=1)
    months = [first]
    for _ in range(5):
        months.insert(0, (months[0] - timedelta(days=1)).replace(day=1))
    # UTC bounds preserve Tunis calendar months without requiring MySQL time-zone tables.
    revenue = {}
    for month in months:
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        start = timezone.make_aware(datetime.combine(month, time.min))
        end = timezone.make_aware(datetime.combine(next_month, time.min))
        revenue[month] = Invoice.objects.filter(issued_at__gte=start, issued_at__lt=end).aggregate(total=Sum("total_amount"))["total"] or Decimal(0)
    maximum = max(revenue.values(), default=Decimal(0)) or Decimal(1)
    chart = [{"date": month, "amount": revenue.get(month, Decimal(0)), "height": round(float(revenue.get(month, 0) / maximum) * 100)} for month in months]
    statuses = dict(Appointment.objects.values_list("status").annotate(total=Count("pk")))
    total = sum(statuses.values())
    counts = {
        "clients": role_queryset("client").count(), "pcs": PC.objects.count(),
        "active": sum(statuses.get(value, 0) for value in ("pending", "confirmed", "diagnosis", "repair")),
        "pending": statuses.get("pending", 0), "completed": statuses.get("completed", 0), "appointments": total,
        "monthly_revenue": revenue.get(first, Decimal(0)), "technicians": Technician.objects.filter(is_available=True, user__is_active=True).count(),
        "alerts": Recommendation.objects.filter(is_active=True, rule__is_active=True, rule__priority="high").values("pc").distinct().count(),
    }
    return render(request, "backoffice/dashboard.html", {
        "active_page": "dashboard", "counts": counts, "chart": chart,
        "completion": round(counts["completed"] / total * 100) if total else 0,
        "upcoming": Appointment.objects.filter(starts_at__gte=timezone.now()).exclude(status__in=["completed", "cancelled"]).select_related("pc", "client", "technician__user").order_by("starts_at")[:5],
        "recent_logs": LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[:5],
    })


@staff_required
def accounts(request):
    role = request.GET.get("role", "")
    state = request.GET.get("state", "")
    q = request.GET.get("q", "").strip()[:100]
    users = role_queryset(role).select_related("technician_profile").annotate(pc_count=Count("pcs", distinct=True)).order_by("-date_joined", "-pk")
    if state in ("active", "inactive"):
        users = users.filter(is_active=state == "active")
    if q:
        users = users.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q))
    return render(request, "backoffice/accounts.html", page(request, users, active_page="accounts", role=role, state=state, q=q, total=User.objects.count(), technician_count=Technician.objects.count(), inactive_count=User.objects.filter(is_active=False).count()))


def editable_account(actor, pk, lock=False):
    queryset = User.objects.select_for_update() if lock else User.objects.all()
    target = get_object_or_404(queryset, pk=pk)
    if not actor.is_superuser and (target.is_staff or target.is_superuser):
        raise PermissionDenied("Seul un superadministrateur peut gérer les administrateurs.")
    return target


@staff_required
def account_form(request, pk=None):
    with transaction.atomic():
        target = editable_account(request.user, pk, lock=request.method == "POST") if pk else None
        form = AccountForm(request.POST if request.method == "POST" else None, instance=target, actor=request.user, initial={"role": request.GET.get("role", "client")})
        if request.method == "POST" and form.is_valid():
            account = form.save(commit=False)
            account.is_staff = form.cleaned_data["role"] == "admin"
            if form.cleaned_data["password1"]:
                account.set_password(form.cleaned_data["password1"])
            try:
                with transaction.atomic():
                    account.save()
                    if form.cleaned_data["role"] == "technician":
                        Technician.objects.update_or_create(user=account, defaults={"specialty": form.cleaned_data["specialty"], "is_available": form.cleaned_data["is_available"]})
                    else:
                        Technician.objects.filter(user=account).delete()
                    audit(request.user, account, CHANGE if pk else ADDITION, "Compte modifié depuis le backoffice." if pk else "Compte créé depuis le backoffice.")
            except (IntegrityError, ProtectedError):
                form.add_error(None, "Le compte a changé pendant l’enregistrement ou cet identifiant existe déjà. Rechargez la page et réessayez.")
            else:
                if account.pk == request.user.pk:
                    update_session_auth_hash(request, account)
                messages.success(request, "Le compte a été enregistré.")
                return redirect("backoffice:accounts")
    return render(request, "backoffice/form.html", {"active_page": "accounts", "form": form, "account": target, "title": "Modifier le compte" if pk else "Créer un compte", "subtitle": "Identité, accès et rôle au sein de l’atelier.", "back_url": "backoffice:accounts", "form_kind": "account"})


@staff_required
def account_state(request, pk):
    with transaction.atomic():
        target = editable_account(request.user, pk, lock=request.method == "POST")
        if target.pk == request.user.pk:
            messages.error(request, "Vous ne pouvez pas suspendre votre propre compte.")
            return redirect("backoffice:accounts")
        if request.method == "POST":
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            audit(request.user, target, CHANGE, "Compte activé." if target.is_active else "Compte suspendu.")
            messages.success(request, "Le compte a été activé." if target.is_active else "Le compte a été suspendu. Ses données et son historique sont conservés.")
            return redirect("backoffice:accounts")
    return render(request, "backoffice/confirm.html", {"active_page": "accounts", "title": "Suspendre ce compte ?" if target.is_active else "Activer ce compte ?", "description": f"Compte : {target.username}. La suspension bloque la connexion et les nouvelles réservations pour un technicien. Les rendez-vous existants restent à traiter.", "back_url": "backoffice:accounts", "button_label": "Suspendre le compte" if target.is_active else "Activer le compte"})


@staff_required
def technicians(request):
    technicians = Technician.objects.select_related("user").annotate(ongoing=Count("appointments", filter=Q(appointments__status__in=["pending", "confirmed", "diagnosis", "repair"])), done=Count("appointments", filter=Q(appointments__status="completed")))
    return render(request, "backoffice/technicians.html", {"active_page": "technicians", "technicians": technicians})


@staff_required
def pcs(request):
    q = request.GET.get("q", "").strip()[:100]
    kind = request.GET.get("kind", "")
    alert = request.GET.get("alert", "")
    pcs = PC.objects.select_related("owner").annotate(record_count=Count("maintenance_records", distinct=True), alert_count=Count("recommendations", filter=Q(recommendations__is_active=True, recommendations__rule__is_active=True), distinct=True)).order_by("-created_at", "-pk")
    if q:
        pcs = pcs.filter(Q(name__icontains=q) | Q(serial_number__icontains=q) | Q(owner__username__icontains=q) | Q(brand__icontains=q))
    if kind in PC.DeviceType.values:
        pcs = pcs.filter(device_type=kind)
    if alert == "high":
        pcs = pcs.filter(recommendations__is_active=True, recommendations__rule__is_active=True, recommendations__rule__priority="high").distinct()
    return render(request, "backoffice/pcs.html", page(request, pcs, active_page="pcs", q=q, kind=kind, alert=alert, kinds=PC.DeviceType.choices))


@staff_required
def pc_form(request, pk=None):
    pc = get_object_or_404(PC.objects.select_related("owner"), pk=pk) if pk else None
    form = AdminPCForm(request.POST if request.method == "POST" else None, instance=pc, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                saved = form.save()
                audit(request.user, saved, CHANGE if pk else ADDITION, "Fiche PC enregistrée depuis le backoffice.")
        except IntegrityError:
            form.add_error("serial_number", "Ce numéro de série est déjà utilisé par ce propriétaire.")
        else:
            messages.success(request, "La fiche de l’ordinateur a été enregistrée.")
            return redirect("backoffice:pc_detail", pk=saved.pk)
    return render(request, "backoffice/form.html", {"active_page": "pcs", "form": form, "title": "Modifier l’ordinateur" if pk else "Ajouter un ordinateur", "subtitle": "La configuration et l’historique du parc informatique.", "back_url": "backoffice:pcs"})


@staff_required
def pc_detail(request, pk):
    pc = get_object_or_404(PC.objects.select_related("owner"), pk=pk)
    return render(request, "backoffice/pc_detail.html", {"active_page": "pcs", "pc": pc, "records": pc.maintenance_records.all(), "recommendations": pc.recommendations.filter(is_active=True, rule__is_active=True).select_related("rule"), "appointments": pc.appointments.select_related("technician__user")[:8]})


@staff_required
def pc_delete(request, pk):
    pc = get_object_or_404(PC, pk=pk)
    if request.method == "POST":
        try:
            with transaction.atomic():
                audit(request.user, pc, DELETION, "Fiche PC supprimée depuis le backoffice.")
                pc.delete()
        except ProtectedError:
            messages.error(request, "Ce PC est lié à un rendez-vous. Sa fiche et son historique doivent être conservés.")
            return redirect("backoffice:pc_detail", pk=pk)
        messages.success(request, "L’ordinateur a été supprimé.")
        return redirect("backoffice:pcs")
    return render(request, "backoffice/confirm.html", {"active_page": "pcs", "title": "Supprimer cet ordinateur ?", "description": f"La fiche « {pc.name} », ses recommandations et ses anciens entretiens seront supprimés. Un PC lié à un rendez-vous ne peut pas être supprimé.", "back_url": "backoffice:pcs", "button_label": "Supprimer l’ordinateur"})


@staff_required
def rules(request):
    return render(request, "backoffice/rules.html", {"active_page": "rules", "rules": MaintenanceRule.objects.all()})


@staff_required
def rule_form(request, pk=None):
    rule = get_object_or_404(MaintenanceRule, pk=pk) if pk else None
    form = RuleForm(request.POST if request.method == "POST" else None, instance=rule)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                saved = form.save()
                audit(request.user, saved, CHANGE if pk else ADDITION, "Règle de maintenance enregistrée.")
        except IntegrityError:
            form.add_error("code", "Ce code de règle existe déjà.")
        else:
            messages.success(request, "La règle a été enregistrée et les recommandations ont été recalculées.")
            return redirect("backoffice:rules")
    return render(request, "backoffice/form.html", {"active_page": "rules", "form": form, "title": "Modifier la règle" if pk else "Créer une règle", "subtitle": "Les conseils des clients sont recalculés à chaque enregistrement.", "back_url": "backoffice:rules"})
