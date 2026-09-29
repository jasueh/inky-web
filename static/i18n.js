// UI strings. Keys are referenced from the HTML (data-i18n, data-i18n-title,
// data-i18n-placeholder, data-i18n-alt) and from app.js via t(). Error codes
// sent by the server are looked up as "err.<code>".

const I18N = {
  es: {
    "lang.title": "Idioma",
    "header.busy": "Actualizando pantalla…",

    "status.title": "En pantalla",
    "status.previewAlt": "Vista previa de la pantalla",
    "status.rotLeft": "Girar vista previa a la izquierda",
    "status.rotRight": "Girar vista previa a la derecha",
    "status.rotReset": "Volver a la orientación automática",
    "status.rotHint": "Solo gira la vista previa, no la pantalla.",
    "status.mode": "Modo",
    "status.showing": "Mostrando",
    "status.last": "Último refresco",
    "status.next": "Próximo refresco",
    "status.resolution": "Resolución",
    "status.refresh": "Refrescar ahora",
    "status.save": "Guardar en galería",
    "status.saved": "Guardada ✓",
    "status.savedMsg": "Guardada en la galería",
    "status.download": "Descargar",

    "common.apply": "Aplicar",
    "common.discard": "Descartar",
    "common.pending": "Cambios sin aplicar",

    "mode.title": "Modo",
    "mode.single": "Imagen única",
    "mode.gallery": "Galería",
    "mode.comics": "Cómics random",
    "mode.every": "Cambiar cada",
    "mode.minutes": "minutos",
    "mode.min": "(mínimo {n})",
    "mode.hint": "La frecuencia aplica a Galería y Cómics. En Imagen única la pantalla no rota.",
    "mode.refreshOnStart": "Refrescar al iniciar la app",
    "mode.refreshOnStartHint": "(apagado: la pantalla conserva la imagen y no se llama a Comic Vine al arrancar)",

    "images.title": "Imágenes",
    "images.choose": "Elegir archivos",
    "images.noneChosen": "Ningún archivo elegido",
    "images.chosen": "{n} archivo(s) elegido(s)",
    "images.upload": "Subir",
    "images.uploading": "Subiendo…",
    "images.uploaded": "{n} subida(s)",
    "images.uploadErrors": "errores: {list}",
    "images.order": "Orden de la galería",
    "images.random": "Aleatorio",
    "images.sequential": "Secuencial",
    "images.all": "Todas en galería",
    "images.none": "Ninguna",
    "images.empty": "Todavía no hay imágenes.",
    "images.inGallery": "En galería",
    "images.show": "Mostrar",
    "images.delete": "Borrar",
    "images.confirmDelete": "¿Borrar {name}?",

    "comics.title": "Cómics (Comic Vine)",
    "comics.apiKey": "API key",
    "comics.keySet": "configurada ({hint})",
    "comics.keyUnset": "sin configurar",
    "comics.save": "Guardar",
    "comics.randomVolume": "Volumen aleatorio (entre los 5 primeros resultados)",
    "comics.searches": "Búsquedas",
    "comics.queryPlaceholder": "Ej: Weird Science",
    "comics.add": "Agregar",
    "comics.remove": "Quitar",

    "display.title": "Pantalla",
    "display.fit": "Ajuste",
    "display.contain": "Completa (bordes)",
    "display.fill": "Llenar (recortar)",
    "display.border": "Color de bordes",
    "display.white": "Blanco",
    "display.black": "Negro",
    "display.autoRotate": "Rotar imágenes verticales",
    "display.color": "Saturación de color",
    "display.contrast": "Contraste",
    "display.brightness": "Brillo",
    "display.saturation": "Paleta Inky (saturation)",
    "display.hint":
      "Aplicar vuelve a dibujar la imagen que está en pantalla con estos valores, para comparar. No cambia el horario de rotación.",
    "display.defaults": "Valores de Pimoroni",
    "display.defaultsTitle": "Sin realce: color, contraste y brillo 1.0, paleta 0.5 (default de la librería inky)",

    "presets.title": "Perfiles",
    "presets.hint": "Guardan color, contraste, brillo y paleta. Cargar un perfil lo deja pendiente: después Aplicar.",
    "presets.empty": "Todavía no hay perfiles guardados.",
    "presets.namePlaceholder": "Nombre del perfil (ej: Phantom)",
    "presets.save": "Guardar valores actuales",
    "presets.saved": "Perfil \"{name}\" guardado",
    "presets.load": "Cargar",
    "presets.deleteTitle": "Borrar perfil",
    "presets.values": "color {color} · contraste {contrast} · brillo {brightness} · paleta {saturation}",
    "presets.confirmDelete": "¿Borrar el perfil \"{name}\"?",
    "presets.confirmOverwrite": "Ya existe \"{name}\". ¿Sobrescribirlo?",

    "err.invalid_mode": "Modo inválido",
    "err.unknown_image": "Imagen inexistente",
    "err.preset_name": "El nombre debe tener entre 1 y {max} caracteres",
    "err.preset_values": "Faltan valores o no son números",
    "err.preset_not_found": "Perfil inexistente",
    "err.panel_busy": "La pantalla se está actualizando; esperá a que termine",
    "err.not_a_comic": "Solo se pueden guardar portadas de cómics",
    "err.image_changed": "La imagen en pantalla cambió; revisá y volvé a intentar",
    "err.no_current_image": "No hay imagen actual guardada",
    "err.unsupported_type": "{file}: tipo de archivo no soportado",
    "err.invalid_image": "{file}: no es una imagen válida ({detail})",
    "err.no_redraw_source": "No hay imagen actual para redibujar; esperá al próximo refresco",
    "err.gallery_empty": "La galería está vacía",
    "err.api_key_missing": "Falta configurar la API key de Comic Vine",
    "err.no_queries": "No hay búsquedas configuradas",
    "err.no_volumes": "No se encontraron volúmenes para \"{query}\"",
    "err.no_issues": "No se encontraron números para el volumen {volume}",
  },

  en: {
    "lang.title": "Language",
    "header.busy": "Updating display…",

    "status.title": "On screen",
    "status.previewAlt": "Display preview",
    "status.rotLeft": "Rotate preview left",
    "status.rotRight": "Rotate preview right",
    "status.rotReset": "Back to automatic orientation",
    "status.rotHint": "Only rotates the preview, not the display.",
    "status.mode": "Mode",
    "status.showing": "Showing",
    "status.last": "Last refresh",
    "status.next": "Next refresh",
    "status.resolution": "Resolution",
    "status.refresh": "Refresh now",
    "status.save": "Save to gallery",
    "status.saved": "Saved ✓",
    "status.savedMsg": "Saved to the gallery",
    "status.download": "Download",

    "common.apply": "Apply",
    "common.discard": "Discard",
    "common.pending": "Unapplied changes",

    "mode.title": "Mode",
    "mode.single": "Single image",
    "mode.gallery": "Gallery",
    "mode.comics": "Random comics",
    "mode.every": "Change every",
    "mode.minutes": "minutes",
    "mode.min": "(minimum {n})",
    "mode.hint": "The interval applies to Gallery and Comics. In Single image the display doesn't rotate.",
    "mode.refreshOnStart": "Refresh when the app starts",
    "mode.refreshOnStartHint": "(off: the display keeps its image and Comic Vine isn't called on startup)",

    "images.title": "Images",
    "images.choose": "Choose files",
    "images.noneChosen": "No files chosen",
    "images.chosen": "{n} file(s) chosen",
    "images.upload": "Upload",
    "images.uploading": "Uploading…",
    "images.uploaded": "{n} uploaded",
    "images.uploadErrors": "errors: {list}",
    "images.order": "Gallery order",
    "images.random": "Random",
    "images.sequential": "Sequential",
    "images.all": "All in gallery",
    "images.none": "None",
    "images.empty": "No images yet.",
    "images.inGallery": "In gallery",
    "images.show": "Show",
    "images.delete": "Delete",
    "images.confirmDelete": "Delete {name}?",

    "comics.title": "Comics (Comic Vine)",
    "comics.apiKey": "API key",
    "comics.keySet": "set ({hint})",
    "comics.keyUnset": "not set",
    "comics.save": "Save",
    "comics.randomVolume": "Random volume (among the top 5 results)",
    "comics.searches": "Searches",
    "comics.queryPlaceholder": "e.g. Weird Science",
    "comics.add": "Add",
    "comics.remove": "Remove",

    "display.title": "Display",
    "display.fit": "Fit",
    "display.contain": "Whole image (borders)",
    "display.fill": "Fill (crop)",
    "display.border": "Border colour",
    "display.white": "White",
    "display.black": "Black",
    "display.autoRotate": "Rotate portrait images",
    "display.color": "Colour saturation",
    "display.contrast": "Contrast",
    "display.brightness": "Brightness",
    "display.saturation": "Inky palette (saturation)",
    "display.hint":
      "Apply redraws the image on screen with these values, so you can compare. It doesn't change the rotation schedule.",
    "display.defaults": "Pimoroni values",
    "display.defaultsTitle": "No enhancement: colour, contrast and brightness 1.0, palette 0.5 (inky library default)",

    "presets.title": "Presets",
    "presets.hint": "They store colour, contrast, brightness and palette. Loading a preset leaves it pending: then Apply.",
    "presets.empty": "No saved presets yet.",
    "presets.namePlaceholder": "Preset name (e.g. Phantom)",
    "presets.save": "Save current values",
    "presets.saved": "Preset \"{name}\" saved",
    "presets.load": "Load",
    "presets.deleteTitle": "Delete preset",
    "presets.values": "colour {color} · contrast {contrast} · brightness {brightness} · palette {saturation}",
    "presets.confirmDelete": "Delete preset \"{name}\"?",
    "presets.confirmOverwrite": "\"{name}\" already exists. Overwrite it?",

    "err.invalid_mode": "Invalid mode",
    "err.unknown_image": "Unknown image",
    "err.preset_name": "The name must be 1 to {max} characters long",
    "err.preset_values": "Missing or non-numeric values",
    "err.preset_not_found": "Preset not found",
    "err.panel_busy": "The display is updating; wait for it to finish",
    "err.not_a_comic": "Only comic covers can be saved",
    "err.image_changed": "The image on screen changed; check and try again",
    "err.no_current_image": "No current image saved",
    "err.unsupported_type": "{file}: unsupported file type",
    "err.invalid_image": "{file}: not a valid image ({detail})",
    "err.no_redraw_source": "No current image to redraw; wait for the next refresh",
    "err.gallery_empty": "The gallery is empty",
    "err.api_key_missing": "The Comic Vine API key is not set",
    "err.no_queries": "No search queries configured",
    "err.no_volumes": "No volumes found for \"{query}\"",
    "err.no_issues": "No issues found for volume {volume}",
  },
};

const LANGS = Object.keys(I18N);

function loadLang() {
  try {
    const saved = localStorage.getItem("lang");
    if (LANGS.includes(saved)) return saved;
  } catch {}
  return "es";
}

let lang = loadLang();

function t(key, params = {}) {
  const s = I18N[lang][key] ?? I18N.es[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? params[k] : m));
}

// Server errors: {code, params, message}. Unknown codes fall back to the
// server's (English) message.
function tErr(err) {
  if (!err) return "";
  if (typeof err === "string") return err; // state saved by an older version
  const key = `err.${err.code}`;
  return err.code && key in I18N[lang] ? t(key, err.params || {}) : err.message;
}

function applyStaticI18n() {
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-title]")) el.title = t(el.dataset.i18nTitle);
  for (const el of document.querySelectorAll("[data-i18n-placeholder]")) el.placeholder = t(el.dataset.i18nPlaceholder);
  for (const el of document.querySelectorAll("[data-i18n-alt]")) el.alt = t(el.dataset.i18nAlt);
  for (const b of document.querySelectorAll("[data-lang]")) b.setAttribute("aria-pressed", b.dataset.lang === lang);
}

function setLang(next) {
  if (!LANGS.includes(next)) return;
  lang = next;
  try {
    localStorage.setItem("lang", lang);
  } catch {}
  applyStaticI18n();
}
