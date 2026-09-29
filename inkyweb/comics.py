"""Random comic covers from the Comic Vine API.

Adapted from pimoroni/inky examples/spectra6/comics/comic.py, with the API key,
search queries and RANDOM_VOLUME taken from the web config instead of constants.
"""

import logging
import random
from io import BytesIO

import requests
from PIL import Image

from .errors import UserError

log = logging.getLogger(__name__)

BASE_URL = "https://comicvine.gamespot.com/api/"
HEADERS = {"User-Agent": "inky-web Comic Vine Client"}
TIMEOUT = 30


def find_volume(api_key, query, random_volume):
    params = {"api_key": api_key, "format": "json", "query": query, "resources": "volume", "limit": 5}
    r = requests.get(f"{BASE_URL}search/", headers=HEADERS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise UserError("no_volumes", "No volumes found for '{query}'", query=query)
    return random.choice(results) if random_volume else results[0]


def random_issue(api_key, volume_id):
    params = {"api_key": api_key, "format": "json", "filter": f"volume:{volume_id}", "limit": 100}
    r = requests.get(f"{BASE_URL}issues/", headers=HEADERS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise UserError("no_issues", "No issues found for volume {volume}", volume=volume_id)
    return random.choice(results)


def fetch_random_cover(comics_cfg):
    """Return (PIL image, detail dict) for a random cover matching the config."""
    api_key = comics_cfg.get("api_key", "").strip()
    queries = [q for q in comics_cfg.get("queries", []) if q.strip()]
    if not api_key:
        raise UserError("api_key_missing", "Comic Vine API key is not set")
    if not queries:
        raise UserError("no_queries", "No search queries configured")

    query = random.choice(queries)
    volume = find_volume(api_key, query, comics_cfg.get("random_volume", False))
    issue = random_issue(api_key, volume["id"])
    log.info("Comic: '%s' -> %s #%s", query, volume["name"], issue.get("issue_number"))

    r = requests.get(issue["image"]["original_url"], headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content))
    img.load()

    detail = {
        "query": query,
        "volume": volume["name"],
        "issue_number": issue.get("issue_number"),
        "url": issue.get("site_detail_url"),
    }
    return img, detail
