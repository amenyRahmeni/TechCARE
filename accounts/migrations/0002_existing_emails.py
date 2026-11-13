from django.db import migrations


def seed(apps, schema_editor):
    User = apps.get_model("auth", "User")
    EmailAddress = apps.get_model("accounts", "EmailAddress")
    db = schema_editor.connection.alias
    seen, ambiguous = {}, set()
    for user in User.objects.using(db).exclude(email="").iterator():
        address = user.email.strip().lower()
        if not address:
            continue
        if address in seen:
            ambiguous.add(address)
        else:
            seen[address] = user.pk
    for address, user_id in seen.items():
        if address not in ambiguous:
            EmailAddress.objects.using(db).get_or_create(user_id=user_id, defaults={"address": address})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
