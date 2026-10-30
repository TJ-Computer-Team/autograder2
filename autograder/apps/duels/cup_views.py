from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..index.models import GraderUser
from ..oauth.decorators import admin_required, login_required
from .cup import CupError, draw_bracket, set_winner, start_next_round
from .models import Cup, CupEntry, CupMatch, Duel
from .refresh import refresh_duel
from .tasks import start_cup_match
from .views import RATING_CEIL, RATING_FLOOR, _can_duel, _name


def _int(request, field, default, low, high):
    try:
        value = int(request.POST.get(field, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


@login_required
def cup_list(request):
    cups = Cup.objects.annotate(players=Count("entries"))
    context = {
        "active": "duels",
        "can_duel": _can_duel(request.user),
        "open_cups": cups.filter(status__in=(Cup.REGISTRATION, Cup.RUNNING)),
        "finished": cups.filter(status=Cup.FINISHED).select_related("champion")[:10],
        "rating_floor": RATING_FLOOR,
        "rating_ceil": RATING_CEIL,
    }
    return render(request, "duels/cups.html", context)


@admin_required
@require_POST
def create_cup(request):
    rating_min = _int(request, "rating_min", 800, RATING_FLOOR, RATING_CEIL)
    rating_max = _int(request, "rating_max", 1100, RATING_FLOOR, RATING_CEIL)
    if rating_min > rating_max:
        rating_min, rating_max = rating_max, rating_min
    cup = Cup.objects.create(
        name=request.POST.get("name", "").strip()[:100] or "Blitz Cup",
        created_by=request.user,
        rating_min=rating_min,
        rating_max=rating_max,
        rating_step=_int(request, "rating_step", 200, 0, 500),
        duel_minutes=_int(request, "duel_minutes", 15, 3, 60),
        sudden_death_minutes=_int(request, "sudden_death_minutes", 10, 3, 60),
    )
    return redirect("duels:cup", cup_id=cup.id)


def _wrong_answers(duel_ids):
    """{(duel_id, user_id): count} of judged, non-accepted submissions."""
    rows = (
        Duel.objects.filter(pk__in=duel_ids)
        .values("pk", "submissions__user")
        .annotate(
            n=Count(
                "submissions",
                filter=~Q(submissions__verdict__in=("OK", "")),
            )
        )
    )
    return {(r["pk"], r["submissions__user"]): r["n"] for r in rows}


def _side(match, player, duel, seeds, wrong):
    if player is None:
        return None
    return {
        "id": player.pk,
        "name": _name(player),
        "seed": seeds.get(player.pk),
        "won": match.winner_id == player.pk,
        "lost": match.winner_id is not None and match.winner_id != player.pk,
        "wa": wrong.get((duel.pk, player.pk), 0) if duel else 0,
    }


def _bracket(cup):
    """Rounds of match dicts for the template and the live JSON."""
    seeds = dict(cup.entries.values_list("user_id", "seed"))
    matches = list(
        cup.matches.select_related("player_a", "player_b", "winner").order_by(
            "round", "slot"
        )
    )
    latest = {}
    for duel in Duel.objects.filter(bracket_match__cup=cup).order_by("created_at"):
        latest[duel.bracket_match_id] = duel  # last one wins: the rematch if any
    was_replayed = set(
        CupMatch.objects.filter(cup=cup)
        .annotate(n=Count("duels"))
        .filter(n__gt=1)
        .values_list("pk", flat=True)
    )
    wrong = _wrong_answers(
        [d.pk for d in latest.values() if d.status in (Duel.ACTIVE, Duel.FINISHED)]
    )

    rounds = []
    for number in range(1, cup.round_count + 1):
        rounds.append({"number": number, "name": cup.round_name(number), "matches": []})
    for m in matches:
        duel = latest.get(m.pk)
        if m.is_bye:
            state = "bye"
        elif m.winner_id:
            state = "done"
        elif duel and duel.status == Duel.ACTIVE:
            state = "live"
        elif duel and duel.status == Duel.PENDING:
            state = "stuck" if duel.selection_error else "drawing"
        elif len(m.players) == 2:
            state = "ready"
        else:
            state = "waiting"

        rounds[m.round - 1]["matches"].append(
            {
                "id": m.pk,
                "state": state,
                "a": _side(m, m.player_a, duel, seeds, wrong),
                "b": _side(m, m.player_b, duel, seeds, wrong),
                "decided_by": m.decided_by,
                "sudden_death": m.pk in was_replayed,
                "duel_id": duel.pk if duel else None,
                "deadline": duel.deadline.isoformat()
                if duel and duel.deadline and state == "live"
                else None,
                "error": duel.selection_error if duel else "",
                "problem": duel.cf_name if duel and state == "done" else "",
            }
        )
    # Pairs feeding the same next-round match, so the page can draw the joins.
    for r in rounds:
        r["pairs"] = [r["matches"][i : i + 2] for i in range(0, len(r["matches"]), 2)]
    return rounds


def _version(cup, rounds):
    """Changes whenever the bracket's shape or any match's state does."""
    parts = [cup.status, str(cup.current_round), cup.error]
    for r in rounds:
        for m in r["matches"]:
            parts.append(
                f"{m['id']}:{m['state']}:{m['duel_id']}:"
                f"{m['a'] and m['a']['id']}:{m['b'] and m['b']['id']}"
            )
    return "|".join(parts)


def _refresh_live_duels(cup):
    """Drive the current round's duels from the bracket page.

    Players' own duel pages do this too, but the projector is the one page that
    is always open, so timeouts and late solves still settle if everyone closed
    their tab. Throttled per duel and by the site-wide CF budget.
    """
    for duel in Duel.objects.filter(
        bracket_match__cup=cup, status=Duel.ACTIVE
    ).select_related("challenger", "opponent"):
        refresh_duel(duel)


@login_required
def cup_detail(request, cup_id):
    cup = get_object_or_404(Cup.objects.select_related("champion"), pk=cup_id)
    if cup.status == Cup.RUNNING:
        _refresh_live_duels(cup)
        cup.refresh_from_db()
    rounds = _bracket(cup)

    my_live_duel = (
        Duel.objects.filter(bracket_match__cup=cup, status=Duel.ACTIVE)
        .filter(Q(challenger=request.user) | Q(opponent=request.user))
        .first()
    )
    entrants = cup.entries.select_related("user").order_by("seed", "joined_at")
    context = {
        "active": "duels",
        "cup": cup,
        "rounds": rounds,
        "version": _version(cup, rounds),
        "is_staff": request.user.is_staff,
        "projector": request.GET.get("projector") == "1",
        "can_duel": _can_duel(request.user),
        "registered": cup.entries.filter(user=request.user).exists(),
        "entrants": entrants,
        "my_live_duel": my_live_duel,
        "current_round_name": cup.round_name(cup.current_round)
        if cup.current_round
        else "",
        "next_round_name": cup.round_name(cup.current_round + 1)
        if cup.current_round < cup.round_count
        else "",
        "round_done": cup.current_round == 0
        or not cup.matches.filter(
            round=cup.current_round, winner__isnull=True
        ).exists(),
    }
    return render(request, "duels/cup.html", context)


@login_required
def cup_state(request, cup_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    if cup.status == Cup.RUNNING:
        _refresh_live_duels(cup)
        cup.refresh_from_db()
    rounds = _bracket(cup)
    return JsonResponse(
        {
            "version": _version(cup, rounds),
            "entrants": cup.entries.count(),
            "matches": {
                m["id"]: {
                    "deadline": m["deadline"],
                    "a_wa": m["a"]["wa"] if m["a"] else 0,
                    "b_wa": m["b"]["wa"] if m["b"] else 0,
                }
                for r in rounds
                for m in r["matches"]
            },
        }
    )


@login_required
@require_POST
def register(request, cup_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    if not _can_duel(request.user):
        messages.error(
            request, "Verify your Codeforces handle on your profile before entering."
        )
    elif cup.status != Cup.REGISTRATION:
        messages.error(request, "Registration is closed.")
    else:
        CupEntry.objects.get_or_create(cup=cup, user=request.user)
    return redirect("duels:cup", cup_id=cup.id)


@login_required
@require_POST
def unregister(request, cup_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    if cup.status == Cup.REGISTRATION:
        cup.entries.filter(user=request.user).delete()
    return redirect("duels:cup", cup_id=cup.id)


def _staff_action(request, cup, action):
    try:
        action()
    except CupError as e:
        messages.error(request, str(e))
    return redirect("duels:cup", cup_id=cup.id)


@admin_required
@require_POST
def draw(request, cup_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    return _staff_action(request, cup, lambda: draw_bracket(cup))


@admin_required
@require_POST
def start_round(request, cup_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    return _staff_action(request, cup, lambda: start_next_round(cup))


@admin_required
@require_POST
def retry_match(request, cup_id, match_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    match = get_object_or_404(CupMatch, pk=match_id, cup=cup)
    Cup.objects.filter(pk=cup.pk).update(error="")
    start_cup_match.delay(match.pk)
    return redirect("duels:cup", cup_id=cup.id)


@admin_required
@require_POST
def override(request, cup_id, match_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    match = get_object_or_404(CupMatch, pk=match_id, cup=cup)
    winner = get_object_or_404(GraderUser, pk=request.POST.get("winner"))
    return _staff_action(request, cup, lambda: set_winner(match, winner))


@admin_required
@require_POST
def cancel_cup(request, cup_id):
    cup = get_object_or_404(Cup, pk=cup_id)
    Cup.objects.filter(pk=cup.pk).exclude(status=Cup.FINISHED).update(
        status=Cup.CANCELLED, ended_at=timezone.now()
    )
    Duel.objects.filter(
        bracket_match__cup=cup, status__in=(Duel.PENDING, Duel.ACTIVE)
    ).update(status=Duel.FINISHED, end_reason=Duel.VOIDED, ended_at=timezone.now())
    return redirect("duels:cups")
