import logging

logger = logging.getLogger(__name__)


def active_nav_item(request):
    path = request.path

    if path == "/":
        active = "home"
    elif path.startswith("/contests/"):
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
