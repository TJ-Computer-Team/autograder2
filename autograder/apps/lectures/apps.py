from django.apps import AppConfig


class LecturesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "autograder.apps.lectures"
    verbose_name = "Lecture Sets"
