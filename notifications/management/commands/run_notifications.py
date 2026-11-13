import time

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
from django.utils import timezone

from maintenance.services import refresh_all_recommendations
from notifications.push import configured, dispatch_push
from notifications.services import generate_reminders, sync_current_recommendations


class Command(BaseCommand):
    help = "Génère les rappels J-1, actualise la maintenance et envoie les notifications navigateur en attente."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Effectuer un passage, pour le Planificateur de tâches ou cron.")
        parser.add_argument("--interval", type=int, default=30, help="Intervalle entre deux passages, de 10 à 3600 secondes.")

    def handle(self, *args, **options):
        if not 10 <= options["interval"] <= 3600:
            raise CommandError("L’intervalle doit être compris entre 10 et 3600 secondes.")
        if not configured():
            self.stdout.write("Le centre d’alertes fonctionne. Exécutez setup_webpush pour activer les envois navigateur.")
        last_refresh = None
        self.stdout.write("Traitement des notifications démarré.")
        try:
            while True:
                close_old_connections()
                try:
                    today = timezone.localdate()
                    if last_refresh != today:
                        refresh_all_recommendations()
                        sync_current_recommendations()
                        last_refresh = today
                    reminders = generate_reminders()
                    sent = dispatch_push()
                except DatabaseError:
                    if options["once"]:
                        raise CommandError("Base MySQL temporairement indisponible. Les envois conservés seront repris au prochain passage.") from None
                    self.stderr.write("Base MySQL temporairement indisponible ; nouvelle tentative au prochain passage.")
                else:
                    if options["once"] or reminders or any(sent.values()):
                        self.stdout.write(f"Rappels créés : {reminders} · push envoyés : {sent['sent']} · à vérifier : {sent['failed']} · expirés : {sent['cancelled']}")
                if options["once"]:
                    break
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Traitement des notifications arrêté.")
        finally:
            close_old_connections()
