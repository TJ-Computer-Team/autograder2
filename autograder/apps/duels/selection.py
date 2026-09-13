import logging
import random

from ..index.cf_utils import fetch_cf_problems, fetch_solved_set

logger = logging.getLogger(__name__)


class SelectionError(Exception):
    """No problem could be drawn; the duel must not start."""


def _parse_tags(raw):
    return {t.strip().lower() for t in (raw or "").split(",") if t.strip()}


def pick_duel_problem(rating_min, rating_max, handles, tags=""):
    """Draw a Codeforces problem in range that none of `handles` has solved.

    Raises SelectionError rather than returning something unsuitable. Starting a
    duel on a problem one player has already solved would let them paste an old
    accepted solution and win instantly, so "couldn't check" has to be fatal, not
    a silent fallback.
    """
    problems = fetch_cf_problems()
    if not problems:
        raise SelectionError("Could not reach Codeforces to load the problemset.")

    wanted_tags = _parse_tags(tags)
    candidates = [
        p
        for p in problems
        if p.get("rating") is not None
        and rating_min <= p["rating"] <= rating_max
        and p.get("contestId") is not None
        and p.get("index")
        and (not wanted_tags or wanted_tags <= {t.lower() for t in p.get("tags", [])})
    ]
    if not candidates:
        raise SelectionError(
            f"No Codeforces problems rated {rating_min}-{rating_max}"
            + (f" tagged {tags}." if wanted_tags else ".")
        )

    solved = set()
    for handle in handles:
        # None means the lookup failed. Treating that as "solved nothing" would
        # reopen the exact hole this check exists to close.
        handle_solved = fetch_solved_set(handle)
        if handle_solved is None:
            raise SelectionError(
                f"Could not load Codeforces history for {handle}. Try again."
            )
        solved |= handle_solved

    fresh = [p for p in candidates if (p["contestId"], p["index"]) not in solved]
    if not fresh:
        raise SelectionError(
            f"Both players have already solved every problem rated "
            f"{rating_min}-{rating_max}. Widen the range."
        )

    return random.choice(fresh)
