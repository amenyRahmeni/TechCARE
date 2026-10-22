from datetime import datetime, timedelta

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from maintenance.models import PC
from .models import Appointment, Intervention, PartLine, Technician
from .scheduling import validate_start, working_times


class StyledFormMixin:
    def style_fields(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")


class AppointmentForm(StyledFormMixin, forms.Form):
    pc = forms.ModelChoiceField(label="Ordinateur", queryset=PC.objects.none(), empty_label="Choisir un ordinateur")
    technician = forms.ModelChoiceField(label="Technicien", queryset=Technician.objects.none(), empty_label="Choisir un technicien")
    category = forms.ChoiceField(label="Type de demande", choices=Appointment.Category.choices)
    reason = forms.CharField(label="Motif du rendez-vous", max_length=150, widget=forms.TextInput(attrs={"placeholder": "Ex. Nettoyage et contrôle du ventilateur"}))
    date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    time = forms.ChoiceField(label="Créneau", choices=[])
    description = forms.CharField(label="Précisions", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Décrivez votre besoin pour aider le technicien à préparer le rendez-vous."}))

    def __init__(self, *args, actor, appointment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pc"].queryset = PC.objects.all() if actor.is_staff else PC.objects.filter(owner=actor)
        if appointment and not actor.is_staff and appointment.client_id != actor.pk:
            self.fields["pc"].queryset = PC.objects.filter(pk=appointment.pc_id)
        self.fields["technician"].queryset = Technician.objects.filter(is_available=True, user__is_active=True).select_related("user")
        self.fields["date"].widget.attrs.update({"min": timezone.localdate().isoformat(), "max": (timezone.localdate() + timedelta(days=365)).isoformat()})
        self.fields["time"].choices = [("", "Choisir un créneau")] + [(slot.strftime("%H:%M"), f"{slot:%H:%M} – {slot.hour + 1:02d}:00") for slot in working_times()]
        if appointment and not self.is_bound:
            local = timezone.localtime(appointment.starts_at)
            self.initial.update({"pc": appointment.pc_id, "technician": appointment.technician_id, "category": appointment.category, "reason": appointment.reason, "date": local.date(), "time": local.strftime("%H:%M"), "description": appointment.description})
        self.style_fields()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date") and cleaned.get("time"):
            starts = timezone.make_aware(datetime.combine(cleaned["date"], datetime.strptime(cleaned["time"], "%H:%M").time()))
            validate_start(starts)
            cleaned["starts_at"] = starts
        return cleaned


class InterventionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Intervention
        fields = ["diagnosis", "solution", "labour_cost"]
        widgets = {"diagnosis": forms.Textarea(attrs={"rows": 5}), "solution": forms.Textarea(attrs={"rows": 5}), "labour_cost": forms.NumberInput(attrs={"step": "0.001", "min": "0", "data-labour-cost": ""})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class PartLineForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PartLine
        fields = ["name", "quantity", "unit_price"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Ex. SSD 512 Go"}), "quantity": forms.NumberInput(attrs={"min": "1", "max": "1000", "data-part-quantity": ""}), "unit_price": forms.NumberInput(attrs={"min": "0", "step": "0.001", "data-part-price": ""})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


PartLineFormSet = inlineformset_factory(Intervention, PartLine, form=PartLineForm, extra=1, can_delete=True, max_num=20, validate_max=True, absolute_max=40)
