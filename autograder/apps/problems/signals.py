from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from .models import Problem, compact_problem_numbers
from ...coderunner.files import add_problem_to_coderunner, add_tests_to_coderunner
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Problem)
def add_problem_folder(sender, instance, created, **kwargs):
    add_problem_to_coderunner(instance.id)


@receiver(post_save, sender=Problem)
def add_problem_tests(sender, instance, created, **kwargs):
    add_tests_to_coderunner(instance.id)


@receiver(post_delete, sender=Problem)
def close_number_gap(sender, instance, **kwargs):
    compact_problem_numbers()
