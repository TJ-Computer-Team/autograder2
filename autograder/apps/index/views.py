from ..oauth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django_user_agents.utils import get_user_agent
from .models import GraderUser, ProblemOfTheWeek
from ..rankings.models import RatingChange
from django.http import JsonResponse
import requests
import json
import os
from django.contrib.admin.views.decorators import staff_member_required

# --- Start Settings Helpers ---
SETTINGS_FILE = os.path.join(settings.BASE_DIR, 'autograder', 'validation_settings.json')

def get_validation_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "enforce_cf_handle_name_match": False,
            "enforce_cf_handle_for_samuel_zhang": False
        }

def save_validation_settings(settings_data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings_data, f, indent=4)

# --- End Settings Helpers ---


@login_required
def potw_view(request):
    """Render the Problem of the Week page with beginner, intermediate and advanced entries."""
    beginner = ProblemOfTheWeek.objects.filter(level=ProblemOfTheWeek.BEGINNER).first()
    intermediate = ProblemOfTheWeek.objects.filter(level=ProblemOfTheWeek.INTERMEDIATE).first()
    advanced = ProblemOfTheWeek.objects.filter(level=ProblemOfTheWeek.ADVANCED).first()

    context = {
        "active": "potw",
        "beginner": beginner,
        "intermediate": intermediate,
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

# --- CF API Helper ---
def get_codeforces_info(handle):
    url = f"https://codeforces.com/api/user.info?handles={handle}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "OK":
            return data["result"][0]
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to Codeforces API: {e}")
    return None


@login_required
@require_POST
def update_stats(request):
    usaco = request.POST.get("usaco_div", "").strip()
    cf = request.POST.get("cf_handle", "").strip()
    user = request.user

    if usaco and usaco != "none":
        user.usaco_division = {
            "bronze": "Bronze",
            "silver": "Silver",
            "gold": "Gold",
            "plat": "Platinum",
        }.get(usaco, "Not Participated")
    else:
        user.usaco_division = "Not Participated"

    if cf is not None and cf != user.cf_handle:
        validation_settings = get_validation_settings()
        needs_validation = validation_settings.get('enforce_cf_handle_name_match', False) or \
                           (validation_settings.get('enforce_cf_handle_for_samuel_zhang', False) and user.display_name == "Samuel Zhang")

        if needs_validation:
            cf_info = get_codeforces_info(cf)
            if not cf_info:
                return JsonResponse({"status": "error", "message": f"Could not retrieve Codeforces info for handle '{cf}'."})

            first_name = cf_info.get("firstName")
            last_name = cf_info.get("lastName")

            if not first_name or not last_name:
                return JsonResponse({"status": "error", "message": "The Codeforces account must have both a first and last name set."})

            cf_name = f"{first_name} {last_name}".strip()

            if cf_name.lower() != user.display_name.lower():
                return JsonResponse({"status": "error", "message": f"Codeforces name '{cf_name}' does not match your name '{user.display_name}'."})
        
        user.cf_handle = cf

    user.save()
    return JsonResponse({"status": "success", "message": "Profile updated successfully!"})


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

@staff_member_required
def validation_settings_view(request):
    if request.method == 'POST':
        settings_data = {
            'enforce_cf_handle_name_match': request.POST.get('enforce_cf_handle_name_match') == 'on',
            'enforce_cf_handle_for_samuel_zhang': request.POST.get('enforce_cf_handle_for_samuel_zhang') == 'on',
        }
        save_validation_settings(settings_data)
        return redirect('index:validation_settings')

    context = {
        'title': 'Validation Settings',
        'settings': get_validation_settings(),
        'has_permission': True, # For admin template
    }
    return render(request, 'admin/index/validation_settings.html', context)
