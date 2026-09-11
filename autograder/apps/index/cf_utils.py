import requests
import random
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

CF_LANGUAGES = [
    "GNU C++17",
    "Python 3",
    "Java 11",
    "PyPy 3",
    "GNU C++20 (64)"
]

def fetch_cf_problems():
    cached_problems = cache.get("cf_problems")
    if cached_problems:
        return cached_problems

    url = "https://codeforces.com/api/problemset.problems"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('status') == 'OK':
            problems = data['result']['problems']
            valid_problems = [
                p for p in problems 
                if p.get('type') == 'PROGRAMMING' 
                and 'interactive' not in [tag.lower() for tag in p.get('tags', [])]
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
    return prob['contestId'], prob['index'], random.choice(CF_LANGUAGES)

def verify_cf_submission(handle, contest_id, problem_index, language, issued_at):
    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=20"
    effective_start = issued_at - timedelta(minutes=2)
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('status') == 'OK':
            for sub in data['result']:
                creation_ts = sub.get('creationTimeSeconds')
                if creation_ts is None:
                    continue

                creation_time = datetime.fromtimestamp(creation_ts, tz=dt_timezone.utc)
                if creation_time < effective_start:
                    break

                problem = sub.get('problem') or {}
                if problem.get('contestId') != contest_id or problem.get('index') != problem_index:
                    continue

                verdict = sub.get('verdict')
                if verdict:
                    return True
    except Exception as e:
        logger.error(f"Error verifying CF submission for {handle}: {e}")

    return False
