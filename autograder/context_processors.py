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
