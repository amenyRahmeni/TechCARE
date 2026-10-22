from django.db import migrations, models


def empty_serials_to_null(apps, schema_editor):
    PC = apps.get_model("maintenance", "PC")
    PC.objects.using(schema_editor.connection.alias).filter(serial_number="").update(serial_number=None)


def null_serials_to_empty(apps, schema_editor):
    PC = apps.get_model("maintenance", "PC")
    PC.objects.using(schema_editor.connection.alias).filter(serial_number__isnull=True).update(serial_number="")


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0002_default_rules")]
    operations = [
        migrations.RemoveConstraint(model_name="pc", name="unique_owner_pc_serial"),
        migrations.AlterField(
            model_name="pc",
            name="serial_number",
            field=models.CharField(blank=True, null=True, default=None, max_length=100, verbose_name="numéro de série"),
        ),
        migrations.RunPython(empty_serials_to_null, null_serials_to_empty),
        # MySQL's MODIFY ... NULL resets collation when it is omitted. Apply
        # collation separately, after nullability, so it remains case-sensitive.
        migrations.AlterField(
            model_name="pc",
            name="serial_number",
            field=models.CharField(blank=True, null=True, default=None, db_collation="utf8mb4_bin", max_length=100, verbose_name="numéro de série"),
        ),
        migrations.AddConstraint(model_name="pc", constraint=models.UniqueConstraint(fields=("owner", "serial_number"), name="unique_owner_pc_serial")),
    ]
