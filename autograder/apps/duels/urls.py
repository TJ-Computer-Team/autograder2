from django.urls import path

from . import cup_views, ladder_views, views

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
    path("cup/", cup_views.cup_list, name="cups"),
    path("cup/create/", cup_views.create_cup, name="cup_create"),
    path("cup/<int:cup_id>/", cup_views.cup_detail, name="cup"),
    path("cup/<int:cup_id>/state/", cup_views.cup_state, name="cup_state"),
    path("cup/<int:cup_id>/register/", cup_views.register, name="cup_register"),
    path("cup/<int:cup_id>/unregister/", cup_views.unregister, name="cup_unregister"),
    path("cup/<int:cup_id>/draw/", cup_views.draw, name="cup_draw"),
    path(
        "cup/<int:cup_id>/start-round/", cup_views.start_round, name="cup_start_round"
    ),
    path("cup/<int:cup_id>/cancel/", cup_views.cancel_cup, name="cup_cancel"),
    path(
        "cup/<int:cup_id>/match/<int:match_id>/retry/",
        cup_views.retry_match,
        name="cup_retry",
    ),
    path(
        "cup/<int:cup_id>/match/<int:match_id>/winner/",
        cup_views.override,
        name="cup_override",
    ),
]
