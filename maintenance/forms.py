from django import forms
from django.utils import timezone

from .models import PC


class PCForm(forms.ModelForm):
    class Meta:
        model = PC
        fields = ["name", "device_type", "brand", "model", "serial_number", "purchased_on", "operating_system", "processor", "ram_gb", "storage_gb", "storage_type", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex. Mon PC de travail", "autofocus": True}),
            "brand": forms.TextInput(attrs={"placeholder": "Ex. Dell", "list": "brands"}),
            "model": forms.TextInput(attrs={"placeholder": "Ex. Latitude 5420"}),
            "serial_number": forms.TextInput(attrs={"placeholder": "Facultatif"}),
            "operating_system": forms.TextInput(attrs={"placeholder": "Ex. Windows 11", "list": "systems"}),
            "processor": forms.TextInput(attrs={"placeholder": "Ex. Intel Core i5-1145G7"}),
            "ram_gb": forms.NumberInput(attrs={"placeholder": "16"}),
            "storage_gb": forms.NumberInput(attrs={"placeholder": "512"}),
            "purchased_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Un détail utile sur votre ordinateur…"}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.owner = owner
        self.fields["purchased_on"].widget.attrs["max"] = timezone.localdate().isoformat()
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-input"

    def full_clean(self):
        super().full_clean()
        for name, field in self.fields.items():
            if name in self._errors:
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"error_{name}"

    def clean(self):
        cleaned = super().clean()
        serial = (cleaned.get("serial_number") or "").strip() or None
        cleaned["serial_number"] = serial
        if serial and PC.objects.filter(owner=self.instance.owner, serial_number=serial).exclude(pk=self.instance.pk).exists():
            self.add_error("serial_number", "Vous avez déjà un PC avec ce numéro de série.")
        bought = cleaned.get("purchased_on")
        if bought and self.instance.pk and self.instance.maintenance_records.filter(completed_on__lt=bought).exists():
            self.add_error("purchased_on", "La date d’achat ne peut pas être après une maintenance existante.")
        return cleaned
