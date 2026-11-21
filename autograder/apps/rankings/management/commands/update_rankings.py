from django.core.management.base import BaseCommand

from ....index.models import GraderUser
from ....contests.utils import get_standings
from ...formula import (
    SeasonContests,
    finished_rated_contests,
    index_for_user,
    inhouse_contest_score,
    inhouse_score,
)
from ...models import RatingChange


class Command(BaseCommand):
    help = "Updates the user rankings based on contest performance and other metrics."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting user ranking update..."))

        users = list(GraderUser.objects.filter(is_tjioi=False, is_staff=False))
        taken = {user.id: [] for user in users}

        # Only rated contests this season that have finished. One still scheduled
        # or running has no final standings, and must not look skipped.
        contests = finished_rated_contests().prefetch_related("writers")
        season = SeasonContests.load(contests)

        # Collect the score of every in-house each user took. A contest someone
        # wrote is left out entirely, even if they show up on its standings, and
        # one they skipped simply adds nothing.
        for contest in contests:
            writer_ids = {w.id for w in contest.writers.all()}
            standings = get_standings(contest.id)["load"]
            for entry in standings:
                if entry["id"] in taken and entry["id"] not in writer_ids:
                    taken[entry["id"]].append(
                        inhouse_contest_score(entry["rank"], len(standings))
                    )

        for user in users:
            user.inhouses = taken[user.id]
            user.inhouse = inhouse_score(user.inhouses)
            # Shared with the rankings page and update_user_index, which decides
            # between the writer and standard formula.
            user.index = index_for_user(user, season)

            RatingChange.objects.create(user=user, rating=user.index)
            user.save()

        self.stdout.write(self.style.SUCCESS("Ranking update complete."))
