from django.contrib import admin
from .models import MaintenanceRecord, MaintenanceRule, PC, Recommendation


@admin.register(PC)
class PCAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "model", "owner", "ram_gb", "storage_type"]
    search_fields = ["name", "model", "serial_number", "owner__username"]
    list_filter = ["device_type", "storage_type"]


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ["title", "pc", "kind", "completed_on", "technician"]
    list_filter = ["kind"]
    autocomplete_fields = ["pc"]

    def get_readonly_fields(self, request, obj=None):
        return ["pc"] if obj else []

    def has_change_permission(self, request, obj=None):
        if obj and hasattr(obj, "intervention"):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and hasattr(obj, "intervention"):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(MaintenanceRule)
class MaintenanceRuleAdmin(admin.ModelAdmin):
    list_display = ["title", "criterion", "threshold", "priority", "is_active"]
    list_filter = ["priority", "is_active"]


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ["pc", "rule", "is_active", "updated_at"]
    readonly_fields = ["pc", "rule", "reason", "is_active", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False


admin.site.site_header = "TECHcare · Administration"
admin.site.site_title = "TECHcare"
