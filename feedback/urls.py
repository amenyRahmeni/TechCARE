from django.urls import path
from . import views

app_name = "feedback"
urlpatterns = [path("", views.overview, name="list"), path("<str:kind>/<int:pk>/evaluer/", views.create, name="create")]
