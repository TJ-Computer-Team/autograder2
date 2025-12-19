from django.urls import path

from . import views

app_name = "index"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("first_time/", views.first_time_view, name="first_time"),
    path("update_first_time/", views.update_first_time, name="update_first_time"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/<int:id>/", views.user_profile_view, name="user_profile"),
    path("update_stats/", views.update_stats, name="update_stats"),
    path("info/", views.info_view, name="info"),
    path("potw/", views.potw_view, name="potw"),
    path("mobile/", views.mobile_home, name="mobile"),
    path("toggle_particles/", views.toggle_particles, name="toggle_particles"),
]
