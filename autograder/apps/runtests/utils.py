from .models import Submission

# Filler data and older rows use "AC"; the grader writes "Accepted".
SOLVED_VERDICTS = ("Accepted", "AC")


def solved_problem_ids(user, problem_ids):
    """Problem ids this user has an accepted submission for. One query."""
    if not problem_ids:
        return set()
    return set(
        Submission.objects.filter(
            usr=user, problem_id__in=problem_ids, verdict__in=SOLVED_VERDICTS
        ).values_list("problem_id", flat=True)
    )
