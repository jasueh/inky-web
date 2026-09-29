# inky-web

[English](README.md) · **Español**

Web UI liviana para manejar una **Pimoroni Inky Impression 13.3"** (Spectra 6, 1600×1200) desde el navegador: subir y gestionar imágenes, rotar una galería o mostrar portadas de cómics al azar desde [Comic Vine](https://comicvine.gamespot.com/api/).

No tiene autenticación: está pensada solo para usar en tu red local.

## Funciones

**Modos**
- **Imagen única:** elegís una imagen subida y queda fija en la pantalla.
- **Galería:** rota entre las imágenes marcadas, en orden aleatorio o secuencial.
- **Cómics random:** portadas al azar desde Comic Vine (basado en el ejemplo `examples/spectra6/comics` de [`pimoroni/inky`](https://github.com/pimoroni/inky)).
- **Frecuencia configurable** (mínimo 2 minutos; un refresco completo del panel tarda unos 30–40 s). Los cambios de modo y frecuencia pasan por **Aplicar / Descartar**, así un clic accidental no refresca el panel.
- **No redibuja al arrancar:** la tinta e-ink conserva la imagen sin corriente, así que la app retoma la rotación desde el último refresco. Se puede activar "Refrescar al iniciar la app".

**Imágenes**
- Subir varias a la vez, mostrarlas, borrarlas e incluirlas o excluirlas de la galería.
- **Guardar el cómic en pantalla** en la galería (la portada original, con un nombre legible) o **descargar** lo que esté en pantalla.

**Pantalla**
- **Mantiene el aspect ratio:** la imagen completa con bordes, o llenando el panel y recortando. Las imágenes verticales se giran automáticamente.
- **Color, contraste, brillo y saturación de la paleta Inky.** Los valores por defecto son neutros (1.0 / 1.0 / 1.0, paleta 0.5), iguales a los ejemplos de Pimoroni, y hay un botón "Valores de Pimoroni" para volver a ellos.
- **Aplicar redibuja la imagen que está en pantalla** con los valores nuevos, para comparar ajustes. No cambia el horario de rotación.
- **Perfiles:** guardar combinaciones de color / contraste / brillo / paleta con un nombre y volver a cargarlas.
- **Vista previa derecha:** la vista previa de la web deshace el giro automático, con botones ⟲ / ⟳ para ajustarla (solo en la web; se recuerda por navegador).

**Búsquedas de cómics**
- **Las búsquedas simples** se comportan exactamente como el ejemplo de Pimoroni: `/search/`, 5 volúmenes, el primero (o uno al azar), y un número al azar entre los primeros 100 de ese volumen.
- **Las búsquedas avanzadas** agregan:
  - **Fuente:** `search` (búsqueda de texto por relevancia), `volumes` (filtro por nombre) o `issues` (números directamente, por ejemplo todas las portadas de un rango de fechas).
  - **Consulta a Comic Vine:** filtro y orden (solo sobre los campos que acepta la API) y páginas × resultados configurables.
  - **Filtros en la app:** editoriales, año de inicio de la serie, mínimo de números y palabras a excluir del título.
  - **Elección:** serie fija por ID, rango de fecha de portada, y el número elegido entre **todos** los de la serie.
  - **Expresión jq opcional** sobre la lista de candidatos.
- **Caché:** la lista de candidatos de cada búsqueda avanzada se guarda (24 h por defecto, en `data/cache/`). Cambiar los filtros de la app o jq no gasta llamadas a la API.
- **Probar:** muestra los candidatos y el `curl` equivalente, y pide confirmación antes de gastar llamadas.
- **Nombre:** cada búsqueda puede tener un nombre propio (se muestra en la lista y en "Mostrando" en lugar del término o el ID).
- **Activar / desactivar:** cada búsqueda se puede prender o apagar sin perder su configuración.
- La API key, las búsquedas y el tope de llamadas se editan desde la web.

**Interfaz** en español o inglés (selector ES/EN arriba a la derecha; se recuerda por navegador).

## Requisitos

- Una Raspberry Pi con la Inky Impression 13.3" y el venv de Pimoroni con la librería `inky` instalada (su instalador crea `~/.virtualenvs/pimoroni`).
- Una API key gratuita de Comic Vine, solo para el modo cómics: https://comicvine.gamespot.com/api/
- `jq` (`sudo apt install jq`), solo para las expresiones jq de las búsquedas avanzadas.

## Instalación en la Pi

```bash
git clone <repo> ~/inky-web
cd ~/inky-web
~/.virtualenvs/pimoroni/bin/pip install -r requirements.txt
```

Para probarla a mano:

```bash
~/.virtualenvs/pimoroni/bin/python app.py
# http://<hostname-de-la-pi>.local:8080
```

En el log tiene que aparecer `Inky display detected: ...`. Si en cambio dice `running in mock mode`, la app no está usando el venv que tiene la librería `inky`.

Como servicio (la unidad asume el usuario `jasueh`, `~/inky-web` y el venv de Pimoroni; ajustá `inky-web.service` si en tu caso es distinto):

```bash
sudo cp inky-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now inky-web
journalctl -u inky-web -f
```

Si el script de cómics de Pimoroni u otra cosa maneja el panel (por cron, otro servicio, etc.), desactivalo: la pantalla la tiene que usar un solo proceso.

## Actualizar

```bash
cd ~/inky-web && git pull && sudo systemctl restart inky-web
```

Recargá la página con `Ctrl+Shift+R` para que el navegador baje el JS nuevo.

## Imágenes copiadas a mano

Podés copiar archivos directo a `data/images/` (por ejemplo con `scp`) y aparecen en la web. Dos salvedades:
- **No se crea la miniatura:** las miniaturas solo se generan al subir desde la web, así que el cuadro se ve como imagen rota. Subí el archivo desde la web, o creá la miniatura en `data/thumbs/<nombre>.jpg` (máx. 400×300).
- **El nombre tiene que ser "seguro":** sin espacios ni acentos (`secure_filename` de Werkzeug). Si no, la app lista el archivo pero no deja mostrarlo ni borrarlo.

Algunas imágenes de ejemplo de Pimoroni (por ejemplo `examples/spectra6/images/vincent-van-gogh-inky13.jpg`) ya vienen giradas para el buffer horizontal del panel. Ponelas derechas antes de usarlas acá, así las gira la app.

## Comic Vine: notas de la API

Según la documentación oficial (comicvine.gamespot.com/api y /api/documentation):
- **Límite:** 200 llamadas por **endpoint** por hora, más "velocity detection" (bloqueos temporales si hay demasiadas llamadas por segundo). La app espacia sus llamadas 1 s y aplica un tope propio configurable (150/h por endpoint por defecto). La web muestra las llamadas de la última hora.
- **`/search/`:** devuelve como máximo **10 resultados por llamada** y **no acepta `filter` ni `sort`**. **Ignora `offset`**, aunque la documentación lo liste (`offset=10` responde `"offset":0` con los mismos resultados); pagina con el parámetro **`page`** (empieza en 1), que es el que usa la app. Si una página no trae nada nuevo, la app deja de paginar en vez de gastar más llamadas.
- **`/volumes/` y `/issues/`:** devuelven hasta 100 por llamada y aceptan `filter=campo:valor,...` solo sobre estos campos:

| Endpoint | Filtrables | Ordenables |
|---|---|---|
| `/volumes/` | `name`, `id`, `date_added`, `date_last_updated` | los mismos |
| `/issues/` | `name`, `aliases`, `id`, `issue_number`, `volume`, `cover_date`, `store_date`, `date_added`, `date_last_updated` | todos salvo `aliases` y `volume` |

- **La editorial, el año de inicio y la cantidad de números no se pueden filtrar en la consulta.** Por eso los filtra la app. Por ejemplo, una búsqueda de `wolverine` devuelve primero la edición italiana de Panini, antes que la de Marvel.
- La documentación no aclara si `filter=name:` busca "contiene" o el nombre exacto, ni el formato exacto de fecha de `cover_date` (la app usa `AAAA-MM-DD|AAAA-MM-DD`).

**Expresiones jq:** jq puede leer archivos (`import` / `include` de módulos `.jq` / `.json`, por ejemplo `data/config.json` con la API key) y el entorno (`env`, `$ENV`), y una expresión que empieza con `-` se interpretaría como opción de línea de comandos. La app rechaza esas expresiones y corre jq con el entorno vacío, en un directorio temporal y con un timeout de 5 s. El resultado tiene que ser una sola lista.

## Desarrollo sin hardware

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
INKY_MOCK=1 .venv/bin/python app.py
```

En modo mock la imagen procesada solo se escribe en `data/current.png` (se ve como vista previa en la web).

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `INKY_WEB_PORT` | `8080` | Puerto HTTP |
| `INKY_WEB_HOST` | `0.0.0.0` | Interfaz de escucha |
| `INKY_WEB_DATA` | `./data` | Carpeta de imágenes, config, estado y caché |
| `INKY_MOCK` | — | `1` para correr sin pantalla |

## Estructura del proyecto

```
app.py                  app Flask + API JSON
inkyweb/config.py       config.json / state.json persistentes (en data/), migraciones
inkyweb/display.py      preparación de imagen + driver Inky (o mock)
inkyweb/scheduler.py    thread en segundo plano: refresca / redibuja según el modo
inkyweb/comics.py       búsquedas simples y avanzadas de cómics, caché, jq, "Probar"
inkyweb/cvapi.py        cliente de Comic Vine: espaciado de llamadas, tope por endpoint, curl
inkyweb/errors.py       errores con código que traduce la web
templates/, static/     web (HTML + JS sin frameworks); textos en static/i18n.js
inky-web.service        unidad de systemd
data/                   (no versionado) imágenes, miniaturas, config, estado, caché, vista previa
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/status` | Config (sin la API key), estado, imágenes, uso de la API |
| POST | `/api/config` | Actualización parcial de la config (JSON) |
| POST | `/api/refresh` | Refrescar ahora (siguiente imagen según el modo) |
| POST | `/api/redraw` | Redibujar la imagen actual con los ajustes de pantalla vigentes |
| POST | `/api/images` | Subir imágenes (`multipart`, campo `files`) |
| DELETE | `/api/images/<name>` | Borrar una imagen |
| POST | `/api/images/<name>/show` | Pasar a modo imagen única con esa imagen |
| POST | `/api/current/save` | Guardar la portada de cómic en pantalla en la galería (`{"last_refresh": ...}`) |
| GET | `/current/download` | Descargar el original de la imagen en pantalla (JPEG) |
| POST | `/api/presets` | Guardar / sobrescribir un perfil (`{"name": ..., "values": {color, contrast, brightness, saturation}}`) |
| DELETE | `/api/presets/<name>` | Borrar un perfil |
| POST | `/api/comics/probe` | Probar una búsqueda avanzada (`{"search": {...}, "dry_run": true}` solo informa cuántas llamadas haría) |
| POST | `/api/comics/cache/clear` | Vaciar el caché de una búsqueda (`{"search": {...}}`) |

Los errores de la API se devuelven como `{"error": {"code": ..., "params": {...}, "message": ...}}`. La web traduce `code` (ver `static/i18n.js`) y usa `message` (en inglés) como respaldo.
