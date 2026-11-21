from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

# One definition of the index, used by the rankings page, the post-save task, and
# the update_rankings command. These had drifted into three separate copies, which
# is how a user's index came to depend on which path last touched their row.
#
# The rankings page now derives the index at render time rather than trusting the
# stored column, so what it shows can never disagree with the USACO, Codeforces and
# in-house numbers printed beside it.

USACO_RATINGS = {
    "Not Participated": 800,
    "Bronze": 800,
    "Silver": 1200,
    "Gold": 1600,
    "Platinum": 1900,
    "Camper": 2200,
}
DEFAULT_USACO_RATING = 800

INHOUSE_PRECISION = Decimal("0.001")  # matches GraderUser.inhouse's decimal_places


def usaco_rating_for(division):
    return USACO_RATINGS.get(division, DEFAULT_USACO_RATING)


def finished_rated_contests():
    """The contests that count this season: rated and already over.

    A rated contest that is scheduled or still running has no final standings
    yet, so it must not count as one someone skipped.
    """
    from ..contests.models import Contest

    return Contest.objects.filter(
        rated=True, season=settings.CURRENT_SEASON, end__lte=timezone.now()
    )


@dataclass(frozen=True)
class SeasonContests:
    """What the writer-formula decision needs to know about the season."""

    any_finished: bool
    writer_ids: frozenset

    @classmethod
    def load(cls, contests=None):
        if contests is None:
            contests = finished_rated_contests()
        contests = list(contests.prefetch_related("writers"))
        return cls(
            any_finished=bool(contests),
            writer_ids=frozenset(w.id for c in contests for w in c.writers.all()),
        )


def inhouse_contest_score(rank, participants):
    """Score for placing ``rank`` of ``participants``: 2000 for first, ~800 for last."""
    score = Decimal(1200) * (participants - rank + 1) / participants + 800
    return score.quantize(INHOUSE_PRECISION)


def inhouse_score(taken_scores):
    """A user's in-house: their best contest taken this season, or 0 if none."""
    return max(taken_scores, default=Decimal(0))


def uses_writer_formula(*, took_any, wrote_any, any_finished):
    """Whether a user is ranked by the writer formula instead of the standard one.

    Only for people who have taken no in-house this season and either wrote one
    (anyone who wrote one and skipped the rest stays a writer) or have had none
    to take yet. Taking a single in-house moves a writer onto the standard formula.
    """
    if took_any:
        return False
    return wrote_any or not any_finished


def compute_index(usaco, cf, inhouse, *, use_writer_formula=False):
    """The index for one set of inputs.

    Writer formula: 0.4*min + 0.6*max over USACO and Codeforces.
    Standard: 0.2/0.35/0.45 over USACO, Codeforces and in-house, smallest to largest.
    """
    usaco = Decimal(str(usaco or 0))
    cf = Decimal(str(cf or 0))
    inhouse = Decimal(str(inhouse or 0))

    if use_writer_formula:
        return Decimal("0.4") * min(cf, usaco) + Decimal("0.6") * max(cf, usaco)

    low, mid, high = sorted([usaco, cf, inhouse])
    return Decimal("0.2") * low + Decimal("0.35") * mid + Decimal("0.45") * high


def index_for_user(user, season=None):
    """The index a user should have right now, from their current fields.

    ``user.inhouses`` holds the scores of the in-houses they took (written ones
    are left out), as stored by update_rankings. Pass ``season`` when ranking
    many users to avoid reloading the contests for each one.
    """
    if season is None:
        season = SeasonContests.load()
    return compute_index(
        usaco_rating_for(user.usaco_division),
        user.cf_rating,
        user.inhouse,
        use_writer_formula=uses_writer_formula(
            took_any=bool(user.inhouses),
            wrote_any=user.id in season.writer_ids,
            any_finished=season.any_finished,
        ),
    )
