# Scraper de X para bancadas legislativas

Descarga la actividad pública en X (Twitter) de un grupo de personas durante un
periodo largo, con una sola sesión de Firefox y sin API de pago. Está pensado
para investigación social: prioriza que el resultado sea **auditable y
reanudable** antes que rápido.

Se construyó para descargar las 54 cuentas de los congresistas del Pacto
Histórico (Colombia) entre el 20 de julio de 2022 y el 19 de julio de 2026:
**212.962 publicaciones**. El censo de ese caso viene incluido como ejemplo, y
la herramienta sirve para cualquier otra bancada cambiando un archivo JSON.

---

## 1. Qué hace y qué no

**Qué hace**

- Descarga por **cuenta y trimestre**, con una búsqueda avanzada por lote.
- Guarda cada lote por separado y deja una marca al terminarlo, así que se puede
  interrumpir en cualquier momento y continuar sin repetir trabajo.
- Detecta cuando X **corta la paginación** antes de llegar al inicio del lote y
  vuelve a pedir sólo el tramo que falta.
- Expande las publicaciones largas ("Mostrar más") y el texto original cuando X
  muestra una traducción.
- Guarda favoritos en formato original (`2.1K`) y numérico (`2100`).
- Deduplica por el identificador de la publicación, no por texto ni por URL.

**Qué NO hace**

- No descarga retuits sin comentario: la búsqueda de X no los devuelve.
- No descarga publicaciones borradas, de cuentas privadas o suspendidas.
- No usa la API de X. Depende de la interfaz web, que cambia sin avisar.
- No paraleliza: una sola ventana de Firefox, porque X limita por sesión.

---

## 2. Requisitos

- **Python 3.11 o superior** (probado en 3.14).
- **Firefox** instalado, con **sesión iniciada en X** en el perfil que se va a usar.
  La búsqueda avanzada de X no funciona sin sesión.
- **geckodriver**. Selenium 4 lo descarga solo (Selenium Manager); si prefieres
  fijarlo, apunta la variable `GECKODRIVER` al ejecutable.
- Firefox **no puede estar abierto** con ese mismo perfil mientras corre el scraper.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Preparar el censo (el paso que de verdad importa)

El scraper no adivina a quién descargar: lee un JSON con la lista de personas.
Parte de `censo_plantilla.json` y usa `pacto_historico_2022_2026.json` como
ejemplo completo.

```json
{
  "scope": {
    "name": "Bancada X, periodo 2022-2026",
    "scrape_start_local": "2022-07-20T00:00:00-05:00",
    "scrape_end_local_exclusive": "2026-07-20T00:00:00-05:00",
    "query_timezone": "UTC",
    "selection_rule": "A quién se incluye y por qué.",
    "official_chamber_directory": "URL oficial que respalda la lista"
  },
  "accounts": [
    {
      "id": "camara-nombre-apellido",
      "corporation": "Cámara de Representantes",
      "name": "Nombre completo",
      "district": "Circunscripción",
      "x_handle": "usuarioDeX",
      "account_url": "https://x.com/usuarioDeX",
      "official_source_url": "URL de la ficha oficial de esa persona",
      "service_intervals": ["2022-07-20/2026-07-20"],
      "notes": "Titular o reemplazo; dónde se verificó la cuenta."
    }
  ]
}
```

Tres reglas aprendidas a golpes:

1. **Reconstruye el periodo, no el directorio de hoy.** En cuatro años hay
   renuncias, muertes y reemplazos. `service_intervals` registra cuándo ejerció
   cada persona; la descarga cubre la cuenta completa y el análisis filtra después.
2. **Verifica cada usuario de X contra una fuente institucional.** Dos de las 54
   cuentas del ejemplo estaban mal y devolvían cero publicaciones en cuatro años.
   Un usuario equivocado no produce error: produce silencio.
3. **Anota en `notes` de dónde salió cada cuenta.** Es lo que permite defender el
   corpus después.

Para revisar el censo como hoja de cálculo:

```bash
python exportar_censo_pacto_historico.py --roster mi_censo.json --output mi_censo.csv
```

---

## 4. Ejecutar la descarga

Primero, sin abrir el navegador, para ver el plan:

```bash
python descargar_cuentas_pacto_historico.py --roster mi_censo.json --plan-only
```

Luego la descarga real:

```bash
python descargar_cuentas_pacto_historico.py \
  --roster mi_censo.json \
  --output mi_corpus.csv \
  --parts-directory mi_corpus_partes \
  --window-months 3 \
  --retries 12 \
  --retry-backoff 600
```

Opciones que importan:

| Opción | Para qué |
|---|---|
| `--window-months 3` | Meses por lote. Trimestres rinden mejor: menos búsquedas que mensual, y los lotes saturados se subdividen solos. |
| `--retries 12 --retry-backoff 600` | Reintentos y espera en segundos cuando X bloquea. 10–15 minutos funciona; esperas cortas sólo gastan intentos. |
| `--account ID` / `--corporation senado` | Limitar a una persona o a una corporación. |
| `--start` / `--end` | Acotar el periodo (el final es exclusivo). |
| `--headed` | Ver el navegador. Útil para depurar. |
| `--force --refresh` | Volver a leer lotes ya terminados **una sola vez** (para corregir datos viejos). |

Para pausar: `Ctrl+C`, o `kill -TERM <pid>` si corre en segundo plano. Para
continuar: el mismo comando. Omite lo ya terminado.

---

## 5. Qué esperar de X (planifica con esto)

- X permite **unas 12 búsquedas nuevas** y luego bloquea entre **9 y 15 minutos**.
- El ritmo real observado fue de **10 a 30 lotes por hora**.
- Las 54 cuentas por 4 años (≈1.300 lotes) tomaron **unos 3 días** de reloj.
- X **corta la paginación** sin avisar, a veces con 20 resultados y a veces con 400.
  Por eso el scraper compara la fecha más antigua recuperada con el inicio del
  lote y reencola el tramo faltante. Sin esa verificación se pierden semanas
  enteras en silencio.

En portátiles: el proceso muere si la máquina se suspende. En macOS,
`caffeinate -i` evita la suspensión por inactividad, **pero no la de cerrar la
tapa**. Déjalo con cargador y tapa abierta:

```bash
nohup caffeinate -i python -u descargar_cuentas_pacto_historico.py ... >> salida.log 2>&1 &
```

---

## 6. Verificar antes de analizar

Nunca des por buena una descarga sin estos tres chequeos.

**a) Lotes truncados que quedaron certificados**

```bash
python reparar_truncamientos_pacto_historico.py --min-records 1 --min-expected 1          # simula
python reparar_truncamientos_pacto_historico.py --min-records 1 --min-expected 1 --apply  # reabre
```

Reabre los tramos que X no entregó y luego vuelves a correr la descarga. No borra
nada.

**b) Huecos por cuenta**

Compara, para cada cuenta, su ritmo de publicación con los silencios largos. Un
hueco de 80 días en alguien que publica 5 veces al día es sospechoso; en alguien
que publica una vez al mes, no. Los huecos reales suelen explicarse por recesos
legislativos, fallecimientos o cuentas que abrieron tarde. Verifica los
sospechosos volviendo a pedir ese intervalo.

**c) Textos cortados**

X recorta las publicaciones largas a ~280 caracteres en los resultados de
búsqueda, **sin dejar ninguna marca**. Señal de alarma: un pico de longitudes
entre 270 y 285 caracteres. Este scraper ya pulsa "Mostrar más", pero si heredas
datos de una versión anterior:

```bash
python descargar_cuentas_pacto_historico.py --roster mi_censo.json --force --refresh ...
```

En el caso del Pacto Histórico eso recuperó **44.061 publicaciones** y **12,3
millones de caracteres** que faltaban.

---

## 7. Salida

Un CSV con separador `;` y codificación UTF-8 con BOM (Excel lo abre directo):

| Columna | Contenido |
|---|---|
| `corporation`, `congressperson`, `district`, `roster_id` | Identidad, desde el censo |
| `queried_handle`, `service_intervals` | Cuenta consultada y cuándo ejerció |
| `username`, `real_name` | Autor según X |
| `date` | Marca de tiempo ISO en UTC |
| `text` | Texto completo |
| `favorites_raw`, `favorites` | `"2.1K"` y `2100` |
| `tweet_id`, `url` | Identificadores |
| `scraped_at`, `source_query` | Trazabilidad: cuándo y con qué consulta |

En pandas:

```python
import pandas as pd
df = pd.read_csv("mi_corpus.csv", sep=";", encoding="utf-8-sig")
```

También deja `*_descarga.log` (registro completo), `*_progreso.json` (estado) y
la carpeta de lotes, que es la que permite reanudar y auditar.

---

## 8. Descargar por términos en vez de por cuentas

`descargar_prioridad_nacional.py` hace lo mismo pero buscando expresiones en
todas las cuentas, día por día, con un filtro local que descarta las
publicaciones que X muestra pero no contienen literalmente ninguno de los
términos. Útil para hashtags y consignas.

---

## 9. Pruebas

```bash
python -m unittest test_scraper_x_mejorado test_descargar_cuentas_pacto_historico
```

27 pruebas que no abren el navegador: cubren la construcción de consultas, la
conversión de medianoche local a UTC, la deduplicación, la detección de
truncamiento, la reanudación y la protección del texto recuperado.

---

## 10. Antes de publicar el corpus

- La descarga sólo lee contenido **público**, pero scrapear va contra los
  términos de servicio de X. Es tu decisión y tu riesgo.
- Para compartir el conjunto, la práctica aceptada en investigación es publicar
  **sólo los identificadores** (`tweet_id`) y el código que los rehidrata, no el
  texto completo. Eso respeta los borrados posteriores.
- Hay datos personales: aunque sean figuras públicas, revisa las reglas de tu
  comité de ética antes de redistribuir.
- Documenta siempre las limitaciones: sin retuits, sin publicaciones borradas,
  y huecos donde X no entregó resultados.
