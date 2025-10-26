from django.contrib import admin
from .models import Submission
from .tasks import grade_submission_task


@admin.action(description="Rerun submissions")
def rerun_submissions(modeladmin, request, queryset):
    for old_sub in queryset:
        new_sub = Submission.objects.create(
            usr=old_sub.usr,
            code=old_sub.code,
            problem=old_sub.problem,
            language=old_sub.language,
            contest=old_sub.contest,
            timestamp=old_sub.timestamp,
        )
        new_sub.save()
        grade_submission_task.delay(new_sub.id)


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
