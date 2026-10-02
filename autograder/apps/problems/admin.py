import json

from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from .models import Problem, renumber_problems


class ProblemAdminForm(forms.ModelForm):
    class Meta:
        model = Problem
        fields = "__all__"


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    form = ProblemAdminForm
    change_list_template = "admin/problems/problem/change_list.html"
    list_per_page = 500

    list_display = (
        "drag_handle",
        "number",
        "name",
        "contest",
        "contest_letter",
        "points",
        "interactive",
        "secret",
    )
    list_filter = ("interactive", "secret", "contest")
    search_fields = ("name",)
    ordering = ("-number",)

    fieldsets = (
        (None, {"fields": ("name", "contest", "points", "contest_letter")}),
        ("Limits", {"fields": ("tl", "ml")}),
        ("Flags", {"fields": ("interactive", "secret")}),
        (
            "Text Fields",
            {"fields": ("statement", "inputtxt", "outputtxt", "samples")},
        ),
        ("Testcases zip", {"fields": ("testcases_zip",)}),
    )

    @admin.display(description="")
    def drag_handle(self, obj):
        return format_html(
            '<span class="problem-drag-handle" data-pk="{}" title="Drag to reorder">'
            "&#9776;</span>",
            obj.pk,
        )

    def get_urls(self):
        return [
            path(
                "reorder/",
                self.admin_site.admin_view(require_POST(self.reorder_view)),
                name="problems_problem_reorder",
            ),
        ] + super().get_urls()

    def reorder_view(self, request):
        if not self.has_change_permission(request):
            return JsonResponse({"error": "Permission denied"}, status=403)
        try:
            order = [int(pk) for pk in json.loads(request.body)["order"]]
            renumber_problems(order)
        except (ValueError, KeyError, TypeError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"ok": True})
