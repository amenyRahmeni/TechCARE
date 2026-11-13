from django import forms


class TrainingCSVForm(forms.Form):
    dataset = forms.FileField(label="Jeu de données CSV", help_text="CSV UTF-8, 5 Mo maximum ; utilisez les colonnes du gabarit.", widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": ".csv,text/csv"}))

    def clean_dataset(self):
        file = self.cleaned_data["dataset"]
        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le CSV doit faire au maximum 5 Mo.")
        if not file.name.lower().endswith(".csv"):
            raise forms.ValidationError("Choisissez un fichier .csv.")
        return file
