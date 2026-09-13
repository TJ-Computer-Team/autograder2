from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..index.models import GraderUser
from .models import Duel, DuelSubmission
from .refresh import expire_stale_challenges, refresh_duel
from .selection import SelectionError, pick_duel_problem

# Codeforces is never called in tests; every helper is patched at its boundary.
PROBLEMS = [
    {"contestId": 1, "index": "A", "name": "Easy", "rating": 800, "tags": ["math"]},
    {"contestId": 2, "index": "B", "name": "Mid", "rating": 1200, "tags": ["dp"]},
    {
        "contestId": 3,
        "index": "C",
        "name": "Hard",
        "rating": 2000,
        "tags": ["dp", "greedy"],
    },
]


def make_user(username, handle, verified=True):
    user = GraderUser.objects.create_user(
        email=f"{username}@example.com",
        username=username,
        display_name=username.title(),
        cf_handle=handle,
    )
    if verified:
        user.cf_verified_at = timezone.now()
        user.save(update_fields=["cf_verified_at"])
    return user


class SelectionTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_respects_rating_band(self, problems, solved):
        problems.return_value = PROBLEMS
        solved.return_value = set()
        picked = pick_duel_problem(1000, 1500, ["a", "b"])
        self.assertEqual(picked["contestId"], 2)

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_respects_tags(self, problems, solved):
        problems.return_value = PROBLEMS
        solved.return_value = set()
        picked = pick_duel_problem(800, 3500, ["a"], tags="greedy")
        self.assertEqual(picked["contestId"], 3)

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_excludes_problems_either_player_solved(self, problems, solved):
        """The core anti-cheat: a solved problem could be won by resubmitting."""
        problems.return_value = PROBLEMS
        solved.side_effect = [{(1, "A")}, {(3, "C")}]
        picked = pick_duel_problem(800, 3500, ["a", "b"])
        self.assertEqual(picked["contestId"], 2)

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_raises_when_pool_exhausted(self, problems, solved):
        problems.return_value = PROBLEMS
        solved.return_value = {(1, "A"), (2, "B"), (3, "C")}
        with self.assertRaises(SelectionError):
            pick_duel_problem(800, 3500, ["a"])

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_history_failure_is_fatal_not_ignored(self, problems, solved):
        """None means 'unknown', and must not be treated as 'solved nothing'."""
        problems.return_value = PROBLEMS
        solved.return_value = None
        with self.assertRaises(SelectionError):
            pick_duel_problem(800, 3500, ["a"])

    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_raises_when_codeforces_unreachable(self, problems):
        problems.return_value = []
        with self.assertRaises(SelectionError):
            pick_duel_problem(800, 3500, ["a"])

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_raises_when_band_has_no_problems(self, problems, solved):
        problems.return_value = PROBLEMS
        solved.return_value = set()
        with self.assertRaises(SelectionError):
            pick_duel_problem(3000, 3100, ["a"])


class DuelBase(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = make_user("alice", "alice_cf")
        self.bob = make_user("bob", "bob_cf")

    def make_duel(self, **kwargs):
        defaults = dict(
            challenger=self.alice,
            opponent=self.bob,
            status=Duel.ACTIVE,
            cf_contest_id=1,
            cf_index="A",
            cf_name="Easy",
            started_at=timezone.now() - timedelta(minutes=1),
        )
        defaults.update(kwargs)
        return Duel.objects.create(**defaults)


class WinnerDetectionTests(DuelBase):
    def _sub(self, user, verdict, offset_seconds):
        """Fake one CF submission for `user` at start + offset."""
        return (
            abs(hash((user.id, offset_seconds))) % 10**9,
            verdict,
            self.duel.started_at + timedelta(seconds=offset_seconds),
        )

    def _refresh_with(self, per_handle):
        def fake(handle, contest_id, index, since, count=20):
            return [s for s in per_handle.get(handle, []) if s[2] >= since]

        with patch("autograder.apps.duels.refresh.fetch_recent_submissions", fake):
            refresh_duel(self.duel, force=True)
        self.duel.refresh_from_db()

    def test_first_accepted_wins(self):
        self.duel = self.make_duel()
        self._refresh_with(
            {
                "alice_cf": [self._sub(self.alice, "OK", 90)],
                "bob_cf": [self._sub(self.bob, "OK", 30)],
            }
        )
        self.assertEqual(self.duel.status, Duel.FINISHED)
        self.assertEqual(self.duel.winner, self.bob)
        self.assertEqual(self.duel.end_reason, Duel.SOLVED)

    def test_wrong_answers_do_not_end_the_duel(self):
        self.duel = self.make_duel()
        self._refresh_with(
            {
                "alice_cf": [self._sub(self.alice, "WRONG_ANSWER", 10)],
                "bob_cf": [self._sub(self.bob, "TIME_LIMIT_EXCEEDED", 20)],
            }
        )
        self.assertEqual(self.duel.status, Duel.ACTIVE)
        self.assertIsNone(self.duel.winner)
        self.assertEqual(self.duel.submissions.count(), 2)

    def test_accept_before_start_is_ignored(self):
        """Resubmitting a solve from before the duel must not win it."""
        self.duel = self.make_duel()
        old = (
            999,
            "OK",
            self.duel.started_at - timedelta(days=30),
        )
        self._refresh_with({"alice_cf": [old]})
        self.assertEqual(self.duel.status, Duel.ACTIVE)
        self.assertIsNone(self.duel.winner)

    def test_loser_accepting_later_does_not_flip_the_result(self):
        self.duel = self.make_duel()
        self._refresh_with({"bob_cf": [self._sub(self.bob, "OK", 30)]})
        self.assertEqual(self.duel.winner, self.bob)

        self._refresh_with(
            {
                "bob_cf": [self._sub(self.bob, "OK", 30)],
                "alice_cf": [self._sub(self.alice, "OK", 120)],
            }
        )
        self.assertEqual(self.duel.winner, self.bob)

    def test_still_judging_is_recorded_without_winning(self):
        self.duel = self.make_duel()
        self._refresh_with(
            {"alice_cf": [(1234, None, self.duel.started_at + timedelta(seconds=5))]}
        )
        self.assertEqual(self.duel.status, Duel.ACTIVE)
        self.assertEqual(self.duel.submissions.first().verdict, "")

    def test_submission_is_not_duplicated_across_polls(self):
        self.duel = self.make_duel()
        sub = self._sub(self.alice, "WRONG_ANSWER", 10)
        self._refresh_with({"alice_cf": [sub]})
        self._refresh_with({"alice_cf": [sub]})
        self.assertEqual(self.duel.submissions.count(), 1)


class ThrottleTests(DuelBase):
    def test_repeat_polls_within_the_window_make_one_cf_call(self):
        duel = self.make_duel()
        with patch(
            "autograder.apps.duels.refresh.fetch_recent_submissions", return_value=[]
        ) as fetch:
            self.assertTrue(refresh_duel(duel))
            self.assertFalse(refresh_duel(duel))
            self.assertFalse(refresh_duel(duel))
        # two players, one window
        self.assertEqual(fetch.call_count, 2)


class LifecycleTests(DuelBase):
    def test_timeout_ends_as_a_draw(self):
        duel = self.make_duel(
            started_at=timezone.now() - timedelta(minutes=90), duration_minutes=45
        )
        with patch(
            "autograder.apps.duels.refresh.fetch_recent_submissions", return_value=[]
        ) as fetch:
            refresh_duel(duel, force=True)
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.FINISHED)
        self.assertIsNone(duel.winner)
        self.assertEqual(duel.end_reason, Duel.TIMEOUT)
        fetch.assert_not_called()

    def test_finished_duel_is_not_refreshed(self):
        duel = self.make_duel(status=Duel.FINISHED)
        with patch(
            "autograder.apps.duels.refresh.fetch_recent_submissions", return_value=[]
        ) as fetch:
            self.assertFalse(refresh_duel(duel))
        fetch.assert_not_called()

    def test_stale_challenges_expire(self):
        fresh = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, status=Duel.PENDING
        )
        stale = Duel.objects.create(
            challenger=self.bob, opponent=self.alice, status=Duel.PENDING
        )
        Duel.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

        expire_stale_challenges()
        fresh.refresh_from_db()
        stale.refresh_from_db()
        self.assertEqual(fresh.status, Duel.PENDING)
        self.assertEqual(stale.status, Duel.EXPIRED)


class ViewTests(DuelBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)

    def test_unverified_user_cannot_challenge(self):
        carol = make_user("carol", "carol_cf", verified=False)
        self.client.force_login(carol)
        resp = self.client.post(
            reverse("duels:challenge"),
            {"opponent": self.bob.id, "rating_min": 800, "rating_max": 1200},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Duel.objects.filter(challenger=carol).exists())

    def test_cannot_challenge_an_unverified_opponent(self):
        carol = make_user("carol", "carol_cf", verified=False)
        self.client.post(
            reverse("duels:challenge"),
            {"opponent": carol.id, "rating_min": 800, "rating_max": 1200},
        )
        self.assertFalse(Duel.objects.filter(opponent=carol).exists())

    def test_cannot_challenge_yourself(self):
        self.client.post(
            reverse("duels:challenge"),
            {"opponent": self.alice.id, "rating_min": 800, "rating_max": 1200},
        )
        self.assertFalse(Duel.objects.filter(opponent=self.alice).exists())

    @patch("autograder.apps.duels.views.start_duel")
    def test_challenge_creates_a_pending_duel(self, task):
        resp = self.client.post(
            reverse("duels:challenge"),
            {"opponent": self.bob.id, "rating_min": 1500, "rating_max": 1200},
        )
        duel = Duel.objects.get(challenger=self.alice, opponent=self.bob)
        self.assertEqual(duel.status, Duel.PENDING)
        # reversed bounds are normalised rather than rejected
        self.assertEqual((duel.rating_min, duel.rating_max), (1200, 1500))
        self.assertRedirects(resp, reverse("duels:detail", args=[duel.id]))
        task.delay.assert_not_called()

    @patch("autograder.apps.duels.views.start_duel")
    def test_only_the_opponent_can_accept(self, task):
        duel = self.make_duel(status=Duel.PENDING, started_at=None, cf_contest_id=None)
        self.client.post(reverse("duels:accept", args=[duel.id]))
        duel.refresh_from_db()
        self.assertIsNone(duel.accepted_at)
        task.delay.assert_not_called()

        self.client.force_login(self.bob)
        self.client.post(reverse("duels:accept", args=[duel.id]))
        duel.refresh_from_db()
        self.assertIsNotNone(duel.accepted_at)
        task.delay.assert_called_once_with(duel.id)

    def test_forfeit_awards_the_opponent(self):
        duel = self.make_duel()
        self.client.post(reverse("duels:forfeit", args=[duel.id]))
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.FINISHED)
        self.assertEqual(duel.winner, self.bob)
        self.assertEqual(duel.end_reason, Duel.FORFEIT)

    def test_non_participant_cannot_forfeit(self):
        duel = self.make_duel()
        carol = make_user("carol", "carol_cf")
        self.client.force_login(carol)
        self.client.post(reverse("duels:forfeit", args=[duel.id]))
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.ACTIVE)

    def test_non_participant_can_watch_an_active_duel(self):
        duel = self.make_duel()
        carol = make_user("carol", "carol_cf")
        self.client.force_login(carol)
        with patch(
            "autograder.apps.duels.refresh.fetch_recent_submissions", return_value=[]
        ):
            resp = self.client.get(reverse("duels:detail", args=[duel.id]))
        self.assertEqual(resp.status_code, 200)

    def test_pending_duel_is_private(self):
        duel = self.make_duel(status=Duel.PENDING, started_at=None)
        carol = make_user("carol", "carol_cf")
        self.client.force_login(carol)
        resp = self.client.get(reverse("duels:detail", args=[duel.id]))
        self.assertEqual(resp.status_code, 404)

    def test_state_endpoint_returns_json(self):
        duel = self.make_duel()
        DuelSubmission.objects.create(
            duel=duel,
            user=self.alice,
            cf_submission_id=1,
            verdict="WRONG_ANSWER",
            created_at=timezone.now(),
        )
        with patch(
            "autograder.apps.duels.refresh.fetch_recent_submissions", return_value=[]
        ):
            resp = self.client.get(reverse("duels:state", args=[duel.id]))
        data = resp.json()
        self.assertEqual(data["status"], Duel.ACTIVE)
        self.assertEqual(len(data["submissions"]), 1)
        self.assertFalse(data["submissions"][0]["accepted"])

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("duels:list"))
        self.assertEqual(resp.status_code, 302)


class StartTaskTests(DuelBase):
    @patch("autograder.apps.duels.tasks.pick_duel_problem")
    def test_start_sets_the_problem_and_activates(self, pick):
        pick.return_value = PROBLEMS[1]
        duel = self.make_duel(status=Duel.PENDING, started_at=None, cf_contest_id=None)
        from .tasks import start_duel

        start_duel(duel.id)
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.ACTIVE)
        self.assertEqual(duel.cf_contest_id, 2)
        self.assertIsNotNone(duel.started_at)

    @patch("autograder.apps.duels.tasks.pick_duel_problem")
    def test_selection_failure_leaves_it_pending_with_a_reason(self, pick):
        pick.side_effect = SelectionError("Pool exhausted.")
        duel = self.make_duel(status=Duel.PENDING, started_at=None, cf_contest_id=None)
        from .tasks import start_duel

        start_duel(duel.id)
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.PENDING)
        self.assertIn("Pool exhausted", duel.selection_error)


class StateJsonNameTests(DuelBase):
    """A blank display_name must not make the page report a draw.

    duel_state used to send display_name directly. For an account with no display
    name that is "", which is falsy in JavaScript, so the client rendered the
    "Draw" branch even though a winner was set.
    """

    def setUp(self):
        super().setUp()
        GraderUser.objects.filter(pk=self.alice.pk).update(display_name="")
        self.alice.refresh_from_db()
        self.client.force_login(self.alice)

    def _state(self, duel):
        with patch(
            "autograder.apps.duels.refresh.fetch_recent_submissions", return_value=[]
        ):
            return self.client.get(reverse("duels:state", args=[duel.id])).json()

    def test_winner_name_falls_back_to_username(self):
        duel = self.make_duel()
        duel.finish(self.alice, Duel.FORFEIT)
        data = self._state(duel)
        self.assertEqual(data["winner"], "alice")
        self.assertTrue(data["winner"])  # would be "" before the fix

    def test_player_names_fall_back_to_username(self):
        duel = self.make_duel()
        names = [p["name"] for p in self._state(duel)["players"]]
        self.assertIn("alice", names)
        self.assertTrue(all(names))

    def test_submission_names_fall_back_to_username(self):
        duel = self.make_duel()
        DuelSubmission.objects.create(
            duel=duel,
            user=self.alice,
            cf_submission_id=7,
            verdict="WRONG_ANSWER",
            created_at=timezone.now(),
        )
        self.assertEqual(self._state(duel)["submissions"][0]["name"], "alice")

    def test_draw_still_reports_no_winner(self):
        duel = self.make_duel()
        duel.finish(None, Duel.TIMEOUT)
        self.assertIsNone(self._state(duel)["winner"])
