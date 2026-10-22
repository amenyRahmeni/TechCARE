from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from maintenance.models import PC
from .forms import AppointmentForm, InterventionForm, PartLineFormSet
from .models import Appointment, Intervention, Technician
from .pdf import generate_pdf
from .permissions import can_manage_intervention, is_technician, visible_appointments, visible_invoices
from .scheduling import day_slots
from .services import TRANSITIONS, book_appointment, cancel_appointment, save_intervention, update_status


class WorkspaceLoginView(LoginView):
    def get_default_redirect_url(self):
        if self.request.user.is_staff:
            return reverse("backoffice:dashboard")
        if is_technician(self.request.user):
            return reverse("appointments:list")
        return super().get_default_redirect_url()


def _appointments(user):
    return visible_appointments(user).select_related("client", "pc", "technician__user", "intervention")


def _followup(request, appointment):
    namespace = "backoffice" if request.resolver_match.namespace == "backoffice" else "appointments"
    return redirect(f"{namespace}:detail", pk=appointment.pk)


@login_required
def appointment_list(request):
    appointments = _appointments(request.user)
    scope = request.GET.get("scope", "assigned" if is_technician(request.user) and not request.user.is_staff else "all")
    if scope == "assigned":
        appointments = appointments.filter(technician__user=request.user)
    elif scope == "client":
        appointments = appointments.filter(client=request.user)
    counts = {"total": appointments.count(), "pending": appointments.filter(status="pending").count(), "active": appointments.filter(status__in=["confirmed", "diagnosis", "repair"]).count(), "completed": appointments.filter(status="completed").count()}
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()[:100]
    if status in Appointment.Status.values:
        appointments = appointments.filter(status=status)
    if q:
        appointments = appointments.filter(Q(pc__name__icontains=q) | Q(reason__icontains=q) | Q(client__username__icontains=q) | Q(client__first_name__icontains=q) | Q(client__last_name__icontains=q) | Q(technician__user__first_name__icontains=q) | Q(technician__user__last_name__icontains=q))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "appointments/list.html", {"active_page": "appointments", "page_obj": Paginator(appointments, 10).get_page(request.GET.get("page")), "counts": counts, "status": status, "statuses": Appointment.Status.choices, "q": q, "scope": scope, "page_query": params.urlencode()})


@login_required
def appointment_form(request, pk=None):
    appointment = get_object_or_404(_appointments(request.user), pk=pk) if pk else None
    if appointment and not appointment.can_modify:
        messages.error(request, "Ce rendez-vous ne peut plus être modifié à cette étape.")
        return _followup(request, appointment)
    initial = {"reason": request.GET.get("motif", "")[:150]}
    selected_pc = request.GET.get("pc", "")
    if selected_pc.isdigit():
        initial["pc"] = int(selected_pc)
    form = AppointmentForm(request.POST if request.method == "POST" else None, actor=request.user, appointment=appointment, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            saved = book_appointment(request.user, form.cleaned_data, pk)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Rendez-vous modifié. Le nouveau créneau est en attente de confirmation." if pk else "Votre rendez-vous a été réservé. Le technicien peut maintenant le confirmer.")
            if not request.user.is_staff and saved.client_id != request.user.pk and saved.technician.user_id != request.user.pk:
                return redirect("appointments:list")
            return _followup(request, saved)
    return render(request, "appointments/form.html", {"active_page": "appointments", "form": form, "appointment": appointment, "technicians": form.fields["technician"].queryset})


def _detail_context(request, appointment, form=None, formset=None):
    intervention = getattr(appointment, "intervention", None)
    manager = can_manage_intervention(request.user, appointment)
    invoice = getattr(intervention, "invoice", None) if intervention else None
    workflow = [("pending", "En attente"), ("confirmed", "Confirmé"), ("diagnosis", "Diagnostic"), ("repair", "Réparation"), ("completed", "Terminé")]
    current = next((i for i, (value, _) in enumerate(workflow) if value == appointment.status), -1)
    return {
        "active_page": "appointments", "appointment": appointment, "intervention": intervention,
        "can_manage": manager, "can_download": request.user.is_staff or appointment.client_id == request.user.pk,
        "status_choices": [(value, Appointment.Status(value).label) for value in TRANSITIONS.get(appointment.status, ())],
        "can_complete": Appointment.Status.COMPLETED in TRANSITIONS.get(appointment.status, ()),
        "intervention_form": form if form is not None else InterventionForm(instance=intervention),
        "parts_formset": formset if formset is not None else PartLineFormSet(instance=intervention, prefix="parts"),
        "invoice": invoice,
        "workflow_steps": [{"label": label, "state": "current" if i == current else "done" if i < current else "future"} for i, (_, label) in enumerate(workflow)],
    }


@login_required
def detail(request, pk):
    appointment = get_object_or_404(_appointments(request.user), pk=pk)
    return render(request, "appointments/detail.html", _detail_context(request, appointment))


@login_required
def cancel(request, pk):
    appointment = get_object_or_404(_appointments(request.user), pk=pk)
    if not appointment.can_modify:
        messages.error(request, "Ce rendez-vous ne peut plus être annulé à cette étape.")
        return _followup(request, appointment)
    if request.method == "POST":
        try:
            appointment = cancel_appointment(request.user, pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Le rendez-vous a été annulé et le créneau libéré.")
        return _followup(request, appointment)
    return render(request, "appointments/cancel.html", {"active_page": "appointments", "appointment": appointment})


@login_required
@require_POST
def status_update(request, pk):
    appointment = get_object_or_404(_appointments(request.user), pk=pk)
    if not can_manage_intervention(request.user, appointment):
        raise PermissionDenied
    try:
        update_status(request.user, pk, request.POST.get("status", ""))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Le statut du rendez-vous a été mis à jour.")
    return _followup(request, appointment)


@login_required
@require_POST
def intervention_update(request, pk):
    appointment = get_object_or_404(_appointments(request.user), pk=pk)
    if not can_manage_intervention(request.user, appointment):
        raise PermissionDenied
    if appointment.is_closed:
        messages.error(request, "Cette intervention est clôturée et reste en lecture seule.")
        return _followup(request, appointment)
    intervention = get_object_or_404(Intervention, appointment=appointment)
    form = InterventionForm(request.POST, instance=intervention)
    formset = PartLineFormSet(request.POST, instance=intervention, prefix="parts")
    if form.is_valid() and formset.is_valid():
        lines = []
        valid = True
        for part_form in formset.forms:
            data = part_form.cleaned_data
            part_id = data.get("id")
            if part_id and part_id.intervention_id != intervention.pk:
                part_form.add_error(None, "Cette ligne n’appartient pas à l’intervention.")
                valid = False
            if data and not data.get("DELETE") and data.get("name"):
                lines.append({key: data[key] for key in ("name", "quantity", "unit_price")})
        if valid:
            try:
                save_intervention(request.user, pk, form.cleaned_data, lines, complete=request.POST.get("action") == "complete")
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Intervention terminée : historique, rapport et facture disponibles." if request.POST.get("action") == "complete" else "Le compte rendu et les coûts ont été enregistrés.")
                return _followup(request, appointment)
    # Rendering errors uses the submitted forms, without writing partial data.
    return render(request, "appointments/detail.html", _detail_context(request, appointment, form, formset), status=200)


@login_required
def availability(request):
    technician_id = request.GET.get("technician", "")
    if not technician_id.isdigit():
        return JsonResponse({"error": "Choisissez un technicien."}, status=400)
    technician = get_object_or_404(Technician, pk=int(technician_id), is_available=True, user__is_active=True)
    try:
        chosen_date = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        return JsonResponse({"error": "Choisissez une date valide."}, status=400)
    appointment = None
    appointment_id = request.GET.get("appointment", "")
    if appointment_id:
        if not appointment_id.isdigit():
            return JsonResponse({"error": "Rendez-vous invalide."}, status=400)
        appointment = get_object_or_404(visible_appointments(request.user), pk=int(appointment_id))
    pc = None
    pc_id = request.GET.get("pc", "")
    if pc_id:
        if not pc_id.isdigit():
            return JsonResponse({"error": "Ordinateur invalide."}, status=400)
        pcs = PC.objects.all() if request.user.is_staff else PC.objects.filter(owner=request.user)
        if appointment and can_manage_intervention(request.user, appointment):
            pcs = PC.objects.filter(pk=appointment.pc_id) if not request.user.is_staff else pcs
        pc = get_object_or_404(pcs, pk=int(pc_id))
    return JsonResponse({"slots": day_slots(technician, chosen_date, pc, appointment), "note": "Horaires de Tunis · lundi au samedi, de 09:00 à 18:00."})


@login_required
def documents(request):
    invoices = visible_invoices(request.user).select_related("intervention__appointment__pc")
    q = request.GET.get("q", "").strip()[:100]
    counts = {"total": invoices.count(), "amount": invoices.aggregate(total=Sum("total_amount"))["total"] or 0}
    if q:
        invoices = invoices.filter(Q(number__icontains=q) | Q(snapshot__pc__name__icontains=q))
    return render(request, "appointments/documents.html", {"active_page": "documents", "page_obj": Paginator(invoices, 10).get_page(request.GET.get("page")), "q": q, "counts": counts})


@login_required
def download_pdf(request, pk, kind):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    if kind not in ("report", "invoice"):
        from django.http import Http404
        raise Http404
    pdf = generate_pdf(invoice, kind)
    prefix = "rapport" if kind == "report" else "facture"
    response = FileResponse(pdf, as_attachment=True, filename=f"{prefix}-{invoice.number}.pdf", content_type="application/pdf")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
