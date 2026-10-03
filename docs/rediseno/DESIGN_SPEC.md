# DESIGN_SPEC · Focus Flow · Liquid Glass 2026 (macOS 27) en Windows

Versión 1.0 · 03/10/2026 · Dirección de diseño. Documento **normativo**.

- **Debe** = obligatorio (QA lo bloquea). **[D]** = deseable (QA lo anota, no bloquea).
- Toda medida está en **px lógicos a 96 dpi (100 %)**. Ver §1 para escalar.
- Referencias visuales que mandan: `SP/design/mockup-enfoque.png` y `SP/design/mockup-historial.png`
  (1280×800). La matemática de fondo, vidrio, sombras, anillo, reloj tabular e íconos está en
  `SP/design/mockup/mk.py` (código de referencia para portar, no para importar desde la app).
- Contratos de código: `SP/design/CONTRACTS.md`. Reparto de trabajo: `SP/design/PLAN.md`.
- `SP` = `/tmp/claude-0/-home-user-focus-flow/e1cc284d-b8f6-527a-9c84-85de88380066/scratchpad`.

---

## 0. Decisiones de base (lo que no se discute)

1. **Un Stage por ventana.** Cada ventana principal tiene un único `Stage` (el "Canvas de fondo")
   dueño de la **luz ambiente**: base casi negra violácea + manchas suaves + una **mancha de fase**
   que cambia de color con la sesión (sin sesión / concentración / no concentración) con un fundido
   de 1,2 s. Todo lo que se ve "a través" (huecos entre tarjetas, vidrio, texto suelto) es un
   recorte de ese fondo, calculado con numpy/PIL. No hay transparencia real entre widgets Tk.
2. **Dos capas.** Capa funcional = **vidrio** (barra lateral, botones y grupos de controles
   flotantes, segmentados, pop-ups, menús, popovers, avisos, hojas/diálogos, pestaña flotante).
   Capa de contenido = **tarjetas sólidas** con elevación sutil. Nunca vidrio sobre vidrio; lo que
   va encima del vidrio son **rellenos** (blanco con alfa) y etiquetas "vibrantes".
3. **Nada de widgets CustomTkinter sobre el fondo ni sobre el vidrio.** Sobre el fondo y el vidrio
   sólo hay `BackdropCanvas` (textos, contenedores transparentes, controles dibujados). Los widgets
   CTk (entradas, cuadros de texto) viven sólo dentro de superficies sólidas.
4. **Barra lateral de borde a borde** (macOS 27): vidrio que toca arriba, abajo e izquierda; sólo
   su filo derecho muestra brillo, refracción y filo oscuro. Íconos en el color de acento;
   selección en cápsula con texto semibold.
5. **Diálogos = hojas dentro de la ventana**: velo que oscurece una foto de la ventana y una hoja
   de vidrio centrada sobre la app (no sobre la pantalla), sin barra de título nativa.
6. **Ventanas sin marco** (avisos, menús, sugerencias de hashtag, pestaña flotante, splash): vidrio
   sobre una foto de lo que hay detrás tomada al abrirse (o vidrio sintético en la pestaña y el
   splash). Corte por color clave, con el borde suavizado contra lo de atrás.
7. **Tipografía**: SF Pro si está en `assets/` (local del usuario, no se distribuye) → Inter 4.1
   empaquetada (OFL) → Segoe UI Variable → Segoe UI. Pesos reales Regular/Medium/Semibold/Bold.
8. **Movimiento físico**: resortes interrumpibles que arrancan del valor y la velocidad
   presentes. Nada se anima en el tick del reloj. El ticker se apaga cuando no hay nada vivo.
9. **Un solo acento por vista** (celeste) y color de datos sólo en el contenido (menta =
   concentración, rosa = no concentración).

---

## 1. Unidades, escala y coordenadas

| Qué | Regla |
|---|---|
| Medidas | px lógicos a 96 dpi. En canvas y PIL: `round(v * s)` con `s = theme.ui_scale(widget)` (= `ScalingTracker.get_widget_scaling`). Radios y trazos se calculan en float (numpy) sin redondear. |
| Toplevels sin widget CTk | `s = ctk.ScalingTracker.get_window_scaling(root)`. |
| Fuentes Tk en ítems de canvas | `(familia, -round(px * s), peso)` vía `Typography.tk(rol, s)`. |
| Fuentes PIL | `Typography.pil(rol, s)` (tamaño `round(px * s)`). |
| Widgets CTk | se les pasa el valor lógico; CTk escala solo. |
| Coordenadas de fondo | siempre **de ventana** (área cliente del toplevel, px físicos): `x = w.winfo_rootx() - top.winfo_rootx()`. |
| Cambio de DPI (otro monitor) | el Stage escucha `<Configure>` del root y compara `ui_scale`; si cambió, invalida cachés y re-renderiza todo como en un redimensionado. |

---

## 2. Tokens

### 2.1 Fondo ambiental (Backdrop)

Fórmula (idéntica a `mk.ambient`): se calcula a **1/4 de resolución** en float32, se agranda con
`Image.resize(BILINEAR)` y se le suma un tramado 0/1 fijo (semilla 7) con `ImageChops.add` para
que el degradé no haga escalones.

`acc = bg_base` y, en orden, para cada mancha `(cx, cy, r, color, k)` (fracciones del ancho y alto
de la ventana): `d² = ((x−cx)·W/H)² + (y−cy)²`, `f = exp(−d² / (2·(r/2)²))·k`,
`acc += (color − acc)·f`.

| Capa | cx | cy | r | color | k |
|---|---|---|---|---|---|
| base `bg_base` | — | — | — | `#0C0A1F` | — |
| A violeta (detrás de la barra lateral) | 0,06 | 0,10 | 0,62 | `#5B3FD9` | 0,60 |
| B celeste (esquina superior derecha) | 0,98 | 0,02 | 0,46 | `#2E7FB8` | 0,34 |
| C magenta (abajo) | 0,62 | 1,04 | 0,58 | `#7A3C8F` | 0,32 |
| D verde azulado | 0,20 | 0,78 | 0,40 | `#1E5F73` | 0,26 |
| **E fase** (detrás del anillo de Enfoque) | 0,445 | 0,42 | 0,46 | según fase ↓ | según fase ↓ |

| Fase de luz | Estados del motor | color E | k E |
|---|---|---|---|
| `idle` | sin sesión | `#3B3F99` | 0,30 |
| `focus` | `focus` | `#1F9A6E` | 0,46 |
| `other` | `break`, `tolerance`, `paused`, `away` | `#A23C66` | 0,44 |

- La mancha E se guarda como **capa aparte**: `base` (A–D) + máscara `mE` (L, 0–255). El fondo de
  una fase es `composite(color_E, base, mE·k_E)`. Así el fundido de fase sólo interpola `color_E` y
  `k_E` (1,2 s, `in_out_cubic`, a 15 cuadros/s) y cada cuadro cuesta una composición en C.
- **Versión desenfocada** para el vidrio dentro de la ventana: radio 28 px (gaussiano a 1/4 con
  σ = 7 y agrandado). Se guarda `base_blur` y `mE_blur`; el desenfocado de una fase es
  `composite(color_E, base_blur, mE_blur·k_E)`.
- **Reducir transparencia**: todas las `k` × 0,5. **Aumentar contraste**: sin manchas, plano `#05040F`.

### 2.2 Paleta

Se conservan **todas** las claves actuales de `COLORS` (con valores nuevos) y se suman claves.
Columnas: estándar (oscuro) · **RT** = Reducir transparencia (vacío = igual) · **AC** = Aumentar
contraste.

#### Superficies

| Clave | Estándar | RT | AC | Uso |
|---|---|---|---|---|
| `bg_base` (nueva) | `#0C0A1F` | | `#05040F` | base del fondo, color de barra de título DWM |
| `app` | `#0C0A1F` | | `#05040F` | = `bg_base` (texto oscuro sobre acentos en `TONES`) |
| `sidebar` | `#15122E` | `#1A1736` | `#17143A` | color sólido equivalente del vidrio lateral |
| `bg` | `#12102A` | | `#0A0920` | fondo heredado (diálogos viejos); no usar en código nuevo |
| `surface` | `#1C1938` | | `#121027` | **tarjeta** |
| `surface_raised` (nueva) | `#252142` | | `#1C1938` | mosaicos, filas y campos dentro de tarjetas |
| `surface_sunken` (nueva) | `#120F28` | | `#05040F` | rieles de barras, fondos de gráficos |
| `surface2` | `#252142` | | `#1C1938` | = `surface_raised` (heredada) |
| `surface3` | `#2F2A50` | | `#2A2648` | riel del anillo vacío, botones `ghost` |
| `surface4` | `#3A355E` | | `#3A3660` | hover de `ghost` |
| `separator` (nueva) | `#2F2B4C` | | `#6E6A8C` | divisores de 1 px |
| `border` | `#2F2B4C` | | `#9A96B8` | = `separator`; en AC es el borde visible de tarjetas |
| `border_soft` | `#252142` | | `#6E6A8C` | |
| `hairline` (nueva) | `#2B2847` | | `#9A96B8` | |
| `overlay` | `#08071A` | | `#000000` | color del velo de hojas |
| `focus_ring` (nueva) | `#64D2FF` | | `#FFFFFF` | anillo de foco de teclado, 2 px |

#### Etiquetas sobre superficies sólidas (opacas)

| Clave | Estándar | AC | Contraste sobre `surface` / `surface_raised` | Uso |
|---|---|---|---|---|
| `label` / `text` | `#F4F3FA` | `#FFFFFF` | 15,3 / 13,9 | texto principal |
| `text_muted` | `#C6C4D8` | `#E6E4F4` | 9,9 / 8,9 | texto secundario fuerte (valores, leyendas) |
| `label_secondary` / `text_dim` | `#A9A6BF` | `#DAD8EC` | 7,1 / 6,5 | texto secundario, metadatos |
| `text_faint` | `#8E8BA9` | `#ADA9C8` | 5,2 / 4,7 | ayudas y pistas (cumple 4,5:1) |
| `label_tertiary` (nueva) | `#7F7C98` | `#ADA9C8` | 4,2 / 3,8 | **sólo** placeholder, deshabilitado y texto no esencial ≥ 13 px |
| `label_quaternary` (nueva) | `#4A4766` | `#6E6A8C` | 1,9 / 1,7 | **nunca texto**: marcas, líneas punteadas |
| `on_accent` (nueva) | `#0C0A1F` | `#05040F` | ≥ 8,7 sobre cualquier acento | etiqueta sobre rellenos de acento |
| `danger_text` (nueva) | `#FF7A7F` | `#FF9AA0` | 6,7 / 6,1 | texto destructivo ("Borrar", "Terminar sesión") |

#### Acentos (con hover/presionado/suave)

| Clave | Estándar | `_hover` | `_press` | `_soft` (α 0,22 sobre `surface`) | AC |
|---|---|---|---|---|---|
| `accent` | `#64D2FF` | `#7BD9FF` | `#58B9E0` | `#22405E` | `#8BE0FF` |
| `mint` | `#5FE3A1` | `#79E8B2` | `#54C88E` | `#24474A` | `#7CF0BE` |
| `rose` | `#FF8A9E` | `#FF9EAF` | `#E0798B` | `#4B2E4D` | `#FFA8B6` |
| `amber` | `#FFC56B` | `#FFD08A` | `#E0AD5E` | `#4A3B3E` | `#FFD38A` |
| `lavender` | `#B4A5FF` | `#C2B6FF` | `#9E91E0` | `#3A3466` | `#CEC4FF` |
| `danger` | `#FF5A60` | `#FF7378` | `#E04F54` | `#4B2236` | `#FF7A80` |
| `orange` | `#FF9F45` | `#FFB066` | `#E08C3D` | `#4B3433` | `#FFB873` |
| `yellow` | `#FFD84D` | `#FFE170` | `#E0BE44` | `#4A4232` | `#FFE27A` |
| `pink` / `pink_text` | `#FFB3C4` / `#5C1F33` | | | | heredadas (los hashtags pasan a `lavender`) |
| `cream` / `cream_text` | `#FFE2B8` / `#5C3F12` | | | | heredadas, sin uso |

Se conservan las claves `accent_press`, `*_soft`, `*_hover` existentes con los valores de arriba.
**Nunca texto blanco sobre `danger`** (2,8:1): lo destructivo es texto `danger_text` sobre relleno
neutro.

#### Rellenos sobre vidrio y sobre sólidos (blanco con alfa, se componen al dibujar)

`FILLS` (alfa de blanco): `hover 0.07` · `selected 0.12` · `pressed 0.16` · `control 0.10` ·
`control_hover 0.14` · `control_pressed 0.18` · `track 0.16` · `keycap 0.12`. En AC todos × 1,8 y
con borde de 1 px blanco α 0,55.

### 2.3 Etiquetas sobre fondo y vidrio ("vibrancy")

El color se calcula opaco contra el **promedio del recorte** que hay debajo
(`theme.label_on(nivel, sobre_hex)`):

| Nivel | Base | α inicial | Piso de contraste |
|---|---|---|---|
| `label` | `#FFFFFF` | 0,92 | 7,0:1 |
| `secondary` | `#EBEBF5` | 0,64 | 4,5:1 |
| `tertiary` | `#EBEBF5` | 0,46 | 3,0:1 (sólo no esencial) |
| `quaternary` | `#EBEBF5` | 0,22 | — (decorativo) |

Si el contraste con `sobre_hex` no llega al piso, el α sube de a 0,02 hasta llegar (máx. 1,0).
Ejemplo medido: sobre el centro de la luz de concentración (`#194F4B`) el secundario inicial da
4,25:1 y el piso lo lleva a ≥ 4,5:1. En AC: `label #FFFFFF`, `secondary #DAD8EC`, `tertiary #ADA9C8`
fijos.

### 2.4 Datos y estados

| Token | Valor | Notas |
|---|---|---|
| `DATA["focus"]` | `mint` | concentración |
| `DATA["other"]` | `rose` | no concentración (descanso, tolerancia, pausa, pausa corta) |
| `DATA_LABELS` | "Concentración" / "No concentración" | sin cambios |
| `PHASE_STYLE` | (etiqueta, color, color de texto) por estado | se conserva; valores recalculados |
| `PHASE_DETAIL` (nueva) | idle "Sin sesión", focus "Concentración", break "Descanso", tolerance "Tolerancia", paused "En pausa", away "Pausa corta" | rótulo corto específico (insignia del anillo, pestaña) |
| `PHASE_LIGHT` (nueva) | idle/focus/other → (color, k) | §2.1 |
| `score_color(p)` | ≥ 70 `mint`, ≥ 45 `amber`, si no `rose` | sin cambios |
| `HEAT_RAMP` | `#1E1A40 → #21456A → #2A6F96 → #3E9CC4 → #64D2FF → #B8ECFF` | AC: `#2A2648 → … → #DFF6FF` |
| barras no destacadas | `mix(accent, fondo, 0.58)` | contra el fondo **real** de la tarjeta |
| línea de meta | `label_quaternary`, punteada 2/4 px | |

**Formato de datos** (español rioplatense; espacio no separable U+00A0 entre número y unidad):
duraciones `"1 h 17 min"`, `"17 min"`, `"45 s"`; relojes `mm:ss` y `hh:mm:ss` con cifras
tabulares; porcentajes `"92 %"` (también dentro de anillos); horas con coma decimal `"7,4 h"`;
fechas `dd/mm/aaaa` y la forma larga `"Sábado 3 de octubre"`; rangos `"Del 4/9/2026 al 3/10/2026"`.
`fmt_short` y `fmt_hours` pasan a estos formatos; se suma `fmt_pct`.

Colores semánticos de estado: éxito = `mint`, advertencia = `amber`, error = `rose` (texto) /
`danger_text` (acciones destructivas), información = `accent`, pausa corta = `lavender` (sólo en
avisos). Nunca son el único canal: siempre van con ícono o texto.

Tonos de aviso (clave de `COLORS` → ícono): `mint` → `checkmark.circle` · `rose` →
`exclamationmark.circle` · `amber` → `eye` (vigilante) · `lavender` → `pause.circle` · `accent` →
`info.circle` · `yellow`/`orange` → `pip`. El color del tono va **en el ícono**, no en el panel.

### 2.5 Materiales de vidrio

Fórmula: la de `mk.glass` (§3.4 de 03 y el prototipo): muestreo con refracción en el borde,
saturación sobre luminancia, tinte, relleno de estado, brillo especular (fuerte arriba), brillo
superior ("sheen"), sombra interior abajo; sombra proyectada + filo oscuro de 1 px los dibuja el
**host** (§3.1). La forma (SDF, máscara, desplazamientos, especular, sombra interior) se cachea por
`(w, h, r, material, escala)`.

| Parámetro | `sidebar` | `control` | `prominent` | `popover` | `sheet` | `hud` |
|---|---|---|---|---|---|---|
| Fuente del fondo | Backdrop desenfocado | Backdrop desenf. | Backdrop desenf. | foto de atrás | foto de la ventana | sintético |
| Desenfoque de la foto (px) | — | — | — | 32 | 32 | — |
| Tinte | `#14112C` | `#1C1840` | tono (`accent`/`mint`/`amber`/`rose`) | `#191536` | `#1A1638` | `#1A1638` |
| α del tinte | 0,56 | 0,42 | 0,90 | 0,66 | 0,72 | 0,88 |
| Saturación | ×1,30 | ×1,45 | ×1,20 | ×1,30 | ×1,25 | ×1,20 |
| Refracción ancho / fuerza (px) | 12 / 6 | 10 / 7 | 10 / 7 | 14 / 9 | 16 / 10 | 10 / 6 |
| Especular arriba / resto (α blanco) | 0,42 / 0,10 | 0,55 / 0,12 | 0,50 / 0,14 | 0,45 / 0,10 | 0,45 / 0,10 | 0,55 / 0,12 |
| Sheen (α, 40 % superior) | 0,05 | 0,06 | 0,08 | 0,05 | 0,04 | 0,06 |
| Sombra interior abajo | 0,10 | 0,16 | 0,16 | 0,14 | 0,12 | 0,12 |
| Filo oscuro 1 px (α negro) | 0,38 | 0,32 | 0,32 | 0,38 | 0,40 | 0,40 |
| Sombra: desenfoque / α / dy | — | 12 / 0,32 / 4 | 14 / 0,36 / 5 | 28 / 0,45 / 12 | 40 / 0,50 / 16 | (sólo con ventana con alfa) 16 / 0,40 / 6 |
| Etiqueta | vibrancy | vibrancy | `on_accent` (ámbar: `#1F1503`) | vibrancy | vibrancy | vibrancy |

- **`clear`** (variante transparente de Apple): tinte α 0, saturación ×1,10, refracción 10 / 8,
  especular 0,50 / 0,12, filo 0,30 y **capa de oscurecimiento negra α 0,35** si la luminancia media
  del recorte supera 0,5. **No se usa en Focus Flow** (todo es regular; nunca se mezclan las dos
  variantes); queda definida para una futura pestaña flotante con foto real del escritorio.
- **Estados dentro del vidrio** (rellenos blancos, no otro vidrio): hover +0,07 · seleccionado
  +0,12 · presionado +0,16 (+ escala 0,97, ver §5) · deshabilitado: etiqueta `tertiary` y, si es
  prominente, pasa a `control` con etiqueta `tertiary`. Prominente en hover: tinte +6 % de blanco.
- **Destructivo**: material `control`, etiqueta `danger_text`.
- **Regulador "Transparencia del vidrio"** (`glass_tint`, 0–100, defecto 50): multiplica el α del
  tinte por `m = 0,60 + 0,008·v` (v ≤ 50) o `m = 1,0 + 0,014·(v − 50)` (v > 50); tope 0,95.
  No afecta a `prominent`.
- **Reducir transparencia**: sin muestreo; cuerpo sólido `sidebar #1A1736`, `control #24204A`,
  `popover/sheet #201C42`, `hud #1C1840`, `prominent` = color del tono sólido; especular × 0,5;
  filo y sombras iguales.
- **Aumentar contraste**: cuerpo sólido `#17143A` + borde interior 1,5 px `#9795A6`; sin sheen;
  prominente = tono AC sólido con borde 1,5 px blanco.
- **Ventana inactiva** [D]: especular × 0,5, saturación ×1,10, íconos y etiquetas sobre vidrio
  mezclados 30 % hacia el promedio del vidrio. Se aplica en `<FocusOut>` real del root.

### 2.6 Tarjetas y grupos (capa de contenido)

| | Tarjeta (`Card`) | Grupo de formulario (`Card(radius=16)`) | Mosaico (`StatTile`) |
|---|---|---|---|
| Radio | 24 | 16 | 8 (concéntrico: 24 − 16) |
| Relleno | `surface` | `surface` | `surface_raised` |
| Padding interior | 16 (tarjetas de sesión: 20) | filas de 44, márgenes 16 | 12 |
| Borde interior 1 px | blanco α 0,06 | igual | — |
| Luz superior (sobre el borde de 1 px) | blanco α 0,10 que se apaga en `1,4·r` px | igual | — |
| Filo oscuro exterior 1 px | negro α 0,40 | igual | — |
| Sombra (la dibuja el host) | desenfoque 10 (σ 5), α 0,30, dy 3 | igual | — |
| AC | borde 1 px `#9A96B8`, sin luz ni sombra | igual | borde 1 px `#6E6A8C` |

Los hijos de una tarjeta deben quedar a ≥ 12 px de cada borde (con radio 24 la esquina invade
7 px). Sin cajas anidadas: dentro de una tarjeta sólo mosaicos (`surface_raised`) o filas con
separadores.

### 2.7 Radios y concentricidad

Regla: `r_hijo = max(r_padre − margen, 6)`; cápsula = `alto / 2`.

| Elemento | Radio |
|---|---|
| Ventana (Windows 11) | 8 restaurada / 0 maximizada (informativo) |
| Tarjeta | 24 |
| Grupo de formulario, tarjeta de sesión del Historial | 16 / 20 |
| Hoja (sheet) / alerta | 26 |
| Menú, popover, sugerencias | 14 (fila resaltada: 9 = 14 − 5) |
| Aviso (toast) | cápsula (`h/2`, h 40 → 20; 2 líneas h 56 → 22 tope) |
| Pestaña flotante | cápsula |
| Controles de alto ≥ 32 | cápsula |
| Controles de alto 28 (pop-up de formulario, stepper) | 8 |
| Teclas (F8…) | 5 |
| Mosaico dentro de tarjeta | 8 |
| Selección de día del calendario | círculo de 32 |
| Celda del mapa de calor | `round(celda × 0,28)` (14 → 4) |
| Barras de gráfico (arriba) | `min(6, ancho/2)` |
| Barras de progreso / línea de tiempo | cápsula |

### 2.8 Espaciado y layout

`SPACE` (grilla de 4; mismas claves, valores nuevos): `xs 4 · sm 8 · md 12 · lg 16 · xl 20 ·
2xl 24 · 3xl 32 · 4xl 40`.

`LAYOUT` (nuevo):

| Token | Valor |
|---|---|
| `sidebar_w` | 240 |
| `page_margin` | 24 (borde de la vista a contenido) |
| `header_h` | 52 (título 34 + subtítulo 18) |
| `header_gap` | 18 → el cuerpo arranca en y = 94 |
| `gutter` | 20 (entre tarjetas) |
| `card_pad` | 16 |
| `toolbar_h` | 36 · separación entre ítems 12 |
| `row_h` | 44 (filas de formulario) |
| `min_window` | 1120 × 720 · ventana inicial 1280 × 820 y después maximizar |

### 2.9 Tipografía

**Orden de resolución** (`Typography`):
1. **SF Pro** si hay archivos en `assets/` o `assets/fonts/` con alguno de estos nombres:
   `SF-Pro-Display-{Regular,Medium,Semibold,Bold}.otf`, `SF-Pro-Text-{Regular,Medium,Semibold,Bold}.otf`,
   `SF-Pro.ttf` (variable; ejes `wght`/`opsz` si están), y los viejos `SF-Pro-Text-*.otf`,
   `SFUIDisplay-Regular.otf`. Text < 20 px, Display ≥ 20 px.
2. **Inter 4.1 empaquetada** en `assets/fonts/`: `Inter-Regular.ttf`, `Inter-Medium.ttf`,
   `Inter-SemiBold.ttf`, `Inter-Bold.ttf`, `InterDisplay-Medium.ttf`, `InterDisplay-SemiBold.ttf`,
   `InterDisplay-Bold.ttf` + `assets/fonts/LICENSE.txt` (OFL).
3. **Segoe UI Variable** (Text/Display) → 4. **Segoe UI** (pesos: "Segoe UI", "Segoe UI Semibold",
   "Segoe UI" bold).

Registro en Windows: `AddFontResourceExW(ruta, FR_PRIVATE=0x10, 0)` **sin** `SendMessageW`
broadcast. Familias Tk en Windows (GDI, nombre legado): `Inter`, `Inter Medium`, `Inter SemiBold`,
`Inter Display`, `Inter Display Medium`, `Inter Display SemiBold` (+ `weight="bold"` para Bold). En
X11/fontconfig (desarrollo y capturas) sólo existen `Inter` e `Inter Display` con normal/bold:
Medium → normal, Semibold → bold (medido en este contenedor). PIL carga siempre el archivo exacto.

**Escala** (px a 96 dpi; tracking en em; "Tk" = ítem de texto/CTk, "PIL" = dibujado en imagen):

| Rol | Familia y peso | px / interlínea | Tracking | Motor | Uso |
|---|---|---|---|---|---|
| `clock` | Display Semibold | `round(0,18·D)` (D = diámetro del anillo; 440 → 79) | −0,01 | PIL, cifras tabulares por celda | reloj del anillo |
| `clock_sm` | Display Semibold | 22 / 26 | 0 | PIL tabular | pestaña flotante |
| `large_title` | Display Bold | 28 / 34 | 0 | PIL | título de cada vista |
| `sheet_title` | Display Bold | 20 / 26 | 0 | PIL | título de hojas y alertas |
| `title1` | Display Semibold | 22 / 28 | 0 | PIL | cifras grandes (porcentajes, métricas) |
| `title2` | Display Semibold | 20 / 24 | 0 | PIL | valores de mosaicos (tabular), encabezados de sección |
| `title3` | Text Semibold | 15 / 20 | −0,005 | Tk | títulos de tarjeta |
| `headline` | Text Semibold | 13 / 18 | 0 | Tk | títulos de fila, ítem seleccionado, valores |
| `body` | Text Regular | 13 / 18 | 0 | Tk | texto general |
| `control` | Text Medium | 13 / 18 | 0 | Tk | botones, navegación, segmentados |
| `control_lg` | Text Semibold | 15 / 20 | −0,005 | Tk/PIL | botón prominente grande |
| `callout` | Text Regular | 12 / 16 | 0 | Tk | descripciones, metadatos |
| `caption` | Text Medium | 11 / 14 | +0,01 | Tk/PIL | ejes, leyendas mínimas, teclas |
| `badge` | Text Semibold, MAYÚSCULAS | 11 / 14 | +0,06 | PIL | insignia del anillo, rótulo de fase |

Reglas: **nada por debajo de 11 px**; texto < 20 px que no se anima → ítem de texto Tk (ClearType);
≥ 20 px, con tracking o animado → PIL. Los relojes y cifras que cambian por segundo → PIL por
celdas (ancho del dígito más ancho, dos puntos centrados en la altura de las cifras), como
`mk.clock`.

Claves heredadas de `fonts[...]` (se conservan, con este mapeo): `title → title1` ·
`section → title3` · `card → headline` · `body → body` · `body_bold → headline` ·
`small → callout` · `small_bold → callout Semibold` · `tiny → caption Regular 11` ·
`tiny_bold → caption Semibold 11` · `micro → caption 11` · `button → control` ·
`button_lg → control_lg` · `metric → title1` · `metric_sm → title2` · `clock`, `clock_sm`,
`display (= large_title)`, `nav (= control)`.

### 2.10 Iconografía

`focusflow/icons.py`: íconos propios dibujados con PIL (no SF Symbols: su licencia no permite
Windows). Grilla de 24 unidades, trazo 1,75 px a 18 px (escala lineal con el tamaño, mínimo 1,5),
puntas y uniones redondeadas, supersampling 4× + LANCZOS, salida RGBA monocroma.

Tamaños: barra lateral 18 · barra de herramientas 18 · en línea con texto 16 · avisos 18 · menús 16
· estado vacío 40. Color: acento en la barra lateral; en el resto, el de la etiqueta vecina
(vibrancy o `label`/`secondary`).

Juego obligatorio (nombres estilo SF): `timer`, `calendar`, `chart`, `gear`, `pip`, `speaker`,
`speaker.slash`, `play`, `pause`, `stop`, `forward` (ir a descanso/concentración), `sliders`
(ajustar ritmo), `export`, `import`, `hashtag`, `chevron.left`, `chevron.right`, `chevron.down`,
`chevron.up.down`, `xmark`, `checkmark`, `checkmark.circle`, `exclamationmark.circle`,
`exclamationmark.triangle`, `info.circle`, `pause.circle`, `eye`, `pencil`, `trash`, `plus`,
`minus`, `today`, `flame` (racha), `target` (objetivo), `clock`, `arrow.up.forward.app` (abrir la
app). Referencia de trazo de los primeros 13 en `mk.icon`.

---

## 3. Componentes

Formato: **qué es · medidas · estados · material · movimiento**. Las firmas están en CONTRACTS.md.
"Fondo" = recorte del host (fondo ambiental o lo que corresponda).

### 3.1 Infraestructura visible (surface.py)

- **Stage** (uno por ventana): canvas que cubre el root; dueño del `Backdrop`. Casi nunca se ve
  (lo tapan barra lateral y vista activa); su `bg` es `bg_base` para que un hueco momentáneo no
  destelle.
- **ViewSurface** (una por vista): host que muestra su recorte del fondo + las **sombras de las
  tarjetas y vidrios registrados** en su subárbol. Al pasar a inactiva (otra vista al frente o
  ventana minimizada) deja de redibujar y marca sucio.
- **ScrollSurface**: host desplazable para Análisis, Ajustes y la lista del Historial. Fondo fijo
  a la ventana (el contenido pasa por encima, como en macOS); tarjetas y sombras se mueven.
  - Rueda: 64 px por muesca (Windows `delta/120`; X11 Button-4/5), con resorte `scroll`.
  - **Indicador superpuesto**: cápsula de 6 px (8 en hover) a 6 px del borde derecho del
    viewport, en el margen (nunca encima de tarjetas), alto ∝ viewport/contenido (mín. 32),
    blanco α 0,35 (hover 0,50); aparece al desplazar o con el puntero en el margen derecho;
    se desvanece 1,2 s después (tween 0,3 s). Arrastrable. **Nunca** barra de scroll de Tk/CTk.
  - Borde superior: corte limpio; [D] cuando `yview > 0`, la barra de herramientas de arriba
    refuerza su filo inferior (α 0,10 → 0,22).
- **Clear**: contenedor transparente (muestra su recorte). Para agrupar widgets sobre el fondo.
- **GlassPanel**: host de vidrio (barra lateral, cuerpo de hojas): su recorte = fondo + cuerpo de
  vidrio; sus hijos dibujan rellenos y texto encima.

### 3.2 `Label` (texto sobre fondo, vidrio o sólido)

Canvas con un ítem de texto Tk sobre su recorte. Rol tipográfico + nivel (`label`, `secondary`,
`tertiary`) o color fijo. Color por vibrancy (§2.3) contra el promedio del recorte, recalculado
cuando cambia el fondo (p. ej. fundido de fase). Ancho = medida del texto; con `wrap=True` envuelve
al ancho asignado y pide alto. `max_lines` con elipsis "…". Sin estados interactivos (salvo
`LinkLabel` = `Button(style="borderless")`).

### 3.3 `PageHeader`

Fila superior de cada vista (y = 24 a 76): título `large_title` (PIL) a la izquierda, subtítulo
`callout secondary` debajo (baseline 72), y a la derecha `.toolbar` (Clear, ítems de 36 de alto
centrados en y = 41, separados 12, alineados a la derecha en x = ancho − 24). El subtítulo se
recorta con elipsis antes de pisar la barra de herramientas.

### 3.4 Botones

| Variante | Dónde | Forma y medidas | Etiqueta | Estados |
|---|---|---|---|---|
| `GlassButton(style="regular")` | sobre el fondo (barras, Enfoque) | cápsula 36 (o la altura pedida); padding horizontal 16 (h 36), 28 (h 52); sólo ícono: círculo de 36 con ícono 18 | `control` vibrancy; ícono 18 | hover +0,07 · presionado +0,16 y escala 0,97 · deshabilitado: etiqueta `tertiary`, sin hover · foco: anillo 2 px `focus_ring` a 2 px del borde · seleccionado (toggle): +0,12 e ícono `accent` |
| `GlassButton(style="prominent", tone=…)` | la acción principal de la vista (uno por vista) | cápsula 52 × 280 en Enfoque; 36 en barras | `control_lg` (52) / `control` (36), `on_accent` (ámbar `#1F1503`) | hover tinte +6 % blanco · presionado escala 0,97 + tinte −6 % · deshabilitado → regular con `tertiary` |
| `GlassButton(style="destructive")` | "Terminar sesión" | como regular | `danger_text` | como regular |
| `GlassGroup` | grupo de acciones secundarias sobre el fondo | cápsula 40; segmentos de ancho = texto + 36; separador vertical 1 px × 20 (`quaternary` vibrancy) | `control` vibrancy | por segmento: resaltado cápsula inset 4 px (r = 16) +0,07 hover / +0,16 presionado; segmento deshabilitado `tertiary` |
| `Button(style="fill")` | sobre sólidos y sobre vidrio de hojas | cápsula 32 (r 8 si h 28); padding 16; ancho mínimo 88 | `control` `label` | relleno blanco 0,10 → hover 0,14 → presionado 0,18; deshabilitado α 0,5 |
| `Button(style="prominent", tone)` | botón por defecto de hojas, "Guardar" | igual | `control` Semibold `on_accent` | relleno tono → hover `_hover` → presionado `_press` |
| `Button(style="destructive")` | "Borrar", "No guardar", "Salir igual" | igual | `danger_text` | como fill |
| `Button(style="borderless")` | acciones dentro de tarjetas ("Cambiar…", "Editar") | sólo texto (+ ícono 16 a la izquierda, separación 6); área de clic ≥ 28 alto | `control` `accent` (destructiva: `danger_text`) | hover: color `_hover` · presionado: `_press` |
| `SmoothButton` / `button()` (compat) | código existente sobre sólidos | `corner_radius` = cápsula si h ≥ 32, si no 8 | según `TONES` | hover/press por color (tween); `set_base_color` **idempotente** |

`TONES` se conserva (mismas claves) con estos significados: `accent`, `mint`, `amber`, `rose`,
`lavender`, `orange`, `yellow` → relleno sólido del tono + etiqueta `app`; `ghost` →
`surface3`/`surface4` + `text`; `quiet` → `surface2`/`surface3` + `text`; `danger` →
`surface2`/`surface3` + `danger_text`.

### 3.5 Controles

- **`SegmentedControl`** (vidrio, en barras): cápsula 36 de material `control`; segmentos de ancho
  igual = máx(texto) + 28; píldora de selección = relleno blanco 0,16 cápsula inset 3 px (no otro
  vidrio) que se desliza con `select` y se **estira** hasta +12 % en la dirección del movimiento
  [D]; texto seleccionado `headline` `label`, resto `control` `secondary`; hover +0,07 en el
  segmento. **El clic selecciona solo** (además llama `command`). Teclado: ←/→ con foco.
- **`Toggle`**: regular 40×24 (perilla 20), mini 36×20 (perilla 16). Riel apagado: blanco 0,16
  sobre el fondo; encendido: `accent`. Perilla blanca con sombra (desenfoque 3, α 0,30, dy 1).
  Clic o Espacio alterna; la perilla viaja con `select`; [D] al presionar la perilla se ensancha
  4 px. Deshabilitado: todo al 50 % hacia el fondo. Foco: anillo.
- **`Slider`**: riel 4 px cápsula (blanco 0,16), tramo lleno `accent` (silenciado: `tertiary`),
  perilla círculo blanco 16 (14 en la barra lateral) con sombra; [D] al arrastrar la perilla pasa a
  lente de vidrio 22 px. `on_change(valor, final)`: `final=True` sólo al soltar (recién ahí se
  guarda a disco). Rueda ±5. Teclado ←/→ ±1, Re Pág/Av Pág ±10.
- **`Stepper`**: alto 28, relleno `surface_raised` r 8: `[−]` 28×28 · valor 64 (`body`, cifras
  tabulares, con unidad "min"/"s") · `[+]` 28×28, separadores de 1 px. Clic en el valor → edición
  en línea (CTkEntry del mismo color); Enter o perder foco confirma, Esc cancela. Rueda y ↑/↓ ±paso;
  mantener presionado repite (400 ms y después cada 80 ms). Fuera de rango: se ajusta al límite.
- **`TextField`** (CTkEntry con estilo): alto 32, r 8, `surface_sunken`, borde 1 px `separator`;
  con foco borde 2 px `accent`; texto `body` `label`; placeholder `label_tertiary`.
- **`TextArea`** (CTkTextbox con estilo): r 10, `surface_sunken`, borde 1 px `separator` (foco
  `accent`), padding 8, texto `body`; los `#hashtags` se colorean `accent` (etiqueta de texto Tk).
  Sin barras de scroll visibles salvo desborde.
- **`PopUpButton`** (menus.py): variante `glass` (barras: cápsula 36, ícono opcional 16 +
  texto `control` + `chevron.down` 12) y variante `fill` (formularios: alto 28, r 8,
  `surface_raised`, texto + `chevron.up.down` 12 a la derecha). Abre un `Menu` debajo, alineado a
  la izquierda, con ancho mínimo = el del botón y el ítem actual tildado. API compatible con lo que
  las vistas usaban de `CTkOptionMenu` (`get`, `set`, `configure(values=…)`).

### 3.6 Barra lateral (`Sidebar`)

Medidas a 1×, vidrio `sidebar` de borde a borde (la forma se extiende 40 px fuera de la ventana
arriba, abajo e izquierda).

| Pieza | Medidas |
|---|---|
| Marca | logo: anillo de 22 (trazo 3,2, `accent` al 72 %, riel blanco 0,14, punto `mint` de 5 a las 12) en x 19–41, centro y 36; "Focus Flow" Display Semibold 18, x 50, baseline 42 |
| Navegación | primera fila y = 76; fila 36; paso 40; píldora x 12–228 (cápsula r 18); ícono 18 en x 26 (`accent`); texto en x 54 centrado en la fila |
| Seleccionado | relleno blanco 0,12; texto `headline` (Semibold) `label` |
| No seleccionado | texto `body` `label`; hover relleno 0,06; presionado 0,16 |
| Separador del pie | 1 px `quaternary` vibrancy, x 20–220, en y = H − 24 − 32 − 8 − 32 − 12 |
| Fila "Pestaña flotante" | y = H − 24 − 72, alto 32: ícono `pip` 18 en x 22 (`secondary`), texto `body` en x 50, `Toggle` mini (36×20) en x 184 |
| Fila volumen | y = H − 24 − 32, alto 32: botón parlante 18 en x 22 (`speaker`/`speaker.slash`; clic silencia/restaura), `Slider` x 50–220, perilla 14 |
| Teclado | Ctrl+1…4 cambia de vista (en el root); ↑/↓ con la navegación enfocada |

Movimiento: la píldora persigue la fila con `select` (interrumpible; [D] se estira hasta +12 %
del alto en la dirección del viaje). El cambio de vista no espera a la píldora.

### 3.7 Gráficos (charts.py)

- **`GoalRing`** (anillo de la sesión): sobre el **fondo** (no en tarjeta), `background=BACKDROP`.
  Trazo `round(D × 0,032)` (440 → 14) con puntas redondeadas; riel blanco α 0,10 sobre el fondo;
  progreso del color de fase con **resplandor** (máscara del arco desenfocada σ = 0,9·trazo,
  α 0,22). Con progreso < 0,5 % no se dibujan las tapas (arregla el "punto" del arranque).
  Contenido: insignia `badge` (color de fase; en idle `tertiary`) a `cy − 0,20·D`; reloj `clock`
  en `cy − 6`; leyenda `body 15 px` `secondary` vibrancy a `cy + 0,15·D`, **ancho máximo
  0,62 × diámetro interior**, hasta 2 líneas, achicando hasta 12 px y con elipsis como último
  recurso: **nunca pisa el trazo**. Cache: (fondo + riel) por tamaño y versión del fondo; por
  segundo sólo se recompone arco + cifras (≤ 5 ms a 440). `set_progress` sin animación en el tick;
  con animación (`data`) sólo en saltos > 2 %.
- **`DonutChart`**: anillo `inner_ratio 0,74`, separación 3°, sin "glow". Centro: porcentaje
  `title1`; sin rótulo interno (lo explica la leyenda). Vacío: riel `surface3` fino
  (`inner_ratio 0,90`) y "—" en `tertiary`. En vivo (`key="live"`): **sin tween en el tick**;
  sólo redibuja si el porcentaje redondeado o el reparto cambian ≥ 0,5 %.
- **`MiniDonut`**: se conserva (el Historial nuevo no lo usa). Porcentaje con tamaño que entre en
  el hueco (`≤ 0,62 × interior`).
- **`RadialHours`**: perfil de 24 franjas, máx. 240; rótulos 0/6/12/18 **afuera** del círculo
  (caption `secondary`), centro con la mejor hora `title2`. Máscaras de sector cacheadas por tamaño:
  **≤ 15 ms** por render a 240.
- **`ProgressBar`**: cápsula, riel `surface_sunken`, relleno `accent` (`mint` al cumplir).
  `set_fraction`/`set_color` idempotentes; animan con `data`.
- **`TimelineBar`**: cápsula (alto 8 en Enfoque, 6 en Historial), riel `surface_sunken` (sobre el
  fondo: blanco 0,12), tramos `DATA` con 1 px de separación. Sobre el fondo usa `BACKDROP`.
- **`BarsView`**: barras con tope redondeado `min(6, w/2)`, ancho = 0,56 del slot (máx. 28);
  destacada = **hoy** (o la última) en `accent`, resto `mix(accent, fondo, 0.58)`; rótulos
  `caption` `secondary` (hoy `headline` `label`); valor sobre la barra destacada (`caption`
  `accent`); [D] línea de meta punteada con "meta" a la derecha. Vacío: texto `callout`
  `secondary` centrado.
- **`Heatmap`**: celda auto (10–20, gap 3), radio `round(celda·0,28)`; vacías `surface_raised`;
  rampa `HEAT_RAMP`; meses `caption secondary` (todos los meses que tengan ≥ 2 columnas, sin
  saltear), días L/X/V; hover: contorno 1,5 px `label` y tooltip propio en el encabezado de la
  tarjeta; **API pública `hovered()`** para no leer `_hover`. Clic abre el día en Historial.

### 3.8 Calendario (dates.py)

`MiniCalendar` dentro de tarjeta: encabezado "Octubre 2026" `title3` + flechas `chevron.left/right`
18 en `accent` (botones de 28 con hover relleno 0,07); fila de iniciales **L M X J V S D**
(`caption` `tertiary`); celdas de 36 de alto, ancho = (ancho − 32)/7; seleccionado: círculo de
32 `accent` con número `headline` `on_accent`; hoy: número `headline` `accent`; con sesiones: número
`label` + punto de 4 px debajo (`mix(surface, accent, 0.35 + 0.65·nivel)`); sin sesiones: `secondary`
(días pasados) o `tertiary` (futuros). Cambio de mes: el mes saliente se desliza y se desvanece y
el entrante entra (resorte `select`, desplazamiento 24 %). Teclado: flechas mueven el día, Re
Pág/Av Pág el mes. Atributo `selected` y `set_selected` se conservan. `DateField` se conserva
(estilo nuevo, popover con `Menu`/frameless).

### 3.9 Menús, popovers y avisos (Toplevels de vidrio)

- **`Menu`**: material `popover` sobre la foto de lo de atrás; radio 14; padding 6; filas de 28;
  texto `body`; ícono 16 opcional (o todos o ninguno por grupo); tilde `checkmark` 14 en una
  columna de 20 a la izquierda si hay ítems marcables; separador 1 px `quaternary` con 6 px arriba y
  abajo; resaltado: cápsula inset 4 px r 9 relleno blanco 0,12; deshabilitado `tertiary`. Ancho =
  máx(texto) + 48 (mín. 180). Máx. 12 filas visibles, después rueda. Teclado ↑/↓/Enter/Esc y
  búsqueda por inicial [D]. Abre **desde el control** (rect del ancla → rect final, `pop_in`),
  contenido desde el 40 %; cierra `pop_out`. Clic afuera o Esc cierra.
- **`ToastManager`**: cápsula de vidrio `popover`, alto 40 (2 líneas: 56), padding 16, ícono 18
  del tono + separación 10 + texto `body` `label` (máx. 2 líneas, ancho de texto máx. 360) +
  acción opcional `Button(style="prominent", tone)` alto 28 a 12 del texto. **Abajo al centro de
  la ventana**, a 24 del borde; se apilan hacia arriba con 8 de separación, máx. 3 (el más viejo se
  va). Si el root está minimizado, oculto o fuera de pantalla: abajo a la derecha del área de
  trabajo (24 de margen, 48 por la barra de tareas). Duración 3,2 s; con acción 9 s; el puntero
  encima pausa el tiempo [D]; clic en el cuerpo lo cierra. Al irse uno, los demás se reacomodan con
  `snappy`. Entrada `pop_in` (escala 0,92→1 y 12 px desde abajo), salida `pop_out`.
- **`HashtagPopup`**: menú `popover` de 240 de ancho, filas de 30, máx. 6, "#" en `tertiary` + tag
  en `label`, seleccionado con resaltado 0,12; contador "2/9" `caption` `tertiary`; debajo del
  cursor (+6) o arriba si no entra. **`attach` idempotente** (una sola vez por textbox).

### 3.10 Pestaña flotante (floating.py)

| | Expandida | Minimizada |
|---|---|---|
| Forma | cápsula alto 56 | cápsula alto 36 |
| Anillo | 32, trazo 4, riel blanco 0,16, x 12 | 20, trazo 3, x 8 |
| Texto | línea 1: `PHASE_DETAIL` en `badge` color de fase (baseline 23); línea 2: reloj `clock_sm` 22 tabular (baseline 45) | "14 min" `headline` `label` en x 34 |
| Ancho | 12 + 32 + 12 + máx(textos) + 18 (mín. 150) | 34 + texto + 14 |

Material `hud` sintético (degradé interno con resplandor del color de fase α 0,18 detrás del
anillo). Corte por color clave; el borde de 1 px se suaviza contra `edge_bg` = promedio del anillo
de 2 px **alrededor** de la pestaña tomado con `ImageGrab` al mostrarla y al soltar un arrastre (si
no hay captura: `#808080`). Hover +0,06; presionar escala 0,97; arrastre 1:1 respetando el punto de
agarre; doble clic alterna tamaño con morph de ancho/alto (`select`); clic derecho abre `Menu`:
"Minimizar"/"Expandir", "Abrir Focus Flow" (restaura la ventana), separador, "Cerrar pestaña".
Aparece **sólo** con la app arrancada (`app.booted`), la opción activa y el root minimizado
(`pop_in`); se va con `pop_out`. Ventana con alfa por píxel (sombra real, bordes suaves) sólo con
`FOCUSFLOW_LAYERED=1` [D, experimental].

### 3.11 Splash

400 × 128, radio 28, vidrio `hud` con un mini fondo ambiental adentro (manchas A y B). Logo: anillo
64 (trazo 7, `accent` 72 %, punto `mint` 10); "Focus Flow" `large_title` en x 112, baseline 60;
lema `callout` `secondary` baseline 84. Centrado en la pantalla. Entra `pop_in`; al terminar la
precarga sale con `pop_out` mientras el root pasa de α 0 a 1 en 0,28 s.

### 3.12 Hojas y alertas (sheets.py / dialogs.py)

- **Velo** (`SheetLayer`): canvas que cubre el root con una foto de la ventana (`ImageGrab` del
  área cliente justo antes) oscurecida: `foto × (1 − 0,38)` (AC: 0,55). Sin foto: el fondo
  ambiental oscurecido. Bloquea clics y foco del resto (Tab circula sólo dentro de la hoja).
- **Hoja**: `GlassPanel` material `sheet` sobre la foto desenfocada (32); radio 26; padding 24;
  ancho 480 (alertas 420, Guardar 560); centrada en x sobre la ventana; y = máx(72, (H − h)/2 −
  24). Título `sheet_title` alineado a la izquierda; mensaje `body` `secondary` (≤ 3 líneas);
  contenido en **grupos sólidos** (`Card(radius=16)` con color `surface`) para campos CTk; pie con
  botones a la derecha (alto 32, mín. 96 de ancho, separación 8): secundario `fill` + principal
  `prominent`. Enter = principal **salvo** destructivo; Esc = cancelar.
- **Contenidos**:
  1. *Confirmar* (alerta 420): título + mensaje + [Cancelar][Acción]. Tono `amber`/`accent` →
     `prominent`; `rose` → `destructive`.
  2. *Comenzar sesión* (480): mensaje "Elegí el ritmo. Podés cambiarlo con la sesión andando."; grupo
     con 5 filas de 44 seleccionables (nombre `headline`, pista `callout secondary`, a la derecha
     "25 / 5 min" `callout secondary`, tilde `accent` en la elegida; por defecto la que coincide
     con los ajustes); grupo con 3 filas `Stepper` (Concentración, Descanso, Tolerancia; tocar un
     stepper deselecciona el preset); [Cancelar][Comenzar].
  3. *Ajustar ritmo* (440): mensaje + grupo de 3 `Stepper` + [Cancelar][Aplicar].
  4. *Objetivo de hoy* (440): mensaje + fila de 4 `Button` (1 h, 2 h, 3 h, 4 h; el actual
     `prominent`) + grupo con "Minutos por día" `Stepper` (paso 15, 5–1440) + [Cancelar][Guardar].
  5. *Guardar sesión* (560): grupo con 5 métricas en columnas (Duración, Concentración,
     Productividad, Cortes, Bloques: rótulo `caption secondary` + valor `title2`), `TimelineBar` 8,
     "Nombre" `TextField` (placeholder "Sesión sin nombre"), "Anotaciones — usá # para etiquetar"
     `TextArea` de 96 con `HashtagPopup`; [No guardar (destructivo)][Guardar]. Esc = No guardar.
- Movimiento: velo de 0 a 1 en 0,20 s (tween); hoja `pop_in` desde escala 0,94 y 8 px arriba;
  contenido desde el 40 %. Cierre: `pop_out` + velo 0,18 s.

### 3.13 Otros

- **`Card`**, **`card_title`** (encabezado `title3` con padding 16/16/8), **`StatTile`** (mosaico
  `surface_raised` r 8, rótulo `caption secondary` con punto de 7 si hay color, valor `title2`
  tabular, cuenta animada con `data` sólo si `animate=True`), **`Legend`** (punto 8 + texto
  `callout secondary` + valor `headline` alineado a la derecha), **`Chip`** (cápsula 24, texto
  `caption` Semibold; `set_state` **idempotente**), **`Dot`**.
- **`SpeakerButton`** (ícono `speaker`/`speaker.slash` 18 dentro de un área de 28; hover relleno
  0,07; silenciado en `tertiary`) y **`VolumeControl`** (rótulo `caption secondary` "Sonido de la
  app" + parlante + `Slider`; misma lógica de silenciar y restaurar el nivel previo que hoy, vía
  `VolumeModel`). La barra lateral dibuja su propia fila de volumen con el mismo modelo.
- **`KeyHints`**: fila de teclas (tecla: relleno 0,12 r 5 alto 18, texto `caption` `label`,
  padding 6) + acción `callout` `secondary`, separación 6 y 16 entre pares.
- **`ContentUnavailable`**: ícono 40 `tertiary`, título `title3` `label`, texto `callout`
  `secondary` (ancho máx. 320, centrado), acción opcional `borderless`. Centrado en su área.
- **`Separator`**: 1 px `separator` (sobre sólido) o `quaternary` vibrancy (sobre vidrio).

---

## 4. Pantallas

### 4.1 Ventana

- Mínimo **1120 × 720**; arranca en 1280 × 820 y se maximiza. Todo entra sin recortes a
  **1280 × 800** y a 1120 × 720 (con scroll sólo donde está previsto: Análisis, Ajustes, lista del
  Historial).
- Regiones: `Sidebar` x 0–240 (alto total); vista activa x 240–W (alto total; la vista incluye sus
  márgenes de 24).
- [D] Windows 11: `DWMWA_CAPTION_COLOR = bg_base`, `DWMWA_BORDER_COLOR = #2C2650`.
- **Redimensionar**: el Stage espera 120 ms sin `<Configure>` y recién ahí reconstruye fondo,
  barra lateral y **sólo la vista activa**; las demás quedan sucias hasta mostrarse. Mientras se
  arrastra, se ve la imagen anterior (el canvas tiene `bg_base` en lo nuevo).

### 4.2 Enfoque (`views/focus.py`) — mockup `mockup-enfoque.png`

Cuadrícula: encabezado (y 24–76) + cuerpo (y 94 → H − 24). Columna derecha `R = clamp(0,36 ·
ancho_cuerpo redondeado a múltiplo de 10, 340, 420)`; izquierda = resto − 20. A 1280: izquierda
612 (x 264–876), derecha 360 (x 896–1256). A 1120: izquierda 472, derecha 340. A 1920: derecha 420.

**Columna izquierda (escenario, sobre el fondo, sin tarjeta)**, pila centrada verticalmente:

| Pieza | Alto | Notas |
|---|---|---|
| Anillo `GoalRing` | D = min(ancho_izq − 40, alto_cuerpo − 232, 440) | 1280×800 → 440; 1120×720 → 370 |
| separación | 20 | |
| `TimelineBar` (ancho D) + fila de leyenda | 8 + 8 + 16 | "Inicio 13:12" a la izquierda, "1 corte"/"N cortes" a la derecha, `callout secondary` |
| separación | 24 | |
| Botón principal `GlassButton(prominent)` | 52 × 280 | |
| separación | 12 | |
| `GlassGroup` secundario | 40 | |
| separación | 12 | |
| Ayuda (`Label callout secondary`, 1 línea, elipsis) | 16 | |
| separación | 8 | |
| `KeyHints` F8 pausar · F9 volver · F10 pausa corta | 16 | |

Lo que no corresponde a un estado se **desmaterializa** pero conserva su lugar (la pila no salta).

**Encabezado**: título "Enfoque"; subtítulo = configuración (sin sesión: "Al comenzar elegís el
ritmo. La pausa corta no te reinicia el bloque."; con bloques: "Pomodoro clásico · bloques de
25 min con 5 de descanso · pausa corta de 5 min"; libre: "Sesión libre · pausa corta de 5 min").
Barra: `GlassButton` ícono `pip` (toggle de pestaña flotante, seleccionado si está activa; tooltip
[D]) + `GlassButton(destructive)` "Terminar sesión" (sólo con sesión).

**Estados** (la app los decide en `refresh_engine`; nada se anima si no cambió):

| Estado | Insignia (color) | Anillo | Reloj | Leyenda | Principal (tono) | Grupo | Ayuda |
|---|---|---|---|---|---|---|---|
| sin sesión | SIN SESIÓN (`tertiary`) | sólo riel | duración del bloque por defecto "25:00" (libre: "00:00") | "Listo para empezar" | Comenzar sesión (`accent`) | oculto | oculta (teclas ocultas) |
| concentración | CONCENTRACIÓN · BLOQUE 2 (`mint`; sin bloque si es libre) | `mint`, progreso del bloque | restante mm:ss | "Restante del bloque" | Pausar (`amber`) | Pausa corta · Ir a descanso (si hay bloques) · Ajustar ritmo… | "Pausar reinicia el bloque. Para algo puntual, usá Pausa corta." |
| descanso | DESCANSO (`rose`) | `rose`, progreso del descanso | restante | "Descanso del pomodoro" | Volver a concentrarme (`mint`) | Pausa corta · Ir a concentración · Ajustar ritmo… | — |
| tolerancia | TOLERANCIA (`rose`) | `rose`, progreso | restante | "Se terminó el descanso" | Volver a concentrarme (`mint`) | igual | "Volvé antes de que se pause solo." |
| en pausa | EN PAUSA (`rose`) | `rose`, sin progreso | total hh:mm:ss | "Tiempo total de la sesión" | Volver a concentrarme (`mint`) | Pausa corta · Ajustar ritmo… | "El bloque arranca de nuevo." |
| pausa corta | PAUSA CORTA (`rose`) | `rose`, progreso del margen | restante | "El bloque está congelado" | Ya volví (`mint`) | Ajustar ritmo… | "Seguís donde lo dejaste." |
| sesión libre (concentrado) | CONCENTRACIÓN (`mint`) | `mint`, progreso = minutos de la hora en curso / 60 | transcurrido hh:mm:ss | "Sesión libre" | Pausar (`amber`) | Pausa corta · Ajustar ritmo… | igual que concentración |

La luz ambiente sigue la fase (`idle`/`focus`/`other`) con el fundido de 1,2 s.

**Columna derecha (tarjetas sólidas)**:
- *Reparto de la sesión* (alto 264): título `title3` (y + 16); `DonutChart` 120 a la izquierda
  (y + 52) con el % en el centro; `Legend` a la derecha (x + 160, filas a ±14 del centro de la
  dona, valores alineados a la derecha a 16 del borde); dos `StatTile` de 64 de alto (y + 188),
  "Tiempo total" y "● Concentración", valores hh:mm:ss tabulares. Sin sesión: dona vacía, "0 %",
  00:00:00.
- *Objetivo de hoy* (resto del alto): título + `Button(borderless)` "Cambiar…" a la derecha; fila
  "1 h 17 min de 3 h" `callout secondary` + "43 %" `headline`; `ProgressBar` 6; "Esta semana llevás
  7,4 h · racha de 6 días" `callout secondary`; separador; "Últimos 7 días" `headline`; `BarsView`
  que ocupa el resto (mín. 120) con hoy destacado y línea de meta.

### 4.3 Historial (`views/history.py`) — mockup `mockup-historial.png`

- Encabezado: "Historial"; subtítulo "31 sesiones guardadas desde el 4 de septiembre" (vacío:
  "Todavía no hay sesiones guardadas"); barra: `PopUpButton(glass, icon="hashtag")` "Todos los
  hashtags" / "#tag" + `GlassButton` "Hoy".
- Columna izquierda 300 (x 264–564):
  - Tarjeta calendario: alto 16 + 28 + 8 + 20 + 6×36 + 12 = 300 (siempre 6 filas).
  - Tarjeta "Resumen del día" (y + 320 hasta el fondo del cuerpo): título con la fecha larga
    ("Sábado 3 de octubre") `title3`; 3 filas de 28 (Sesiones · Concentración · Productividad, valor
    `headline` a la derecha, separadores); "El día en 24 horas" `headline` + barra de 10 con las
    sesiones del día ubicadas en 0–24 h (tramos `mint`/`rose`) + eje 0/6/12/18/24 `caption
    tertiary`; "Hashtags" `headline` + chips (cápsula 24, relleno `mix(surface, lavender, 0.20)`,
    texto `control` `lavender`; clic filtra por ese hashtag). Los chips ocupan como mucho dos
    filas (el resto se resume en un chip "+N"); si la tarjeta tiene menos de 290 de alto (p. ej. a
    1120×720) se muestra una sola fila, y si tiene menos de 250 se oculta el bloque Hashtags.
- Columna derecha (x 584–1256): `ScrollSurface` sin margen propio. Encabezado de sección sobre el
  fondo: "Sesiones del día" `title2` + resumen "2 sesiones · 1 h 35 min · 81 % concentrado"
  `callout secondary` a la derecha. Una tarjeta por sesión (radio 20, padding 20, separación 12):
  - título `title3` + % `title1` en `score_color` a la derecha;
  - metadatos `callout secondary` ("00:05 – 00:59 · 54 min · 2 bloques · Pomodoro clásico");
  - `TimelineBar` 6;
  - métricas: punto + "Concentración" `callout secondary` + "50 min" `headline`, ídem no
    concentración;
  - notas `body` `label` con `#hashtags` en `accent` ("Sin descripción" en `tertiary`); al editar
    se reemplaza por `TextArea` (mismo lugar, alto según contenido, mín. 72) con `HashtagPopup`;
  - separador + acciones a la derecha: `borderless` "Editar" (ícono `pencil`) → "Guardar"
    (ícono `checkmark`) y `borderless destructivo` "Borrar" (`trash`) → alerta de confirmación.
- Día vacío: `ContentUnavailable(calendar, "Sin sesiones este día", "Elegí otro día en el
  calendario.")` centrado en la columna.
- La lista **no se destruye entera** en cada refresco si el día no cambió (reutiliza tarjetas por id
  de sesión) y no deja `after()` huérfanos.

### 4.4 Análisis (`views/insights.py`)

- Encabezado: "Análisis"; subtítulo "Del 4/9/2026 al 3/10/2026 · 31 sesiones" (con hashtag:
  "#álgebra · …"); barra: `SegmentedControl` [7 días | 30 días | 90 días | Todo] +
  `PopUpButton(glass, hashtag)` + `GlassButton` ícono+texto "Exportar CSV…" (`export`).
- Cuerpo: `ScrollSurface` (y 94 → borde inferior de la ventana; padding inferior 24), filas con
  separación 20 sobre el ancho del cuerpo:
  1. *Resumen* (ancho completo, alto 104): 5 métricas en columnas iguales separadas por divisores
     verticales: rótulo `caption secondary` (con punto de color en Productividad/Concentración/No
     concentración) + valor `title1` tabular.
  2. *Reparto* (ancho 320, alto 300): `DonutChart` 160 + `Legend` debajo · *Concentración por día*
     (resto): título dinámico (día/semana/mes) + `BarsView` (alto 200) con rótulos de fecha cada
     N barras sin pisarse.
  3. *Mapa del año* (ancho completo): título + tooltip a la derecha del título (`callout
     secondary`); `Heatmap` que llena el ancho (semanas = las que entren con celda ≥ 14);
     pie "21 días con actividad · racha actual de 6 · mejor racha: 9" `callout secondary`.
  4. *Tu reloj de concentración* (ancho 440): `RadialHours` 240 + texto `callout secondary` ·
     *Por día de la semana* (resto): `BarsView` 160 (rótulos "Lun Mar Mié Jue Vie Sáb Dom") +
     "Récords" `headline` + filas (`callout secondary` / valor `headline` / fecha `callout
     tertiary` **en formato dd/mm/aaaa**).
  5. *Hashtags* (ancho completo): filas de 40: `#tag` `headline` `lavender`, meta a la derecha
     ("3,2 h · 81 % · 6 sesiones" `callout secondary`), `ProgressBar` 6 en `score_color`.
- A 1120 de ancho las filas 2 y 4 pasan a una columna si la columna flexible queda < 360.
- Sin datos en el período: una sola `ContentUnavailable(chart, "Sin datos en este período",
  "Probá con otro rango o hashtag.")`; con la base vacía: "Todavía no hay sesiones" + `borderless`
  "Ir a Enfoque".
- **Cambiar de rango**: la píldora empieza a moverse en ≤ 16 ms; el recálculo corre después del
  primer cuadro; no se crean ni destruyen widgets (filas reutilizadas); el mapa del año sólo se
  recalcula si cambió el hashtag; bloqueo total ≤ 60 ms.

### 4.5 Ajustes (`views/settings.py`)

Formulario agrupado estilo Ajustes del Sistema. Encabezado "Ajustes", subtítulo "Los cambios se
guardan solos". Cuerpo: `ScrollSurface`; columna centrada de ancho `min(680, ancho_cuerpo)`.
Secciones: título `headline` `secondary` vibrancy (8 arriba del grupo) + grupo (`Card(radius=16)`)
con filas de 44 (etiqueta `body` a la izquierda, control a la derecha, separadores inset 16) + pie
`callout secondary` (8 debajo). 28 entre secciones. **Sin botones "Guardar"**: cada control guarda
al confirmar (stepper/campo al Enter o al perder foco; toggle al cambiar; slider al soltar).

| Sección | Filas | Pie |
|---|---|---|
| Ritmo por defecto | Preset (`PopUpButton fill` con los 5 presets; "Personalizado" si no coincide) · Concentración `Stepper` min · Descanso min · Tolerancia min · Pausa corta min · Pasar al descanso automáticamente `Toggle` · Volver a concentración automáticamente `Toggle` | "Es lo que aparece propuesto al comenzar. Tolerancia: cuánto espera después del descanso antes de pausarse solo (0 la desactiva)." |
| Objetivo diario | Minutos de concentración por día `Stepper` (paso 15) | "Es la meta de la barra de Enfoque y de la racha." |
| Vigilante de distracciones | Activar `Toggle` · Esperar antes de avisar `Stepper` s · Palabras a vigilar (fila alta: `TextArea` 3 líneas, guarda al perder foco) | texto actual del vigilante |
| Pestaña flotante y sonido | Mostrar la pestaña al minimizar `Toggle` · Sonidos `Toggle` · Volumen `Slider` | — |
| Accesibilidad | Reducir movimiento · Reducir transparencia · Aumentar contraste (`PopUpButton fill`: Automático / Sí / No) · Transparencia del vidrio `Slider` (Ultra claro … Totalmente teñido) | "Automático sigue la configuración de Windows." |
| Datos | "31 sesiones guardadas, desde 04/09/2026 hasta 03/10/2026." · botones `fill` "Importar del programa viejo…" y "Exportar CSV…" | "La base es un archivo SQLite (focusflow.db) en <carpeta real de BASE_DIR>." |

Nada se recorta horizontalmente a 1120 × 720; todo es alcanzable con scroll.

### 4.6 Hojas, avisos, pestaña, splash

Ver §3.9–3.12. Los avisos siempre caben en pantalla; los diálogos nunca salen de la ventana (a
1120 × 720 "Comenzar sesión" mide ≤ 600 de alto).

---

## 5. Movimiento

### 5.1 Resortes y curvas

Parámetros de diseño `(duration, bounce)` → física con masa 1: `k = (2π/duration)²`,
`c = 4π(1 − bounce)/duration`. Integración semi-implícita en subpasos de 4 ms con el `dt` real.
Asentado: `|x − objetivo| < 0,5 px·escala` (o 1e-3 relativo) y `|v|` despreciable.

| Token | duration | bounce | Uso |
|---|---|---|---|
| `snappy` | 0,30 | 0,00 | cambios de estado, reacomodos, colores por resorte |
| `select` | 0,42 | 0,12 | píldoras (barra lateral, segmentado), perillas, mes del calendario, morph de la pestaña |
| `pop_in` | 0,38 | 0,15 | materializar: menús, avisos, hojas, grupos, pestaña, splash |
| `pop_out` | 0,24 | 0,00 | desmaterializar |
| `press` | 0,15 | 0,00 | hundirse al presionar (escala 0,97) |
| `release` | 0,40 | 0,30 | volver al soltar |
| `data` | 0,55 | 0,00 | anillos, barras, donas, contadores (sólo en saltos, nunca en el tick) |
| `page` | 0,28 | 0,00 | desplazamiento de 6 px en la transición de vista |
| `scroll` | 0,25 | 0,00 | desplazamiento con rueda |
| `hover` | tween 0,12 s `out_cubic` (salida 0,20 s) | — | rellenos de hover |
| `ambient` | tween 1,2 s `in_out_cubic` a 15 cuadros/s | — | luz de fase |

**Materializar** = un parámetro `m` 0→1 con `pop_in`: escala de la forma 0,94 + 0,06·m, α del
tinte × m, especular × m, sombra × m, refracción × m; el contenido (texto/íconos) pasa del color
del vidrio a su color final entre m = 0,4 y 1. **Desmaterializar** = lo inverso con `pop_out`.

### 5.2 Todas las transiciones

| Transición | Qué se mueve | Token | Reducir movimiento |
|---|---|---|---|
| Arranque | splash `pop_in`; al terminar splash `pop_out` + root α 0→1 0,28 s | pop_in/out | fundidos de 0,15 s, sin escala |
| Cambio de vista | foto de la vista vieja → foto de la nueva, fundido 0,20 s `out_cubic` y la nueva sube 6 px (`page`); en paralelo la píldora lateral (`select`). Sin foto (ImageGrab falla): cambio seco | page | fundido 0,15 s sin desplazamiento |
| Hover de cualquier control | relleno | hover | igual (no es movimiento) |
| Presionar / soltar control de vidrio | escala 0,97 / vuelta | press / release | sólo relleno, sin escala |
| Píldora lateral / segmentado | posición (+ estiramiento [D]) | select | salto + fundido de relleno 0,12 s |
| Toggle | perilla | select | salto |
| Slider (rueda/teclado) | perilla | snappy | salto |
| Cambio de fase | luz ambiente; color del anillo (`snappy` sobre t); insignia | ambient / snappy | luz 0,3 s; color directo |
| Botón principal cambia de texto/tono | tinte del vidrio y etiqueta | snappy | directo |
| Aparecen/desaparecen grupo secundario, ayuda, teclas, "Terminar sesión" | materializar / desmaterializar | pop_in / pop_out | fundido 0,15 s |
| Progreso del anillo | **sin animación** por tick; salto > 2 % (p. ej. ajustar ritmo) | data | directo |
| Dona en vivo, mosaicos en vivo | **sin animación** en el tick | — | — |
| Dona/barras/mosaicos al cambiar filtro o rango | valores | data | directo |
| Mes del calendario | mes saliente sale y entrante entra (24 %) | select | fundido 0,15 s |
| Abrir menú / pop-up / sugerencias | forma desde el rect del control al final | pop_in | fundido 0,15 s |
| Cerrar menú | inverso | pop_out | fundido 0,12 s |
| Aviso entra / sale / reacomodo | pop_in desde 0,92 y +12 px / pop_out / y con snappy | pop_in/out, snappy | fundidos 0,15 s; reacomodo directo |
| Hoja abre / cierra | velo 0,20 s + hoja pop_in desde 0,94 / inverso | pop_in/out | fundido 0,15 s sin escala |
| Pestaña flotante aparece/desaparece | pop_in / pop_out | | fundido 0,15 s |
| Pestaña: doble clic | morph de tamaño | select | directo |
| Pestaña: arrastre | 1:1 con el puntero (sin resorte) | — | — |
| Scroll con rueda | posición | scroll | directo |
| Indicador de scroll | aparece/desaparece | tween 0,3 s | igual |
| Editar nota (Historial) | texto ↔ campo | snappy (alto de la tarjeta) | directo |

### 5.3 Reglas

- Toda animación arranca del **valor presente** y, si es resorte, **conserva la velocidad** al
  cambiar de objetivo (`Animator.spring(key, …)` con la misma clave = `retarget`).
- **Nada se relanza si el objetivo no cambió** (setters idempotentes en todos los widgets).
- Un widget animado se redibuja **una vez por cuadro** (`Animator.request_frame`), aunque tenga
  varias propiedades en movimiento.
- El ticker (`after` ≈ 16 ms) corre sólo si hay tareas vivas y se apaga solo.
- Las excepciones dentro de un `on_update` se registran (stderr con traceback, una vez por clave)
  en vez de tragarse.
- Evitar oscilaciones sostenidas cerca de 0,2 Hz y cambios bruscos de brillo (la luz de fase va
  lenta a propósito).

---

## 6. Accesibilidad

### 6.1 Contraste (WCAG; medido con la paleta de §2)

- Texto < 18,66 px (o < 24 px regular): **≥ 4,5:1**. Texto grande, íconos y bordes de
  controles: **≥ 3:1**. Objetivo para texto principal: ≥ 7:1.
- Medidos: `label` 15,3 (tarjeta) · `secondary` 7,1 · `text_faint` 5,2 / 4,7 (sobre
  `surface_raised`) · `tertiary` 4,2 (sólo no esencial) · `accent` 9,8 · `mint` 10,4 · `rose` 7,5 ·
  `amber` 10,8 · `danger_text` 6,7 · `on_accent` sobre acentos ≥ 8,7 (ámbar con `#1F1503`: 9,6) ·
  vibrancy sobre vidrio lateral: `label` 14,5, `secondary` 6,5 · sobre botón de vidrio: `label`
  10,6, `secondary` 5,3 · `danger_text` sobre botón de vidrio 4,9 · sobre la luz de concentración
  `secondary` con piso ≥ 4,5.
- **Prohibido**: texto blanco sobre `danger`; `tertiary` en texto esencial; `quaternary` en texto.
- QA lo verifica con `theme.contrast(a, b)` sobre los pares de esta tabla y con el promedio real
  de los recortes en capturas.

### 6.2 Ajustes del sistema (a11y.py)

| Ajuste | Windows | Fuera de Windows |
|---|---|---|
| Reducir movimiento | `SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION=0x1042)` = FALSE | no |
| Reducir transparencia | `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\EnableTransparency` = 0 | no |
| Aumentar contraste | `SPI_GETHIGHCONTRAST (0x0042)` con `HCF_HIGHCONTRASTON` | no |

Se leen al arrancar y al volver el foco a la ventana (como mucho una vez cada 2 s). Cualquier
error → valor seguro "no". El ajuste propio (Automático / Sí / No) manda sobre el sistema.

### 6.3 Efecto de cada modo

- **Reducir movimiento**: resortes sin rebote ni escala; ver columna de §5.2. No cambia la luz de
  fase salvo su duración (0,3 s).
- **Reducir transparencia**: §2.1 y §2.5 (vidrio sólido, manchas a la mitad). En vivo.
- **Aumentar contraste**: paleta AC completa (§2.2), bordes visibles en tarjetas y vidrio, rellenos
  × 1,8 con borde, anillo de foco blanco. Implica **reconstruir la interfaz** (≈ 1 s, con el estado
  intacto).
- **Transparencia del vidrio**: §2.5, en vivo.

### 6.4 Teclado y foco

- Todo control dibujado acepta foco (`takefocus`), muestra anillo de 2 px `focus_ring` a 2 px del
  borde y se activa con Espacio/Enter. Tab recorre en orden visual; en hojas, Tab queda dentro.
- Atajos: F8/F9/F10 (sin cambios), Ctrl+1…4 vistas, Esc cierra menús/hojas/avisos con acción,
  Enter acepta en hojas (salvo destructivas).
- No depender sólo del color: estados con texto (insignia), datos con rótulo o leyenda, toggles con
  posición de perilla.

---

## 7. Rendimiento

### 7.1 Presupuestos (medidos en el contenedor con Xvfb, que es más lento que una PC normal)

| Qué | Presupuesto |
|---|---|
| Tick del reloj con Enfoque visible (engine + UI) | mediana ≤ 8 ms, p95 ≤ 12 ms |
| Tick con otra vista o minimizada | ≤ 2 ms (+ pestaña flotante visible ≤ 4 ms) |
| Ticker de animación en sesión estable | **0 cuadros/s**; se apaga ≤ 1 s después de la última animación |
| Redimensionar (tras el debounce de 120 ms) | ≤ 80 ms a 1280×800 · ≤ 120 ms a 1920×1032; vistas ocultas: 0 ms |
| Primera vez que se muestra una vista sucia | ≤ 120 ms |
| Cambio de vista: clic → primer cuadro | ≤ 60 ms; cada cuadro ≤ 12 ms |
| Paso del fundido de fase | ≤ 45 ms por paso (15 pasos/s) |
| Cuadro de hover/presión de un control | ≤ 4 ms |
| Cuadro de scroll en `ScrollSurface` | ≤ 12 ms |
| Cambio de rango en Análisis | ≤ 60 ms de bloqueo; píldora en movimiento ≤ 16 ms tras el clic |
| `RadialHours` 240 | ≤ 15 ms por render |
| Arranque: splash visible | ≤ 300 ms; ventana visible ≤ 2,5 s |

### 7.2 Qué se cachea (LRU acotado)

| Caché | Clave | Tamaño |
|---|---|---|
| Capas del fondo (base, base_blur, mE, mE_blur) | (w, h, modo) | 2 |
| Forma de vidrio (SDF, máscara, desplazamientos, especular, sombra interior) | (w, h, r, material, escala) | 64 |
| Mapa de sombra + filo | (w, h, r, spec) | 64 |
| Máscara redondeada / esquina de tarjeta | (w, h, r) | 128 |
| Íconos | (nombre, tamaño, color, trazo) | 256 |
| Fuentes PIL | (ruta, px, variación) | sin límite (pocas) |
| Base del anillo (fondo + riel) | (lado, trazo, versión del fondo) | 4 |
| Celdas de dígitos del reloj | (px, color) | 16 |
| Grillas polares, coronas, θ (ya existen) | tamaño | 16 (sin vaciar todo de golpe: LRU) |

`PhotoImage` se **reutiliza** con `paste` si el tamaño no cambió. Re-render del vidrio sólo al
cambiar tamaño, fase, modo de accesibilidad o estado propio (hover/presión).

### 7.3 Cómo se mide

`time.perf_counter()` alrededor de `app._tick` (20 ticks), contador `Animator.frame_count`, el
manifiesto de `shoot.py` (`max_update_ms`, `updates_over_17ms`), y las pruebas de cada rol (PLAN).

---

## 8. Lista de capturas que QA compara contra este documento

Con `shoot.py` a 1280×800 y 1120×720 (y 1600×1000 para comprobar que nada se estira mal):
enfoque en los 7 estados de §4.2 · historial (con sesiones, día vacío, editando) · análisis (arriba,
abajo, hover del mapa, vacío) · ajustes (arriba, abajo) · barra lateral con hover y con la pestaña
activada · hojas (las 5) · avisos (simple, con acción, 3 apilados, con la app minimizada) · menú de
hashtags abierto · sugerencias de hashtag · pestaña flotante expandida, minimizada y su menú ·
splash · las tres variantes de accesibilidad sobre Enfoque concentración (RT, AC, RT+AC) ·
animaciones: cambio de vista, comenzar sesión, segmentado, calendario, aviso, fundido de fase,
redimensionado.
