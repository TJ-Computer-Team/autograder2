from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .ladder import JoinError, join_ladder, poll_window, refresh_entry, skip_rung
from .models import Ladder, LadderEntry, LadderRung
from .selection import SelectionError, ladder_ratings, pick_ladder_problems
from .tests import make_user


def problem(cid, rating, index="A", tags=()):
    return {
        "contestId": cid,
        "index": index,
        "name": f"P{cid}",
        "rating": rating,
        "tags": list(tags),
    }


class LadderSelectionTests(TestCase):
    def test_ratings_ramp_evenly(self):
        self.assertEqual(ladder_ratings(800, 1600, 5), [800, 1000, 1200, 1400, 1600])
        self.assertEqual(ladder_ratings(1200, 1600, 1), [1200])

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_picks_one_per_rung_easiest_first(self, problems, solved):
        problems.return_value = [
            problem(1003, 1200),
            problem(1001, 800),
            problem(1002, 1000),
        ]
        solved.return_value = set()
        picked = pick_ladder_problems(800, 1200, 3, ["a"])
        self.assertEqual([p["contestId"] for p in picked], [1001, 1002, 1003])

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_skips_solved_and_falls_back_to_nearest(self, problems, solved):
        problems.return_value = [
            problem(1001, 800),
            problem(1002, 900),
            problem(1003, 1000),
        ]
        solved.return_value = {(1001, "A")}
        picked = pick_ladder_problems(800, 1000, 2, ["a"])
        self.assertEqual([p["contestId"] for p in picked], [1002, 1003])

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_not_enough_problems_is_an_error(self, problems, solved):
        problems.return_value = [problem(1001, 800)]
        solved.return_value = set()
        with self.assertRaises(SelectionError):
            pick_ladder_problems(800, 1000, 2, ["a"])

    @patch("autograder.apps.duels.selection.fetch_solved_set")
    @patch("autograder.apps.duels.selection.fetch_cf_problems")
    def test_history_failure_is_fatal(self, problems, solved):
        problems.return_value = [problem(1001, 800)]
        solved.return_value = None
        with self.assertRaises(SelectionError):
            pick_ladder_problems(800, 800, 1, ["a"])


class LadderBase(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = make_user("alice", "alice_cf")
        self.bob = make_user("bob", "bob_cf")

    def make_ladder(self, rungs=3, **kwargs):
        defaults = dict(
            host=self.alice,
            status=Ladder.ACTIVE,
            rung_count=rungs,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        defaults.update(kwargs)
        ladder = Ladder.objects.create(**defaults)
        for i in range(1, rungs + 1):
            LadderRung.objects.create(
                ladder=ladder, position=i, cf_contest_id=1000 + i, cf_index="A"
            )
        return ladder

    def enter(self, ladder, user, **kwargs):
        defaults = dict(reached_at=ladder.started_at)
        defaults.update(kwargs)
        return LadderEntry.objects.create(ladder=ladder, user=user, **defaults)

    def refresh_with(self, entry, subs):
        """subs: {(contest_id, index): [(cf_id, verdict, created)]}"""

        def fake(handle, contest_id, index, since, count=20):
            return [s for s in subs.get((contest_id, index), []) if s[2] >= since]

        with patch("autograder.apps.duels.ladder.fetch_recent_submissions", fake):
            refresh_entry(entry, force=True)
        entry.refresh_from_db()


class ClimbTests(LadderBase):
    def test_accepted_moves_you_up_and_scores(self):
        ladder = self.make_ladder()
        entry = self.enter(ladder, self.alice)
        at = timezone.now() - timedelta(minutes=1)
        self.refresh_with(entry, {(1001, "A"): [(1, "OK", at)]})
        self.assertEqual(entry.position, 2)
        self.assertEqual(entry.solved, 1)
        self.assertEqual(entry.last_solve_at, at)
        self.assertEqual(entry.solve_times, [at.isoformat()])

    def test_wrong_answer_does_not_move_you(self):
        ladder = self.make_ladder()
        entry = self.enter(ladder, self.alice)
        at = timezone.now() - timedelta(minutes=1)
        self.refresh_with(entry, {(1001, "A"): [(1, "WRONG_ANSWER", at)]})
        self.assertEqual(entry.position, 1)
        self.assertEqual(entry.solved, 0)

    def test_accept_before_reaching_the_rung_is_ignored(self):
        ladder = self.make_ladder()
        entry = self.enter(ladder, self.alice)
        before = ladder.started_at - timedelta(minutes=1)
        self.refresh_with(entry, {(1001, "A"): [(1, "OK", before)]})
        self.assertEqual(entry.position, 1)

    def test_accept_after_the_deadline_is_ignored(self):
        ladder = self.make_ladder(
            started_at=timezone.now() - timedelta(minutes=61), duration_minutes=60
        )
        entry = self.enter(ladder, self.alice)
        late = ladder.deadline + timedelta(seconds=5)
        self.refresh_with(entry, {(1001, "A"): [(1, "OK", late)]})
        self.assertEqual(entry.solved, 0)

    def test_skip_moves_up_without_a_point(self):
        ladder = self.make_ladder(skips=1)
        entry = self.enter(ladder, self.alice)
        self.assertTrue(skip_rung(entry))
        entry.refresh_from_db()
        self.assertEqual((entry.position, entry.solved, entry.skips_used), (2, 0, 1))
        self.assertFalse(skip_rung(entry))

    def test_standings_rank_by_solves_then_time(self):
        ladder = self.make_ladder()
        now = timezone.now()
        self.enter(ladder, self.alice, solved=2, last_solve_at=now)
        self.enter(ladder, self.bob, solved=2, last_solve_at=now - timedelta(minutes=3))
        carol = make_user("carol", "carol_cf")
        self.enter(ladder, carol, solved=3, position=4, last_solve_at=now)
        order = [e.user.username for e in ladder.standings()]
        self.assertEqual(order, ["carol", "bob", "alice"])

    def test_ladder_finishes_when_everyone_is_done(self):
        ladder = self.make_ladder(rungs=1)
        entry = self.enter(ladder, self.alice)
        at = timezone.now() - timedelta(minutes=1)
        self.refresh_with(entry, {(1001, "A"): [(1, "OK", at)]})
        ladder.refresh_from_db()
        self.assertEqual(ladder.status, Ladder.FINISHED)


class JoinTests(LadderBase):
    def test_join_before_start(self):
        ladder = Ladder.objects.create(host=self.alice)
        entry = join_ladder(ladder, self.bob)
        self.assertEqual(entry.position, 1)
        self.assertIsNone(entry.reached_at)

    def test_joining_twice_is_harmless(self):
        ladder = Ladder.objects.create(host=self.alice)
        join_ladder(ladder, self.bob)
        join_ladder(ladder, self.bob)
        self.assertEqual(ladder.entries.count(), 1)

    @patch("autograder.apps.duels.ladder.fetch_solved_set")
    def test_late_joiner_passes_over_rungs_already_solved(self, solved):
        ladder = self.make_ladder()
        solved.return_value = {(1001, "A"), (1003, "A")}
        entry = join_ladder(ladder, self.bob)
        self.assertEqual(entry.position, 2)
        self.assertEqual(entry.solved, 0)
        # Solving rung 2 jumps over the presolved rung 3.
        at = timezone.now()
        self.refresh_with(entry, {(1002, "A"): [(1, "OK", at)]})
        self.assertEqual(entry.position, 4)
        self.assertEqual(entry.solved, 1)

    @patch("autograder.apps.duels.ladder.fetch_solved_set")
    def test_late_join_fails_closed_without_history(self, solved):
        ladder = self.make_ladder()
        solved.return_value = None
        with self.assertRaises(JoinError):
            join_ladder(ladder, self.bob)
        self.assertFalse(ladder.entries.exists())

    def test_cannot_join_once_time_is_up(self):
        ladder = self.make_ladder(
            started_at=timezone.now() - timedelta(minutes=61), duration_minutes=60
        )
        with (
            patch("autograder.apps.duels.ladder.fetch_solved_set", return_value=set()),
            self.assertRaises(JoinError),
        ):
            join_ladder(ladder, self.bob)

    def test_cannot_join_while_problems_are_drawn(self):
        ladder = Ladder.objects.create(
            host=self.alice, start_requested_at=timezone.now()
        )
        with self.assertRaises(JoinError):
            join_ladder(ladder, self.bob)


class TaskTests(LadderBase):
    @patch("autograder.apps.duels.tasks.pick_ladder_problems")
    def test_start_draws_rungs_and_opens(self, pick):
        pick.return_value = [problem(1001, 800), problem(1002, 1000)]
        ladder = Ladder.objects.create(host=self.alice, rung_count=2)
        join_ladder(ladder, self.alice)
        Ladder.objects.filter(pk=ladder.pk).update(start_requested_at=timezone.now())
        from .tasks import start_ladder

        start_ladder(ladder.id)
        ladder.refresh_from_db()
        self.assertEqual(ladder.status, Ladder.ACTIVE)
        self.assertEqual(ladder.rungs.count(), 2)
        self.assertIsNotNone(ladder.entries.get().reached_at)

    @patch("autograder.apps.duels.tasks.pick_ladder_problems")
    def test_selection_failure_lets_the_host_retry(self, pick):
        pick.side_effect = SelectionError("Not enough.")
        ladder = Ladder.objects.create(
            host=self.alice, start_requested_at=timezone.now()
        )
        from .tasks import start_ladder

        start_ladder(ladder.id)
        ladder.refresh_from_db()
        self.assertEqual(ladder.status, Ladder.PENDING)
        self.assertIsNone(ladder.start_requested_at)
        self.assertIn("Not enough", ladder.selection_error)

    def test_close_sweeps_then_finishes(self):
        ladder = self.make_ladder(
            started_at=timezone.now() - timedelta(minutes=61), duration_minutes=60
        )
        entry = self.enter(ladder, self.alice)
        in_time = ladder.deadline - timedelta(seconds=2)

        def fake(handle, contest_id, index, since, count=20):
            return [(1, "OK", in_time)] if contest_id == 1001 else []

        from .tasks import close_ladder

        with patch("autograder.apps.duels.ladder.fetch_recent_submissions", fake):
            close_ladder(ladder.id)
        entry.refresh_from_db()
        ladder.refresh_from_db()
        self.assertEqual(entry.solved, 1)
        self.assertEqual(ladder.status, Ladder.FINISHED)


class LadderViewTests(LadderBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)

    def test_create_makes_host_an_entrant(self):
        resp = self.client.post(
            reverse("duels:ladder_create"),
            {"rating_min": "1600", "rating_max": "800", "rung_count": "99"},
        )
        ladder = Ladder.objects.get()
        self.assertRedirects(resp, reverse("duels:ladder", args=[ladder.id]))
        self.assertEqual((ladder.rating_min, ladder.rating_max), (800, 1600))
        self.assertEqual(ladder.rung_count, 20)
        self.assertEqual(ladder.skips, 1)
        self.assertTrue(ladder.entries.filter(user=self.alice).exists())

    @patch("autograder.apps.duels.ladder_views.start_ladder")
    def test_only_host_starts(self, task):
        ladder = Ladder.objects.create(host=self.bob)
        self.client.post(reverse("duels:ladder_start", args=[ladder.id]))
        task.delay.assert_not_called()

    @patch("autograder.apps.duels.ladder_views.start_ladder")
    def test_double_start_draws_once(self, task):
        ladder = Ladder.objects.create(host=self.alice)
        url = reverse("duels:ladder_start", args=[ladder.id])
        self.client.post(url)
        self.client.post(url)
        task.delay.assert_called_once_with(ladder.id)

    def test_problem_hidden_from_spectators(self):
        ladder = self.make_ladder(host=self.bob)
        self.enter(ladder, self.bob)
        resp = self.client.get(reverse("duels:ladder", args=[ladder.id]))
        self.assertNotContains(resp, "codeforces.com/problemset/problem/1001")

    def test_state_json(self):
        ladder = self.make_ladder()
        self.enter(ladder, self.alice)
        with patch(
            "autograder.apps.duels.ladder.fetch_recent_submissions", return_value=[]
        ):
            data = self.client.get(
                reverse("duels:ladder_state", args=[ladder.id])
            ).json()
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["my_position"], 1)
        self.assertTrue(data["standings"][0]["me"])
        self.assertEqual(data["chart"]["max"], 3)
        self.assertEqual(data["chart"]["players"][0]["solves"], [])

    def test_skip_view_checks_cf_first(self):
        ladder = self.make_ladder()
        entry = self.enter(ladder, self.alice)
        at = timezone.now() - timedelta(seconds=30)
        with patch(
            "autograder.apps.duels.ladder.fetch_recent_submissions",
            return_value=[(1, "OK", at)],
        ):
            self.client.post(reverse("duels:ladder_skip", args=[ladder.id]))
        entry.refresh_from_db()
        self.assertEqual((entry.position, entry.solved, entry.skips_used), (2, 1, 0))

    def test_list_page_renders(self):
        self.make_ladder()
        resp = self.client.get(reverse("duels:ladders"))
        self.assertContains(resp, "Host a battle royale")
        self.assertContains(self.client.get(reverse("duels:list")), "Battle Royale")


class PollWindowTests(LadderBase):
    def test_small_ladder_uses_the_floor(self):
        ladder = self.make_ladder()
        self.enter(ladder, self.alice)
        self.enter(ladder, self.bob)
        self.assertEqual(poll_window(ladder), 4)

    def test_window_grows_with_climbers_only(self):
        ladder = self.make_ladder(rungs=2)
        for i in range(12):
            self.enter(ladder, make_user(f"p{i}", f"p{i}_cf"))
        self.assertEqual(poll_window(ladder), 18)
        # Finished players are no longer polled, so they don't stretch the window.
        ladder.entries.filter(user__username__in=["p0", "p1"]).update(position=3)
        self.assertEqual(poll_window(ladder), 15)

    def test_repeat_polls_within_the_window_make_one_cf_call(self):
        ladder = self.make_ladder()
        entry = self.enter(ladder, self.alice)
        with patch(
            "autograder.apps.duels.ladder.fetch_recent_submissions", return_value=[]
        ) as fetch:
            refresh_entry(entry)
            refresh_entry(entry)
        self.assertEqual(fetch.call_count, 1)
