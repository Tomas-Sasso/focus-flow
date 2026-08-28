# Créditos y licencias de terceros

El **código** de Focus Flow es MIT (ver [LICENSE](LICENSE)). Lo que sigue son los
recursos que no son código propio.

## Tipografías — NO se distribuyen en este repositorio

La aplicación fue diseñada con las tipografías **SF Pro Text** y **SF UI Display**
de Apple. Esas fuentes **no están incluidas acá**, y no pueden estarlo: la licencia
de Apple permite usarlas para diseñar interfaces, pero no redistribuirlas.

**No hace falta hacer nada.** El código ya lo contempla:

- `focusflow/theme.py` registra cada `.otf` sólo `if os.path.exists(path)`, y
  después resuelve la familia con una cadena de alternativas que termina en
  **Segoe UI**.
- `focusflow/render.py` (`load_font`) intenta los `.otf`, después `segoeui.ttf`,
  después `arial.ttf`, y por último la tipografía por defecto de Pillow.

Es decir: sin las fuentes de Apple la aplicación funciona igual, con Segoe UI.

Si querés el aspecto original y ya tenés licencia para usarlas, poné los archivos
`SF-Pro-Text-Regular.otf`, `SF-Pro-Text-Medium.otf`, `SF-Pro-Text-Semibold.otf` y
`SFUIDisplay-Regular.otf` en `assets/`. El `.gitignore` los excluye para que no
terminen subidos por accidente.

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
