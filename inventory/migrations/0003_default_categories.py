from django.db import migrations


def create_categories(apps, schema_editor):
    Category = apps.get_model("inventory", "Category")
    for code, name in [("ram", "Mémoire RAM"), ("ssd", "SSD"), ("hdd", "Disque dur HDD"), ("battery", "Batterie"), ("charger", "Chargeur"), ("screen", "Écran"), ("keyboard", "Clavier"), ("fan", "Ventilateur"), ("motherboard", "Carte mère"), ("gpu", "Carte graphique"), ("psu", "Alimentation"), ("accessory", "Accessoires")]:
        Category.objects.get_or_create(code=code, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_initial")]
    operations = [migrations.RunPython(create_categories, migrations.RunPython.noop)]
