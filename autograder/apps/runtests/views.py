from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator, EmptyPage
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from ..oauth.decorators import login_required
from ..problems.models import Problem
from ..contests.models import Contest
from .models import Submission
from .tasks import grade_submission_task
import logging

logger = logging.getLogger(__name__)


def get_last_sub_lang(user):
    try:
        return Submission.objects.filter(usr=user).latest().language
    except Exception:
        return "cpp"


@login_required
def submit_view(request, cid=None, pid=None):
    context = {"last_sub_lang": get_last_sub_lang(request.user)}

    if pid is not None:
        problem = get_object_or_404(Problem, id=pid)

        if (
            not request.user.is_staff
            and (problem.secret or problem.contest.start > timezone.now())
        ) or not (settings.TJIOI_MODE == problem.contest.tjioi):
            return redirect("runtests:submit")

        context["problem"] = problem

    elif cid is not None:
        contest = get_object_or_404(Contest, id=cid)
        problems = Problem.objects.filter(
            contest__id=cid, contest__tjioi=settings.TJIOI_MODE
        )
        if not request.user.is_staff:
            problems = problems.filter(secret=False)
            if contest.start > timezone.now():
                return redirect("runtests:submit")

        problems = problems.order_by("id")
        context["contest"] = contest
        context["problems"] = problems

    else:
        problems = Problem.objects.filter(contest__tjioi=settings.TJIOI_MODE)
        if not request.user.is_staff:
            problems = problems.filter(secret=False, contest__start__lte=timezone.now())

        problems = problems.order_by("id")
        context["problems"] = problems

    return render(request, "runtests/submit.html", context)


@login_required
def status_view(request, page, cid=None, mine=False):
    submissions = Submission.objects.filter(contest__tjioi=settings.TJIOI_MODE)
    if not request.user.is_staff:
        submissions = submissions.filter(usr__is_staff=False)

    if cid is not None:
        submissions = submissions.filter(contest=cid)

    if mine:
        submissions = submissions.filter(usr=request.user)

    submissions = submissions.order_by("-timestamp")
    paginator = Paginator(submissions, 25)  # 25 per page

    try:
        submissions_page = paginator.get_page(page)
    except EmptyPage:
        return redirect("runtests:status", cid=cid, mine=mine, page=1)

    context = {
        "submissions": submissions_page.object_list,
        "page_obj": submissions_page,
        "admin": request.user.is_staff,
        "page": page,
        "cid": cid,
        "mine": mine,
    }

    return render(request, "runtests/status.html", context)


@login_required
def submission_view(request, id):
    submission = get_object_or_404(Submission, id=id)

    if submission.usr == request.user or request.user.is_staff:
        context = {"admin": request.user.is_staff, "submission": submission}
        if request.user.is_staff:
            context["insight"] = submission.insight

        return render(request, "runtests/submission.html", context)

    context = {"insight": "You do not have permission to view this submission"}
    return render(request, "runtests/submission.html", context)


@login_required
@require_POST
def submit_post(request):
    pid = request.POST.get("problemid")
    lang = request.POST.get("lang")
    code = request.POST.get("code")
    uploaded_file = request.FILES.get("files")

    if lang not in ["python", "cpp", "java"]:
        logger.info(f"user {request.user} tried to use invalid lang")
        return HttpResponse(status=500)

    problem = Problem.objects.select_related("contest").get(id=pid)

    if len(code) > 60000:
        return HttpResponse(status=413)

    if uploaded_file:
        filename = uploaded_file.name
        if not filename.lower().endswith((".py", ".cpp", ".java")):
            return HttpResponse("Invalid file extension")

        ext = filename.split(".")[-1].lower()
        lang = {"py": "python", "cpp": "cpp", "java": "java"}[ext]
        code = uploaded_file.read().decode("utf-8")

    if not request.user.is_staff and timezone.now() < problem.contest.start:
        return HttpResponse("Contest has not started yet", status=403)

    last_sub_time = None
    try:
        last_sub_time = Submission.objects.filter(usr=request.user).latest().timestamp
    except Exception:
        pass

    if (
        last_sub_time is None
        or timezone.now() - last_sub_time > timedelta(seconds=30)
        or request.user.is_staff
        or settings.DEBUG
    ):
        new_sub = Submission.objects.create(
            usr=request.user,
            code=code,
            problem=problem,
            language=lang,
            contest=problem.contest,
        )
        new_sub.save()

        grade_submission_task.delay(new_sub.id)
        return redirect("runtests:status", page=1)
    else:
        return HttpResponse(
            "Too many requests! Please wait at least 30 seconds between submissions!",
            status=429,
        )
        
@login_required
@require_POST
def run_code_post(request):
    """Process code execution request for testing (similar to submit_post but without saving to database)"""
    try:
        lang = request.POST.get("lang")
        code = request.POST.get("code")
        input_data = request.POST.get("input", "")

        if lang not in ["python", "cpp", "java"]:
            return JsonResponse({"error": "Invalid language"}, status=400)

        if not code or not code.strip():
            return JsonResponse({"error": "No code provided"}, status=400)

        if len(code) > 60000:
            return JsonResponse({"error": "Code too long (max 60,000 characters)"}, status=413)

        # Temporarily disabled to avoid overloading submission queue
        # TODO: Implement actual code execution service for testing later

        return JsonResponse({
            "success": True,
            "output": "Running code on here will be implemented later!\n\nCode validation passed:\n- Language: " + lang.upper() + "\n- Code length: " + str(len(code)) + " characters\n- Input length: " + str(len(input_data)) + " characters",
            "language": lang,
            "verdict": "SKIP",  # Skip verdict to indicate not actually executed
            "runtime": -1,
            "memory": -1
        })

    except Exception as e:
        return JsonResponse({"error": f"Execution failed: {str(e)}"}, status=500)
