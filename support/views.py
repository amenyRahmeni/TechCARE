from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from backoffice.views import audit, staff_required
from .forms import FAQForm
from .models import FAQItem


def filtered(request, rows):
    q = request.GET.get("q", "").strip()[:160]
    category = request.GET.get("category", "")
    # AND across up to eight terms, OR across question / answer for each term.
    for term in q.split()[:8]:
        rows = rows.filter(Q(question__icontains=term) | Q(answer__icontains=term))
    if category in FAQItem.Category.values:
        rows = rows.filter(category=category)
    return rows, q, category


@login_required
def faq(request):
    rows, q, category = filtered(request, FAQItem.objects.filter(is_active=True))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "support/faq.html", {"active_page": "faq", "q": q, "category": category,
                  "categories": FAQItem.Category.choices, "page_obj": Paginator(rows, 12).get_page(request.GET.get("page")),
                  "page_query": params.urlencode(), "workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html"})


@staff_required
def manage(request):
    rows, q, category = filtered(request, FAQItem.objects.all())
    state = request.GET.get("state", "")
    if state in ("published", "draft"):
        rows = rows.filter(is_active=state == "published")
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "support/manage.html", {"active_page": "faq", "q": q, "category": category, "state": state,
                  "categories": FAQItem.Category.choices, "page_obj": Paginator(rows, 12).get_page(request.GET.get("page")), "page_query": params.urlencode()})


@staff_required
def edit(request, pk=None):
    item = get_object_or_404(FAQItem, pk=pk) if pk else None
    form = FAQForm(request.POST if request.method == "POST" else None, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save()
            audit(request.user, item, CHANGE if pk else ADDITION, "Question FAQ enregistrée depuis le backoffice.")
        messages.success(request, "La question a été enregistrée.")
        return redirect("backoffice:faq")
    return render(request, "backoffice/form.html", {"active_page": "faq", "form": form,
                  "title": "Modifier la question" if pk else "Ajouter une question", "subtitle": "Des réponses claires pour accompagner vos clients.", "back_url": "backoffice:faq"})


@staff_required
def delete(request, pk):
    item = get_object_or_404(FAQItem, pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            audit(request.user, item, DELETION, "Question FAQ supprimée depuis le backoffice.")
            item.delete()
        messages.success(request, "La question a été supprimée.")
        return redirect("backoffice:faq")
    return render(request, "backoffice/confirm.html", {"active_page": "faq", "title": "Supprimer cette question ?", "description": item.question,
                  "back_url": "backoffice:faq", "button_label": "Supprimer la question"})
