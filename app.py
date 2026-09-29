"""inky-web: small web UI to control a Pimoroni Inky Impression."""

import logging
import os
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

from inkyweb import config, display
from inkyweb.scheduler import Scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("inky-web")

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
THUMB_SIZE = (400, 300)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

config.ensure_dirs()
scheduler = Scheduler()


# ---------- helpers ----------

def list_images():
    files = sorted(
        (p for p in config.IMAGES_DIR.iterdir() if p.suffix.lower() in ALLOWED_EXT),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p.name for p in files]


def thumb_name(name):
    return Path(name).stem + ".jpg"


def make_thumb(name):
    with Image.open(config.IMAGES_DIR / name) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail(THUMB_SIZE)
        img.save(config.THUMBS_DIR / thumb_name(name), quality=85)


def unique_name(filename):
    name = secure_filename(filename) or "image"
    stem, ext = os.path.splitext(name)
    if (config.IMAGES_DIR / name).exists() or (config.THUMBS_DIR / thumb_name(name)).exists():
        name = f"{stem}-{uuid.uuid4().hex[:6]}{ext}"
    return name


def valid_image_name(name):
    return name == secure_filename(name) and (config.IMAGES_DIR / name).is_file()


def public_config(cfg):
    out = {**cfg, "comics": {**cfg["comics"]}}
    key = out["comics"].pop("api_key", "")
    out["comics"]["api_key_set"] = bool(key)
    out["comics"]["api_key_hint"] = f"…{key[-4:]}" if len(key) >= 4 else ""
    return out


def clamp(value, lo, hi):
    return max(lo, min(hi, float(value)))


# ---------- pages & files ----------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/images/<path:name>")
def image_file(name):
    return send_from_directory(config.IMAGES_DIR, name)


@app.get("/thumbs/<path:name>")
def thumb_file(name):
    return send_from_directory(config.THUMBS_DIR, name)


@app.get("/preview.png")
def preview():
    if not config.PREVIEW_FILE.exists():
        abort(404)
    return send_from_directory(config.DATA_DIR, config.PREVIEW_FILE.name, max_age=0)


# ---------- API ----------

@app.get("/api/status")
def status():
    images = list_images()
    return jsonify(
        config=public_config(config.load_config()),
        state={**config.load_state(), "busy": scheduler.busy},
        images=[{"name": n, "thumb": f"/thumbs/{thumb_name(n)}"} for n in images],
        resolution=display.resolution(),
        min_interval=config.MIN_INTERVAL_MINUTES,
    )


@app.post("/api/config")
def update_config():
    data = request.get_json(force=True) or {}
    cfg = config.load_config()
    old = {k: cfg[k] for k in ("mode", "single_image")} | {"display": dict(cfg["display"])}

    if "mode" in data:
        if data["mode"] not in config.MODES:
            abort(400, "invalid mode")
        cfg["mode"] = data["mode"]

    if "interval_minutes" in data:
        cfg["interval_minutes"] = max(config.MIN_INTERVAL_MINUTES, int(data["interval_minutes"]))

    if "single_image" in data:
        name = data["single_image"]
        if name is not None and not valid_image_name(name):
            abort(400, "unknown image")
        cfg["single_image"] = name

    if "gallery" in data:
        g = data["gallery"]
        if "images" in g:
            cfg["gallery"]["images"] = [n for n in g["images"] if valid_image_name(n)]
        if g.get("order") in ("random", "sequential"):
            cfg["gallery"]["order"] = g["order"]

    if "comics" in data:
        c = data["comics"]
        if "queries" in c:
            cfg["comics"]["queries"] = [q.strip() for q in c["queries"] if q and q.strip()]
        if "random_volume" in c:
            cfg["comics"]["random_volume"] = bool(c["random_volume"])
        if c.get("api_key"):  # empty = keep current key
            cfg["comics"]["api_key"] = c["api_key"].strip()

    if "display" in data:
        d, cd = data["display"], cfg["display"]
        if d.get("fit") in ("contain", "fit"):
            cd["fit"] = d["fit"]
        if d.get("border") in display.BORDERS:
            cd["border"] = d["border"]
        if "auto_rotate" in d:
            cd["auto_rotate"] = bool(d["auto_rotate"])
        for key, lo, hi in (("color", 0, 3), ("contrast", 0, 3), ("brightness", 0, 3), ("saturation", 0, 1)):
            if key in d:
                cd[key] = clamp(d[key], lo, hi)

    config.save_config(cfg)

    # Show changes immediately when they affect what's on screen right now;
    # otherwise just recompute the next rotation time.
    changed_view = cfg["mode"] != old["mode"] or (
        cfg["mode"] == "single" and (cfg["single_image"] != old["single_image"] or cfg["display"] != old["display"])
    )
    if changed_view:
        scheduler.trigger()
    else:
        scheduler.reschedule()
    return status()


@app.post("/api/refresh")
def refresh_now():
    scheduler.trigger()
    return status()


@app.post("/api/images")
def upload():
    saved, errors = [], []
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        if Path(f.filename).suffix.lower() not in ALLOWED_EXT:
            errors.append(f"{f.filename}: unsupported type")
            continue
        name = unique_name(f.filename)
        path = config.IMAGES_DIR / name
        f.save(path)
        try:
            make_thumb(name)
            saved.append(name)
        except (UnidentifiedImageError, OSError) as e:
            path.unlink(missing_ok=True)
            errors.append(f"{f.filename}: {e}")
    log.info("Uploaded %s", saved)
    return jsonify(saved=saved, errors=errors)


@app.delete("/api/images/<name>")
def delete_image(name):
    if not valid_image_name(name):
        abort(404)
    (config.IMAGES_DIR / name).unlink()
    (config.THUMBS_DIR / thumb_name(name)).unlink(missing_ok=True)

    cfg = config.load_config()
    cfg["gallery"]["images"] = [n for n in cfg["gallery"]["images"] if n != name]
    if cfg["single_image"] == name:
        cfg["single_image"] = None
    config.save_config(cfg)
    return status()


@app.post("/api/images/<name>/show")
def show_image(name):
    if not valid_image_name(name):
        abort(404)
    cfg = config.load_config()
    cfg["mode"] = "single"
    cfg["single_image"] = name
    config.save_config(cfg)
    scheduler.trigger()
    return status()


scheduler.start()

if __name__ == "__main__":
    app.run(host=os.environ.get("INKY_WEB_HOST", "0.0.0.0"), port=int(os.environ.get("INKY_WEB_PORT", 8080)))
