import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Cup, CupEntry, CupMatch, Duel

logger = logging.getLogger(__name__)


class CupError(Exception):
    """A staff action can't be done right now; the message says why."""


def seed_order(size):
    """Seeds in bracket order for a power-of-two `size`: 1 v size, and the top two
    seeds can only meet in the final. size 8 -> [1, 8, 4, 5, 2, 7, 3, 6]."""
    order = [1]
    while len(order) < size:
        n = len(order) * 2
        order = [s for seed in order for s in (seed, n + 1 - seed)]
    return order


@transaction.atomic
def draw_bracket(cup):
    """Seed everyone by Codeforces rating and lay out the whole bracket.

    The field is padded to a power of two with byes, which go to the top seeds.
    """
    cup = Cup.objects.select_for_update().get(pk=cup.pk)
    if cup.status != Cup.REGISTRATION:
        raise CupError("The bracket has already been drawn.")

    entries = list(
        cup.entries.select_related("user").order_by(
            F("user__cf_rating").desc(nulls_last=True), "joined_at"
        )
    )
    if len(entries) < 2:
        raise CupError("Need at least two players.")

    for seed, entry in enumerate(entries, start=1):
        entry.seed = seed
    CupEntry.objects.bulk_update(entries, ["seed"])
    by_seed = {e.seed: e.user for e in entries}

    size = 2
    while size < len(entries):
        size *= 2
    rounds = size.bit_length() - 1

    order = seed_order(size)
    for r in range(1, rounds + 1):
        for slot in range(size >> r):
            match = CupMatch(cup=cup, round=r, slot=slot)
            if r == 1:
                match.player_a = by_seed.get(order[2 * slot])
                match.player_b = by_seed.get(order[2 * slot + 1])
                match.is_bye = match.player_b is None
            match.save()

    cup.status = Cup.RUNNING
    cup.round_count = rounds
    cup.error = ""
    cup.save(update_fields=["status", "round_count", "error"])

    for match in cup.matches.filter(round=1, is_bye=True):
        _decide(match, match.player_a, "bye")
    return cup


def round_is_done(cup, round_number):
    return not cup.matches.filter(round=round_number, winner__isnull=True).exists()


def start_next_round(cup):
    """Claim the next round and hand it to the task that starts its duels."""
    with transaction.atomic():
        cup = Cup.objects.select_for_update().get(pk=cup.pk)
        if cup.status != Cup.RUNNING:
            raise CupError("The cup isn't running.")
        if cup.current_round >= cup.round_count:
            raise CupError("Every round has been played.")
        if cup.current_round and not round_is_done(cup, cup.current_round):
            raise CupError("Some matches in this round haven't finished yet.")
        cup.current_round += 1
        cup.error = ""
        cup.save(update_fields=["current_round", "error"])

    from .tasks import start_cup_round

    transaction.on_commit(lambda: start_cup_round.delay(cup.pk, cup.current_round))
    return cup


def create_match_duel(match, minutes):
    """A pre-accepted duel for this match. The caller starts it (start_duel)."""
    low, high = match.cup.rating_range(match.round)
    return Duel.objects.create(
        challenger=match.player_a,
        opponent=match.player_b,
        rating_min=low,
        rating_max=high,
        duration_minutes=minutes,
        accepted_at=timezone.now(),
        bracket_match=match,
    )


def duel_finished(duel):
    """Called from Duel.finish for every cup duel: advance the winner, or replay."""
    with transaction.atomic():
        match = (
            CupMatch.objects.select_for_update()
            .select_related("cup")
            .get(pk=duel.bracket_match_id)
        )
        if match.winner_id:
            return  # staff already decided it

        if duel.winner_id:
            _decide(match, duel.winner, "")
            return
        if duel.end_reason != Duel.TIMEOUT:
            return  # voided; staff will pick a winner

        if match.duels.count() < 2:
            # Nobody solved it: one sudden-death rematch on a fresh problem.
            rematch = create_match_duel(match, match.cup.sudden_death_minutes)
            from .tasks import start_duel

            transaction.on_commit(lambda: start_duel.delay(rematch.pk))
            return

        # Two draws in a row: the better seed goes through rather than stalling
        # the whole round.
        seeds = dict(
            CupEntry.objects.filter(
                cup=match.cup, user__in=[match.player_a, match.player_b]
            ).values_list("user_id", "seed")
        )
        a_seed = seeds.get(match.player_a_id) or 10**6
        b_seed = seeds.get(match.player_b_id) or 10**6
        _decide(match, match.player_a if a_seed <= b_seed else match.player_b, "seed")


@transaction.atomic
def set_winner(match, user):
    """Staff override for a match in the current round. Stops any live duel."""
    match = CupMatch.objects.select_for_update().select_related("cup").get(pk=match.pk)
    if user.pk not in (match.player_a_id, match.player_b_id):
        raise CupError("That player isn't in this match.")
    if match.round != match.cup.current_round:
        raise CupError("Only matches in the current round can be overridden.")
    if match.winner_id:
        raise CupError("That match is already decided.")

    # Updated directly rather than via finish(), which would re-enter this module.
    match.duels.filter(status__in=(Duel.PENDING, Duel.ACTIVE)).update(
        status=Duel.FINISHED, end_reason=Duel.VOIDED, ended_at=timezone.now()
    )
    _decide(match, user, "staff")


def _decide(match, winner, how):
    """Record the winner and move them into the next round. Caller holds the lock."""
    match.winner = winner
    match.decided_by = how
    match.save(update_fields=["winner", "decided_by"])

    cup = match.cup
    if match.round == cup.round_count:
        Cup.objects.filter(pk=cup.pk).update(
            status=Cup.FINISHED, champion=winner, ended_at=timezone.now()
        )
        return

    side = "player_a" if match.slot % 2 == 0 else "player_b"
    CupMatch.objects.filter(
        cup=cup, round=match.round + 1, slot=match.slot // 2
    ).update(**{side: winner})
