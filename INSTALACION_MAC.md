# Instalación en macOS, desde cero

Guía para un Mac recién estrenado, sin nada instalado. No supone conocimientos
de programación: cada paso dice qué hacer, qué deberías ver y cómo comprobar que
quedó bien antes de seguir.

Cuenta con una hora la primera vez. Las descargas pesan unos 400 MB en total.
Sirve igual para Mac con chip Apple (M1 en adelante) y para los Intel más
viejos; donde cambia algo, la guía lo dice.

**Si algo falla**, salta a la sección 11: están los errores más frecuentes con
su causa y su arreglo.

---

## Contenido

1. [Qué vas a instalar y para qué](#1-qué-vas-a-instalar-y-para-qué)
2. [Elegir dónde va a vivir el proyecto](#2-elegir-dónde-va-a-vivir-el-proyecto)
3. [La Terminal y las herramientas de desarrollo](#3-la-terminal-y-las-herramientas-de-desarrollo)
4. [Python](#4-python)
5. [Visual Studio Code](#5-visual-studio-code)
6. [Firefox](#6-firefox)
7. [Bajar el scraper](#7-bajar-el-scraper)
8. [Crear el entorno virtual](#8-crear-el-entorno-virtual)
9. [Preparar la sesión de X](#9-preparar-la-sesión-de-x)
10. [Primera descarga de prueba](#10-primera-descarga-de-prueba)
11. [Errores frecuentes](#11-errores-frecuentes)

---

## 1. Qué vas a instalar y para qué

| Programa | Para qué sirve aquí | Tamaño |
|---|---|---|
| **Herramientas de desarrollo de Apple** | Traen `git`, para bajar el proyecto | ~1 GB |
| **Python** | El lenguaje en que está escrito el scraper | ~60 MB |
| **Visual Studio Code** | Editar archivos y correr el cuaderno de ejemplo | ~120 MB |
| **Firefox** | El navegador que el scraper controla | ~140 MB |

La **Terminal** ya viene con macOS: no hay que instalarla. Es la ventaja
respecto a Windows, donde hay que montar Git Bash para tener una terminal
parecida.

### Enlaces de descarga

Todos son los sitios oficiales. No bajes ninguno de otro lado.

| Programa | Enlace |
|---|---|
| Python para macOS | <https://www.python.org/downloads/macos/> |
| Visual Studio Code | <https://code.visualstudio.com/Download> |
| Firefox | <https://www.mozilla.org/firefox/new/> |
| geckodriver (sólo si hace falta, §8) | <https://github.com/mozilla/geckodriver/releases> |
| Homebrew (alternativa, opcional) | <https://brew.sh> |

Y los del proyecto, por si los necesitas:

| Qué | Enlace |
|---|---|
| Documentación de Selenium | <https://www.selenium.dev/documentation/> |
| Buscador avanzado de X | <https://x.com/search-advanced> |

---

## 2. Elegir dónde va a vivir el proyecto

**Hazlo antes de instalar nada.** Es el error más costoso de esta guía y no da
ningún mensaje de error.

Si tienes activado **"Carpetas Escritorio y Documentos"** en iCloud, todo lo que
pongas en `Documentos` se sincroniza. Una descarga de este scraper puede durar
días y reescribir un archivo de cientos de megabytes muchas veces: iCloud
intenta subirlo con cada escritura, crea copias en conflicto con un ` 2` al final
del nombre y puede subir un archivo a medio escribir.

> Esto no es hipotético: al armar el corpus de 212.962 publicaciones que viene
> como ejemplo, iCloud generó una copia en conflicto a mitad de la descarga.

Compruébalo en **Ajustes del Sistema** → tu nombre arriba → **iCloud** →
**iCloud Drive** → **Opciones**. Si **Carpetas Escritorio y Documentos** está
marcado, está sincronizando.

**Usa una carpeta fuera de iCloud**, directamente en tu carpeta personal:

```bash
mkdir -p ~/investigacion
```

Sin tildes ni espacios en el nombre: ahorra problemas al escribir rutas.

---

## 3. La Terminal y las herramientas de desarrollo

La **Terminal** es donde vas a escribir los comandos. Ábrela con `Cmd+Espacio`,
escribe `terminal` y Enter. Aparece una ventana con una línea que termina en
`%`. Ahí se escribe.

macOS no trae `git` instalado, pero sabe cómo conseguirlo. Escribe:

```bash
git --version
```

La primera vez sale una ventana que ofrece instalar las **herramientas de línea
de comandos para desarrolladores** (*Command Line Tools*). Acepta e instala:
tarda entre 5 y 20 minutos según tu conexión. Cuando termine, vuelve a escribir
el comando: debe responder algo como `git version 2.39.5`.

> **No necesitas Xcode completo**, que pesa más de 10 GB. Sólo estas
> herramientas de línea de comandos, que son mucho más livianas y es lo que
> ofrece esa ventana.

---

## 4. Python

macOS trae una versión de Python, pero es la que usa el sistema y conviene no
tocarla. Instala la tuya:

1. Entra a <https://www.python.org/downloads/macos/> y baja el
   **"macOS 64-bit universal2 installer"** de la última versión 3.x estable.
   Este proyecto necesita **3.11 o superior**. El instalador "universal2" sirve
   tanto para chip Apple como para Intel.

2. Abre el `.pkg` descargado y sigue el instalador: **Continuar**, aceptar la
   licencia, **Instalar**. Te pedirá tu contraseña de administrador.

3. **Al terminar se abre una ventana del Finder.** Haz doble clic en
   **`Install Certificates.command`** y espera a que diga `Process completed`.

   > **Este paso se salta fácil y luego confunde.** Sin él, Python no conoce los
   > certificados de seguridad y cualquier descarga por internet —incluida la de
   > `geckodriver`— falla con un error de `SSL: CERTIFICATE_VERIFY_FAILED` que no
   > menciona por ningún lado que el problema sea éste.

**Comprobación.** En la Terminal:

```bash
python3 --version
```

Debe responder la versión que acabas de instalar.

> **Alternativa con Homebrew.** Si ya usas [Homebrew](https://brew.sh) o
> prefieres instalarlo todo desde la terminal, `brew install python` sirve igual
> y no necesita el paso de los certificados. Si no sabes qué es Homebrew, usa el
> instalador de arriba: es más simple para una sola máquina.

---

## 5. Visual Studio Code

1. Entra a <https://code.visualstudio.com/Download> y baja la versión para Mac.
   Elige **Apple silicon** si tu Mac es M1 o posterior, o **Intel chip** si es
   más viejo. Para saber cuál tienes: menú  → **Acerca de este Mac**.

2. Se baja un `.zip`. Haz doble clic y arrastra **Visual Studio Code** a la
   carpeta **Aplicaciones**. Ábrelo desde ahí.

3. Instala dos extensiones: haz clic en el icono de cuadritos de la barra
   izquierda (**Extensions**, o `Cmd+Shift+X`), busca e instala:

   - **Python** (de Microsoft)
   - **Jupyter** (de Microsoft)

4. Habilita el comando `code` para abrir carpetas desde la Terminal:
   `Cmd+Shift+P`, escribe `Shell Command: Install 'code' command in PATH` y
   Enter.

---

## 6. Firefox

Entra a <https://www.mozilla.org/firefox/new/>, baja el `.dmg` y arrastra
Firefox a **Aplicaciones**. Si ya lo tienes, sirve igual.

**No uses Safari ni Chrome:** el scraper está escrito para Firefox.

---

## 7. Bajar el scraper

En la Terminal:

```bash
cd ~/investigacion
```

```bash
git clone https://github.com/manuelcastiblan/scraper-x.git scraper-x
```

Si en cambio
recibiste un archivo `scraper-x.zip`, haz doble clic para descomprimirlo y mueve
la carpeta resultante a `~/investigacion`.

```bash
cd scraper-x
ls
```

`ls` lista la carpeta. Debes ver `README.md`, `scraper_x.py`,
`descargar_cuentas.py`, `ejemplo.ipynb` y varios más.

---

## 8. Crear el entorno virtual

Un *entorno virtual* es una carpeta donde se instalan las librerías de este
proyecto y de ningún otro. Así no choca con otras cosas que instales después.

```bash
python3 -m venv .venv
```

Tarda unos segundos y no imprime nada. Ahora actívalo:

```bash
source .venv/bin/activate
```

El texto del indicador cambia y empieza por `(.venv)`. Eso significa que está
activo. **Hay que activarlo en cada ventana nueva de Terminal**; no queda puesto
para siempre.

Instala las librerías:

```bash
pip install -r requirements.txt
```

Y las del análisis y el cuaderno:

```bash
pip install pandas matplotlib jupyter ipykernel
```

**Comprobación.**

```bash
python -c "import selenium, pandas; print('todo bien')"
```

Debe imprimir `todo bien`.

### geckodriver: normalmente no tienes que hacer nada

`geckodriver` es el programa que le permite a Python manejar Firefox. **Selenium
lo descarga solo** la primera vez que corras el scraper, así que lo habitual es
no tocarlo.

Hazle caso a esta sección sólo si al correr el scraper aparece un error que
mencione `geckodriver` o `Selenium Manager`, lo que pasa en redes
institucionales que bloquean la descarga. Con Homebrew es una línea:

```bash
brew install geckodriver
```

A mano, desde <https://github.com/mozilla/geckodriver/releases>: en la versión
más reciente, abre **Assets** y baja el archivo que corresponda a tu Mac.

```bash
uname -m
```

- Responde `arm64` → baja el que termina en **`macos-aarch64.tar.gz`**
- Responde `x86_64` → baja el que termina en **`macos.tar.gz`**

Descomprímelo y copia el archivo `geckodriver` a la carpeta `scraper-x`, junto a
`scraper_x.py`. El scraper lo busca ahí antes de intentar descargarlo. Después
quítale la marca de cuarentena que macOS le pone a todo lo bajado de internet, o
el sistema se negará a abrirlo:

```bash
xattr -dr com.apple.quarantine geckodriver
chmod +x geckodriver
```

**Comprobación.**

```bash
./geckodriver --version
```

Debe imprimir la versión. Si en cambio sale una ventana diciendo que *no se
puede abrir porque Apple no puede comprobar si contiene software malicioso*, es
que faltó el `xattr` de arriba.

Si prefieres dejarlo en otra carpeta, dile dónde está con la variable
`GECKODRIVER`:

```bash
export GECKODRIVER="$HOME/herramientas/geckodriver"
```

---

## 9. Preparar la sesión de X

El scraper **no inicia sesión ni maneja contraseñas**. Reutiliza las cookies de
un perfil de Firefox donde tú ya entraste a X a mano. Conviene usar un perfil
aparte, para poder seguir navegando mientras la descarga corre.

1. Cierra Firefox. En la Terminal, abre el administrador de perfiles:

   ```bash
   /Applications/Firefox.app/Contents/MacOS/firefox -P
   ```

2. **Create Profile…** → llámalo `scraper` → **Finish** → **Start Firefox**.

3. En esa ventana, entra a <https://x.com> e inicia sesión normalmente. Resuelve
   el código de verificación si lo pide. Comprueba que ves tu inicio.

4. Entra a `about:profiles` en la barra de direcciones. Busca el bloque del
   perfil `scraper` y copia la ruta que dice **Directorio raíz**. Se parece a:

   ```
   /Users/TU_USUARIO/Library/Application Support/Firefox/Profiles/a1b2c3d4.scraper
   ```

5. **Cierra Firefox por completo** (`Cmd+Q`, no sólo la ventana). Mientras está
   abierto, bloquea el perfil y el scraper no puede usarlo.

6. Declara esa ruta. En el cuaderno, primera celda:

   ```python
   PERFIL_FIREFOX = "/Users/TU_USUARIO/Library/Application Support/Firefox/Profiles/a1b2c3d4.scraper"
   ```

   Y si vas a correr los scripts desde la Terminal:

   ```bash
   export X_FIREFOX_PROFILE="$HOME/Library/Application Support/Firefox/Profiles/a1b2c3d4.scraper"
   ```

   Esa variable se borra al cerrar la ventana. Para no repetirla cada vez,
   agrégala al final del archivo `~/.zshrc`, que la Terminal lee al abrirse.

> **Por qué declararlo y no dejar que lo adivine.** Si no dices cuál es, el
> scraper toma el perfil marcado como predeterminado, que normalmente es el de
> uso diario y puede no tener sesión en X. El fallo es silencioso: X manda el
> navegador al formulario de acceso y la descarga termina **vacía, sin ningún
> mensaje de error**.
>
> Ojo con los espacios: la ruta contiene `Application Support`, con un espacio en
> medio. En la Terminal va **siempre entre comillas**.

**Conectar Visual Studio Code.** Abre la carpeta con `code .` desde la Terminal,
o con **File** → **Open Folder…**. Luego `Cmd+Shift+P` → `Python: Select
Interpreter` → elige el que diga **`.venv`**. Ese paso es el que hace que el
cuaderno use las librerías que instalaste.

**Comprobación.** Abre `ejemplo.ipynb` y ejecuta las tres primeras celdas de
código. La tercera abre Firefox sin ventana y debe imprimir
`estado de la página: results` y `Sesión lista.` Si dice `login`, la sesión no
quedó: repite desde el paso 3 y asegúrate de cerrar Firefox antes de probar.

---

## 10. Primera descarga de prueba

Sigue el cuaderno `ejemplo.ipynb` de principio a fin: baja dos días de un
hashtag y un mes de una cuenta, revisa la calidad del resultado y hace un primer
análisis. Son unos pocos minutos.

Cuando pases a tu propio estudio, lee el `README.md`: explica el censo de
cuentas, qué esperar de los bloqueos de X y las comprobaciones que hay que hacer
antes de analizar.

### Dejarlo corriendo varios días

Las descargas largas se lanzan **fuera** del cuaderno:

```bash
nohup caffeinate -i python -u descargar_cuentas.py --roster censo.json \
    --profile "$X_FIREFOX_PROFILE" \
    --window-months 3 --retries 12 --retry-backoff 600 >> salida.log 2>&1 &
```

`caffeinate -i` impide que el Mac se duerma por inactividad mientras el proceso
corre. Sigue el avance con:

```bash
tail -f salida.log
```

`Ctrl+C` corta el `tail`, no la descarga.

> **`caffeinate` no impide que se duerma al cerrar la tapa.** En un portátil,
> cerrar la pantalla suspende el Mac aunque `caffeinate` esté corriendo, y la
> descarga se detiene. Déjalo **enchufado y con la tapa abierta**. Pasó durante
> la descarga del corpus de ejemplo y costó varias horas.

El scraper es reanudable: si se corta, lo vuelves a lanzar con el mismo comando
y continúa donde quedó.

---

## 11. Errores frecuentes

| Lo que ves | Qué pasa | Arreglo |
|---|---|---|
| `command not found: python` | En macOS el comando es `python3`, salvo dentro del entorno virtual | Usa `python3`, o activa el entorno: `source .venv/bin/activate` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Faltó correr `Install Certificates.command` al instalar Python | Ábrelo en `/Applications/Python 3.x/` (sección 4) |
| `error: externally-managed-environment` al usar `pip` | Estás instalando fuera del entorno virtual, y macOS protege el Python del sistema | `source .venv/bin/activate` y repite; el indicador debe empezar por `(.venv)` |
| `source .venv/Scripts/activate: No such file` | Esa ruta es de Windows | En macOS es `source .venv/bin/activate` |
| *No se puede abrir porque Apple no puede comprobar…* | Cuarentena de Gatekeeper sobre `geckodriver` | `xattr -dr com.apple.quarantine geckodriver` |
| El cuaderno dice que falta `pandas`, pero lo instalaste | Visual Studio Code está usando otro Python | `Cmd+Shift+P` → `Python: Select Interpreter` → el que diga `.venv` |
| `FileNotFoundError: No existe el perfil de Firefox` | La ruta está mal escrita, o le faltan las comillas por el espacio de `Application Support` | Cópiala de `about:profiles` y enciérrala entre comillas |
| `estado de la página: login` | Ese perfil no tiene sesión en X, o es otro perfil | Repite la sección 9; confirma que la ruta sea la del perfil donde iniciaste sesión |
| La descarga termina al instante y el CSV sale vacío | Casi siempre es lo mismo: perfil sin sesión | Igual que la fila anterior. Es el fallo silencioso de la sección 9 |
| Firefox se queda colgado al arrancar el scraper | Firefox está abierto con ese perfil | Ciérralo con `Cmd+Q`; que no quede el punto debajo del icono en el Dock |
| La descarga se detuvo sola de madrugada | El Mac se durmió, casi siempre por la tapa cerrada | Enchufado y con la tapa abierta; relanza y continúa donde quedó |
| Aparecen copias del CSV terminadas en ` 2` | El proyecto está dentro de iCloud | Mueve la carpeta fuera de `Documentos` (sección 2) |
| `Algo salió mal` o la descarga se detiene a los pocos lotes | X te limitó por hacer muchas búsquedas | Normal: el scraper espera y reintenta. Ver `README.md` §7 |

---

## Nota sobre esta guía

Las versiones de macOS, de los instaladores y de las extensiones cambian, así
que algún nombre de botón puede no coincidir palabra por palabra. Los pasos y
las comprobaciones siguen siendo los mismos.

A diferencia de la guía de Windows, ésta sí se apoya en el uso real del scraper
en un Mac: las rutas de perfiles, el comportamiento de `caffeinate` y los
conflictos de iCloud salen de haber descargado con él un corpus de cuatro años.
