from django.db.models import Q
from django.utils import timezone

from ..contests.models import Contest


def can_see_problem(problem, user):
    """Whether `user` may view/submit to `problem`.

    The single source of truth for the gates that were previously repeated
    inline across problems/views.py, runtests/views.py and the lecture sets:
    secret problems, unreleased contests, TJIOI-only contests, and contests
    hidden from admins who aren't on their visible_to list.
    """
    contest = problem.contest
    if user.is_staff and (contest is None or contest.is_admin_for(user)):
        return True
    if problem.secret:
        return False

    if contest is None:
        # Lecture-only problem: no contest window to wait for, so `secret` above
        # is the only gate.
        return True

    # Admins left off a contest's visible_to still see TJIOI contests; they just
    # wait for the start like everyone else.
    if contest.tjioi and not user.is_tjioi and not user.is_staff:
        return False
    return contest.start <= timezone.now()


def exclude_locked_problems(problems, user):
    """Drop problems an admin could only see through contest admin privileges
    they don't have: secret or unstarted problems of contests in
    ``Contest.locked_for(user)``. Callers already filter these for non-staff.
    """
    return problems.exclude(
        Q(contest__in=Contest.locked_for(user))
        & (Q(secret=True) | Q(contest__start__gt=timezone.now()))
    )
