from decimal import Decimal

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


def usaco_rating_for(division):
    return USACO_RATINGS.get(division, DEFAULT_USACO_RATING)


def compute_index(usaco, cf, inhouse, *, use_writer_formula=False, has_inhouses=True):
    """The index for one set of inputs.

    Writer formula (0.4*min + 0.6*max over USACO and Codeforces) applies to problem
    setters, and to anyone with no in-house scores at all -- otherwise the standard
    three-way weighting would fold in a 0.2 * 0 term and push them below people they
    outrank on every component.
    """
    usaco = Decimal(str(usaco or 0))
    cf = Decimal(str(cf or 0))
    inhouse = Decimal(str(inhouse or 0))

    if use_writer_formula or not has_inhouses:
        return Decimal("0.4") * min(cf, usaco) + Decimal("0.6") * max(cf, usaco)

    low, mid, high = sorted([usaco, cf, inhouse])
    return Decimal("0.2") * low + Decimal("0.35") * mid + Decimal("0.45") * high


def index_for_user(user):
    """The index a user should have right now, from their current fields."""
    return compute_index(
        usaco_rating_for(user.usaco_division),
        user.cf_rating,
        user.inhouse,
        use_writer_formula=user.use_writer_formula,
        has_inhouses=bool(user.inhouses),
    )
