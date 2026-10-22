import logging

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..index.cf_utils import fetch_recent_submissions, fetch_solved_set
from .models import Ladder, LadderEntry

logger = logging.getLogger(__name__)

# Each player's own page drives the CF polling for their handle, so a ladder costs
# one request per climbing player per window. Spectators never trigger a CF call.
# The window stretches with the field so a big ladder stays near ~0.7 req/s, under
# Codeforces' ~1 req/s per-IP limit. CF judging takes 5-30s anyway, so the extra
# few seconds of lag are barely noticeable.
MIN_POLL_WINDOW_SECONDS = 4
SECONDS_PER_PLAYER = 1.5


def poll_window(ladder):
    climbing = ladder.entries.filter(position__lte=ladder.rung_count).count()
    return max(MIN_POLL_WINDOW_SECONDS, round(SECONDS_PER_PLAYER * climbing))


class JoinError(Exception):
    """The user cannot join this ladder right now; the message says why."""


def join_ladder(ladder, user):
    """Add `user` to the ladder. Joining is open until the clock runs out.

    A late joiner's CF history is checked against the rungs first: any rung they
    have already solved is passed over without a point, since they could otherwise
    resubmit an old accepted solution.
    """
    existing = LadderEntry.objects.filter(ladder=ladder, user=user).first()
    if existing:
        return existing

    presolved = []
    if ladder.status == Ladder.ACTIVE:
        # Forced: someone already climbing could have shown them a later rung.
        solved = fetch_solved_set(user.cf_handle, force=True)
        if solved is None:
            raise JoinError("Could not load your Codeforces history. Try again.")
        presolved = [
            r.position
            for r in ladder.rungs.all()
            if (r.cf_contest_id, r.cf_index) in solved
        ]

    with transaction.atomic():
        # Locked so a join cannot slip in between the start task reading the
        # entrants (to exclude their solved problems) and the ladder going live.
        locked = Ladder.objects.select_for_update().get(pk=ladder.pk)
        if locked.status != ladder.status:
            # Went live after the history check above was skipped.
            raise JoinError("It just started. Try again.")
        if locked.status == Ladder.PENDING and locked.start_requested_at:
            raise JoinError("Problems are being drawn. Try again in a few seconds.")
        if locked.status == Ladder.ACTIVE and locked.is_overdue:
            raise JoinError("This battle royale is over.")
        if locked.status not in (Ladder.PENDING, Ladder.ACTIVE):
            raise JoinError("This battle royale is over.")

        entry = LadderEntry(
            ladder=locked,
            user=user,
            presolved=",".join(str(p) for p in presolved),
        )
        if locked.status == Ladder.ACTIVE:
            entry.reached_at = timezone.now()
            while entry.position in presolved:
                entry.position += 1
        try:
            with transaction.atomic():
                entry.save()
        except IntegrityError:
            # Double click; the first request already joined them.
            return LadderEntry.objects.get(ladder=ladder, user=user)
    return entry


def refresh_entry(entry, force=False):
    """Check one player's current rung on CF and move them up if it is accepted.

    Returns True if a CF call was made.
    """
    ladder = entry.ladder
    if ladder.status != Ladder.ACTIVE or entry.is_done or entry.reached_at is None:
        return False
    if not force and not cache.add(f"ladder_poll:{entry.pk}", 1, poll_window(ladder)):
        return False

    rung = ladder.rungs.filter(position=entry.position).first()
    if rung is None:
        return False

    deadline = ladder.deadline
    accepted = [
        created
        for _cf_id, verdict, created in fetch_recent_submissions(
            entry.user.cf_handle, rung.cf_contest_id, rung.cf_index, entry.reached_at
        )
        if verdict == "OK" and created < deadline
    ]
    if accepted:
        _credit(entry, rung.position, min(accepted))
    return True


def _copy_progress(src, dst):
    for field in (
        "position",
        "solved",
        "skips_used",
        "last_solve_at",
        "solve_times",
        "reached_at",
    ):
        setattr(dst, field, getattr(src, field))


@transaction.atomic
def _credit(entry, position, solved_at):
    locked = LadderEntry.objects.select_for_update().get(pk=entry.pk)
    # Already moved on (another poll, or a skip) -- don't award twice.
    if locked.position != position:
        return
    locked.solved += 1
    locked.last_solve_at = solved_at
    locked.solve_times = [*locked.solve_times, solved_at.isoformat()]
    locked.move_up()
    locked.save(
        update_fields=[
            "position",
            "solved",
            "last_solve_at",
            "solve_times",
            "reached_at",
        ]
    )
    _copy_progress(locked, entry)
    _finish_if_everyone_done(locked.ladder_id)


@transaction.atomic
def skip_rung(entry):
    """Move up one rung without a point. Returns False if no skips are left."""
    locked = LadderEntry.objects.select_for_update().get(pk=entry.pk)
    if locked.is_done or locked.skips_left == 0:
        return False
    locked.skips_used += 1
    locked.move_up()
    locked.save(update_fields=["position", "skips_used", "reached_at"])
    _copy_progress(locked, entry)
    _finish_if_everyone_done(locked.ladder_id)
    return True


def _finish_if_everyone_done(ladder_id):
    ladder = Ladder.objects.select_for_update().get(pk=ladder_id)
    if ladder.status != Ladder.ACTIVE:
        return
    if not ladder.entries.filter(position__lte=ladder.rung_count).exists():
        ladder.finish()


def close_if_overdue(ladder):
    """Hand an expired ladder to the closing task, once."""
    if ladder.status != Ladder.ACTIVE or not ladder.is_overdue:
        return
    if cache.add(f"ladder_close:{ladder.pk}", 1, 600):
        from .tasks import close_ladder

        close_ladder.delay(ladder.pk)
