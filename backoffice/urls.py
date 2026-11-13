from django.urls import path

from appointments import views as workflow
from repairs import views as repairs
from inventory import views as inventory
from support import views as support
from feedback import views as feedback
from predictions import views as predictions
from notifications import admin_views as notifications
from . import views

app_name = "backoffice"
urlpatterns = [
    path("notifications/", notifications.overview, name="notifications"),
    path("notifications/nouvelle/", notifications.compose, name="notification_create"),
    path("notifications/<int:pk>/", notifications.detail, name="notification_detail"),
    path("notifications/<int:pk>/retirer/", notifications.withdraw, name="notification_withdraw"),
    path("prediction-ml/", predictions.manage, name="ml_model"),
    path("prediction-ml/gabarit.csv", predictions.dataset_template, name="ml_template"),
    path("avis/", views.staff_required(feedback.overview), name="feedback"),
    path("faq/", support.manage, name="faq"),
    path("faq/nouvelle/", support.edit, name="faq_create"),
    path("faq/<int:pk>/modifier/", support.edit, name="faq_update"),
    path("faq/<int:pk>/supprimer/", support.delete, name="faq_delete"),
    path("reparations/", views.staff_required(repairs.request_list), name="repair_list"),
    path("reparations/nouvelle/", views.staff_required(repairs.request_create), name="repair_create"),
    path("reparations/<int:pk>/", views.staff_required(repairs.detail), name="repair_detail"),
    path("reparations/<int:pk>/affecter/", views.staff_required(repairs.assign), name="repair_assign"),
    path("reparations/<int:pk>/statut/", views.staff_required(repairs.status_update), name="repair_status"),
    path("reparations/<int:pk>/compte-rendu/", views.staff_required(repairs.report_update), name="repair_report"),
    path("reparations/<int:pk>/message/", views.staff_required(repairs.message), name="repair_message"),
    path("reparations/<int:pk>/annuler/", views.staff_required(repairs.cancel), name="repair_cancel"),
    path("reparations/<int:pk>/photo/", views.staff_required(repairs.photo), name="repair_photo"),
    path("composants/", views.staff_required(inventory.catalog), name="components"),
    path("composants/nouveau/", views.staff_required(inventory.component_form), name="component_create"),
    path("composants/<int:pk>/", views.staff_required(inventory.detail), name="component_detail"),
    path("composants/<int:pk>/modifier/", views.staff_required(inventory.component_form), name="component_update"),
    path("composants/<int:pk>/stock/", views.staff_required(inventory.stock_adjust), name="stock_adjust"),
    path("stock/", views.staff_required(inventory.movements), name="stock"),
    path("categories/", views.staff_required(inventory.categories), name="categories"),
    path("categories/<int:pk>/modifier/", views.staff_required(inventory.categories), name="category_update"),
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
    path("rendez-vous/<int:pk>/message/", views.staff_required(workflow.message), name="message"),
    path("rendez-vous/<int:pk>/modifier/", views.staff_required(workflow.appointment_form), name="update"),
    path("rendez-vous/<int:pk>/annuler/", views.staff_required(workflow.cancel), name="cancel"),
    path("rendez-vous/<int:pk>/statut/", views.staff_required(workflow.status_update), name="status_update"),
    path("rendez-vous/<int:pk>/intervention/", views.staff_required(workflow.intervention_update), name="intervention_update"),
    path("documents/", views.staff_required(workflow.documents), name="documents"),
    path("documents/<int:pk>/<str:kind>.pdf", views.staff_required(workflow.download_pdf), name="pdf"),
]
