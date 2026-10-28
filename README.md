# scraper-x

Descarga publicaciones públicas de X (Twitter) para investigación, con Firefox y
Selenium, sin API de pago. Funciona en **macOS, Linux y Windows**.

Sirve para dos cosas:

- **Por cuentas**: la actividad de un grupo de personas durante años (una
  bancada, un gabinete, un conjunto de medios, los competidores de un sector).
- **Por términos**: todo lo que se publique con ciertas palabras o hashtags, en
  cualquier cuenta.

Está pensado para corpus largos, donde lo que importa es que el resultado sea
**auditable y reanudable** antes que rápido. Se usó para descargar 212.962
publicaciones de 54 congresistas durante cuatro años; ese censo viene como
ejemplo.

---

## 1. Qué hace y qué no

**Qué hace**

- Divide la descarga en **lotes** (por cuenta y trimestre, o por días) y deja una
  marca al terminar cada uno: se puede interrumpir y continuar sin repetir.
- Detecta cuando X **corta la paginación** antes de llegar al inicio del lote y
  vuelve a pedir sólo el tramo que falta.
- Expande las publicaciones largas ("Mostrar más") y el texto original cuando X
  muestra una traducción.
- Guarda favoritos en formato original (`2.1K`) y numérico (`2100`).
- Deduplica por identificador de publicación, no por texto ni por URL.
- En las búsquedas por términos, **verifica en local** que el texto contenga
  alguno de los términos: X devuelve publicaciones de contexto que no los
  mencionan.

**Qué NO hace**

- No descarga retuits sin comentario: la búsqueda de X no los devuelve.
- No descarga publicaciones borradas, de cuentas privadas o suspendidas.
- No usa la API de X. Depende de la interfaz web, que cambia sin avisar.
- No paraleliza: una sola ventana de Firefox, porque X limita por sesión.

---

## 2. Instalación

Necesitas **Python 3.11 o superior** (probado en 3.14) y **Firefox**.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`geckodriver` lo descarga Selenium solo. Si tu red lo bloquea, bájalo de
[mozilla/geckodriver](https://github.com/mozilla/geckodriver/releases) y déjalo
junto a los scripts (`geckodriver` o `geckodriver.exe`), o apunta la variable
`GECKODRIVER` al ejecutable.

---

## 3. Preparar la sesión de X en Firefox

El scraper **no inicia sesión ni maneja contraseñas**. Reutiliza las cookies de
un perfil de Firefox donde una persona ya entró a X a mano. Es el único paso
manual, se hace una vez y dura semanas.

**Usa un perfil aparte**, para poder seguir navegando mientras la descarga corre.

1. Abre el administrador de perfiles:

   ```bash
   # macOS
   /Applications/Firefox.app/Contents/MacOS/firefox --no-remote -P
   # Linux
   firefox --no-remote -P
   ```

   ```powershell
   # Windows
   & "C:\Program Files\Mozilla Firefox\firefox.exe" --no-remote -P
   ```

   Crea un perfil llamado `scraper` e inícialo.

2. En esa ventana entra a <https://x.com/login> y **escribe tú** usuario,
   contraseña y segundo factor. Marca que recuerde la sesión.

3. Comprueba que la búsqueda avanzada responde:
   `https://x.com/search?q=from%3Apetrogustavo&f=live`. Si pide iniciar sesión,
   no quedó guardada.

4. **Cierra Firefox por completo.** Bloquea el perfil mientras está abierto y el
   scraper no puede usarlo al mismo tiempo.

5. Copia la ruta del perfil desde `about:profiles` ("Directorio raíz") y pásala
   al scraper:

   ```bash
   export X_FIREFOX_PROFILE="$HOME/Library/Application Support/Firefox/Profiles/xxxxxxxx.scraper"
   ```

   ```powershell
   $env:X_FIREFOX_PROFILE = "$env:APPDATA\Mozilla\Firefox\Profiles\xxxxxxxx.scraper"
   ```

   Sin esa variable, el scraper toma el perfil predeterminado de `profiles.ini`,
   que suele ser el de uso diario.

**Cosas que conviene saber**

- Corre sin ventana visible. Con `--headed` se ve el navegador, útil para
  comprobar que la sesión entró bien.
- Si X cierra la sesión, el scraper lo detecta como estado `login` y **falla el
  lote** en vez de guardar datos vacíos. Vuelve a entrar a mano y relanza.
- **Nunca pongas credenciales en los scripts.** El código no las pide.
- Scrapear con la cuenta personal implica riesgo de límites y de suspensión.
  Evalúalo frente a los términos de servicio de X y las reglas de tu institución.
- Cada persona que replique el estudio necesita **su propia sesión**: las cookies
  son credenciales y no se comparten.

---

## 4. Descargar por términos

El caso más simple: todo lo que se publique con ciertas palabras.

```bash
python descargar_busqueda.py \
  --term "Prioridad Nacional" --term "#PrioridadNacional" \
  --start 2026-03-01 --end 2026-08-01 \
  --output prioridad_nacional.csv
```

- `--term` se repite tantas veces como haga falta. Las frases se buscan como
  frase exacta; los hashtags, tal cual.
- `--end` es **exclusivo**: `2026-08-01` incluye todo el 31 de julio.
- `--batch-days 3` agrupa días por búsqueda y reduce los bloqueos de X. Si un
  lote resulta demasiado voluminoso, el scraper baja a días sueltos solo.
- `--query` acepta una expresión completa de X si necesitas operadores
  (`lang:es`, `-filter:replies`, `from:`). El filtro local sigue exigiendo que el
  texto contenga alguno de los `--term`.

---

## 5. Descargar por cuentas

Para un grupo de personas necesitas un **censo**: un JSON con la lista. Parte de
`censo_plantilla.json`; `ejemplo_pacto_historico.json` es un caso real completo.

```json
{
  "scope": {
    "name": "Mi grupo, periodo 2022-2026",
    "scrape_start_local": "2022-07-20T00:00:00-05:00",
    "scrape_end_local_exclusive": "2026-07-20T00:00:00-05:00",
    "query_timezone": "UTC",
    "selection_rule": "A quién se incluye y por qué.",
    "official_chamber_directory": "URL que respalda la lista"
  },
  "accounts": [
    {
      "id": "grupo-nombre-apellido",
      "corporation": "Cámara de Representantes",
      "name": "Nombre completo",
      "district": "Circunscripción, área o cargo",
      "x_handle": "usuarioDeX",
      "account_url": "https://x.com/usuarioDeX",
      "official_source_url": "URL de la ficha oficial de esa persona",
      "service_intervals": ["2022-07-20/2026-07-20"],
      "notes": "Dónde se verificó la cuenta."
    }
  ]
}
```

`corporation` y `district` son etiquetas libres: sirven para agrupar en el
análisis y para filtrar con `--corporation`. No tienen que ser cámaras
legislativas.

Primero el plan, sin abrir el navegador:

```bash
python descargar_cuentas.py --roster mi_censo.json --plan-only
```

Luego la descarga:

```bash
python descargar_cuentas.py \
  --roster mi_censo.json \
  --output mi_corpus.csv \
  --window-months 3 \
  --retries 12 --retry-backoff 600
```

| Opción | Para qué |
|---|---|
| `--window-months 3` | Meses por lote. Trimestres rinden mejor que meses; los lotes saturados se subdividen solos. |
| `--retries 12 --retry-backoff 600` | Reintentos y espera en segundos cuando X bloquea. 10–15 minutos funciona; esperas cortas sólo gastan intentos. |
| `--account ID` / `--corporation texto` | Limitar a una persona o a un subconjunto. |
| `--start` / `--end` | Acotar el periodo (final exclusivo). |
| `--headed` | Ver el navegador. |
| `--force --refresh` | Volver a leer lotes ya terminados **una sola vez**, para corregir datos viejos. |

Para revisar el censo como hoja de cálculo:

```bash
python exportar_censo.py --roster mi_censo.json --output mi_censo.csv
```

### Tres reglas sobre el censo

1. **Reconstruye el periodo, no el directorio de hoy.** En cuatro años hay
   renuncias, muertes y reemplazos. `service_intervals` registra cuándo ejerció
   cada persona; la descarga cubre la cuenta completa y el análisis filtra después.
2. **Verifica cada usuario de X contra una fuente institucional.** Dos de las 54
   cuentas del ejemplo estaban mal y devolvían cero publicaciones en cuatro años.
   Un usuario equivocado no produce error: produce silencio.
3. **Anota en `notes` de dónde salió cada cuenta.** Es lo que permite defender el
   corpus después.

---

## 6. Pausar, continuar y dejarlo corriendo

Pausar: `Ctrl+C`. Continuar: el mismo comando; omite lo ya terminado.

**macOS / Linux**

```bash
nohup caffeinate -i python -u descargar_cuentas.py --roster mi_censo.json >> salida.log 2>&1 &
```

`caffeinate -i` evita la suspensión por inactividad, **pero no la de cerrar la
tapa**. Déjalo con cargador y tapa abierta. En Linux, `systemd-inhibit --what=idle`.

**Windows (PowerShell)**

```powershell
powercfg /change standby-timeout-ac 0          # no suspender con cargador
Start-Process -WindowStyle Hidden py -ArgumentList "-3","-u","descargar_cuentas.py","--roster","mi_censo.json" -RedirectStandardOutput salida.log
```

Para detenerlo: `Stop-Process -Id <pid>`. El proceso guarda sus checkpoints al
recibir la señal.

En cualquier sistema: si la máquina se suspende o se reinicia, el proceso muere
y **no se pierde nada**; basta relanzar el mismo comando.

---

## 7. Qué esperar de X (planifica con esto)

- X permite **unas 12 búsquedas nuevas** y luego bloquea entre **9 y 15 minutos**.
- Ritmo observado: **10 a 30 lotes por hora**.
- 54 cuentas por 4 años (≈1.300 lotes) tomaron **unos 3 días** de reloj.
- X **corta la paginación** sin avisar, a veces con 20 resultados y a veces con
  400. Por eso el scraper compara la fecha más antigua recuperada con el inicio
  del lote y reencola el tramo faltante. Sin esa verificación se pierden semanas
  enteras en silencio.

---

## 8. Verificar antes de analizar

Nunca des por buena una descarga sin estos tres chequeos.

**a) Lotes truncados que quedaron certificados**

```bash
python reparar_truncamientos.py --roster mi_censo.json --min-records 1 --min-expected 1          # simula
python reparar_truncamientos.py --roster mi_censo.json --min-records 1 --min-expected 1 --apply  # reabre
```

Reabre los tramos que X no entregó; después vuelve a correr la descarga. No borra
nada.

**b) Huecos por cuenta**

Compara el ritmo de publicación de cada cuenta con sus silencios largos. Un hueco
de 80 días en alguien que publica 5 veces al día es sospechoso; en alguien que
publica una vez al mes, no. Los huecos reales suelen explicarse por recesos,
fallecimientos o cuentas abiertas tarde. Verifica los sospechosos volviendo a
pedir ese intervalo con `--start` y `--end`.

**c) Textos cortados**

X recorta las publicaciones largas a ~280 caracteres en los resultados de
búsqueda, **sin dejar ninguna marca**. Señal de alarma: un pico de longitudes
entre 270 y 285 caracteres. Este scraper ya pulsa "Mostrar más"; si heredas datos
de una versión anterior, reléelos:

```bash
python descargar_cuentas.py --roster mi_censo.json --force --refresh
```

En el corpus del Pacto Histórico eso recuperó **44.061 publicaciones** y **12,3
millones de caracteres** que faltaban.

---

## 9. Salida

CSV con separador `;` y codificación UTF-8 con BOM (Excel lo abre directo):

| Columna | Contenido |
|---|---|
| `corporation`, `congressperson`, `district`, `roster_id` | Identidad, desde el censo (sólo en la descarga por cuentas) |
| `queried_handle`, `service_intervals` | Cuenta consultada y cuándo ejerció |
| `username`, `real_name` | Autor según X |
| `date` | Marca de tiempo ISO en UTC |
| `text` | Texto completo |
| `matched_terms` | Términos encontrados (búsquedas temáticas) |
| `favorites_raw`, `favorites` | `"2.1K"` y `2100` |
| `tweet_id`, `url` | Identificadores |
| `scraped_at`, `source_query` | Trazabilidad: cuándo y con qué consulta |

```python
import pandas as pd
df = pd.read_csv("mi_corpus.csv", sep=";", encoding="utf-8-sig")
```

También deja `*_descarga.log`, `*_progreso.json` y la carpeta de lotes, que es la
que permite reanudar y auditar.

---

## 10. Cuaderno de ejemplo

`ejemplo.ipynb` recorre todo el flujo con descargas pequeñas: comprobar el
entorno, verificar la sesión de X, descargar dos días por términos y un mes de
una cuenta, revisar la calidad del resultado y hacer un primer análisis.

```bash
pip install pandas matplotlib jupyter
jupyter lab ejemplo.ipynb     # o: jupyter notebook ejemplo.ipynb
```

Ábrelo desde esta carpeta, para que encuentre los scripts y el censo de ejemplo.
Las descargas largas conviene lanzarlas fuera del cuaderno (§6): duran días y el
kernel no debería quedarse ocupado tanto tiempo.

---

## 11. Pruebas

```bash
python -m unittest test_scraper_x test_descargar_cuentas
```

28 pruebas que no abren navegador: construcción de consultas, conversión de
medianoche local a UTC, deduplicación, detección de truncamiento, reanudación y
protección del texto recuperado.

---

## 12. Antes de publicar el corpus

- La descarga sólo lee contenido **público**, pero scrapear va contra los
  términos de servicio de X. Es tu decisión y tu riesgo.
- Para compartir el conjunto, la práctica aceptada en investigación es publicar
  **sólo los identificadores** (`tweet_id`) y el código que los rehidrata, no el
  texto completo. Eso respeta los borrados posteriores.
- Hay datos personales: aunque sean figuras públicas, revisa las reglas de tu
  comité de ética antes de redistribuir.
- Documenta las limitaciones: sin retuits, sin publicaciones borradas, y huecos
  donde X no entregó resultados.
