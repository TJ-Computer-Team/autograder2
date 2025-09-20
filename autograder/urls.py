"""
URL configuration for autograder project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = (
    [
        path("djangoadmin/", admin.site.urls),
        path("", include("autograder.apps.index.urls", namespace="index")),
        path("oauth/", include("autograder.apps.oauth.urls", namespace="oauth")),
        path(
            "contests/", include("autograder.apps.contests.urls", namespace="contests")
        ),
        path(
            "problems/", include("autograder.apps.problems.urls", namespace="problems")
        ),
        path("status/", include("autograder.apps.runtests.urls", namespace="runtests")),
        path(
            "rankings/", include("autograder.apps.rankings.urls", namespace="rankings")
        ),
        path("tjioi/", include("autograder.apps.tjioi.urls", namespace="tjioi")),
        path("", include("social_django.urls", namespace="social")),
    ]
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
