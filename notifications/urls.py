from django.urls import path

from . import views

app_name = "notifications"
urlpatterns = [
    path("", views.inbox, name="list"),
    path("flux/", views.feed, name="feed"),
    path("tout-lire/", views.read_all, name="read_all"),
    path("<int:pk>/lire/", views.read, name="read"),
    path("<int:pk>/non-lue/", views.read, {"value": False}, name="unread"),
    path("<int:pk>/ouvrir/", views.visit, name="visit"),
    path("push/abonnement/", views.subscribe, name="subscribe"),
    path("push/desactiver/", views.unsubscribe, name="unsubscribe"),
    path("push/session/", views.push_session, name="push_session"),
    path("service-worker.js", views.service_worker, name="service_worker"),
]
