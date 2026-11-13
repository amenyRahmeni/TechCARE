from django.contrib import admin
from .models import FAQItem


@admin.register(FAQItem)
class FAQAdmin(admin.ModelAdmin):
    list_display = ["question", "category", "is_active", "position"]
    list_filter = ["category", "is_active"]
    search_fields = ["question", "answer"]
