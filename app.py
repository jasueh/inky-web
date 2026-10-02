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

from inkyweb import buttons, comics, config, cvapi, display, library, newspapers
from inkyweb.errors import UserError
from inkyweb.scheduler import Scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("inky-web")
# The UI polls /api/status every few seconds; keep request lines out of the journal.
logging.getLogger("werkzeug").setLevel(logging.WARNING)

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
    return isinstance(name, str) and name == secure_filename(name) and (config.IMAGES_DIR / name).is_file()


def valid_names(names):
    if not isinstance(names, list):
        raise UserError("invalid_names", "A list of image names is required")
    return [n for n in names if valid_image_name(n)]


def remove_images(names):
    """Delete image files and forget them in the collections / single image."""
    for name in names:
        (config.IMAGES_DIR / name).unlink(missing_ok=True)
        (config.THUMBS_DIR / thumb_name(name)).unlink(missing_ok=True)
    gone = set(names)
    cfg = config.load_config()
    library.forget(cfg, gone)
    if cfg["single_image"] in gone:
        cfg["single_image"] = None
    config.save_config(cfg)
    log.info("Deleted %s", sorted(gone))


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
    elif state.get("last_source") == "newspapers":
        base = f"{detail.get('paper', 'newspaper')} {detail.get('date') or ''}"
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
    images = library.list_images()
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
        comics_meta={
            "search_defaults": comics.SEARCH_DEFAULTS,
            "page_max": comics.PAGE_MAX,
            "max_pages": comics.MAX_PAGES,
            "filter_fields": comics.FILTER_FIELDS,
            "sort_fields": comics.SORT_FIELDS,
            "jq_available": comics.jq_available(),
            "api_usage": cvapi.usage(),
            "official_limit": cvapi.OFFICIAL_LIMIT,
        },
        newspapers_meta={
            "sources": newspapers.SOURCES,
            "pdf_available": newspapers.pdf_available(),
            "days_back": newspapers.DAYS_BACK,
        },
        buttons={"actions": buttons.ACTIONS, "available": buttons.available},
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
        if cfg["mode"] != data["mode"]:
            cfg["paused"] = False  # picking a mode means wanting to see it
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

    if "buttons" in data:
        for label, action in data["buttons"].items():
            if label not in buttons.LABELS or action not in buttons.ACTIONS:
                raise UserError("invalid_button", "Invalid button or action")
            cfg["buttons"][label] = action

    if "gallery" in data:
        g = data["gallery"]
        if g.get("order") in ("random", "sequential"):
            cfg["gallery"]["order"] = g["order"]

    if "comics" in data:
        c = data["comics"]
        if "searches" in c:
            cfg["comics"]["searches"] = [comics.normalize_search(item) for item in c["searches"]]
            comics.prune_sequences({x["id"] for x in cfg["comics"]["searches"]})
        if "rate_limit_per_hour" in c:
            cfg["comics"]["rate_limit_per_hour"] = int(clamp(c["rate_limit_per_hour"], 10, cvapi.OFFICIAL_LIMIT))
        if "random_volume" in c:
            cfg["comics"]["random_volume"] = bool(c["random_volume"])
        if c.get("api_key"):  # empty = keep current key
            cfg["comics"]["api_key"] = c["api_key"].strip()

    if "newspapers" in data:
        n = data["newspapers"]
        if "papers" in n:
            cfg["newspapers"]["papers"] = [newspapers.normalize_paper(item) for item in n["papers"]]

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


@app.post("/api/comics/probe")
def probe_search():
    """Preview an advanced search. dry_run only reports the calls it would make."""
    body = request.get_json(force=True) or {}
    s = comics.normalize_search(body.get("search") or {})
    return jsonify(comics.probe(config.load_config()["comics"], s, bool(body.get("dry_run"))))


@app.post("/api/comics/sequence/reset")
def reset_sequence():
    """Start a search's sequential picking over from the first issue."""
    body = request.get_json(force=True) or {}
    comics.reset_sequence(str(body.get("id") or ""))
    return status()


@app.post("/api/comics/cache/clear")
def clear_search_cache():
    body = request.get_json(force=True) or {}
    comics.clear_cache(comics.normalize_search(body.get("search") or {}))
    return jsonify(ok=True)


@app.get("/api/newspapers/catalog")
def newspaper_catalog():
    """Countries of a source, or with ?country= the newspapers it has there."""
    source = request.args.get("source", "")
    refresh = request.args.get("refresh") == "1"
    country = request.args.get("country")
    if country:
        return jsonify(papers=newspapers.papers(source, country, refresh))
    return jsonify(countries=newspapers.countries(source, refresh))


@app.post("/api/newspapers/probe")
def probe_newspaper():
    """Fetch a newspaper's latest front page into the cache and describe it."""
    return jsonify(newspapers.probe(request.get_json(force=True) or {}))


@app.get("/newspapers/cover/<name>")
def newspaper_cover(name):
    return send_from_directory(newspapers.CACHE_DIR, name, max_age=0)


@app.post("/api/refresh")
def refresh_now():
    scheduler.trigger()
    return status()


@app.post("/api/pause")
def pause():
    """Pause or resume the rotation: {"paused": true|false}."""
    body = request.get_json(force=True) or {}
    buttons.set_paused(bool(body.get("paused")), scheduler)
    return status()


@app.post("/api/buttons/<label>/press")
def press_button(label):
    """Do what pressing that button on the display does (to try it from the UI)."""
    if label not in buttons.LABELS:
        raise UserError("invalid_button", "Invalid button or action", status=404)
    if buttons.press(label, scheduler) == "busy":
        raise UserError("panel_busy", "The display is updating; wait for it to finish", status=409)
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
    """Save the comic cover on screen into the library, in its own collection."""
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
    saved = next((c for c in cfg["collections"] if c["id"] == library.SAVED_COMICS), None)
    if saved is None:
        names = {c["name"].lower() for c in cfg["collections"]}
        title = next(t for t in ("Comics guardados", f"Comics guardados {uuid.uuid4().hex[:4]}") if t.lower() not in names)
        saved = library.create(cfg, title, library.SAVED_COMICS)
    library.add(saved, [name])
    config.save_config(cfg)
    config.update_state(last_detail={**detail, "saved_as": name})
    log.info("Saved comic cover as %s", name)
    return status()


@app.post("/api/images")
def upload():
    """Store the uploaded files, optionally straight into a collection."""
    cid = request.form.get("collection")
    if cid:
        library.find(config.load_config(), cid)  # fail before storing anything
    saved, errors = [], []
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        if Path(f.filename).suffix.lower() not in library.ALLOWED_EXT:
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
    if cid and saved:
        cfg = config.load_config()
        library.add(library.find(cfg, cid), saved)
        config.save_config(cfg)
    log.info("Uploaded %s", saved)
    return jsonify(saved=saved, errors=errors)


@app.delete("/api/images/<name>")
def delete_image(name):
    if not valid_image_name(name):
        raise UserError("unknown_image", "Unknown image", status=404)
    remove_images([name])
    return status()


@app.post("/api/images/delete")
def delete_images():
    """Delete several images at once. Names that no longer exist are skipped."""
    remove_images(valid_names((request.get_json(force=True) or {}).get("names")))
    return status()


# ---------- collections ----------

@app.post("/api/collections")
def create_collection():
    """Create a collection, optionally with some images already in it."""
    body = request.get_json(force=True) or {}
    cfg = config.load_config()
    col = library.create(cfg, body.get("name"))
    library.add(col, valid_names(body.get("images") or []))
    config.save_config(cfg)
    return status()


@app.post("/api/collections/<cid>")
def update_collection(cid):
    """Rename, enable/disable or move a collection. The built-in "unsorted"
    group only takes "enabled"."""
    body = request.get_json(force=True) or {}
    cfg = config.load_config()
    if cid == library.UNSORTED:
        if "enabled" in body:
            cfg["unsorted_enabled"] = bool(body["enabled"])
    else:
        col = library.find(cfg, cid)
        if "name" in body:
            col["name"] = library.clean_name(cfg, body["name"], skip_id=cid)
        if "enabled" in body:
            col["enabled"] = bool(body["enabled"])
        if body.get("move") in ("up", "down"):  # the list order is the sequential order
            cols = cfg["collections"]
            i = cols.index(col)
            j = i + (-1 if body["move"] == "up" else 1)
            if 0 <= j < len(cols):
                cols[i], cols[j] = cols[j], cols[i]
    config.save_config(cfg)
    scheduler.reschedule()
    return status()


@app.delete("/api/collections/<cid>")
def delete_collection(cid):
    """Remove the grouping only; its images stay in the library."""
    cfg = config.load_config()
    cfg["collections"].remove(library.find(cfg, cid))
    config.save_config(cfg)
    return status()


@app.post("/api/collections/<cid>/images")
def collection_images(cid):
    """Add and/or remove images: {"add": [...], "remove": [...]}."""
    body = request.get_json(force=True) or {}
    cfg = config.load_config()
    col = library.find(cfg, cid)
    library.add(col, valid_names(body.get("add") or []))
    drop = set(valid_names(body.get("remove") or []))
    col["images"] = [n for n in col["images"] if n not in drop]
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
buttons.start(scheduler)

if __name__ == "__main__":
    app.run(host=os.environ.get("INKY_WEB_HOST", "0.0.0.0"), port=int(os.environ.get("INKY_WEB_PORT", 8080)))
