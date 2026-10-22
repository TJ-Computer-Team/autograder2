from django.urls import path

from . import ladder_views, views

app_name = "duels"

urlpatterns = [
    path("", views.duel_list, name="list"),
    path("challenge/", views.create_challenge, name="challenge"),
    path("<int:duel_id>/", views.duel_detail, name="detail"),
    path("<int:duel_id>/state/", views.duel_state, name="state"),
    path("<int:duel_id>/accept/", views.accept_duel, name="accept"),
    path("<int:duel_id>/decline/", views.decline_duel, name="decline"),
    path("<int:duel_id>/forfeit/", views.forfeit_duel, name="forfeit"),
    path("royale/", ladder_views.ladder_list, name="ladders"),
    path("royale/create/", ladder_views.create_ladder, name="ladder_create"),
    path("royale/<int:ladder_id>/", ladder_views.ladder_detail, name="ladder"),
    path(
        "ladders/<int:ladder_id>/state/", ladder_views.ladder_state, name="ladder_state"
    ),
    path("royale/<int:ladder_id>/join/", ladder_views.join, name="ladder_join"),
    path("royale/<int:ladder_id>/start/", ladder_views.start, name="ladder_start"),
    path("royale/<int:ladder_id>/cancel/", ladder_views.cancel, name="ladder_cancel"),
    path("royale/<int:ladder_id>/skip/", ladder_views.skip, name="ladder_skip"),
]
