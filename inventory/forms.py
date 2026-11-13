import uuid

from django import forms

from appointments.forms import StyledFormMixin
from appointments.permissions import visible_appointments
from repairs.permissions import visible_repairs
from .models import Category, SparePart


class ComponentForm(StyledFormMixin, forms.ModelForm):
    opening_stock = forms.IntegerField(label="Stock initial", min_value=0, max_value=100000, initial=0, required=False)

    class Meta:
        model = SparePart
        fields = ["category", "reference", "name", "brand", "description", "unit_price", "low_stock_threshold", "is_active", "device_type", "compatible_brands", "compatible_models", "ram_type", "ram_format", "storage_interface", "cpu_socket", "compatibility_notes"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "compatible_models": forms.Textarea(attrs={"rows": 3}), "unit_price": forms.NumberInput(attrs={"step": "0.001", "min": "0"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop("opening_stock")
        self.style_fields()


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "code", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class StockForm(StyledFormMixin, forms.Form):
    delta = forms.IntegerField(label="Variation de stock", min_value=-100000, max_value=100000, help_text="Ex. +10 pour une réception, −2 pour une correction d’inventaire.")
    reason = forms.CharField(label="Motif", max_length=250)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class UseForm(StyledFormMixin, forms.Form):
    component = forms.ModelChoiceField(label="Composant", queryset=SparePart.objects.none())
    quantity = forms.IntegerField(label="Quantité", min_value=1, max_value=1000, initial=1)
    target = forms.ChoiceField(label="Réparation / intervention")
    token = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, actor, fixed_target=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["component"].queryset = SparePart.objects.filter(is_active=True).select_related("category")
        repairs = visible_repairs(actor).filter(status__in=["diagnosis", "repair", "waiting"])
        appointments = visible_appointments(actor).filter(status__in=["diagnosis", "repair"])
        if not actor.is_staff:
            repairs = repairs.filter(technician__user=actor)
            appointments = appointments.filter(technician__user=actor)
        choices = [(f"repair:{item.pk}", f"{item.reference} · {item.pc.name}") for item in repairs.select_related("pc")]
        choices += [(f"appointment:{item.pk}", f"RDV #{item.pk} · {item.pc.name}") for item in appointments.select_related("pc")]
        if fixed_target:
            choices = [choice for choice in choices if choice[0] == fixed_target]
            self.fields["target"].widget = forms.HiddenInput()
            self.initial["target"] = fixed_target
        self.fields["target"].choices = choices
        self.initial["token"] = uuid.uuid4()
        self.style_fields()
