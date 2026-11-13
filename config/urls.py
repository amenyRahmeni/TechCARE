from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from appointments.views import WorkspaceLoginView

urlpatterns = [
    path("predictions/", include("predictions.urls")),
    path("", include("accounts.urls")),
    path("avis/", include("feedback.urls")),
    path("aide/", include("support.urls")),
    path("reparations/", include("repairs.urls")),
    path("composants/", include("inventory.urls")),
    path("notifications/", include("notifications.urls")),
    path("backoffice/", include("backoffice.urls")),
    path("admin/", admin.site.urls),
    path("connexion/", WorkspaceLoginView.as_view(template_name="registration/login.html"), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("appointments.urls")),
    path("", include("maintenance.urls")),
]
