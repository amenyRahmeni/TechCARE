import uuid

from django import forms

from .campaigns import recipients
from .models import Notification, NotificationCampaign


class RecipientChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, user):
        role = "Technicien" if hasattr(user, "technician_profile") else "Client"
        name = user.get_full_name() or user.email or user.username
        return f"{name} · {role}" + (f" · {user.email}" if user.email and user.email != name else "")


class CampaignForm(forms.Form):
    token = forms.UUIDField(widget=forms.HiddenInput)
    audience = forms.ChoiceField(label="Envoyer à", choices=NotificationCampaign.Audience.choices, initial="clients")
    recipients = RecipientChoiceField(label="Choisir les destinataires", queryset=None, required=False, widget=forms.CheckboxSelectMultiple)
    title = forms.CharField(label="Titre", max_length=150, widget=forms.TextInput(attrs={"placeholder": "Ex. Horaires de l’atelier cette semaine"}))
    message = forms.CharField(label="Message", max_length=700, widget=forms.Textarea(attrs={"rows": 6, "placeholder": "Rédigez le message destiné aux clients ou aux techniciens…"}))
    level = forms.ChoiceField(label="Priorité", choices=Notification.Level.choices, initial="info")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["token"].initial = uuid.uuid4()
        self.fields["recipients"].queryset = recipients().select_related("technician_profile").order_by("first_name", "last_name", "pk")
        for name, field in self.fields.items():
            if name not in {"token", "recipients"}:
                field.widget.attrs["class"] = "form-input"

    def clean(self):
        data = super().clean()
        audience = data.get("audience")
        if audience == "selected":
            if not data.get("recipients"):
                self.add_error("recipients", "Choisissez au moins un destinataire.")
        elif audience and not recipients(audience).exists():
            self.add_error("audience", "Aucun compte actif ne correspond à ce public.")
        return data
