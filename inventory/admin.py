from django.contrib import admin

from appointments.admin import WorkflowReadOnlyAdmin
from .models import Category, ComponentListing, ComponentUsage, SparePart, StockMovement


@admin.register(SparePart)
class ComponentAdmin(WorkflowReadOnlyAdmin):
    list_display = ["reference", "name", "category", "stock", "unit_price", "is_active"]
    search_fields = ["reference", "name", "brand"]
    list_filter = ["category", "is_active"]


@admin.register(StockMovement)
class MovementAdmin(WorkflowReadOnlyAdmin):
    list_display = ["component", "kind", "delta", "stock_after", "actor", "created_at"]
    list_filter = ["kind"]


admin.site.register(ComponentUsage, WorkflowReadOnlyAdmin)
admin.site.register(Category)


@admin.register(ComponentListing)
class ComponentListingAdmin(WorkflowReadOnlyAdmin):
    list_display = ["title", "seller", "category", "unit_price", "quantity", "status"]
    list_filter = ["status", "category", "condition"]
    search_fields = ["title", "seller__user__username", "location"]
