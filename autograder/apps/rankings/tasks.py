import requests
import logging
import string
from ..index.models import GraderUser
from decimal import Decimal
from ...celery import app
from .formula import index_for_user

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

        # Recompute unconditionally. This used to sit inside the branch above, so
        # an index only ever refreshed when the Codeforces rating itself moved --
        # a changed USACO division, recomputed in-houses, or a corrected formula
        # would leave the stored index stale forever, because every later run saw
        # the rating already matching and returned without touching it.
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

    # Single source of truth, shared with the rankings page and the
    # update_rankings command; these had drifted into three separate copies.
    new_index = index_for_user(user)

    if user.index != new_index:
        user.index = new_index
        user.save(update_fields=["index"])
