from django.urls import path

from . import views

app_name = "appointments"
urlpatterns = [
    path("rendez-vous/", views.appointment_list, name="list"),
    path("rendez-vous/nouveau/", views.appointment_form, name="create"),
    path("rendez-vous/disponibilites/", views.availability, name="availability"),
    path("rendez-vous/<int:pk>/", views.detail, name="detail"),
    path("rendez-vous/<int:pk>/modifier/", views.appointment_form, name="update"),
    path("rendez-vous/<int:pk>/annuler/", views.cancel, name="cancel"),
    path("rendez-vous/<int:pk>/statut/", views.status_update, name="status_update"),
    path("rendez-vous/<int:pk>/intervention/", views.intervention_update, name="intervention_update"),
    path("documents/", views.documents, name="documents"),
    path("documents/<int:pk>/<str:kind>.pdf", views.download_pdf, name="pdf"),
]
