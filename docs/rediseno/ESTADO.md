# Estado del rediseño Liquid Glass

Última actualización: 03/10/2026 · rama `claude/fervent-clarke-6k94ku`.
El plan completo está en [PLAN.md](PLAN.md); la especificación en
[DESIGN_SPEC.md](DESIGN_SPEC.md) y las firmas entre módulos en
[CONTRACTS.md](CONTRACTS.md).

## Hecho

**Ola 1 · Fundaciones (6 de 7 roles):**

- **R0:** `widgets.py` partido en el paquete `focusflow/widgets/`.
- **A:** paleta nueva y tipografía, en `theme.py`. Usa SF Pro si está en
  `assets/`; si no, Inter empaquetada en `assets/fonts`. Accesibilidad de Windows en `a11y.py`.
- **B:** `render.py` con fondo ambiental, vidrio, sombras y reloj tabular.
- **C:** `anim.py` con resortes interrumpibles y movimiento reducido.
- **I:** `icons.py`, 36 íconos estilo SF Symbols.
- **H1:** `frameless.py`, la base de las ventanas sin marco.

**Arreglos aplicados sobre las pantallas actuales:**

- Barra lateral estilo macOS 27: marca con anillo, selección en cápsula,
  íconos en acento e interruptor de pestaña flotante.
- Botones en cápsula, con el tono destructivo para "Terminar sesión" y "Borrar".
- Anillo de Enfoque:
  - luz de fase detrás y resplandor;
  - reloj tabular;
  - reloj y leyendas que entran en el hueco, partidas en dos renglones si hace falta.
- Tarjetas con filo de luz; hashtags en lavanda.
- Ajustes entra a 1280x800; la tarjeta Datos muestra la ruta real de la base.
- Bug: crash `compact_text` al arrancar con la pestaña activada y minimizada.

## Falta

1. **Rol D (camino crítico):** `surface.py`, `widgets/_base.py`, `widgets/surfaces.py`.
   Es la arquitectura de ventana que pone el vidrio y el fondo ambiental detrás de las
   pantallas. Se empezó y se frenó; no hay nada entregado.
2. **Ola 2 · Componentes:**
   - E: gráficos;
   - F1: botones y controles de vidrio;
   - F2: Sidebar;
   - G1: avisos y menús;
   - G2: calendario y sonido;
   - H2: pestaña flotante y splash.
3. **Ola 3 · Ensamblado:**
   - S1: `app.py`, con transiciones entre vistas;
   - S2: hojas y diálogos;
   - V1–V4: las cuatro vistas.
4. **Ola 4 · QA:**
   - Q1: visual/HIG;
   - Q2: funcional y rendimiento;
   - Q3: código.

   Después, la ola 5 de correcciones.
5. **Ejecutable de Windows.** Va al final, como pidió el usuario:
   - build endurecido con PyInstaller;
   - CI en Windows;
   - firma de código. Es lo único que evita del todo el aviso de SmartScreen y
     requiere un certificado propio.
6. **Pendientes menores:**
   - tres `bgerror` "after huérfano" al refrescar Historial (ya estaban antes);
   - CPU del tick durante la sesión (ver auditoría: `Chip`, `SmoothButton.set_base_color`,
     dona en vivo).

Las pruebas por rol (unittest) y la herramienta de capturas `shoot.py` vivían en el
scratchpad de la sesión y no están en el repo: cada rol las vuelve a escribir según
PLAN.md §2.
