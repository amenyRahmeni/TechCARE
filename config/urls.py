from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from appointments.views import WorkspaceLoginView

urlpatterns = [
    path("backoffice/", include("backoffice.urls")),
    path("admin/", admin.site.urls),
    path("connexion/", WorkspaceLoginView.as_view(template_name="registration/login.html"), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("appointments.urls")),
    path("", include("maintenance.urls")),
]
