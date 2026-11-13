"""Transfer an existing SQLite database into an empty, migrated MySQL database."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def export_legacy_data(source):
    """Read only columns present in the old schema; new fields keep model defaults."""
    from django.apps import apps
    from django.db.models import BooleanField, JSONField

    result = []
    with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        def permissions(table, owner_column, owner_id):
            return [list(row) for row in connection.execute(f'SELECT p.codename, c.app_label, c.model FROM "{table}" link JOIN auth_permission p ON p.id=link.permission_id JOIN django_content_type c ON c.id=p.content_type_id WHERE link."{owner_column}"=?', [owner_id])]
        for label in ["auth.group", "auth.user", "maintenance.pc", "maintenance.maintenancerecord", "maintenance.maintenancerule", "maintenance.recommendation"]:
            model = apps.get_model(label)
            table = model._meta.db_table
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if not columns:
                raise ValueError(f"Table historique absente : {table}")
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY id'):
                fields = {}
                for field in model._meta.concrete_fields:
                    if field.primary_key or field.column not in columns:
                        continue
                    value = row[field.column]
                    if isinstance(field, BooleanField):
                        value = bool(value)
                    elif isinstance(field, JSONField) and value is not None:
                        value = json.loads(value)
                    fields[field.name] = value
                if label == "auth.group":
                    fields["permissions"] = permissions("auth_group_permissions", "group_id", row["id"])
                elif label == "auth.user":
                    fields["groups"] = [[group[0]] for group in connection.execute("SELECT g.name FROM auth_user_groups link JOIN auth_group g ON g.id=link.group_id WHERE link.user_id=?", [row["id"]])]
                    fields["user_permissions"] = permissions("auth_user_user_permissions", "user_id", row["id"])
                result.append({"model": label, "pk": row["id"], "fields": fields})
    return result


def main():
    if not (ROOT / "db.sqlite3").is_file():
        raise SystemExit("Ancienne base db.sqlite3 introuvable. Utilisez seed_demo pour démarrer une nouvelle base.")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import transaction
    from maintenance.models import MaintenanceRule, PC
    from maintenance.services import refresh_all_recommendations

    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.mysql":
        raise SystemExit("La destination doit être MySQL.")
    if get_user_model().objects.exists() or PC.objects.exists():
        raise SystemExit("Import arrêté : MySQL contient déjà des utilisateurs ou des PC. Utilisez une base vide pour éviter tout écrasement.")
    try:
        data = export_legacy_data(ROOT / "db.sqlite3")
    except (sqlite3.Error, ValueError):
        raise SystemExit("L’export SQLite a échoué. Vérifiez la structure de la source ; aucune donnée MySQL n’a été modifiée.") from None
    for record in data:
        if record["model"] == "maintenance.pc":
            record["fields"]["serial_number"] = (record["fields"].get("serial_number") or "").strip() or None
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f"sqlite-{stamp}.json"
    backup.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with transaction.atomic():
        # The target contains only the rules supplied by Django's initial migrations.
        MaintenanceRule.objects.all().delete()
        call_command("loaddata", str(backup), verbosity=0)
        refresh_all_recommendations()
    print(f"Import terminé : {len(data)} objets transférés vers MySQL.")
    print("Comptes et mots de passe conservés. La base SQLite d’origine est intacte.")
    print(f"Sauvegarde privée : {backup.relative_to(ROOT)} (ne pas partager ce fichier).")


if __name__ == "__main__":
    main()
