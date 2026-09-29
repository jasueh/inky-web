# inky-web

Web UI ligera para controlar una **Pimoroni Inky Impression 13.3"** (Spectra 6, 1600×1200) desde el navegador.

- **Imagen única**: elegir una imagen subida y dejarla fija.
- **Galería**: rotar entre las imágenes marcadas, en orden aleatorio o secuencial.
- **Cómics random**: portadas al azar desde la API de [Comic Vine](https://comicvine.gamespot.com/api/) (adaptado del ejemplo `examples/spectra6/comics` de `pimoroni/inky`).
  - Búsquedas **simples** (como el ejemplo de Pimoroni: `/search/`, 5 volúmenes, primeros 100 números) o **avanzadas**: fuente `search` o `volumes`, filtro y orden de Comic Vine, paginado configurable, filtros en la app (editoriales, año de inicio, mínimo de números, palabras excluidas), serie fija por ID, fecha de portada y número al azar entre **todos** los de la serie.
  - La lista de series de cada búsqueda avanzada se guarda en caché (`data/cache/`, 24 h por defecto); cambiar filtros de la app no hace llamadas. "Probar" muestra los candidatos y el `curl` equivalente.
  - Todas las llamadas pasan por un contador por endpoint con tope configurable (150/h por defecto; Comic Vine permite 200 por endpoint por hora) y se espacian 1 s.
- Frecuencia de rotación configurable (mínimo 2 min, un refresco completo tarda ~30-40 s).
- No redibuja al iniciar la app (la tinta e-ink conserva la imagen): retoma la rotación desde el último refresco. Se puede activar "Refrescar al iniciar la app" en la sección Modo.
- Gestión de imágenes: subir (varias a la vez), mostrar, borrar, incluir/excluir de la galería.
- API key y lista de búsquedas de Comic Vine editables desde la UI.
- Ajuste de pantalla: mantener aspect ratio con bordes o recortar, rotación automática de imágenes verticales, realce de color/contraste/brillo y saturación de paleta Inky. Por defecto no se realza nada (1.0 / 1.0 / 1.0, paleta 0.5, igual que los ejemplos de Pimoroni).
- Perfiles de ajuste: guardar combinaciones de color/contraste/brillo/paleta con nombre y volver a cargarlas.

- Interfaz en español o inglés (selector ES/EN arriba a la derecha; se recuerda por navegador).

Sin autenticación: pensado para uso en LAN.

## Estructura

```
app.py                Flask app + API JSON
inkyweb/config.py     config.json / state.json persistentes (en data/)
inkyweb/display.py    preparación de imagen + driver Inky (o mock)
inkyweb/comics.py     cliente Comic Vine
inkyweb/scheduler.py  thread que refresca según el modo
templates/, static/   UI (HTML + JS vanilla)
inky-web.service      unit de systemd
data/                 (no versionado) imágenes, thumbnails, config, preview
```

## Instalación en la Raspberry Pi

Requiere el venv de Pimoroni con la librería `inky` ya instalada (`~/.virtualenvs/pimoroni`).

```bash
git clone <repo> ~/inky-web
cd ~/inky-web
~/.virtualenvs/pimoroni/bin/pip install -r requirements.txt
```

Probar a mano:

```bash
~/.virtualenvs/pimoroni/bin/python app.py
# http://eInkPI.local:8080
```

Como servicio:

```bash
sudo cp inky-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now inky-web
journalctl -u inky-web -f
```

Si el script de cómics de Pimoroni (u otro) está corriendo por cron, desactivarlo: solo un proceso debe manejar la pantalla.

## Desarrollo sin hardware

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
INKY_MOCK=1 .venv/bin/python app.py
```

En modo mock la imagen procesada solo se escribe en `data/current.png` (visible en la UI).

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `INKY_WEB_PORT` | `8080` | Puerto HTTP |
| `INKY_WEB_HOST` | `0.0.0.0` | Interfaz de escucha |
| `INKY_WEB_DATA` | `./data` | Carpeta de imágenes, config y estado |
| `INKY_MOCK` | — | `1` para correr sin pantalla |

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/status` | Config (sin API key), estado, lista de imágenes |
| POST | `/api/config` | Actualización parcial de config (JSON) |
| POST | `/api/refresh` | Refrescar ahora (siguiente imagen según el modo) |
| POST | `/api/redraw` | Redibujar la imagen actual con los ajustes de pantalla vigentes |
| POST | `/api/comics/probe` | Probar una búsqueda avanzada (`{"search": {...}, "dry_run": true}` solo informa cuántas llamadas haría) |
| POST | `/api/comics/cache/clear` | Vaciar el caché de una búsqueda (`{"search": {...}}`) |
| POST | `/api/presets` | Guardar/sobrescribir un perfil (`{"name": ..., "values": {color, contrast, brightness, saturation}}`) |
| DELETE | `/api/presets/<name>` | Borrar un perfil |
| POST | `/api/images` | Subir imágenes (`multipart`, campo `files`) |
| DELETE | `/api/images/<name>` | Borrar imagen |
| POST | `/api/images/<name>/show` | Pasar a modo imagen única con esa imagen |
| POST | `/api/current/save` | Guardar la portada de cómic en pantalla en la galería (`{"last_refresh": ...}`) |
| GET | `/current/download` | Descargar el original de la imagen en pantalla (JPEG) |

Los errores de la API se devuelven como `{"error": {"code": ..., "params": {...}, "message": ...}}`; la UI traduce `code` (ver `static/i18n.js`) y usa `message` (inglés) como respaldo.
