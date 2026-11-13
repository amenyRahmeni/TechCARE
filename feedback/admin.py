from django.contrib import admin
from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["client", "technician", "rating", "created_at"]
    list_filter = ["rating", "technician"]
    readonly_fields = ["client", "technician", "appointment", "repair", "rating", "comment", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
