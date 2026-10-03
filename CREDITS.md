# Créditos y licencias de terceros

El **código** de Focus Flow es MIT (ver [LICENSE](LICENSE)). Lo que sigue son los
recursos que no son código propio.

## Tipografías

### Inter — incluida (SIL Open Font License 1.1)

La interfaz usa **[Inter 4.1](https://github.com/rsms/inter)**, de Rasmus Andersson
y The Inter Project Authors, con licencia **SIL Open Font License 1.1** (OFL). La
OFL permite empaquetarla y redistribuirla junto con el programa, siempre que la
licencia viaje con ella y la tipografía no se venda sola.

En `assets/fonts/` van los siete TrueType estáticos con *hinting* para ClearType
(de `extras/ttf/` del paquete oficial) y la licencia completa:

| archivo | uso |
|---|---|
| `Inter-Regular.ttf` | texto general |
| `Inter-Medium.ttf` | botones, navegación, controles |
| `Inter-SemiBold.ttf` | títulos de tarjeta, valores, énfasis |
| `Inter-Bold.ttf` | énfasis fuerte |
| `InterDisplay-Medium.ttf`, `InterDisplay-SemiBold.ttf`, `InterDisplay-Bold.ttf` | tamaños de 20 px para arriba: títulos, cifras, reloj |
| `LICENSE.txt` | texto de la OFL 1.1 (obligatorio al redistribuir) |

En Windows se registran sólo para el proceso (`AddFontResourceExW` con
`FR_PRIVATE`): no se instalan en el sistema ni quedan después de cerrar.

### SF Pro — opcional, sólo en tu máquina

Si la encuentra, la app usa **SF Pro** de Apple antes que Inter: bajala de
[developer.apple.com/fonts](https://developer.apple.com/fonts/) y copiá los
archivos (`SF-Pro-Text-*.otf`, `SF-Pro-Display-*.otf` o la variable `SF-Pro.ttf`;
también sirven los nombres viejos como `SFUIDisplay-Regular.otf`) a `assets/` o
`assets/fonts/`. Su licencia **no permite redistribuirla**: por eso no está en el
repositorio ni en los instaladores, el `.gitignore` la excluye, y no hay que
dejarla adentro de un ejecutable que se vaya a compartir.

### Si no hay ninguna

`focusflow/theme.py` (`Typography`) resuelve en este orden: SF Pro (si está en
`assets/`) → Inter empaquetada → Segoe UI Variable → Segoe UI. Sin Inter ni SF
la aplicación funciona igual con las de Windows.

## Sonidos

Los seis avisos de `assets/` se generan con `make_sounds.py`:

- **`pausacorta.wav`**, **`vueltapausa.wav`** y **`bienvenida.wav`** están
  **sintetizados** por el script. Son obra propia.
- **`empiezadescanso.wav`**, **`findescanso.wav`** y **`victoria.wav`** salen de
  las grabaciones en `originales/`, a las que el script sólo les ajusta el nivel.
  Provienen de un banco de sonidos libre.

> **Pendiente:** completar acá el nombre del banco, el enlace a cada sonido y la
> licencia exacta. Si son CC0 / dominio público, alcanza con decirlo. Si son
> **CC BY**, la atribución es obligatoria y tiene que figurar el autor y el enlace
> original. Si no se puede confirmar la procedencia, lo más limpio es
> reemplazarlos por versiones sintetizadas: `make_sounds.py` ya sabe generar
> avisos de dos notas y sólo habría que sumar tres entradas más al bloque de
> AJUSTES.

## Dependencias

| paquete | licencia |
|---|---|
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT |
| [Pillow](https://python-pillow.org/) | MIT-CMU |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [keyboard](https://github.com/boppreh/keyboard) | MIT |
| [miniaudio](https://github.com/irmen/pyminiaudio) | MIT |
