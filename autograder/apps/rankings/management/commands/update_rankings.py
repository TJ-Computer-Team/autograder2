from decimal import Decimal
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.core.management.base import BaseCommand

from ....index.models import GraderUser
from ....contests.models import Contest
from ....contests.utils import get_standings
from ...formula import compute_index, usaco_rating_for
from ...models import RatingChange


class Command(BaseCommand):
    help = "Updates the user rankings based on contest performance and other metrics."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting user ranking update..."))

        # Load normal users
        users = GraderUser.objects.filter(is_tjioi=False, is_staff=False)

        # Initialize ranking data for each user
        rankings = [
            {
                "id": user.id,
                "name": user.display_name,
                "usaco": usaco_rating_for(user.usaco_division),
                "cf": user.cf_rating,
                "inhouses": [],
            }
            for user in users
        ]

        # Load all rated contests for current season
        contests = Contest.objects.filter(rated=True, season=settings.CURRENT_SEASON)

        # Compute inhouse scores for each contest
        for contest in contests:
            contest_standings = get_standings(contest.id)
            for i in range(len(rankings)):
                user = get_object_or_404(GraderUser, id=rankings[i]["id"])

                # Authors score their own contest at the writer formula rather
                # than taking a zero for not competing in it.
                if user in contest.writers.all():
                    rankings[i]["inhouses"].append(
                        compute_index(
                            rankings[i]["usaco"],
                            rankings[i]["cf"],
                            0,
                            has_inhouses=False,
                        )
                    )
                    continue

                # Check if user participated
                took = False
                for j, entry in enumerate(contest_standings["load"]):
                    if rankings[i]["id"] == entry["id"]:
                        score = 1200 * (len(contest_standings["load"]) - entry["rank"] + 1) / len(contest_standings["load"]) + 800
                        rankings[i]["inhouses"].append(score)
                        took = True
                        break

                # If user did not participate, score is 0
                if not took:
                    rankings[i]["inhouses"].append(0)

        # Compute inhouse averages and final index for each user
        for r in range(len(rankings)):
            # Remove None values from writer contests
            valid_scores = [float(x) for x in rankings[r]["inhouses"] if x is not None]
            valid_scores.sort()

            user = get_object_or_404(GraderUser, id=rankings[r]["id"])

            # Compute drops based on actual participated contests
            drops = max(0, min(2, len(valid_scores) - 2) + user.author_drops)

            # Compute overall inhouse score after drops
            overall = sum(valid_scores[drops:]) if len(valid_scores) > drops else 0
            if len(valid_scores) - drops > 0:
                overall /= (len(valid_scores) - drops)

            rankings[r]["inhouse"] = overall

            # Shared with the rankings page and update_user_index.
            rankings[r]["index"] = compute_index(
                rankings[r]["usaco"],
                rankings[r]["cf"],
                rankings[r]["inhouse"],
                use_writer_formula=user.use_writer_formula,
                has_inhouses=bool(valid_scores),
            )

        # Sort users by index descending and assign ranks
        rankings.sort(key=lambda x: x["index"], reverse=True)
        for i in range(len(rankings)):
            if i > 0 and rankings[i]["index"] == rankings[i - 1]["index"]:
                rankings[i]["rank"] = rankings[i - 1]["rank"]
            else:
                rankings[i]["rank"] = i + 1

        # Persist results to database
        for r in rankings:
            user = get_object_or_404(GraderUser, id=r["id"])
            RatingChange.objects.create(user=user, rating=r["index"])

            user.inhouses = r["inhouses"]
            user.inhouse = r["inhouse"]
            user.index = r["index"]
            user.rank = r["rank"]
            user.save()

        self.stdout.write(self.style.SUCCESS("Ranking update complete."))
