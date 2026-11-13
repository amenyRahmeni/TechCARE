from django.contrib import admin

from appointments.admin import WorkflowReadOnlyAdmin
from .models import RepairEvent, RepairMessage, RepairRequest


class RepairWorkspaceOnlyAdmin(WorkflowReadOnlyAdmin):
    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RepairRequest)
class RepairAdmin(RepairWorkspaceOnlyAdmin):
    list_display = ["id", "pc", "client", "technician", "problem", "status", "created_at"]
    list_filter = ["status", "problem"]
    search_fields = ["description", "pc__name", "client__username"]
    exclude = ["photo"]


admin.site.register(RepairEvent, RepairWorkspaceOnlyAdmin)
admin.site.register(RepairMessage, RepairWorkspaceOnlyAdmin)
