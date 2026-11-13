from django.db import migrations


def skills_from_specialty(apps, schema_editor):
    Technician = apps.get_model("appointments", "Technician")
    for technician in Technician.objects.all():
        specialty = technician.specialty.casefold()
        if "matériel" in specialty:
            technician.skills = ["hardware"]
        elif "logiciel" in specialty:
            technician.skills = ["software"]
        elif "réseau" in specialty:
            technician.skills = ["network"]
        else:
            continue
        technician.save(update_fields=["skills"])


class Migration(migrations.Migration):
    dependencies = [("appointments", "0002_invoice_repair_partline_stock_usage_and_more")]
    operations = [migrations.RunPython(skills_from_specialty, migrations.RunPython.noop)]
