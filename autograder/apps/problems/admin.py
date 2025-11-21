from django import forms
from django.contrib import admin
from .models import Problem


class ProblemAdminForm(forms.ModelForm):
    class Meta:
        model = Problem
        fields = "__all__"


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    form = ProblemAdminForm

    list_display = (
        "id",
        "pid",
        "name",
        "contest",
        "contest_letter",
        "points",
        "interactive",
        "secret",
    )
    list_filter = ("interactive", "secret", "contest")
    search_fields = ("name",)
    ordering = ("-id",)
    readonly_fields = ("id",)

    fieldsets = (
        (None, {"fields": ("name", "contest", "points", "contest_letter", "pid")}),
        ("Limits", {"fields": ("tl", "ml")}),
        ("Flags", {"fields": ("interactive", "secret")}),
        (
            "Text Fields",
            {"fields": ("statement", "inputtxt", "outputtxt", "samples")},
        ),
        ("Testcases zip", {"fields": ("testcases_zip",)}),
    )
