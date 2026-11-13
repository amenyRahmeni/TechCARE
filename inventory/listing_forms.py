import re
import uuid

from django import forms

from appointments.forms import StyledFormMixin
from repairs.uploads import clean_photo
from .models import ComponentListing


class ListingForm(StyledFormMixin, forms.ModelForm):
    photo = forms.FileField(label="Photo du composant", required=False, help_text="JPEG, PNG ou WebP ; 5 Mo maximum.", widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "data-photo-input": ""}))
    remove_photo = forms.BooleanField(label="Supprimer la photo actuelle", required=False)
    submission_token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    class Meta:
        model = ComponentListing
        fields = ["title", "category", "brand", "reference", "condition", "unit_price", "quantity", "description", "compatibility_notes", "location", "contact_phone", "contact_email", "photo"]
        widgets = {"title": forms.TextInput(attrs={"placeholder": "Ex. Barrette RAM DDR4 8 Go SO-DIMM"}), "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Caractéristiques, état, tests effectués et accessoires inclus…"}), "unit_price": forms.NumberInput(attrs={"step": "0.001", "min": "0"}), "quantity": forms.NumberInput(attrs={"min": "1", "max": "100000"}), "location": forms.TextInput(attrs={"placeholder": "Ex. Tunis, Centre-ville"}), "contact_phone": forms.TextInput(attrs={"placeholder": "+216 22 123 456", "inputmode": "tel"}), "contact_email": forms.EmailInput(attrs={"placeholder": "Votre e-mail de contact"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop("submission_token")
            if not self.instance.photo:
                self.fields.pop("remove_photo")
        else:
            self.fields.pop("remove_photo")
        self.style_fields()

    def clean_photo(self):
        upload = self.cleaned_data.get("photo")
        # The initial ImageFieldFile is not a new upload and must stay untouched.
        return clean_photo(upload) if "photo" in self.files else None

    def clean_contact_phone(self):
        phone = self.cleaned_data.get("contact_phone", "").strip()
        if phone and (not re.fullmatch(r"\+?[0-9 ()-]+", phone) or len(re.sub(r"[^0-9]", "", phone)) < 6):
            raise forms.ValidationError("Indiquez un téléphone valide, par exemple +216 22 123 456.")
        return phone

    def clean(self):
        data = super().clean()
        if not data.get("contact_phone") and not data.get("contact_email"):
            raise forms.ValidationError("Indiquez un téléphone ou un e-mail pour que les techniciens puissent vous contacter.")
        return data
