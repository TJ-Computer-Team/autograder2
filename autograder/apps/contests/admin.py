from django.contrib import admin
from .models import Contest


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rated", "season", "tjioi", "start", "end")
    list_filter = ("rated", "tjioi", "season")
    search_fields = ("name",)
    ordering = ("-start",)   

    filter_horizontal = ('writers',)

    fieldsets = (
        (None, {
            'fields': ('name', 'editorial', 'writers'),
        }),
        ('Competition settings', {
            'fields': ('rated', 'tjioi', 'season'),
        }),
        ('Schedule', {
            'fields': ('start', 'end'),
        }),
    )

    