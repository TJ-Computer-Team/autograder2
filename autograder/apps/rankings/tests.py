from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from ..index.models import GraderUser
from .formula import compute_index, index_for_user
from .tasks import update_codeforces_rating, update_user_index


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
        user = self.make(
            "2027player", GraderUser.GOLD, 1400, inhouses=[Decimal("1500")]
        )
        GraderUser.objects.filter(pk=user.pk).update(inhouse=Decimal("1500"))
        user.refresh_from_db()
        update_user_index(user.id)
        user.refresh_from_db()

        vals = sorted([Decimal("1600"), Decimal("1400"), Decimal("1500")])
        expected = (
            Decimal("0.2") * vals[0]
            + Decimal("0.35") * vals[1]
            + Decimal("0.45") * vals[2]
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


class CodeforcesRefreshTests(TestCase):
    """update_codeforces_rating must always leave the index consistent.

    It used to recompute the index only when the CF rating changed, so a stale
    index -- from an edited USACO division, recomputed in-houses, or a corrected
    formula -- was never repaired.
    """

    def make(self, cf=1610, division=GraderUser.GOLD):
        return GraderUser.objects.create_user(
            email="zain@example.com",
            username="2028zmarshal",
            display_name="Zain",
            usaco_division=division,
            cf_rating=cf,
            cf_handle="zen10",
        )

    def _cf_response(self, max_rating):
        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"status": "OK", "result": [{"maxRating": max_rating}]}

        return Resp()

    @patch("autograder.apps.rankings.tasks.update_user_index")
    @patch("autograder.apps.rankings.tasks.requests.get")
    def test_recomputes_even_when_rating_is_unchanged(self, get, index_task):
        user = self.make(cf=1669)
        get.return_value = self._cf_response(1669)

        update_codeforces_rating(user.id)

        index_task.delay.assert_called_once_with(user.id)

    @patch("autograder.apps.rankings.tasks.update_user_index")
    @patch("autograder.apps.rankings.tasks.requests.get")
    def test_recomputes_when_rating_changes(self, get, index_task):
        user = self.make(cf=1610)
        get.return_value = self._cf_response(1669)

        update_codeforces_rating(user.id)

        user.refresh_from_db()
        self.assertEqual(user.cf_rating, 1669)
        index_task.delay.assert_called_once_with(user.id)

    @patch("autograder.apps.rankings.tasks.requests.get")
    def test_index_follows_a_rating_rise(self, get):
        """End to end: the stored index must track the new rating."""
        user = self.make(cf=1610)
        update_user_index(user.id)
        user.refresh_from_db()
        # writer formula, no in-houses: 0.4*1600 + 0.6*1610
        self.assertEqual(user.index, Decimal("1606.000"))

        get.return_value = self._cf_response(1669)
        update_codeforces_rating(user.id)
        update_user_index(user.id)
        user.refresh_from_db()
        # 0.4*1600 + 0.6*1669
        self.assertEqual(user.index, Decimal("1641.400"))


class IndexIsDerivedOnReadTests(TestCase):
    """The rankings page must never show an index that contradicts its own columns.

    The index used to be read from a stored column that three different code paths
    wrote to. A gap between them left a value that disagreed with the USACO /
    Codeforces / in-house numbers displayed next to it, and nothing ever noticed.
    """

    @override_settings(CURRENT_SEASON=2027)
    def test_page_ignores_a_stale_stored_index(self):
        user = GraderUser.objects.create_user(
            email="zain@example.com",
            username="2028zmarshal",
            display_name="Zain",
            usaco_division=GraderUser.GOLD,
            cf_rating=1669,
        )
        # Exactly the reported bug: stored index left over from cf=1610.
        GraderUser.objects.filter(pk=user.pk).update(index=Decimal("1606.000"))

        viewer = GraderUser.objects.create_user(
            email="v@example.com", username="2027viewer", display_name="V"
        )
        self.client.force_login(viewer)
        resp = self.client.get(reverse("rankings:rankings", args=[2027]))

        row = next(r for r in resp.context["rankings"] if r["name"] == "Zain")
        # 0.4*1600 + 0.6*1669
        self.assertEqual(row["index"], Decimal("1641.400"))
        self.assertNotEqual(row["index"], Decimal("1606.000"))

    @override_settings(CURRENT_SEASON=2027)
    def test_displayed_index_always_follows_the_displayed_columns(self):
        for division, cf in (
            (GraderUser.PLATINUM, 2054),
            (GraderUser.GOLD, 1669),
            (GraderUser.SILVER, 900),
            (GraderUser.BRONZE, 0),
        ):
            GraderUser.objects.all().delete()
            user = GraderUser.objects.create_user(
                email=f"u{cf}@example.com",
                username=f"2028u{cf}",
                display_name=f"U{cf}",
                usaco_division=division,
                cf_rating=cf,
            )
            GraderUser.objects.filter(pk=user.pk).update(index=Decimal("1"))
            viewer = GraderUser.objects.create_user(
                email="v@example.com", username="2027viewer", display_name="V"
            )
            self.client.force_login(viewer)
            resp = self.client.get(reverse("rankings:rankings", args=[2027]))
            row = next(
                (r for r in resp.context["rankings"] if r["name"] == f"U{cf}"), None
            )
            if row is None:
                continue  # filtered out for having nothing to rank on
            expected = compute_index(
                row["usaco"], row["cf"], row["inhouse"], has_inhouses=False
            )
            self.assertEqual(row["index"], expected, f"{division} / {cf}")


class FormulaAgreementTests(TestCase):
    """All three paths must agree. They previously did not."""

    def test_task_and_page_agree(self):
        user = GraderUser.objects.create_user(
            email="a@example.com",
            username="2028agree",
            display_name="A",
            usaco_division=GraderUser.PLATINUM,
            cf_rating=2054,
        )
        update_user_index(user.id)
        user.refresh_from_db()
        self.assertEqual(user.index, index_for_user(user))

    def test_no_inhouses_uses_writer_in_both(self):
        user = GraderUser.objects.create_user(
            email="b@example.com",
            username="2028nohouse",
            display_name="B",
            usaco_division=GraderUser.GOLD,
            cf_rating=1669,
        )
        self.assertEqual(index_for_user(user), Decimal("1641.400"))

    def test_with_inhouses_uses_standard_in_both(self):
        user = GraderUser.objects.create_user(
            email="c@example.com",
            username="2028house",
            display_name="C",
            usaco_division=GraderUser.GOLD,
            cf_rating=1400,
        )
        GraderUser.objects.filter(pk=user.pk).update(
            inhouses=[Decimal("1500")], inhouse=Decimal("1500")
        )
        user.refresh_from_db()
        vals = sorted([Decimal("1600"), Decimal("1400"), Decimal("1500")])
        expected = (
            Decimal("0.2") * vals[0]
            + Decimal("0.35") * vals[1]
            + Decimal("0.45") * vals[2]
        )
        self.assertEqual(index_for_user(user), expected)


class SignalLoopTests(TestCase):
    """Saves made *by* the ranking tasks must not re-queue those tasks.

    update_codeforces_rating calls update_user_index, which writes user.index,
    which fired post_save, which queued update_codeforces_rating again. Each lap
    cost a Codeforces call throttled to 2/s, and the default queue backed up to
    hundreds of tasks -- starving unrelated work like starting a duel.
    """

    def setUp(self):
        self.user = GraderUser.objects.create_user(
            email="loop@example.com",
            username="2028loop",
            display_name="Loop",
            usaco_division=GraderUser.GOLD,
            cf_rating=1500,
        )

    @patch("autograder.apps.index.signals.update_codeforces_rating")
    def test_index_only_save_does_not_requeue(self, task):
        self.user.index = Decimal("1234.000")
        self.user.save(update_fields=["index"])
        task.delay.assert_not_called()

    @patch("autograder.apps.index.signals.update_codeforces_rating")
    def test_cf_rating_only_save_does_not_requeue(self, task):
        self.user.cf_rating = 1600
        self.user.save(update_fields=["cf_rating"])
        task.delay.assert_not_called()

    @patch("autograder.apps.index.signals.update_codeforces_rating")
    def test_inhouse_only_save_does_not_requeue(self, task):
        self.user.inhouse = Decimal("1500")
        self.user.save(update_fields=["inhouse"])
        task.delay.assert_not_called()

    @patch("autograder.apps.index.signals.update_codeforces_rating")
    def test_a_real_profile_edit_still_refreshes(self, task):
        self.user.display_name = "Renamed"
        self.user.save()
        task.delay.assert_called_once_with(self.user.id)

    @patch("autograder.apps.index.signals.update_codeforces_rating")
    def test_editing_a_handle_still_refreshes(self, task):
        self.user.cf_handle = "somebody"
        self.user.save(update_fields=["cf_handle"])
        task.delay.assert_called_once_with(self.user.id)

    @patch("autograder.apps.index.signals.update_codeforces_rating")
    def test_update_user_index_does_not_requeue(self, task):
        """The full path: running the index task must not feed itself."""
        update_user_index(self.user.id)
        task.delay.assert_not_called()
