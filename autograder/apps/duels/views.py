import logging

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..index.models import GraderUser
from ..oauth.decorators import login_required
from .models import Duel
from .refresh import expire_stale_challenges, refresh_duel
from .tasks import start_duel

logger = logging.getLogger(__name__)

RATING_FLOOR, RATING_CEIL = 800, 3500


def _name(user):
    """Display name, or username when it is blank."""
    return user.display_name or user.username


def _can_duel(user):
    """A verified handle is required, else you could duel as someone else."""
    return bool(user.cf_handle) and user.cf_verified_at is not None


@login_required
def duel_list(request):
    expire_stale_challenges()

    mine = Duel.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user)
    ).select_related("challenger", "opponent", "winner")

    context = {
        "active": "duels",
        "can_duel": _can_duel(request.user),
        "incoming": mine.filter(status=Duel.PENDING, opponent=request.user),
        "outgoing": mine.filter(status=Duel.PENDING, challenger=request.user),
        "ongoing": mine.filter(status=Duel.ACTIVE),
        "finished": mine.filter(status=Duel.FINISHED)[:20],
        "opponents": GraderUser.objects.filter(
            cf_verified_at__isnull=False, is_active=True
        )
        .exclude(pk=request.user.pk)
        .order_by("display_name"),
        "rating_floor": RATING_FLOOR,
        "rating_ceil": RATING_CEIL,
    }
    return render(request, "duels/list.html", context)


@login_required
@require_POST
def create_challenge(request):
    if not _can_duel(request.user):
        messages.error(
            request, "Verify your Codeforces handle on your profile before duelling."
        )
        return redirect("duels:list")

    opponent = get_object_or_404(GraderUser, pk=request.POST.get("opponent"))
    if opponent.pk == request.user.pk:
        messages.error(request, "You cannot duel yourself.")
        return redirect("duels:list")
    if not _can_duel(opponent):
        messages.error(
            request, f"{opponent.display_name} has not verified a Codeforces handle."
        )
        return redirect("duels:list")

    try:
        rating_min = int(request.POST.get("rating_min", 800))
        rating_max = int(request.POST.get("rating_max", 1200))
    except (TypeError, ValueError):
        messages.error(request, "Rating range must be numbers.")
        return redirect("duels:list")

    rating_min = max(RATING_FLOOR, min(RATING_CEIL, rating_min))
    rating_max = max(RATING_FLOOR, min(RATING_CEIL, rating_max))
    if rating_min > rating_max:
        rating_min, rating_max = rating_max, rating_min

    duel = Duel.objects.create(
        challenger=request.user,
        opponent=opponent,
        rating_min=rating_min,
        rating_max=rating_max,
        tags=request.POST.get("tags", "").strip()[:200],
    )
    messages.success(request, f"Challenge sent to {opponent.display_name}.")
    return redirect("duels:detail", duel_id=duel.id)


@login_required
def duel_detail(request, duel_id):
    duel = get_object_or_404(
        Duel.objects.select_related("challenger", "opponent", "winner"), pk=duel_id
    )

    # A pending challenge is private to the two people involved; once it starts,
    # anyone logged in may watch, which is what the Blitz Cup will need.
    if duel.status == Duel.PENDING and not duel.includes(request.user):
        raise Http404

    refresh_duel(duel)

    context = {
        "active": "duels",
        "duel": duel,
        "is_player": duel.includes(request.user),
        "rows": _submission_rows(duel),
    }
    return render(request, "duels/detail.html", context)


def _submission_rows(duel):
    """Both players' submissions, newest first, for the live board."""
    subs = duel.submissions.select_related("user").order_by("-created_at")
    return [
        {
            "user": s.user,
            "verdict": s.verdict or "Running",
            "accepted": s.is_accepted,
            "created_at": s.created_at,
        }
        for s in subs
    ]


@login_required
def duel_state(request, duel_id):
    """JSON for the live board. Polled by the detail page every couple of seconds.

    The Codeforces refresh inside is throttled per duel, so extra viewers cost
    nothing beyond a database read.
    """
    duel = get_object_or_404(
        Duel.objects.select_related("challenger", "opponent", "winner"), pk=duel_id
    )
    if duel.status == Duel.PENDING and not duel.includes(request.user):
        raise Http404

    refresh_duel(duel)
    duel.refresh_from_db()

    return JsonResponse(
        {
            "status": duel.status,
            "problem": {
                "name": duel.cf_name,
                "url": duel.problem_url,
                "rating": duel.cf_rating,
            },
            "started_at": duel.started_at.isoformat() if duel.started_at else None,
            "deadline": duel.deadline.isoformat() if duel.deadline else None,
            # Fall back to username: an account with a blank display_name would
            # send "", which is falsy in JS and made the page report a draw.
            "winner": _name(duel.winner) if duel.winner else None,
            "end_reason": duel.end_reason,
            "selection_error": duel.selection_error,
            "players": [
                {"name": _name(p), "handle": p.cf_handle} for p in duel.players
            ],
            "submissions": [
                {
                    "name": _name(r["user"]),
                    "verdict": r["verdict"],
                    "accepted": r["accepted"],
                    "at": r["created_at"].isoformat(),
                }
                for r in _submission_rows(duel)
            ],
        }
    )


@login_required
@require_POST
def accept_duel(request, duel_id):
    duel = get_object_or_404(Duel, pk=duel_id)
    if duel.opponent_id != request.user.pk:
        messages.error(request, "Only the challenged player can accept.")
        return redirect("duels:detail", duel_id=duel.id)
    if duel.status != Duel.PENDING:
        messages.error(request, "That challenge is no longer open.")
        return redirect("duels:detail", duel_id=duel.id)

    duel.accepted_at = duel.accepted_at or timezone.now()
    duel.selection_error = ""
    duel.save(update_fields=["accepted_at", "selection_error"])

    # Picking a problem needs both players' full CF history (~2s each), so it
    # happens off-request; the page polls until the duel flips to active.
    start_duel.delay(duel.id)
    return redirect("duels:detail", duel_id=duel.id)


@login_required
@require_POST
def decline_duel(request, duel_id):
    duel = get_object_or_404(Duel, pk=duel_id)
    if not duel.includes(request.user):
        raise Http404
    if duel.status != Duel.PENDING:
        messages.error(request, "That challenge is no longer open.")
        return redirect("duels:list")

    duel.status = Duel.DECLINED
    duel.save(update_fields=["status"])
    return redirect("duels:list")


@login_required
@require_POST
def forfeit_duel(request, duel_id):
    duel = get_object_or_404(Duel, pk=duel_id)
    if not duel.includes(request.user):
        messages.error(request, "You are not in this duel.")
        return redirect("duels:detail", duel_id=duel.id)
    if duel.status != Duel.ACTIVE:
        messages.error(request, "That duel is not running.")
        return redirect("duels:detail", duel_id=duel.id)

    duel.finish(duel.other_player(request.user), Duel.FORFEIT)
    messages.info(request, "You forfeited the duel.")
    return redirect("duels:detail", duel_id=duel.id)
