import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from dotenv import set_key


class Command(BaseCommand):
    help = "Prépare les clés Web Push locales sans remplacer une clé privée existante."

    def handle(self, *args, **options):
        path = Path(settings.WEBPUSH_PRIVATE_KEY)
        if not path.is_absolute():
            path = settings.BASE_DIR / path
        try:
            if path.exists():
                private = serialization.load_pem_private_key(path.read_bytes(), password=None)
                if not isinstance(private, ec.EllipticCurvePrivateKey) or not isinstance(private.curve, ec.SECP256R1):
                    raise ValueError
            else:
                private = ec.generate_private_key(ec.SECP256R1())
                path.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents accidentally rotating a key in parallel.
                with path.open("xb") as destination:
                    destination.write(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            public = base64.urlsafe_b64encode(private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).rstrip(b"=").decode("ascii")
            env_path = settings.BASE_DIR / ".env"
            env_path.touch(exist_ok=True)
            set_key(str(env_path), "WEBPUSH_PRIVATE_KEY", str(path))
            set_key(str(env_path), "WEBPUSH_PUBLIC_KEY", public)
        except (OSError, ValueError, TypeError):
            raise CommandError("Impossible de préparer les clés Web Push. Vérifiez le fichier privé configuré ; aucune clé existante n’a été remplacée.") from None
        self.stdout.write(self.style.SUCCESS("Clés Web Push prêtes. La clé privée reste locale et exclue de Git."))
        self.stdout.write("Redémarrez Django puis lancez : python manage.py run_notifications")
