from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import GraderUser


class GraderUserAdmin(UserAdmin):
    model = GraderUser
    list_display = (
        "id",
        "display_name",
        "username",
        "is_staff",
        "is_tjioi",
        "grade",
        "cf_handle",
        "usaco_division",
        "cf_rating",
        "inhouse",
        "index",
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


admin.site.register(GraderUser, GraderUserAdmin)
