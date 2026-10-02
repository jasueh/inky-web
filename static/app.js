const $ = (id) => document.getElementById(id);
const SLIDERS = ["color", "contrast", "brightness", "saturation"];

let data = null;
let modeDirty = false;
let displayDirty = false;

function markModeDirty() {
  const cfg = data.config;
  const mode = document.querySelector("input[name=mode]:checked")?.value;
  modeDirty =
    mode !== cfg.mode ||
    String($("interval").value) !== String(cfg.interval_minutes) ||
    $("refresh-on-start").checked !== cfg.refresh_on_start;
  $("mode-apply").disabled = !modeDirty;
  $("mode-discard").disabled = !modeDirty;
  $("mode-pending").hidden = !modeDirty;
}

async function api(method, url, body) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = new Error(body?.error?.message || `${res.status} ${res.statusText}`);
    err.data = body?.error; // {code, params, message}
    throw err;
  }
  return res.json();
}

const saveConfig = async (patch) => render(await api("POST", "/api/config", patch));

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(lang);
}

const errText = (err) => (err.data ? tErr(err.data) : err.message);

function lastErrorText(e) {
  if (!e) return "";
  if (typeof e === "string") return e; // saved by an older version
  return `${fmtTime(e.at)}: ${tErr(e)}`;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function describe(state) {
  const d = state.last_detail;
  if (!d) return "—";
  if (state.last_source === "comics") {
    const title = esc(`${d.volume} #${d.issue_number ?? "?"}`) + (d.publisher ? ` · ${esc(d.publisher)}` : "");
    return d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${title}</a> (${esc(d.query)})` : title;
  }
  return esc(d.image);
}

function render(next) {
  data = next;
  const { config: cfg, state, images } = data;

  // status
  $("busy").hidden = !state.busy;
  $("btn-refresh").disabled = state.busy;
  $("st-mode").textContent = t(`mode.${cfg.mode}`);
  $("st-detail").innerHTML = describe(state);
  $("st-last").textContent = fmtTime(state.last_refresh);
  $("st-next").textContent = state.next_refresh ? fmtTime(state.next_refresh) : "—";
  $("st-res").textContent = data.resolution.join("×");
  $("st-error").hidden = !state.last_error;
  $("st-error").textContent = lastErrorText(state.last_error);
  const ts = state.rendered_at || state.last_refresh || "";
  if (ts !== $("preview").dataset.ts) {
    $("preview").dataset.ts = ts;
    if (ts) $("preview").src = `/preview.png?t=${encodeURIComponent(ts)}`;
  }
  applyPreviewRotation();

  // save / download what's on screen (disabled mid-refresh: the source file
  // may already hold the next image)
  const isComic = state.last_source === "comics" && state.has_source;
  $("btn-save-current").hidden = !isComic;
  $("btn-save-current").disabled = state.saved || state.busy;
  $("btn-save-current").textContent = t(state.saved ? "status.saved" : "status.save");
  $("btn-download").hidden = !state.has_source || state.busy;
  $("btn-download").href = `/current/download?t=${encodeURIComponent(ts)}`;

  // mode: staged until "Aplicar", so polling must not overwrite a pending edit
  if (modeDirty) markModeDirty(); // re-check against the fresh config
  if (!modeDirty) {
    document.querySelector(`input[name=mode][value=${cfg.mode}]`).checked = true;
    $("interval").value = cfg.interval_minutes;
    $("refresh-on-start").checked = cfg.refresh_on_start;
  }
  $("interval").min = data.min_interval;
  $("interval-hint").textContent = t("mode.min", { n: data.min_interval });
  $("mode-apply").disabled = !modeDirty;
  $("mode-discard").disabled = !modeDirty;
  $("mode-pending").hidden = !modeDirty;

  // images
  $("gallery-order").value = cfg.gallery.order;
  $("images-empty").hidden = images.length > 0;
  $("select-all").disabled = !images.length;
  renderImages(cfg, images);
  const names = new Set(images.map((i) => i.name));
  for (const n of selected) if (!names.has(n)) selected.delete(n); // deleted elsewhere
  updateSelection();

  // comics
  $("api-key").placeholder = cfg.comics.api_key_set ? t("comics.keySet", { hint: cfg.comics.api_key_hint }) : t("comics.keyUnset");
  $("random-volume").checked = cfg.comics.random_volume;
  if (document.activeElement !== $("rate-limit")) $("rate-limit").value = cfg.comics.rate_limit_per_hour;
  const u = data.comics_meta.api_usage;
  $("api-usage").textContent = t("comics.usage", { ...u, limit: cfg.comics.rate_limit_per_hour });
  renderSearches(cfg);
  if (updateOpenPanel) updateOpenPanel();

  // display: staged until "Aplicar", like the mode section
  if (displayDirty) markDisplayDirty();
  if (!displayDirty) {
    $("fit").value = cfg.display.fit;
    $("border").value = cfg.display.border;
    $("auto-rotate").checked = cfg.display.auto_rotate;
    for (const key of SLIDERS) $(key).value = cfg.display[key];
  }
  for (const key of SLIDERS) $(key).nextElementSibling.textContent = Number($(key).value).toFixed(2);
  setDisplayButtons();
  renderPresets(cfg.display_presets);
}

// ---------- images ----------
// The grid is only rebuilt when something it shows changed, so polling doesn't
// steal the focus or reload thumbnails. The selection lives outside the DOM
// and is painted onto the tiles by updateSelection().

const selected = new Set();
let lastPicked = null; // anchor for shift+click ranges
let imagesKey = "";

function renderImages(cfg, images) {
  const key = lang + JSON.stringify([images, cfg.gallery.images, cfg.mode, cfg.single_image]);
  if (key === imagesKey) return;
  imagesKey = key;
  const inGallery = new Set(cfg.gallery.images);
  $("images").replaceChildren(
    ...images.map((img) => {
      const tile = document.createElement("div");
      tile.className = "tile" + (cfg.single_image === img.name && cfg.mode === "single" ? " current" : "");
      tile.dataset.name = img.name;
      tile.innerHTML = `
        <label class="pick" title="${esc(t("images.select"))}"><input type="checkbox" data-act="select"></label>
        <a href="/images/${encodeURIComponent(img.name)}" target="_blank"><img loading="lazy" src="${img.thumb}" alt=""></a>
        <div class="meta">
          <span class="name" title="${img.name}">${img.name}</span>
          <label><input type="checkbox" data-act="gallery" ${inGallery.has(img.name) ? "checked" : ""}> ${esc(t("images.inGallery"))}</label>
          <div class="actions">
            <button type="button" data-act="show">${esc(t("images.show"))}</button>
            <button type="button" data-act="delete" class="danger">${esc(t("images.delete"))}</button>
          </div>
        </div>`;
      tile.querySelector("[data-act=select]").addEventListener("click", (e) => pick(img.name, e.target.checked, e.shiftKey));
      tile.querySelector("[data-act=gallery]").addEventListener("change", (e) => toggleGallery(img.name, e.target.checked));
      tile.querySelector("[data-act=show]").addEventListener("click", async () =>
        render(await api("POST", `/api/images/${encodeURIComponent(img.name)}/show`)));
      tile.querySelector("[data-act=delete]").addEventListener("click", async () => {
        if (confirm(t("images.confirmDelete", { name: img.name }))) render(await api("DELETE", `/api/images/${encodeURIComponent(img.name)}`));
      });
      return tile;
    })
  );
}

// With shift, everything between the last picked tile and this one follows it.
function pick(name, on, range) {
  const names = data.images.map((i) => i.name);
  const from = range ? names.indexOf(lastPicked) : -1;
  const to = names.indexOf(name);
  const span = from < 0 ? [name] : names.slice(Math.min(from, to), Math.max(from, to) + 1);
  for (const n of span) on ? selected.add(n) : selected.delete(n);
  lastPicked = name;
  updateSelection();
}

function updateSelection() {
  for (const tile of $("images").children) {
    const on = selected.has(tile.dataset.name);
    tile.classList.toggle("selected", on);
    tile.querySelector("[data-act=select]").checked = on;
  }
  $("select-none").disabled = !selected.size;
  $("delete-selected").disabled = !selected.size;
  $("delete-selected").textContent = t("images.deleteSelected", { n: selected.size });
}

function renderPresets(presets) {
  const names = Object.keys(presets);
  $("presets-empty").hidden = names.length > 0;
  $("presets").replaceChildren(
    ...names.map((name) => {
      const p = presets[name];
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="preset-name"></span>
        <span class="preset-values"></span>
        <button type="button" data-act="load"></button>
        <button type="button" data-act="delete" class="danger">×</button>`;
      const fixed = Object.fromEntries(SLIDERS.map((k) => [k, p[k].toFixed(2)]));
      li.querySelector(".preset-values").textContent = t("presets.values", fixed);
      li.querySelector("[data-act=load]").textContent = t("presets.load");
      li.querySelector("[data-act=delete]").title = t("presets.deleteTitle");
      li.querySelector(".preset-name").textContent = name;
      li.querySelector("[data-act=load]").addEventListener("click", () => loadIntoForm(p));
      li.querySelector("[data-act=delete]").addEventListener("click", async () => {
        if (confirm(t("presets.confirmDelete", { name })))
          render(await api("DELETE", `/api/presets/${encodeURIComponent(name)}`));
      });
      return li;
    })
  );
}

// Put values into the display form as a pending change (still needs Aplicar).
function loadIntoForm(values) {
  for (const id of ["fit", "border"]) if (id in values) $(id).value = values[id];
  if ("auto_rotate" in values) $("auto-rotate").checked = values.auto_rotate;
  for (const key of SLIDERS) {
    if (!(key in values)) continue;
    $(key).value = values[key];
    $(key).nextElementSibling.textContent = Number(values[key]).toFixed(2);
  }
  markDisplayDirty();
}

function readDisplayForm() {
  const d = { fit: $("fit").value, border: $("border").value, auto_rotate: $("auto-rotate").checked };
  for (const key of SLIDERS) d[key] = Number($(key).value);
  return d;
}

function markDisplayDirty() {
  const form = readDisplayForm();
  const cfg = data.config.display;
  displayDirty = Object.keys(form).some((k) => form[k] !== cfg[k]);
  setDisplayButtons();
}

function setDisplayButtons() {
  $("display-apply").disabled = !displayDirty;
  $("display-discard").disabled = !displayDirty;
  $("display-pending").hidden = !displayDirty;
}

// ---------- preview rotation (UI only) ----------
// The panel buffer is landscape; images auto-rotated 90° CCW to fit are turned
// back here. The manual offset compensates for how the panel is mounted and is
// remembered per browser.

function loadRotOffset() {
  try {
    return parseInt(localStorage.getItem("previewRotOffset"), 10) || 0;
  } catch {
    return 0;
  }
}

let rotOffset = loadRotOffset();

function setRotOffset(deg) {
  rotOffset = ((deg % 360) + 360) % 360;
  try {
    localStorage.setItem("previewRotOffset", rotOffset);
  } catch {}
  applyPreviewRotation();
}

function applyPreviewRotation() {
  if (!data) return;
  const [w, h] = data.resolution;
  const auto = data.state.preview_rotated ? 90 : 0;
  const rot = (auto + rotOffset) % 360;
  const box = $("preview-box");
  box.style.setProperty("--pw", w);
  box.style.setProperty("--ph", h);
  box.style.setProperty("--inv", h / w);
  box.classList.toggle("quarter", rot % 180 !== 0);
  $("preview").style.setProperty("--rot", `${rot}deg`);
  $("rot-reset").disabled = rotOffset === 0;
}

function toggleGallery(name, on) {
  const set = new Set(data.config.gallery.images);
  on ? set.add(name) : set.delete(name);
  saveConfig({ gallery: { images: [...set] } });
}

// ---------- events ----------

$("btn-refresh").addEventListener("click", async () => render(await api("POST", "/api/refresh")));
$("btn-save-current").addEventListener("click", async () => {
  $("current-msg").textContent = "";
  try {
    render(await api("POST", "/api/current/save", { last_refresh: data.state.last_refresh }));
    $("current-msg").textContent = t("status.savedMsg");
  } catch (err) {
    $("current-msg").textContent = errText(err);
  }
});
$("rot-left").addEventListener("click", () => setRotOffset(rotOffset - 90));
$("rot-right").addEventListener("click", () => setRotOffset(rotOffset + 90));
$("rot-reset").addEventListener("click", () => setRotOffset(0));

document.querySelectorAll("input[name=mode]").forEach((el) => el.addEventListener("change", markModeDirty));
$("interval").addEventListener("input", markModeDirty);
$("refresh-on-start").addEventListener("change", markModeDirty);

$("mode-apply").addEventListener("click", async () => {
  const mode = document.querySelector("input[name=mode]:checked").value;
  const interval = Math.max(data.min_interval, parseInt($("interval").value, 10) || data.min_interval);
  modeDirty = false;
  await saveConfig({ mode, interval_minutes: interval, refresh_on_start: $("refresh-on-start").checked });
});
$("mode-discard").addEventListener("click", () => {
  modeDirty = false;
  render(data);
});

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const files = $("files").files;
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  $("upload-msg").textContent = t("images.uploading");
  try {
    const res = await api("POST", "/api/images", fd);
    $("upload-msg").textContent =
      t("images.uploaded", { n: res.saved.length }) +
      (res.errors.length ? " · " + t("images.uploadErrors", { list: res.errors.map(tErr).join("; ") }) : "");
    $("files").value = "";
    updateChosen();
    render(await api("GET", "/api/status"));
  } catch (err) {
    $("upload-msg").textContent = `Error: ${errText(err)}`;
  }
});

$("gallery-order").addEventListener("change", () => saveConfig({ gallery: { order: $("gallery-order").value } }));
$("gallery-all").addEventListener("click", () => saveConfig({ gallery: { images: data.images.map((i) => i.name) } }));
$("gallery-none").addEventListener("click", () => saveConfig({ gallery: { images: [] } }));

$("select-all").addEventListener("click", () => {
  for (const img of data.images) selected.add(img.name);
  updateSelection();
});
$("select-none").addEventListener("click", () => {
  selected.clear();
  updateSelection();
});
$("delete-selected").addEventListener("click", async () => {
  if (!confirm(t("images.confirmDeleteMany", { n: selected.size }))) return;
  $("selection-msg").textContent = "";
  try {
    render(await api("POST", "/api/images/delete", { names: [...selected] }));
  } catch (err) {
    $("selection-msg").textContent = errText(err);
  }
});

$("save-key").addEventListener("click", async () => {
  const key = $("api-key").value.trim();
  if (!key) return;
  await saveConfig({ comics: { api_key: key } });
  $("api-key").value = "";
});
$("random-volume").addEventListener("change", () => saveConfig({ comics: { random_volume: $("random-volume").checked } }));

$("query-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("query-input").value.trim();
  if (!q) return;
  saveConfig({ comics: { searches: [...data.config.comics.searches, { term: q }] } });
  $("query-input").value = "";
});

for (const id of ["fit", "border", "auto-rotate"]) $(id).addEventListener("change", markDisplayDirty);
for (const key of SLIDERS) {
  const el = $(key);
  el.addEventListener("input", () => {
    el.nextElementSibling.textContent = Number(el.value).toFixed(2);
    markDisplayDirty();
  });
}

$("display-apply").addEventListener("click", async () => {
  const display = readDisplayForm();
  displayDirty = false;
  await saveConfig({ display });
  render(await api("POST", "/api/redraw"));
});
$("display-discard").addEventListener("click", () => {
  displayDirty = false;
  render(data);
});
$("display-defaults").addEventListener("click", () => loadIntoForm(data.display_defaults));

$("preset-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("preset-name").value.trim();
  if (!name) return;
  if (name in data.config.display_presets && !confirm(t("presets.confirmOverwrite", { name }))) return;
  const form = readDisplayForm();
  const values = Object.fromEntries(SLIDERS.map((k) => [k, form[k]]));
  try {
    render(await api("POST", "/api/presets", { name, values }));
    $("preset-name").value = "";
    $("preset-msg").textContent = t("presets.saved", { name });
  } catch (err) {
    $("preset-msg").textContent = errText(err);
  }
});

function updateChosen() {
  const n = $("files").files.length;
  $("files-chosen").textContent = n ? t("images.chosen", { n }) : t("images.noneChosen");
}
$("files").addEventListener("change", updateChosen);

for (const b of document.querySelectorAll("[data-lang]")) {
  b.addEventListener("click", () => {
    setLang(b.dataset.lang);
    // messages from earlier actions were written in the old language
    for (const id of ["current-msg", "upload-msg", "preset-msg", "selection-msg"]) $(id).textContent = "";
    updateChosen();
    if (updateOpenPanel) updateOpenPanel();
    if (data) render(data);
  });
}

applyStaticI18n();
updateChosen();

// ---------- comic searches ----------
// Each search is simple (just a term, like the Pimoroni example) or advanced
// (source, paging, Comic Vine filter/sort, app-side filters, issue picking).
// Only one panel is open at a time, and while it's open polling doesn't
// rebuild the list, so the edits in progress survive.

let openSearchId = null;
let searchesKey = "";
let updateOpenPanel = null; // re-renders dynamic texts of the open panel

// Same fallback as comics._label on the server: what the search is about.
function searchLabel(s) {
  if (s.name) return s.name;
  if (s.term) return s.term;
  if (s.volume_id) return `#${s.volume_id}`;
  if (s.cv_filter) return s.cv_filter;
  return `${s.cover_date_from || "…"} – ${s.cover_date_to || "…"}`;
}

function searchSummary(s) {
  // with a custom name, still show what is actually searched
  const searched = s.name && s.term ? [`"${s.term}"`] : [];
  if (!s.advanced) return searched.join(" · ");
  const parts = [...searched, s.volume_id ? `#${s.volume_id}` : s.source];
  if (s.publishers.length) parts.push(s.publishers.join(", "));
  if (s.year_from || s.year_to) parts.push(`${s.year_from || "…"}–${s.year_to || "…"}`);
  if (s.min_issues) parts.push(`≥${s.min_issues}`);
  if (s.cover_date_from || s.cover_date_to) parts.push(t("adv.coverShort", { from: s.cover_date_from || "…", to: s.cover_date_to || "…" }));
  if (s.jq) parts.push("jq");
  if (isSequential(s)) {
    const entries = Object.values((data.state.sequences || {})[s.id] || {});
    parts.push(entries.length === 1 ? t("adv.seqShort", { n: entries[0].next_number, total: entries[0].total }) : t("adv.seqWord"));
  }
  return parts.join(" · ");
}

function isSequential(s) {
  return s.advanced && (s.source === "issues" ? s.volume_pick === "sequential" : s.issue_pick === "sequential");
}

// "Próximo: #N de M" for each series this search is going through.
function sequenceInfo(id) {
  const entries = Object.values((data.state.sequences || {})[id] || {});
  if (!entries.length) return t("adv.seqNotStarted");
  return entries
    .map((e) => t("adv.seqNext", { n: e.next_number, total: e.total, label: e.label || "?" }))
    .join(" · ");
}

function renderSearches(cfg) {
  const key = lang + JSON.stringify(cfg.comics.searches) + JSON.stringify(data.state.sequences || {});
  if (openSearchId || key === searchesKey) return;
  // Fill defaults (older or hand-edited configs may lack fields) and only mark
  // the list as rendered once it actually rendered.
  const defaults = data.comics_meta.search_defaults;
  $("searches").replaceChildren(...cfg.comics.searches.map((s) => searchItem({ ...defaults, ...s })));
  searchesKey = key;
}

function forceRenderSearches() {
  openSearchId = null;
  updateOpenPanel = null;
  searchesKey = "";
  if (data) render(data);
}

function searchItem(s) {
  const li = document.createElement("li");
  li.dataset.id = s.id;
  li.innerHTML = `
    <div class="search-row">
      <input type="checkbox" data-act="toggle">
      <span class="search-term"></span>
      <span class="badge" hidden></span>
      <span class="search-summary"></span>
      <button type="button" data-act="edit"></button>
      <button type="button" data-act="remove" class="danger">×</button>
    </div>`;
  li.querySelector(".search-term").textContent = searchLabel(s);
  const enabled = s.enabled !== false;
  li.classList.toggle("disabled", !enabled);
  const toggle = li.querySelector("[data-act=toggle]");
  toggle.checked = enabled;
  toggle.title = t(enabled ? "adv.disableTitle" : "adv.enableTitle");
  toggle.addEventListener("change", () =>
    saveConfig({
      comics: {
        searches: data.config.comics.searches.map((x) => (x.id === s.id ? { ...x, enabled: toggle.checked } : x)),
      },
    }));
  const badge = li.querySelector(".badge");
  badge.hidden = !s.advanced;
  badge.textContent = t("adv.badge");
  li.querySelector(".search-summary").textContent = searchSummary(s);
  const edit = li.querySelector("[data-act=edit]");
  edit.textContent = t("adv.configure");
  edit.addEventListener("click", () => openPanel(li, s));
  const remove = li.querySelector("[data-act=remove]");
  remove.title = t("comics.remove");
  remove.addEventListener("click", () => {
    if (s.advanced && !confirm(t("adv.confirmRemove", { term: searchLabel(s) }))) return;
    saveConfig({ comics: { searches: data.config.comics.searches.filter((x) => x.id !== s.id) } });
  });
  return li;
}

const LIST_FIELDS = ["publishers", "exclude_words"];
const NUMBER_FIELDS = ["pages", "page_size", "volume_id", "year_from", "year_to", "min_issues", "cache_hours"];

function fillPanel(panel, s) {
  for (const el of panel.querySelectorAll("[name]")) {
    const v = s[el.name];
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = LIST_FIELDS.includes(el.name) ? (v || []).join(", ") : v ?? "";
  }
}

function readPanel(panel, id) {
  const s = { id };
  for (const el of panel.querySelectorAll("[name]")) {
    if (el.type === "checkbox") s[el.name] = el.checked;
    else if (NUMBER_FIELDS.includes(el.name)) s[el.name] = el.value === "" ? null : Number(el.value);
    else if (LIST_FIELDS.includes(el.name)) s[el.name] = el.value.split(",").map((w) => w.trim()).filter(Boolean);
    else s[el.name] = el.value.trim() || (el.type === "date" ? null : "");
  }
  return s;
}

function updatePanel(panel) {
  const meta = data.comics_meta;
  const f = (name) => panel.querySelector(`[name=${name}]`);
  const advanced = f("advanced").checked;
  const source = f("source").value;
  const issues = source === "issues";
  const show = (sel, on) => panel.querySelectorAll(sel).forEach((el) => (el.hidden = !on));
  panel.querySelector(".adv-fields").hidden = !advanced;
  show(".adv-only", advanced);
  show(".cv-only", source in meta.filter_fields); // search takes no filter/sort
  show(".vol-only", !issues); // issues carry no publisher/year/issue count
  show(".issues-only", issues);

  const max = meta.page_max[source];
  f("page_size").max = max;
  f("pages").max = meta.max_pages;
  if (Number(f("page_size").value) > max) f("page_size").value = max;
  const fixedVolume = f("volume_id").value && !issues; // with issues the id is just a filter
  const calls = fixedVolume ? 1 : Math.min(meta.max_pages, Math.max(1, Number(f("pages").value) || 1));
  const size = Math.min(max, Math.max(1, Number(f("page_size").value) || max));
  panel.querySelector(".cost").textContent = fixedVolume
    ? t("adv.costFixed")
    : t("adv.cost", { calls, results: calls * size, max });
  panel.querySelector(".fields-hint").textContent =
    source in meta.filter_fields
      ? t("adv.fieldsHint", { fields: meta.filter_fields[source].join(", "), sort: meta.sort_fields[source].join(", ") })
      : t("adv.searchHint");
  panel.querySelector(".volume-id-hint").textContent = t(issues ? "adv.volumeIdIssuesHint" : "adv.volumeIdHint");
  panel.querySelector(".volume-pick-label").textContent = t(issues ? "adv.issuesPick" : "adv.volumePick");

  if (!issues && f("volume_pick").value === "sequential") f("volume_pick").value = "random";
  const sequential = issues ? f("volume_pick").value === "sequential" : f("issue_pick").value === "sequential";
  show(".seq-row", advanced && sequential);
  panel.querySelector(".seq-info").textContent = sequenceInfo(panel.dataset.id);

  f("jq").disabled = !meta.jq_available;
  panel.querySelector(".jq-hint").textContent = t(meta.jq_available ? "adv.jqHint" : "adv.jqMissing", {
    kind: t(issues ? "adv.jqIssues" : "adv.jqVolumes"),
  });
}

function openPanel(li, s) {
  if (openSearchId) {
    // only one open panel: discard the other one and find this item again
    forceRenderSearches();
    li = $("searches").querySelector(`li[data-id="${s.id}"]`);
  }
  openSearchId = s.id;
  const panel = $("search-panel-tpl").content.firstElementChild.cloneNode(true);
  panel.dataset.id = s.id;
  applyStaticI18n(panel);
  fillPanel(panel, { ...data.comics_meta.search_defaults, ...s });
  li.append(panel);
  updateOpenPanel = () => updatePanel(panel);
  updateOpenPanel();
  // A new source starts at its own per-call maximum (10 search, 100 volumes/issues).
  const pageSize = panel.querySelector("[name=page_size]");
  if (!pageSize.value) pageSize.value = data.comics_meta.page_max[panel.querySelector("[name=source]").value];
  panel.querySelector("[name=source]").addEventListener("change", (e) => {
    pageSize.value = data.comics_meta.page_max[e.target.value];
  });
  panel.addEventListener("input", updateOpenPanel);
  panel.addEventListener("change", updateOpenPanel);

  const msg = panel.querySelector(".panel-msg");
  const act = (name, fn) =>
    panel.querySelector(`[data-act=${name}]`).addEventListener("click", async () => {
      msg.textContent = "";
      try {
        await fn();
      } catch (err) {
        msg.textContent = errText(err);
      }
    });

  act("save", async () => {
    const current = data.config.comics.searches.find((x) => x.id === s.id);
    // the panel doesn't edit "enabled": keep whatever the row checkbox says
    const edited = { ...readPanel(panel, s.id), enabled: current ? current.enabled !== false : true };
    const searches = data.config.comics.searches.map((x) => (x.id === s.id ? edited : x));
    const next = await api("POST", "/api/config", { comics: { searches } });
    openSearchId = null;
    updateOpenPanel = null;
    searchesKey = "";
    render(next);
  });
  act("cancel", async () => forceRenderSearches());
  act("probe", async () => {
    const search = readPanel(panel, s.id);
    const dry = await api("POST", "/api/comics/probe", { search, dry_run: true });
    if (dry.would_call > 0 && !confirm(t("adv.confirmCalls", { n: dry.would_call }))) return;
    msg.textContent = t("adv.probing");
    const res = await api("POST", "/api/comics/probe", { search, dry_run: false });
    msg.textContent = "";
    showProbe(panel.querySelector(".probe-out"), res);
    poll(); // refresh the API usage counter
  });
  act("reset-seq", async () => {
    render(await api("POST", "/api/comics/sequence/reset", { id: s.id }));
    updateOpenPanel();
    msg.textContent = t("adv.seqResetDone");
  });
  act("clear-cache", async () => {
    await api("POST", "/api/comics/cache/clear", { search: readPanel(panel, s.id) });
    msg.textContent = t("adv.cacheCleared");
  });
}

function showProbe(out, r) {
  out.hidden = false;
  const age = Math.round((Date.now() / 1000 - r.fetched_at) / 60);
  const head = document.createElement("p");
  head.textContent =
    t(r.kind === "issues" ? "adv.probeSummaryIssues" : "adv.probeSummary", {
      fetched: r.fetched,
      total: r.total ?? "?",
      passed: r.passed,
    }) +
    " · " +
    (r.cached ? t("adv.fromCache", { minutes: age }) : t("adv.fresh", { calls: r.calls }));

  const table = document.createElement("table");
  table.className = "probe-table";
  const hdr = table.insertRow();
  const issues = r.kind === "issues";
  const cols = issues
    ? ["adv.colIssue", "adv.colCoverDate", "adv.colId"]
    : ["adv.colName", "adv.colYear", "adv.colPublisher", "adv.colIssues", "adv.colId"];
  for (const k of cols) {
    const th = document.createElement("th");
    th.textContent = t(k);
    hdr.append(th);
  }
  for (const c of r.candidates) {
    const row = table.insertRow();
    const name = row.insertCell();
    if (c.url) {
      const a = document.createElement("a");
      a.href = c.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = c.name;
      name.append(a);
    } else name.textContent = c.name;
    const rest = issues ? [c.cover_date, c.id] : [c.start_year, c.publisher, c.count_of_issues, c.id];
    for (const v of rest) row.insertCell().textContent = v ?? "—";
  }

  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = t("adv.curl", { n: r.curl.length });
  const pre = document.createElement("pre");
  pre.textContent = r.curl.join("\n\n");
  details.append(summary, pre);

  const more = document.createElement("small");
  more.className = "hint";
  more.textContent = r.passed > r.candidates.length ? t("adv.moreRows", { n: r.passed - r.candidates.length }) : "";
  out.replaceChildren(head, r.candidates.length ? table : "", more, details);
}

$("rate-limit").addEventListener("change", () =>
  saveConfig({ comics: { rate_limit_per_hour: Number($("rate-limit").value) } }));

// ---------- polling ----------

async function poll() {
  try {
    render(await api("GET", "/api/status"));
  } catch (err) {
    console.error(err);
  }
}
poll();
setInterval(poll, 5000);
