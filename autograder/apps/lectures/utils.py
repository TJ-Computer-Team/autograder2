from ..problems.utils import can_see_problem
from ..runtests.utils import SOLVED_VERDICTS, solved_problem_ids

__all__ = [
    "can_see_problem",
    "visible_entries",
    "solved_problem_ids",
    "SOLVED_VERDICTS",
]


def visible_entries(entries, user):
    """Drop entries the user is not allowed to see. External links always pass."""
    return [e for e in entries if e.is_external or can_see_problem(e.problem, user)]
