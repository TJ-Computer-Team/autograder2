from django.shortcuts import redirect
from django.contrib.auth import logout


def logout_view(request):
    if request.user.is_authenticated:
        request.user.access_token = None
        request.user.save()
    logout(request)
    return redirect("index:index")
