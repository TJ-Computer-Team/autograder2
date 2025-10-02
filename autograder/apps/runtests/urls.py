from django.urls import path

from . import views

app_name = "runtests"

urlpatterns = [
    path("submit/", views.submit_view, name="submit"),
    path("submit/contest/<int:cid>/", views.submit_view, name="submitcontest"),
    path("submit/problem/<int:pid>/", views.submit_view, name="submitproblem"),
    path(
        "<int:page>/",
        views.status_view,
        {"mine": False, "cid": None},
        name="status",
    ),
    path(
        "<int:cid>/<int:page>/",
        views.status_view,
        {"mine": False},
        name="status",
    ),
    path(
        "mine/<int:page>/",
        views.status_view,
        {"mine": True, "cid": None},
        name="status",
    ),
    path(
        "mine/<int:cid>/<int:page>/",
        views.status_view,
        {"mine": True},
        name="status",
    ),
    path("submission/<int:id>/", views.submission_view, name="submission"),
    path("process_submit/", views.submit_post, name="submit_post"),
]
