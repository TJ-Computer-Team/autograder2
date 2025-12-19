from ..oauth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django_user_agents.utils import get_user_agent
from .models import GraderUser, ProblemOfTheWeek
from ..rankings.models import RatingChange


@login_required
def potw_view(request):
    """Render the Problem of the Week page with beginner and advanced entries."""
    beginner = ProblemOfTheWeek.objects.filter(level=ProblemOfTheWeek.BEGINNER).first()
    advanced = ProblemOfTheWeek.objects.filter(level=ProblemOfTheWeek.ADVANCED).first()

    context = {
        "active": "potw",
        "beginner": beginner,
        "advanced": advanced,
    }
    return render(request, "index/potw.html", context)

import logging

logger = logging.getLogger(__name__)
# Create your views here.


def mobile_home(request):
    user_agent = get_user_agent(request)

    if not user_agent.is_mobile:
        return redirect("/")
    return render(request, "index/mobile.html")


def index_view(request):
    if request.user.is_authenticated:
        return redirect("index:profile")

    context = {"tjioi": settings.TJIOI_MODE}
    return render(request, "index/index.html", context)


@login_required
def first_time_view(request):
    if not request.user.first_time:
        return redirect("index:profile")

    return render(request, "index/start.html")


@login_required
@require_POST
def update_first_time(request):
    email = request.POST.get("email", "").strip()
    request.user.personal_email = email
    request.user.first_time = False
    request.user.save()
    return redirect("index:profile")


@login_required
def profile_view(request):
    if request.user.first_time:
        return redirect("index:first_time")

    cfh = request.user.cf_handle

    context = {"cf_handle": cfh if cfh and len(cfh) > 0 else ""}
    return render(request, "index/profile.html", context=context)


@login_required
@require_POST
def update_stats(request):
    usaco = request.POST.get("usaco_div", "").strip()
    cf = request.POST.get("cf_handle", "").strip()

    if usaco and usaco != "none":
        request.user.usaco_division = {
            "bronze": "Bronze",
            "silver": "Silver",
            "gold": "Gold",
            "plat": "Platinum",
        }.get(usaco, "Not Participated")
    else:
        request.user.usaco_division = "Not Participated"

    if cf is not None:
        request.user.cf_handle = cf

    request.user.save()
    return redirect("index:profile")


@login_required
def info_view(request):
    context = {"active": "info", "tjioi": settings.TJIOI_MODE}
    return render(request, "index/info.html", context=context)


@login_required
def user_profile_view(request, id):
    user = get_object_or_404(GraderUser, pk=id)

    if settings.TJIOI_MODE and not request.user.is_staff:
        return redirect("index:profile")

    rating_changes = (
        RatingChange.objects.filter(user=user)
        .order_by("time")
        .values("id", "rating", "time")
    )

    context = {
        "name": user.display_name,
        "username": user.username,
        "cf": user.cf_handle,
        "usaco": user.usaco_division,
        "rating_changes": list(rating_changes),
        "no_rating_history": "false",
        "admin": request.user.is_staff,
    }

    if rating_changes.count() == 0:
        context["no_rating_history"] = "true"

    return render(request, "index/user_profile.html", context)


@login_required
def toggle_particles(request):
    user = request.user
    user.particles_enabled = not user.particles_enabled
    user.save()
    next_url = request.GET.get("next", "/")
    return redirect(next_url)
