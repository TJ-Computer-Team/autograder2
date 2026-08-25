from django.test import TestCase, override_settings
from django.urls import reverse

from ..index.models import GraderUser


@override_settings(CURRENT_SEASON=2027)
class RankingsViewTests(TestCase):
    def create_user(self, username, display_name):
        return GraderUser.objects.create_user(
            email=f"{username}@example.com",
            username=username,
            display_name=display_name,
            usaco_rating=1200,
        )

    def test_only_users_graduating_within_four_seasons_are_shown(self):
        viewer = self.create_user("2027viewer", "Current year")
        self.create_user("2028student", "Next year")
        self.create_user("2029student", "Two years out")
        self.create_user("2030student", "Three years out")
        self.create_user("2026student", "Past graduate")
        self.create_user("2031student", "Four years out")

        self.client.force_login(viewer)
        response = self.client.get(reverse("rankings:rankings", args=[2027]))

        self.assertEqual(response.status_code, 200)
        names = [ranking["name"] for ranking in response.context["rankings"]]
        self.assertCountEqual(
            names,
            ["Current year", "Next year", "Two years out", "Three years out"],
        )
