from datetime import timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..oauth.decorators import login_required
from .ladder import JoinError, close_if_overdue, join_ladder, refresh_entry, skip_rung
from .models import Ladder
from .tasks import start_ladder
from .views import RATING_CEIL, RATING_FLOOR, _can_duel, _name

# Clamps for the create form.
MAX_RUNGS = 20
MAX_SKIPS = 5
DURATION_RANGE = (5, 240)


def _int(request, field, default, low, high):
    try:
        value = int(request.POST.get(field, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


@login_required
def ladder_list(request):
    # Pending ladders nobody started within a day are just clutter.
    recent = timezone.now() - timedelta(days=1)
    ladders = Ladder.objects.select_related("host")
    context = {
        "active": "duels",
        "can_duel": _can_duel(request.user),
        "open_ladders": ladders.filter(status=Ladder.ACTIVE)
        | ladders.filter(status=Ladder.PENDING, created_at__gte=recent),
        "finished": ladders.filter(status=Ladder.FINISHED)[:15],
        "rating_floor": RATING_FLOOR,
        "rating_ceil": RATING_CEIL,
        "max_rungs": MAX_RUNGS,
    }
    return render(request, "duels/ladders.html", context)


@login_required
@require_POST
def create_ladder(request):
    if not _can_duel(request.user):
        messages.error(
            request, "Verify your Codeforces handle on your profile before playing."
        )
        return redirect("duels:ladders")

    rating_min = _int(request, "rating_min", 800, RATING_FLOOR, RATING_CEIL)
    rating_max = _int(request, "rating_max", 1600, RATING_FLOOR, RATING_CEIL)
    if rating_min > rating_max:
        rating_min, rating_max = rating_max, rating_min

    ladder = Ladder.objects.create(
        host=request.user,
        rating_min=rating_min,
        rating_max=rating_max,
        rung_count=_int(request, "rung_count", 8, 1, MAX_RUNGS),
        duration_minutes=_int(request, "duration_minutes", 60, *DURATION_RANGE),
        skips=_int(request, "skips", 1, 0, MAX_SKIPS),
        tags=request.POST.get("tags", "").strip()[:200],
    )
    join_ladder(ladder, request.user)
    return redirect("duels:ladder", ladder_id=ladder.id)


def _chart(ladder, entry):
    """Everyone's solve times, for the solves-over-time graph."""
    return {
        "started_at": ladder.started_at.isoformat() if ladder.started_at else None,
        "deadline": ladder.deadline.isoformat() if ladder.deadline else None,
        "ended_at": ladder.ended_at.isoformat() if ladder.ended_at else None,
        "max": ladder.rung_count,
        "players": [
            {
                "name": _name(e.user),
                "solves": e.solve_times,
                "me": entry is not None and e.pk == entry.pk,
            }
            for e in ladder.standings()
        ],
    }


def _my_entry(ladder, user):
    return ladder.entries.select_related("user", "ladder").filter(user=user).first()


@login_required
def ladder_detail(request, ladder_id):
    ladder = get_object_or_404(Ladder.objects.select_related("host"), pk=ladder_id)
    close_if_overdue(ladder)
    entry = _my_entry(ladder, request.user)
    if entry:
        refresh_entry(entry)
        ladder.refresh_from_db()

    rung = None
    if entry and ladder.status == Ladder.ACTIVE and not entry.is_done:
        rung = ladder.rungs.filter(position=entry.position).first()

    context = {
        "active": "duels",
        "ladder": ladder,
        "entry": entry,
        "rung": rung,
        "is_host": ladder.host_id == request.user.pk,
        "can_duel": _can_duel(request.user),
        "standings": ladder.standings(),
        "chart": _chart(ladder, entry),
        # The whole sequence stays hidden until the end, or a spectator could read
        # ahead, solve offline, then join and paste.
        "all_rungs": ladder.rungs.all() if ladder.status == Ladder.FINISHED else None,
    }
    return render(request, "duels/ladder.html", context)


@login_required
def ladder_state(request, ladder_id):
    """JSON for the live standings, polled by the ladder page.

    Only the viewer's own entry is checked against Codeforces.
    """
    ladder = get_object_or_404(Ladder, pk=ladder_id)
    close_if_overdue(ladder)
    entry = _my_entry(ladder, request.user)
    if entry:
        refresh_entry(entry)
    ladder.refresh_from_db()

    return JsonResponse(
        {
            "status": ladder.status,
            "starting": ladder.start_requested_at is not None,
            "selection_error": ladder.selection_error,
            "deadline": ladder.deadline.isoformat() if ladder.deadline else None,
            "my_position": entry.position if entry else None,
            "chart": _chart(ladder, entry),
            "standings": [
                {
                    "name": _name(e.user),
                    "solved": e.solved,
                    "rung": min(e.position, ladder.rung_count),
                    "done": e.position > ladder.rung_count,
                    "skips_used": e.skips_used,
                    "me": entry is not None and e.pk == entry.pk,
                }
                for e in ladder.standings()
            ],
        }
    )


@login_required
@require_POST
def join(request, ladder_id):
    ladder = get_object_or_404(Ladder, pk=ladder_id)
    if not _can_duel(request.user):
        messages.error(
            request, "Verify your Codeforces handle on your profile before playing."
        )
        return redirect("duels:ladder", ladder_id=ladder.id)
    try:
        join_ladder(ladder, request.user)
    except JoinError as e:
        messages.error(request, str(e))
    return redirect("duels:ladder", ladder_id=ladder.id)


@login_required
@require_POST
def start(request, ladder_id):
    ladder = get_object_or_404(Ladder, pk=ladder_id)
    if ladder.host_id != request.user.pk:
        messages.error(request, "Only the host can start it.")
        return redirect("duels:ladder", ladder_id=ladder.id)
    # Conditional update so a double click enqueues one draw, not two.
    claimed = Ladder.objects.filter(
        pk=ladder.pk, status=Ladder.PENDING, start_requested_at__isnull=True
    ).update(start_requested_at=timezone.now(), selection_error="")
    if claimed:
        start_ladder.delay(ladder.id)
    return redirect("duels:ladder", ladder_id=ladder.id)


@login_required
@require_POST
def cancel(request, ladder_id):
    ladder = get_object_or_404(Ladder, pk=ladder_id)
    if ladder.host_id != request.user.pk:
        messages.error(request, "Only the host can cancel it.")
        return redirect("duels:ladder", ladder_id=ladder.id)
    Ladder.objects.filter(
        pk=ladder.pk, status=Ladder.PENDING, start_requested_at__isnull=True
    ).update(status=Ladder.CANCELLED, ended_at=timezone.now())
    return redirect("duels:ladders")


@login_required
@require_POST
def skip(request, ladder_id):
    ladder = get_object_or_404(Ladder, pk=ladder_id)
    entry = _my_entry(ladder, request.user)
    if entry is None or ladder.status != Ladder.ACTIVE or ladder.is_overdue:
        messages.error(request, "You can't skip right now.")
        return redirect("duels:ladder", ladder_id=ladder.id)

    # Check CF first: skipping a rung you already solved would throw the point away.
    position = entry.position
    refresh_entry(entry, force=True)
    if entry.position != position:
        messages.info(request, "You had already solved that one, so no skip used.")
    elif not skip_rung(entry):
        messages.error(request, "No skips left.")
    return redirect("duels:ladder", ladder_id=ladder.id)
