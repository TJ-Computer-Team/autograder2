from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import GraderUser, ProblemOfTheWeek
from django.urls import reverse
from django.utils.html import format_html


class GraderUserAdmin(UserAdmin):
    model = GraderUser
    list_display = (
        "id",
        "display_name",
        "username",
        "is_staff",
        "validation_settings_link", # Added link
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "is_tjioi")
    search_fields = ("id", "username", "display_name")
    ordering = ("id",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "display_name",
                    "username",
                    "usaco_division",
                    "cf_handle",
                    "cf_rating",
                    "grade",
                    "personal_email",
                    "is_tjioi",
                    "particles_enabled",
                )
            },
        ),
        (
            "Ratings",
            {
                "fields": (
                    "inhouse",
                    "index",
                    "inhouses",
                    "use_writer_formula",
                    "author_drops",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_active",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "display_name",
                    "username",
                    "usaco_division",
                    "is_staff",
                    "is_active",
                    "is_tjioi",
                    "cf_handle",
                    "cf_rating",
                    "grade",
                    "personal_email",
                ),
            },
        ),
    )
    
    def validation_settings_link(self, obj):
        url = reverse("index:validation_settings")
        return format_html('<a href="{}">Validation Settings</a>', url)
    validation_settings_link.short_description = "Validation Settings"


admin.site.register(GraderUser, GraderUserAdmin)


@admin.register(ProblemOfTheWeek)
class ProblemOfTheWeekAdmin(admin.ModelAdmin):
    list_display = ("level", "title", "link")
    list_editable = ("title", "link")
