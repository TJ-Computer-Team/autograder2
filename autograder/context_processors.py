import logging
import json
import os

from django.conf import settings

logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(settings.BASE_DIR, 'autograder', 'validation_settings.json')


def attendance_enabled(request):
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings_data = {}

    return {"attendance_enabled": settings_data.get("enable_code_attendance", False)}


def cnav_active_item(request):
    """Which contest navbar item to highlight.

    Resolved from the matched route rather than the path -- the contest pages all
    live under /contests/, so path matching can't tell them apart.
    """
    match = request.resolver_match
    if match is None:
        return {"cnav_active": "other"}

    route = f"{match.namespace}:{match.url_name}"

    if route in ("contests:contest", "problems:problem"):
        active = "problems"
    elif route == "contests:standings":
        active = "standings"
    elif route == "contests:status":
        active = "mine" if match.kwargs.get("mine_only") == "mine" else "all"
    elif route == "runtests:submission":
        active = "mine"
    elif match.namespace == "runtests" and match.url_name.startswith("submit"):
        active = "submit"
    else:
        active = "other"

    return {"cnav_active": active}


def active_nav_item(request):
    path = request.path

    if path.startswith("/contests/"):
        active = "contests"
    elif path.startswith("/problems/"):
        active = "problems"
    elif path.startswith("/status/submit/"):
        active = "submit"
    elif path.startswith("/status/"):
        active = "status"
    elif path.startswith("/rankings/"):
        active = "rankings"
    elif path == "/profile/":
        active = "profile"
    elif path.startswith("/info/"):
        active = "info"
    else:
        active = "other"

    return {"active": active}
