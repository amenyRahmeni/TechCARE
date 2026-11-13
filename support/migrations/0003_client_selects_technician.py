from django.db import migrations


def update_default_answer(apps, schema_editor):
    FAQItem = apps.get_model("support", "FAQItem")
    original = "Dans Assistance & réparation, choisissez Déclarer une panne, sélectionnez votre PC et le type de problème, puis décrivez les symptômes. Vous pouvez joindre une photo JPEG, PNG ou WebP de 5 Mo maximum. L’administration affectera un technicien qualifié."
    updated = "Dans Assistance & réparation, choisissez Déclarer une panne, sélectionnez votre PC et le type de problème, puis choisissez un technicien actif, disponible et qualifié dans la liste proposée. Décrivez les symptômes et ajoutez si nécessaire une photo JPEG, PNG ou WebP de 5 Mo maximum. La demande sera envoyée directement au technicien choisi."
    FAQItem.objects.using(schema_editor.connection.alias).filter(question="Comment déclarer une panne avec une photo ?", answer=original).update(answer=updated)


class Migration(migrations.Migration):
    dependencies = [("support", "0002_initial_questions")]
    operations = [migrations.RunPython(update_default_answer, migrations.RunPython.noop)]
