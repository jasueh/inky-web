"""Background thread that refreshes the panel according to the current mode."""

import logging
import random
import threading
import time
from datetime import datetime, timezone

from PIL import Image

from . import comics, config, display

log = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Scheduler:
    def __init__(self):
        self._wake = threading.Event()
        self._refresh_now = False
        self._refresh_lock = threading.Lock()
        self._next_at = None
        self._thread = threading.Thread(target=self._run, name="scheduler", daemon=True)

    def start(self):
        config.update_state(busy=False)
        self._thread.start()

    def trigger(self):
        """Refresh as soon as possible (config change or 'refresh now')."""
        self._refresh_now = True
        self._wake.set()

    def reschedule(self):
        """Recompute the next refresh time without refreshing now."""
        self._wake.set()

    @property
    def busy(self):
        return self._refresh_lock.locked()

    def _run(self):
        # Refresh once on startup so the panel reflects the saved config.
        self._refresh_now = True
        while True:
            cfg = config.load_config()
            if self._refresh_now:
                self._refresh_now = False
                self.refresh(cfg)
                self._schedule_next(cfg, from_now=True)
            elif self._next_at is None:
                self._schedule_next(cfg, from_now=True)
            elif self._next_at and time.time() >= self._next_at:
                self.refresh(cfg)
                self._schedule_next(cfg, from_now=True)
            else:
                self._schedule_next(cfg, from_now=False)

            timeout = None if self._next_at is None else max(1, self._next_at - time.time())
            self._wake.wait(timeout)
            self._wake.clear()

    def _schedule_next(self, cfg, from_now):
        rotating = cfg["mode"] in ("gallery", "comics")
        if not rotating:
            self._next_at = None
        else:
            interval = max(config.MIN_INTERVAL_MINUTES, int(cfg["interval_minutes"])) * 60
            last = self._last_refresh_ts()
            base = time.time() if from_now or last is None else last
            self._next_at = base + interval
        config.update_state(
            next_refresh=datetime.fromtimestamp(self._next_at, timezone.utc).isoformat(timespec="seconds")
            if self._next_at
            else None
        )

    def _last_refresh_ts(self):
        last = config.load_state().get("last_refresh")
        return datetime.fromisoformat(last).timestamp() if last else None

    def refresh(self, cfg):
        if not self._refresh_lock.acquire(blocking=False):
            log.info("Refresh already in progress, skipping")
            return
        config.update_state(busy=True)
        try:
            img, source, detail = self._pick(cfg)
            if img is None:
                config.update_state(last_error=None)
                return
            display.show(img, cfg["display"])
            config.update_state(last_refresh=_now(), last_source=source, last_detail=detail, last_error=None)
        except Exception as e:
            log.exception("Refresh failed")
            config.update_state(last_error=f"{_now()}: {e}")
        finally:
            config.update_state(busy=False)
            self._refresh_lock.release()

    def _pick(self, cfg):
        mode = cfg["mode"]
        if mode == "comics":
            img, detail = comics.fetch_random_cover(cfg["comics"])
            return img, "comics", detail

        if mode == "single":
            name = cfg.get("single_image")
            if not name:
                return None, None, None
            return self._open(name), "single", {"image": name}

        # gallery
        names = [n for n in cfg["gallery"]["images"] if (config.IMAGES_DIR / n).exists()]
        if not names:
            raise ValueError("Gallery is empty")
        state = config.load_state()
        if cfg["gallery"]["order"] == "sequential":
            idx = state["gallery_index"] % len(names)
            config.update_state(gallery_index=idx + 1)
        else:
            last = (state.get("last_detail") or {}).get("image")
            choices = [n for n in names if n != last] or names
            idx = names.index(random.choice(choices))
        return self._open(names[idx]), "gallery", {"image": names[idx]}

    @staticmethod
    def _open(name):
        img = Image.open(config.IMAGES_DIR / name)
        img.load()
        return img
