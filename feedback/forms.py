from django import forms
from .models import Feedback


class FeedbackForm(forms.ModelForm):
    rating = forms.TypedChoiceField(label="Votre note", choices=[(i, f"{i} étoile{'s' if i > 1 else ''}") for i in range(1, 6)], coerce=int, widget=forms.RadioSelect)

    class Meta:
        model = Feedback
        fields = ["rating", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"class": "form-input", "rows": 5, "maxlength": 2000, "placeholder": "Comment s’est passée votre prise en charge ?"})}

    def clean_comment(self):
        value = self.cleaned_data["comment"].strip()
        if not value:
            raise forms.ValidationError("Ajoutez un commentaire sur la réparation.")
        return value
