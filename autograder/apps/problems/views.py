from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.contrib import messages
from ..oauth.decorators import login_required
from ..contests.utils import get_contest_nav
from ..runtests.utils import solved_problem_ids
from .models import Problem
from .utils import can_see_problem
import logging

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
def problemset_view(request):
    problems = Problem.objects.all()
    if not request.user.is_staff:
        # Lecture-only problems have no contest, so a bare `contest__start__lte`
        # would hide them from the problemset entirely.
        problems = problems.filter(secret=False).filter(
            Q(contest__isnull=True) | Q(contest__start__lte=timezone.now())
        )
        # Prevent non-TJIOI users from seeing TJIOI problems
        if not request.user.is_tjioi:
            problems = problems.exclude(contest__tjioi=True)

    problems = list(problems.select_related("contest").order_by("-id"))
    solved = solved_problem_ids(request.user, [p.id for p in problems])

    context = {
        "problems": problems,
        "solved_ids": solved,
        "rows": [{"problem": p, "solved": p.id in solved} for p in problems],
    }

    return render(request, "problems/problemset.html", context)


@login_required
def problem_view(request, pid):
    problem = get_object_or_404(Problem, id=pid)
    contest = problem.contest

    if not can_see_problem(problem, request.user):
        logger.info(f"User {request.user} tried to access gated problem {problem.name}")
        messages.error(request, "You do not have permission to access this problem.")
        # A lecture-only problem has no contest to send them back to.
        if contest is None:
            return redirect("lectures:list")
        return redirect("contests:contest", cid=contest.id)

    def format_text(text):
        return text.replace("\n", "<br>") if text else ""

    context = {
        "problem": problem,
        "contest_nav": get_contest_nav(request, problem.contest_id),
        "tl_cpp": problem.tl / 1000,
        "tl_java": problem.tl / 1000 * 2,
        "tl_python": problem.tl / 1000 * 3,
        "statement": format_text(problem.statement),
        "inputtxt": format_text(problem.inputtxt),
        "outputtxt": format_text(problem.outputtxt),
        "samples": format_text(problem.samples),
    }

    return render(request, "problems/problem.html", context)
