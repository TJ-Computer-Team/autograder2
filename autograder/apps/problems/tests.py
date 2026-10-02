import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Problem, renumber_problems


def make_problem(name):
    return Problem.objects.create(
        name=name,
        points=100,
        statement="",
        inputtxt="",
        outputtxt="",
        samples="",
    )


# Saving a problem writes its testcase folder to the coderunner filesystem.
@mock.patch("autograder.apps.problems.signals.add_problem_to_coderunner")
@mock.patch("autograder.apps.problems.signals.add_tests_to_coderunner")
class ProblemNumberTests(TestCase):
    def numbers(self):
        return list(Problem.objects.order_by("-number").values_list("name", "number"))

    def test_new_problems_go_on_top(self, *_):
        for name in "abc":
            make_problem(name)
        self.assertEqual(self.numbers(), [("c", 3), ("b", 2), ("a", 1)])

    def test_reorder_permutes_numbers(self, *_):
        a, b, c = (make_problem(n) for n in "abc")
        renumber_problems([a.pk, c.pk, b.pk])
        self.assertEqual(self.numbers(), [("a", 3), ("c", 2), ("b", 1)])

    def test_reorder_subset_keeps_numbers_dense(self, *_):
        a, b, c, d = (make_problem(n) for n in "abcd")
        # Only b and d on screen (e.g. a filtered page): they swap 4 and 2.
        renumber_problems([b.pk, d.pk])
        self.assertEqual(self.numbers(), [("b", 4), ("c", 3), ("d", 2), ("a", 1)])

    def test_reorder_rejects_unknown_ids(self, *_):
        a = make_problem("a")
        with self.assertRaises(ValueError):
            renumber_problems([a.pk, a.pk + 999])

    def test_delete_closes_gap(self, *_):
        a, b, c = (make_problem(n) for n in "abc")
        b.delete()
        self.assertEqual(self.numbers(), [("c", 2), ("a", 1)])

    def test_bulk_delete_closes_gaps(self, *_):
        problems = [make_problem(n) for n in "abcde"]
        Problem.objects.filter(pk__in=[problems[1].pk, problems[3].pk]).delete()
        self.assertEqual(self.numbers(), [("e", 3), ("c", 2), ("a", 1)])

    def test_admin_reorder_endpoint(self, *_):
        a, b = make_problem("a"), make_problem("b")
        admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pw"
        )
        self.client.force_login(admin)
        resp = self.client.post(
            reverse("admin:problems_problem_reorder"),
            json.dumps({"order": [a.pk, b.pk]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.numbers(), [("a", 2), ("b", 1)])

    def test_admin_changelist_renders_handles(self, *_):
        a = make_problem("a")
        admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pw"
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse("admin:problems_problem_changelist"))
        self.assertContains(resp, f'data-pk="{a.pk}"')
        self.assertContains(resp, reverse("admin:problems_problem_reorder"))
