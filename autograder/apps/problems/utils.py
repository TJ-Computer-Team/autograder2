from django.utils import timezone


def can_see_problem(problem, user):
    """Whether `user` may view/submit to `problem`.

    The single source of truth for the three gates that were previously repeated
    inline across problems/views.py, runtests/views.py and the lecture sets:
    secret problems, unreleased contests, and TJIOI-only contests.
    """
    if user.is_staff:
        return True
    if problem.secret:
        return False

    contest = problem.contest
    if contest is None:
        # Lecture-only problem: no contest window to wait for, so `secret` above
        # is the only gate.
        return True

    if contest.tjioi and not user.is_tjioi:
        return False
    return contest.start <= timezone.now()
