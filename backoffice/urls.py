from django.urls import path

from appointments import views as workflow
from . import views

app_name = "backoffice"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("comptes/", views.accounts, name="accounts"),
    path("comptes/nouveau/", views.account_form, name="account_create"),
    path("comptes/<int:pk>/modifier/", views.account_form, name="account_update"),
    path("comptes/<int:pk>/activation/", views.account_state, name="account_state"),
    path("techniciens/", views.technicians, name="technicians"),
    path("ordinateurs/", views.pcs, name="pcs"),
    path("ordinateurs/nouveau/", views.pc_form, name="pc_create"),
    path("ordinateurs/<int:pk>/", views.pc_detail, name="pc_detail"),
    path("ordinateurs/<int:pk>/modifier/", views.pc_form, name="pc_update"),
    path("ordinateurs/<int:pk>/supprimer/", views.pc_delete, name="pc_delete"),
    path("regles/", views.rules, name="rules"),
    path("regles/nouvelle/", views.rule_form, name="rule_create"),
    path("regles/<int:pk>/modifier/", views.rule_form, name="rule_update"),
    path("rendez-vous/", views.staff_required(workflow.appointment_list), name="list"),
    path("rendez-vous/nouveau/", views.staff_required(workflow.appointment_form), name="create"),
    path("rendez-vous/disponibilites/", views.staff_required(workflow.availability), name="availability"),
    path("rendez-vous/<int:pk>/", views.staff_required(workflow.detail), name="detail"),
    path("rendez-vous/<int:pk>/modifier/", views.staff_required(workflow.appointment_form), name="update"),
    path("rendez-vous/<int:pk>/annuler/", views.staff_required(workflow.cancel), name="cancel"),
    path("rendez-vous/<int:pk>/statut/", views.staff_required(workflow.status_update), name="status_update"),
    path("rendez-vous/<int:pk>/intervention/", views.staff_required(workflow.intervention_update), name="intervention_update"),
    path("documents/", views.staff_required(workflow.documents), name="documents"),
    path("documents/<int:pk>/<str:kind>.pdf", views.staff_required(workflow.download_pdf), name="pdf"),
]
