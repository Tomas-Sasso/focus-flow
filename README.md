# Focus Flow

Un medidor de concentración para Windows. La idea no es contar cuántas horas
estuviste sentado, sino cuánto de ese tiempo fue concentración de verdad.

Es la reescritura completa de **Focus Better**, un programa que había hecho antes
con la misma idea: misma pregunta, otra arquitectura, otro modelo de datos, y
varias funciones que en el original estaban sólo anotadas en un `ideas.txt`.

> **Sólo Windows.** Los sonidos y el vigilante de ventana activa usan APIs de
> Windows. En otro sistema esas dos cosas no hacen nada y el resto funciona igual,
> pero no está probado.

---

## Para usarlo

**Desde el código:**

```bash
pip install -r requirements.txt
```

```bash
python "Focus Flow.py"
```

**Compilado:** en la pestaña [Releases](../../releases) están el instalador y la
versión portable, las dos salidas del mismo `.exe`. No hace falta Python.

La primera vez Windows va a desconfiar, porque el ejecutable no está firmado
digitalmente. Ver [Windows no me deja abrirlo](#windows-no-me-deja-abrirlo).

## Los atajos

| tecla | qué hace |
|---|---|
| **F8** | cortar por distracción (el bloque se reinicia al volver) |
| **F9** | volver a concentrarse |
| **F10** | pausa corta (algo puntual, sin perder el bloque) |

Funcionan aunque la ventana esté atrás.

---

## Qué hace, y por qué así

### En pantalla, dos categorías

Sólo hay dos cosas que mirar: **Concentración** y **No concentración**. Los
gráficos tienen dos colores y la leyenda dos renglones, así que se leen de un
vistazo sin tener que descifrar una paleta.

Por debajo, la base guarda tres tipos de tramo —`focus`, `rest` y `away`— con
marca de tiempo. Eso permite que el pomodoro sepa cuándo estabas descansando de
verdad, y deja la puerta abierta a mostrar más detalle sin volver a medir nada.

El motivo de cada "no concentración" aparece igual, pero donde corresponde: en la
línea debajo del reloj (*"Descanso del pomodoro"*, *"Pausa corta: el bloque está
congelado"*), no como una etiqueta más en cada gráfico.

### La pausa corta

Esta función estaba anotada así en mis notas:

> *agregar que al pausar la sesión te de un tiempo de guarda, por si alguien te
> habla o algo y tenés que contestar pero no estás pelotudeando ni descansando
> pero no querés que se te reinicie el pomodoro*

El botón **Pausa corta** (F10) congela el bloque de pomodoro donde está: cuando
volvés, seguís con los minutos que te quedaban en vez de arrancar de nuevo. Tiene
un margen configurable (5 minutos por defecto); si te pasás, el bloque se
reinicia como en una pausa normal.

Tiene aviso propio en las dos puntas: dos notas que **bajan** al entrar y las
mismas **al revés** al volver, así se reconoce sin mirar la pantalla.

### Línea de tiempo de cada sesión

Otra de las ideas anotadas:

> *que muestre en una barra un resumen de cuándo hubo pausas y cuando hubo
> estudio (…) para poder visualizar en que momentos de la sesión me distraje*

Cada sesión guarda sus tramos con marca de tiempo. La barra de colores está en la
pantalla de enfoque mientras trabajás, en el diálogo de guardado y en cada
tarjeta del historial.

### Vigilante de distracciones

Y la tercera:

> *que registre si abro Instagram, tw o algo y me pregunte si quiero pausar el
> temporizador concentración*

En **Ajustes** se activa. Mira el título de la ventana que tenés adelante; si
alguna de las palabras de la lista aparece durante más de unos segundos, te
aparece un aviso preguntando si querés cortar. Nunca pausa por su cuenta, y no
manda nada a ningún lado: es una lectura local del título de la ventana activa.

### Análisis

- **Mapa del año** al estilo de los mapas de contribuciones. Se hace clic en un
  día y se abre ese día en el historial.
- **Reloj de concentración**: 24 franjas en círculo con tus horas productivas. Se
  arma con los tramos reales, no repartiendo el total de la sesión en partes
  iguales, así que una sesión de 20:00 a 23:00 no ensucia las tres horas por
  igual.
- Por día de la semana, rachas (actual y mejor), récords personales y ranking de
  hashtags.
- Exportación a CSV.

### Pestaña flotante

Para cuando estudiás desde un PDF a pantalla completa y no podés tener la ventana
abierta. Se activa con el botón de abajo a la izquierda y aparece al minimizar la
app: un recuadro chico, siempre encima, con el anillo de progreso, el tiempo que
falta y el modo en su color.

- Se **arrastra** a donde quieras y se acuerda de dónde la dejaste.
- **Click derecho** abre un menú con la estética de la app: *Minimizar* y
  *Cerrar pestaña*.
- **Minimizada** queda del tamaño de una pastilla y muestra sólo los minutos que
  faltan; abajo del minuto pasa a segundos. Ahí el menú ofrece *Maximizar*.

Las esquinas están recortadas de verdad: fuera de la silueta redondeada se pinta
un color que Windows vuelve transparente, así no asoma el rectángulo de la
ventana por detrás. Los avisos usan lo mismo.

### Sonidos

Los seis están normalizados y guardados como WAV. Los originales venían muy
dispares: `victoria` sonaba casi nueve veces más bajo que `empiezadescanso`.

El nivel se mide como RMS de la parte con señal, sumando la energía de los
canales igual que la norma de loudness. Eso importa: `victoria` tiene los canales
en contrafase, así que medirlo mezclando a mono lo subestimaba.

Se regeneran con **`make_sounds.py`**. Lee las grabaciones de `originales/` (que
no se tocan) y escribe en `assets/`, que es exactamente de donde la app carga los
sonidos.

```bash
python make_sounds.py
```

Si después querés que el `.exe` use los nuevos, hay que recompilarlo: el
ejecutable lleva su propia copia de los sonidos adentro.

Todo lo que conviene ajustar está en el bloque **AJUSTES** al principio del
archivo:

| variable | qué controla |
|---|---|
| `VOLUMEN` | el volumen de cada sonido por separado |
| `NOTA_MS` | cuánto dura cada nota de los avisos sintetizados |
| `SILENCIO_MS` | el silencio entre una nota y la siguiente (0 = van pegadas) |
| `ENTRADA_MS` | silencio al principio del archivo |
| `NIVEL` / `TECHO` | nivel de referencia y pico máximo |

El nivel se ajusta **escalando, nunca comprimiendo**. Hubo una versión que
comprimía para ganar volumen y fue un error: aplastaba la envolvente, y con los
ataques planchados las dos notas de un aviso se escuchaban como un solo bloque.
Si el volumen pedido no entra bajo el techo, se sube hasta donde se puede y el
script lo avisa. El factor de cresta (pico dividido nivel) está verificado por
las pruebas justamente para que eso no vuelva a pasar.

Los avisos de la pausa corta son **dos notas separadas por silencio real**. El
intervalo importa: a una quinta justa el tercer armónico de una nota cae en
1762 Hz y el segundo de la otra en 1760 —prácticamente el mismo parcial— y el
oído las funde en un solo timbre. Van a una séptima menor, que no comparte
ninguno de los parciales que se sintetizan.

### Volumen

Abajo a la izquierda, debajo del interruptor de la pestaña. La barra ajusta el
volumen y el parlante silencia; al des-silenciar vuelve el nivel que tenías, no
un valor cualquiera. Queda guardado entre sesiones.

El volumen se aplica **al mezclar**, multiplicando las muestras justo antes de
mandarlas al dispositivo. El nivel es exacto, no depende del mezclador de Windows
y se puede mover con un aviso ya sonando.

### El dispositivo de audio queda abierto

Focus Flow abre la salida de audio al arrancar y la deja abierta hasta que
cerrás: cuando no hay nada que sonar, escribe silencio.

Suena a desperdicio y no lo es. Las dos versiones anteriores fueron por el otro
lado —abrir el dispositivo en cada aviso— y las dos fallaron:

* Con **MCI**, `setaudio ... volume` devuelve error 261 sobre `waveaudio`: la
  barra de volumen no hacía absolutamente nada.
* Con **`winsound.PlaySound`** el volumen sí funcionaba, pero apareció el
  problema de fondo. Windows apaga el endpoint de audio a los pocos segundos de
  silencio, y los avisos de Focus Flow van separados por minutos, así que todos
  lo encontraban dormido. Medido acá: **1,05 s** desde la llamada hasta que sale
  por los parlantes con el endpoint dormido, contra **0,10 s** con el dispositivo
  despierto. Y mientras termina de encender no sale nada, así que además se comía
  el principio: los dos tonos de la pausa corta se escuchaban como uno solo.

Teniendo el dispositivo abierto el endpoint nunca se duerme. El aviso sale entero
y con la latencia del buffer (15 ms) y nada más. Cuesta una devolución de llamada
cada 15 ms que casi siempre escribe ceros.

Si `miniaudio` no está o el dispositivo no abre, se cae al camino con `winsound`:
llega tarde, pero suena.

### Pantalla de arranque

Al abrir aparece un recuadro con el logo y el nombre durante alrededor de un
segundo. No es decoración: mientras se muestra, la ventana ya está maximizada y
en su tamaño definitivo pero invisible, y ahí se calculan y dibujan las cuatro
pantallas.

Dos cosas dependen de eso. La primera vez que se entraba a Análisis se veía cómo
se armaba, porque los lienzos nacían con tamaño 1 y se redibujaban al recibir su
medida real. Y si la ventana se maximizaba recién al aparecer, todo se reacomodaba
a la vista: por eso el arranque espera a que el tamaño se sostenga —customtkinter
reaplica `geometry()` al ajustar su escalado— antes de dibujar nada.

### Otras cosas

- **Objetivo diario** con progreso y racha.
- **Presets de ritmo**: pomodoro clásico, bloque largo, ultradiano, arranque
  suave, sin bloques.
- **Hashtags** en tablas propias, con autocompletado navegable por teclado.

### Los controles

Hay **un solo botón grande a la vez**, y cambia según el estado:

| estado | botón grande |
|---|---|
| sin sesión | Comenzar sesión |
| concentrado | Pausar |
| en pausa, descanso o tolerancia | Volver a concentrarme |
| en pausa corta | Ya volví |

**Terminar sesión** está en rojo, arriba a la derecha: es la única acción
irreversible, así que es la única en ese color.

Los secundarios (Pausa corta, Ir a descanso, Ajustar ritmo) aparecen chicos y
sólo cuando sirven: la pausa corta se esconde si ya estás en una, y el cambio de
fase sólo está si hay bloques. Sin sesión no hay más que un botón en toda la
pantalla.

**Ajustar ritmo** cambia los tiempos con la sesión andando, sin perder lo medido.

---

## Cómo está armado

```
Focus Flow.py            lanzador
make_sounds.py           genera y nivela los sonidos de assets/
originales/              las grabaciones sin procesar, fuente de make_sounds.py
installer.iss            script del instalador (Inno Setup)
empaque/                 lo que acompaña al .zip portable
assets/                  los sonidos (las tipografías no se distribuyen, ver más abajo)
focusflow/
  engine.py              máquina de estados de la sesión — sin Tk, se testea sola
  db.py                  esquema SQLite, consultas e importador del programa viejo
  stats.py               análisis (rachas, mapas, perfiles horarios, CSV)
  render.py              dibujo antialiaseado con numpy
  anim.py                motor de animación y curvas de aceleración
  widgets.py             widgets propios
  theme.py               paleta, tipografía, espaciado
  config.py              preferencias persistentes y presets
  system.py              sonido y vigilante de ventana activa
  app.py                 ventana principal
  views/                 una pantalla por archivo
```

### Por qué el motor está separado

En el original el tiempo se llevaba con relojes en paralelo (`c2`, `rest_time`,
banderas de "está corriendo") que había que sumar y restar a mano en cada
transición. Cualquier camino que se olvidara descuadraba los totales.

Acá lo único que se guarda son los tramos, y los totales se derivan de ellos. Por
construcción siempre suman el tiempo real transcurrido. Además, como `engine.py`
no importa nada de Tk, la lógica se prueba sin abrir una ventana: hay 50
verificaciones sobre transiciones, vencimientos y contabilidad.

Un detalle que salió de esas pruebas: cuando un contador vence en medio de un
intervalo, la transición se hace en el instante exacto del vencimiento y no
cuando llega el tick. Si no, una pausa corta con 2 minutos de margen podía
terminar contando 2:20 de "ausente" sólo porque el tick cayó veinte segundos
tarde.

### El modelo de datos

`focusflow.db` (SQLite) con tablas relacionadas de verdad:

```
sessions      una fila por sesión, con los totales de las tres categorías
segments      los tramos, con inicio y fin relativos al arranque de la sesión
tags          cada hashtag una vez, con cuántas veces se usó
session_tags  la relación entre ambos
```

En el original los hashtags se guardaban como texto dentro de una columna y se
buscaban con `LIKE '% #tag %'`. Acá una pregunta como "cuántas horas concentrado
bajo #teleco los martes" es una consulta, no leer todas las filas y parsear
strings.

### El importador

Lee la base del programa anterior y trae todo. Es idempotente: se saltea las
sesiones que ya estén (mismo inicio y mismo nombre), así que se puede correr las
veces que haga falta sin duplicar nada. Las sesiones viejas no tienen tramos
guardados, así que se les arma una línea de tiempo proporcional.

Nunca escribe en la base vieja.

### Dónde guarda tus datos

La carpeta se decide al arrancar, con tres reglas en orden:

1. Hay un `portable.txt` al lado del programa → los datos van ahí mismo. Es lo
   que lleva el `.zip`.
2. Ya hay un `focusflow.db` al lado del programa → se sigue usando ése. Así el
   que viene de una versión anterior no ve desaparecer su historial.
3. Si no → `%LOCALAPPDATA%\Focus Flow`.

La tercera es la importante para quien lo recibe. Guardar siempre al lado del
ejecutable tiene dos agujeros: el historial se queda atrás si movés el programa
de carpeta, y en una instalación quedaría adentro de la carpeta de instalación,
que es justo lo que se borra al desinstalar o al actualizar.

La regla 2 además mantiene juntas la copia compilada y la que corre desde el
código. El Python de la Microsoft Store redirige lo que se escribe en
`%LOCALAPPDATA%` a un sandbox propio, así que si las dos cayeran en la regla 3
estarían escribiendo en carpetas distintas sin decirlo.

Desinstalar borra el programa y nada más: el historial queda donde está.

---

## Compilar el ejecutable

```bash
pip install pyinstaller
```

```bash
python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Focus Flow" --icon focusflow.ico --add-data "assets;assets" --collect-data customtkinter --hidden-import PIL._tkinter_finder --hidden-import _miniaudio --hidden-import _cffi_backend "Focus Flow.py"
```

**Por qué `--onedir` y no `--onefile`.** Un `--onefile` se autodescomprime en una
carpeta temporal al arrancar, que es exactamente el patrón que usan los
empaquetadores de malware: varios antivirus lo marcan como falso positivo y lo
mandan a cuarentena sin mirar más. Con `--onedir` eso casi no pasa, y además
arranca bastante más rápido. A cambio queda una carpeta en vez de un archivo
suelto, que para distribuir da igual porque va adentro del `.zip` o del
instalador.

Tres de esos argumentos no son opcionales y cuestan encontrarlos:

- `--collect-data customtkinter` — customtkinter lee sus temas de archivos JSON
  que PyInstaller no arrastra solo.
- `--hidden-import PIL._tkinter_finder` — lo necesita `ImageTk`.
- `--hidden-import _miniaudio` y `_cffi_backend` — `miniaudio` es una extensión
  de cffi. PyInstaller encuentra el `.pyd` pero no ve que por dentro necesita
  `_cffi_backend`, que es un módulo de Python y no una DLL. Sin eso el `.exe`
  se queda mudo y cae al respaldo con `winsound`, que es justo lo que se quería
  evitar.

**El instalador** se arma con [Inno Setup](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`) a partir de `installer.iss`:

```bash
ISCC.exe /DOneDir /DDistDir=dist /DAppVersion=1.1.0 /DOutputDir=entregas installer.iss
```

Son dos rutas distintas y conviene no confundirlas: `SourceDir` es la raíz del
proyecto, de donde sale el ícono, y `DistDir` es donde PyInstaller dejó la
carpeta `Focus Flow\` con el `.exe` y su `_internal`. Con `--onedir` eso es
`dist`. Si no se pasa `DistDir`, toma el valor de `SourceDir`, que es lo que
servía cuando el build era `--onefile` y todo caía en el mismo lugar.

Sin `/DOneDir` empaqueta el `.exe` suelto de un build `--onefile`. La
instalación es por usuario a propósito: no pide contraseña de administrador, que
es la diferencia entre "doble clic y listo" y "pedile permiso a quien te prestó
la computadora".

## Requisitos

```
customtkinter    interfaz
pillow           imágenes
numpy            dibujo antialiaseado
keyboard         atajos globales (opcional)
miniaudio        audio de baja latencia (opcional)
```

`keyboard` es opcional: da los atajos globales aunque la ventana no tenga el
foco, y en algunos equipos pide permisos de administrador. Sin él los atajos
siguen funcionando mientras la ventana esté adelante. `miniaudio` también es
opcional: es lo que mantiene el dispositivo de audio abierto, y sin él los avisos
suenan igual pero con el retraso del arranque en frío.

---

## Tus datos

Todo queda en `focusflow.db`, un archivo SQLite, y las preferencias en
`settings.json`. **Nada sale de tu computadora**: no hay cuentas, ni servidores,
ni telemetría. El vigilante de distracciones lee el título de la ventana activa
localmente y no lo guarda ni lo manda a ningún lado.

Para llevarte todo a otra máquina, copiá esos dos archivos a la carpeta que
corresponda.

Ninguno de los dos está en este repositorio: se crean solos la primera vez que
abrís el programa.

## Windows no me deja abrirlo

Son dos problemas distintos que se ven parecido.

### Pantalla azul: "Windows protegió tu PC"

El archivo sigue estando; Windows sólo no lo deja arrancar de una. Pasa con
cualquier ejecutable sin firma digital y no dice nada sobre el programa.

Lo más limpio no es "ejecutar de todas formas", sino **quitarle la marca de
origen**: Windows le pega un atributo invisible (*Mark of the Web*) a todo lo que
se descarga, y es eso lo que dispara el aviso.

**Clic derecho → Propiedades → tildar "Desbloquear" abajo de todo → Aplicar.**
O por consola:

```bash
Unblock-File "Focus Flow.exe"
```

Si bajaste el `.zip`, desbloqueá **el zip antes de descomprimir**: la marca se
propaga a cada archivo que sale adentro.

Si preferís el otro camino: **Más información → Ejecutar de todas formas**. El
enlace "Más información" es texto gris chico arriba del botón, cuesta verlo.

### El archivo desaparece solo

Eso no es SmartScreen, es el antivirus poniéndolo en cuarentena, y casi siempre
es un falso positivo de PyInstaller. Por eso las compilaciones de este repo van
con `--onedir`.

Para recuperarlo: **Seguridad de Windows → Protección antivirus y contra
amenazas → Historial de protección → Permitir en el dispositivo.**

### La solución de fondo

Firmar el ejecutable. Un certificado OV cuesta 200–400 USD al año y sólo reduce
el aviso hasta que el archivo acumule reputación; uno EV cuesta más y la da desde
el día uno. Azure Trusted Signing es bastante más barato pero tiene requisitos de
elegibilidad. La opción más razonable para un proyecto personal es publicarlo en
la Microsoft Store: la cuenta de desarrollador individual es un pago único y
Microsoft firma por vos.

## Créditos y licencias

Ver [CREDITS.md](CREDITS.md) para las tipografías y los sonidos.

El código es MIT — ver [LICENSE](LICENSE).
