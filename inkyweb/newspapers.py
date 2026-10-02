"""Newspaper front pages, rotated one paper at a time.

Two sources, neither of them an official API (URLs may change without notice):

- ff: Freedom Forum "Today's Front Pages". The front page comes as a PDF,
  rendered with pdftoppm (poppler-utils) at the panel's size; without
  pdftoppm, or if the PDF fails, the 700 px wide JPEG is used instead.
  Files live in a folder per day of the month, so only recent days are tried.
- kiosko: kiosko.net, a JPEG of up to 880 px wide in a folder per date.

The idea of showing Freedom Forum front pages comes from the newspaper plugin
of fatihak/InkyPi; no code was taken from it.
"""

import html
import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError

from . import config, display
from .errors import UserError

log = logging.getLogger(__name__)

SOURCES = ("kiosko", "ff")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; inky-web)"}
TIMEOUT = 30
# kiosko.net's servers reject about half of the new TLS connections; an open
# connection keeps working, so requests share a session and retry.
ATTEMPTS = 5
DAYS_BACK = 7  # how far back to look for a front page (covers weeklies)
PDF_TIMEOUT = 60
CATALOG_HOURS = 24 * 7
NAME_MAX = 80
CACHE_DIR = config.DATA_DIR / "cache" / "newspapers"

FF_PAPERS_URL = "https://api.freedomforum.org/cache/papers.js"
FF_CDN = "https://cdn.freedomforum.org/dfp"
FF_STALE_DAYS = 3  # a file older than this is last month's, left in the day folder

KIOSKO_SITE = "https://en.kiosko.net"
KIOSKO_IMG = "https://img.kiosko.net"
KIOSKO_SPACING = 0.3  # seconds between pages when listing a country
KIOSKO_MAX_PAGES = 80

_session = requests.Session()
_session.headers.update(HEADERS)

PAPER_RE = {"ff": re.compile(r"[A-Z0-9_]{2,40}"), "kiosko": re.compile(r"[a-z]{2}/[a-z0-9_]{1,60}")}


def pdf_available():
    return shutil.which("pdftoppm") is not None


def normalize_paper(item):
    """Validate a configured newspaper: {"id", "source", "paper", "name", "enabled"}."""
    source = str(item.get("source") or "")
    paper = str(item.get("paper") or "").strip()
    if source not in SOURCES or not PAPER_RE[source].fullmatch(paper):
        raise UserError("invalid_newspaper", "Invalid newspaper: {paper}", paper=f"{source}:{paper}")
    return {
        "id": str(item.get("id") or uuid.uuid4().hex[:8]),
        "source": source,
        "paper": paper,
        "name": str(item.get("name") or "").strip()[:NAME_MAX] or paper,
        "enabled": item.get("enabled") is not False,
    }


# ---------- catalogs ----------

def _get(url, kind=None):
    """GET that returns None when the file isn't there (or isn't of that kind)."""
    for attempt in range(ATTEMPTS):
        try:
            r = _session.get(url, timeout=TIMEOUT)
            break
        except requests.ConnectionError:  # includes TLS handshake failures
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(0.5)
    if r.status_code != 200 or (kind and kind not in r.headers.get("Content-Type", "")):
        return None
    return r


def _catalog(name, build, refresh=False):
    """A list cached on disk for CATALOG_HOURS."""
    path = CACHE_DIR / f"catalog_{name}.json"
    if not refresh:
        try:
            saved = json.loads(path.read_text())
            if time.time() - saved["fetched_at"] < CATALOG_HOURS * 3600:
                return saved["items"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
    items = build()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": time.time(), "items": items}))
    return items


def _page(url):
    try:
        r = _get(url)
    except requests.RequestException as e:
        log.warning("%s: %s", url, e)
        r = None
    if r is None:
        raise UserError("newspaper_source", "Could not read the newspaper list ({url})", status=502, url=url)
    return r.content.decode("utf-8", "replace")  # kiosko.net doesn't declare its charset


def _ff_papers():
    text = _page(FF_PAPERS_URL)
    try:
        raw = json.loads(text[text.index("[") : text.rindex("]") + 1])
    except ValueError:
        raise UserError("newspaper_source", "Could not read the newspaper list ({url})", status=502, url=FF_PAPERS_URL) from None
    return [
        {"paper": p["paperId"], "name": p.get("title") or p["paperId"], "country": p.get("country") or "", "city": p.get("city") or ""}
        for p in raw
        if PAPER_RE["ff"].fullmatch(p.get("paperId") or "")
    ]


def _kiosko_countries():
    found = re.findall(r'<a href="/([a-z]{2})/" title="[^"]*">([^<]+)</a>', _page(f"{KIOSKO_SITE}/"))
    return [{"code": code, "name": html.unescape(name)} for code, name in sorted(set(found), key=lambda c: c[1])]


def _kiosko_papers(country):
    """Every paper shown on the country's index, section and region pages."""
    index = _page(f"{KIOSKO_SITE}/{country}/")
    pages = sorted(set(re.findall(rf'href="/{country}/((?:geo/)?[A-Za-z0-9_]+\.html)"', index)))
    papers = {}

    def collect(text):
        for tag in re.findall(rf"<img[^>]*img\.kiosko\.net/[\d/]+{country}/[a-z0-9_]+\.\d+\.jpg[^>]*>", text):
            slug = re.search(rf"/{country}/([a-z0-9_]+)\.\d+\.jpg", tag).group(1)
            alt = re.search(r'alt="([^"]*)"', tag)
            papers.setdefault(slug, html.unescape(alt.group(1)).strip() if alt else slug)

    collect(index)
    for page in pages[:KIOSKO_MAX_PAGES]:
        time.sleep(KIOSKO_SPACING)
        collect(_page(f"{KIOSKO_SITE}/{country}/{page}"))
    return [{"paper": f"{country}/{slug}", "name": name or slug, "city": ""} for slug, name in sorted(papers.items(), key=lambda p: p[1].lower())]


def countries(source, refresh=False):
    """[{"code", "name"}] of the countries a source has newspapers for."""
    if source == "kiosko":
        return _catalog("kiosko_countries", _kiosko_countries, refresh)
    if source == "ff":
        names = sorted({p["country"] for p in _catalog("ff", _ff_papers, refresh) if p["country"]})
        return [{"code": n, "name": n} for n in names]
    raise UserError("invalid_newspaper", "Invalid newspaper: {paper}", paper=source)


def papers(source, country, refresh=False):
    """[{"paper", "name", "city"}] of a source's newspapers in a country."""
    if source == "kiosko":
        if not re.fullmatch(r"[a-z]{2}", country or ""):
            raise UserError("invalid_newspaper", "Invalid newspaper: {paper}", paper=f"{source}:{country}")
        return _catalog(f"kiosko_{country}", lambda: _kiosko_papers(country), refresh)
    if source == "ff":
        found = [p for p in _catalog("ff", _ff_papers, refresh) if p["country"] == country]
        return sorted(({"paper": p["paper"], "name": p["name"], "city": p["city"]} for p in found), key=lambda p: p["name"].lower())
    raise UserError("invalid_newspaper", "Invalid newspaper: {paper}", paper=source)


# ---------- front pages ----------

def _prefix(source, paper):
    return f"{source}_{paper.replace('/', '_')}_"


def _valid(path):
    try:
        with Image.open(path) as img:
            img.load()
        return True
    except (UnidentifiedImageError, OSError):
        return False


def _render_pdf(data, out):
    """First page of a PDF as a PNG whose long side matches the panel's
    (the part of it inside the margins).

    Runs like jq does: empty environment, temporary directory, timeout.
    """
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "page.pdf").write_bytes(data)
        size = str(max(display.usable_size(config.load_config()["display"])))
        try:
            p = subprocess.run(
                ["pdftoppm", "-f", "1", "-l", "1", "-scale-to", size, "-png", "-singlefile", "page.pdf", "page"],
                capture_output=True,
                text=True,
                timeout=PDF_TIMEOUT,
                cwd=tmp,
                env={},
            )
        except subprocess.TimeoutExpired:
            log.warning("pdftoppm timed out after %ss", PDF_TIMEOUT)
            return False
        png = Path(tmp) / "page.png"
        if p.returncode or not png.exists():
            log.warning("pdftoppm failed: %s", p.stderr.strip()[:300] or f"exit {p.returncode}")
            return False
        shutil.move(png, out)
    return True


def _fresh(response, day):
    """False for a file left over from a previous month in the day's folder."""
    try:
        modified = parsedate_to_datetime(response.headers["Last-Modified"])
    except (KeyError, TypeError, ValueError):
        return True
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    return abs((noon - modified).days) <= FF_STALE_DAYS


def _download(source, paper, day):
    """Store that day's front page in the cache. Returns its path or None."""
    base = CACHE_DIR / f"{_prefix(source, paper)}{day.isoformat()}"
    if source == "kiosko":
        r = _get(f"{KIOSKO_IMG}/{day:%Y/%m/%d}/{paper}.jpg", "image/")
        if r is None:
            return None
        out = base.with_name(base.name + "_jpg.jpg")
        out.write_bytes(r.content)
        return out if _valid(out) else out.unlink()

    if pdf_available():
        r = _get(f"{FF_CDN}/pdf{day.day}/{paper}.pdf", "pdf")
        if r is not None and _fresh(r, day):
            out = base.with_name(base.name + "_pdf.png")
            if _render_pdf(r.content, out) and _valid(out):
                return out
            out.unlink(missing_ok=True)
    r = _get(f"{FF_CDN}/jpg{day.day}/lg/{paper}.jpg", "image/")
    if r is None or not _fresh(r, day):
        return None
    out = base.with_name(base.name + "_jpg.jpg")
    out.write_bytes(r.content)
    return out if _valid(out) else out.unlink()


def cover(source, paper):
    """Latest front page available: (path, date, "pdf" | "jpg", from cache).

    Tries today and then back DAYS_BACK days; Freedom Forum also tomorrow,
    for papers from time zones ahead. A day already in the cache isn't
    downloaded again.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    days = [today - timedelta(days=n) for n in range(DAYS_BACK + 1)]
    if source == "ff":
        days.insert(0, today + timedelta(days=1))
    prefix = _prefix(source, paper)
    for day in days:
        cached = next(iter(sorted(CACHE_DIR.glob(f"{prefix}{day.isoformat()}_*"))), None)
        path = cached or _download(source, paper, day)
        if path:
            for old in CACHE_DIR.glob(f"{prefix}*"):  # keep one front page per paper
                if old != path:
                    old.unlink(missing_ok=True)
            return path, day.isoformat(), path.stem.rsplit("_", 1)[1], bool(cached)
    raise UserError("no_front_page", "No front page of {paper} in the last {days} days", status=404, paper=paper, days=DAYS_BACK)


def probe(item):
    """What the next refresh would show for a newspaper, without showing it."""
    p = normalize_paper(item)
    path, day, kind, cached = cover(p["source"], p["paper"])
    with Image.open(path) as img:
        width, height = img.size
    return {"file": path.name, "date": day, "kind": kind, "cached": cached, "width": width, "height": height}


def fetch_next(ncfg):
    """Front page of the next enabled newspaper, in list order.

    A paper without a recent front page is skipped; the error is only
    raised if none of them has one. Returns (image, detail).
    """
    enabled = [p for p in ncfg["papers"] if p.get("enabled") is not False]
    if not enabled:
        raise UserError("no_newspapers", "No newspapers enabled; add or enable at least one")
    start = config.load_state()["newspaper_index"]
    error = None
    for n in range(len(enabled)):
        idx = (start + n) % len(enabled)
        p = enabled[idx]
        try:
            path, day, kind, _ = cover(p["source"], p["paper"])
        except UserError as e:
            log.warning("%s: %s", p["name"], e)
            error = error or e
            continue
        config.update_state(newspaper_index=idx + 1)
        img = Image.open(path)
        img.load()
        detail = {"paper": p["name"], "source": p["source"], "code": p["paper"], "date": day, "kind": kind}
        if p["source"] == "kiosko":
            country, slug = p["paper"].split("/")
            detail["url"] = f"{KIOSKO_SITE}/{country}/np/{slug}.html"
        log.info("Front page: %s %s (%s)", p["name"], day, kind)
        return img, detail
    raise error
