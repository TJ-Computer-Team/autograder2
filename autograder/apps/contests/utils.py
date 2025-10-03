from .models import Contest
from ..problems.models import Problem
from ..index.models import GraderUser
from ..runtests.models import Submission
import logging

logger = logging.getLogger(__name__)


def get_standings(cid):
    contest = Contest.objects.get(id=cid)

    problems = list(Problem.objects.filter(contest=contest).order_by("contest_letter"))
    pid_index = {p.contest_letter: i for i, p in enumerate(problems)}
    start, end = contest.start, contest.end

    users = GraderUser.objects.filter(is_staff=False)
    stats = {
        u.id: {
            "id": u.id,
            "name": u.display_name,
            "solved": 0,
            "penalty": 0,
            "problems": [0] * len(problems),
        }
        for u in users
    }

    subs = (
        Submission.objects.filter(contest=contest, timestamp__range=(start, end))
        .order_by("timestamp")
        .select_related("usr")
    )

    for s in subs:
        user_data = stats.get(s.usr_id)
        prob_idx = pid_index.get(s.problem.contest_letter)

        if user_data is None or prob_idx is None:
            continue

        if user_data["problems"][prob_idx] <= 0:
            user_data["problems"][prob_idx] -= 1

        if s.verdict in ("Accepted", "AC"):
            if user_data["problems"][prob_idx] < 0:
                user_data["solved"] += problems[prob_idx].points
                minutes = int((s.timestamp - start).total_seconds() / 60)

                user_data["problems"][prob_idx] = abs(user_data["problems"][prob_idx])
                user_data["penalty"] += minutes + 5 * user_data["problems"][prob_idx]

    # Filter and sort
    standings = [
        u for u in stats.values() if u["solved"] > 0 and u["penalty"] >= 0 and u["id"]
    ]
    standings.sort(key=lambda x: (-x["solved"], x["penalty"]))

    # Assign ranks (with ties)
    prev = None
    for idx, row in enumerate(standings, start=1):
        if (
            prev
            and row["solved"] == prev["solved"]
            and row["penalty"] == prev["penalty"]
        ):
            row["rank"] = prev["rank"]
        else:
            row["rank"] = idx
        prev = row

    res = {"title": contest.name, "pnum": len(problems), "load": standings}

    return res
