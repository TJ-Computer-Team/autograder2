from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from ..index.models import GraderUser
from ..problems.models import Problem
from ..runtests.models import Submission
from .models import Contest
from .utils import get_contest_nav, get_standings


class GetContestNavTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=1)

        self.contest = Contest.objects.create(
            name="Open Contest", season=2027, start=start, end=end
        )
        self.tjioi_contest = Contest.objects.create(
            name="TJIOI Contest", season=2027, tjioi=True, start=start, end=end
        )

        self.user = GraderUser.objects.create_user(
            email="student@example.com", username="2027student", display_name="Student"
        )

    def _request(self, query, user=None):
        request = self.factory.get("/problems/1/", query)
        request.user = user or self.user
        return request

    def test_returns_contest_for_valid_param(self):
        request = self._request({"contest": self.contest.id})
        self.assertEqual(get_contest_nav(request, self.contest.id), self.contest)

    def test_returns_none_without_param(self):
        self.assertIsNone(get_contest_nav(self._request({})))

    def test_returns_none_for_non_numeric_param(self):
        self.assertIsNone(get_contest_nav(self._request({"contest": "abc"})))

    def test_returns_none_for_unknown_contest(self):
        request = self._request({"contest": self.contest.id + 999})
        self.assertIsNone(get_contest_nav(request))

    def test_rejects_mismatched_contest(self):
        """A hand-edited cid for a contest the problem isn't in is ignored."""
        request = self._request({"contest": self.tjioi_contest.id})
        self.assertIsNone(get_contest_nav(request, self.contest.id))

    def test_rejects_tjioi_contest_for_regular_user(self):
        request = self._request({"contest": self.tjioi_contest.id})
        self.assertIsNone(get_contest_nav(request, self.tjioi_contest.id))

    def test_allows_tjioi_contest_for_tjioi_user(self):
        self.user.is_tjioi = True
        request = self._request({"contest": self.tjioi_contest.id})
        self.assertEqual(
            get_contest_nav(request, self.tjioi_contest.id), self.tjioi_contest
        )

    def test_allows_tjioi_contest_for_staff(self):
        self.user.is_staff = True
        request = self._request({"contest": self.tjioi_contest.id})
        self.assertEqual(
            get_contest_nav(request, self.tjioi_contest.id), self.tjioi_contest
        )


class ContestNavbarTests(TestCase):
    """The contest navbar replaces the main one and survives the whole loop."""

    def setUp(self):
        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=1)

        self.contest = Contest.objects.create(
            name="Winter Inhouse", season=2027, start=start, end=end
        )
        self.other_contest = Contest.objects.create(
            name="Other Contest", season=2027, start=start, end=end
        )
        self.problem = Problem.objects.create(
            name="Cookie Cutter",
            contest=self.contest,
            points=100,
            contest_letter="A",
            statement="s",
            inputtxt="i",
            outputtxt="o",
            samples="x",
            tl=1000,
            ml=256,
        )
        self.user = GraderUser.objects.create_user(
            email="student@example.com", username="2027student", display_name="Student"
        )
        self.client.force_login(self.user)

    def assertContestNav(self, response):
        self.assertContains(response, "Winter Inhouse")
        self.assertContains(response, "Return Home")
        self.assertNotContains(response, "Rankings")

    def assertMainNav(self, response):
        self.assertContains(response, "Rankings")
        self.assertNotContains(response, "Return Home")

    def test_contest_page_replaces_main_navbar(self):
        response = self.client.get(reverse("contests:contest", args=[self.contest.id]))
        self.assertContestNav(response)

    def test_problem_keeps_navbar_when_entered_from_contest(self):
        response = self.client.get(
            reverse("problems:problem", args=[self.problem.id]),
            {"contest": self.contest.id},
        )
        self.assertContestNav(response)

    def test_problem_shows_main_navbar_from_problemset(self):
        response = self.client.get(reverse("problems:problem", args=[self.problem.id]))
        self.assertMainNav(response)

    def test_problem_ignores_mismatched_contest_param(self):
        response = self.client.get(
            reverse("problems:problem", args=[self.problem.id]),
            {"contest": self.other_contest.id},
        )
        self.assertMainNav(response)

    def test_submit_page_keeps_navbar(self):
        response = self.client.get(
            reverse("runtests:submitproblem", args=[self.problem.id]),
            {"contest": self.contest.id},
        )
        self.assertContestNav(response)

    def test_submission_page_keeps_navbar(self):
        submission = Submission.objects.create(
            usr=self.user,
            code="print(1)",
            problem=self.problem,
            language="python",
            contest=self.contest,
        )
        response = self.client.get(
            reverse("runtests:submission", args=[submission.id]),
            {"contest": self.contest.id},
        )
        self.assertContestNav(response)

    def test_submit_post_redirects_back_into_contest(self):
        response = self.client.post(
            reverse("runtests:submit_post"),
            {
                "problemid": self.problem.id,
                "lang": "python",
                "code": "print(1)",
                "contest": self.contest.id,
            },
        )
        self.assertRedirects(
            response,
            reverse(
                "contests:status",
                kwargs={"cid": self.contest.id, "mine_only": "mine", "page": 1},
            ),
            fetch_redirect_response=False,
        )

    def test_submit_post_without_contest_uses_global_status(self):
        response = self.client.post(
            reverse("runtests:submit_post"),
            {"problemid": self.problem.id, "lang": "python", "code": "print(1)"},
        )
        self.assertRedirects(
            response,
            reverse("runtests:status", kwargs={"page": 1}),
            fetch_redirect_response=False,
        )

    def test_submit_post_ignores_mismatched_contest(self):
        response = self.client.post(
            reverse("runtests:submit_post"),
            {
                "problemid": self.problem.id,
                "lang": "python",
                "code": "print(1)",
                "contest": self.other_contest.id,
            },
        )
        self.assertRedirects(
            response,
            reverse("runtests:status", kwargs={"page": 1}),
            fetch_redirect_response=False,
        )


@override_settings(CURRENT_SEASON=2027)
class ContestSeasonGroupingTests(TestCase):
    """Past seasons collapse so they don't bury the current one."""

    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        self.client.force_login(self.user)
        now = timezone.now()
        for season, count in ((2027, 2), (2026, 3), (2025, 1)):
            for i in range(count):
                Contest.objects.create(
                    name=f"IH{i} {season}",
                    season=season,
                    start=now - timedelta(days=(2028 - season) * 100 + i),
                    end=now - timedelta(days=(2028 - season) * 100 + i - 1),
                )

    def _groups(self):
        return self.client.get(reverse("contests:contests")).context["groups"]

    def test_grouped_newest_season_first(self):
        self.assertEqual([g["season"] for g in self._groups()], [2027, 2026, 2025])

    def test_only_the_current_season_is_expanded(self):
        groups = self._groups()
        self.assertTrue(groups[0]["is_current"])
        self.assertFalse(any(g["is_current"] for g in groups[1:]))

    def test_labels_span_two_years(self):
        self.assertEqual(self._groups()[0]["label"], "2026-2027")

    def test_every_contest_appears_exactly_once(self):
        groups = self._groups()
        total = sum(len(g["contests"]) for g in groups)
        self.assertEqual(total, Contest.objects.count())

    def test_past_seasons_render_as_collapsed_details(self):
        resp = self.client.get(reverse("contests:contests"))
        self.assertContains(resp, "2025-2026 Contests")
        self.assertContains(resp, "<details")

    def test_no_contests_is_handled(self):
        Contest.objects.all().delete()
        resp = self.client.get(reverse("contests:contests"))
        self.assertEqual(resp.context["groups"], [])
        self.assertContains(resp, "No contests yet")


class ContestVisibilityTests(TestCase):
    """Admins left off visible_to are treated as participants until it ends."""

    def setUp(self):
        self.factory = RequestFactory()
        now = timezone.now()
        self.upcoming = Contest.objects.create(
            name="Secret Upcoming",
            season=2027,
            start=now + timedelta(days=1),
            end=now + timedelta(days=2),
        )
        self.running = Contest.objects.create(
            name="Running", season=2027, start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        self.tester = GraderUser.objects.create_user(
            email="t@example.com", username="2027tester", display_name="Tester",
            is_staff=True,
        )
        self.outsider = GraderUser.objects.create_user(
            email="o@example.com", username="2027outsider", display_name="Outsider",
            is_staff=True,
        )
        for contest in (self.upcoming, self.running):
            contest.visible_to.add(self.tester)
        self.problem = self._problem(self.upcoming, "Leaky Problem")
        self.running_problem = self._problem(self.running, "Running Problem")

    def _problem(self, contest, name):
        return Problem.objects.create(
            name=name, contest=contest, points=100, contest_letter="A",
            statement="s", inputtxt="i", outputtxt="o", samples="x", tl=1000, ml=256,
        )

    def test_is_admin_for(self):
        self.assertTrue(self.upcoming.is_admin_for(self.tester))
        self.assertFalse(self.upcoming.is_admin_for(self.outsider))

    def test_every_admin_regains_access_once_it_ends(self):
        self.upcoming.end = timezone.now() - timedelta(minutes=1)
        self.upcoming.save()
        self.assertTrue(self.upcoming.is_admin_for(self.outsider))

    def test_contest_list_hides_unstarted_contest_from_outsider(self):
        self.client.force_login(self.outsider)
        names = [
            c.name
            for g in self.client.get(reverse("contests:contests")).context["groups"]
            for c in g["contests"]
        ]
        self.assertNotIn("Secret Upcoming", names)
        self.assertIn("Running", names)

    def test_contest_list_shows_unstarted_contest_to_tester(self):
        self.client.force_login(self.tester)
        self.assertContains(self.client.get(reverse("contests:contests")), "Secret Upcoming")

    def test_outsider_cannot_open_unstarted_contest_or_problem(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(reverse("contests:contest", args=[self.upcoming.id]))
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(reverse("problems:problem", args=[self.problem.id]))
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse("problems:problemset"))
        self.assertNotContains(resp, "Leaky Problem")

    def test_tester_can_open_unstarted_problem(self):
        self.client.force_login(self.tester)
        resp = self.client.get(reverse("problems:problem", args=[self.problem.id]))
        self.assertEqual(resp.status_code, 200)

    def test_outsider_cannot_read_tester_submission(self):
        sub = Submission.objects.create(
            usr=self.tester, code="secret code", problem=self.problem,
            language="python", contest=self.upcoming,
        )
        self.client.force_login(self.outsider)
        resp = self.client.get(reverse("runtests:submission", args=[sub.id]))
        self.assertNotContains(resp, "secret code")

    def test_outsider_is_ranked_and_tester_is_not(self):
        for usr in (self.tester, self.outsider):
            Submission.objects.create(
                usr=usr, code="x", problem=self.running_problem, language="python",
                contest=self.running, verdict="Accepted",
            )
        names = [row["name"] for row in get_standings(self.running.id)["load"]]
        self.assertEqual(names, ["Outsider"])

    def _admin_request(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_admin_site_hides_contest_and_its_problems_and_submissions(self):
        from django.contrib import admin as django_admin

        Submission.objects.create(
            usr=self.tester, code="x", problem=self.problem, language="python",
            contest=self.upcoming,
        )
        site = django_admin.site
        for model, hidden in (
            (Contest, {"contest": self.upcoming}),
            (Problem, {"problem": self.problem}),
            (Submission, {"submission": Submission.objects.get()}),
        ):
            obj = next(iter(hidden.values()))
            model_admin = site._registry[model]
            outsider_qs = model_admin.get_queryset(self._admin_request(self.outsider))
            tester_qs = model_admin.get_queryset(self._admin_request(self.tester))
            self.assertNotIn(obj, outsider_qs)
            self.assertIn(obj, tester_qs)

    def test_contest_form_requires_visible_to(self):
        from .admin import ContestAdminForm

        data = {
            "name": "New", "season": 2027,
            "start": "2027-01-01 10:00", "end": "2027-01-01 12:00",
            "writers": [self.tester.pk],
        }
        form = ContestAdminForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("visible_to", form.errors)

        form = ContestAdminForm(data={**data, "visible_to": [self.tester.pk]})
        self.assertTrue(form.is_valid(), form.errors)

    def test_contest_form_only_offers_admins(self):
        from .admin import ContestAdminForm

        student = GraderUser.objects.create_user(
            email="s@example.com", username="2027s", display_name="Student"
        )
        choices = ContestAdminForm().fields["visible_to"].queryset
        self.assertNotIn(student, choices)
        self.assertIn(self.outsider, choices)
