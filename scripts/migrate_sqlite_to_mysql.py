"""Transfer an existing SQLite database into an empty, migrated MySQL database."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


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
    export = subprocess.run(
        [sys.executable, str(ROOT / "manage.py"), "dumpdata", "auth.group", "auth.user", "maintenance", "--natural-foreign", "--settings=config.sqlite_export_settings", "--indent=2"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if export.returncode:
        raise SystemExit("L’export SQLite a échoué. Aucune donnée MySQL n’a été modifiée.\n" + export.stderr)
    data = json.loads(export.stdout)
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
