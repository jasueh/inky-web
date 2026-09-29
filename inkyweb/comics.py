"""Random comic covers from the Comic Vine API.

Each configured search is either:

- simple: the behaviour of pimoroni/inky examples/spectra6/comics/comic.py —
  /search/ for 5 volumes, take the first (or a random one), then a random
  issue among the volume's first 100;
- advanced: candidates come from /search/, /volumes/ or /issues/ with
  configurable paging, Comic Vine filter and sort, are filtered in the app
  (publisher, start year, issue count, excluded words, optional jq
  expression) and cached on disk. For volume sources the issue is then
  picked among all of the volume's issues (optionally within a cover date
  range); with /issues/ the candidates already are issues.
"""

import hashlib
import json
import logging
import random
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from io import BytesIO

from PIL import Image

from . import config, cvapi
from .errors import UserError

log = logging.getLogger(__name__)

SIMPLE_LIMIT = 5
MAX_PAGES = 10
PAGE_MAX = {"search": 10, "volumes": 100, "issues": 100}  # per-call maximum of each resource
VOLUME_FIELDS = "id,name,start_year,publisher,count_of_issues,site_detail_url"
ISSUE_FIELDS = "id,issue_number,name,cover_date,image,site_detail_url"
ISSUE_LIST_FIELDS = ISSUE_FIELDS + ",volume"
# Fields Comic Vine accepts in filter= / sort= (API docs); /search/ takes none.
FILTER_FIELDS = {
    "volumes": ("name", "id", "date_added", "date_last_updated"),
    "issues": ("name", "aliases", "id", "issue_number", "volume", "cover_date", "store_date", "date_added", "date_last_updated"),
}
SORT_FIELDS = {
    "volumes": ("name", "id", "date_added", "date_last_updated"),
    "issues": ("name", "id", "issue_number", "cover_date", "store_date", "date_added", "date_last_updated"),
}
CACHE_DIR = config.DATA_DIR / "cache"

JQ_TIMEOUT = 5
# jq can read files (import/include of .jq/.json modules, e.g. data/config.json
# with the API key) and the environment; expressions using these are refused.
# A leading "-" would be parsed as a jq command-line option (e.g. --rawfile).
JQ_FORBIDDEN = re.compile(
    r"^\s*-|\b(import|include|env|input_filename|modulemeta|get_search_list|get_prog_origin|get_jq_origin|halt_error)\b|\$ENV|\$__"
)

SEARCH_DEFAULTS = {
    "name": "",  # optional display name (list, "Showing"); falls back to the term / id
    "term": "",
    "advanced": False,
    "source": "search",  # search | volumes | issues
    "cv_filter": "",  # volumes/issues, e.g. "date_added:2020-01-01|2026-12-31"
    "sort": "",  # volumes/issues, e.g. "name:asc"
    "pages": 1,
    "page_size": None,  # None = the source's maximum (10 search, 100 volumes/issues)
    "volume_id": None,  # fixed volume (skips the search); with issues: filter by volume
    "publishers": [],
    "year_from": None,
    "year_to": None,
    "min_issues": None,
    "exclude_words": [],
    "cover_date_from": None,
    "cover_date_to": None,
    "volume_pick": "random",  # random | first
    "issue_pick": "random_all",  # random_all | first100
    "cache_hours": 24,
    "jq": "",  # optional jq expression applied to the candidate list
    "enabled": True,  # disabled searches keep their config but aren't used
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^[0-9a-f]{8}$")


# ---------- validation ----------

def _int_or_none(v, lo, hi):
    if v in (None, ""):
        return None
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return None


def _words(v):
    if isinstance(v, str):
        v = v.split(",")
    return [w.strip() for w in (v or []) if str(w).strip()][:20]


def _check_pairs(value, allowed, what):
    """Validate "field:value,field:value" against the allowed fields."""
    for part in filter(None, (p.strip() for p in value.split(","))):
        field, sep, rest = part.partition(":")
        if not sep or not rest or field not in allowed:
            raise UserError(
                f"invalid_{what}",
                "Invalid {what} '{part}'; allowed fields: {fields}",
                what=what,
                part=part,
                fields=", ".join(allowed),
            )


def normalize_search(item):
    """Fill defaults, clamp values and validate a search from the UI."""
    s = {**SEARCH_DEFAULTS, **{k: v for k, v in (item or {}).items() if k in SEARCH_DEFAULTS}}
    s["id"] = item.get("id") if _ID.match(str(item.get("id", ""))) else uuid.uuid4().hex[:8]
    s["name"] = str(s["name"] or "").strip()[:60]
    s["term"] = str(s["term"] or "").strip()[:100]
    s["advanced"] = bool(s["advanced"])
    s["enabled"] = bool(s["enabled"])
    s["source"] = s["source"] if s["source"] in PAGE_MAX else "search"
    s["cv_filter"] = str(s["cv_filter"] or "").strip()
    s["sort"] = str(s["sort"] or "").strip()
    if s["source"] in FILTER_FIELDS:
        _check_pairs(s["cv_filter"], FILTER_FIELDS[s["source"]], "cv_filter")
        if s["sort"]:
            field, _, direction = s["sort"].partition(":")
            if field not in SORT_FIELDS[s["source"]] or direction not in ("asc", "desc"):
                raise UserError(
                    "invalid_sort",
                    "Invalid sort '{sort}'; use field:asc or field:desc with: {fields}",
                    sort=s["sort"],
                    fields=", ".join(SORT_FIELDS[s["source"]]),
                )
    else:
        s["cv_filter"], s["sort"] = "", ""
    s["pages"] = _int_or_none(s["pages"], 1, MAX_PAGES) or 1
    s["page_size"] = _int_or_none(s["page_size"], 1, PAGE_MAX[s["source"]]) or PAGE_MAX[s["source"]]
    s["volume_id"] = _int_or_none(s["volume_id"], 1, 10**9)
    s["publishers"] = _words(s["publishers"])
    s["exclude_words"] = _words(s["exclude_words"])
    s["year_from"] = _int_or_none(s["year_from"], 1800, 2200)
    s["year_to"] = _int_or_none(s["year_to"], 1800, 2200)
    s["min_issues"] = _int_or_none(s["min_issues"], 1, 100000)
    for k in ("cover_date_from", "cover_date_to"):
        s[k] = s[k] if s[k] and _DATE.match(str(s[k])) else None
    s["volume_pick"] = s["volume_pick"] if s["volume_pick"] in ("random", "first") else "random"
    s["issue_pick"] = s["issue_pick"] if s["issue_pick"] in ("random_all", "first100") else "random_all"
    s["cache_hours"] = _int_or_none(s["cache_hours"], 1, 168) or 24
    s["jq"] = str(s["jq"] or "").strip()[:2000]
    if s["jq"] and JQ_FORBIDDEN.search(s["jq"]):
        raise UserError("jq_forbidden", "The jq expression can't use import, include, env, $ENV or similar")

    has_query = s["volume_id"] or s["cv_filter"] or (s["source"] == "issues" and (s["cover_date_from"] or s["cover_date_to"]))
    needs_term = not (s["advanced"] and has_query)
    if needs_term and not s["term"]:
        raise UserError("search_term_required", "The search needs a term")
    return s


# ---------- candidates (advanced) ----------

def _cover_range(s):
    return f"cover_date:{s['cover_date_from'] or '1800-01-01'}|{s['cover_date_to'] or '2200-12-31'}"


def plan_requests(s):
    """The Comic Vine calls needed to fetch the candidates (at most)."""
    issues = s["source"] == "issues"
    if s["volume_id"] and not issues:
        return [("volumes", {"filter": f"id:{s['volume_id']}", "limit": 1, "field_list": VOLUME_FIELDS})]
    size, plan = s["page_size"], []
    for page in range(s["pages"]):
        if s["source"] == "search":
            # /search/ ignores offset (the docs say otherwise; checked against
            # the real API: offset=10 answers "offset":0 with the same results).
            # It pages with a 1-based page number instead.
            params = {"query": s["term"], "resources": "volume", "limit": size, "page": page + 1}
        else:
            filters = [f"name:{s['term']}"] if s["term"] else []
            if issues and s["volume_id"]:
                filters.append(f"volume:{s['volume_id']}")
            if issues and (s["cover_date_from"] or s["cover_date_to"]):
                filters.append(_cover_range(s))
            if s["cv_filter"]:
                filters.append(s["cv_filter"])
            params = {"filter": ",".join(filters), "limit": size, "offset": page * size}
            if s["sort"]:
                params["sort"] = s["sort"]
        plan.append((s["source"], {**params, "field_list": ISSUE_LIST_FIELDS if issues else VOLUME_FIELDS}))
    return plan


def _cache_file(s):
    # Only what goes to Comic Vine: app-side filters and jq reuse the cache.
    fields = ["source", "term", "cv_filter", "sort", "pages", "page_size", "volume_id"]
    if s["source"] == "issues":
        fields += ["cover_date_from", "cover_date_to"]
    key = {k: s[k] for k in fields}
    digest = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.json"


def read_cache(s):
    try:
        data = json.loads(_cache_file(s).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if time.time() - data["fetched_at"] < s["cache_hours"] * 3600 else None


def clear_cache(s):
    _cache_file(s).unlink(missing_ok=True)


def _prune_cache(max_age=7 * 86400):
    for f in CACHE_DIR.glob("*.json"):
        if time.time() - f.stat().st_mtime > max_age:
            f.unlink(missing_ok=True)


def fetch_candidates(api_key, s, budget):
    """Return (volumes, info) from the cache or Comic Vine."""
    cached = read_cache(s)
    if cached:
        return cached["results"], {"calls": 0, "cached": True, "fetched_at": cached["fetched_at"], "total": cached["total"]}

    results, seen, total, calls = [], set(), None, 0
    for n, (resource, params) in enumerate(plan_requests(s)):
        data = cvapi.request(resource, api_key, params, budget)
        calls += 1
        total = data.get("number_of_total_results") if total is None else total
        page = data.get("results") or []
        if isinstance(page, dict):  # some single-result responses
            page = [page]
        new = 0
        for v in page:
            if v.get("id") not in seen:
                seen.add(v.get("id"))
                results.append(v)
                new += 1
        # Stop early: last page reached, or the page brought nothing new
        # (Comic Vine ignored the paging parameter) - don't waste more calls.
        fetched_so_far = (n + 1) * params["limit"]
        if len(page) < params["limit"] or (total is not None and fetched_so_far >= total) or (n > 0 and not new):
            if n > 0 and not new and page:
                log.warning("Comic Vine returned a repeated page for %s; stopped paging", resource)
            break

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _prune_cache()
    now = time.time()
    _cache_file(s).write_text(json.dumps({"fetched_at": now, "total": total, "results": results}))
    return results, {"calls": calls, "cached": False, "fetched_at": now, "total": total}


def _publisher(v):
    return ((v.get("publisher") or {}).get("name")) or ""


def apply_filters(items, s):
    """App-side filters (Comic Vine can't filter these in the query), then jq."""
    words = [w.lower() for w in s["exclude_words"]]
    if s["source"] == "issues":
        # Issues don't carry publisher/start year/issue count: only excluded
        # words apply, on the volume and issue names.
        out = [
            i for i in items
            if not any(w in f"{(i.get('volume') or {}).get('name') or ''} {i.get('name') or ''}".lower() for w in words)
        ]
        return run_jq(s["jq"], out)

    pubs = {p.lower() for p in s["publishers"]}
    out = []
    for v in items:
        if pubs and _publisher(v).lower() not in pubs:
            continue
        year = _int_or_none(v.get("start_year"), 0, 10000)
        if s["year_from"] and (year is None or year < s["year_from"]):
            continue
        if s["year_to"] and (year is None or year > s["year_to"]):
            continue
        if s["min_issues"] and (v.get("count_of_issues") or 0) < s["min_issues"]:
            continue
        name = (v.get("name") or "").lower()
        if any(w in name for w in words):
            continue
        out.append(v)
    return run_jq(s["jq"], out)


def jq_available():
    return shutil.which("jq") is not None


def run_jq(expr, items):
    """Apply a user jq expression to the candidate list; it must return a list.

    Runs with an empty environment, in a temporary directory and with a
    timeout; expressions that could read files or the environment are
    refused at validation (JQ_FORBIDDEN) and checked again here.
    """
    if not expr:
        return items
    if JQ_FORBIDDEN.search(expr):
        raise UserError("jq_forbidden", "The jq expression can't use import, include, env, $ENV or similar")
    if not jq_available():
        raise UserError("jq_missing", "jq is not installed (sudo apt install jq)")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            p = subprocess.run(
                ["jq", "-c", expr],
                input=json.dumps(items),
                capture_output=True,
                text=True,
                timeout=JQ_TIMEOUT,
                cwd=tmp,
                env={},
            )
        except subprocess.TimeoutExpired:
            raise UserError("jq_error", "jq: {detail}", detail=f"timeout ({JQ_TIMEOUT}s)") from None
    if p.returncode:
        raise UserError("jq_error", "jq: {detail}", detail=p.stderr.strip()[:300] or f"exit {p.returncode}")
    try:
        out = json.loads(p.stdout or "null")
    except json.JSONDecodeError:
        raise UserError("jq_not_list", "The jq expression must return a single array") from None
    if not isinstance(out, list):
        raise UserError("jq_not_list", "The jq expression must return a single array")
    # keep only objects that still look like Comic Vine records
    return [x for x in out if isinstance(x, dict) and x.get("id") is not None]


# ---------- issue selection ----------

_count_cache = {}  # (volume id, issue filter) -> (timestamp, total)


def _issue_filter(volume_id, s):
    f = f"volume:{volume_id}"
    if s["cover_date_from"] or s["cover_date_to"]:
        f += f",cover_date:{s['cover_date_from'] or '1800-01-01'}|{s['cover_date_to'] or '2200-12-31'}"
    return f


def _issue_count(api_key, volume, f, s, budget, use_volume_count):
    if use_volume_count and volume.get("count_of_issues"):
        return volume["count_of_issues"]
    hit = _count_cache.get((volume["id"], f))
    if hit and time.time() - hit[0] < s["cache_hours"] * 3600:
        return hit[1]
    data = cvapi.request("issues", api_key, {"filter": f, "limit": 1, "field_list": "id"}, budget)
    total = data.get("number_of_total_results") or 0
    _count_cache[(volume["id"], f)] = (time.time(), total)
    return total


def pick_issue(api_key, volume, s, budget):
    f = _issue_filter(volume["id"], s)
    if s["issue_pick"] == "first100":
        data = cvapi.request("issues", api_key, {"filter": f, "limit": 100, "field_list": ISSUE_FIELDS}, budget)
        results = data.get("results") or []
        if not results:
            raise UserError("no_issues", "No issues found for volume {volume}", volume=volume["id"])
        return random.choice(results)

    # Random among all issues: pick an offset and fetch just that one.
    date_filtered = f != f"volume:{volume['id']}"
    for use_volume_count in (not date_filtered, False):
        total = _issue_count(api_key, volume, f, s, budget, use_volume_count)
        if not total:
            break
        data = cvapi.request(
            "issues", api_key, {"filter": f, "limit": 1, "offset": random.randrange(total), "field_list": ISSUE_FIELDS}, budget
        )
        if data.get("results"):
            return data["results"][0]
        _count_cache.pop((volume["id"], f), None)  # stale count: retry with a fresh one
        if not use_volume_count:
            break
    raise UserError("no_issues", "No issues found for volume {volume}", volume=volume["id"])


# ---------- entry points ----------

def _simple(api_key, s, random_volume, budget):
    data = cvapi.request("search", api_key, {"query": s["term"], "resources": "volume", "limit": SIMPLE_LIMIT}, budget)
    results = data.get("results") or []
    if not results:
        raise UserError("no_volumes", "No volumes found for '{query}'", query=s["term"])
    volume = random.choice(results) if random_volume else results[0]
    data = cvapi.request("issues", api_key, {"filter": f"volume:{volume['id']}", "limit": 100}, budget)
    issues = data.get("results") or []
    if not issues:
        raise UserError("no_issues", "No issues found for volume {volume}", volume=volume["id"])
    return volume, random.choice(issues)


def _advanced(api_key, s, budget):
    items, _ = fetch_candidates(api_key, s, budget)
    candidates = apply_filters(items, s)
    if not candidates:
        raise UserError("no_candidates", "No volumes left after the filters for '{query}'", query=_label(s))
    chosen = candidates[0] if s["volume_pick"] == "first" else random.choice(candidates)
    if s["source"] == "issues":
        # the candidates already are issues; their volume only has id and name
        return chosen.get("volume") or {}, chosen
    return chosen, pick_issue(api_key, chosen, s, budget)


def _label(s):
    if s.get("name"):
        return s["name"]
    if s["term"]:
        return s["term"]
    if s["volume_id"]:
        return f"#{s['volume_id']}"
    if s["cv_filter"]:
        return s["cv_filter"]
    return f"{s['cover_date_from'] or '…'} – {s['cover_date_to'] or '…'}"


def _budget(comics_cfg):
    return int(comics_cfg.get("rate_limit_per_hour") or 150)


def fetch_random_cover(comics_cfg):
    """Return (PIL image, detail dict) for a random cover matching the config."""
    api_key = comics_cfg.get("api_key", "").strip()
    searches = comics_cfg.get("searches") or []
    if not api_key:
        raise UserError("api_key_missing", "Comic Vine API key is not set")
    if not searches:
        raise UserError("no_queries", "No search queries configured")
    enabled = [x for x in searches if x.get("enabled", True)]
    if not enabled:
        raise UserError("no_enabled_searches", "All searches are disabled; enable at least one")

    s = {**SEARCH_DEFAULTS, **random.choice(enabled)}
    budget = _budget(comics_cfg)
    if s["advanced"]:
        volume, issue = _advanced(api_key, s, budget)
    else:
        volume, issue = _simple(api_key, s, comics_cfg.get("random_volume", False), budget)
    log.info("Comic: '%s' -> %s (%s) #%s", _label(s), volume.get("name"), _publisher(volume), issue.get("issue_number"))

    img = Image.open(BytesIO(cvapi.download(issue["image"]["original_url"])))
    img.load()
    detail = {
        "query": _label(s),
        "volume": volume.get("name"),
        "volume_id": volume.get("id"),
        "publisher": _publisher(volume),
        "issue_number": issue.get("issue_number"),
        "url": issue.get("site_detail_url"),
    }
    return img, detail


def probe(comics_cfg, s, dry_run):
    """Preview an advanced search's candidates without touching the panel."""
    plan = plan_requests(s)
    cached = read_cache(s)
    curls = [cvapi.curl(resource, params) for resource, params in plan]
    if dry_run:
        return {"would_call": 0 if cached else len(plan), "cached": bool(cached), "curl": curls}

    api_key = comics_cfg.get("api_key", "").strip()
    if not api_key:
        raise UserError("api_key_missing", "Comic Vine API key is not set")
    items, info = fetch_candidates(api_key, s, _budget(comics_cfg))
    passed = apply_filters(items, s)
    return {
        **info,
        "kind": "issues" if s["source"] == "issues" else "volumes",
        "fetched": len(items),
        "passed": len(passed),
        "candidates": [_probe_row(x, s) for x in passed[:50]],
        "curl": curls,
    }


def _probe_row(x, s):
    if s["source"] == "issues":
        volume = (x.get("volume") or {}).get("name") or "?"
        return {
            "id": x.get("id"),
            "name": f"{volume} #{x.get('issue_number') or '?'}",
            "cover_date": x.get("cover_date"),
            "url": x.get("site_detail_url"),
        }
    return {
        "id": x.get("id"),
        "name": x.get("name"),
        "start_year": x.get("start_year"),
        "publisher": _publisher(x),
        "count_of_issues": x.get("count_of_issues"),
        "url": x.get("site_detail_url"),
    }
