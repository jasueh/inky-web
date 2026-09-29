"""Persistent configuration and runtime state, stored as JSON under DATA_DIR."""

import copy
import json
import os
import threading
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
    "single_image": None,
    "gallery": {
        "images": [],
        "order": "random",  # random | sequential
    },
    "comics": {
        "api_key": "",
        "queries": ["Weird Science"],
        "random_volume": False,
    },
    "display": {
        "fit": "contain",  # contain (letterbox) | fit (crop)
        "auto_rotate": True,
        "border": "white",  # white | black
        "color": 1.5,
        "contrast": 1.2,
        "brightness": 1.0,
        "saturation": 1.0,
    },
}

DEFAULT_STATE = {
    "gallery_index": 0,
    "last_refresh": None,
    "rendered_at": None,  # last time the panel was drawn (refresh or redraw)
    "next_refresh": None,
    "last_source": None,
    "last_detail": None,
    "last_error": None,
    "preview_rotated": False,
    "busy": False,
}

_lock = threading.RLock()


def _merge(defaults, data):
    out = copy.deepcopy(defaults)
    for key, value in (data or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
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


def load_config():
    with _lock:
        return _read(CONFIG_FILE, DEFAULT_CONFIG)


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
