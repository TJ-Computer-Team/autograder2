from django.shortcuts import render, redirect
from django.conf import settings
from django.db.models import Q
from ..oauth.decorators import login_required
from ..index.models import GraderUser

import logging

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
def rankings_view(request, season):
    if season != settings.CURRENT_SEASON:
        return redirect("rankings:rankings", season=settings.CURRENT_SEASON)

    graduation_years = range(settings.CURRENT_SEASON, settings.CURRENT_SEASON + 4)
    graduation_year_filter = Q()
    for year in graduation_years:
        graduation_year_filter |= Q(username__startswith=str(year))

    rankings = [
        {
            "id": user.id,
            "name": user.display_name,
            "index": user.index,
            "usaco": user.usaco_rating,
            "cf": user.cf_rating,
            "inhouse": user.inhouse,
        }
        for user in GraderUser.objects.filter(
            graduation_year_filter, is_tjioi=False, is_staff=False
        )
    ]

    rankings = [
        r for r in rankings if r["usaco"] > 800 or r["cf"] > 0 or r["inhouse"] > 0
    ]

    rankings.sort(key=lambda x: x["index"], reverse=True)
    for i in range(len(rankings)):
        rankings[i]["rank"] = i + 1

    context = {"rankings": rankings}

    return render(request, "rankings/rankings.html", context)
