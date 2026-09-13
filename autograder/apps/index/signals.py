from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import GraderUser
from ..rankings.formula import usaco_rating_for
from ..rankings.tasks import update_codeforces_rating
import threading
import logging

logger = logging.getLogger(__name__)
_signal_lock = threading.local()

# Fields the ranking tasks write back to the user. A save touching only these came
# *from* those tasks, so re-queueing them would loop:
#   update_codeforces_rating -> update_user_index -> save(index) -> this signal ->
#   update_codeforces_rating -> ...
# Each lap costs a Codeforces call throttled to 2/s, which is enough to back the
# default queue up by hundreds of tasks and starve everything else on it.
_TASK_WRITTEN_FIELDS = {"index", "usaco_rating", "cf_rating", "inhouse", "inhouses"}


@receiver(post_save, sender=GraderUser)
def handle_user_updates(sender, instance, created, update_fields=None, **kwargs):
    if getattr(_signal_lock, "in_signal", False):
        return

    new_usaco_rating = usaco_rating_for(instance.usaco_division)
    if instance.usaco_rating != new_usaco_rating:
        instance.usaco_rating = new_usaco_rating
        try:
            _signal_lock.in_signal = True
            instance.save(update_fields=["usaco_rating"])
        finally:
            _signal_lock.in_signal = False

    if update_fields and set(update_fields) <= _TASK_WRITTEN_FIELDS:
        return

    update_codeforces_rating.delay(instance.id)
