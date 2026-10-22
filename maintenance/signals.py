from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import MaintenanceRecord, MaintenanceRule, PC
from .services import refresh_all_recommendations, refresh_recommendations


@receiver(post_save, sender=PC)
def pc_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        refresh_recommendations(instance)


@receiver(post_save, sender=MaintenanceRecord)
@receiver(post_delete, sender=MaintenanceRecord)
def record_changed(sender, instance, **kwargs):
    origin = kwargs.get("origin")
    # A PC cascade already removes its histories and recommendations together.
    if isinstance(origin, PC) or getattr(origin, "model", None) is PC:
        return
    if not kwargs.get("raw"):
        pc = PC.objects.filter(pk=instance.pc_id).first()
        if pc:
            refresh_recommendations(pc)


@receiver(post_save, sender=MaintenanceRule)
@receiver(post_delete, sender=MaintenanceRule)
def rule_changed(sender, **kwargs):
    if not kwargs.get("raw"):
        refresh_all_recommendations()
