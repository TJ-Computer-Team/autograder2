from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
from ..oauth.decorators import login_required, admin_required
from .models import Contest
from ..problems.models import Problem
from ..index.models import GraderUser
from ..runtests.models import Submission
from .utils import get_standings
import logging

logger = logging.getLogger(__name__)


@login_required
def contests_view(request):
    contests = Contest.objects.filter(tjioi=settings.TJIOI_MODE).order_by("-start")
    if not request.user.is_staff:
        contests = contests.filter(start__lte=timezone.now())
    context = {"contests": contests}
    return render(request, "contest/contests.html", context)


@login_required
def contest_view(request, cid):
    contest = get_object_or_404(Contest, pk=cid)

    problems = list(Problem.objects.filter(contest=contest).order_by("contest_letter"))
    if problems is None:
        problems = []

    time_message = contest.start if timezone.now() < contest.start else contest.end
    time_type = "start" if timezone.now() < contest.start else "end"
    if not request.user.is_staff and timezone.now() < contest.start:
        return HttpResponse("Contest has not started yet", status=403)

    ordered = []
    for problem in problems:
        ordered.append(
            {
                "name": problem.name,
                "problem": problem,
                "id": problem.id,
                "letter": problem.contest_letter,
                "points": getattr(problem, "points", 0),
                "solves": 0,
                "available": (
                    not getattr(problem, "secret", False) or request.user.is_staff
                ),
                "users": [],
            }
        )

    subs = Submission.objects.filter(contest=cid)
    users = list(GraderUser.objects.all())
    user_id_map = {user.id: idx for idx, user in enumerate(users)}

    for sub in subs:
        if sub.timestamp > contest.end or sub.timestamp < contest.start:
            continue
        ind = user_id_map.get(sub.usr_id)
        pind = None
        for j, prob in enumerate(ordered):
            if prob["id"] == getattr(sub, "problem_id", None):
                pind = j
                break
        if pind is None or ind is None:
            continue
        if sub.verdict in ["Accepted", "AC"]:
            if ind in ordered[pind]["users"]:
                continue
            ordered[pind]["solves"] += 1
            ordered[pind]["users"].append(ind)

    context = {
        "not_empty": "yes" if ordered else "no",
        "title": contest.name,
        "problems": ordered,
        "user": request.user.id,
        "cid": contest.id,
        "timeStatus": time_message,
        "timeType": time_type,
        "editorial": getattr(contest, "editorial", None),
        "contest_over": timezone.now() > contest.end,
    }
    return render(request, "contest/contest.html", context)


@login_required
def contest_standings_view(request, cid):
    standings = get_standings(cid)
    problems = Problem.objects.filter(contest_id=cid)
    contest = get_object_or_404(Contest, id=cid)

    if timezone.now() < contest.start:
        return HttpResponse("Contest has not started yet", status=403)

    context = {
        "title": standings["title"],
        "cid": cid,
        "pnum": standings["pnum"],
        "load": standings["load"],
        "problems": problems,
        "contest_over": timezone.now() > contest.end,
    }

    return render(request, "contest/standings.html", context)


@login_required
def contest_status_view(request, cid, mine_only, page):
    contest = get_object_or_404(Contest, id=cid)
    if timezone.now() < contest.start:
        return HttpResponse("Contest has not started yet", status=403)
    subs = Submission.objects.filter(contest=contest)
    if not request.user.is_staff:
        subs = subs.filter(usr__is_staff=False)

    if mine_only == "mine" or (
        timezone.now() < contest.end and not request.user.is_staff
    ):
        subs = subs.filter(usr=request.user)

    if not request.user.is_staff:
        subs = subs.filter(timestamp__gte=contest.start)

    subs = subs.order_by("-timestamp")

    # Pagination
    paginator = Paginator(subs, 25)  # Show 25 submissions per page
    page_number = page
    page_obj = paginator.get_page(page_number)

    context = {
        "title": contest.name,
        "user_id": request.user.id,
        "cid": cid,
        "page_obj": page_obj,
        "submissions": page_obj.object_list,
        "contest_over": timezone.now() > contest.end,
        "mine_only": mine_only,
    }
    return render(request, "contest/status.html", context)


@login_required
@admin_required
def contest_skip_view(request, sid, cid, mine_only, page):
    sub = get_object_or_404(Submission, id=sid)
    sub.verdict = "Skipped"
    sub.insight = "Your submission was manually skipped by an admin"
    sub.save()

    return redirect("contests:status", cid=cid, mine_only=mine_only, page=page)
