from django import forms
from django.contrib import admin
from .models import Contest
from ..index.models import GraderUser


class ContestAdminForm(forms.ModelForm):
    class Meta:
        model = Contest
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        visible_to = self.fields["visible_to"]
        visible_to.queryset = GraderUser.objects.filter(is_staff=True).order_by(
            "username"
        )
        visible_to.label_from_instance = lambda u: u.username
        visible_to.help_text = (
            "Admins allowed to see this contest before it ends. Every other "
            "admin is treated as a regular participant and can't see the "
            "contest, its problems or its submissions here until it ends."
        )

    def clean_visible_to(self):
        visible_to = self.cleaned_data["visible_to"]
        if not visible_to:
            raise forms.ValidationError(
                "Select at least one admin who can see this contest."
            )
        return visible_to


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    form = ContestAdminForm
    list_display = ("id", "name", "rated", "season", "tjioi", "start", "end")
    list_filter = ("rated", "tjioi", "season")
    search_fields = ("name",)
    ordering = ("-start",)   

    filter_horizontal = ('writers', 'visible_to')

    fieldsets = (
        (None, {
            'fields': ('name', 'editorial', 'writers'),
        }),
        ('Visibility', {
            'fields': ('visible_to',),
        }),
        ('Competition settings', {
            'fields': ('rated', 'tjioi', 'season'),
        }),
        ('Schedule', {
            'fields': ('start', 'end'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(
            id__in=Contest.locked_for(request.user)
        )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("visible_to", [request.user.pk])
        return initial
