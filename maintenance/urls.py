from django.urls import path
from . import views

app_name = "maintenance"
urlpatterns = [
    path("", views.pc_list, name="pc_list"),
    path("pc/ajouter/", views.pc_form, name="pc_create"),
    path("pc/<int:pk>/", views.pc_detail, name="pc_detail"),
    path("pc/<int:pk>/modifier/", views.pc_form, name="pc_update"),
    path("pc/<int:pk>/supprimer/", views.pc_delete, name="pc_delete"),
    path("historique/", views.history, name="history"),
    path("recommandations/", views.recommendations, name="recommendations"),
    path("recommandations/analyser/", views.analyze, name="analyze"),
]
