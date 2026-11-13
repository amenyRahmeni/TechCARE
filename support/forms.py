from django import forms
from .models import FAQItem


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQItem
        fields = ["question", "answer", "category", "position", "is_active"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 7})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-input"

    def clean_question(self):
        return self.cleaned_data["question"].strip()

    def clean_answer(self):
        return self.cleaned_data["answer"].strip()
