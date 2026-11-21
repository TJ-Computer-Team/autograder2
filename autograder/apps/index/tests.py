from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..lectures.models import LectureSet
from .models import GraderUser


class PotwViewTests(TestCase):
    """POTW was absorbed into Lecture Sets; /potw/ is now a redirect."""

    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="student@example.com", username="2027student", display_name="Student"
        )
        self.client.force_login(self.user)

    def test_redirects_to_newest_published_potw_set(self):
        LectureSet.objects.create(
            title="POTW Sep 1",
            slug="potw-sep-1",
            kind=LectureSet.POTW,
            published=True,
            date=timezone.localdate() - timedelta(days=7),
        )
        newest = LectureSet.objects.create(
            title="POTW Sep 8",
            slug="potw-sep-8",
            kind=LectureSet.POTW,
            published=True,
            date=timezone.localdate(),
        )

        resp = self.client.get(reverse("index:potw"))
        self.assertRedirects(resp, reverse("lectures:detail", args=[newest.slug]))

    def test_ignores_unpublished_potw_sets(self):
        LectureSet.objects.create(
            title="Draft POTW",
            slug="draft-potw",
            kind=LectureSet.POTW,
            published=False,
            date=timezone.localdate(),
        )
        resp = self.client.get(reverse("index:potw"))
        self.assertRedirects(resp, reverse("lectures:list"))

    def test_falls_back_to_list_when_none_exist(self):
        resp = self.client.get(reverse("index:potw"))
        self.assertRedirects(resp, reverse("lectures:list"))

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("index:potw"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/sets/", resp["Location"])
