from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("inscription/", views.signup, name="signup"),
    path("mon-profil/", views.profile, name="profile"),
    path("mon-profil/mot-de-passe/", views.ChangePasswordView.as_view(), name="password"),
    path("api/auth/token/", views.token, name="token"),
    path("api/auth/me/", views.me, name="me"),
]
