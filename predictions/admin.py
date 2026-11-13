from django.contrib import admin
from .models import FailureModel, FailurePrediction


class ReadOnlyMLAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FailureModel)
class FailureModelAdmin(ReadOnlyMLAdmin):
    list_display = ["short_version", "origin", "sample_count", "trained_at"]
    exclude = ["forest"]

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields if field.name != "forest"]


@admin.register(FailurePrediction)
class PredictionAdmin(ReadOnlyMLAdmin):
    list_display = ["pc", "level", "score", "model", "created_at"]
    list_filter = ["level", "model__origin"]
