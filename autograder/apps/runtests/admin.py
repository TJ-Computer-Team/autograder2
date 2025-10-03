from django.contrib import admin
from .models import Submission


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
    search_fields = ("usr__display_name", "problem__name", "verdict")
    ordering = ("-timestamp",)
    readonly_fields = ("timestamp",)

    fieldsets = (
        (None, {"fields": ("usr__display_name", "contest", "problem", "language", "code")}),
        (
            "Result Info",
            {"fields": ("verdict", "runtime", "timestamp", "insight")},
        ),
    )
