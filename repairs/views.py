from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from inventory.forms import UseForm
from appointments.permissions import can_use_client_features
from .forms import AssignmentForm, ReportForm, RequestForm
from .models import RepairRequest
from .permissions import can_create_repair_requests, can_manage, qualified_technicians, repair_access_required, visible_repairs
from .services import TRANSITIONS, assign_technician, change_status, create_request, save_report, send_message


def context(request, **values):
    staff = request.resolver_match.namespace == "backoffice"
    return {"workspace_base": "backoffice/base.html" if staff else "base.html", "active_page": "repairs", "can_create_repair_requests": can_create_repair_requests(request.user), "repair_urls": {name: f"backoffice:repair_{name}" if staff else f"repairs:{name}" for name in ("list", "create", "detail", "assign", "status", "report", "message", "photo", "cancel")}, **values}


def items(user):
    return visible_repairs(user).select_related("pc", "client", "technician__user", "invoice")


def followup(request, repair):
    return redirect("backoffice:repair_detail" if request.resolver_match.namespace == "backoffice" else "repairs:detail", pk=repair.pk)


@never_cache
@repair_access_required
@require_GET
def request_list(request):
    repairs = items(request.user)
    counts = repairs.aggregate(total=Count("pk"), sent=Count("pk", filter=Q(status="sent")), active=Count("pk", filter=~Q(status__in=["resolved", "cancelled"])), waiting=Count("pk", filter=Q(status="waiting")))
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()[:100]
    if status in RepairRequest.Status.values:
        repairs = repairs.filter(status=status)
    if q:
        repairs = repairs.filter(Q(pc__name__icontains=q) | Q(description__icontains=q) | Q(client__username__icontains=q) | Q(technician__user__first_name__icontains=q))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "repairs/list.html", context(request, page_obj=Paginator(repairs, 12).get_page(request.GET.get("page")), page_query=params.urlencode(), counts=counts, statuses=RepairRequest.Status.choices, status=status, q=q))


@never_cache
@repair_access_required
def request_create(request):
    if not can_create_repair_requests(request.user):
        raise PermissionDenied("La déclaration d’une panne appartient à l’espace client.")
    initial = {"pc": request.GET.get("pc", ""), "problem": request.GET.get("problem", "")}
    form = RequestForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None, actor=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            repair = create_request(request.user, form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Votre demande a été envoyée au technicien choisi.")
            return followup(request, repair)
    return render(request, "repairs/form.html", context(request, form=form))


def detail_context(request, repair, report_form=None):
    manager = can_manage(request.user, repair)
    paginator = Paginator(repair.messages.select_related("sender"), 30)
    thread_page = paginator.get_page(request.GET.get("messages_page", paginator.num_pages))
    return context(request, repair=repair, can_manage=manager, can_download=can_use_client_features(request.user) and (request.user.is_staff or repair.client_id == request.user.pk), report_form=report_form or ReportForm(instance=repair), assignment_form=AssignmentForm(repair=repair), use_form=UseForm(actor=request.user, fixed_target=f"repair:{repair.pk}"), status_choices=[(value, RepairRequest.Status(value).label) for value in TRANSITIONS[repair.status]], usages=repair.component_usages.select_related("component", "used_by").all(), timeline=repair.events.select_related("actor")[:40], thread=thread_page.object_list, thread_page=thread_page, can_cancel=not repair.is_closed and (manager or repair.status in ("sent", "assigned", "diagnosis")), can_resolve="resolved" in TRANSITIONS[repair.status], can_choose_technician=can_create_repair_requests(request.user) and repair.client_id == request.user.pk and repair.status in ('sent', 'assigned'))


@never_cache
@repair_access_required
@require_GET
def detail(request, pk):
    repair = get_object_or_404(items(request.user), pk=pk)
    return render(request, "repairs/detail.html", detail_context(request, repair))


@repair_access_required
@require_POST
def assign(request, pk):
    if not can_create_repair_requests(request.user):
        raise PermissionDenied
    repair = get_object_or_404(items(request.user), pk=pk)
    form = AssignmentForm(request.POST, repair=repair)
    if form.is_valid():
        try:
            assign_technician(request.user, pk, form.cleaned_data["technician"].pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Votre choix de technicien a été enregistré et les participants ont été avertis.")
    else:
        messages.error(request, "Choisissez un technicien actif disposant de la compétence requise.")
    return followup(request, repair)


@repair_access_required
@require_GET
def technicians(request):
    if not can_create_repair_requests(request.user):
        raise PermissionDenied
    problem = request.GET.get("problem", "")
    if problem not in RepairRequest.Problem.values:
        return JsonResponse({"error": "Choisissez un type de panne valide."}, status=400)
    return JsonResponse({"technicians": [{"id": tech.pk, "name": str(tech), "specialty": tech.specialty} for tech in qualified_technicians(problem)]})


@repair_access_required
@require_POST
def status_update(request, pk):
    repair = get_object_or_404(items(request.user), pk=pk)
    try:
        change_status(request.user, pk, request.POST.get("status", ""), request.POST.get("reason", "")[:250])
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Le suivi de la réparation a été mis à jour.")
    return followup(request, repair)


@repair_access_required
@require_POST
def report_update(request, pk):
    repair = get_object_or_404(items(request.user), pk=pk)
    if not can_manage(request.user, repair):
        raise PermissionDenied
    form = ReportForm(request.POST, instance=repair)
    if form.is_valid():
        try:
            save_report(request.user, pk, form.cleaned_data, resolve=request.POST.get("action") == "resolve")
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Le compte rendu a été enregistré." if request.POST.get("action") != "resolve" else "Réparation résolue : historique et documents PDF disponibles.")
            return followup(request, repair)
    # ModelForms modify the in-memory instance during validation; reload canonical state.
    repair = get_object_or_404(items(request.user), pk=pk)
    return render(request, "repairs/detail.html", detail_context(request, repair, form))


@repair_access_required
@require_POST
def message(request, pk):
    repair = get_object_or_404(items(request.user), pk=pk)
    try:
        send_message(request.user, pk, request.POST.get("body", ""))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Votre message a été envoyé.")
    return followup(request, repair)


@never_cache
@repair_access_required
def cancel(request, pk):
    repair = get_object_or_404(items(request.user), pk=pk)
    if request.method == "POST":
        try:
            change_status(request.user, pk, "cancelled", request.POST.get("reason", "")[:250])
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "La demande a été annulée. Les composants utilisés ont été retournés au stock.")
        return followup(request, repair)
    return render(request, "repairs/cancel.html", context(request, repair=repair))


@never_cache
@repair_access_required
@require_GET
def photo(request, pk):
    repair = get_object_or_404(visible_repairs(request.user), pk=pk)
    if not repair.photo:
        raise Http404
    try:
        response = FileResponse(repair.photo.open("rb"), content_type="image/jpeg")
    except FileNotFoundError:
        raise Http404 from None
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="photo-panne.jpg"'
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response
