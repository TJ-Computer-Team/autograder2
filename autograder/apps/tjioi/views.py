from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


# Create your views here.
@require_http_methods(["GET", "POST"])
def tjioi_login_view(request):
    if request.user.is_authenticated:
        return redirect("index:profile")

    context = {}

    if request.method == "POST":
        username = request.POST.get("id", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_tjioi and settings.TJIOI_MODE:
            login(request, user)
            return redirect("index:profile")
        else:
            if user is None:
                logger.info(f"Invalid TJIOI login under user {username}")
            elif not user.is_tjioi:
                logger.info(f"Non-tjioi user {username} tried to log in using tjioi")
            elif not settings.TJIOI_MODE:
                logger.info(
                    f"TJIOI user {username} tried to log without tjioi mode. Try turning on tjioi mode in settings"
                )
            context["error"] = "Login failed"

    return render(request, "tjioi/login.html", context)
