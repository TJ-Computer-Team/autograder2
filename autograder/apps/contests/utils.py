from .models import Contest
from ..problems.models import Problem
from ..index.models import GraderUser
from ..runtests.models import Submission
import logging

logger = logging.getLogger(__name__)


def get_standings(cid):
    contest = Contest.objects.get(id=cid)

    problems = list(Problem.objects.filter(contest=contest).order_by("contest_letter"))
    pid_index = {p.id: i for i, p in enumerate(problems)}
    start, end = contest.start, contest.end

    users = GraderUser.objects.filter(is_staff=False)
    stats = {
        u.id: {
            "id": u.id,
            "name": u.display_name,
            "score": 0,
            "problems": [
                {"score": 0, "wrong": 0, "accepted": False, "display": "0"}
                for _ in problems
            ],
        }
        for u in users
    }

    subs = (
        Submission.objects.filter(contest=contest, timestamp__range=(start, end))
        .order_by("timestamp")
        .select_related("usr", "problem")
    )

    for s in subs:
        user_data = stats.get(s.usr_id)
        prob_idx = pid_index.get(s.problem_id)

        if user_data is None or prob_idx is None:
            continue

        problem_result = user_data["problems"][prob_idx]
        if problem_result["accepted"] or s.verdict in ["Skipped", "Rerun"]:
            continue

        if s.verdict in ("Accepted", "AC"):
            problem_points = problems[prob_idx].points
            if problem_points <= 0:
                problem_result["accepted"] = True
                problem_result["display"] = "0"
                continue
            minutes = max(0, int((s.timestamp - start).total_seconds() / 60))
            decayed_score = problem_points - (minutes * 250 / problem_points)
            score = max(problem_points * 0.3, decayed_score)
            score = round(score, 2)
            problem_result["accepted"] = True
            problem_result["score"] = score
            problem_result["display"] = f"{score:g}"
            user_data["score"] += score
        else:
            problem_result["wrong"] += 1
            problem_result["display"] = f"-{problem_result['wrong']}"

    # Filter and sort
    standings = [
        u
        for u in stats.values()
        if u["id"] and (u["score"] > 0 or any(p["wrong"] for p in u["problems"]))
    ]
    standings.sort(key=lambda x: (-x["score"], x["name"]))

    # Assign ranks (with ties)
    prev = None
    for idx, row in enumerate(standings, start=1):
        if prev and row["score"] == prev["score"]:
            row["rank"] = prev["rank"]
        else:
            row["rank"] = idx
        prev = row

    res = {"title": contest.name, "pnum": len(problems), "load": standings}

    return res
