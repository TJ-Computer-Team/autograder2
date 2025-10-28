from django import forms
from django.contrib import admin
from .models import Problem


class ProblemAdminForm(forms.ModelForm):
    class Meta:
        model = Problem
        fields = "__all__"
        help_texts = {
            'interactive': 'Check this for interactive problems (real-time communication)',
            'testcases_zip': 'For standard problems: zip with test inputs and expected outputs. For interactive: zip with test inputs + interactor file (interactor.py/.cpp/.java)',
        }


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    form = ProblemAdminForm

    list_display = (
        "id",
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
        (None, {"fields": ("name", "contest", "points", "contest_letter")}),
        ("Limits", {"fields": ("tl", "ml")}),
        ("Flags", {"fields": ("interactive", "secret")}),
        (
            "Text Fields",
            {"fields": ("statement", "inputtxt", "outputtxt", "samples")},
        ),
        ("Testcases", {
            "fields": ("testcases_zip",),
            "description": "Standard: Include test/ and sol/ folders. Interactive: Include interactor.py/.cpp/.java + test input files"
        }),
    )
    
    class Media:
        js = ('admin/js/interactive_problem.js',)
