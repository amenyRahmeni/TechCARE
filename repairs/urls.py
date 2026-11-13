from django.urls import path
from . import views

app_name = "repairs"
urlpatterns = [path("", views.request_list, name="list"), path("nouvelle/", views.request_create, name="create"), path("<int:pk>/", views.detail, name="detail"), path("<int:pk>/affecter/", views.assign, name="assign"), path("<int:pk>/statut/", views.status_update, name="status"), path("<int:pk>/compte-rendu/", views.report_update, name="report"), path("<int:pk>/message/", views.message, name="message"), path("<int:pk>/annuler/", views.cancel, name="cancel"), path("<int:pk>/photo/", views.photo, name="photo")]
urlpatterns.insert(2, path("techniciens/", views.technicians, name="technicians"))
