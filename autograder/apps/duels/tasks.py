import logging
import time

from django.db import transaction
from django.utils import timezone

from ...celery import app
from ..index.cf_utils import fetch_solved_set
from .models import Cup, CupMatch, Duel, Ladder, LadderRung
from .selection import SelectionError, pick_duel_problem, pick_ladder_problems

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


@app.task
def start_ladder(ladder_id):
    """Draw every rung and open the ladder. Same shape as start_duel."""
    try:
        ladder = Ladder.objects.get(id=ladder_id)
    except Ladder.DoesNotExist:
        logger.error(f"Ladder {ladder_id} vanished before it could start.")
        return
    if ladder.status != Ladder.PENDING:
        return

    handles = [e.user.cf_handle for e in ladder.entries.select_related("user")]
    try:
        problems = pick_ladder_problems(
            ladder.rating_min,
            ladder.rating_max,
            ladder.rung_count,
            handles,
            ladder.tags,
        )
    except SelectionError as e:
        logger.warning(f"Ladder {ladder_id} could not pick problems: {e}")
        # Clearing the request lets the host retry, and reopens joining meanwhile.
        Ladder.objects.filter(id=ladder_id, status=Ladder.PENDING).update(
            selection_error=str(e)[:300], start_requested_at=None
        )
        return

    with transaction.atomic():
        locked = Ladder.objects.select_for_update().get(id=ladder_id)
        if locked.status != Ladder.PENDING:
            return
        LadderRung.objects.bulk_create(
            LadderRung(
                ladder=locked,
                position=i,
                cf_contest_id=p["contestId"],
                cf_index=p["index"],
                cf_name=p.get("name", ""),
                cf_rating=p.get("rating"),
            )
            for i, p in enumerate(problems, start=1)
        )
        now = timezone.now()
        locked.status = Ladder.ACTIVE
        locked.started_at = now
        locked.selection_error = ""
        locked.save(update_fields=["status", "started_at", "selection_error"])
        locked.entries.update(reached_at=now)

    logger.info(f"Ladder {ladder_id} started with {len(problems)} rungs")


@app.task
def close_ladder(ladder_id):
    """Final sweep once time is up, then mark the ladder finished.

    Players are normally polled only while their own page is open, so someone who
    solved in the last seconds (or closed the tab) would otherwise lose that rung.
    Accepted runs after the deadline are ignored by refresh_entry.
    """
    from .ladder import refresh_entry

    ladder = Ladder.objects.filter(id=ladder_id, status=Ladder.ACTIVE).first()
    if ladder is None:
        return
    entries = ladder.entries.select_related("user", "ladder")
    for i, entry in enumerate(entries):
        if entry.is_done:
            continue
        if i:
            time.sleep(1)  # stay under Codeforces' ~1 request/second
        refresh_entry(entry, force=True)

    with transaction.atomic():
        locked = Ladder.objects.select_for_update().get(id=ladder_id)
        if locked.status == Ladder.ACTIVE:
            locked.finish()


@app.task
def start_cup_round(cup_id, round_number):
    """Start every undecided match in a round, one after another."""
    match_ids = CupMatch.objects.filter(
        cup_id=cup_id, round=round_number, winner__isnull=True
    ).values_list("id", flat=True)
    for match_id in match_ids:
        start_cup_match(match_id)


@app.task
def start_cup_match(match_id):
    """Draw a problem for one cup match and start its duel.

    Also what staff's Retry button runs, so it reuses a duel stuck drawing.
    """
    from .cup import create_match_duel

    match = CupMatch.objects.select_related("cup", "player_a", "player_b").get(
        id=match_id
    )
    cup = match.cup
    if match.winner_id or len(match.players) < 2:
        return
    if match.duels.filter(status=Duel.ACTIVE).exists():
        return

    # Forced: the cached list (10 min) can predate last round's problem, which
    # they could otherwise just resubmit. Waits its turn in the site-wide budget.
    for player in match.players:
        if fetch_solved_set(player.cf_handle, force=True, wait=60) is None:
            msg = f"Couldn't load {player.cf_handle}'s Codeforces history. Retry the match."
            logger.warning(f"Cup {cup.pk}: {msg}")
            Cup.objects.filter(pk=cup.pk).update(error=msg[:300])
            return

    duel = match.duels.filter(status=Duel.PENDING).first() or create_match_duel(
        match, cup.duel_minutes
    )
    start_duel(duel.id)
