import requests
import logging
import string
from ..index.models import GraderUser
from decimal import Decimal
from ...celery import app

logger = logging.getLogger(__name__)


@app.task(rate_limit="2/s")
def update_codeforces_rating(user_id):
    user = GraderUser.objects.get(id=user_id)
    if not user.cf_handle:
        update_user_index.delay(user.id)
        return

    handle = str(user.cf_handle)

    if not all(c in string.ascii_letters + string.digits + "_." for c in handle):
        logger.warning(f"Invalid Codeforces handle: {handle}")
        update_user_index.delay(user.id)
        return

    url = f"https://codeforces.com/api/user.info?handles={handle}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Codeforces API: {e}")
        update_user_index.delay(user.id)
        return

    data = response.json()
    if data["status"] == "OK":
        max_rating = data["result"][0].get("maxRating", 0)
        logger.info(
            f"Fetched cf rating of {max_rating} from handle {handle} for user {user.username}"
        )

        if user.cf_rating != max_rating:
            user.cf_rating = max_rating
            user.save(update_fields=["cf_rating"])
            update_user_index.delay(user.id)
    else:
        logger.error(
            f"Codeforces API error for handle {handle}: {data.get('comment', 'No comment')}"
        )


@app.task
def update_user_index(user_id):
    try:
        user = GraderUser.objects.get(id=user_id)
    except GraderUser.DoesNotExist:
        logger.error(f"User with ID {user_id} not found.")
        return

    usaco_map = {
        "Not Participated": 800,
        "Bronze": 800,
        "Silver": 1200,
        "Gold": 1600,
        "Platinum": 1900,
    }

    new_usaco_rating = usaco_map.get(user.usaco_division, 800)

    # Use writer formula if enabled: 0.4 * min(cf, usaco) + 0.6 * max(cf, usaco)
    # Otherwise use standard formula: 0.2 * min + 0.35 * mid + 0.45 * max
    if user.use_writer_formula:
        cf_rating = Decimal(str(user.cf_rating))
        usaco_rating = Decimal(str(new_usaco_rating))
        new_index = (
            Decimal("0.4") * min(cf_rating, usaco_rating)
            + Decimal("0.6") * max(cf_rating, usaco_rating)
        )
    else:
        vals = sorted(
            [
                Decimal(str(new_usaco_rating)),
                Decimal(str(user.cf_rating)),
                Decimal(str(user.inhouse)),
            ]
        )
        new_index = (
            Decimal("0.2") * vals[0] + Decimal("0.35") * vals[1] + Decimal("0.45") * vals[2]
        )

    if user.index != new_index:
        user.index = new_index
        user.save(update_fields=["index"])
