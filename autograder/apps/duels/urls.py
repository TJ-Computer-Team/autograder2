from django.urls import path

from . import views

app_name = "duels"

urlpatterns = [
    path("", views.duel_list, name="list"),
    path("challenge/", views.create_challenge, name="challenge"),
    path("<int:duel_id>/", views.duel_detail, name="detail"),
    path("<int:duel_id>/state/", views.duel_state, name="state"),
    path("<int:duel_id>/accept/", views.accept_duel, name="accept"),
    path("<int:duel_id>/decline/", views.decline_duel, name="decline"),
    path("<int:duel_id>/forfeit/", views.forfeit_duel, name="forfeit"),
]
