from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from appointments.models import Appointment, Technician
from appointments.permissions import is_technician_workspace
from repairs.models import RepairRequest
from .forms import FeedbackForm
from .models import Feedback
from .services import source_queryset, submit_feedback


@login_required
def overview(request):
    rows = Feedback.objects.select_related("client", "technician__user", "appointment__pc", "repair__pc")
    tech = is_technician_workspace(request.user)
    if tech:
        rows = rows.filter(technician__user=request.user)
    elif not request.user.is_staff:
        rows = rows.filter(client=request.user)
    stats = rows.aggregate(average=Avg("rating"), count=Count("pk"))
    distribution = [{"rating": value, "count": rows.filter(rating=value).count()} for value in range(5, 0, -1)]
    q = request.GET.get("q", "").strip()[:100]
    rating = request.GET.get("rating", "")
    technician_id = request.GET.get("technician", "")
    if q:
        rows = rows.filter(Q(comment__icontains=q) | Q(technician__user__first_name__icontains=q) | Q(client__username__icontains=q))
    if rating in {"1", "2", "3", "4", "5"}:
        rows = rows.filter(rating=int(rating))
    if request.user.is_staff and technician_id.isdigit():
        rows = rows.filter(technician_id=int(technician_id))
    pending = []
    if not tech and not request.user.is_staff:
        for item in Appointment.objects.filter(client=request.user, status="completed", feedback__isnull=True).select_related("pc", "technician__user")[:12]:
            pending.append({"item": item, "kind": "appointment"})
        for item in RepairRequest.objects.filter(client=request.user, status="resolved", feedback__isnull=True).select_related("pc", "technician__user")[:12]:
            pending.append({"item": item, "kind": "repair"})
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "feedback/list.html", {"active_page": "feedback", "workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html",
                  "page_obj": Paginator(rows, 12).get_page(request.GET.get("page")), "stats": stats, "distribution": distribution,
                  "pending": pending, "q": q, "rating": rating, "technician_id": technician_id,
                  "technicians": Technician.objects.select_related("user") if request.user.is_staff else [], "page_query": params.urlencode()})


@login_required
def create(request, kind, pk):
    if request.user.is_staff or is_technician_workspace(request.user):
        raise PermissionDenied("Les avis sont réservés aux clients concernés.")
    try:
        sources = source_queryset(kind)
    except ValidationError:
        raise Http404
    source = get_object_or_404(sources.select_related("pc", "technician__user"), pk=pk, client=request.user)
    if source.status != ("completed" if kind == "appointment" else "resolved"):
        messages.error(request, "Vous pourrez donner votre avis après la clôture.")
        return redirect(source.get_absolute_url())
    existing = Feedback.objects.filter(**{kind: source}).first()
    if existing:
        return redirect("feedback:list")
    form = FeedbackForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            submit_feedback(request.user, kind, pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Merci, votre avis a été enregistré et transmis au technicien.")
            return redirect("feedback:list")
    return render(request, "feedback/form.html", {"form": form, "source": source, "kind": kind, "active_page": "feedback"})
