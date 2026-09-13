from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from ..index.models import GraderUser
from .tasks import update_user_index


@override_settings(CURRENT_SEASON=2027)
class RankingsViewTests(TestCase):
    def create_user(self, username, display_name):
        # Set the division, not the rating: GraderUser's post_save signal
        # recomputes usaco_rating from usaco_division, so passing a rating here
        # is immediately overwritten with Bronze's 800 and the user then fails
        # rankings_view's `usaco > 800` filter.
        return GraderUser.objects.create_user(
            email=f"{username}@example.com",
            username=username,
            display_name=display_name,
            usaco_division=GraderUser.SILVER,
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


class IndexFormulaTests(TestCase):
    """The index must not depend on which code path last touched the user.

    update_user_index runs on every GraderUser save; the update_rankings command
    runs on demand. They previously disagreed for users with no in-house scores,
    so a user's rank silently changed when they edited their profile.
    """

    def make(self, username, division, cf, inhouses=None, writer=False):
        user = GraderUser.objects.create_user(
            email=f"{username}@example.com",
            username=username,
            display_name=username,
            usaco_division=division,
            cf_rating=cf,
            use_writer_formula=writer,
        )
        if inhouses is not None:
            GraderUser.objects.filter(pk=user.pk).update(inhouses=inhouses)
            user.refresh_from_db()
        return user

    @staticmethod
    def writer_index(usaco, cf):
        return Decimal("0.4") * min(Decimal(cf), Decimal(usaco)) + Decimal("0.6") * max(
            Decimal(cf), Decimal(usaco)
        )

    def test_no_inhouses_uses_writer_formula(self):
        """The regression: highest USACO + highest CF must not rank below peers."""
        user = self.make("2027zhang", GraderUser.PLATINUM, 2054)
        update_user_index(user.id)
        user.refresh_from_db()
        self.assertEqual(user.index, self.writer_index(1900, 2054))
        # The bug produced 0.2*0 + 0.35*1900 + 0.45*2054 = 1589.3
        self.assertNotEqual(user.index, Decimal("1589.300"))

    def test_writer_flag_uses_writer_formula(self):
        user = self.make("2027writer", GraderUser.GOLD, 1712, writer=True)
        update_user_index(user.id)
        user.refresh_from_db()
        self.assertEqual(user.index, self.writer_index(1600, 1712))

    def test_with_inhouses_uses_standard_formula(self):
        user = self.make("2027player", GraderUser.GOLD, 1400, inhouses=[Decimal("1500")])
        GraderUser.objects.filter(pk=user.pk).update(inhouse=Decimal("1500"))
        user.refresh_from_db()
        update_user_index(user.id)
        user.refresh_from_db()

        vals = sorted([Decimal("1600"), Decimal("1400"), Decimal("1500")])
        expected = (
            Decimal("0.2") * vals[0] + Decimal("0.35") * vals[1] + Decimal("0.45") * vals[2]
        )
        self.assertEqual(user.index, expected)

    def test_resaving_does_not_change_the_index(self):
        """A profile edit must not silently re-rank someone."""
        user = self.make("2027stable", GraderUser.PLATINUM, 2054)
        update_user_index(user.id)
        user.refresh_from_db()
        before = user.index

        user.display_name = "Renamed"
        user.save()
        update_user_index(user.id)
        user.refresh_from_db()
        self.assertEqual(user.index, before)
