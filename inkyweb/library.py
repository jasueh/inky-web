"""Image library: the files on disk and the collections that group them.

A collection only references image names, so an image can be in several.
Images in no collection form the built-in "unsorted" group, which the gallery
can rotate like any other collection.
"""

import uuid

from . import config
from .errors import UserError

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
NAME_MAX = 40
UNSORTED = "unsorted"  # id of the built-in group in the API
SAVED_COMICS = "saved-comics"  # collection that receives saved comic covers


def list_images():
    """Image names, newest first."""
    files = sorted(
        (p for p in config.IMAGES_DIR.iterdir() if p.suffix.lower() in ALLOWED_EXT),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p.name for p in files]


def clean_name(cfg, name, skip_id=None):
    """Validate a collection name; skip_id is the collection being renamed."""
    name = str(name or "").strip()
    if not name or len(name) > NAME_MAX:
        raise UserError("collection_name", "The name must be 1 to {max} characters long", max=NAME_MAX)
    if any(c["name"].lower() == name.lower() and c["id"] != skip_id for c in cfg["collections"]):
        raise UserError("collection_exists", 'There is already a collection called "{name}"', name=name)
    return name


def create(cfg, name, cid=None):
    col = {"id": cid or uuid.uuid4().hex[:8], "name": clean_name(cfg, name), "enabled": True, "images": []}
    cfg["collections"].append(col)
    return col


def find(cfg, cid):
    for col in cfg["collections"]:
        if col["id"] == cid:
            return col
    raise UserError("collection_not_found", "Collection not found", status=404)


def add(col, names):
    col["images"] += [n for n in dict.fromkeys(names) if n not in col["images"]]


def forget(cfg, names):
    """Drop images from every collection (they were deleted)."""
    gone = set(names)
    for col in cfg["collections"]:
        col["images"] = [n for n in col["images"] if n not in gone]


def rotation(cfg):
    """Images the gallery goes through: each enabled collection in list order,
    then the unsorted ones. An image in several collections appears once."""
    names = list_images()
    existing = set(names)
    out = []
    for col in cfg["collections"]:
        if col["enabled"]:
            out += [n for n in col["images"] if n in existing]
    if cfg["unsorted_enabled"]:
        used = {n for col in cfg["collections"] for n in col["images"]}
        out += [n for n in names if n not in used]
    return list(dict.fromkeys(out))
