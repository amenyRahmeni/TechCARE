from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from appointments.models import Technician
from .models import ComponentListing
from .permissions import can_edit_listing

FIELDS = ("title", "category", "brand", "reference", "condition", "unit_price", "quantity", "description", "compatibility_notes", "location", "contact_phone", "contact_email")


def _delete_photo(storage, name):
    # Run after commit: a rejected update must never remove the current image.
    transaction.on_commit(lambda: storage.delete(name))


def save_listing(actor, data, *, pk=None, draft=False):
    uploaded_name = None
    uploaded_storage = None
    try:
        with transaction.atomic():
            if pk:
                listing = ComponentListing.objects.select_for_update(of=("self",)).select_related("seller__user").get(pk=pk)
                if not can_edit_listing(actor, listing):
                    raise PermissionDenied
            else:
                if not actor.is_active:
                    raise PermissionDenied
                seller = Technician.objects.select_for_update().filter(user=actor).first()
                if not seller:
                    raise PermissionDenied("Un profil technicien est nécessaire pour déposer une annonce.")
                existing = ComponentListing.objects.filter(submission_token=data["submission_token"]).first()
                if existing:
                    if existing.seller_id != seller.pk:
                        raise PermissionDenied
                    return existing
                listing = ComponentListing(seller=seller, submission_token=data["submission_token"])
            old_photo = listing.photo.name
            for name in FIELDS:
                setattr(listing, name, data[name])
            listing.status = ComponentListing.Status.DRAFT if draft else ComponentListing.Status.PUBLISHED
            listing.full_clean(exclude=["photo"])
            if data.get("photo"):
                listing.photo.save("photo.jpg", data["photo"], save=False)
                uploaded_name, uploaded_storage = listing.photo.name, listing.photo.storage
            elif data.get("remove_photo"):
                listing.photo = ""
            listing.save()
            if old_photo and old_photo != listing.photo.name:
                _delete_photo(listing.photo.storage, old_photo)
            return listing
    except Exception:
        if uploaded_name:
            uploaded_storage.delete(uploaded_name)
        raise


@transaction.atomic
def change_listing_status(actor, pk, status):
    listing = ComponentListing.objects.select_for_update(of=("self",)).select_related("seller__user").get(pk=pk)
    if not can_edit_listing(actor, listing):
        raise PermissionDenied
    if status not in ComponentListing.Status.values:
        raise ValidationError("Statut d’annonce invalide.")
    if status == ComponentListing.Status.PUBLISHED and not listing.seller.user.is_active:
        raise ValidationError("Une annonce d’un compte désactivé ne peut pas être publiée.")
    if listing.status != status:
        listing.status = status
        listing.save(update_fields=["status", "updated_at"])
    return listing
