# PLAN · ejecución del rediseño por roles y olas

Versión 1.0 · 03/10/2026. Lo que se construye está en `DESIGN_SPEC.md`; las firmas, en
`CONTRACTS.md`. `SP` = `/tmp/claude-0/-home-user-focus-flow/e1cc284d-b8f6-527a-9c84-85de88380066/scratchpad`.
Repo: `/home/user/focus-flow`. **Nadie hace commits**: el orquestador integra y commitea al final
de cada ola.

---

## 0. Resumen

| Ola | Roles (en paralelo) | Depende de |
|---|---|---|
| **1 · Fundaciones** | **R0** paquete widgets (mecánico) → al entregar arranca **D**; en paralelo desde el inicio: **A** tokens/tipografía/a11y · **B** render y materiales · **C** movimiento · **I** iconografía · **H1** ventanas sin marco | nada (D: R0) |
| **2 · Componentes** | **E** gráficos · **F1** botones y controles · **F2** navegación · **G1** avisos y menús · **G2** calendario y sonido · **H2** pestaña flotante y splash | ola 1 |
| **3 · Ensamblado** | **S1** shell (app.py) · **S2** hojas, diálogos y herramienta de capturas · **V1** Enfoque · **V2** Historial · **V3** Análisis · **V4** Ajustes | olas 1–2 |
| **4 · QA** | **Q1** visual/HIG · **Q2** funcional y rendimiento · **Q3** código | olas 1–3 |
| **5 · Correcciones** | los dueños de cada archivo con defectos (mismo reparto) + re-QA parcial | ola 4 |

**Decisión sobre `widgets.py`**: se parte en el paquete `focusflow/widgets/` (R0, puramente
mecánico, primer paso de la ola 1). Sin eso, `widgets.py` (1882 líneas) tendría un solo dueño y
sería el cuello de botella de toda la ola 2. R0 entrega antes que nadie porque **D** edita dos de
los archivos que R0 crea (`_base.py`, `surfaces.py`); por eso D arranca cuando R0 termina (R0 es
corto: < 30 min).

---

## 1. Matriz de propiedad (exclusiva por ola)

| Archivo | Ola 1 | Ola 2 | Ola 3 | Ola 5 |
|---|---|---|---|---|
| `focusflow/widgets.py` → `focusflow/widgets/__init__.py` | R0 | — | — | R0* |
| `focusflow/widgets/_base.py`, `surfaces.py` | R0 crea → **D** | — | — | D |
| `focusflow/widgets/buttons.py`, `controls.py` (nuevo) | R0 crea | **F1** | — | F1 |
| `focusflow/widgets/navigation.py` | R0 crea | **F2** | — | F2 |
| `focusflow/widgets/charts.py` | R0 crea | **E** | — | E |
| `focusflow/widgets/overlays.py`, `menus.py` (nuevo) | R0 crea | **G1** | — | G1 |
| `focusflow/widgets/dates.py`, `sound.py` | R0 crea | **G2** | — | G2 |
| `focusflow/theme.py`, `a11y.py` (nuevo), `config.py`, `assets/fonts/*`, `CREDITS.md`, `.gitignore` | **A** | — | — | A |
| `focusflow/render.py` | **B** | — | — | B |
| `focusflow/icons.py` (nuevo) | **I** | — | — | I |
| `focusflow/anim.py` | **C** | — | — | C |
| `focusflow/frameless.py` (nuevo) | **H1** | — | — | H1 |
| `focusflow/surface.py` (nuevo) | **D** | — | — | D |
| `focusflow/floating.py`, `splash.py` | — | **H2** | — | H2 |
| `focusflow/app.py` | — | — | **S1** | S1 |
| `focusflow/sheets.py`, `dialogs.py` (nuevos) | — | — | **S2** | S2 |
| `focusflow/views/focus.py` | — | — | **V1** | V1 |
| `focusflow/views/history.py` | — | — | **V2** | V2 |
| `focusflow/views/insights.py` | — | — | **V3** | V3 |
| `focusflow/views/settings.py` | — | — | **V4** | V4 |
| `focusflow/engine.py`, `db.py`, `stats.py`, `system.py`, `views/__init__.py`, `Focus Flow.py`, `installer.iss`, `make_sounds.py` | **nadie** | | | |
| `README.md` | orquestador al final (cada rol anota en su reporte qué cambiar) | | | |
| `SP/tools/galeria.py` (nuevo, arnés de capturas de componentes) | **D** | — | — | D |
| `SP/tools/shoot.py` | — | — | **S2** | S2 |
| `SP/tests/test_<rol>.py` | cada rol el suyo | | | |
| `SP/reports/<rol>.md`, `SP/shots/<rol>/` | cada rol el suyo | | | |
| `SP/qa/*.md` | — | — | — | Q1–Q3 (ola 4) |

\* R0 sólo vuelve a tocar `__init__.py` si un `from .X import *` falla; en ola 2+ nadie lo toca
(cada módulo exporta con `__all__`).

---

## 2. Reglas de trabajo para todos los roles

1. **Leé primero**: `SP/AGENTS_CONTEXT.md`, `SP/design/DESIGN_SPEC.md`, `SP/design/CONTRACTS.md`, tu
   sección de este plan, y las auditorías `SP/audit/01..03` en lo que toque a tus archivos.
   Mirá `SP/design/mockup-enfoque.png` y `mockup-historial.png`, y `SP/design/mockup/mk.py` si
   dibujás vidrio, fondo, anillo, reloj o íconos.
2. **Copia privada**: trabajá en `SP/work/<rol>/repo`, no en el repo compartido:
   `rsync -a --delete --exclude .git --exclude __pycache__ /home/user/focus-flow/ $SP/work/<rol>/repo/`.
   Ahí podés poner **shims** (implementaciones provisorias) de módulos de otros roles para probar;
   **nunca los entregás**.
3. **Entrega**: al terminar copiás **sólo tus archivos** de la copia privada al repo
   (`cp` archivo por archivo) y verificás con `git -C /home/user/focus-flow status --short` que no
   tocaste nada ajeno. No hagas commits.
4. **Pantalla y datos propios**: `Xvfb :<N> -screen 0 1600x1000x24 &`, `export DISPLAY=:<N>`,
   `export LOCALAPPDATA=$SP/data-<rol>`. Nunca crees `focusflow.db`/`settings.json` en el repo.

   | Rol | R0 | A | B | C | I | H1 | D | E | F1 | F2 | G1 | G2 | H2 | S1 | S2 | V1 | V2 | V3 | V4 | Q1 | Q2 | Q3 |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
   | `:N` | 70 | 71 | 72 | 73 | 74 | 75 | 76 | 77 | 78 | 79 | 80 | 81 | 82 | 83 | 84 | 85 | 86 | 87 | 88 | 89 | 90 | 91 |

5. **Tipografías en Linux**: Tk sólo ve lo que conoce fontconfig. Creá
   `SP/work/<rol>/fonts.conf` con `<include ignore_missing="yes">/etc/fonts/fonts.conf</include>` y
   `<dir>…/repo/assets</dir>` (desde la ola 2; en la ola 1, `<dir>$SP/inter/extras/ttf</dir>`) y
   exportá `FONTCONFIG_FILE`. PIL carga por ruta. (shoot.py ya hace esto solo.)
6. **Python**: `$SP/venv/bin/python` (no hay pytest: pruebas con `unittest`). Tus pruebas van en
   `SP/tests/test_<rol>.py`, se corren con
   `$SP/venv/bin/python -m unittest discover -s $SP/tests -p 'test_<rol>.py' -v`, apuntando al repo
   por `FOCUSFLOW_REPO` (o tu copia privada mientras desarrollás). Tienen que pasar contra el repo
   compartido después de entregar.
7. **Capturas**: componentes sueltos con `SP/tools/galeria.py` (lo entrega D en la ola 1; antes,
   cada uno arma su canvas de prueba); la app entera con `SP/tools/shoot.py` (ver su docstring).
   Guardá en `SP/shots/<rol>/` y miralas vos con la herramienta de leer imágenes.
8. **Reporte**: `SP/reports/<rol>.md` (≤ 80 líneas): qué hiciste, desvíos del spec y por qué, lo
   que no pudiste verificar (sobre todo lo de Windows), qué hay que cambiar en el README, y
   pedidos a otros roles.
9. **Windows**: no rompas `ctypes.windll`, `winsound`, `keyboard`, `-transparentcolor`,
   `-toolwindow`, `state("zoomed")`, `AddFontResourceExW`. Todo camino de Windows conserva su
   respaldo y no se ejecuta fuera de Windows.
10. Comentarios y textos de la interfaz en **español rioplatense**, con el estilo del código actual.

---

## 3. Ola 1 · Fundaciones

### R0 · Paquete de widgets (mecánico)

- **Misión**: convertir `focusflow/widgets.py` en `focusflow/widgets/` sin cambiar comportamiento.
- **Archivos**: borra `focusflow/widgets.py`; crea `focusflow/widgets/{__init__, _base, buttons,
  controls, navigation, charts, surfaces, dates, sound, overlays, menus}.py`.
- **Reparto**: `_base` (scaling_of, fmt_*, MONTHS_ES, MONTHS_SHORT, WEEKDAY_*, PILCanvas, _dot, Dot)
  · `buttons` (SmoothButton, TONES, button) · `navigation` (_draw_icon, NavRail, SegmentedControl)
  · `charts` (DonutChart, MiniDonut, GoalRing, RadialHours, ProgressBar, TimelineBar, BarsView,
  Heatmap) · `surfaces` (Card, card_title, StatTile, Legend, Chip) · `dates` (MiniCalendar,
  _chevron, DateField) · `sound` (SpeakerButton, VolumeControl) · `overlays` (ToastManager,
  HashtagPopup) · `controls`, `menus`: vacíos con docstring y `__all__ = []`.
- Cada módulo: imports mínimos que necesite, `__all__` con sus nombres públicos. `__init__.py`:
  docstring del viejo `widgets.py` + `from ._base import *` … en el orden de CONTRACTS §9.
  Código **copiado tal cual** (ni una línea de lógica distinta).
- **Aceptación**:
  1. `python -c "from focusflow import widgets as W; [getattr(W, n) for n in NOMBRES]"` con la lista
     de 40 nombres de la auditoría 01 §2 (+ `MONTHS_SHORT`, `_draw_icon` no hace falta exportarlo).
  2. Capturas de `shoot.py --only 'enfoque-*,historial,analisis,ajustes,toast,popup-hashtags'`
     **idénticas píxel a píxel** a las de HEAD (misma semilla), hechas en tu copia privada.
  3. `errores.log` sin errores nuevos.
- **Verificación**: script de diff de imágenes (`ImageChops.difference(...).getbbox() is None`).
- **Esfuerzo**: S.

### A · Tokens, tipografía y accesibilidad

- **Misión**: paleta nueva con variantes, materiales, tarjetas, radios, espaciado, layout, escala
  tipográfica con pesos reales, vibrancy con pisos de contraste, detección de accesibilidad de
  Windows y ajustes propios; Inter empaquetada; arreglo del broadcast de fuentes.
- **Archivos**: `focusflow/theme.py`, `focusflow/a11y.py` (nuevo), `focusflow/config.py` (sólo
  `DEFAULTS` + `Settings.stage`), `assets/fonts/` (los 7 TTF de `SP/inter/extras/ttf/` de
  DESIGN_SPEC §2.9 + `LICENSE.txt` de `SP/inter/`), `CREDITS.md` (sección tipografías: Inter OFL
  empaquetada, SF Pro opcional local), `.gitignore` (excluir SF en `assets/` y `assets/fonts/`:
  `assets/**/SF-Pro*`, `assets/**/SFPro*`, `assets/**/SFUI*`; mantener `assets/*.otf`).
- **Lee**: render.py (mix), customtkinter (FontManager, ScalingTracker), auditorías 01 §3, 02 §3,
  03 §2.13–2.16, §5, §6.
- **Implementa**: CONTRACTS §1, §2, §3. **Depende de**: nada.
- **Aceptación**:
  1. `COLORS` contiene todas las claves de CONTRACTS §1.1 (prueba con la lista).
  2. Tabla de contraste de DESIGN_SPEC §6.1 reproducida por prueba con `theme.contrast` (cada par
     ≥ su mínimo); `label_on` cumple el piso sobre 200 colores de fondo al azar entre `#0C0A1F` y
     `#5A4A8F`.
  3. `apply_palette("contrast")` y vuelta a `"standard"` dejan `COLORS`, `DATA`, `PHASE_STYLE`,
     `HEAT_RAMP` idénticos al original (mismos objetos dict/list).
  4. En Xvfb con `FONTCONFIG_FILE` apuntando a `assets/`: `Typography(root).source == "inter"`,
     `fonts.pil("title3")` carga `Inter-SemiBold.ttf`, `fonts.pil("large_title")` carga
     `InterDisplay-Bold.ttf`; `fonts["section"].actual()["family"]` es "Inter" con peso bold en
     X11. Con un directorio de assets vacío cae a Segoe UI sin excepción.
  5. Simulación de SF: con archivos falsos renombrados (copias de Inter con nombre SF) en un assets
     temporal, `source == "sf"` y se eligen las rutas SF.
  6. `grep -n SendMessageW focusflow/theme.py` vacío.
  7. `read_windows_settings()` en Linux devuelve el respaldo; `Accessibility` combina
     "auto/on/off" con el sistema (prueba con un `read_windows_settings` simulado).
  8. Capturas: hoja de muestras `SP/shots/A/tokens.png` (paleta estándar y AC, tipografía en
     todos los roles con Tk y PIL lado a lado).
- **Esfuerzo**: M.

### B · Render y materiales

- **Misión**: fondo ambiental por capas, vidrio, sombras, tarjetas, texto con tracking, reloj
  tabular, cachés LRU, fondos `ndarray` en todas las funciones de dibujo; sin romper firmas.
- **Archivos**: `focusflow/render.py`.
- **Lee**: `SP/design/mockup/mk.py` (portar la matemática), `SP/proto/*.py`, 03 §4, 01 §4.
- **Implementa**: CONTRACTS §4. **Depende de**: nada (los materiales llegan por parámetro; probá
  con `SimpleNamespace`).
- **Aceptación**:
  1. Todas las funciones viejas devuelven lo mismo con fondo hex (diff = 0 contra HEAD en 12
     casos de prueba guardados).
  2. Con fondo `ndarray`, cada función devuelve el tamaño correcto y los píxeles fuera de la forma
     son exactamente los del arreglo.
  3. `glass_compose` reproduce `mk.glass` (diferencia media < 2 niveles, máx. < 12) en la escena del
     mockup; `ambient_compose` reproduce `mk.ambient` (media < 2).
  4. Tiempos (Xvfb, mediana de 5): `ambient_layers` 1920×1032 ≤ 60 ms; `ambient_compose` ≤ 8 ms;
     `glass_compose` 280×52 con forma cacheada ≤ 2 ms; barra lateral 240×1032 cacheada ≤ 12 ms;
     `progress_ring` 440 ≤ 6 ms; `draw_clock` ≤ 1 ms.
  5. `progress_ring(fraction=0.001)` no dibuja tapas; `draw_clock("11:11")` y `("00:00")` miden
     igual.
  6. Las cachés no pasan su tamaño (prueba que llena 200 tamaños).
  7. Captura `SP/shots/B/materiales.png`: los 6 materiales × (normal, hover, presionado, RT, AC) y
     una tarjeta con sombra sobre el fondo de cada fase.
- **Esfuerzo**: L.

### C · Movimiento

- **Misión**: resortes interrumpibles con velocidad, tokens, materialización, movimiento reducido,
  coalescer redibujos por cuadro, registrar errores; sin romper la API actual.
- **Archivos**: `focusflow/anim.py`.
- **Lee**: `SP/proto/spring_proto.py`, 03 §3, 01 §5.
- **Implementa**: CONTRACTS §6. **Depende de**: nada.
- **Aceptación** (con un widget falso que simula `after` y un reloj controlado):
  1. `SpringSpec(0.5, 0.3)` → rigidez 157,9 y amortiguamiento 17,6 (±0,1).
  2. `bounce 0.15` sobrepasa 0,3–0,8 %; `bounce 0` no sobrepasa.
  3. Interrumpir a mitad con otro objetivo: la velocidad es continua (|Δv| entre cuadros < 5 % del
     pico) y el valor no salta.
  4. Sin tareas, el ticker no reprograma `after`; `idle` es True; `frame_count` no crece.
  5. `request_frame(w)` pedido 10 veces en un cuadro llama `w.redraw()` 1 vez.
  6. `reduced_motion=True`: `spring()` salta al objetivo en 1 llamada; con `fade=True` dura 0,15 s.
  7. Una excepción en `on_update` se imprime una vez con traceback y la tarea se descarta.
  8. `to/color/sequence/cancel/is_running/stop`, `AnimatedValue`, `AnimatedVector` y `_tweens`
     siguen funcionando igual (pruebas de regresión).
- **Esfuerzo**: M.

### I · Iconografía

- **Misión**: juego de íconos propios (DESIGN_SPEC §2.10) dibujado con PIL.
- **Archivos**: `focusflow/icons.py`.
- **Lee**: `mk.icon` (13 íconos de referencia), 02 §3 T7.
- **Implementa**: CONTRACTS §5.
- **Aceptación**: todos los nombres obligatorios a 16/18/40 px y escala 1,0/1,5 sin error; trazo
  visible (≥ 1 px con α > 128 en el centro del trazo); nombre desconocido → `KeyError`; caché
  acotada; hoja de contacto `SP/shots/I/iconos.png` (blanco sobre `#1C1938` y `accent` sobre el
  vidrio lateral) revisada a ojo: mismo peso óptico, centrados en la grilla, sin cortes.
- **Esfuerzo**: M.

### H1 · Ventanas sin marco (infraestructura)

- **Misión**: `FramelessWindow` y utilidades de foto de pantalla para avisos, menús, sugerencias,
  pestaña y splash, con color clave (defecto), alfa por píxel opcional (Windows,
  `FOCUSFLOW_LAYERED=1`) y respaldo X11.
- **Archivos**: `focusflow/frameless.py`.
- **Lee**: floating.py, splash.py, widgets (ToastManager, ContextMenu), 01 §6.1, 03 §4.9–4.11.
- **Implementa**: CONTRACTS §8 (su propia composición de borde contra lo de atrás, sin depender de
  render nuevo).
- **Aceptación**: en Xvfb, una cápsula RGBA mostrada con `show_image` deja `#FE00FE` fuera de la
  forma, borde suavizado contra `behind` (ningún píxel magenta parcial); `snapshot` devuelve una
  imagen del tamaño pedido; `grab_behind` antes de mostrar no incluye la propia ventana;
  `edge_color_around` da el promedio esperado sobre un fondo de color conocido; `scale` = escala de
  ventana de CTk; con `FOCUSFLOW_LAYERED=1` fuera de Windows sigue en color clave; código
  `UpdateLayeredWindow` presente, protegido y documentado como "a verificar en Windows".
- **Esfuerzo**: M.

### D · Superficies y escenario (camino crítico)

- **Misión**: la arquitectura de ventana (CONTRACTS §7): `Backdrop`, `Host`, `BackdropCanvas`,
  `Clear`, `Stage`, `ViewSurface`, `ScrollSurface`, `GlassPanel`, enrutador de rueda; `PILCanvas`
  sobre `BackdropCanvas`; componentes de superficie (`Card`, `card_title`, `StatTile`, `Legend`,
  `Chip`, `Dot` + nuevos `Label`, `PageHeader`, `KeyHints`, `ContentUnavailable`, `Separator`);
  arnés de capturas de componentes.
- **Archivos**: `focusflow/surface.py` (nuevo), `focusflow/widgets/_base.py`,
  `focusflow/widgets/surfaces.py`, `SP/tools/galeria.py` (nuevo).
- **Lee**: todo el código de widgets, app.py (cómo se apilan las vistas), 01 §4, 03 §4.2–4.8.
- **Implementa**: CONTRACTS §7, §9.1 (filas de `_base` y `surfaces`), §9.2 (`surfaces.py`).
  **Depende de** (por contrato, con shims en su copia hasta integrar): A (tokens, `Typography.tk`,
  `label_on`, `SHADOWS`, `CARD_STYLE`, `material`), B (`ambient_layers/compose`, `glass_compose`,
  `card_layer`, `apply_shadows`), C (`Animator.request_frame`, `to`).
- **`galeria.py`**: `stage_window(size=(1280, 800), phase="focus", scale=None) -> (root, app_like,
  stage, view)` (con `fonts`, `animator`, `backdrop`) + `capture(widget_or_root, path)` +
  `pump(root, ms)`; documentado en su docstring.
- **Aceptación**:
  1. Continuidad: un `Clear` y un `Label` dentro de una `ViewSurface` muestran exactamente los
     píxeles del fondo en sus bordes (diferencia máx. ≤ 2 niveles a través del borde en una captura).
  2. `Card` dentro de una vista: esquinas con el fondo real + su sombra; los hijos CTk con
     `fg_color="transparent"` toman `card.fill`; ninguna franja de otro color en la captura.
  3. Vistas inactivas no redibujan: con 4 vistas apiladas, un redimensionado redibuja sólo la
     activa (contador de `render()` por vista).
  4. Redimensionar 1280×800 → 1920×1032: un solo rebuild tras 120 ms, ≤ 120 ms total (sin vistas
     de la app: Stage + barra de prueba + vista con 4 tarjetas).
  5. Fundido de fase: 18 pasos en 1,2 s, cada paso ≤ 45 ms con una vista de prueba de 12 hijos.
  6. `ScrollSurface`: al desplazar 300 px el fondo de la región libre queda igual (diff ≤ 2) y las
     tarjetas se mueven 300 px; indicador visible y luego oculto; rueda funciona en X11
     (Button-4/5) y con `<MouseWheel>` simulado.
  7. `PILCanvas` con fondo hex: capturas de Historial/Análisis viejos (shoot.py) sin cambios
     visibles salvo los tokens nuevos (comparar a ojo; ningún error en `errores.log`).
  8. Ningún `after` huérfano al destruir una vista de prueba (`root.tk.call("after", "info")`
     vacío de ids propios).
- **Esfuerzo**: XL.

**Cierre de la ola 1 (orquestador)**: integrar; correr `SP/tests/test_{R0,A,B,C,I,H1,D}.py` contra
el repo; si fallan las de D por diferencias con A/B/C reales, D corrige antes de abrir la ola 2;
`shoot.py --only 'enfoque-*'` sin errores; commit.

---

## 4. Ola 2 · Componentes

Todos usan `SP/tools/galeria.py` para mostrar sus componentes **en todos sus estados** sobre el
fondo de las tres fases y a escala 1,0 y 1,5 (`ScalingTracker.set_widget_scaling(1.5)`), y
capturan en `SP/shots/<rol>/`.

### E · Gráficos

- **Archivos**: `focusflow/widgets/charts.py`.
- **Implementa**: CONTRACTS §9.1 (filas de `charts`) y DESIGN_SPEC §3.7.
- **Aceptación**:
  1. Cada gráfico renderiza con fondo hex y con `BACKDROP` (`GoalRing`, `TimelineBar` en el
     escenario).
  2. `GoalRing`: para D ∈ {300, 370, 440} y las 7 leyendas de Enfoque, el texto medido nunca supera
     0,62 × diámetro interior (prueba) y la captura no muestra texto sobre el trazo; el cambio por
     segundo (texto + arco) ≤ 5 ms a 440; con fracción 0 no hay punto.
  3. `DonutChart(key="live")`: 20 llamadas a `set_values` con totales crecientes (92 % estable) no
     crean tareas en el animador ni redibujos.
  4. `RadialHours` 240 ≤ 15 ms; `Heatmap.hovered()` existe y `tooltip_for` sin cambios.
  5. Escala 1,5: grosores, rótulos y celdas escalan (captura).
- **Esfuerzo**: L.

### F1 · Botones y controles

- **Archivos**: `focusflow/widgets/buttons.py`, `focusflow/widgets/controls.py`.
- **Implementa**: CONTRACTS §9.1 (`buttons`) y §9.2 (`GlassButton`, `GroupItem`, `GlassGroup`,
  `Button`, `Toggle`, `Slider`, `Stepper`, `TextField`, `TextArea`), DESIGN_SPEC §3.4–3.5.
- **Aceptación**:
  1. `SmoothButton.set_base_color` con el mismo color no crea tareas (prueba); `button()` y `TONES`
     compatibles (mismas claves, valores = claves de `COLORS`).
  2. `GlassButton` regular/prominente (4 tonos)/destructivo/ícono: estados normal, hover,
     presionado (escala 0,97 con resorte), deshabilitado, foco, seleccionado — captura en las 3
     fases; `set_visible` materializa y conserva el lugar.
  3. `GlassGroup.set_items` con los mismos ítems no anima; con otros, morph del ancho.
  4. `Toggle`/`Slider`/`Stepper` responden a `event_generate` de clic, teclado y rueda; `Slider`
     llama `command(v, final=True)` una sola vez al soltar; `Stepper` respeta límites y repetición.
  5. Hover/presión: ≤ 4 ms por cuadro (medido).
- **Esfuerzo**: L.

### F2 · Navegación

- **Archivos**: `focusflow/widgets/navigation.py`.
- **Implementa**: `Sidebar` (CONTRACTS §9.2, DESIGN_SPEC §3.6) y `SegmentedControl` (§9.1, §3.5);
  retira `NavRail` y `_draw_icon` (los reemplazan `Sidebar` e `icons`).
- **Aceptación**:
  1. Captura de la barra lateral a 1280×800 que coincide con `mockup-enfoque.png` (marca, filas,
     pie) en posiciones ±2 px.
  2. Interrumpir la píldora a mitad de camino (dos `select` seguidos) no produce salto de
     velocidad (registrar posiciones por cuadro).
  3. Ctrl+1…4, ↑/↓ y clic cambian la selección y llaman `command`.
  4. El toggle de pestaña llama `on_toggle_floating`; el deslizador guarda en disco sólo al soltar
     (contar escrituras de `Settings.save`).
  5. `SegmentedControl` selecciona solo al hacer clic y anima con `select`.
- **Esfuerzo**: M.

### G1 · Avisos y menús

- **Archivos**: `focusflow/widgets/overlays.py`, `focusflow/widgets/menus.py`.
- **Implementa**: `ToastManager`, `HashtagPopup` (§9.1), `MenuItem`, `Menu`, `PopUpButton` (§9.2);
  DESIGN_SPEC §3.9 y §3.5 (`PopUpButton`). Usan `frameless.FramelessWindow`.
- **Aceptación**:
  1. Avisos: simple, con acción, 3 apilados, reacomodo al cerrarse uno, con el root `withdraw()`
     (abajo a la derecha de la pantalla, dentro del área visible) — capturas.
  2. `HashtagPopup.attach` llamado 3 veces sobre el mismo textbox: una tecla se procesa una vez
     (contar llamadas al proveedor).
  3. `Menu` abre desde el rect del ancla (cuadros intermedios capturados), navega con teclado, se
     cierra con Esc y clic afuera, no deja `grab` colgado.
  4. `PopUpButton` tiene `get/set/configure(values=)` como lo usaban las vistas con `CTkOptionMenu`.
  5. Escala 1,5 correcta (todas las medidas × 1,5).
- **Esfuerzo**: L.

### G2 · Calendario y sonido

- **Archivos**: `focusflow/widgets/dates.py`, `focusflow/widgets/sound.py`.
- **Implementa**: `MiniCalendar`, `DateField` (§9.1, DESIGN_SPEC §3.8); `SpeakerButton`,
  `VolumeControl`, `VolumeModel` (§9.1–9.2).
- **Aceptación**: calendario igual al mockup del Historial (±2 px); iniciales "L M X J V S D";
  cambio de mes con resorte y sin "pop" del mes viejo; flechas de teclado; `selected` y
  `set_selected` compatibles; `VolumeModel` guarda a disco sólo con `final=True`; `VolumeControl`
  sigue funcionando con la lógica de silenciar/restaurar.
- **Esfuerzo**: M.

### H2 · Pestaña flotante y splash

- **Archivos**: `focusflow/floating.py`, `focusflow/splash.py`.
- **Implementa**: CONTRACTS §10, DESIGN_SPEC §3.10–3.11. Usan `frameless`, `render`, `icons` y
  `widgets.menus.Menu` (de G1, misma ola: probá con un shim de `Menu` y conectalo al integrar).
- **Aceptación**:
  1. **Bug compact_text**: `settings.json` con `{"floating_tab": true, "floating_tab_minimized":
     true}` y `root.withdraw()` antes de crear la app → sin excepción y sin pestaña hasta
     `app.booted`.
  2. Expandida/minimizada en las 3 fases y sin sesión, a escala 1,0 y 1,5, sobre fondo claro y
     oscuro (capturas): sin magenta, borde suave contra lo de atrás.
  3. `update_from` idempotente (sin render si no cambió el texto/fracción).
  4. Arrastre conserva el punto de agarre y guarda la posición al soltar; doble clic morph.
  5. Splash 400×128 centrado, con materialización (cuadros capturados con `--anim`).
- **Esfuerzo**: M.

**Cierre de la ola 2**: integrar; todas las pruebas de olas 1–2; la app vieja (vistas sin
migrar) tiene que seguir arrancando: `shoot.py --only 'enfoque-*,historial,analisis,ajustes'` sin
excepciones (puede verse mezclado); commit.

---

## 5. Ola 3 · Ensamblado

### S1 · Shell (app.py)

- **Archivos**: `focusflow/app.py`.
- **Misión**: Stage + Sidebar + vistas como `ViewSurface`; cambio de vista con transición;
  tick idempotente y con compuertas; redimensionado con debounce; accesibilidad conectada;
  `rebuild_ui`; pestaña flotante y avisos; arranque con splash nuevo; hotkeys intactos;
  delegación de diálogos a `dialogs`; [D] color de barra de título DWM y ventana inactiva.
- **Implementa**: CONTRACTS §12; DESIGN_SPEC §4.1, §5.2 (arranque, cambio de vista), §7.
- **Aceptación**:
  1. Arranque sin excepciones; `app.booted` True tras el splash; F8/F9/F10 siguen registrados
     (con `keyboard` simulado) y con respaldo `bind_all`.
  2. **Tick**: 20 ticks en concentración con Enfoque visible: mediana ≤ 8 ms, p95 ≤ 12 ms; con
     Análisis visible ≤ 2 ms; `animator.frame_count` crece ≤ 2 en 5 s de sesión estable.
  3. Cambio de vista: primer cuadro ≤ 60 ms; sin foto (ImageGrab que falla, simulado) cambia seco.
  4. Redimensionado 1280×800 → 1600×1000 → 1120×720: un rebuild por tamaño, sólo la vista activa.
  5. Con el root minimizado, Enfoque no se refresca y la pestaña sí.
  6. `rebuild_ui()` con contraste alto conserva vista actual, sesión en curso y ajustes.
  7. Recuperación: `RECOVERY_PATH` se sigue limpiando al arrancar y al terminar.
- **Esfuerzo**: L.

### S2 · Hojas, diálogos y herramienta de capturas

- **Archivos**: `focusflow/sheets.py`, `focusflow/dialogs.py` (nuevos), `SP/tools/shoot.py`.
- **Misión**: `SheetLayer`, `Sheet` y los 5 diálogos (DESIGN_SPEC §3.12); actualizar `shoot.py`
  para la interfaz nueva: diálogos capturados desde el root, estados nuevos (fundido de fase,
  RT/AC/RT+AC, menú de hashtags abierto, pestaña minimizada, aviso con la app minimizada,
  Análisis vacío, Ajustes abajo a 1120×720), animaciones nuevas (`fase`, `hoja`, `menu`), y que
  los estados viejos sigan andando con los atributos de CONTRACTS §12.1.
- **Aceptación**:
  1. Cada diálogo abre y cierra; Esc cancela; Enter acepta (salvo destructivos); Tab no sale de la
     hoja; el foco inicial es el primer campo.
  2. Los 5 diálogos entran a 1120×720 sin recortes (capturas) y se ven como DESIGN_SPEC §3.12.
  3. Misma lógica de negocio que hoy: guardar/descartar sesión, objetivo, ajustar ritmo,
     comenzar con preset (prueba de extremo a extremo con la base de prueba).
  4. `shoot.py --list` muestra los estados nuevos; una corrida completa termina con código 0.
- **Esfuerzo**: L.

### V1 · Enfoque

- **Archivos**: `focusflow/views/focus.py`.
- **Implementa**: DESIGN_SPEC §4.2 (layout, 7 estados, columna derecha), §5.2 (materializar
  grupo/ayuda/teclas/Terminar), idempotencia.
- **Aceptación**:
  1. A 1280×800, captura en concentración comparable con `mockup-enfoque.png`: posiciones de
     anillo, botones, tarjetas y textos ±4 px; mismos tamaños de tipografía.
  2. Los 7 estados a 1280×800, 1120×720 y 1600×1000 sin recortes (`redimension.json` con
     `clipped` vacío) y con la leyenda dentro del anillo.
  3. `refresh_engine` repetido con el mismo estado: 0 configuraciones de widgets, 0 tareas de
     animación (instrumentar con contadores).
  4. Tick ≤ 8 ms mediana con esta vista (junto con S1).
- **Esfuerzo**: L.

### V2 · Historial

- **Archivos**: `focusflow/views/history.py`.
- **Implementa**: DESIGN_SPEC §4.3.
- **Aceptación**: captura comparable con `mockup-historial.png` (±4 px); día vacío con
  `ContentUnavailable`; editar/guardar nota con `HashtagPopup` (adjuntado una sola vez); borrar con
  alerta; filtro por hashtag desde la barra y desde los chips; refrescar el mismo día no recrea
  tarjetas y no deja `after()` huérfanos (`invalid command name` ausente de `errores.log`).
- **Esfuerzo**: M.

### V3 · Análisis

- **Archivos**: `focusflow/views/insights.py`.
- **Implementa**: DESIGN_SPEC §4.4.
- **Aceptación**: cambio de rango ≤ 60 ms de bloqueo y píldora moviéndose ≤ 16 ms (medido con
  `perf_counter` y la animación `segmentado` de shoot.py); sin creación/destrucción de widgets en
  `refresh` (filas reutilizadas); mapa del año sólo se recalcula al cambiar el hashtag; fechas de
  récords en dd/mm/aaaa; estado vacío; filas 2 y 4 apiladas a 1120 si no entran; export CSV igual.
- **Esfuerzo**: M.

### V4 · Ajustes

- **Archivos**: `focusflow/views/settings.py`.
- **Implementa**: DESIGN_SPEC §4.5 (secciones, guardado inmediato, accesibilidad, pestaña y
  sonido, datos).
- **Aceptación**: todo visible y alcanzable a 1280×800 y 1120×720 (ningún control recortado ni con
  ancho < su mínimo, capturas arriba/medio/abajo); los 5 presets elegibles; cada control guarda al
  confirmar (prueba: cambiar y releer `settings.json`); cambiar accesibilidad aplica en vivo
  (RT/tinte) o reconstruye (AC); el texto de Datos muestra la carpeta real (`BASE_DIR`).
- **Esfuerzo**: M.

**Cierre de la ola 3**: integrar; todas las pruebas; `shoot.py` completo a 3 tamaños con
`--anim todas`; commit. Se abre la ola 4.

---

## 6. Ola 4 · QA (sólo lectura: no editan código; reportan en `SP/qa/`)

Cada QA corre `shoot.py` (con su display y datos) y escribe `SP/qa/Q<n>.md` con defectos
numerados: **severidad** (bloqueante / mayor / menor), **archivo y dueño**, **cómo
reproducir**, **evidencia** (captura o medición), **qué dice el spec**.

### Q1 · QA visual / HIG

Checklist (cada ítem contra DESIGN_SPEC):
- [ ] Mockups: Enfoque concentración e Historial a 1280×800 comparados lado a lado (diferencias
      > 4 px en posiciones o de color > 6 niveles en superficies, explicadas o reportadas).
- [ ] Paleta: superficies, etiquetas, acentos con los valores de §2.2 (muestreo de píxeles).
- [ ] Contraste: los pares de §6.1 en capturas reales (muestrear texto y fondo); ningún texto bajo
      4,5:1 salvo `tertiary` no esencial; nada blanco sobre rojo.
- [ ] Vidrio sólo en la capa funcional; tarjetas sólidas; nunca vidrio sobre vidrio; ningún widget
      CTk sobre fondo o vidrio (sin rectángulos de otro color alrededor de textos o controles).
- [ ] Materiales: brillo especular arriba, filo oscuro, sombra; prominente uno por vista.
- [ ] Radios de §2.7 y concentricidad (mosaicos 8 en tarjeta 24 con padding 16).
- [ ] Espaciado: márgenes 24, separación 20, encabezado en y 24–76, cuerpo desde 94.
- [ ] Tipografía: roles de §2.9 (tamaños medidos en capturas), pesos visibles (títulos bold/semibold
      distintos del cuerpo), nada < 11 px, reloj tabular (no "baila" entre dos capturas
      seguidas), leyenda dentro del anillo en los 7 estados.
- [ ] Íconos: mismo peso, alineados, acento en la barra lateral.
- [ ] Estados de cada componente (hover, presionado, deshabilitado, foco, seleccionado) en la
      galería de cada rol y en la app.
- [ ] Movimiento: cuadros de las animaciones de §5.2 (rebote sólo en `select`/`pop_in`/`release`,
      nada se anima por tick, menús nacen del control, materializar ≠ fundido simple).
- [ ] Accesibilidad visual: RT, AC y RT+AC sobre Enfoque, Historial y una hoja.
- [ ] Tamaños: 1120×720, 1280×800, 1600×1000 sin recortes ni franjas sin pintar.
- [ ] Escala 125 % y 150 % (`set_widget_scaling`/`set_window_scaling`): avisos, pestaña, splash,
      menú y sugerencias escalan igual que el resto.
- [ ] Textos en español rioplatense, sin anglicismos ni tuteo.

### Q2 · QA funcional y de rendimiento

Checklist:
- [ ] Motor: comenzar con cada preset; pausar (F8), volver (F9), pausa corta (F10) y su vencimiento;
      ir a descanso / a concentración; tolerancia y autopausa; bloque completo; sesión libre;
      ajustar ritmo en curso; terminar → guardar / no guardar.
- [ ] Atajos: F8/F9/F10 con `keyboard` simulado y con el respaldo `bind_all`; Ctrl+1…4; Esc/Enter
      en hojas; Tab dentro de hojas.
- [ ] Pestaña flotante: activar/desactivar (barra lateral, Enfoque y Ajustes), aparece sólo
      minimizada, arrastre y posición guardada, doble clic, menú (Minimizar/Expandir, Abrir Focus
      Flow, Cerrar pestaña), arranque con la pestaña activada y minimizada (bug compact_text).
- [ ] Sonidos: `SoundPlayer.play` llamado en cada evento del motor (con reproductor simulado);
      volumen y silencio persisten; deslizador escribe a disco sólo al soltar.
- [ ] Historial: calendario (mes, día, teclado), filtro por hashtag, editar nota con sugerencias,
      borrar con confirmación, día vacío, "Hoy".
- [ ] Análisis: los 4 rangos, filtro por hashtag, clic en el mapa abre el día, export CSV (archivo
      válido), estado vacío.
- [ ] Ajustes: cada control persiste en `settings.json` y se aplica (motor, vigilante, objetivo);
      importador del programa viejo con una `productivity.db` de prueba; accesibilidad en vivo.
- [ ] Recuperación: `.sesion-activa.json` se limpia; salir con sesión abierta pide confirmación.
- [ ] Avisos: todos los `toasts.show` de la app (28) se ven y se van; acción del vigilante.
- [ ] Presupuestos de DESIGN_SPEC §7.1 medidos y tabulados (tick, ticker apagado, resize, cambio de
      vista, fundido de fase, Análisis, RadialHours, arranque).
- [ ] `errores.log` sin tracebacks; ningún `invalid command name`.
- [ ] Bugs de la decisión 6 del orquestador cerrados (tabla §8 de este plan) con evidencia.

### Q3 · QA de código

Checklist:
- [ ] Propiedad: `git diff --stat` por archivo coincide con la matriz §1; nada en engine/db/stats/
      system.
- [ ] Contratos: firmas de CONTRACTS presentes y compatibles (script con `inspect.signature`);
      API de §9.1 intacta; claves de `COLORS` de §1.1 presentes.
- [ ] Windows: llamadas `ctypes.windll`/`winreg`/atributos Tk de Windows protegidas y con respaldo;
      `SendMessageW` ausente; `AddFontResourceExW` con `FR_PRIVATE`; `FOCUSFLOW_LAYERED` sólo en
      Windows.
- [ ] Sin `except Exception: pass` nuevos sin comentario; animaciones registran errores.
- [ ] Cachés acotadas; `PhotoImage` reutilizada; ningún `after` sin cancelar en `destroy`.
- [ ] Idempotencia de setters (lectura de código + pruebas).
- [ ] Código muerto retirado (`NavRail`, `_draw_icon`, `ContextMenu`, `_keep_maximized` si nadie lo
      usa, `MONTHS_SHORT` puede quedar) y nada nuevo sin uso.
- [ ] Estilo: comentarios en español rioplatense con la densidad del código existente; nombres
      consistentes; sin prints de depuración.
- [ ] Empaquetado: `assets/fonts/*.ttf` y `LICENSE.txt` presentes, `.gitignore` excluye SF,
      `CREDITS.md` actualizado, el comando de PyInstaller del README sigue sirviendo
      (`--add-data "assets;assets"` incluye `assets/fonts`).
- [ ] Todas las pruebas `SP/tests/test_*.py` pasan contra el repo.

---

## 7. Ola 5 · Correcciones

El orquestador reparte los defectos de `SP/qa/` por dueño (matriz §1). Cada dueño trabaja igual
que en su ola (copia privada, entrega sólo sus archivos) y agrega una prueba por cada defecto
bloqueante o mayor. Después, el QA que reportó re-verifica sólo esos ítems.

---

## 8. Bugs de la auditoría → dueño

| Bug (decisión 6) | Dueño | Prueba de cierre |
|---|---|---|
| Crash `compact_text` de floating.py | H2 (+ S1: `app.booted`) | H2 aceptación 1 |
| Ticks no idempotentes / ticker a ~49 fps | E (dona en vivo), D (`Chip`), F1 (`set_base_color`), V1 (`refresh_engine`), S1 (compuertas) | S1 aceptación 2, V1 aceptación 3 |
| Leyenda del anillo que desborda | E (`GoalRing`) + V1 (textos cortos) | E aceptación 2 |
| `HashtagPopup` duplica bindings | G1 | G1 aceptación 2 |
| Ajustes no entra a 1280×800 / tamaño mínimo | V4 | V4 aceptación |
| Redimensionar redibuja las 4 vistas | D (inactivas) + S1 (debounce/activación) | D aceptación 3, S1 aceptación 4 |
| Contraste insuficiente | A (paleta, `label_on`) + todos los consumidores | Q1 contraste |
| Escalado DPI en avisos/pestaña/splash/menú/popup | G1, H1, H2 | G1 aceptación 5, H2 aceptación 2 |
| Selector de rango de Análisis congela ~150 ms | V3 (+ E: `RadialHours`) | V3 aceptación |
| `SendMessageW` broadcast en theme.py | A | A aceptación 6 |
