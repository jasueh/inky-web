"""Background thread that refreshes the panel according to the current mode."""

import logging
import random
import threading
import time
from datetime import datetime, timezone

from PIL import Image, ImageOps

from . import comics, config, display, library, newspapers
from .errors import UserError

log = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


class Scheduler:
    def __init__(self):
        self._wake = threading.Event()
        self._refresh_now = False
        self._redraw_now = False
        self._refresh_lock = threading.Lock()
        self._next_at = None
        self._base = None  # timestamp the rotation interval counts from
        self._thread = threading.Thread(target=self._run, name="scheduler", daemon=True)

    def start(self):
        config.update_state(busy=False)
        self._thread.start()

    def trigger(self):
        """Refresh as soon as possible (config change or 'refresh now')."""
        self._refresh_now = True
        self._wake.set()

    def request_redraw(self):
        """Redraw the image currently on screen with the current display settings."""
        self._redraw_now = True
        self._wake.set()

    def reschedule(self):
        """Recompute the next refresh time without refreshing now."""
        self._wake.set()

    def restart_interval(self):
        """Count the rotation interval from now (e.g. when resuming from pause)."""
        self._base = time.time()
        self._wake.set()

    @property
    def busy(self):
        return self._refresh_lock.locked()

    def _run(self):
        cfg = config.load_config()
        if cfg.get("refresh_on_start"):
            self._refresh_now = True
        else:
            # The e-ink panel keeps its image without power, so don't redraw
            # (or call Comic Vine) on startup. Resume the rotation from the last
            # refresh, or wait a full interval if that time already passed.
            last = self._last_refresh_ts()
            now = time.time()
            self._base = last if last and last + self._interval(cfg) > now else now
            log.info("Startup without refresh; rotation resumes from %s", _iso(self._base))
        while True:
            cfg = config.load_config()
            if self._refresh_now:
                self._refresh_now = False
                self._redraw_now = False  # a full refresh already uses the latest settings
                self.refresh(cfg)
                self._schedule_next(cfg, from_now=True)
            elif self._redraw_now:
                self._redraw_now = False
                self.redraw(cfg)
                self._schedule_next(cfg, from_now=False)  # keep the rotation timing
            elif self._next_at is None:
                self._schedule_next(cfg, from_now=False)
            elif self._next_at and time.time() >= self._next_at:
                self.refresh(cfg)
                self._schedule_next(cfg, from_now=True)
            else:
                self._schedule_next(cfg, from_now=False)

            timeout = None if self._next_at is None else max(1, self._next_at - time.time())
            self._wake.wait(timeout)
            self._wake.clear()

    @staticmethod
    def _interval(cfg):
        return max(config.MIN_INTERVAL_MINUTES, int(cfg["interval_minutes"])) * 60

    def _schedule_next(self, cfg, from_now):
        """Next refresh = base + interval. from_now restarts the count (after a
        refresh attempt, successful or not); otherwise the base is kept so an
        interval change or a redraw doesn't move or re-trigger the rotation."""
        if from_now or self._base is None:
            self._base = time.time()
        rotating = cfg["mode"] != "single" and not cfg["paused"]
        self._next_at = self._base + self._interval(cfg) if rotating else None
        config.update_state(next_refresh=_iso(self._next_at) if self._next_at else None)

    def _last_refresh_ts(self):
        last = config.load_state().get("last_refresh")
        return datetime.fromisoformat(last).timestamp() if last else None

    def refresh(self, cfg):
        """Pick the next image for the current mode and show it."""

        def run():
            img, source, detail = self._pick(cfg)
            if img is None:
                return
            # Keep the original so it can be redrawn with other display settings.
            # Bake in the EXIF orientation (PNG drops it) and normalise the mode.
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.save(config.SOURCE_FILE)
            rotated = display.show(img, cfg["display"])
            now = _now()
            config.update_state(
                last_refresh=now, rendered_at=now, last_source=source, last_detail=detail, preview_rotated=rotated
            )

        self._locked("Refresh", run)

    def redraw(self, cfg):
        """Show the current image again, e.g. after changing display settings."""

        def run():
            if not config.SOURCE_FILE.exists():
                raise UserError("no_redraw_source", "No current image to redraw; wait for the next refresh")
            with Image.open(config.SOURCE_FILE) as img:
                img.load()
                rotated = display.show(img, cfg["display"])
            config.update_state(rendered_at=_now(), preview_rotated=rotated)

        self._locked("Redraw", run)

    def _locked(self, what, fn):
        if not self._refresh_lock.acquire(blocking=False):
            log.info("%s skipped: panel update already in progress", what)
            return
        config.update_state(busy=True)
        try:
            fn()
            config.update_state(last_error=None)
        except Exception as e:
            log.exception("%s failed", what)
            # Coded errors are translated by the UI; anything else (network,
            # HTTP...) is shown with its original message.
            err = e.to_dict() if isinstance(e, UserError) else {"code": None, "params": {}, "message": str(e)}
            config.update_state(last_error={"at": _now(), **err})
        finally:
            config.update_state(busy=False)
            self._refresh_lock.release()

    def _pick(self, cfg):
        mode = cfg["mode"]
        if mode == "comics":
            img, detail = comics.fetch_random_cover(cfg["comics"])
            return img, "comics", detail

        if mode == "newspapers":
            img, detail = newspapers.fetch_next(cfg["newspapers"])
            return img, "newspapers", detail

        if mode == "single":
            name = cfg.get("single_image")
            if not name:
                return None, None, None
            return self._open(name), "single", {"image": name}

        # gallery
        names = library.rotation(cfg)
        if not names:
            raise UserError("gallery_empty", "The enabled collections have no images")
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
