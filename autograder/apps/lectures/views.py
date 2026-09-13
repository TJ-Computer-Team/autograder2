import logging

from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from ..oauth.decorators import login_required
from .models import LectureSet
from .utils import solved_problem_ids, visible_entries

logger = logging.getLogger(__name__)


@login_required
def problemset_list(request):
    sets = LectureSet.objects.annotate(entry_count=Count("entries"))
    if not request.user.is_staff:
        sets = sets.filter(published=True)

    groups = [
        {"label": label, "sets": [s for s in sets if s.kind == kind]}
        for kind, label in LectureSet.KIND_CHOICES
    ]

    context = {
        "active": "lectures",
        "groups": groups,
        "any_sets": any(group["sets"] for group in groups),
    }
    return render(request, "lectures/list.html", context)


@login_required
def problemset_detail(request, slug):
    lecture_set = get_object_or_404(LectureSet, slug=slug)

    if not lecture_set.published and not request.user.is_staff:
        logger.info(
            f"User {request.user} tried to open unpublished lecture set {lecture_set.slug}"
        )
        raise Http404

    entries = list(lecture_set.entries.select_related("problem", "problem__contest"))
    entries = visible_entries(entries, request.user)

    solved = solved_problem_ids(
        request.user, [e.problem_id for e in entries if e.problem_id is not None]
    )

    # Labels follow position in the visible list, so a hidden entry doesn't leak
    # its existence as a gap in the lettering.
    rows = [
        {
            "entry": entry,
            "label": lecture_set.label_for(index),
            "solved": entry.problem_id in solved,
        }
        for index, entry in enumerate(entries)
    ]

    context = {
        "active": "lectures",
        "lecture_set": lecture_set,
        "rows": rows,
    }
    return render(request, "lectures/detail.html", context)
