from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..index.cf_utils import take_cf_slot
from .cup import (
    CupError,
    create_match_duel,
    draw_bracket,
    seed_order,
    set_winner,
    start_next_round,
)
from .models import Cup, CupEntry, CupMatch, Duel, DuelSubmission
from .refresh import expire_stale_challenges, refresh_duel
from .tests import make_user


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(CF_RATE_LIMIT=True)
    def test_one_call_per_second_site_wide(self):
        with patch("autograder.apps.index.cf_utils.time.time", return_value=1000.5):
            self.assertTrue(take_cf_slot())
            self.assertFalse(take_cf_slot())
        with patch("autograder.apps.index.cf_utils.time.time", return_value=1001.1):
            self.assertTrue(take_cf_slot())

    def test_off_in_tests(self):
        self.assertTrue(take_cf_slot())
        self.assertTrue(take_cf_slot())


class SeedingTests(TestCase):
    def test_top_seeds_only_meet_late(self):
        self.assertEqual(seed_order(2), [1, 2])
        self.assertEqual(seed_order(4), [1, 4, 2, 3])
        self.assertEqual(seed_order(8), [1, 8, 4, 5, 2, 7, 3, 6])


class CupBase(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = make_user("staff", "staff_cf")
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])

    def make_cup(self, ratings):
        """One player per rating; higher rating means better seed."""
        cup = Cup.objects.create(created_by=self.staff)
        self.players = []
        for i, rating in enumerate(ratings):
            user = make_user(f"p{i}", f"p{i}_cf")
            user.cf_rating = rating
            user.save(update_fields=["cf_rating"])
            CupEntry.objects.create(cup=cup, user=user)
            self.players.append(user)
        return cup

    def match(self, cup, round_number, slot):
        return CupMatch.objects.get(cup=cup, round=round_number, slot=slot)

    def live_duel(self, match):
        duel = create_match_duel(match, 15)
        duel.status = Duel.ACTIVE
        duel.started_at = timezone.now() - timedelta(minutes=1)
        duel.cf_contest_id, duel.cf_index = 1001, "A"
        duel.save()
        return duel


class DrawTests(CupBase):
    def test_byes_go_to_top_seeds_and_advance(self):
        cup = self.make_cup([1500, 1400, 1300, 1200, 1100])  # p0 is seed 1
        cup = draw_bracket(cup)
        self.assertEqual((cup.status, cup.round_count), (Cup.RUNNING, 3))
        byes = cup.matches.filter(round=1, is_bye=True)
        self.assertEqual(sorted(m.player_a.username for m in byes), ["p0", "p1", "p2"])
        self.assertTrue(all(m.winner_id == m.player_a_id for m in byes))
        # Seed 1's bye lands them in the top half of round 2.
        self.assertEqual(self.match(cup, 2, 0).player_a.username, "p0")
        # The only real round-1 match is seed 4 v seed 5.
        real = cup.matches.get(round=1, is_bye=False, player_b__isnull=False)
        self.assertEqual({real.player_a.username, real.player_b.username}, {"p3", "p4"})

    def test_two_players_is_just_a_final(self):
        cup = draw_bracket(self.make_cup([1200, 1000]))
        self.assertEqual(cup.round_count, 1)
        self.assertEqual(cup.round_name(1), "Final")

    def test_needs_two_players(self):
        with self.assertRaises(CupError):
            draw_bracket(self.make_cup([1200]))

    def test_cannot_draw_twice(self):
        cup = draw_bracket(self.make_cup([1200, 1000]))
        with self.assertRaises(CupError):
            draw_bracket(cup)


class AdvanceTests(CupBase):
    def setUp(self):
        super().setUp()
        self.cup = draw_bracket(self.make_cup([1600, 1500, 1400, 1300]))
        Cup.objects.filter(pk=self.cup.pk).update(current_round=1)
        self.cup.refresh_from_db()

    def test_duel_winner_moves_on(self):
        m = self.match(self.cup, 1, 0)  # seed 1 v seed 4
        self.live_duel(m).finish(m.player_b, Duel.SOLVED)
        m.refresh_from_db()
        self.assertEqual(m.winner_id, m.player_b_id)
        self.assertEqual(self.match(self.cup, 2, 0).player_a_id, m.player_b_id)

    def test_bottom_match_fills_the_other_side(self):
        m = self.match(self.cup, 1, 1)
        self.live_duel(m).finish(m.player_a, Duel.FORFEIT)
        self.assertEqual(self.match(self.cup, 2, 0).player_b_id, m.player_a_id)

    def test_final_crowns_a_champion(self):
        final = self.match(self.cup, 2, 0)
        final.player_a, final.player_b = self.players[0], self.players[1]
        final.save()
        Cup.objects.filter(pk=self.cup.pk).update(current_round=2)
        self.live_duel(final).finish(self.players[1], Duel.SOLVED)
        self.cup.refresh_from_db()
        self.assertEqual(self.cup.status, Cup.FINISHED)
        self.assertEqual(self.cup.champion_id, self.players[1].pk)

    @patch("autograder.apps.duels.tasks.start_duel")
    def test_draw_means_sudden_death_then_seed(self, start):
        m = self.match(self.cup, 1, 0)
        with self.captureOnCommitCallbacks(execute=True):
            self.live_duel(m).finish(None, Duel.TIMEOUT)
        m.refresh_from_db()
        self.assertIsNone(m.winner_id)
        self.assertEqual(m.duels.count(), 2)
        rematch = m.duels.order_by("-created_at").first()
        self.assertEqual(rematch.duration_minutes, self.cup.sudden_death_minutes)
        start.delay.assert_called_once_with(rematch.pk)

        rematch.status = Duel.ACTIVE
        rematch.save()
        rematch.finish(None, Duel.TIMEOUT)
        m.refresh_from_db()
        self.assertEqual(m.winner_id, self.players[0].pk)  # seed 1
        self.assertEqual(m.decided_by, "seed")

    def test_staff_override_stops_the_live_duel(self):
        m = self.match(self.cup, 1, 0)
        duel = self.live_duel(m)
        set_winner(m, m.player_b)
        duel.refresh_from_db()
        self.assertEqual((duel.status, duel.end_reason), (Duel.FINISHED, Duel.VOIDED))
        m.refresh_from_db()
        self.assertEqual((m.winner_id, m.decided_by), (m.player_b_id, "staff"))

    def test_override_only_in_the_current_round(self):
        with self.assertRaises(CupError):
            set_winner(self.match(self.cup, 2, 0), self.players[0])

    def test_next_round_waits_for_every_match(self):
        with self.assertRaises(CupError):
            start_next_round(self.cup)
        for slot in (0, 1):
            m = self.match(self.cup, 1, slot)
            self.live_duel(m).finish(m.player_a, Duel.SOLVED)
        with (
            patch("autograder.apps.duels.tasks.start_cup_round") as task,
            self.captureOnCommitCallbacks(execute=True),
        ):
            start_next_round(self.cup)
        task.delay.assert_called_once_with(self.cup.pk, 2)

    def test_cup_duel_is_not_declinable_or_expired(self):
        m = self.match(self.cup, 1, 0)
        duel = create_match_duel(m, 15)
        Duel.objects.filter(pk=duel.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        expire_stale_challenges()
        self.client.force_login(m.player_b)
        self.client.post(reverse("duels:decline", args=[duel.pk]))
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.PENDING)

    def test_last_second_solve_beats_the_timeout(self):
        m = self.match(self.cup, 1, 0)
        duel = self.live_duel(m)
        Duel.objects.filter(pk=duel.pk).update(
            started_at=timezone.now() - timedelta(minutes=16)
        )
        duel.refresh_from_db()
        just_in_time = duel.deadline - timedelta(seconds=3)

        def fake(handle, contest_id, index, since, count=20):
            if handle == m.player_b.cf_handle:
                return [(77, "OK", just_in_time)]
            return []

        with patch("autograder.apps.duels.refresh.fetch_recent_submissions", fake):
            refresh_duel(duel)
        duel.refresh_from_db()
        self.assertEqual(
            (duel.winner_id, duel.end_reason), (m.player_b_id, Duel.SOLVED)
        )
        self.assertTrue(DuelSubmission.objects.filter(duel=duel).exists())


class StartMatchTaskTests(CupBase):
    def setUp(self):
        super().setUp()
        self.cup = draw_bracket(self.make_cup([1600, 1500]))
        self.final = self.match(self.cup, 1, 0)

    @patch("autograder.apps.duels.tasks.start_duel")
    @patch("autograder.apps.duels.tasks.fetch_solved_set", return_value=set())
    def test_starts_a_pre_accepted_duel(self, solved, start):
        from .tasks import start_cup_match

        start_cup_match(self.final.pk)
        duel = self.final.duels.get()
        self.assertIsNotNone(duel.accepted_at)
        self.assertEqual((duel.rating_min, duel.rating_max), (800, 1100))
        start.assert_called_once_with(duel.pk)
        # Forced: last round's problem must not hide behind a stale cache.
        self.assertTrue(all(c.kwargs["force"] for c in solved.call_args_list))

    @patch("autograder.apps.duels.tasks.start_duel")
    @patch("autograder.apps.duels.tasks.fetch_solved_set", return_value=None)
    def test_history_failure_holds_the_match(self, solved, start):
        from .tasks import start_cup_match

        start_cup_match(self.final.pk)
        self.assertFalse(self.final.duels.exists())
        start.assert_not_called()
        self.cup.refresh_from_db()
        self.assertIn("Retry", self.cup.error)

    def test_later_rounds_get_harder(self):
        self.cup.rating_step = 200
        self.assertEqual(self.cup.rating_range(3), (1200, 1500))


class CupViewTests(CupBase):
    def test_only_staff_create(self):
        player = make_user("player", "player_cf")
        self.client.force_login(player)
        self.client.post(reverse("duels:cup_create"), {"name": "Nope"})
        self.assertFalse(Cup.objects.exists())
        self.client.force_login(self.staff)
        self.client.post(reverse("duels:cup_create"), {"name": "Fall Cup"})
        self.assertEqual(Cup.objects.get().name, "Fall Cup")

    def test_register_needs_a_verified_handle(self):
        cup = Cup.objects.create(created_by=self.staff)
        unverified = make_user("u", "u_cf", verified=False)
        self.client.force_login(unverified)
        self.client.post(reverse("duels:cup_register", args=[cup.pk]))
        self.assertFalse(cup.entries.exists())
        verified = make_user("v", "v_cf")
        self.client.force_login(verified)
        self.client.post(reverse("duels:cup_register", args=[cup.pk]))
        self.assertTrue(cup.entries.filter(user=verified).exists())

    def test_bracket_and_projector_render(self):
        cup = draw_bracket(self.make_cup([1600, 1500, 1400]))
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("duels:cup", args=[cup.pk]))
        self.assertContains(resp, "Semifinals")
        self.assertContains(resp, "Start Semifinals")
        resp = self.client.get(reverse("duels:cup", args=[cup.pk]) + "?projector=1")
        self.assertContains(resp, 'class="projector"')
        self.assertNotContains(resp, "Start Semifinals")
        data = self.client.get(reverse("duels:cup_state", args=[cup.pk])).json()
        self.assertIn("version", data)
        self.assertEqual(len(data["matches"]), 3)
