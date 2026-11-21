from django.urls import path

from . import views

app_name = "lectures"

urlpatterns = [
    path("", views.problemset_list, name="list"),
    path("<slug:slug>/", views.problemset_detail, name="detail"),
]
