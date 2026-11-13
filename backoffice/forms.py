from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError

from appointments.models import Technician
from maintenance.forms import PCForm
from maintenance.models import MaintenanceRule

User = get_user_model()


def style_fields(form):
    for field in form.fields.values():
        field.widget.attrs["class"] = "form-input"


class AccountForm(forms.ModelForm):
    def clean_email(self):
        from accounts.forms import clean_email
        return clean_email(self.cleaned_data.get("email", ""), self.instance.pk)

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=value).exclude(pk=self.instance.pk).exists() or User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cet identifiant est déjà utilisé.")
        return value

    role = forms.ChoiceField(label="Rôle", choices=[("client", "Client"), ("technician", "Technicien"), ("admin", "Administrateur")])
    specialty = forms.CharField(label="Spécialité du technicien", max_length=120, required=False)
    is_available = forms.BooleanField(label="Accepte de nouveaux rendez-vous", required=False, initial=True)
    skills = forms.MultipleChoiceField(label="Compétences de réparation", choices=[("hardware", "Matériel"), ("software", "Logiciel / système"), ("network", "Réseau")], required=False, help_text="Sans sélection, les compétences sont déduites de la spécialité ; maintenance générale : les trois domaines.")
    password1 = forms.CharField(label="Mot de passe", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), help_text="Au moins 8 caractères. Évitez les mots de passe courants et uniquement numériques.")
    password2 = forms.CharField(label="Confirmer le mot de passe", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {"username": "Identifiant", "first_name": "Prénom", "last_name": "Nom", "email": "Adresse e-mail"}

    def __init__(self, *args, actor, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        if not actor.is_superuser:
            self.fields["role"].choices = self.fields["role"].choices[:2]
        if self.instance.pk:
            profile = getattr(self.instance, "technician_profile", None)
            self.initial["role"] = "admin" if self.instance.is_staff else "technician" if profile else "client"
            if profile:
                self.initial.update(specialty=profile.specialty, is_available=profile.is_available, skills=profile.skills)
            self.fields["password1"].label = "Nouveau mot de passe"
            self.fields["password1"].help_text = "Laissez les deux champs vides pour conserver le mot de passe actuel."
        else:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
            self.initial.setdefault("role", "client")
        style_fields(self)

    def clean(self):
        data = super().clean()
        role = data.get("role")
        current = "admin" if self.instance.is_staff else "technician" if Technician.objects.filter(user_id=self.instance.pk).exists() else "client"
        if self.instance.pk == self.actor.pk and role != current:
            self.add_error("role", "Vous ne pouvez pas changer votre propre rôle.")
        if self.instance.is_superuser and role != "admin":
            self.add_error("role", "Le rôle de ce superadministrateur doit être conservé.")
        profile = getattr(self.instance, "technician_profile", None)
        if profile and role != "technician" and (profile.appointments.exists() or profile.repair_requests.exists() or profile.component_listings.exists()):
            self.add_error("role", "Ce technicien possède des rendez-vous, des réparations ou des annonces. Conservez son rôle et désactivez son compte si nécessaire.")
        if role == "technician" and not data.get("specialty"):
            self.add_error("specialty", "Indiquez la spécialité du technicien.")
        if role == "technician" and not data.get("skills"):
            specialty = data.get("specialty", "").casefold()
            data["skills"] = ["hardware"] if "matériel" in specialty else ["software"] if "logiciel" in specialty else ["network"] if "réseau" in specialty else ["hardware", "software", "network"]
        password = data.get("password1")
        if password != data.get("password2"):
            self.add_error("password2", "Les deux mots de passe doivent être identiques.")
        if password:
            candidate = User(username=data.get("username", ""), first_name=data.get("first_name", ""), last_name=data.get("last_name", ""), email=data.get("email", ""))
            try:
                password_validation.validate_password(password, candidate)
            except ValidationError as error:
                self.add_error("password1", error)
        return data


class AdminPCForm(PCForm):
    owner = forms.ModelChoiceField(label="Propriétaire", queryset=User.objects.none())

    def __init__(self, *args, actor, **kwargs):
        instance = kwargs.get("instance")
        data = args[0] if args else None
        owner = instance.owner if instance else actor
        if not instance and data:
            raw = data.get("owner", "")
            if raw.isdigit():
                owner = User.objects.filter(pk=int(raw), is_active=True).first() or actor
        super().__init__(*args, owner=owner, **kwargs)
        self.fields["owner"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.order_fields(["owner"] + list(PCForm.Meta.fields))
        if instance:
            self.fields["owner"].queryset = User.objects.filter(pk=instance.owner_id)
            self.fields["owner"].initial = instance.owner_id
            self.fields["owner"].disabled = True
            self.fields["owner"].help_text = "Le propriétaire reste associé à l’historique de cet ordinateur."
        self.fields["owner"].widget.attrs["class"] = "form-input"

    def clean(self):
        data = super().clean()
        if data.get("owner"):
            self.instance.owner = data["owner"]
        return data


class RuleForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRule
        fields = ["code", "title", "criterion", "threshold", "priority", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
