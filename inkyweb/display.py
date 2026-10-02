"""Image preparation (aspect ratio, colour boost) and the Inky display driver.

Set INKY_MOCK=1 to run without hardware: the processed image is only written
to the preview file.
"""

import logging
import math
import os
import threading

from PIL import Image, ImageEnhance, ImageOps

from . import config

log = logging.getLogger(__name__)

DEFAULT_RESOLUTION = (1600, 1200)
BORDERS = {"white": (255, 255, 255), "black": (0, 0, 0)}
# Margins leave room for a frame's mat. They are given as seen on the wall, so
# the app needs to know how the panel hangs (its buffer is landscape).
SIDES = ("top", "right", "bottom", "left")
MOUNTS = ("landscape", "portrait")
UNITS = ("px", "mm")
MARGIN_MAX = 600  # per side, in either unit; together they take at most half the panel
# Diagonal of each Inky Impression by resolution, for the mm <-> px conversion.
DIAGONAL_INCHES = {(1600, 1200): 13.3, (800, 480): 7.3, (640, 400): 4.0, (600, 448): 5.7}

_display = None
_display_lock = threading.Lock()


def _get_display():
    global _display
    if _display is None:
        if os.environ.get("INKY_MOCK") == "1":
            _display = False
        else:
            try:
                from inky.auto import auto

                _display = auto()
                log.info("Inky display detected: %s %s", type(_display).__name__, _display.resolution)
            except Exception as e:  # no hardware / not on a Pi
                log.warning("No Inky display available (%s); running in mock mode", e)
                _display = False
    return _display


def resolution():
    d = _get_display()
    return tuple(d.resolution) if d else DEFAULT_RESOLUTION


def px_per_mm():
    w, h = resolution()
    return math.hypot(w, h) / (DIAGONAL_INCHES.get((w, h), 13.3) * 25.4)


def margins(opts):
    """The margins in panel pixels, as (left, top, right, bottom) of the buffer."""
    w, h = resolution()
    scale = px_per_mm() if opts.get("margin_unit") == "mm" else 1
    m = {side: max(0, round(float(opts.get(f"margin_{side}", 0)) * scale)) for side in SIDES}
    if opts.get("mount") == "portrait":
        # Portrait images are turned 90° CCW to fit the buffer, so the top of
        # what hangs on the wall is the buffer's left side.
        left, top, right, bottom = m["top"], m["right"], m["bottom"], m["left"]
    else:
        left, top, right, bottom = m["left"], m["top"], m["right"], m["bottom"]

    def limit(a, b, size):
        if a + b <= size // 2:
            return a, b
        a = a * (size // 2) // (a + b)
        return a, size // 2 - a

    left, right = limit(left, right, w)
    top, bottom = limit(top, bottom, h)
    return left, top, right, bottom


def usable_size(opts):
    """Size in pixels of the part of the panel left inside the margins."""
    w, h = resolution()
    left, top, right, bottom = margins(opts)
    return w - left - right, h - top - bottom


def prepare(img, opts):
    """Fit an image to the panel keeping its aspect ratio and boost colours.

    Returns (image, rotated) where rotated tells whether it was turned 90° CCW
    to match the panel orientation.
    """
    w, h = resolution()
    img = ImageOps.exif_transpose(img).convert("RGB")

    rotated = opts.get("auto_rotate", True) and (img.height > img.width) != (h > w)
    if rotated:
        img = img.rotate(90, expand=True)

    left, top, right, bottom = margins(opts)
    area = (w - left - right, h - top - bottom)
    border = BORDERS.get(opts.get("border"), BORDERS["white"])
    if opts.get("fit") == "fit":
        img = ImageOps.fit(img, area, method=Image.LANCZOS, centering=(0.5, 0.5))
    else:
        img = ImageOps.pad(img, area, method=Image.LANCZOS, color=border)
    if area != (w, h):
        canvas = Image.new("RGB", (w, h), border)
        canvas.paste(img, (left, top))
        img = canvas

    img = ImageEnhance.Color(img).enhance(float(opts.get("color", 1.0)))
    img = ImageEnhance.Contrast(img).enhance(float(opts.get("contrast", 1.0)))
    img = ImageEnhance.Brightness(img).enhance(float(opts.get("brightness", 1.0)))
    return img, rotated


def show(img, opts):
    """Prepare and push an image to the panel. Blocks for the full refresh.

    Returns whether the image was auto-rotated.
    """
    img, rotated = prepare(img, opts)
    with _display_lock:
        img.save(config.PREVIEW_FILE)
        d = _get_display()
        if d:
            d.set_image(img, saturation=float(opts.get("saturation", 0.5)))
            d.show()
        else:
            log.info("Mock display: preview written to %s", config.PREVIEW_FILE)
    return rotated
