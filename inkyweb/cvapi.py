"""Comic Vine API client with request accounting.

Comic Vine officially supports 200 requests per resource per hour and
temporarily blocks bursts of requests per second. Every API call goes
through request(), which:
  - spaces calls at least MIN_SPACING seconds apart,
  - counts calls per resource over the last hour (persisted, so a restart
    doesn't reset the count),
  - refuses to call once the configured hourly budget is used up.
"""

import json
import logging
import threading
import time

import requests

from . import config
from .errors import UserError

log = logging.getLogger(__name__)

BASE_URL = "https://comicvine.gamespot.com/api"
HEADERS = {"User-Agent": "inky-web Comic Vine Client"}
TIMEOUT = 30
MIN_SPACING = 1.0  # seconds between calls
WINDOW = 3600  # the official limit is per hour
OFFICIAL_LIMIT = 200
RESOURCES = ("search", "volumes", "issues")
USAGE_FILE = config.DATA_DIR / "api_usage.json"

_lock = threading.Lock()
_last_call = 0.0


def _load_usage():
    try:
        return json.loads(USAGE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _recent(stamps, now):
    return [t for t in stamps if now - t < WINDOW]


def usage():
    """Calls made per resource during the last hour."""
    with _lock:
        now = time.time()
        u = _load_usage()
        return {r: len(_recent(u.get(r, []), now)) for r in RESOURCES}


def request(resource, api_key, params, budget):
    """Call a Comic Vine list resource and return the decoded JSON."""
    global _last_call
    with _lock:
        now = time.time()
        u = _load_usage()
        calls = _recent(u.get(resource, []), now)
        if len(calls) >= budget:
            raise UserError(
                "rate_limited",
                "Comic Vine hourly budget reached for {resource} ({limit} calls); try again later",
                status=429,
                resource=resource,
                limit=budget,
            )
        wait = MIN_SPACING - (now - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        calls.append(_last_call)
        u[resource] = calls
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(u))

    log.info("Comic Vine %s %s", resource, {k: v for k, v in params.items() if k != "field_list"})
    r = requests.get(
        f"{BASE_URL}/{resource}/",
        headers=HEADERS,
        params={"api_key": api_key, "format": "json", **params},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status_code") != 1:
        raise UserError("cv_error", "Comic Vine: {detail}", detail=data.get("error") or "unknown error")
    return data


def curl(resource, params):
    """The equivalent curl command, with the API key left as a placeholder."""
    lines = [
        f'curl -s -G "{BASE_URL}/{resource}/"',
        f'  -H "User-Agent: {HEADERS["User-Agent"]}"',
        '  --data-urlencode "api_key=TU_API_KEY"',
        '  --data-urlencode "format=json"',
    ]
    for k, v in params.items():
        lines.append(f'  --data-urlencode "{k}={v}"'.replace("\n", " "))
    return " \\\n".join(lines)


def download(url):
    """Fetch a cover image (not an API resource, so not counted)."""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content

