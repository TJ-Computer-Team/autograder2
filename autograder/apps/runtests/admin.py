from django.contrib import admin
from .models import Submission
from .tasks import grade_submission_task


@admin.action(description="Rerun submissions")
def rerun_submissions(modeladmin, request, queryset):
    for sub in queryset:
        grade_submission_task.delay(sub.id)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "usr",
        "contest",
        "problem",
        "language",
        "verdict",
        "runtime",
        "timestamp",
    )
    list_filter = ("verdict", "language", "problem", "usr", "contest")
    search_fields = ("problem__name", "verdict")
    ordering = ("-timestamp",)
    readonly_fields = ("timestamp",)

    fieldsets = (
        (
            None,
            {"fields": ("contest", "problem", "language", "code")},
        ),
        (
            "Result Info",
            {"fields": ("verdict", "runtime", "timestamp", "insight")},
        ),
    )

    actions = [rerun_submissions]
