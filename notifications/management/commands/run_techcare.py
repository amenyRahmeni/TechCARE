from threading import Thread

from django.contrib.staticfiles.management.commands.runserver import Command as RunserverCommand
from django.core.management import call_command


class Command(RunserverCommand):
    help = "Démarre le serveur de développement TECHcare avec le traitement automatique des notifications."

    def inner_run(self, *args, **options):
        # inner_run executes only inside the serving process, after autoreload setup.
        # The daemon belongs to that process and ends with it; no separate service is installed.
        worker = Thread(target=call_command, args=("run_notifications",), kwargs={"stdout": self.stdout, "stderr": self.stderr}, name="techcare-notifications", daemon=True)
        worker.start()
        super().inner_run(*args, **options)
