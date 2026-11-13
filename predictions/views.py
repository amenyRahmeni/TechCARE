from io import StringIO

from django.contrib import messages
from django.contrib.admin.models import ADDITION
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from backoffice.views import audit, staff_required
from maintenance.permissions import viewable_pcs
from .dataset import demo_rows, read_csv, write_csv
from .forms import TrainingCSVForm
from .models import FailureModel
from .services import analyze_pc, context_for_pc, current_model


@login_required
@never_cache
def dashboard(request):
    pcs = viewable_pcs(request.user).select_related("owner").order_by("name", "pk")
    q = request.GET.get("q", "").strip()[:100]
    if q:
        pcs = pcs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(model__icontains=q))
    page = Paginator(pcs, 12).get_page(request.GET.get("page"))
    for pc in page:
        pc.ml_latest = pc.failure_predictions.select_related("model").defer("model__forest").first()
    return render(request, "predictions/dashboard.html", {"active_page": "predictions", "page_obj": page, "q": q,
        "ml_model": current_model(), "workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html"})


@login_required
@never_cache
def detail(request, pk):
    pc = get_object_or_404(viewable_pcs(request.user).select_related("owner"), pk=pk)
    return render(request, "predictions/detail.html", {"active_page": "predictions", "pc": pc, **context_for_pc(pc),
        "prediction_history": pc.failure_predictions.select_related("model").defer("model__forest")[:6],
        "workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html"})


@login_required
@require_POST
def analyze(request, pk):
    pc = get_object_or_404(viewable_pcs(request.user), pk=pk)
    try:
        result = analyze_pc(request.user, pc.pk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Analyse de démonstration enregistrée." if result.model.is_demo else "Analyse enregistrée avec le modèle de l’atelier.")
    return redirect("predictions:detail", pk=pc.pk)


@staff_required
def manage(request):
    from .training import train_model
    form = TrainingCSVForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST":
        rows = None
        if request.POST.get("action") == "demo":
            rows = demo_rows()
        elif form.is_valid():
            try:
                rows = read_csv(form.cleaned_data["dataset"].read())
            except ValidationError as exc:
                form.add_error("dataset", exc)
        if rows is not None:
            try:
                model = train_model(rows, request.user)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                audit(request.user, model, ADDITION, "Modèle Random Forest entraîné depuis le backoffice.")
                messages.success(request, f"Modèle {model.short_version} entraîné et activé ({model.get_origin_display().lower()}).")
                return redirect("backoffice:ml_model")
    return render(request, "predictions/manage.html", {"active_page": "ml_model", "form": form,
        "ml_model": current_model(), "model_history": FailureModel.objects.defer("forest")[:8]})


@staff_required
def dataset_template(request):
    stream = StringIO()
    write_csv([], stream)
    response = HttpResponse(stream.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="techcare-dataset-template.csv"'
    response["Cache-Control"] = "private, no-store"
    return response
