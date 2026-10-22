from django.db import migrations


DEFAULT_RULES = [
    {"code": "preventive-cleaning", "title": "Un entretien préventif à prévoir", "description": "Un nettoyage des ventilateurs et des grilles d’aération aide à limiter la poussière et la surchauffe. Faites vérifier votre ordinateur lors d’un entretien préventif.", "criterion": "maintenance_overdue", "threshold": 180, "priority": "high"},
    {"code": "ram-upgrade", "title": "Un peu plus de mémoire ?", "description": "Une augmentation de la RAM peut améliorer le confort lorsque plusieurs applications sont ouvertes. Vérifiez la compatibilité de votre PC avant tout achat.", "criterion": "ram_below", "threshold": 8, "priority": "medium"},
    {"code": "ssd-upgrade", "title": "Passez à la vitesse SSD", "description": "Remplacer un disque mécanique par un SSD peut améliorer la réactivité de votre PC. Faites vérifier la compatibilité et sauvegardez vos données avant le remplacement.", "criterion": "hdd", "threshold": 0, "priority": "medium"},
    {"code": "storage-review", "title": "Faites le point sur votre stockage", "description": "La capacité du disque est limitée. Vérifiez l’espace réellement disponible, archivez les fichiers inutilisés et prévoyez une sauvegarde externe.", "criterion": "storage_below", "threshold": 256, "priority": "low"},
]


def create_rules(apps, schema_editor):
    Rule = apps.get_model("maintenance", "MaintenanceRule")
    for data in DEFAULT_RULES:
        Rule.objects.using(schema_editor.connection.alias).get_or_create(code=data["code"], defaults=data)


def delete_rules(apps, schema_editor):
    apps.get_model("maintenance", "MaintenanceRule").objects.using(schema_editor.connection.alias).filter(code__in=[r["code"] for r in DEFAULT_RULES]).delete()


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0001_initial")]
    operations = [migrations.RunPython(create_rules, delete_rules)]
