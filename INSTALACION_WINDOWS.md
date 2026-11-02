# Instalación en Windows, desde cero

Guía para una computadora con Windows 10 u 11 recién estrenada, sin nada
instalado. No supone conocimientos de programación: cada paso dice qué hacer,
qué deberías ver y cómo comprobar que quedó bien antes de seguir.

Cuenta con hora y media la primera vez. Las descargas pesan unos 500 MB en
total.

**Si algo falla**, salta a la sección 12: están los errores más frecuentes con su
causa y su arreglo.

---

## Contenido

1. [Qué vas a instalar y para qué](#1-qué-vas-a-instalar-y-para-qué)
2. [Elegir dónde va a vivir el proyecto](#2-elegir-dónde-va-a-vivir-el-proyecto)
3. [Python](#3-python)
4. [Git y Git Bash](#4-git-y-git-bash)
5. [Visual Studio Code](#5-visual-studio-code)
6. [Firefox](#6-firefox)
7. [Bajar el scraper](#7-bajar-el-scraper)
8. [Crear el entorno virtual](#8-crear-el-entorno-virtual)
9. [Conectar Visual Studio Code](#9-conectar-visual-studio-code)
10. [Preparar la sesión de X](#10-preparar-la-sesión-de-x)
11. [Primera descarga de prueba](#11-primera-descarga-de-prueba)
12. [Errores frecuentes](#12-errores-frecuentes)

---

## 1. Qué vas a instalar y para qué

| Programa | Para qué sirve aquí | Tamaño |
|---|---|---|
| **Python** | El lenguaje en que está escrito el scraper | ~100 MB |
| **Git** (trae Git Bash) | Bajar el proyecto y una terminal decente en Windows | ~60 MB |
| **Visual Studio Code** | Editar archivos y correr el cuaderno de ejemplo | ~110 MB |
| **Firefox** | El navegador que el scraper controla | ~60 MB |

### Enlaces de descarga

Todos son los sitios oficiales. No bajes ninguno de otro lado.

| Programa | Enlace |
|---|---|
| Python para Windows | <https://www.python.org/downloads/windows/> |
| Git para Windows (trae Git Bash) | <https://git-scm.com/download/win> |
| Visual Studio Code | <https://code.visualstudio.com/Download> |
| Firefox | <https://www.mozilla.org/firefox/new/> |
| geckodriver (sólo si hace falta, §8) | <https://github.com/mozilla/geckodriver/releases> |

Y los del proyecto, por si los necesitas:

| Qué | Enlace |
|---|---|
| Documentación de Selenium | <https://www.selenium.dev/documentation/> |
| Buscador avanzado de X | <https://x.com/search-advanced> |

Sobre **Git Bash**: Windows trae PowerShell, que funciona, pero toda la
documentación de este proyecto y casi todo lo que vas a encontrar en internet
está escrito para terminales tipo Unix (macOS, Linux). Git Bash te da esa misma
terminal dentro de Windows, así que los comandos se copian y pegan tal cual. Es
la razón de instalarlo.

---

## 2. Elegir dónde va a vivir el proyecto

**Hazlo antes de instalar nada.** Es el error más costoso de esta guía y no da
ningún mensaje de error.

En Windows, la carpeta `Documentos` suele estar sincronizada con **OneDrive**.
Una descarga de este scraper puede durar días y escribir un archivo de cientos
de megabytes muchas veces: OneDrive intenta subirlo con cada escritura, crea
"copias en conflicto" y puede corromper el archivo a medio escribir.

Comprueba si tus Documentos están en OneDrive: abre el Explorador, entra a
`Documentos`, haz clic en la barra de direcciones y mira la ruta. Si aparece
`OneDrive` en el camino, está sincronizada.

**Usa una carpeta fuera de OneDrive.** Por ejemplo:

```
C:\investigacion
```

Créala desde el Explorador: ve a `Disco local (C:)`, clic derecho en un espacio
vacío → **Nuevo** → **Carpeta**, y llámala `investigacion`. Sin tildes ni
espacios en el nombre: ahorra problemas al escribir rutas.

---

## 3. Python

1. Entra a <https://www.python.org/downloads/windows/> y baja el instalador
   **"Windows installer (64-bit)"** de la última versión 3.x estable. Este
   proyecto necesita **3.11 o superior**.

2. Abre el archivo descargado. En la primera pantalla, **antes de instalar**,
   marca las dos casillas de abajo:

   - ☑ **Use admin privileges when installing py.exe**
   - ☑ **Add python.exe to PATH**

   > **La segunda casilla es la importante.** Si no la marcas, la terminal no
   > va a encontrar Python y nada de lo que sigue funciona. Viene desmarcada por
   > omisión. Si ya instalaste sin marcarla, vuelve a correr el instalador,
   > elige **Modify** y márcala.

3. Haz clic en **Install Now** y espera. Al final, si aparece el botón
   **Disable path length limit**, pínchalo: evita problemas con rutas largas.

**Comprobación.** Abre el menú Inicio, escribe `powershell`, abre **Windows
PowerShell** y escribe:

```
py --version
```

Debe responder algo como `Python 3.13.2`. Si en cambio se abre la **Microsoft
Store**, Windows está interceptando el comando: mira la sección 12.

---

## 4. Git y Git Bash

1. Entra a <https://git-scm.com/download/win> y baja **"64-bit Git for Windows
   Setup"**. La descarga puede empezar sola.

2. Abre el instalador. Son muchas pantallas y casi todas se dejan como vienen.
   Estas cuatro sí importan:

   | Pantalla | Qué elegir | Por qué |
   |---|---|---|
   | *Choosing the default editor used by Git* | **Use Visual Studio Code as Git's default editor** | Si no lo instalaste todavía, deja la opción que venga y cámbialo después; evita que se abra Vim, de donde es difícil salir |
   | *Adjusting the name of the initial branch* | **Override the default branch name** → `main` | Es el nombre que usa hoy GitHub |
   | *Adjusting your PATH environment* | **Git from the command line and also from 3rd-party software** (la del medio, recomendada) | Deja que Visual Studio Code use Git |
   | *Configuring the line ending conversions* | **Checkout as-is, commit Unix-style line endings** | Ver la nota de abajo |

   > **Sobre los finales de línea.** Windows termina sus líneas con dos
   > caracteres (`CRLF`) y el resto del mundo con uno (`LF`). La opción que Git
   > trae por omisión convierte los archivos al bajarlos, y eso puede alterar
   > los CSV que produce el scraper y los scripts de Python. La opción
   > recomendada arriba no toca nada.

   El resto de las pantallas: **Next** hasta el final. Los nombres pueden variar
   un poco según la versión del instalador.

**Comprobación.** Abre el menú Inicio, escribe `git bash` y abre **Git Bash**.
Se abre una ventana negra con un texto como `usuario@PC MINGW64 ~`. Escribe:

```bash
git --version
python --version
```

Deben responder las dos versiones. Esta ventana de Git Bash es la terminal que
vas a usar de aquí en adelante.

### Rutas en Git Bash

Git Bash escribe las rutas distinto a Windows. La misma carpeta:

| Dónde | Cómo se escribe |
|---|---|
| Explorador y PowerShell | `C:\investigacion\scraper-x` |
| Git Bash | `/c/investigacion/scraper-x` |

Y hay una tercera forma, `C:/investigacion/scraper-x`, con barras hacia adelante,
que **entienden las dos**. Esa es la que conviene usar cuando le pases una ruta a
Python (por ejemplo la del perfil de Firefox en la sección 10) porque
atraviesa Git Bash sin que nadie la traduzca por el camino.

Pon siempre las rutas **entre comillas** si contienen espacios, lo que pasa
seguido cuando tu nombre de usuario de Windows tiene dos palabras.

---

## 5. Visual Studio Code

1. Entra a <https://code.visualstudio.com/> y baja el instalador para Windows.

2. Instálalo. En la pantalla de tareas adicionales, marca:

   - ☑ **Add "Open with Code" action to Windows Explorer file context menu**
   - ☑ **Add to PATH**

3. Ábrelo. Instala dos extensiones: haz clic en el icono de cuadritos de la barra
   izquierda (**Extensions**, o `Ctrl+Shift+X`), busca e instala:

   - **Python** (de Microsoft)
   - **Jupyter** (de Microsoft)

4. Deja Git Bash como terminal por omisión: presiona `Ctrl+Shift+P`, escribe
   `Terminal: Select Default Profile`, presiona Enter y elige **Git Bash**.

   Desde ahora, la terminal que se abre con `Ctrl+ñ` dentro de Visual Studio Code
   es Git Bash, en la carpeta del proyecto. Es más cómodo que la ventana aparte.

---

## 6. Firefox

Entra a <https://www.mozilla.org/firefox/new/> e instálalo. Si ya lo tienes,
sirve igual.

**No uses Chrome ni Edge:** el scraper está escrito para Firefox.

---

## 7. Bajar el scraper

Abre **Git Bash** y escribe, línea por línea:

```bash
cd /c/investigacion
```

```bash
git clone URL_DEL_REPOSITORIO scraper-x
```

Reemplaza `URL_DEL_REPOSITORIO` por la dirección que te hayan dado. Si en cambio
recibiste un archivo `scraper-x.zip`, descomprímelo dentro de
`C:\investigacion` con clic derecho → **Extraer todo**, y sáltate el `clone`.

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

En Git Bash, dentro de `scraper-x`:

```bash
py -m venv .venv
```

Tarda unos segundos y no imprime nada. Ahora actívalo:

```bash
source .venv/Scripts/activate
```

> **Ojo con esta línea.** En macOS y Linux es `.venv/bin/activate`; en Windows la
> carpeta se llama `Scripts`. Casi toda la documentación de internet muestra la
> primera forma. Si copias esa, da `No such file or directory`.

El texto del indicador cambia y empieza por `(.venv)`. Eso significa que está
activo. **Hay que activarlo en cada ventana nueva de terminal**; no queda puesto
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
institucionales que bloquean la descarga:

1. Entra a <https://github.com/mozilla/geckodriver/releases>.
2. En la versión más reciente, abre **Assets** y baja el archivo que termina en
   **`win64.zip`** (o `win32.zip` en un Windows de 32 bits, hoy raro).
3. Descomprímelo. Adentro hay un solo archivo: `geckodriver.exe`.
4. Cópialo a la carpeta `scraper-x`, junto a `scraper_x.py`. El scraper lo busca
   ahí antes de intentar descargarlo.

Si prefieres dejarlo en otra carpeta, dile dónde está con la variable
`GECKODRIVER`, en Git Bash:

```bash
export GECKODRIVER="C:/herramientas/geckodriver.exe"
```

**Comprobación.**

```bash
./geckodriver.exe --version
```

Debe imprimir la versión. Si Windows lo bloquea por venir de internet, abre sus
**Propiedades** con clic derecho y marca **Desbloquear**.

---

## 9. Conectar Visual Studio Code

Abre la carpeta del proyecto: en Visual Studio Code, **File** → **Open
Folder…** → `C:\investigacion\scraper-x`. Si pregunta si confías en los autores,
responde que sí.

Dile qué Python usar: `Ctrl+Shift+P`, escribe `Python: Select Interpreter`,
Enter, y elige el que diga **`.venv`** (aparece marcado como *Recommended*).
Este paso es el que hace que el cuaderno y la terminal usen las librerías que
acabas de instalar.

**Comprobación.** Abre `ejemplo.ipynb` desde la lista de archivos de la
izquierda. Arriba a la derecha debe decir `.venv`. Presiona el botón de
ejecutar de la primera celda de código: debe imprimir la lista de perfiles de
Firefox de tu computadora.

---

## 10. Preparar la sesión de X

El scraper **no inicia sesión ni maneja contraseñas**. Reutiliza las cookies de
un perfil de Firefox donde tú ya entraste a X a mano. Conviene usar un perfil
aparte, para poder seguir navegando mientras la descarga corre.

1. Cierra Firefox. Presiona `Win+R`, escribe `firefox.exe -P` y Enter. Se abre
   el administrador de perfiles.

2. **Create Profile…** → llámalo `scraper` → **Finish** → **Start Firefox**.

3. En esa ventana, entra a <https://x.com> e inicia sesión normalmente. Resuelve
   el código de verificación si lo pide. Comprueba que ves tu inicio.

4. Entra a `about:profiles` en la barra de direcciones. Busca el bloque del
   perfil `scraper` y copia la ruta que dice **Directorio raíz**. Se parece a:

   ```
   C:\Users\TU_USUARIO\AppData\Roaming\Mozilla\Firefox\Profiles\a1b2c3d4.scraper
   ```

5. **Cierra Firefox por completo.** Mientras está abierto, bloquea el perfil y
   el scraper no puede usarlo.

6. Declara esa ruta. En el cuaderno, primera celda, cambiando las barras `\` por
   `/`:

   ```python
   PERFIL_FIREFOX = "C:/Users/TU_USUARIO/AppData/Roaming/Mozilla/Firefox/Profiles/a1b2c3d4.scraper"
   ```

   Y si vas a correr los scripts desde la terminal, en Git Bash:

   ```bash
   export X_FIREFOX_PROFILE="C:/Users/TU_USUARIO/AppData/Roaming/Mozilla/Firefox/Profiles/a1b2c3d4.scraper"
   ```

   Esa variable se borra al cerrar la ventana. Para no repetirla cada vez,
   agrégala al final del archivo `~/.bashrc`, que Git Bash lee al abrirse.

> **Por qué declararlo y no dejar que lo adivine.** Si no dices cuál es, el
> scraper toma el perfil marcado como predeterminado, que normalmente es el de
> uso diario y puede no tener sesión en X. El fallo es silencioso: X manda el
> navegador al formulario de acceso y la descarga termina **vacía, sin ningún
> mensaje de error**.

**Comprobación.** Ejecuta las tres primeras celdas de código del cuaderno. La tercera abre Firefox
sin ventana y debe imprimir `estado de la página: results` y `Sesión lista.` Si
dice `login`, la sesión no quedó: repite desde el paso 3 y asegúrate de cerrar
Firefox antes de probar.

---

## 11. Primera descarga de prueba

Sigue el cuaderno `ejemplo.ipynb` de principio a fin: baja dos días de un
hashtag y un mes de una cuenta, revisa la calidad del resultado y hace un primer
análisis. Son unos pocos minutos.

Cuando pases a tu propio estudio, lee el `README.md`: explica el censo de
cuentas, qué esperar de los bloqueos de X y las comprobaciones que hay que hacer
antes de analizar.

### Dejarlo corriendo varios días

Las descargas largas se lanzan **fuera** del cuaderno. En Git Bash:

```bash
nohup python -u descargar_cuentas.py --roster censo.json \
    --profile "$X_FIREFOX_PROFILE" \
    --window-months 3 --retries 12 --retry-backoff 600 >> salida.log 2>&1 &
```

Sigue el avance con:

```bash
tail -f salida.log
```

`Ctrl+C` corta el `tail`, no la descarga.

**Impide que Windows se duerma**, o la descarga se interrumpe sola: ve a
**Configuración** → **Sistema** → **Energía** y pon *Suspender* en **Nunca**.
Deja la computadora enchufada. Si es portátil, **cerrar la tapa la suspende**
aunque hayas puesto Nunca; cambia eso en **Panel de control** → **Opciones de
energía** → **Elegir el comportamiento del cierre de la tapa**.

El scraper es reanudable: si se corta, lo vuelves a lanzar con el mismo comando y
continúa donde quedó.

---

## 12. Errores frecuentes

| Lo que ves | Qué pasa | Arreglo |
|---|---|---|
| Se abre la Microsoft Store al escribir `python` | Windows trae un atajo falso que lleva a la tienda | Usa `py` en vez de `python`, o quita el atajo en **Configuración** → **Aplicaciones** → **Configuración avanzada de la aplicación** → **Alias de ejecución de la aplicación**, y apaga los de `python.exe` y `python3.exe` |
| `python: command not found` | No marcaste *Add python.exe to PATH* | Vuelve a correr el instalador de Python → **Modify** → marca la casilla |
| `bash: .venv/bin/activate: No such file or directory` | En Windows la carpeta se llama `Scripts`, no `bin` | `source .venv/Scripts/activate` |
| `pip: command not found` | El entorno virtual no está activo | `source .venv/Scripts/activate`; el indicador debe empezar por `(.venv)` |
| El cuaderno dice que falta `pandas`, pero lo instalaste | Visual Studio Code está usando otro Python | `Ctrl+Shift+P` → `Python: Select Interpreter` → el que diga `.venv` |
| `FileNotFoundError: No existe el perfil de Firefox` | La ruta está mal escrita | Cópiala de `about:profiles` y cambia `\` por `/` |
| `estado de la página: login` | Ese perfil no tiene sesión en X, o es otro perfil | Repite la sección 10; confirma que la ruta sea la del perfil donde iniciaste sesión |
| La descarga termina al instante y el CSV sale vacío | Casi siempre es lo mismo: perfil sin sesión | Igual que la fila anterior. Es el fallo silencioso de la sección 10 |
| `Firefox is already running` o se queda colgado | Firefox está abierto con ese perfil | Ciérralo del todo; revisa que no quede en la bandeja del sistema |
| Aparecen copias del CSV con `(2)` o "conflicto" en el nombre | El proyecto está dentro de OneDrive | Mueve la carpeta fuera de OneDrive (sección 2) |
| `Algo salió mal` o la descarga se detiene a los pocos lotes | X te limitó por hacer muchas búsquedas | Normal: el scraper espera y reintenta. Ver `README.md` §7 |

---

## Nota sobre esta guía

Las versiones de Windows, de los instaladores y de las extensiones cambian, así
que algún nombre de botón puede no coincidir palabra por palabra. Los pasos y
las comprobaciones siguen siendo los mismos.

Esta guía se redactó sin una máquina Windows a mano para recorrerla de punta a
punta: las rutas, los comandos y los mensajes de error salen del código del
proyecto y de la documentación de cada programa. Si encuentras un paso que no
coincide, corrígelo aquí y cuéntalo, que es el tipo de detalle que solo aparece
usándolo.
