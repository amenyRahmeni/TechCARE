from django.urls import path
from . import views

app_name = "predictions"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pc/<int:pk>/", views.detail, name="detail"),
    path("pc/<int:pk>/analyser/", views.analyze, name="analyze"),
]
