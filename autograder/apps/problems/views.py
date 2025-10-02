from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from ..oauth.decorators import login_required
from .models import Problem
import logging

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
def problemset_view(request):
    problems = Problem.objects.filter(contest__tjioi=settings.TJIOI_MODE)
    if not request.user.is_staff:
        problems = problems.filter(secret=False, contest__start__lte=timezone.now())

    problems = problems.order_by("-id")

    context = {"problems": problems}

    return render(request, "problems/problemset.html", context)


@login_required
def problem_view(request, pid):
    problem = get_object_or_404(Problem, id=pid)
    contest = problem.contest

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

    context = {
        "problem": problem,
        "tl_cpp": problem.tl / 1000,
        "tl_java": problem.tl / 1000 * 2,
        "tl_python": problem.tl / 1000 * 3,
        "statement": format_text(problem.statement),
        "inputtxt": format_text(problem.inputtxt),
        "outputtxt": format_text(problem.outputtxt),
        "samples": format_text(problem.samples),
    }

    return render(request, "problems/problem.html", context)
