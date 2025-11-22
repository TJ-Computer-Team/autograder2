from decimal import Decimal
from django.conf import settings
from django.shortcuts import get_object_or_404
from ....index.models import GraderUser
from ....contests.models import Contest
from ....contests.utils import get_standings
from ...models import RatingChange
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Updates the user rankings based on contest performance and other metrics."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting user ranking update..."))
        users = GraderUser.objects.filter(is_tjioi=False, is_staff=False)

        usaco_map = {
            "Not Participated": 800,
            "Bronze": 800,
            "Silver": 1200,
            "Gold": 1600,
            "Platinum": 1900,
        }

        rankings = [
            {
                "id": user.id,
                "name": user.display_name,
                "usaco": usaco_map[user.usaco_division],
                "cf": user.cf_rating,
                "inhouses": [],
            }
            for user in users
        ]

        contests = Contest.objects.filter(rated=True, season=settings.CURRENT_SEASON)

        for contest in contests:
            contest_standings = get_standings(contest.id)
            for i in range(len(rankings)):
                took = False
                for j in range(len(contest_standings["load"])):
                    if rankings[i]["id"] == contest_standings["load"][j]["id"]:
                        rankings[i]["inhouses"].append(
                            1200
                            * (
                                len(contest_standings["load"])
                                - contest_standings["load"][j]["rank"]
                                + 1
                            )
                            / len(contest_standings["load"])
                            + 800
                        )

                        took = True
                        break

                if not took:
                    rankings[i]["inhouses"].append(0)

        for r in range(len(rankings)):
            rankings[r]["inhouses"].sort()

            user = get_object_or_404(GraderUser, id=rankings[r]["id"])
            drops = max(
                0,
                min(2, contests.count() - 2) + user.author_drops,
            )

            overall = 0
            for j in range(drops, contests.count()):
                overall += rankings[r]["inhouses"][j]

            if contests.count() > 0 and contests.count() - drops > 0:
                overall /= contests.count() - drops

            rankings[r]["inhouse"] = overall

            # Use writer formula if enabled: 0.4 * min(cf, usaco) + 0.6 * max(cf, usaco)
            # Otherwise use standard formula: 0.2 * min + 0.35 * mid + 0.45 * max
            if user.use_writer_formula:
                cf_rating = Decimal(str(rankings[r]["cf"]))
                usaco_rating = Decimal(str(rankings[r]["usaco"]))
                rankings[r]["index"] = (
                    Decimal("0.4") * min(cf_rating, usaco_rating)
                    + Decimal("0.6") * max(cf_rating, usaco_rating)
                )
            else:
                vals = [rankings[r]["usaco"], rankings[r]["cf"], rankings[r]["inhouse"]]
                vals.sort()
                rankings[r]["index"] = (
                    Decimal("0.2") * Decimal(str(vals[0]))
                    + Decimal("0.35") * Decimal(str(vals[1]))
                    + Decimal("0.45") * Decimal(str(vals[2]))
                )

        rankings.sort(key=lambda x: x["index"], reverse=True)

        for i in range(len(rankings)):
            if i > 0 and rankings[i]["index"] == rankings[i - 1]["index"]:
                rankings[i]["rank"] = rankings[i - 1]["rank"]
            else:
                rankings[i]["rank"] = i + 1

        for r in rankings:
            user = get_object_or_404(GraderUser, id=r["id"])
            RatingChange.objects.create(user=user, rating=r["index"])

            user.inhouses = r["inhouses"]
            user.inhouse = r["inhouse"]
            user.index = r["index"]
            user.rank = r["rank"]
            user.save()

        self.stdout.write(self.style.SUCCESS("Ranking update complete."))
