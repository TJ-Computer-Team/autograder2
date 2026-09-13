import logging

from django.db import transaction
from django.utils import timezone

from ...celery import app
from .models import Duel
from .selection import SelectionError, pick_duel_problem

logger = logging.getLogger(__name__)


@app.task
def start_duel(duel_id):
    """Draw a problem and move the duel to active.

    Runs on the default queue, not coderunner_queue: this is network I/O against
    the Codeforces API, not sandboxed code execution. It is a task rather than
    inline work because fetching both players' histories takes a couple of seconds
    each and would otherwise block the accept request.
    """
    try:
        duel = Duel.objects.select_related("challenger", "opponent").get(id=duel_id)
    except Duel.DoesNotExist:
        logger.error(f"Duel {duel_id} vanished before it could start.")
        return

    if duel.status != Duel.PENDING:
        logger.info(f"Duel {duel_id} is {duel.status}; not starting.")
        return

    handles = [p.cf_handle for p in duel.players]
    try:
        problem = pick_duel_problem(
            duel.rating_min, duel.rating_max, handles, duel.tags
        )
    except SelectionError as e:
        # Back to pending with a reason shown on the page, so the challenger can
        # widen the range and try again rather than being stuck on a dead duel.
        logger.warning(f"Duel {duel_id} could not pick a problem: {e}")
        Duel.objects.filter(id=duel_id, status=Duel.PENDING).update(
            selection_error=str(e)[:300]
        )
        return

    with transaction.atomic():
        locked = Duel.objects.select_for_update().get(id=duel_id)
        if locked.status != Duel.PENDING:
            return
        locked.cf_contest_id = problem["contestId"]
        locked.cf_index = problem["index"]
        locked.cf_name = problem.get("name", "")
        locked.cf_rating = problem.get("rating")
        locked.status = Duel.ACTIVE
        locked.started_at = timezone.now()
        locked.selection_error = ""
        locked.save()

    logger.info(f"Duel {duel_id} started on {problem['contestId']}{problem['index']}")
