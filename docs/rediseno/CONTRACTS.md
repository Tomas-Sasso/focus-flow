# CONTRACTS · contratos de código entre módulos (rediseño Liquid Glass)

Versión 1.0 · 03/10/2026. Complementa `DESIGN_SPEC.md` (qué se ve) y `PLAN.md` (quién hace qué).
Las firmas de acá son **exactas**: quien implementa un módulo las respeta y quien lo consume no
asume nada más. Si un agente necesita algo que no está, lo agrega **en su propio módulo** con un
nombre privado (`_algo`) o lo pide en su reporte; nunca edita un archivo ajeno.

---

## 0. Reglas generales

1. **Grafo de dependencias** (sin ciclos; `→` = importa):

   ```
   render → (numpy, PIL)                      icons → (PIL)          anim → render (hex_to_rgb)
   theme  → config (ASSETS_DIR), render (mix y helpers de color)
   a11y   → config (claves de Settings)       (theme no importa a11y; la app los conecta)
   surface → theme, render, anim
   frameless → theme, render
   widgets/_base → surface, theme, render
   widgets/* → widgets/_base, surface, theme, render, icons, anim(tipos), frameless(overlays, menus)
   floating, splash → frameless, theme, render, icons, widgets.menus
   sheets → surface, theme, render, frameless(snapshot), widgets
   dialogs → sheets, widgets, config, engine
   views/* → widgets, surface, theme, stats, engine
   app → todo lo anterior
   engine, db, stats, system: NO SE TOCAN.
   ```
   `theme` **no** importa `render` salvo `mix` (como hoy) y helpers puros; `render` no importa
   `theme` (recibe colores y materiales por parámetro).

2. **`COLORS` puede ganar claves pero no perder ni renombrar las existentes** (lista en §1.1). Los
   valores cambian (paleta nueva). Sólo `theme.apply_palette` muta `COLORS` (en el lugar, para que
   todos los `from ..theme import COLORS` vean el cambio).
3. **Coordenadas de fondo = de ventana** (área cliente del toplevel, px físicos). Para un widget:
   `x = w.winfo_rootx() - w.winfo_toplevel().winfo_rootx()`.
4. **Escala**: todo lo que dibuja un canvas multiplica px lógicos por `theme.ui_scale(widget)`.
5. **Imágenes**: todo ítem de imagen de un canvas es **RGB ya compuesto**. No se depende del
   alfa entre ítems de Tk. El texto va como ítem de texto Tk encima de la imagen.
6. **Idempotencia**: todo setter público (`set_*`, `select`, `configure` de estado) sale sin hacer
   nada si el valor no cambió (ni redibujo ni animación).
7. **Hilos**: numpy/PIL pueden correr en un hilo; `PhotoImage` y todo Tk, sólo en el hilo de Tk.
   En esta versión no se usan hilos (no hace falta para los presupuestos).
8. **Errores**: nada de `except Exception: pass` nuevo sin comentario; en animaciones y redibujos se
   registra con `traceback.print_exc()` la primera vez por clave.
9. **Comentarios y textos** en español rioplatense, mismo estilo que el código existente.
10. **Windows**: toda llamada a `ctypes.windll`, `winreg`, `-transparentcolor`, `-toolwindow`,
    `state("zoomed")` va protegida (`os.name == "nt"` y/o `try/except tk.TclError, OSError,
    AttributeError`) y tiene camino de respaldo.

---

## 1. `focusflow/theme.py` (rol A)

### 1.1 Claves de `COLORS` que DEBEN seguir existiendo

`app, sidebar, bg, surface, surface2, surface3, surface4, border, border_soft, overlay, text,
text_muted, text_dim, text_faint, accent, accent_hover, accent_press, accent_soft, amber,
amber_hover, amber_soft, mint, mint_hover, mint_soft, rose, rose_hover, rose_soft, pink, pink_text,
lavender, lavender_soft, cream, cream_text, danger, danger_hover, orange, orange_hover, yellow,
yellow_hover`.

Claves nuevas (obligatorias): `bg_base, surface_raised, surface_sunken, separator, hairline,
label, label_secondary, label_tertiary, label_quaternary, on_accent, danger_text, focus_ring,
amber_press, mint_press, rose_press, lavender_hover, lavender_press, danger_press, danger_soft,
orange_press, orange_soft, yellow_press, yellow_soft`. Valores: DESIGN_SPEC §2.2.

### 1.2 Tokens y estructuras

```python
COLORS: dict[str, str]                       # paleta activa (se muta en el lugar)
PALETTES: dict[str, dict[str, str]]          # "standard", "contrast"
FILLS: dict[str, float]                      # hover .07, selected .12, pressed .16, control .10,
                                             # control_hover .14, control_pressed .18, track .16, keycap .12
DATA: dict[str, str]                         # {"focus": mint, "other": rose} (se recalcula en apply_palette)
DATA_LABELS: dict[str, str]                  # sin cambios
DISPLAY_KIND: dict[str, str]                 # sin cambios
HEAT_RAMP: list[str]                         # 6 colores (se reemplaza en el lugar)
PHASE_STYLE: dict[str, tuple[str, str, str]] # (etiqueta, color, color de texto); claves idle/focus/break/tolerance/paused/away
PHASE_DETAIL: dict[str, str]                 # rótulo corto por estado (DESIGN_SPEC §2.4)
PHASE_OF_STATE: dict[str, str]               # estado del motor -> "idle" | "focus" | "other"
PHASE_LIGHT: dict[str, tuple[str, float]]    # "idle"/"focus"/"other" -> (color de la mancha E, k)
BACKDROP_BLOBS: list[tuple[float, float, float, str, float]]   # A–D de §2.1
BACKDROP_PHASE_POS: tuple[float, float, float]                 # (0.445, 0.42, 0.46)
BACKDROP_BLUR = 28
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "2xl": 24, "3xl": 32, "4xl": 40}
RADIUS = {"xs": 6, "sm": 8, "md": 16, "lg": 24, "xl": 26, "pill": 999,
          "card": 24, "group": 16, "session": 20, "sheet": 26, "menu": 14, "tile": 8,
          "control_sm": 8, "keycap": 5}
LAYOUT = {"sidebar_w": 240, "page_margin": 24, "header_h": 52, "header_gap": 18, "body_top": 94,
          "gutter": 20, "card_pad": 16, "toolbar_h": 36, "toolbar_gap": 12, "row_h": 44,
          "min_w": 1120, "min_h": 720, "start_w": 1280, "start_h": 820}

@dataclass(frozen=True)
class ShadowSpec:
    blur: float          # radio de desenfoque en px lógicos (σ = blur / 2)
    alpha: float         # α del negro de la sombra
    dy: float            # desplazamiento vertical
    edge: float          # α del filo oscuro de 1 px exterior (0 = sin filo)

SHADOWS: dict[str, ShadowSpec]   # "card", "control", "prominent", "popover", "sheet", "hud" (§2.5–2.6)

@dataclass(frozen=True)
class Material:
    name: str
    tint: str; tint_a: float; sat: float
    lens_px: float; lens_amt: float
    rim_top: float; rim_base: float; sheen: float
    inner_shadow: float; edge_dark: float
    shadow: ShadowSpec | None
    blur: float                      # sólo materiales sobre foto (popover, sheet)
    solid: str | None = None         # si no es None: cuerpo sólido (RT/AC), sin muestreo
    border: tuple[str, float] | None = None   # (color, ancho px) en AC

MATERIALS: dict[str, Material]   # "sidebar", "control", "prominent", "popover", "sheet", "hud" (valores estándar)

@dataclass(frozen=True)
class CardStyle:
    radius: float; fill_key: str; border_a: float; top_light_a: float
    edge_dark: float; shadow: ShadowSpec; border_hc: str | None

CARD_STYLE: CardStyle            # §2.6 (grupo = mismo estilo con radius 16)

@dataclass(frozen=True)
class TypeRole:
    design: str        # "text" | "display"
    weight: int        # 400, 500, 600, 700
    px: int; line: int
    tracking: float    # em
    engine: str        # "tk" | "pil"
    upper: bool = False

TYPE_SCALE: dict[str, TypeRole]  # roles de DESIGN_SPEC §2.9: clock (px se calcula), clock_sm,
                                 # large_title, sheet_title, title1, title2, title3, headline, body,
                                 # control, control_lg, callout, caption, badge
```

### 1.3 Funciones

```python
def apply_palette(mode: str) -> None
    """mode: "standard" | "contrast". Muta en el lugar COLORS, DATA, PHASE_STYLE, HEAT_RAMP y el
    estado interno de materiales. No toca widgets: quien llama decide si reconstruye la UI."""

def set_appearance(*, reduce_transparency: bool, increase_contrast: bool, glass_tint: int) -> bool
    """Guarda el modo visual vigente; devuelve True si cambió algo. increase_contrast llama a
    apply_palette. Lo usa la app al recibir avisos de a11y."""

def appearance() -> dict          # {"reduce_transparency": bool, "increase_contrast": bool, "glass_tint": int}

def material(name: str, *, tone: str | None = None) -> Material
    """Material listo para dibujar con el modo vigente aplicado: regulador de tinte, RT (solid),
    AC (solid + border). `tone` (clave de COLORS) sólo para "prominent"."""

def label_on(level: str, over: str) -> str
    """Color opaco de etiqueta 'vibrante' (§2.3) sobre el hex `over`, con piso de contraste.
    level: "label" | "secondary" | "tertiary" | "quaternary". En AC devuelve los fijos."""

def fill_on(name: str, over: str) -> str        # mezcla blanco α FILLS[name] sobre `over` (×1,8 en AC)
def contrast(a: str, b: str) -> float           # WCAG
def ui_scale(widget) -> float                   # ScalingTracker.get_widget_scaling, 1.0 si falla
def window_scale(root) -> float                 # ScalingTracker.get_window_scaling, 1.0 si falla
def score_color(percentage: float) -> str       # sin cambios
def elevate(color: str, steps: int = 1) -> str  # sin cambios
```

### 1.4 `Typography`

```python
class Typography:
    def __init__(self, root): ...
    @classmethod
    def current(cls) -> "Typography"      # última instancia creada (para widgets sin `fonts`)

    source: str                 # "sf" | "inter" | "segoe-variable" | "segoe"
    regular: str; medium: str; semibold: str      # familias Tk (compat)
    paths: list[str]            # Regular de texto para PIL (compat; primero el archivo real)
    paths_bold: list[str]       # Semibold de texto para PIL (compat)

    def __getitem__(self, key: str) -> ctk.CTkFont
        """Claves heredadas (title, section, card, body, body_bold, small, small_bold, tiny,
        tiny_bold, micro, button, button_lg, metric, metric_sm, clock, clock_sm, display, nav) y
        roles nuevos (large_title, sheet_title, title1, title2, title3, headline, control,
        control_lg, callout, caption, badge). Mapeo en DESIGN_SPEC §2.9."""

    def tk(self, role: str, scale: float = 1.0) -> tuple      # (familia, -px, "normal"|"bold") para ítems de canvas
    def pil(self, role: str, scale: float = 1.0, px: float | None = None) -> ImageFont.FreeTypeFont
        """Archivo exacto del peso (variable: set_variation_by_axes). px pisa el del rol (reloj)."""
    def pil_path(self, design: str, weight: int) -> str | None
    def measure(self, role: str, text: str, scale: float = 1.0) -> int   # ancho con la fuente Tk
```

Registro (Windows): `AddFontResourceExW(path, 0x10, 0)` **sin** `SendMessageW`. Fuera de
Windows no se instala nada: Tk ve lo que tenga fontconfig (en desarrollo `FONTCONFIG_FILE`, ver
PLAN §2) y PIL carga por ruta.

---

## 2. `focusflow/a11y.py` (rol A, nuevo)

```python
def read_windows_settings() -> dict
    """{"animations": bool, "transparency": bool, "high_contrast": bool}. Fuera de Windows o ante
    cualquier error: {"animations": True, "transparency": True, "high_contrast": False}."""

class Accessibility:
    KEYS = ("a11y_reduce_motion", "a11y_reduce_transparency", "a11y_increase_contrast", "glass_tint")
    def __init__(self, root, settings): ...
    reduce_motion: bool            # efectivo (ajuste propio "auto"/"on"/"off" sobre el sistema)
    reduce_transparency: bool
    increase_contrast: bool
    glass_tint: int                # 0..100
    system: dict                   # última lectura de read_windows_settings()
    def refresh(self, force: bool = False) -> set[str]
        """Relee sistema (como mucho cada 2 s salvo force) y ajustes; devuelve el conjunto de
        propiedades que cambiaron ({"reduce_motion", ...}) y avisa a los suscriptores."""
    def subscribe(self, callback) -> int        # callback(changed: set[str])
    def unsubscribe(self, token: int) -> None
    def bind_root(self) -> None                 # <FocusIn> del root -> refresh() con throttle
```

## 3. `focusflow/config.py` (rol A, sólo esto)

- `DEFAULTS` suma: `"a11y_reduce_motion": "auto"`, `"a11y_reduce_transparency": "auto"`,
  `"a11y_increase_contrast": "auto"`, `"glass_tint": 50`.
- `Settings.stage(**values)`: actualiza en memoria **sin** escribir a disco (para deslizadores).
  `Settings.save()` ya existe. Nada más cambia en config.py.

---

## 4. `focusflow/render.py` (rol B)

**Se conservan con la misma firma y comportamiento** (con fondo hex): `hex_to_rgb, rgb_to_hex,
mix, lighten, darken, relative_luminance, readable_on, donut, progress_ring, radial_profile,
timeline, bar_chart, heatmap, sparkline, TRANSPARENT_KEY, shaped_panel, rounded_panel, load_font,
draw_text, to_photo, speaker_icon`, y los privados `_rounded_sdf`, `_rounded_mask`, `_smoothstep`.

Cambios compatibles:
- El parámetro `background` de `donut, progress_ring, radial_profile, timeline, bar_chart,
  heatmap, sparkline, rounded_panel, speaker_icon` acepta **hex o `np.ndarray` (h, w, 3)** del
  tamaño exacto del resultado (uint8 o float32). Helper: `_base(background, w, h) -> float32`.
- `progress_ring(..., cap_min_fraction=0.005, glow=0.0)`: sin tapas si `fraction < cap_min_fraction`;
  `glow` = α del resplandor del arco (DESIGN_SPEC §3.7).
- Cachés existentes pasan a LRU (no se vacían enteras); `_rounded_mask` y `rounded_panel` cachean
  máscaras por (w, h, r, feather).
- `load_font(paths, size)` igual; respaldo final: Inter de `assets/fonts` antes que `segoeui.ttf`.

Nuevas (puras, sin Tk):

```python
# --- fondo ambiental
@dataclass
class AmbientLayers:
    size: tuple[int, int]
    base: Image.Image            # RGB, manchas A–D
    base_blur: Image.Image       # RGB, desenfoque BACKDROP_BLUR
    phase_mask: Image.Image      # L, mancha E sin color (0..255 = f/k)
    phase_mask_blur: Image.Image # L
def ambient_layers(width: int, height: int, *, base_hex: str, blobs, phase_pos, intensity: float = 1.0,
                   blur_radius: float = 28, seed: int = 7) -> AmbientLayers      # LRU(2)
def ambient_compose(layers: AmbientLayers, color_hex: str, k: float, *, blurred: bool = False) -> Image.Image

# --- formas y sombras
def rounded_sdf(width: int, height: int, radius: float, pad: int = 0) -> np.ndarray   # LRU(64), negativo adentro
def shadow_alpha(width: int, height: int, radius: float, spec) -> tuple[np.ndarray, int]
    """α (float32) de sombra + filo de 1 px en un lienzo con margen `pad`; 0 bajo la forma. LRU(64).
    spec: cualquier objeto con blur, alpha, dy, edge."""
def apply_shadows(canvas: np.ndarray, shapes: list[tuple[int, int, int, int, float, object]]) -> None
    """Oscurece `canvas` (float32 o uint8, (H, W, 3)) en el lugar con las sombras de
    (x, y, w, h, radio, spec) en coordenadas del canvas; recorta a los bordes."""

# --- vidrio
def glass_shape(width: int, height: int, radius: float, material, scale: float = 1.0) -> object   # LRU(64)
def glass_compose(sharp: np.ndarray, blurred: np.ndarray, rect: tuple[int, int, int, int], radius: float,
                  material, *, tint: str | None = None, tint_a: float | None = None, fill: float = 0.0,
                  press: float = 0.0, materialize: float = 1.0, scale: float = 1.0,
                  extend: tuple[int, int, int, int] = (0, 0, 0, 0)) -> np.ndarray
    """Devuelve una COPIA de `sharp` (uint8, mismo tamaño) con el cuerpo de vidrio compuesto en
    `rect` (coords dentro del arreglo). `blurred` es el mismo recorte desenfocado. `fill` = relleno
    blanco de estado, `press` = brillo extra al presionar (0..1), `materialize` = m de DESIGN_SPEC
    §5.1 (escala 0,94+0,06m y efectos × m). `extend` agranda la forma fuera del rect (barra lateral
    de borde a borde). Si material.solid: cuerpo sólido + especular × 0,5 (+ borde si AC).
    No dibuja la sombra proyectada (la pone el host)."""
def glass_rgba(behind: Image.Image | None, size: tuple[int, int], radius: float, material, *,
               tint=None, fill=0.0, materialize=1.0, scale=1.0, synthetic: str | None = None) -> Image.Image
    """Para ventanas sin marco: RGBA del tamaño `size` (la forma ocupa todo menos el margen de
    sombra si material.shadow y no hay foto). `behind` = foto de lo que hay detrás (se desenfoca
    con material.blur); `synthetic` = hex del color de fase para el vidrio 'hud' sin foto."""

# --- superficies sólidas
def card_layer(crop: np.ndarray, radius: float, fill_hex: str, style) -> np.ndarray
    """Compone sobre `crop` (h, w, 3) el cuerpo de una tarjeta del tamaño del crop: cuerpo
    redondeado AA, borde interior 1 px, luz superior; NO la sombra exterior (host). uint8."""

# --- texto
def text_width(font, text: str, tracking_em: float = 0.0) -> float
def draw_text(image, xy, text, font, color, anchor="la", tracking_em: float = 0.0)    # amplía la actual
def wrap_text(font, text: str, max_width: float, max_lines: int = 2, tracking_em: float = 0.0) -> list[str]   # con "…"
def draw_clock(image, xy, text: str, font, color, *, tracking_em: float = -0.01, anchor: str = "mm") -> tuple[int, int]
    """Cifras tabulares por celda; ':' centrado en la altura de las cifras (ver mk.clock)."""
def clock_size(font, text: str, tracking_em: float = -0.01) -> tuple[int, int]

# --- utilidades
def composite(base: np.ndarray, overlay: Image.Image, x: int, y: int) -> None   # RGBA sobre RGB en el lugar
def blur_image(image: Image.Image, radius: float, scale: int = 4) -> Image.Image
def mean_hex(array: np.ndarray) -> str
def keyed(rgba: Image.Image, behind: Image.Image | str, key: str = TRANSPARENT_KEY, threshold: float = 0.5) -> Image.Image
    """RGB para ventanas con color clave: compone el borde AA contra `behind` (foto o hex) y pone
    `key` donde α < threshold."""
```

---

## 5. `focusflow/icons.py` (rol I, nuevo)

```python
NAMES: tuple[str, ...]      # DESIGN_SPEC §2.10 (obligatorios)
def icon(name: str, size: float, color: str, *, weight: float | None = None,
         scale: float = 1.0) -> Image.Image
    """RGBA de round(size*scale) px; trazo por defecto 1.75 * size/18 (mín. 1.5) * scale. LRU(256).
    Nombre desconocido -> KeyError (no dibuja un cuadrado)."""
def paste_icon(image: Image.Image, name, xy, size, color, **kw) -> None   # compone sobre RGB/RGBA
```

---

## 6. `focusflow/anim.py` (rol C)

Se conserva **todo** lo público actual con la misma firma: `EASINGS`, curvas, `Tween`,
`Animator(widget, fps=60)`, `.to(...)`, `.color(...)`, `.sequence(...)`, `.cancel(key)`,
`.is_running(key)`, `.stop()`, `AnimatedValue`, `AnimatedVector`. `Animator._tweens` sigue siendo
el dict de **todas** las tareas vivas (tweens y resortes) — lo leen herramientas de captura.

```python
@dataclass(frozen=True)
class SpringSpec:
    duration: float
    bounce: float
    @property
    def stiffness(self) -> float      # (2π/duration)²
    @property
    def damping(self) -> float        # 4π(1−bounce)/duration

SPRINGS: dict[str, SpringSpec]        # snappy, select, pop_in, pop_out, press, release, data, page, scroll (DESIGN_SPEC §5.1)
REDUCED_FADE = 0.15                   # duración del fundido que reemplaza al movimiento

class Spring:
    def __init__(self, value=0.0, spec: SpringSpec | str = "snappy", velocity=0.0): ...
    value: float; velocity: float; target: float
    def retarget(self, target: float, velocity: float | None = None, spec=None) -> None
    def step(self, dt: float) -> float          # subpasos de 4 ms
    def settled(self, eps: float = 1e-3) -> bool

class Animator:
    reduced_motion: bool                        # lo setea la app desde a11y
    frame_count: int                            # cuadros procesados desde el arranque
    @property
    def idle(self) -> bool                      # sin tareas vivas

    def spring(self, key, target: float, *, on_update, value: float | None = None,
               velocity: float | None = None, spec: SpringSpec | str = "snappy",
               on_done=None, eps: float | None = None, fade: bool = False) -> None
        """Si ya hay un resorte con `key`: retarget (conserva valor y velocidad; `value` se ignora).
        Si no: arranca desde `value` (obligatorio la primera vez). on_update(valor) por cuadro.
        reduced_motion: fade=False -> salta al objetivo (un on_update y on_done);
        fade=True -> tween de REDUCED_FADE s out_cubic."""
    def spring_vector(self, key, targets: list[float], *, on_update, values: list[float] | None = None,
                      spec="snappy", on_done=None, fade=False) -> None
    def spring_color(self, key, target_hex: str, *, on_update, value_hex: str | None = None,
                     spec="snappy", on_done=None) -> None          # interpola RGB con un resorte de t
    def materialize(self, key, show: bool, *, on_update, value: float | None = None, on_done=None) -> None
        """m 0→1 con pop_in (show) o 1→0 con pop_out; con reduced_motion, fundido REDUCED_FADE."""
    def value_of(self, key): ...                # valor actual (float | list) o None
    def velocity_of(self, key): ...
    def request_frame(self, target) -> None
        """`target` = widget con redraw() o callable. Se ejecuta UNA vez al final del cuadro en curso
        (o del próximo si no hay ticker), aunque se pida muchas veces."""
```

Reglas: el ticker usa el `dt` real; una excepción en `on_update` se imprime con traceback una vez
por clave y la tarea se descarta; el ticker se apaga cuando no hay tareas ni pedidos de cuadro.

---

## 7. `focusflow/surface.py` (rol D, nuevo) — la arquitectura de la ventana

### 7.1 Modelo

```
root (ctk.CTk)
└─ Stage (tk.Canvas, place 0,0 relwidth=1 relheight=1)        Host raíz: dueño del Backdrop
   ├─ Sidebar (GlassPanel, place x=0 w=240 relheight=1)        vidrio de borde a borde
   │    └─ hijos: ítems propios del Sidebar (no widgets)
   ├─ FocusView / HistoryView / InsightsView / SettingsView    ViewSurface cada una, place x=240
   │    ├─ PageHeader (Clear) ── Label, toolbar (Clear) ── GlassButton, PopUpButton, SegmentedControl
   │    ├─ Clear (columnas) ── GoalRing(BACKDROP), TimelineBar(BACKDROP), GlassButton, GlassGroup, Label
   │    ├─ Card (sólida) ── widgets CTk y PILCanvas con background=card.fill
   │    └─ ScrollSurface ── Card …
   └─ SheetLayer (cuando hay hoja; sheets.py) ── GlassPanel (hoja) ── Card(16) ── CTkEntry…
```

- **Host** = sabe dar su **composición** (lo que se ve en su área antes de dibujar a sus hijos):
  `Stage` (fondo ambiental), `ViewSurface` y `ScrollSurface` (recorte del host padre + sombras
  registradas), `GlassPanel` (recorte del host padre + cuerpo de vidrio + sombras registradas),
  `SheetLayer` (foto oscurecida).
- **BackdropCanvas** = todo canvas que dibuja sobre el recorte de su host. `Clear` no es host: es
  un `BackdropCanvas` transparente; sus hijos usan el host de más arriba.
- **Modelo "pull"**: un hijo pide `host.composite(rect)` al redibujar; el host recalcula su
  composición sólo si está sucia. Los cambios se propagan con versiones y una **pasada de
  validación** por host (después de `after_idle`) que redibuja a quien le cambió el rect o la
  versión del host.

### 7.2 API

```python
BACKDROP = "backdrop"          # centinela para background=

class Backdrop:
    """Fondo ambiental de una ventana raíz. Lo crea el Stage."""
    @staticmethod
    def of(widget) -> "Backdrop"
    size: tuple[int, int]; version: int; phase: str
    def resize(self, width: int, height: int) -> None
    def set_phase(self, phase: str, animate: bool = True) -> None          # "idle" | "focus" | "other"; fundido ambient
    def set_mode(self, *, reduce_transparency: bool, increase_contrast: bool) -> None
    def crop(self, x: int, y: int, w: int, h: int, *, blurred: bool = False) -> np.ndarray   # uint8, fuera de rango = bg_base
    def mean(self, x: int, y: int, w: int, h: int) -> str
    def subscribe(self, callback) -> int ; def unsubscribe(self, token: int) -> None    # callback(version)

class Host:   # mixin
    host_version: int
    def composite(self, x: int, y: int, w: int, h: int, *, blurred: bool = False) -> np.ndarray
        """uint8 (h, w, 3) en coords del host (para ScrollSurface: del viewport)."""
    def composite_mean(self, x, y, w, h) -> str
    def add_shadow(self, widget, spec, radius: float) -> None        # el host dibuja sombra+filo bajo `widget`
    def remove_shadow(self, widget) -> None
    def watch(self, widget) -> None ; def unwatch(self, widget) -> None
    def invalidate(self, reason: str = "layout") -> None             # agenda la pasada de validación
    def is_active(self) -> bool                                       # visible (vista al frente, root no minimizado)

def host_of(widget) -> Host | None
def window_rect(widget) -> tuple[int, int, int, int]                  # rect en coords de ventana

class BackdropCanvas(tk.Canvas):
    min_frame_ms: int = 0
    def __init__(self, master, background: str = BACKDROP, width: int = 100, height: int = 100, *,
                 shadow=None, radius: float = 0, **kwargs): ...
    background: str                         # hex o BACKDROP
    host: Host | None                       # resuelto al mapearse
    scale: float                            # theme.ui_scale(self)
    def rect_in_host(self) -> tuple[int, int, int, int]
    def backdrop_crop(self, *, blurred: bool = False) -> np.ndarray   # (h, w, 3) uint8; con hex = mosaico del color
    def backdrop_mean(self) -> str
    def render(self, width: int, height: int):          # subclases: devuelven PIL.Image RGB (o None)
    def redraw(self) -> None                            # render + set_image (reusa PhotoImage con paste)
    def schedule_redraw(self) -> None                   # after_idle, coalescido; si el host está inactivo, marca sucio
    def animation_redraw(self) -> None                  # vía animator.request_frame / min_frame_ms
    def on_backdrop_changed(self) -> None               # por defecto schedule_redraw()
    def set_shadow(self, spec, radius: float) -> None   # registra/actualiza su sombra en el host
    def set_image(self, image) -> None

class Clear(BackdropCanvas):
    def __init__(self, master, **kwargs): ...           # contenedor transparente (grid/pack adentro)

class Stage(tk.Canvas, Host):
    def __init__(self, root, animator, *, a11y=None): ...   # se coloca solo con place
    backdrop: Backdrop
    def set_active(self, active: bool) -> None          # False con el root minimizado
    def on_resize_settled(self, callback) -> None       # tras el debounce de 120 ms

class ViewSurface(BackdropCanvas, Host):
    def __init__(self, master: Stage, app=None, **kwargs): ...
    active: bool
    def set_active(self, active: bool) -> None          # la app la llama al cambiar de vista
    def on_activate(self) -> None                       # hook (vacío) para las vistas
    def on_deactivate(self) -> None

class ScrollSurface(BackdropCanvas, Host):
    def __init__(self, master, *, fill: str | None = None, padding=(24, 0, 24, 24), gap: int = 20,
                 max_width: int | None = None): ...      # fill=None => fondo ambiental fijo; hex => sólido
    def add(self, widget, *, height: int | None = None, align: str = "stretch") -> None
    def add_row(self, widgets: list, *, weights=None, min_widths=None, gap: int | None = None,
                stack_below: int | None = None) -> None # stack_below: si el ancho < este valor, se apilan
    def remove(self, widget) -> None
    def clear(self) -> None                              # destruye y quita todos los hijos agregados
    def relayout(self) -> None
    def scroll_to(self, y: float, animate: bool = True) -> None
    def scroll_by(self, dy: float, animate: bool = True) -> None
    @property
    def offset(self) -> float
    viewport: tuple[int, int]; content_height: int

class GlassPanel(BackdropCanvas, Host):
    def __init__(self, master, *, material: str = "sidebar", radius: float = 0,
                 extend=(0, 0, 0, 0), tone: str | None = None, **kwargs): ...
    def set_material(self, material: str, tone: str | None = None) -> None
    def set_materialize(self, m: float) -> None          # 0..1 (para hojas)

def install_wheel_router(root) -> None
    """Un solo bind_all de rueda (<MouseWheel>, <Button-4/5>) que manda el evento a la
    ScrollSurface bajo el puntero (salvo que el widget bajo el puntero sea un Text con desborde)."""
```

### 7.3 Contratos de comportamiento

- **Cómo se registra una superficie de vidrio**: un widget de vidrio es un `BackdropCanvas` con
  `shadow=theme.SHADOWS[...]` y `radius`; al mapearse llama `host.add_shadow(self, spec, radius)`.
  Su `render()` toma `backdrop_crop()` y `backdrop_crop(blurred=True)` (ambos **ya incluyen su
  propia sombra** porque el host la dibujó) y llama `render.glass_compose(...)` con su rect =
  todo el canvas. Texto e íconos van como ítems de texto Tk o imágenes RGB compuestas encima.
- **Cómo una tarjeta/vista obtiene su color de fondo para gráficos PIL**: `Card.fill` (hex). Los
  PILCanvas dentro de una tarjeta usan `background=card.fill` (como hoy con
  `COLORS["surface"]`). Sobre el fondo ambiental usan `background=BACKDROP` y reciben
  `backdrop_crop()` en `render()` (o el hex promedio con `backdrop_mean()` si necesitan un color).
- **Cambio de fase**: la app llama `stage.backdrop.set_phase(theme.PHASE_OF_STATE[estado])` sólo
  cuando cambia. El Backdrop interpola y en cada paso sube `version` y avisa: el Stage marca a sus
  hosts, cada host activo revalida y redibuja a sus vigilados (un cuadro por paso, coalescido con
  `animator.request_frame`). Hosts inactivos sólo marcan sucio.
- **Cambio de tamaño**: `Stage` hace debounce de 120 ms del `<Configure>` del root;
  `backdrop.resize(w, h)`; avisa. Los hosts inactivos no hacen nada hasta `set_active(True)`.
- **Cambio de layout** (un hijo cambia de tamaño o posición): el `<Configure>` de cualquier
  `BackdropCanvas` llama `host.invalidate()`; la pasada de validación (una por host por ciclo
  ocioso) recompone el host si cambió alguna sombra y redibuja a cada vigilado cuyo `rect_in_host`
  o `host_version` cambió. Un `Clear` que se mueve hace que sus hijos se revaliden.
- **Vistas inactivas**: `schedule_redraw` de cualquier hijo de un host inactivo sólo marca
  `_dirty`. `ViewSurface.set_active(True)` revalida y redibuja lo sucio en un solo pase.
- **ScrollSurface**: los hijos agregados son ítems `create_window`; el fondo es un ítem de imagen
  que se mueve con `canvasy(0)` en el mismo evento del scroll (queda fijo a la ventana); las
  sombras de las tarjetas se recomponen por cuadro de scroll a partir de las coords de los ítems
  (no de `winfo`). El indicador de scroll es un ítem del canvas en el margen derecho.
- **Destrucción**: `BackdropCanvas.destroy()` hace `unwatch` y `remove_shadow`. Ningún `after`
  queda colgado (se cancelan en `destroy`).

---

## 8. `focusflow/frameless.py` (rol H1, nuevo)

```python
def snapshot(bbox: tuple[int, int, int, int]) -> Image.Image | None
    """Foto de pantalla en px físicos (ImageGrab; en X11 con xdisplay=$DISPLAY). None si falla."""
def screen_work_area(root) -> tuple[int, int, int, int]    # Windows: SPI_GETWORKAREA; si no, pantalla − 48 abajo
def layered_enabled() -> bool                              # os.name == "nt" and os.environ.get("FOCUSFLOW_LAYERED") == "1"

class FramelessWindow:
    def __init__(self, root, *, topmost: bool = True, toolwindow: bool = False): ...
    window: tk.Toplevel; canvas: tk.Canvas
    scale: float                       # theme.window_scale(root)
    mode: str                          # "colorkey" | "layered" | "plain" (X11 sin color clave)
    def grab_behind(self, x: int, y: int, w: int, h: int) -> Image.Image | None   # ANTES de mostrar
    def edge_color_around(self, x: int, y: int, w: int, h: int) -> str           # promedio del anillo de 2 px exterior
    def show_image(self, rgba: Image.Image, x: int, y: int, *, behind: Image.Image | str | None = None) -> None
        """Muestra/actualiza. colorkey: render.keyed(rgba, behind) con TRANSPARENT_KEY;
        layered: UpdateLayeredWindow con BGRA premultiplicado; plain: compone contra behind/#0C0A1F."""
    def set_alpha(self, value: float) -> None    # -alpha (no en layered: SourceConstantAlpha)
    def move(self, x: int, y: int) -> None
    def hide(self) -> None ; def destroy(self) -> None
    @property
    def visible(self) -> bool
    def bind(self, sequence, func, add=None)     # sobre el canvas
```

---

## 9. Paquete `focusflow/widgets/`

`__init__.py` (lo crea R0 y no lo toca nadie más) hace `from .X import *` de cada módulo, en este
orden: `_base, buttons, controls, navigation, charts, surfaces, dates, sound, overlays, menus`.
**Cada módulo exporta con `__all__`**; agregar un componente = agregarlo al `__all__` de su
módulo. Las vistas y la app siguen usando `from .. import widgets as W` y `W.Nombre`.

### 9.1 API existente que se conserva TAL CUAL (firma y comportamiento observable)

| Nombre | Módulo | Notas |
|---|---|---|
| `scaling_of(widget)`, `fmt_hms`, `fmt_ms`, `fmt_short`, `fmt_hours`, `MONTHS_ES`, `MONTHS_SHORT`, `WEEKDAY_INITIALS`, `WEEKDAY_NAMES` | `_base` | `WEEKDAY_INITIALS` pasa a `["L","M","X","J","V","S","D"]`; `fmt_short` → `"1 h 17 min"`/`"17 min"`, `fmt_hours` → `"7,4 h"` (DESIGN_SPEC §2.4); nuevo `fmt_pct(v) -> "92 %"` y `fmt_date_long(d) -> "Sábado 3 de octubre"` |
| `PILCanvas(master, background, width=100, height=100, **kw)` | `_base` | ahora subclase de `surface.BackdropCanvas`; `background` hex o `BACKDROP`; `render/redraw/schedule_redraw/animation_redraw`, atributo `background`, `min_frame_ms` |
| `Dot(master, background, color, size=9)` | `_base` | |
| `SmoothButton(master, animator=None, base_color=None, hover_color=None, press_depth=0.12, **ctk_kw)` | `buttons` | API de CTkButton (`configure(text=, text_color=, command=, state=)`, `cget`, `grid/pack/...`); `set_base_color(color, hover_color=None, animate=True)` **idempotente** |
| `button(master, animator, text, command, tone="accent", **kw)` | `buttons` | kw: `font, height, width, corner_radius` |
| `TONES` (claves accent, mint, amber, rose, lavender, ghost, quiet, danger, orange, yellow → (fill_key, hover_key, text_key)) | `buttons` | claves de COLORS |
| `SegmentedControl(master, animator, background, fonts, items, command=None, height=32, pad_x=14, stretch=True, active_color=None)` | `navigation` | `select(name, animate=True)`, `get()`, `measure_width()`; **el clic ahora selecciona solo** y después llama `command(item)` (llamar `select` de nuevo desde la vista es inocuo) |
| `DonutChart(master, animator, background, fonts, key="donut", caption="Concentración", show_center=True, inner_ratio=0.68, max_size=260, glow=0.09, **kw)` | `charts` | `set_values(mapping, animate=True)` |
| `MiniDonut(master, background, fonts, size=84)` | `charts` | `set_values(mapping)` |
| `GoalRing(master, animator, background, fonts, max_size=300, **kw)` | `charts` | `set_progress(f, animate=True)`, `set_color(c, animate=True)`, `set_text(primary, secondary="", badge="", badge_color=None)` (último parámetro nuevo, opcional) |
| `RadialHours(master, background, fonts, max_size=280, **kw)` | `charts` | `set_values(lista24)` |
| `ProgressBar(master, animator, background, color=None, track=None, height=6)` | `charts` | `set_fraction(v, animate=True, duration=0.45)`, `set_color(c, animate=True)` |
| `TimelineBar(master, background, height=14)` | `charts` | `set_spans(spans, duration=None)` |
| `BarsView(master, background, fonts, color=None, height=150, empty_text=…)` | `charts` | `set_data(values, labels=None)`; nuevo kw opcional `highlight="peak"|"last"|int`, `goal=None` |
| `Heatmap(master, background, fonts, on_select=None)` | `charts` | `set_data`, `weeks_that_fit`, `tooltip_for`, `date_of`; nuevo `hovered()`; `_hover` sigue existiendo |
| `Card(master, fill=None, radius=None, **kw)` | `surfaces` | ahora `BackdropCanvas` (no CTkFrame); geometría hija con grid/pack; atributos `fill`, `radius`; kw nuevos: `shadow=True` |
| `card_title(parent, fonts, text, side_widget=None, pady=None)` | `surfaces` | empaqueta (pack) un encabezado y lo devuelve |
| `StatTile(master, animator, fonts, label, color=None, fill=None, formatter=None)` | `surfaces` | `set_value(value, animate=True)` |
| `Legend(master, fonts, keys=("focus","other"), background=None, orientation="vertical")` | `surfaces` | `set_values({key: "NN %"})` |
| `Chip(master, animator, background, fonts, text="", color=None, text_color=None, height=26, pad_x=14, **kw)` | `surfaces` | `set_state(text, color, text_color=None, animate=True)` **idempotente**, `measure()` |
| `MiniCalendar(master, animator, background, fonts, on_select=None, on_month_change=None)` | `dates` | `set_marked`, `set_selected(day, notify=False)`, `shift_month`, atributo `selected` |
| `DateField(master, animator, fonts, value=None, on_change=None)` | `dates` | `get_date/set_date/toggle/open/close` |
| `SpeakerButton(master, background, command=None, size=22)` | `sound` | `set_muted(bool)` |
| `VolumeControl(master, fonts, settings, on_change, background=None)` | `sound` | `refresh()` |
| `ToastManager(root, animator, fonts)` | `overlays` | `show(message, tone="accent", duration=3200, action=None, action_text="", icon=None)`; atributo `active` (lista de avisos vivos) |
| `HashtagPopup(root, animator, fonts, provider)` | `overlays` | `attach(textbox)` **idempotente**, `show/hide/move`, atributos `visible`, `toplevel` |

`NavRail` **se retira** (sólo la usaba app.py): lo reemplaza `Sidebar`. `DateField` y `MiniDonut`
se conservan aunque las vistas nuevas no los usen.

### 9.2 Componentes nuevos (firmas)

```python
# surfaces.py (rol D)
class Label(BackdropCanvas):
    def __init__(self, master, text: str = "", *, role: str = "body", level: str = "label",
                 color: str | None = None, fonts=None, anchor: str = "w", justify: str = "left",
                 wrap: bool = False, max_lines: int = 1, background: str = BACKDROP, **kw): ...
    def configure(self, **kw)   # text=, level=, color=, role= (además de lo de tk.Canvas)
    def cget(self, key)         # "text" incluido
class PageHeader(Clear):
    def __init__(self, master, fonts, title: str, subtitle: str = ""): ...
    toolbar: Clear                                  # los ítems se empaquetan con pack(side="right", padx=(12, 0))
    def set_title(self, text: str) -> None ; def set_subtitle(self, text: str) -> None
class KeyHints(BackdropCanvas):
    def __init__(self, master, fonts, pairs: list[tuple[str, str]], *, background=BACKDROP): ...
class ContentUnavailable(BackdropCanvas):
    def __init__(self, master, fonts, icon: str, title: str, text: str = "", *,
                 action_text: str | None = None, command=None, background=BACKDROP): ...
class Separator(BackdropCanvas):
    def __init__(self, master, *, orient: str = "horizontal", inset: int = 0, background=BACKDROP): ...

# buttons.py (rol F1)
class GlassButton(BackdropCanvas):
    def __init__(self, master, *, text: str | None = None, icon: str | None = None, command=None,
                 style: str = "regular", tone: str = "accent", height: int = 36, width: int | None = None,
                 fonts=None, animator=None, selected: bool = False, takefocus: bool = True, **kw): ...
        # style: "regular" | "prominent" | "destructive"
    def configure(self, **kw)    # text, icon, command, style, tone, state ("normal"/"disabled"), selected
    def set_visible(self, visible: bool, animate: bool = True) -> None    # materializar / desmaterializar (conserva su lugar)
    def invoke(self) -> None
@dataclass
class GroupItem:
    key: str; text: str; command: object; icon: str | None = None; enabled: bool = True
class GlassGroup(BackdropCanvas):
    def __init__(self, master, items: list[GroupItem], *, height: int = 40, fonts=None, animator=None, **kw): ...
    def set_items(self, items: list[GroupItem], animate: bool = True) -> None   # idempotente; morph del ancho
    def set_visible(self, visible: bool, animate: bool = True) -> None
class Button(BackdropCanvas):
    def __init__(self, master, text: str = "", command=None, *, style: str = "fill", tone: str = "accent",
                 icon: str | None = None, height: int = 32, width: int | None = None, fonts=None,
                 animator=None, background: str = BACKDROP, takefocus: bool = True, **kw): ...
        # style: "fill" | "prominent" | "destructive" | "borderless"
    def configure(self, **kw)    # text, icon, command, style, tone, state
    def invoke(self) -> None

# controls.py (rol F1)
class Toggle(BackdropCanvas):
    def __init__(self, master, value: bool = False, command=None, *, size: str = "regular",
                 animator=None, background: str = BACKDROP, **kw): ...     # command(valor)
    def get(self) -> bool ; def set(self, value: bool, animate: bool = True) -> None
    def configure(self, **kw)    # state
class Slider(BackdropCanvas):
    def __init__(self, master, value: float = 0, *, from_: float = 0, to: float = 100, step: float = 1,
                 command=None, knob: int = 16, animator=None, background: str = BACKDROP, **kw): ...
        # command(valor, final: bool) — final=True al soltar / al terminar teclado o rueda
    def get(self) -> float ; def set(self, value: float, animate: bool = False) -> None
    def set_muted(self, muted: bool) -> None
class Stepper(BackdropCanvas):
    def __init__(self, master, value: int, *, minimum: int, maximum: int, step: int = 1, unit: str = "min",
                 command=None, fonts=None, background: str | None = None, width: int = 132, **kw): ...
        # command(valor) al confirmar; background por defecto = fill del Card padre
    def get(self) -> int ; def set(self, value: int) -> None
class TextField(ctk.CTkEntry):       # CTkEntry con estilo (§3.5); misma API de CTkEntry
    def __init__(self, master, *, placeholder: str = "", height: int = 32, **kw): ...
class TextArea(ctk.CTkTextbox):      # CTkTextbox con estilo; misma API
    def __init__(self, master, *, height: int = 96, **kw): ...
    def highlight_hashtags(self) -> None

# navigation.py (rol F2)
class Sidebar(GlassPanel):
    def __init__(self, master, animator, fonts, items, command=None, *, settings,
                 on_toggle_floating=None, volume_model=None, width: int = 240): ...
    def select(self, name: str, animate: bool = True) -> None ; def get(self) -> str
    def set_floating(self, on: bool) -> None
    def refresh_volume(self) -> None
    def set_window_active(self, active: bool) -> None

# menus.py (rol G)
@dataclass
class MenuItem:
    label: str = ""; command: object = None; icon: str | None = None; checked: bool | None = None
    enabled: bool = True; separator: bool = False; value: object = None
class Menu:
    def __init__(self, root, animator, fonts, items: list[MenuItem], *, on_close=None): ...
    def open(self, anchor: tuple[int, int, int, int], *, min_width: int = 0, align: str = "left") -> None
        # anchor = rect del control en coords de pantalla (px físicos); un punto = (x, y, 0, 0)
    def close(self, animate: bool = True) -> None
    @property
    def is_open(self) -> bool
class PopUpButton(BackdropCanvas):
    def __init__(self, master, values: list[str], command=None, *, value: str | None = None,
                 style: str = "glass", icon: str | None = None, width: int | None = None,
                 fonts=None, animator=None, background: str = BACKDROP, **kw): ...
        # command(valor) al elegir
    def get(self) -> str ; def set(self, value: str) -> None
    def configure(self, **kw)    # values=, state=, (y lo de tk.Canvas)

# sound.py (rol G)
class VolumeModel:
    def __init__(self, settings, on_change): ...          # on_change() tras aplicar
    volume: int; muted: bool
    def set_volume(self, value: int, final: bool) -> None # stage() durante el arrastre; save() con final
    def toggle_mute(self) -> None
```

---

## 10. Ventanas: `floating.py`, `splash.py` (rol H2)

```python
class FloatingTab:
    def __init__(self, app): ...        # compact_text = "—" desde el arranque
    minimized: bool; enabled: bool; compact_text: str
    def set_enabled(self, enabled: bool) -> None
    def toggle_minimized(self, value: bool | None = None) -> None
    def sync_visibility(self) -> None    # no muestra nada si not getattr(app, "booted", False)
    def update_from(self, engine) -> None   # idempotente; renderiza sólo si está visible y cambió el texto/fracción
    def destroy(self) -> None
class SplashScreen:
    def __init__(self, root, fonts): ...
    window                                # Toplevel (lo lee shoot.py)
    def show(self) -> None
    def close(self, animate: bool = True) -> None
```

`ContextMenu` se retira (lo reemplaza `widgets.menus.Menu`).

---

## 11. Hojas y diálogos: `sheets.py`, `dialogs.py` (rol S2)

```python
# sheets.py
class SheetLayer(tk.Canvas, Host):
    def __init__(self, root, animator): ...      # place 0,0 relwidth/relheight 1, lift
    def open(self) -> None ; def close(self, on_done=None) -> None
class Sheet:
    def __init__(self, app, title: str, *, message: str = "", width: int = 480, kind: str = "sheet"): ...
        # kind: "sheet" | "alert"
    panel: GlassPanel        # cuerpo de vidrio; los hijos van en `content`
    content: Clear           # zona entre mensaje y botones (pack vertical)
    def add_group(self) -> "W.Card"                         # Card(radius=16) empaquetada en content
    def add_row(self, group, label: str, widget_factory) -> object   # fila de 44: etiqueta + widget creado por la fábrica(master)
    def set_buttons(self, buttons: list[dict]) -> None
        # dict(text=, command=, style="fill"|"prominent"|"destructive", tone="accent", default=False, cancel=False)
    def open(self) -> None
    def close(self, animate: bool = True) -> None
    on_escape: object        # callable; por defecto close

# dialogs.py
def confirm(app, title: str, message: str, confirm_text: str, on_confirm, tone: str = "rose") -> None
def start_session(app) -> None          # llama app._start(focus_s, break_s, tolerance_s, preset)
def tune(app) -> None                   # app._handle(app.engine.reconfigure(...)) + aviso
def goal(app) -> None                   # settings + app.apply_settings() + app.views["Ajustes"].refresh()
def save_session(app, record: dict) -> None   # misma lógica de guardado/descartar que hoy
```

---

## 12. App ↔ vistas (rol S1 y V1–V4)

### 12.1 Lo que se conserva

- Las vistas siguen siendo `FocusView, HistoryView, InsightsView, SettingsView` en
  `views/*.py`, construidas como `Vista(master, app)`, **ahora subclases de
  `surface.ViewSurface`** (antes `ctk.CTkFrame`). `master` = `app.stage`.
- Métodos que la app llama: `view.refresh()`; `FocusView.refresh_engine(engine, now=None)`,
  `.set_config_text(engine, settings)`, `.refresh_today(db, settings)`;
  `HistoryView.refresh_tags()`, `.focus_day(day)`; `InsightsView.refresh_tags()`,
  `.current_rows()`.
- Atributos/métodos de `app` que usan las vistas: `fonts, animator, db, settings, toasts,
  hashtag_popup, confirm, apply_settings, mark_stale, open_day, export_csv, import_legacy, on_end,
  on_primary, on_short_pause, on_toggle_phase, show_tune_dialog, show_goal_dialog`.
- Atributos de `app` que lee `shoot.py`: `views, show_view, settings, toasts(.show,.active),
  toggle_floating_tab, animator(._tweens), nav (con .select/.get), tab, splash(.window), fonts,
  engine, db, hashtag_popup, _end_session, _shutdown, _refresh_engine_ui, show_start_dialog,
  show_tune_dialog, show_goal_dialog, on_pause, on_end`.

### 12.2 Lo nuevo

| De la app (S1) | Para |
|---|---|
| `app.stage: Stage`, `app.backdrop: Backdrop` | vistas (colocar hijos), hojas |
| `app.sidebar: Sidebar` y `app.nav = app.sidebar` | compat |
| `app.a11y: Accessibility` | Ajustes (fila de accesibilidad) |
| `app.toggle_floating_tab()` (ya existe) | botón `pip` de Enfoque y fila de Ajustes |
| `app.volume_model: VolumeModel` | Sidebar y Ajustes |
| `app.booted: bool` | pestaña flotante |
| `app.set_setting(key, value)` → guarda, aplica (`apply_settings`) y refresca lo afectado | Ajustes (guardado inmediato) |
| `app.current_view: str` | vistas |
| `app.rebuild_ui()` → destruye y vuelve a crear barra lateral y vistas conservando motor, vista actual y diálogos cerrados | Aumentar contraste |
| `app.dialogs` (módulo `dialogs`), y `app.confirm/show_*_dialog` como delegados | vistas (sin cambios para ellas) |

| De la vista (V1–V4) | Para |
|---|---|
| `on_activate()` / `on_deactivate()` (heredados de ViewSurface) | la app al cambiar de vista |
| `FocusView.refresh_engine` sólo toca lo que cambió (idempotente) | tick |

### 12.3 Flujo del tick (S1)

`root.after(500)` → `engine.tick()` → `_handle(events)` → `_refresh_engine_ui()`:
1. `fase = theme.PHASE_OF_STATE[estado]`; si cambió → `backdrop.set_phase(fase)`.
2. Si la vista activa es Enfoque **y** el root no está minimizado → `FocusView.refresh_engine`
   (idempotente); si no, `self._focus_dirty = True` y se refresca al volver a mostrarse.
3. `tab.update_from(engine)` (no hace nada si no está visible).

### 12.4 Flujos de notificación (resumen)

| Evento | Quién lo origina | Camino |
|---|---|---|
| Fase | app (`_refresh_engine_ui`) | `Backdrop.set_phase` → versión → Stage → hosts activos → `request_frame` de los vigilados |
| Tamaño de ventana | `Stage` (`<Configure>` del root, debounce 120 ms) | `Backdrop.resize` → hosts activos revalidan; inactivos marcan sucio |
| Layout dentro de un host | `<Configure>` de un `BackdropCanvas` | `host.invalidate()` → pasada de validación (after_idle) |
| Vista activa | `app.show_view` | `vieja.set_active(False)`, `nueva.set_active(True)` (+ transición de S1) |
| Ventana minimizada / restaurada | `<Unmap>/<Map>` del root (app) | `stage.set_active(...)`, `tab.sync_visibility()` |
| Accesibilidad | `Accessibility.subscribe` (app) | reduce_motion → `animator.reduced_motion`; transparencia/tinte → `theme.set_appearance` + `backdrop.set_mode` + avisar a hosts; contraste → `theme.set_appearance` + `app.rebuild_ui()` |
| Ventana activa/inactiva [D] | `<FocusIn>/<FocusOut>` del root (app) | `sidebar.set_window_active(...)` y vidrios de barras |
