"""inky-web: small web UI to control a Pimoroni Inky Impression."""

import logging
import os
import uuid
from io import BytesIO
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from inkyweb import config, display
from inkyweb.errors import UserError
from inkyweb.scheduler import Scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("inky-web")
# The UI polls /api/status every few seconds; keep request lines out of the journal.
logging.getLogger("werkzeug").setLevel(logging.WARNING)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
THUMB_SIZE = (400, 300)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

config.ensure_dirs()
scheduler = Scheduler()


@app.errorhandler(UserError)
def user_error(e):
    return jsonify(error=e.to_dict()), e.status


@app.errorhandler(HTTPException)
def api_error(e):
    if request.path.startswith("/api/"):
        return jsonify(error={"code": f"http_{e.code}", "params": {}, "message": e.description}), e.code
    return e


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


def current_basename(state):
    """A readable file name (no extension) for the image on screen."""
    detail = state.get("last_detail") or {}
    if state.get("last_source") == "comics":
        base = f"{detail.get('volume', 'comic')} {detail.get('issue_number') or ''}"
    else:
        base = Path(detail.get("image") or "inky").stem
    return secure_filename(base.strip()) or "inky"


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
    state = config.load_state()
    saved_as = (state.get("last_detail") or {}).get("saved_as")
    return jsonify(
        config=public_config(config.load_config()),
        state={
            **state,
            "busy": scheduler.busy,
            "has_source": config.SOURCE_FILE.exists(),
            "saved": bool(saved_as) and valid_image_name(saved_as),
        },
        images=[{"name": n, "thumb": f"/thumbs/{thumb_name(n)}"} for n in images],
        display_defaults=config.DEFAULT_CONFIG["display"],
        resolution=display.resolution(),
        min_interval=config.MIN_INTERVAL_MINUTES,
    )


@app.post("/api/config")
def update_config():
    data = request.get_json(force=True) or {}
    cfg = config.load_config()
    old = {k: cfg[k] for k in ("mode", "single_image")}

    if "mode" in data:
        if data["mode"] not in config.MODES:
            raise UserError("invalid_mode", "Invalid mode")
        cfg["mode"] = data["mode"]

    if "interval_minutes" in data:
        cfg["interval_minutes"] = max(config.MIN_INTERVAL_MINUTES, int(data["interval_minutes"]))

    if "refresh_on_start" in data:
        cfg["refresh_on_start"] = bool(data["refresh_on_start"])

    if "single_image" in data:
        name = data["single_image"]
        if name is not None and not valid_image_name(name):
            raise UserError("unknown_image", "Unknown image")
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
        for key, (lo, hi) in config.ADJUSTMENTS.items():
            if key in d:
                cd[key] = clamp(d[key], lo, hi)

    config.save_config(cfg)

    # Show changes immediately when they change which image is on screen;
    # otherwise just recompute the next rotation time. Display settings are
    # applied through /api/redraw.
    changed_view = cfg["mode"] != old["mode"] or (
        cfg["mode"] == "single" and cfg["single_image"] != old["single_image"]
    )
    if changed_view:
        scheduler.trigger()
    else:
        scheduler.reschedule()
    return status()


@app.post("/api/presets")
def save_preset():
    """Save (or overwrite) a named set of image adjustments."""
    body = request.get_json(force=True) or {}
    name = str(body.get("name") or "").strip()
    if not name or len(name) > config.PRESET_NAME_MAX:
        raise UserError("preset_name", "The name must be 1 to {max} characters long", max=config.PRESET_NAME_MAX)
    values = body.get("values") or {}
    try:
        preset = {k: clamp(values[k], lo, hi) for k, (lo, hi) in config.ADJUSTMENTS.items()}
    except (KeyError, TypeError, ValueError):
        raise UserError("preset_values", "Missing or non-numeric values")
    cfg = config.load_config()
    cfg["display_presets"][name] = preset
    config.save_config(cfg)
    return status()


@app.delete("/api/presets/<path:name>")
def delete_preset(name):
    cfg = config.load_config()
    if cfg["display_presets"].pop(name, None) is None:
        raise UserError("preset_not_found", "Preset not found", status=404)
    config.save_config(cfg)
    return status()


@app.post("/api/refresh")
def refresh_now():
    scheduler.trigger()
    return status()


@app.post("/api/redraw")
def redraw():
    scheduler.request_redraw()
    return status()


@app.get("/current/download")
def download_current():
    if not config.SOURCE_FILE.exists():
        abort(404)
    if scheduler.busy:
        raise UserError("panel_busy", "The display is updating; wait for it to finish", status=409)
    buf = BytesIO()
    with Image.open(config.SOURCE_FILE) as img:
        img.convert("RGB").save(buf, "JPEG", quality=95)
    buf.seek(0)
    name = current_basename(config.load_state()) + ".jpg"
    return send_file(buf, mimetype="image/jpeg", as_attachment=True, download_name=name)


@app.post("/api/current/save")
def save_current():
    """Save the comic cover on screen into the image library and gallery."""
    body = request.get_json(silent=True) or {}
    if scheduler.busy:  # current_source.png may already hold the next image
        raise UserError("panel_busy", "The display is updating; wait for it to finish", status=409)
    state = config.load_state()
    if state.get("last_source") != "comics":
        raise UserError("not_a_comic", "Only comic covers can be saved")
    # Guard against a rotation between what the user saw and this request.
    if body.get("last_refresh") != state.get("last_refresh"):
        raise UserError("image_changed", "The image on screen changed; check and try again", status=409)
    if not config.SOURCE_FILE.exists():
        raise UserError("no_current_image", "No current image saved", status=404)

    detail = state.get("last_detail") or {}
    if detail.get("saved_as") and valid_image_name(detail["saved_as"]):
        return status()

    name = unique_name(current_basename(state) + ".jpg")
    with Image.open(config.SOURCE_FILE) as img:
        img.convert("RGB").save(config.IMAGES_DIR / name, "JPEG", quality=95)
    make_thumb(name)

    cfg = config.load_config()
    if name not in cfg["gallery"]["images"]:
        cfg["gallery"]["images"].append(name)
        config.save_config(cfg)
    config.update_state(last_detail={**detail, "saved_as": name})
    log.info("Saved comic cover as %s", name)
    return status()


@app.post("/api/images")
def upload():
    saved, errors = [], []
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        if Path(f.filename).suffix.lower() not in ALLOWED_EXT:
            errors.append(UserError("unsupported_type", "{file}: unsupported type", file=f.filename).to_dict())
            continue
        name = unique_name(f.filename)
        path = config.IMAGES_DIR / name
        f.save(path)
        try:
            make_thumb(name)
            saved.append(name)
        except (UnidentifiedImageError, OSError) as e:
            path.unlink(missing_ok=True)
            errors.append(UserError("invalid_image", "{file}: not a valid image ({detail})", file=f.filename, detail=str(e)).to_dict())
    log.info("Uploaded %s", saved)
    return jsonify(saved=saved, errors=errors)


@app.delete("/api/images/<name>")
def delete_image(name):
    if not valid_image_name(name):
        raise UserError("unknown_image", "Unknown image", status=404)
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
        raise UserError("unknown_image", "Unknown image", status=404)
    cfg = config.load_config()
    cfg["mode"] = "single"
    cfg["single_image"] = name
    config.save_config(cfg)
    scheduler.trigger()
    return status()


scheduler.start()

if __name__ == "__main__":
    app.run(host=os.environ.get("INKY_WEB_HOST", "0.0.0.0"), port=int(os.environ.get("INKY_WEB_PORT", 8080)))
