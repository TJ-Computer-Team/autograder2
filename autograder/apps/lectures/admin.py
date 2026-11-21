from django.contrib import admin

from .models import LectureSet, LectureSetEntry


class LectureSetEntryInline(admin.TabularInline):
    model = LectureSetEntry
    extra = 1
    ordering = ("order", "id")
    autocomplete_fields = ("problem",)
    fields = (
        "order",
        "problem",
        "external_title",
        "external_url",
        "difficulty",
        "note",
    )


@admin.register(LectureSet)
class LectureSetAdmin(admin.ModelAdmin):
    inlines = (LectureSetEntryInline,)
    list_display = ("title", "kind", "topic", "date", "label_style", "published")
    list_filter = ("kind", "published", "label_style")
    search_fields = ("title", "topic")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-date", "-created_at")

    fieldsets = (
        (None, {"fields": ("title", "slug", "kind", "published")}),
        ("Lecture details", {"fields": ("topic", "date", "description")}),
        ("Display", {"fields": ("label_style",)}),
    )
