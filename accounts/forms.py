from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()


def clean_email(value, user_id=None):
    value = value.strip().lower()
    if value and (User.objects.filter(email__iexact=value).exclude(pk=user_id).exists()
                  or User.objects.filter(username__iexact=value).exclude(pk=user_id).exists()):
        raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
    return value


def style(form):
    for field in form.fields.values():
        field.widget.attrs["class"] = "form-input"


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="E-mail ou identifiant", max_length=254,
                               widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Adresse e-mail", max_length=254)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "last_name", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = ""
        self.fields["first_name"].widget.attrs["autofocus"] = True
        style(self)

    def clean_email(self):
        return clean_email(self.cleaned_data["email"])


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "Prénom", "last_name": "Nom", "email": "Adresse e-mail"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        style(self)

    def clean_email(self):
        return clean_email(self.cleaned_data["email"], self.instance.pk)
