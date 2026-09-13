import requests
import random
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

CF_LANGUAGES = ["GNU C++17", "Python 3", "Java 11", "PyPy 3", "GNU C++20 (64)"]


def fetch_cf_problems():
    cached_problems = cache.get("cf_problems")
    if cached_problems:
        return cached_problems

    url = "https://codeforces.com/api/problemset.problems"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("status") == "OK":
            problems = data["result"]["problems"]
            valid_problems = [
                p
                for p in problems
                if p.get("type") == "PROGRAMMING"
                and "interactive" not in [tag.lower() for tag in p.get("tags", [])]
            ]
            if valid_problems:
                cache.set("cf_problems", valid_problems, 86400)
                return valid_problems
    except Exception as e:
        logger.error(f"Error fetching CF problems: {e}")

    return []


def pick_random_challenge(problems=None):
    if not problems:
        problems = fetch_cf_problems()

    if not problems:
        return 4, "A", random.choice(CF_LANGUAGES)

    prob = random.choice(problems)
    return prob["contestId"], prob["index"], random.choice(CF_LANGUAGES)


def verify_cf_submission(handle, contest_id, problem_index, language, issued_at):
    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=20"
    effective_start = issued_at - timedelta(minutes=2)
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("status") == "OK":
            for sub in data["result"]:
                creation_ts = sub.get("creationTimeSeconds")
                if creation_ts is None:
                    continue

                creation_time = datetime.fromtimestamp(creation_ts, tz=dt_timezone.utc)
                if creation_time < effective_start:
                    break

                problem = sub.get("problem") or {}
                if (
                    problem.get("contestId") != contest_id
                    or problem.get("index") != problem_index
                ):
                    continue

                verdict = sub.get("verdict")
                if verdict:
                    return True
    except Exception as e:
        logger.error(f"Error verifying CF submission for {handle}: {e}")

    return False


# --- Duel helpers -----------------------------------------------------------
#
# verify_cf_submission above answers "did this handle submit at all", which is what
# handle verification needs (it looks for a deliberate compilation error). Duels
# need a stricter question -- "was it accepted, and when" -- so these live
# alongside it rather than changing its behaviour.

SOLVED_SET_TTL = 600  # 10 min; a tournament reuses a player's set across duels
CF_API_TIMEOUT = 15


def fetch_solved_set(handle, force=False):
    """{(contestId, index)} the handle has ever had accepted, or None on failure.

    Returning None rather than an empty set matters: an empty set would look like
    "has solved nothing" and let a duel pick a problem they have already solved.
    Callers must treat None as "could not determine" and refuse to start.
    """
    if not handle:
        return None

    key = f"cf_solved:{handle.lower()}"
    if not force:
        cached = cache.get(key)
        if cached is not None:
            return cached

    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=10000"
    try:
        resp = requests.get(url, timeout=CF_API_TIMEOUT)
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"CF history fetch failed for {handle}: {e}")
        return None

    if data.get("status") != "OK":
        logger.error(f"CF history rejected for {handle}: {data.get('comment')}")
        return None

    solved = {
        (sub["problem"].get("contestId"), sub["problem"].get("index"))
        for sub in data["result"]
        if sub.get("verdict") == "OK" and sub.get("problem")
    }
    cache.set(key, solved, SOLVED_SET_TTL)
    return solved


def fetch_recent_submissions(handle, contest_id, problem_index, since, count=20):
    """Submissions by `handle` to one problem at or after `since`, newest first.

    Each item is (cf_submission_id, verdict, created_at). `verdict` is None while
    Codeforces is still judging, which the duel view surfaces as "running".
    """
    if not handle:
        return []

    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count={count}"
    try:
        resp = requests.get(url, timeout=CF_API_TIMEOUT)
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"CF poll failed for {handle}: {e}")
        return []

    if data.get("status") != "OK":
        logger.error(f"CF poll rejected for {handle}: {data.get('comment')}")
        return []

    found = []
    for sub in data["result"]:
        ts = sub.get("creationTimeSeconds")
        if ts is None:
            continue
        created = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
        # Results are newest-first, so once we're before the window we're done.
        if created < since:
            break
        problem = sub.get("problem") or {}
        if (
            problem.get("contestId") != contest_id
            or problem.get("index") != problem_index
        ):
            continue
        found.append((sub.get("id"), sub.get("verdict"), created))
    return found


def find_cf_accepted(handle, contest_id, problem_index, since):
    """When `handle` first solved the problem at or after `since`, else None.

    `since` is the duel start. Anything accepted before it -- including a solve
    from months ago -- is ignored, which is what stops a player pasting an old
    accepted solution the moment the problem is revealed.
    """
    accepted = [
        created
        for _id, verdict, created in fetch_recent_submissions(
            handle, contest_id, problem_index, since
        )
        if verdict == "OK"
    ]
    return min(accepted) if accepted else None
