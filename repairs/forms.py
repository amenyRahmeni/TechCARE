from django import forms

from appointments.forms import StyledFormMixin
from appointments.models import Technician
from maintenance.models import PC
from .models import RepairRequest
from .uploads import clean_photo
from .permissions import qualified_technicians


class RequestForm(StyledFormMixin, forms.ModelForm):
    technician = forms.ModelChoiceField(label="Technicien qualifié", queryset=Technician.objects.none(), empty_label="Choisir un technicien", help_text="Seuls les techniciens actifs, disponibles et qualifiés pour la panne sont proposés.")
    photo = forms.FileField(label="Photo de la panne", required=False, help_text="JPEG, PNG ou WebP ; 5 Mo maximum. Facultative.", widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "data-photo-input": ""}))

    class Meta:
        model = RepairRequest
        fields = ["pc", "problem", "technician", "description", "technical_notes", "photo"]
        widgets = {"description": forms.Textarea(attrs={"rows": 6, "placeholder": "Que se passe-t-il ? Depuis quand ? Quels essais avez-vous effectués ?"}), "technical_notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Message d’erreur, contexte, périphériques concernés…"})}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pc"].queryset = PC.objects.filter(owner=actor)
        self.fields["pc"].empty_label = "Choisir l’ordinateur concerné"
        problem = self.data.get("problem") if self.is_bound else self.initial.get("problem")
        self.fields["technician"].queryset = qualified_technicians(problem) if problem in RepairRequest.Problem.values else Technician.objects.filter(is_available=True, user__is_active=True, user__is_staff=False).select_related("user")
        self.style_fields()

    def clean_photo(self):
        return clean_photo(self.cleaned_data.get("photo"))


class AssignmentForm(StyledFormMixin, forms.Form):
    technician = forms.ModelChoiceField(label="Technicien qualifié", queryset=Technician.objects.none())

    def __init__(self, *args, repair, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["technician"].queryset = qualified_technicians(repair.problem)
        self.style_fields()


class ReportForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = RepairRequest
        fields = ["diagnosis", "solution", "labour_cost"]
        widgets = {"diagnosis": forms.Textarea(attrs={"rows": 5}), "solution": forms.Textarea(attrs={"rows": 5}), "labour_cost": forms.NumberInput(attrs={"min": "0", "step": "0.001"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
