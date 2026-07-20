from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from ..oauth.decorators import login_required
from .models import Problem
from ..runtests.models import Submission
import logging

logger = logging.getLogger(__name__)


def submission_status(verdict):
    normalized = (verdict or "").lower()
    if normalized in ["accepted", "ac"]:
        return {
            "label": "Accepted",
            "icon": "check",
            "class": "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
        }
    if any(term in normalized for term in ["waiting", "queue", "running", "judging", "rerun"]):
        return {
            "label": verdict or "Running",
            "icon": "minus",
            "class": "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
        }
    if "time" in normalized or "tle" in normalized:
        return {
            "label": verdict or "Time Limit",
            "icon": "clock",
            "class": "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
        }
    if any(term in normalized for term in ["wrong", "wa", "failed", "error", "runtime", "compile"]):
        return {
            "label": verdict or "Wrong Answer",
            "icon": "x",
            "class": "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
        }
    if normalized:
        return {
            "label": verdict,
            "icon": "alert-triangle",
            "class": "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
        }
    return {
        "label": "Unsubmitted",
        "icon": "circle",
        "class": "bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400",
    }


# Create your views here.
@login_required
def problemset_view(request):
    problems = Problem.objects.all()
    if not request.user.is_staff:
        problems = problems.filter(secret=False, contest__start__lte=timezone.now())
        # Prevent non-TJIOI users from seeing TJIOI problems
        if not request.user.is_tjioi:
            problems = problems.exclude(contest__tjioi=True)

    problems = problems.order_by("-id")

    context = {"problems": problems}

    return render(request, "problems/problemset.html", context)


@login_required
def problem_view(request, pid):
    problem = get_object_or_404(Problem, id=pid)
    contest = problem.contest

    # Prevent non-TJIOI users from viewing problems in TJIOI contests
    if contest.tjioi and not request.user.is_staff and not request.user.is_tjioi:
        logger.info(
            f"User {request.user} tried to access TJIOI problem {problem.name}"
        )
        messages.error(
            request, "You do not have permission to access this problem."
        )
        return redirect("contests:contest", cid=contest.id)

    if not request.user.is_staff and (timezone.now() < contest.start or problem.secret):
        logger.info(
            f"User {request.user} tried to access problem {problem.name} before contest start"
        )
        messages.error(
            request, "You cannot access this problem before the contest starts."
        )
        return redirect("contests:contest", cid=contest.id)

    def format_text(text):
        return text.replace("\n", "<br>") if text else ""

    contest_problems = Problem.objects.filter(contest=contest).order_by("contest_letter")
    user_submissions = (
        Submission.objects.filter(usr=request.user, contest=contest)
        .select_related("problem")
        .order_by("-timestamp")
    )

    latest_by_problem = {}
    accepted_problem_ids = set()
    for submission in user_submissions:
        latest_by_problem.setdefault(submission.problem_id, submission)
        if submission.verdict in ["Accepted", "AC"]:
            accepted_problem_ids.add(submission.problem_id)

    sidebar_problems = []
    for contest_problem in contest_problems:
        latest_submission = latest_by_problem.get(contest_problem.id)
        status = submission_status(latest_submission.verdict if latest_submission else "")
        if contest_problem.id in accepted_problem_ids:
            status = submission_status("Accepted")
        sidebar_problems.append(
            {
                "problem": contest_problem,
                "status": status,
                "current": contest_problem.id == problem.id,
            }
        )

    problem_submissions = []
    for submission in user_submissions.filter(problem=problem):
        problem_submissions.append(
            {
                "submission": submission,
                "status": submission_status(submission.verdict),
            }
        )

    context = {
        "problem": problem,
        "tl_cpp": problem.tl / 1000,
        "tl_java": problem.tl / 1000 * 2,
        "tl_python": problem.tl / 1000 * 3,
        "statement": format_text(problem.statement),
        "inputtxt": format_text(problem.inputtxt),
        "outputtxt": format_text(problem.outputtxt),
        "samples": format_text(problem.samples),
        "sidebar_problems": sidebar_problems,
        "problem_submissions": problem_submissions,
    }

    return render(request, "problems/problem.html", context)
