from django.urls import path
from . import views
from . import marketplace_views as showcase

app_name = "inventory"
urlpatterns = [
    path("", showcase.catalog, name="catalog"),
    path("mes-annonces/", showcase.catalog, {"mine": True}, name="my_listings"),
    path("deposer/", showcase.listing_form, name="listing_create"),
    path("annonces/<int:pk>/", showcase.detail, name="listing_detail"),
    path("annonces/<int:pk>/modifier/", showcase.listing_form, name="listing_update"),
    path("annonces/<int:pk>/statut/", showcase.status_update, name="listing_status"),
    path("annonces/<int:pk>/photo/", showcase.photo, name="listing_photo"),
    path("stock/", views.catalog, name="stock_catalog"),
    path("stock/<int:pk>/", views.detail, name="detail"),
    path("mouvements/", views.movements, name="movements"),
    path("utiliser/", views.consume, name="consume"),
    path("utilisations/<int:pk>/retour/", views.usage_return, name="return"),
]
