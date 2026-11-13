from django.contrib import admin

from .models import Notification, NotificationCampaign, PushDelivery, PushSubscription


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ["title", "recipient", "kind", "level", "read_at", "created_at"]
    list_filter = ["kind", "level"]
    search_fields = ["title", "recipient__username"]


@admin.register(NotificationCampaign)
class CampaignAdmin(ReadOnlyAdmin):
    list_display = ["title", "author", "audience", "recipient_count", "sent_at", "withdrawn_at"]
    list_filter = ["audience", "level"]


@admin.register(PushSubscription)
class SubscriptionAdmin(ReadOnlyAdmin):
    list_display = ["user", "is_active", "updated_at"]

    def get_fields(self, request, obj=None):
        return ["user", "is_active", "created_at", "updated_at"]


@admin.register(PushDelivery)
class DeliveryAdmin(ReadOnlyAdmin):
    list_display = ["notification", "state", "attempts", "sent_at", "last_error"]
    list_filter = ["state"]
