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
        and p["contestId"] >= 1000
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


def ladder_ratings(rating_min, rating_max, count):
    """Evenly spaced targets from min to max, snapped to CF's 100-point steps."""
    if count <= 1:
        return [rating_min]
    step = (rating_max - rating_min) / (count - 1)
    return [round((rating_min + i * step) / 100) * 100 for i in range(count)]


def pick_ladder_problems(rating_min, rating_max, count, handles, tags=""):
    """Draw `count` distinct problems, easiest first, that no handle has solved.

    Each rung takes the unused problem closest to its target rating, so a gap in
    the problemset bends the ramp a little instead of failing the whole ladder.
    Same fail-closed rule as pick_duel_problem for unreadable histories.
    """
    problems = fetch_cf_problems()
    if not problems:
        raise SelectionError("Could not reach Codeforces to load the problemset.")

    wanted_tags = _parse_tags(tags)
    solved = set()
    for handle in handles:
        handle_solved = fetch_solved_set(handle)
        if handle_solved is None:
            raise SelectionError(
                f"Could not load Codeforces history for {handle}. Try again."
            )
        solved |= handle_solved

    pool = [
        p
        for p in problems
        if p.get("rating") is not None
        and rating_min <= p["rating"] <= rating_max
        and p.get("contestId") is not None
        and p["contestId"] >= 1000
        and p.get("index")
        and (p["contestId"], p["index"]) not in solved
        and (not wanted_tags or wanted_tags <= {t.lower() for t in p.get("tags", [])})
    ]
    if len(pool) < count:
        raise SelectionError(
            f"Only {len(pool)} unsolved problems rated {rating_min}-{rating_max}"
            + (f" tagged {tags}" if wanted_tags else "")
            + f"; need {count}. Widen the range or use fewer problems."
        )

    picked = []
    for target in ladder_ratings(rating_min, rating_max, count):
        best = min(abs(p["rating"] - target) for p in pool)
        choice = random.choice([p for p in pool if abs(p["rating"] - target) == best])
        pool.remove(choice)
        picked.append(choice)
    # Nearest-match can hand a later rung an easier problem; keep it a climb.
    picked.sort(key=lambda p: p["rating"])
    return picked
