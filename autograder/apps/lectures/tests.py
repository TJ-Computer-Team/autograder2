from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..contests.models import Contest
from ..index.models import GraderUser
from ..problems.models import Problem
from ..runtests.models import Submission
from .models import LectureSet, LectureSetEntry, parse_codeforces_url
from .utils import can_see_problem, solved_problem_ids, visible_entries


def make_contest(name="Contest", *, started=True, tjioi=False):
    now = timezone.now()
    start = now - timedelta(days=1) if started else now + timedelta(days=1)
    return Contest.objects.create(
        name=name, season=2027, tjioi=tjioi, start=start, end=start + timedelta(days=2)
    )


def make_problem(contest=None, name="Problem", *, secret=False):
    return Problem.objects.create(
        name=name,
        contest=contest,
        points=100,
        contest_letter="A",
        statement="s",
        inputtxt="i",
        outputtxt="o",
        samples="x",
        tl=1000,
        ml=256,
        secret=secret,
    )


class LabelTests(TestCase):
    def test_letters(self):
        s = LectureSet(label_style=LectureSet.LETTERS)
        self.assertEqual([s.label_for(i) for i in range(4)], ["A", "B", "C", "D"])

    def test_letters_past_z(self):
        s = LectureSet(label_style=LectureSet.LETTERS)
        self.assertEqual(s.label_for(25), "Z")
        self.assertEqual(s.label_for(26), "AA")
        self.assertEqual(s.label_for(27), "AB")

    def test_numbers(self):
        s = LectureSet(label_style=LectureSet.NUMBERS)
        self.assertEqual([s.label_for(i) for i in range(3)], ["1", "2", "3"])

    def test_none(self):
        s = LectureSet(label_style=LectureSet.NONE)
        self.assertEqual(s.label_for(0), "")


class CodeforcesUrlTests(TestCase):
    def test_problemset_url(self):
        self.assertEqual(
            parse_codeforces_url("https://codeforces.com/problemset/problem/1234/A"),
            (1234, "A"),
        )

    def test_contest_url(self):
        self.assertEqual(
            parse_codeforces_url("https://codeforces.com/contest/1700/problem/C2"),
            (1700, "C2"),
        )

    def test_non_codeforces(self):
        self.assertEqual(parse_codeforces_url("https://usaco.org/x"), (None, None))
        self.assertEqual(parse_codeforces_url(""), (None, None))

    def test_ids_stored_on_save(self):
        s = LectureSet.objects.create(title="S", slug="s")
        entry = LectureSetEntry.objects.create(
            lecture_set=s, external_url="https://codeforces.com/problemset/problem/99/B"
        )
        entry.refresh_from_db()
        self.assertEqual((entry.cf_contest_id, entry.cf_index), (99, "B"))

    def test_ids_cleared_for_non_cf_link(self):
        s = LectureSet.objects.create(title="S", slug="s")
        entry = LectureSetEntry.objects.create(
            lecture_set=s, external_url="https://usaco.org/index.php?page=viewproblem"
        )
        entry.refresh_from_db()
        self.assertIsNone(entry.cf_contest_id)
        self.assertEqual(entry.cf_index, "")


class EntryConstraintTests(TestCase):
    def setUp(self):
        self.set = LectureSet.objects.create(title="S", slug="s")
        self.problem = make_problem(make_contest())

    def test_internal_only_is_valid(self):
        LectureSetEntry.objects.create(lecture_set=self.set, problem=self.problem)

    def test_external_only_is_valid(self):
        LectureSetEntry.objects.create(
            lecture_set=self.set, external_url="https://example.com/p"
        )

    def test_both_sides_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LectureSetEntry.objects.create(
                    lecture_set=self.set,
                    problem=self.problem,
                    external_url="https://example.com/p",
                )

    def test_neither_side_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LectureSetEntry.objects.create(lecture_set=self.set)

    def test_clean_reports_both_sides(self):
        entry = LectureSetEntry(
            lecture_set=self.set,
            problem=self.problem,
            external_url="https://example.com/p",
        )
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_clean_reports_neither_side(self):
        with self.assertRaises(ValidationError):
            LectureSetEntry(lecture_set=self.set).clean()


class VisibilityTests(TestCase):
    """A set must not become a side door to a problem the user can't otherwise see."""

    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        self.staff = GraderUser.objects.create_user(
            email="a@example.com", username="2027a", display_name="Admin", is_staff=True
        )
        self.tjioi_user = GraderUser.objects.create_user(
            email="t@example.com", username="2027t", display_name="T", is_tjioi=True
        )

        self.open_problem = make_problem(make_contest("Open"), "Open Problem")
        self.secret_problem = make_problem(make_contest("S"), "Secret", secret=True)
        self.unstarted_problem = make_problem(
            make_contest("Future", started=False), "Unstarted"
        )
        self.tjioi_problem = make_problem(
            make_contest("TJIOI", tjioi=True), "TJIOI Problem"
        )

    def test_open_problem_visible_to_everyone(self):
        self.assertTrue(can_see_problem(self.open_problem, self.user))

    def test_secret_hidden_from_regular_user(self):
        self.assertFalse(can_see_problem(self.secret_problem, self.user))
        self.assertTrue(can_see_problem(self.secret_problem, self.staff))

    def test_unstarted_hidden_from_regular_user(self):
        self.assertFalse(can_see_problem(self.unstarted_problem, self.user))
        self.assertTrue(can_see_problem(self.unstarted_problem, self.staff))

    def test_tjioi_hidden_from_regular_user(self):
        self.assertFalse(can_see_problem(self.tjioi_problem, self.user))
        self.assertTrue(can_see_problem(self.tjioi_problem, self.tjioi_user))
        self.assertTrue(can_see_problem(self.tjioi_problem, self.staff))

    def test_visible_entries_filters_and_keeps_external(self):
        s = LectureSet.objects.create(title="Mixed", slug="mixed", published=True)
        entries = [
            LectureSetEntry.objects.create(
                lecture_set=s, problem=self.open_problem, order=0
            ),
            LectureSetEntry.objects.create(
                lecture_set=s, problem=self.secret_problem, order=1
            ),
            LectureSetEntry.objects.create(
                lecture_set=s, external_url="https://codeforces.com/x", order=2
            ),
        ]
        visible = visible_entries(entries, self.user)
        self.assertEqual(len(visible), 2)
        self.assertNotIn(self.secret_problem.id, [e.problem_id for e in visible])
        self.assertEqual(len(visible_entries(entries, self.staff)), 3)


class SolvedTests(TestCase):
    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        contest = make_contest()
        self.solved = make_problem(contest, "Solved")
        self.unsolved = make_problem(contest, "Unsolved")

    def _submit(self, problem, verdict):
        return Submission.objects.create(
            usr=self.user,
            code="x",
            problem=problem,
            language="python",
            contest=problem.contest,
            verdict=verdict,
        )

    def test_accepted_counts(self):
        self._submit(self.solved, "Accepted")
        self.assertEqual(
            solved_problem_ids(self.user, [self.solved.id]), {self.solved.id}
        )

    def test_ac_alias_counts(self):
        """Filler data and older rows use 'AC' rather than 'Accepted'."""
        self._submit(self.solved, "AC")
        self.assertEqual(
            solved_problem_ids(self.user, [self.solved.id]), {self.solved.id}
        )

    def test_wrong_answer_does_not_count(self):
        self._submit(self.unsolved, "Wrong Answer on test 3")
        self.assertEqual(solved_problem_ids(self.user, [self.unsolved.id]), set())

    def test_empty_input_makes_no_query(self):
        with self.assertNumQueries(0):
            self.assertEqual(solved_problem_ids(self.user, []), set())


class ViewTests(TestCase):
    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        self.staff = GraderUser.objects.create_user(
            email="a@example.com", username="2027a", display_name="Admin", is_staff=True
        )
        self.published = LectureSet.objects.create(
            title="Segment Trees",
            slug="segment-trees",
            topic="Data structures",
            published=True,
        )
        self.draft = LectureSet.objects.create(
            title="Draft Set", slug="draft-set", published=False
        )
        self.problem = make_problem(make_contest(), "Range Sum Query")
        LectureSetEntry.objects.create(
            lecture_set=self.published, problem=self.problem, difficulty="easy", order=0
        )
        self.client.force_login(self.user)

    def test_list_hides_drafts_from_regular_user(self):
        resp = self.client.get(reverse("lectures:list"))
        self.assertContains(resp, "Segment Trees")
        self.assertNotContains(resp, "Draft Set")

    def test_list_shows_drafts_to_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("lectures:list"))
        self.assertContains(resp, "Draft Set")

    def test_draft_detail_404s_for_regular_user(self):
        resp = self.client.get(reverse("lectures:detail", args=["draft-set"]))
        self.assertEqual(resp.status_code, 404)

    def test_draft_detail_opens_for_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("lectures:detail", args=["draft-set"]))
        self.assertEqual(resp.status_code, 200)

    def test_detail_renders_entry_and_unsolved(self):
        resp = self.client.get(reverse("lectures:detail", args=["segment-trees"]))
        self.assertContains(resp, "Range Sum Query")
        self.assertContains(resp, "Unsolved")

    def test_detail_marks_solved(self):
        Submission.objects.create(
            usr=self.user,
            code="x",
            problem=self.problem,
            language="python",
            contest=self.problem.contest,
            verdict="Accepted",
        )
        resp = self.client.get(reverse("lectures:detail", args=["segment-trees"]))
        self.assertContains(resp, "Solved")

    def test_labels_skip_hidden_entries(self):
        """A hidden entry must not leave a gap that reveals it exists."""
        hidden = make_problem(make_contest("S2"), "Secret", secret=True)
        LectureSetEntry.objects.create(
            lecture_set=self.published, problem=hidden, order=1
        )
        visible = make_problem(make_contest("Open2"), "Visible Later")
        LectureSetEntry.objects.create(
            lecture_set=self.published, problem=visible, order=2
        )

        resp = self.client.get(reverse("lectures:detail", args=["segment-trees"]))
        labels = [row["label"] for row in resp.context["rows"]]
        self.assertEqual(labels, ["A", "B"])
        self.assertNotContains(resp, "Secret")

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("lectures:list"))
        self.assertEqual(resp.status_code, 302)


class PotwAbsorptionMigrationTests(TestCase):
    """The 0002 data migration's logic, exercised directly.

    The dev database only holds the linkless `intermediate` row that migration
    index.0013 inserts, so the absorption path never runs there. The module name
    starts with a digit, so it has to be loaded by importlib rather than imported.
    """

    def setUp(self):
        import importlib

        self.mig = importlib.import_module(
            "autograder.apps.lectures.migrations.0002_absorb_potw"
        )
        # The migration takes an app registry; the live one works here because the
        # models have not changed shape since 0001.
        from django.apps import apps

        self.apps = apps

    def test_absorbs_rows_that_have_links(self):
        from ..index.models import ProblemOfTheWeek

        ProblemOfTheWeek.objects.update_or_create(
            level="beginner",
            defaults={
                "title": "Easy One",
                "link": "https://codeforces.com/problemset/problem/4/A",
            },
        )
        ProblemOfTheWeek.objects.update_or_create(
            level="advanced",
            defaults={
                "title": "Hard One",
                "link": "https://codeforces.com/contest/1700/problem/F",
            },
        )

        self.mig.absorb(self.apps, None)

        s = LectureSet.objects.get(slug=self.mig.SLUG)
        self.assertEqual(s.kind, LectureSet.POTW)
        self.assertTrue(s.published)

        entries = list(s.entries.order_by("order"))
        self.assertEqual([e.difficulty for e in entries], ["easy", "hard"])
        self.assertEqual([e.external_title for e in entries], ["Easy One", "Hard One"])
        # CF ids are parsed on save, so the migrated links get them too.
        self.assertEqual(entries[0].cf_contest_id, 4)
        self.assertEqual(entries[1].cf_index, "F")

    def test_skips_rows_without_a_link(self):
        """A linkless placeholder would violate the internal-xor-external constraint."""
        from ..index.models import ProblemOfTheWeek

        ProblemOfTheWeek.objects.update_or_create(
            level="intermediate", defaults={"title": "", "link": None}
        )
        self.mig.absorb(self.apps, None)
        self.assertFalse(LectureSet.objects.filter(slug=self.mig.SLUG).exists())

    def test_absorb_is_idempotent(self):
        from ..index.models import ProblemOfTheWeek

        ProblemOfTheWeek.objects.update_or_create(
            level="beginner",
            defaults={
                "title": "Easy One",
                "link": "https://codeforces.com/problemset/problem/4/A",
            },
        )
        self.mig.absorb(self.apps, None)
        self.mig.absorb(self.apps, None)
        self.assertEqual(LectureSet.objects.filter(slug=self.mig.SLUG).count(), 1)
        self.assertEqual(LectureSet.objects.get(slug=self.mig.SLUG).entries.count(), 1)

    def test_reverse_removes_set_but_keeps_potw_rows(self):
        from ..index.models import ProblemOfTheWeek

        ProblemOfTheWeek.objects.update_or_create(
            level="beginner",
            defaults={
                "title": "Easy One",
                "link": "https://codeforces.com/problemset/problem/4/A",
            },
        )
        self.mig.absorb(self.apps, None)
        self.mig.unabsorb(self.apps, None)

        self.assertFalse(LectureSet.objects.filter(slug=self.mig.SLUG).exists())
        self.assertTrue(ProblemOfTheWeek.objects.filter(level="beginner").exists())


class LectureOnlyProblemTests(TestCase):
    """A problem written for a lecture set and never for a contest."""

    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        self.staff = GraderUser.objects.create_user(
            email="a@example.com", username="2027a", display_name="Admin", is_staff=True
        )
        self.problem = make_problem(None, "Lecture Only Problem")
        self.lecture_set = LectureSet.objects.create(
            title="Intro", slug="intro", published=True
        )
        LectureSetEntry.objects.create(
            lecture_set=self.lecture_set, problem=self.problem, order=0
        )
        self.client.force_login(self.user)

    def test_problem_saves_without_a_contest(self):
        self.problem.refresh_from_db()
        self.assertIsNone(self.problem.contest)

    def test_visible_without_a_contest(self):
        self.assertTrue(can_see_problem(self.problem, self.user))

    def test_secret_still_gates_a_lecture_only_problem(self):
        secret = make_problem(None, "Hidden", secret=True)
        self.assertFalse(can_see_problem(secret, self.user))
        self.assertTrue(can_see_problem(secret, self.staff))

    def test_appears_in_lecture_set(self):
        resp = self.client.get(reverse("lectures:detail", args=[self.lecture_set.slug]))
        self.assertContains(resp, "Lecture Only Problem")

    def test_problem_page_opens(self):
        resp = self.client.get(reverse("problems:problem", args=[self.problem.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Lecture Only Problem")

    def test_problem_page_has_no_back_to_contest_button(self):
        resp = self.client.get(reverse("problems:problem", args=[self.problem.id]))
        self.assertNotContains(resp, "/contests/None/")

    def test_appears_in_problemset(self):
        """A bare contest__start__lte filter would silently hide it."""
        resp = self.client.get(reverse("problems:problemset"))
        self.assertContains(resp, "Lecture Only Problem")

    def test_submit_page_opens(self):
        resp = self.client.get(
            reverse("runtests:submitproblem", args=[self.problem.id])
        )
        self.assertEqual(resp.status_code, 200)

    def test_appears_in_general_submit_list(self):
        resp = self.client.get(reverse("runtests:submit"))
        self.assertContains(resp, "Lecture Only Problem")

    def test_can_be_submitted_to(self):
        resp = self.client.post(
            reverse("runtests:submit_post"),
            {"problemid": self.problem.id, "lang": "python", "code": "print(1)"},
        )
        self.assertEqual(resp.status_code, 302)
        sub = Submission.objects.get(usr=self.user, problem=self.problem)
        self.assertIsNone(sub.contest)

    def test_solved_marker_works_without_a_contest(self):
        Submission.objects.create(
            usr=self.user,
            code="x",
            problem=self.problem,
            language="python",
            contest=None,
            verdict="Accepted",
        )
        resp = self.client.get(reverse("lectures:detail", args=[self.lecture_set.slug]))
        self.assertContains(resp, "Solved")

    def test_contestless_submission_is_absent_from_standings(self):
        """Practice must not leak into any contest's standings."""
        from ..contests.utils import get_standings

        contest = make_contest("Real Contest")
        contest_problem = make_problem(contest, "Contest Problem")
        Submission.objects.create(
            usr=self.user,
            code="x",
            problem=self.problem,
            language="python",
            contest=None,
            verdict="Accepted",
        )
        standings = get_standings(contest.id)
        self.assertEqual(standings["load"], [])
        self.assertEqual(contest_problem.contest, contest)


class SecretSubmitBypassTests(TestCase):
    """submit_post never checked `secret`; submit_view did. Now both do."""

    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        self.secret = make_problem(make_contest(), "Secret", secret=True)
        self.client.force_login(self.user)

    def test_post_to_secret_problem_is_rejected(self):
        resp = self.client.post(
            reverse("runtests:submit_post"),
            {"problemid": self.secret.id, "lang": "python", "code": "print(1)"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Submission.objects.filter(problem=self.secret).exists())
