from django.contrib import admin

from .models import Appointment, BookingSlot, Intervention, Invoice, PartLine, Technician


@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ["user", "specialty", "is_available"]
    list_filter = ["is_available"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "specialty"]
    autocomplete_fields = ["user"]


class WorkflowReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Appointment)
class AppointmentAdmin(WorkflowReadOnlyAdmin):
    list_display = ["id", "pc", "client", "technician", "starts_at", "status"]
    list_filter = ["status", "category"]
    search_fields = ["reason", "pc__name", "client__username"]
    view_on_site = True


@admin.register(Intervention)
class InterventionAdmin(WorkflowReadOnlyAdmin):
    list_display = ["appointment", "labour_cost", "completed_at"]


@admin.register(Invoice)
class InvoiceAdmin(WorkflowReadOnlyAdmin):
    list_display = ["number", "intervention", "total_amount", "issued_at"]
    search_fields = ["number", "intervention__appointment__client__username"]


admin.site.register(BookingSlot, WorkflowReadOnlyAdmin)
admin.site.register(PartLine, WorkflowReadOnlyAdmin)
