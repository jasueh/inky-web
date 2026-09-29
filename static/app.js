const $ = (id) => document.getElementById(id);
const MODE_LABELS = { single: "Imagen única", gallery: "Galería", comics: "Cómics random" };
const SLIDERS = ["color", "contrast", "brightness", "saturation"];

let data = null;

async function api(method, url, body) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

const saveConfig = async (patch) => render(await api("POST", "/api/config", patch));

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function describe(state) {
  const d = state.last_detail;
  if (!d) return "—";
  if (state.last_source === "comics") {
    const title = esc(`${d.volume} #${d.issue_number ?? "?"}`);
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
  $("st-mode").textContent = MODE_LABELS[cfg.mode];
  $("st-detail").innerHTML = describe(state);
  $("st-last").textContent = fmtTime(state.last_refresh);
  $("st-next").textContent = state.next_refresh ? fmtTime(state.next_refresh) : "—";
  $("st-res").textContent = data.resolution.join("×");
  $("st-error").hidden = !state.last_error;
  $("st-error").textContent = state.last_error || "";
  const ts = state.last_refresh || "";
  if (ts !== $("preview").dataset.ts) {
    $("preview").dataset.ts = ts;
    if (ts) $("preview").src = `/preview.png?t=${encodeURIComponent(ts)}`;
  }
  applyPreviewRotation();

  // mode
  document.querySelector(`input[name=mode][value=${cfg.mode}]`).checked = true;
  if (document.activeElement !== $("interval")) $("interval").value = cfg.interval_minutes;
  $("interval").min = data.min_interval;
  $("interval-hint").textContent = `(mínimo ${data.min_interval})`;

  // images
  $("gallery-order").value = cfg.gallery.order;
  const inGallery = new Set(cfg.gallery.images);
  $("images-empty").hidden = images.length > 0;
  $("images").replaceChildren(
    ...images.map((img) => {
      const tile = document.createElement("div");
      tile.className = "tile" + (cfg.single_image === img.name && cfg.mode === "single" ? " current" : "");
      tile.innerHTML = `
        <a href="/images/${encodeURIComponent(img.name)}" target="_blank"><img loading="lazy" src="${img.thumb}" alt=""></a>
        <div class="meta">
          <span class="name" title="${img.name}">${img.name}</span>
          <label><input type="checkbox" ${inGallery.has(img.name) ? "checked" : ""}> En galería</label>
          <div class="actions">
            <button type="button" data-act="show">Mostrar</button>
            <button type="button" data-act="delete" class="danger">Borrar</button>
          </div>
        </div>`;
      tile.querySelector("input").addEventListener("change", (e) => toggleGallery(img.name, e.target.checked));
      tile.querySelector("[data-act=show]").addEventListener("click", async () =>
        render(await api("POST", `/api/images/${encodeURIComponent(img.name)}/show`)));
      tile.querySelector("[data-act=delete]").addEventListener("click", async () => {
        if (confirm(`¿Borrar ${img.name}?`)) render(await api("DELETE", `/api/images/${encodeURIComponent(img.name)}`));
      });
      return tile;
    })
  );

  // comics
  $("api-key").placeholder = cfg.comics.api_key_set ? `configurada (${cfg.comics.api_key_hint})` : "sin configurar";
  $("random-volume").checked = cfg.comics.random_volume;
  $("queries").replaceChildren(
    ...cfg.comics.queries.map((q, i) => {
      const li = document.createElement("li");
      li.textContent = q;
      const b = document.createElement("button");
      b.type = "button";
      b.title = "Quitar";
      b.textContent = "×";
      b.addEventListener("click", () => {
        const queries = cfg.comics.queries.filter((_, j) => j !== i);
        saveConfig({ comics: { queries } });
      });
      li.append(b);
      return li;
    })
  );

  // display
  $("fit").value = cfg.display.fit;
  $("border").value = cfg.display.border;
  $("auto-rotate").checked = cfg.display.auto_rotate;
  for (const key of SLIDERS) {
    const el = $(key);
    if (document.activeElement !== el) el.value = cfg.display[key];
    el.nextElementSibling.textContent = Number(el.value).toFixed(2);
  }
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
$("rot-left").addEventListener("click", () => setRotOffset(rotOffset - 90));
$("rot-right").addEventListener("click", () => setRotOffset(rotOffset + 90));
$("rot-reset").addEventListener("click", () => setRotOffset(0));

document.querySelectorAll("input[name=mode]").forEach((el) =>
  el.addEventListener("change", () => saveConfig({ mode: el.value })));

$("interval").addEventListener("change", () => {
  const v = Math.max(data.min_interval, parseInt($("interval").value, 10) || data.min_interval);
  saveConfig({ interval_minutes: v });
});

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const files = $("files").files;
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  $("upload-msg").textContent = "Subiendo…";
  try {
    const res = await api("POST", "/api/images", fd);
    $("upload-msg").textContent = `${res.saved.length} subida(s)` + (res.errors.length ? ` · errores: ${res.errors.join("; ")}` : "");
    $("files").value = "";
    render(await api("GET", "/api/status"));
  } catch (err) {
    $("upload-msg").textContent = `Error: ${err.message}`;
  }
});

$("gallery-order").addEventListener("change", () => saveConfig({ gallery: { order: $("gallery-order").value } }));
$("gallery-all").addEventListener("click", () => saveConfig({ gallery: { images: data.images.map((i) => i.name) } }));
$("gallery-none").addEventListener("click", () => saveConfig({ gallery: { images: [] } }));

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
  saveConfig({ comics: { queries: [...data.config.comics.queries, q] } });
  $("query-input").value = "";
});

$("fit").addEventListener("change", () => saveConfig({ display: { fit: $("fit").value } }));
$("border").addEventListener("change", () => saveConfig({ display: { border: $("border").value } }));
$("auto-rotate").addEventListener("change", () => saveConfig({ display: { auto_rotate: $("auto-rotate").checked } }));
for (const key of SLIDERS) {
  const el = $(key);
  el.addEventListener("input", () => (el.nextElementSibling.textContent = Number(el.value).toFixed(2)));
  el.addEventListener("change", () => saveConfig({ display: { [key]: Number(el.value) } }));
}

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
