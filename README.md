# inky-web

**English** · [Español](README.es.md)

A lightweight web UI to control a **Pimoroni Inky Impression 13.3"** (Spectra 6, 1600×1200) from the browser: upload and manage images, rotate a gallery, or show random comic covers from [Comic Vine](https://comicvine.gamespot.com/api/).

There is no authentication: it is meant for use on your LAN only.

## Features

**Modes**
- **Single image:** pick an uploaded image and leave it on screen.
- **Gallery:** rotate through the images of the enabled collections, in random or sequential order (collection by collection, in the list order).
- **Random comics:** random covers from Comic Vine (based on the `examples/spectra6/comics` example in [`pimoroni/inky`](https://github.com/pimoroni/inky)).
- **Newspapers:** today's front page of the newspapers you pick, rotated in list order. Sources: [Freedom Forum](https://frontpages.freedomforum.org/) (PDF rendered at the panel's size) and [kiosko.net](https://en.kiosko.net/) (JPEG). Neither is an official API, so they may stop working if their URLs change. A paper without a front page in the last 7 days is skipped.
- **Configurable interval** (minimum 2 minutes; a full panel refresh takes about 30–40 s). Mode and interval changes are staged behind **Apply / Discard**, so a stray click doesn't refresh the panel.
- **No redraw on startup:** e-ink keeps its image without power, so the app resumes the rotation from the last refresh. You can turn on "Refresh when the app starts" instead.
- **Pause:** keep the current image on screen until you resume the rotation.
- **Display buttons:** the four buttons of the Inky Impression (A–D) each run a configurable action: refresh now, switch to Gallery, Comics or Newspapers, pause/resume, or nothing. Presses while the panel is updating are ignored, never queued. Each one can be tried from the web UI.

**Images**
- Upload several at once (optionally straight into a collection), show and delete.
- **Collections:** group images by theme and tick the ones the gallery should rotate, in any combination. A collection only references images, so an image can be in several, and deleting a collection keeps its images. Images in no collection form a built-in group that can be rotated too.
- **Multi-select:** tick images (shift+click for a range, or "Select visible") to add them to a collection, remove them from one or delete them in one go. Filter the grid by collection and by file name to find them.
- **Save the comic on screen** to the "Comics guardados" collection (the original cover, with a readable file name) or **download** whatever is on screen.

**Display**
- **Keeps the aspect ratio:** either the whole image with borders, or filling the panel and cropping. Portrait images are rotated automatically.
- **Margins for a frame's mat:** top, bottom, left and right, in mm or px, measured as the frame hangs (portrait or landscape). The image is drawn inside them and the rest takes the border colour. Newspaper PDFs are rendered at the size left inside the margins.
- **Colour, contrast, brightness and Inky palette saturation.** The defaults are neutral (1.0 / 1.0 / 1.0, palette 0.5), the same as the Pimoroni examples, with a "Pimoroni values" button to go back to them.
- **Apply redraws the image currently on screen** with the new values, so you can compare settings. It doesn't move the rotation schedule.
- **Presets:** save colour / contrast / brightness / palette combinations under a name and load them back.
- **Upright preview:** the UI preview undoes the automatic rotation, with ⟲ / ⟳ buttons to adjust it (UI only, remembered per browser).

**Comic searches**
- **Simple searches** behave exactly like the Pimoroni example: `/search/`, 5 volumes, the first one (or a random one), and a random issue among the volume's first 100.
- **Advanced searches** add:
  - **Source:** `search` (relevance text search), `volumes` (filter by name) or `issues` (issues directly, e.g. every cover in a date range).
  - **Comic Vine query:** filter and sort (only on the fields the API accepts), and configurable pages × page size.
  - **App-side filters:** publishers, volume start year, minimum issue count and excluded title words.
  - **Picking:** a fixed volume by ID, a cover date range, and the issue picked at random among **all** of the volume's issues, or **in order** (#1 → last, then back to #1; the position survives restarts, with "Back to #1" to restart). In order, refreshes make no API calls while the issue list is cached.
  - **Optional jq expression** applied to the candidate list.
- **Cache:** each advanced search's candidate list is cached (24 h by default, in `data/cache/`). Changing app-side filters or jq costs no API calls.
- **Test:** shows the candidates and the equivalent `curl`, and asks before spending calls.
- **Name:** each search can have its own display name (shown in the list and in "Showing" instead of the term or id).
- **Enable / disable:** each search can be turned on or off without losing its configuration.
- The API key, searches and call budget are all editable from the UI.

**Interface** in Spanish or English (ES/EN switch at the top right, remembered per browser).

## Requirements

- Raspberry Pi with the Inky Impression 13.3", and Pimoroni's venv with the `inky` library installed (their installer creates `~/.virtualenvs/pimoroni`).
- A free Comic Vine API key, only for comics mode: https://comicvine.gamespot.com/api/
- `jq` (`sudo apt install jq`), only for jq expressions in advanced searches.
- `pdftoppm` (`sudo apt install poppler-utils`), only for newspapers mode: without it, Freedom Forum front pages fall back to a 700 px wide JPEG.

## Installation on the Pi

```bash
git clone <repo> ~/inky-web
cd ~/inky-web
~/.virtualenvs/pimoroni/bin/pip install -r requirements.txt
```

Run it by hand:

```bash
~/.virtualenvs/pimoroni/bin/python app.py
# http://<pi-hostname>.local:8080
```

The log should say `Inky display detected: ...`. If it says `running in mock mode` instead, the app is not using the venv with the `inky` library.

As a service (the unit assumes user `jasueh`, `~/inky-web` and Pimoroni's venv; adjust `inky-web.service` if yours differ):

```bash
sudo cp inky-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now inky-web
journalctl -u inky-web -f
```

If Pimoroni's comic script or anything else drives the panel (from cron, another service, etc.), disable it: only one process should use the display.

## Updating

```bash
cd ~/inky-web && git pull && sudo systemctl restart inky-web
```

Reload the page with `Ctrl+Shift+R` so the browser picks up the new JS.

## Images copied by hand

You can copy files straight into `data/images/` (e.g. with `scp`) and they show up in the UI. Two caveats:
- **No thumbnail is created:** thumbnails are only made when uploading from the UI, so the tile shows a broken image. Upload the file from the UI instead, or create the thumbnail in `data/thumbs/<name>.jpg` (max. 400×300).
- **File names must be "safe":** no spaces or accents (Werkzeug's `secure_filename`). Otherwise the app lists the file but refuses to show or delete it.

Some of Pimoroni's example images (e.g. `examples/spectra6/images/vincent-van-gogh-inky13.jpg`) are already rotated to fit the landscape panel buffer. Rotate them upright before using them here, so the app rotates them itself.

## Comic Vine: API notes

Taken from the official docs (comicvine.gamespot.com/api and /api/documentation):
- **Rate limit:** 200 requests per **resource** per hour, plus "velocity detection" (temporary blocks for too many requests per second). The app spaces its calls 1 s apart and enforces its own configurable budget (150/h per resource by default). The UI shows the calls made in the last hour.
- **`/search/`:** returns at most **10 results per call** and accepts **no `filter` or `sort`**. **It ignores `offset`**, even though the docs list it (`offset=10` answers `"offset":0` with the same results); it pages with a 1-based **`page`** parameter, which the app uses. If a page comes back with nothing new, the app stops paging instead of spending more calls.
- **`/volumes/` and `/issues/`:** return up to 100 per call and accept `filter=field:value,...` only on these fields:

| Resource | Filterable | Sortable |
|---|---|---|
| `/volumes/` | `name`, `id`, `date_added`, `date_last_updated` | same |
| `/issues/` | `name`, `aliases`, `id`, `issue_number`, `volume`, `cover_date`, `store_date`, `date_added`, `date_last_updated` | all except `aliases` and `volume` |

- **Publisher, start year and issue count can't be filtered in the query.** That's why the app filters them itself. For example, a `wolverine` search returns Panini's Italian edition first, before Marvel's.
- The docs don't say whether `filter=name:` matches "contains" or the exact name, nor the exact date format for `cover_date` (the app uses `YYYY-MM-DD|YYYY-MM-DD`).

**jq expressions:** jq can read files (`import` / `include` of `.jq` / `.json` modules, e.g. `data/config.json` with the API key) and the environment (`env`, `$ENV`), and an expression starting with `-` would be parsed as a command-line option. The app refuses those expressions and runs jq with an empty environment, in a temporary directory, with a 5 s timeout. The result must be a single list.

## Development without hardware

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
INKY_MOCK=1 .venv/bin/python app.py
```

In mock mode the processed image is only written to `data/current.png` (shown as the preview in the UI).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `INKY_WEB_PORT` | `8080` | HTTP port |
| `INKY_WEB_HOST` | `0.0.0.0` | Listen address |
| `INKY_WEB_DATA` | `./data` | Folder for images, config, state and cache |
| `INKY_MOCK` | — | `1` to run without a display |

## Project structure

```
app.py                  Flask app + JSON API
inkyweb/config.py       persistent config.json / state.json (in data/), migrations
inkyweb/display.py      image preparation + Inky driver (or mock)
inkyweb/library.py      image files and the collections that group them
inkyweb/scheduler.py    background thread: refresh / redraw according to the mode
inkyweb/buttons.py      the display's A–D buttons (GPIO) and their actions
inkyweb/newspapers.py   newspaper front pages: source catalogs, download, PDF rendering, cache
inkyweb/comics.py       simple and advanced comic searches, cache, jq, probing
inkyweb/cvapi.py        Comic Vine client: call spacing, per-resource budget, curl
inkyweb/errors.py       coded errors that the UI translates
templates/, static/     UI (HTML + vanilla JS); texts in static/i18n.js
inky-web.service        systemd unit
data/                   (not versioned) images, thumbnails, config, state, cache, preview
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/status` | Config (without the API key), state, images, API usage |
| POST | `/api/config` | Partial config update (JSON) |
| POST | `/api/refresh` | Refresh now (next image for the current mode) |
| POST | `/api/redraw` | Redraw the current image with the current display settings |
| POST | `/api/pause` | Pause or resume the rotation (`{"paused": true}`) |
| POST | `/api/buttons/<A-D>/press` | Do what pressing that display button does |
| POST | `/api/images` | Upload images (`multipart`, field `files`; optional `collection` id) |
| DELETE | `/api/images/<name>` | Delete an image |
| POST | `/api/images/delete` | Delete several images (`{"names": [...]}`) |
| POST | `/api/collections` | Create a collection (`{"name": ..., "images": [...]}`, images optional) |
| POST | `/api/collections/<id>` | Rename, enable/disable or move it (`{"name", "enabled", "move": "up"\|"down"}`); the id `unsorted` (images in no collection) only takes `enabled` |
| DELETE | `/api/collections/<id>` | Delete a collection (its images stay in the library) |
| POST | `/api/collections/<id>/images` | Add / remove images (`{"add": [...], "remove": [...]}`) |
| POST | `/api/images/<name>/show` | Switch to single-image mode with that image |
| POST | `/api/current/save` | Save the comic cover on screen to the "Comics guardados" collection (`{"last_refresh": ...}`) |
| GET | `/current/download` | Download the original of the image on screen (JPEG) |
| POST | `/api/presets` | Save / overwrite a preset (`{"name": ..., "values": {color, contrast, brightness, saturation}}`) |
| DELETE | `/api/presets/<name>` | Delete a preset |
| POST | `/api/comics/probe` | Test an advanced search (`{"search": {...}, "dry_run": true}` only reports how many calls it would make) |
| POST | `/api/comics/sequence/reset` | Restart a search's sequential picking from #1 (`{"id": ...}`) |
| POST | `/api/comics/cache/clear` | Clear a search's cache (`{"search": {...}}`) |
| GET | `/api/newspapers/catalog` | Countries of a source (`?source=kiosko\|ff`), or its newspapers in one (`&country=...`); `&refresh=1` reads the source again |
| POST | `/api/newspapers/probe` | Fetch a newspaper's latest front page into the cache and describe it (`{"source": ..., "paper": ...}`) |
| GET | `/newspapers/cover/<file>` | A cached front page (the `file` returned by the probe) |

API errors are returned as `{"error": {"code": ..., "params": {...}, "message": ...}}`. The UI translates `code` (see `static/i18n.js`) and falls back to `message` (English).

## License and credits

- The code is released under the [MIT License](LICENSE) © 2026 jasueh.
- `inkyweb/comics.py` is adapted from the Comic Vine example in [pimoroni/inky](https://github.com/pimoroni/inky) (MIT, © Pimoroni Ltd.). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- The newspapers mode is inspired by the newspaper plugin of [fatihak/InkyPi](https://github.com/fatihak/InkyPi); no code was taken from it.
- Comic data and cover images come from the [Comic Vine API](https://comicvine.gamespot.com/api/) at runtime, using your own API key. They are not included in this repository and belong to their respective owners. The Comic Vine API is for non-commercial use only.
- This project is not affiliated with or endorsed by Pimoroni, Comic Vine or Fandom.
