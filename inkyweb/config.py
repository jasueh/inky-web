"""Persistent configuration and runtime state, stored as JSON under DATA_DIR."""

import copy
import json
import os
import threading
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("INKY_WEB_DATA", Path(__file__).resolve().parent.parent / "data"))
IMAGES_DIR = DATA_DIR / "images"
THUMBS_DIR = DATA_DIR / "thumbs"
CONFIG_FILE = DATA_DIR / "config.json"
STATE_FILE = DATA_DIR / "state.json"
PREVIEW_FILE = DATA_DIR / "current.png"
SOURCE_FILE = DATA_DIR / "current_source.png"  # original of what's on screen

# A full refresh of the Spectra 6 panel takes ~30-40s; keep a safe margin.
MIN_INTERVAL_MINUTES = 2

MODES = ("single", "gallery", "comics")

DEFAULT_CONFIG = {
    "mode": "single",
    "interval_minutes": 60,
    "refresh_on_start": False,  # e-ink keeps its image; don't redraw on app start
    "paused": False,  # keep the current image: gallery / comics don't rotate
    # Action of each Inky Impression button; see buttons.ACTIONS
    "buttons": {"A": "refresh", "B": "gallery", "C": "comics", "D": "pause"},
    "single_image": None,
    "gallery": {
        "order": "random",  # random | sequential (collection by collection)
    },
    # The gallery rotates the enabled ones: [{"id", "name", "enabled", "images"}]
    "collections": [],
    "unsorted_enabled": True,  # also rotate the images that are in no collection
    "comics": {
        "api_key": "",
        # Each search: {"id", "term", "advanced", ...}; see comics.SEARCH_DEFAULTS
        "searches": [{"id": "00000001", "term": "Weird Science"}],
        "random_volume": False,  # simple searches: pick among the top 5 volumes
        "rate_limit_per_hour": 150,  # own budget per Comic Vine resource (official: 200)
    },
    "display": {
        "fit": "contain",  # contain (letterbox) | fit (crop)
        "auto_rotate": True,
        "border": "white",  # white | black
        "color": 1.0,  # neutral: same as the Pimoroni examples (no enhancement)
        "contrast": 1.0,
        "brightness": 1.0,
        "saturation": 0.5,  # inky set_image() default
    },
    # name -> {color, contrast, brightness, saturation}
    "display_presets": {},
}

# Image adjustments stored in presets, with their allowed ranges.
ADJUSTMENTS = {"color": (0, 3), "contrast": (0, 3), "brightness": (0, 3), "saturation": (0, 1)}
PRESET_NAME_MAX = 40

DEFAULT_STATE = {
    "gallery_index": 0,
    "last_refresh": None,
    "rendered_at": None,  # last time the panel was drawn (refresh or redraw)
    "next_refresh": None,
    "last_source": None,
    "last_detail": None,
    "last_error": None,
    "preview_rotated": False,
    "sequences": {},  # sequential comic picking: {search id: {volume id | "issues": position}}
    "busy": False,
}

_lock = threading.RLock()


def _merge(defaults, data):
    out = copy.deepcopy(defaults)
    for key, value in (data or {}).items():
        # An empty default dict is a free-form map (e.g. presets): take it as is.
        if key in out and isinstance(out[key], dict) and out[key] and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        elif key in out:
            out[key] = value
    return out


def _read(path, defaults):
    try:
        return _merge(defaults, json.loads(path.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        return copy.deepcopy(defaults)


def _write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def ensure_dirs():
    for d in (DATA_DIR, IMAGES_DIR, THUMBS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _migrate(raw):
    """Upgrade configs saved by older versions. Returns True if changed."""
    changed = False
    comics = raw.get("comics")
    if isinstance(comics, dict) and "searches" not in comics and "queries" in comics:
        comics["searches"] = [{"id": uuid.uuid4().hex[:8], "term": q.strip()} for q in comics.pop("queries") if q.strip()]
        changed = True
    gallery = raw.get("gallery")
    if isinstance(gallery, dict) and "images" in gallery:
        # The single gallery list becomes a collection. Images outside it
        # didn't rotate before, so keep the unsorted group off.
        images = gallery.pop("images")
        if images:
            raw.setdefault("collections", []).append(
                {"id": uuid.uuid4().hex[:8], "name": "Galería", "enabled": True, "images": images}
            )
            raw["unsorted_enabled"] = False
        changed = True
    return changed


def load_config():
    with _lock:
        try:
            raw = json.loads(CONFIG_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        migrated = _migrate(raw)
        cfg = _merge(DEFAULT_CONFIG, raw)
        if migrated:  # persist so migrated searches and collections keep stable ids
            _write(CONFIG_FILE, cfg)
        return cfg


def save_config(cfg):
    with _lock:
        _write(CONFIG_FILE, cfg)


def load_state():
    with _lock:
        return _read(STATE_FILE, DEFAULT_STATE)


def update_state(**changes):
    with _lock:
        state = load_state()
        state.update(changes)
        _write(STATE_FILE, state)
        return state
