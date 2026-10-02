"""The four buttons on the side of the Inky Impression (A to D, top to bottom).

Each one runs a configurable action. A full refresh takes long and the panel
gives no instant feedback, so a press while the panel is updating is ignored
rather than queued: pressing again "just in case" never does a second thing.
"""

import logging
import os
import threading
import time

from . import config, display

log = logging.getLogger(__name__)

LABELS = ("A", "B", "C", "D")
# none | refresh (next image) | gallery / comics (switch mode) | pause (toggle the rotation)
ACTIONS = ("none", "refresh", "gallery", "comics", "pause")
DEBOUNCE_SECONDS = 0.5

available = False  # True once the GPIO lines are being watched


def pins():
    """BCM GPIO numbers for A-D. They are fixed by the board; only C differs
    between models (Pimoroni's examples/spectra6/buttons.py): 25 on the 13.3"."""
    return [5, 6, 25 if display.resolution() == (1600, 1200) else 16, 24]


def press(label, scheduler):
    """Run the action configured for a button. Returns what happened."""
    cfg = config.load_config()
    action = cfg["buttons"].get(label, "none")
    if action == "none":
        return "none"
    if scheduler.busy:
        return "busy"
    if action == "refresh":
        scheduler.trigger()
    elif action == "pause":
        set_paused(not cfg["paused"], scheduler)
    else:  # switch mode; shows its next image right away
        cfg["mode"] = action
        cfg["paused"] = False
        config.save_config(cfg)
        scheduler.trigger()
    return action


def set_paused(paused, scheduler):
    """Pause keeps the current image on screen; resuming restarts the interval."""
    cfg = config.load_config()
    cfg["paused"] = bool(paused)
    config.save_config(cfg)
    if paused:
        scheduler.reschedule()
    else:
        scheduler.restart_interval()


def start(scheduler):
    """Watch the buttons in a background thread, if there is GPIO to watch."""
    global available
    if os.environ.get("INKY_MOCK") == "1":
        return
    try:
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge

        chip = gpiodevice.find_chip_by_platform()
        offsets = [chip.line_offset_from_id(pin) for pin in pins()]
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.FALLING)
        request = chip.request_lines(consumer="inky-web-buttons", config=dict.fromkeys(offsets, settings))
    except Exception as e:  # no GPIO / not on a Pi / lines in use
        log.warning("Buttons not available (%s)", e)
        return

    def run():
        last = {}
        while True:
            for event in request.read_edge_events():
                label = LABELS[offsets.index(event.line_offset)]
                now = time.monotonic()
                if now - last.get(label, 0) < DEBOUNCE_SECONDS:
                    continue
                last[label] = now
                try:
                    log.info("Button %s: %s", label, press(label, scheduler))
                except Exception:
                    log.exception("Button %s failed", label)

    available = True
    threading.Thread(target=run, name="buttons", daemon=True).start()
    log.info("Watching buttons A-D on GPIO %s", pins())
