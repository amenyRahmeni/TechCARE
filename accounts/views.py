import json

import jwt
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import ProfileForm, RegistrationForm
from .services import claim_email, register
from .tokens import issue_token, token_user


@never_cache
def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            user = register(form)
        except (IntegrityError, ValidationError):
            form.add_error(None, "L’adresse e-mail est déjà utilisée. Vérifiez vos informations et réessayez.")
        else:
            login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
            messages.success(request, "Bienvenue chez TECHcare. Votre compte client est actif.")
            return redirect("maintenance:pc_list")
    return render(request, "registration/signup.html", {"form": form})


@login_required
@never_cache
def profile(request):
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                claim_email(user)
        except (IntegrityError, ValidationError):
            form.add_error("email", "Cette adresse e-mail est déjà utilisée.")
        else:
            messages.success(request, "Votre profil a été mis à jour.")
            return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "active_page": "profile",
                  "workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html"})


class ChangePasswordView(PasswordChangeView):
    template_name = "accounts/password.html"
    success_url = reverse_lazy("accounts:profile")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(active_page="profile", workspace_base="backoffice/base.html" if self.request.user.is_staff else "base.html")
        for field in data["form"].fields.values():
            field.widget.attrs["class"] = "form-input"
        return data

    def form_valid(self, form):
        messages.success(self.request, "Votre mot de passe a été changé.")
        return super().form_valid(form)


@never_cache
@require_POST
def token(request):
    # CSRF remains enforced. No JWT is written into browser storage.
    try:
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST
        if not isinstance(data, dict) or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
            raise ValueError()
        if len(data["email"]) > 254 or len(data["password"]) > 1024:
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "E-mail et mot de passe requis."}, status=400)
    user = authenticate(request, username=data["email"], password=data["password"])
    if not user:
        return JsonResponse({"error": "Identifiants incorrects ou compte suspendu."}, status=401)
    return JsonResponse({"access_token": issue_token(user), "token_type": "Bearer", "expires_in": 1200})


@never_cache
@require_GET
def me(request):
    header = request.headers.get("Authorization", "")
    try:
        if not header.startswith("Bearer ") or len(header) > 4096:
            raise jwt.InvalidTokenError()
        user = token_user(header[7:])
    except jwt.InvalidTokenError:
        response = JsonResponse({"error": "Jeton invalide ou expiré."}, status=401)
        response["WWW-Authenticate"] = "Bearer"
        return response
    from appointments.permissions import is_technician
    return JsonResponse({"id": user.pk, "username": user.username, "email": user.email,
                         "name": user.get_full_name(), "role": "admin" if user.is_staff else "technician" if is_technician(user) else "client"})
