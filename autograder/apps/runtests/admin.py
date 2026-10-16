from django.contrib import admin
from ..contests.models import Contest
from ..problems.models import Problem
from .models import Submission
from .tasks import grade_submission_task


@admin.action(description="Rerun submissions")
def rerun_submissions(modeladmin, request, queryset):
    for old_sub in queryset:
        if old_sub.verdict in ["Rerun", "Skipped", "Accepted"]:
            continue
        new_sub = Submission.objects.create(
            usr=old_sub.usr,
            code=old_sub.code,
            problem=old_sub.problem,
            language=old_sub.language,
            contest=old_sub.contest,
            timestamp=old_sub.timestamp,
        )
        new_sub.save()
        old_sub.verdict = "Rerun"
        old_sub.insight = "Your submission was manually rerun by an admin"
        old_sub.save()
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
    # RelatedOnly so the sidebar doesn't list problems or contests hidden by
    # get_queryset.
    list_filter = (
        "verdict",
        "language",
        ("problem", admin.RelatedOnlyFieldListFilter),
        "usr",
        ("contest", admin.RelatedOnlyFieldListFilter),
    )
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

    def get_queryset(self, request):
        locked = Contest.locked_for(request.user)
        return (
            super()
            .get_queryset(request)
            .exclude(contest__in=locked)
            .exclude(problem__contest__in=locked)
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        locked = Contest.locked_for(request.user)
        if db_field.name == "contest":
            kwargs["queryset"] = Contest.objects.exclude(id__in=locked)
        elif db_field.name == "problem":
            kwargs["queryset"] = Problem.objects.exclude(contest__in=locked)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
