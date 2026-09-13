import logging

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from ..index.cf_utils import fetch_recent_submissions
from .models import Duel, DuelSubmission

logger = logging.getLogger(__name__)

# One Codeforces call per handle per window, no matter how many people are watching.
# Codeforces tolerates roughly 1 request/second per IP; a duel polls two handles, so
# 4s keeps a single duel at ~0.5 req/s.
POLL_WINDOW_SECONDS = 4


def _lock_key(duel_id):
    return f"duel_poll:{duel_id}"


def refresh_duel(duel, force=False):
    """Pull new Codeforces submissions for an active duel and settle it if won.

    Safe to call on every page poll: the cache lock means N viewers cause one CF
    request per window rather than N. Returns True if a CF call was actually made.
    """
    if duel.status != Duel.ACTIVE or duel.started_at is None:
        return False

    # Timeout is checked before the lock so an abandoned duel still closes even
    # when the throttle would otherwise skip this call.
    if duel.is_overdue:
        _finish_on_timeout(duel)
        return False

    if not force and not cache.add(_lock_key(duel.id), 1, POLL_WINDOW_SECONDS):
        return False

    for player in duel.players:
        _sync_player(duel, player)

    _settle(duel)
    return True


def _sync_player(duel, player):
    handle = player.cf_handle
    if not handle:
        return

    for cf_id, verdict, created in fetch_recent_submissions(
        handle, duel.cf_contest_id, duel.cf_index, duel.started_at
    ):
        if cf_id is None:
            continue
        DuelSubmission.objects.update_or_create(
            duel=duel,
            cf_submission_id=cf_id,
            defaults={
                "user": player,
                "verdict": verdict or "",
                "created_at": created,
            },
        )


@transaction.atomic
def _settle(duel):
    """Award the duel to whoever has the earliest accepted submission."""
    locked = Duel.objects.select_for_update().get(pk=duel.pk)
    if locked.status != Duel.ACTIVE:
        return

    first = (
        DuelSubmission.objects.filter(duel=locked, verdict="OK")
        .order_by("created_at", "cf_submission_id")
        .first()
    )
    if first is None:
        return

    locked.finish(first.user, Duel.SOLVED)
    duel.status = locked.status
    duel.winner = locked.winner
    duel.winner_id = locked.winner_id
    duel.end_reason = locked.end_reason
    duel.ended_at = locked.ended_at


@transaction.atomic
def _finish_on_timeout(duel):
    locked = Duel.objects.select_for_update().get(pk=duel.pk)
    if locked.status != Duel.ACTIVE:
        return
    # No winner: running out of time is a draw.
    locked.finish(None, Duel.TIMEOUT)
    duel.status = locked.status
    duel.end_reason = locked.end_reason
    duel.ended_at = locked.ended_at


def expire_stale_challenges():
    """Close out challenges nobody accepted. Cheap; no external calls."""
    cutoff = timezone.now() - Duel.CHALLENGE_TTL
    return Duel.objects.filter(status=Duel.PENDING, created_at__lt=cutoff).update(
        status=Duel.EXPIRED, ended_at=timezone.now()
    )
