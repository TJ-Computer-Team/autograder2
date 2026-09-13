from django.contrib import admin

from .models import Duel, DuelSubmission


class DuelSubmissionInline(admin.TabularInline):
    model = DuelSubmission
    extra = 0
    readonly_fields = ("user", "cf_submission_id", "verdict", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # These mirror Codeforces; typing one in by hand would be fiction.
        return False


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    inlines = (DuelSubmissionInline,)
    list_display = (
        "id",
        "challenger",
        "opponent",
        "status",
        "cf_name",
        "cf_rating",
        "winner",
        "end_reason",
        "started_at",
    )
    list_filter = ("status", "end_reason")
    search_fields = (
        "challenger__display_name",
        "opponent__display_name",
        "cf_name",
    )
    autocomplete_fields = ("challenger", "opponent", "winner")
    readonly_fields = ("created_at", "accepted_at", "started_at", "ended_at")

    fieldsets = (
        (None, {"fields": ("challenger", "opponent", "status")}),
        (
            "Requested",
            {"fields": ("rating_min", "rating_max", "tags", "duration_minutes")},
        ),
        (
            "Problem",
            {"fields": ("cf_contest_id", "cf_index", "cf_name", "cf_rating")},
        ),
        ("Result", {"fields": ("winner", "end_reason", "selection_error")}),
        (
            "Timing",
            {"fields": ("created_at", "accepted_at", "started_at", "ended_at")},
        ),
    )
