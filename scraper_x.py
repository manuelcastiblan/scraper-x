#!/usr/bin/env python3
"""Extrae publicaciones de una búsqueda de X con Selenium y guardado reanudable.

Ejemplo:
    python scraper_x.py

La fecha de ``until:`` se interpreta como límite exclusivo. Por eso la consulta
predeterminada usa ``until:2026-06-22`` para incluir todo el 21 de junio.
"""

from __future__ import annotations

import argparse
import configparser
import csv
import logging
import os
import random
import re
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlencode


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_QUERY = (
    "(from:IvanCepedaCast OR from:ABDELAESPRIELLA) "
    "since:2026-06-01 until:2026-06-22"
)
DEFAULT_OUTPUT = SCRIPT_DIR / "busqueda_simple.csv"
LOCAL_GECKODRIVER_NAMES = ("geckodriver", "geckodriver.exe")

# X sirve desde 2026 una interfaz sin los data-testid que tenía antes; los
# selectores "legacy" se conservan por si alguna cuenta recibe aún la anterior.
TWEET_SELECTOR = "article"
LIKE_BUTTON_SELECTOR = (
    '[data-engagement-action="like"] button, '
    'button[data-testid="like"], button[data-testid="unlike"]'
)
SHOW_MORE_LABELS = ("Mostrar más", "Show more")
SHOW_ORIGINAL_LABELS = ("Mostrar original", "Show original", "Ver original", "Ver texto original")
LIKE_LABEL_RE = re.compile(r"^\s*(\d[\d.,  ]*?)\s*(?:me gusta|like)", flags=re.IGNORECASE)
SNOWFLAKE_EPOCH_MS = 1288834974657  # 2010-11-04T01:42:54.657Z
FIRST_SNOWFLAKE_ID = 2**35

OWN_ELEMENTS_JS = """
const article = arguments[0];
return [...article.querySelectorAll(arguments[1])]
    .filter(element => element.closest('article') === article);
"""

OWN_STATUS_HREFS_JS = """
const article = arguments[0];
return [...article.querySelectorAll('a[href*="/status/"]')]
    .filter(link => link.closest('article') === article)
    .map(link => link.getAttribute('href'));
"""

ARTICLE_KIND_JS = """
const hasOwnLink = article => [...article.querySelectorAll('a[href*="/status/"]')]
    .some(link => link.closest('article') === article);
const article = arguments[0];
if (!hasOwnLink(article)) return 'wrapper';
const parent = article.parentElement ? article.parentElement.closest('article') : null;
if (!parent) return 'post';
return hasOwnLink(parent) ? 'quote' : 'repost';
"""

TEXT_ELEMENTS_JS = """
const article = arguments[0];
const own = selector => [...article.querySelectorAll(selector)]
    .filter(element => element.closest('article') === article);
const legacy = own('div[data-testid="tweetText"]');
if (legacy.length || article.querySelector('[data-testid]')) return legacy;
return own('div[dir="auto"]');
"""

READ_TEXT_JS = """
const element = arguments[0], labels = arguments[1];
let text = (element.innerText || element.textContent || '').trimEnd();
for (const button of element.querySelectorAll('button')) {
    const label = button.textContent.trim();
    if (labels.includes(label) && text.endsWith(label)) {
        text = text.slice(0, -label.length).trimEnd();
    }
}
return text;
"""

LABELED_CONTROLS_JS = """
const article = arguments[0], labels = arguments[1];
const own = selector => [...article.querySelectorAll(selector)]
    .filter(element => element.closest('article') === article
        && labels.includes(element.textContent.trim()));
const buttons = own('button, [role="button"]');
return buttons.length ? buttons : own('span').slice(0, 1);
"""

REAL_NAME_JS = """
const article = arguments[0], username = arguments[1].toLowerCase();
const texts = [...article.querySelectorAll('a[href], div[data-testid="User-Name"] span')]
    .filter(element => element.closest('article') === article)
    .filter(element => element.tagName !== 'A'
        || element.getAttribute('href').toLowerCase() === '/' + username)
    .map(element => element.textContent.trim());
return texts.find(text => text && !text.startsWith('@') && text.toLowerCase() !== username) || '';
"""
STATUS_RE = re.compile(
    r"(?:https?://(?:www\.)?(?:x|twitter)\.com)?/([^/?#]+)/status/(\d+)",
    flags=re.IGNORECASE,
)
FROM_RE = re.compile(r"\bfrom:([A-Za-z0-9_]{1,15})\b", flags=re.IGNORECASE)
DATE_OPERATOR_RE = re.compile(
    r"\b(since|until):(\d{4}-\d{2}-\d{2})"
    r"(?:_(\d{2}):(\d{2}):(\d{2})_UTC)?\b",
    flags=re.IGNORECASE,
)

CSV_FIELDS = [
    "username",
    "real_name",
    "date",
    "text",
    "matched_terms",
    "favorites_raw",
    "favorites",
    "tweet_id",
    "url",
    "scraped_at",
    "source_query",
]


@dataclass(frozen=True)
class QueryConstraints:
    accounts: frozenset[str]
    since: datetime | None
    until: datetime | None


@dataclass
class TweetRecord:
    username: str
    real_name: str
    date: str
    text: str
    matched_terms: str
    favorites_raw: str
    favorites: int | None
    tweet_id: str
    url: str
    scraped_at: str
    source_query: str

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_query_constraints(query: str) -> QueryConstraints:
    accounts = frozenset(match.casefold() for match in FROM_RE.findall(query))
    bounds: dict[str, datetime] = {}

    for operator, raw_date, hour, minute, second in DATE_OPERATOR_RE.findall(query):
        parsed_date = date.fromisoformat(raw_date)
        parsed_time = (
            datetime_time(int(hour), int(minute), int(second))
            if hour
            else datetime_time.min
        )
        bounds[operator.casefold()] = datetime.combine(
            parsed_date,
            parsed_time,
            tzinfo=timezone.utc,
        )

    since = bounds.get("since")
    until = bounds.get("until")
    if since and until and since >= until:
        raise ValueError("La fecha de since: debe ser anterior a la fecha de until:.")

    return QueryConstraints(accounts=accounts, since=since, until=until)


def timestamp_matches(timestamp: str, constraints: QueryConstraints) -> bool:
    parsed = parse_iso_datetime(timestamp)
    if constraints.since and parsed < constraints.since:
        return False
    if constraints.until and parsed >= constraints.until:
        return False
    return True


def extract_status_identity(url: str) -> tuple[str, str, str]:
    match = STATUS_RE.search(url or "")
    if not match:
        raise ValueError(f"No se encontró una URL canónica de publicación en: {url!r}")

    username, tweet_id = match.groups()
    canonical_url = f"https://x.com/{username}/status/{tweet_id}"
    return username, tweet_id, canonical_url


def parse_compact_number(value: str | None) -> int | None:
    """Convierte 2.1K, 10 mil, 1,234 o 1.234 a enteros sin inventar un cero."""
    if not value:
        return None

    normalized = value.strip().upper().replace("\u00a0", " ")
    suffix_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(K|M|B|MIL)\b", normalized)
    if suffix_match:
        number = float(suffix_match.group(1).replace(",", "."))
        factor = {"K": 1_000, "MIL": 1_000, "M": 1_000_000, "B": 1_000_000_000}[
            suffix_match.group(2)
        ]
        return round(number * factor)

    integer_match = re.search(r"\d[\d.,\s]*", normalized)
    if not integer_match:
        return None
    digits = re.sub(r"\D", "", integer_match.group(0))
    return int(digits) if digits else None


def keep_longest_text(previous: "TweetRecord | None", current: TweetRecord) -> TweetRecord:
    """Conserva el texto más largo al volver a leer una publicación ya guardada.

    Un repaso puede encontrar la publicación otra vez recortada —si el clic en
    "Mostrar más" no alcanza a aplicarse—, y en ese caso sobrescribir borraría
    texto ya recuperado.
    """

    if previous is not None and len(previous.text) > len(current.text):
        current.text = previous.text
    return current


def find_matching_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized_text = text.casefold()
    return [term for term in terms if term.casefold() in normalized_text]


def build_search_url(query: str, language: str = "es") -> str:
    params = urlencode(
        {
            "q": query,
            "src": "typed_query",
            "f": "live",
            "lang": language,
        }
    )
    return f"https://x.com/search?{params}"


def discover_firefox_profile(explicit: Path | None = None) -> Path | None:
    if explicit:
        profile = explicit.expanduser().resolve()
        if not profile.is_dir():
            raise FileNotFoundError(f"No existe el perfil de Firefox: {profile}")
        return profile

    configured = os.environ.get("X_FIREFOX_PROFILE")
    if configured:
        return discover_firefox_profile(Path(configured))

    candidates = [
        # macOS, Linux y Windows (APPDATA es el que usa el instalador oficial).
        Path.home() / "Library/Application Support/Firefox/profiles.ini",
        Path.home() / ".mozilla/firefox/profiles.ini",
        Path.home() / "snap/firefox/common/.mozilla/firefox/profiles.ini",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Mozilla/Firefox/profiles.ini")
    candidates.append(Path.home() / "AppData/Roaming/Mozilla/Firefox/profiles.ini")
    ini_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if not ini_path:
        return None
    return choose_profile_from_ini(ini_path)


def profile_has_x_session(profile: Path, now: float | None = None) -> bool:
    """Indica si el perfil guarda una sesión vigente de X (cookie ``auth_token``).

    Abre ``cookies.sqlite`` en modo inmutable: no escribe nada en el perfil y
    funciona aunque Firefox lo tenga abierto. A cambio no ve lo que Firefox aún
    no haya volcado al archivo, así que una sesión iniciada hace segundos puede
    no aparecer hasta cerrar el navegador.
    """

    cookies = profile / "cookies.sqlite"
    if not cookies.is_file():
        return False
    now = time.time() if now is None else now
    uri = f"file:{quote(cookies.resolve().as_posix())}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            rows = connection.execute(
                "SELECT expiry FROM moz_cookies WHERE name = 'auth_token' AND ("
                "host = 'x.com' OR host LIKE '%.x.com' "
                "OR host = 'twitter.com' OR host LIKE '%.twitter.com')"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return False

    for (expiry,) in rows:
        try:
            expiry = float(expiry)
        except (TypeError, ValueError):
            continue
        if expiry > 1e11:  # Firefox reciente guarda milisegundos
            expiry /= 1000
        if expiry > now:
            return True
    return False


def choose_profile_from_ini(ini_path: Path) -> Path | None:
    """Elige el perfil a usar cuando no se indicó ninguno.

    El orden importa, porque un perfil equivocado no da error: X pide iniciar
    sesión y la descarga sale vacía.

    1. Un perfil con sesión de X. Si hay varios, el de cookies más recientes.
    2. El que la instalación de Firefox usa de verdad (secciones ``[Install…]``).
    3. El marcado ``Default=1``, que en instalaciones modernas suele ser un
       perfil antiguo y vacío llamado ``default``, no el de uso diario.
    4. El primero que exista.
    """

    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")
    base = ini_path.parent

    def resolve(raw: str, relative: bool = True) -> Path | None:
        raw = raw.strip()
        if not raw:
            return None
        path = Path(raw)
        if relative and not path.is_absolute():
            path = base / path
        path = path.expanduser().resolve()
        return path if path.is_dir() else None

    listed: list[Path] = []
    legacy_default: Path | None = None
    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        path = resolve(
            parser.get(section, "Path", fallback=""),
            parser.getboolean(section, "IsRelative", fallback=True),
        )
        if path is None or path in listed:
            continue
        listed.append(path)
        if legacy_default is None and parser.getboolean(section, "Default", fallback=False):
            legacy_default = path

    # Perfiles que existen en disco aunque profiles.ini no los nombre.
    profiles_directory = base / "Profiles"
    if profiles_directory.is_dir():
        for path in sorted(profiles_directory.iterdir()):
            path = path.resolve()
            if path.is_dir() and path not in listed and (path / "cookies.sqlite").is_file():
                listed.append(path)

    with_session = [path for path in listed if profile_has_x_session(path)]
    if with_session:
        with_session.sort(key=lambda path: (path / "cookies.sqlite").stat().st_mtime, reverse=True)
        if len(with_session) > 1:
            logging.warning(
                "Hay %d perfiles de Firefox con sesión de X; se usa %s. "
                "Para elegir otro, usa --profile o X_FIREFOX_PROFILE.",
                len(with_session),
                with_session[0].name,
            )
        return with_session[0]

    for section in parser.sections():
        if section.startswith("Install"):
            path = resolve(parser.get(section, "Default", fallback=""))
            if path is not None:
                return path
    if legacy_default is not None:
        return legacy_default
    return listed[0] if listed else None


def resolve_driver_path(explicit: Path | None = None) -> Path | None:
    configured = explicit or (Path(os.environ["GECKODRIVER"]) if os.environ.get("GECKODRIVER") else None)
    if configured:
        driver_path = configured.expanduser().resolve()
        if not driver_path.is_file():
            raise FileNotFoundError(f"No existe geckodriver: {driver_path}")
        return driver_path
    for name in LOCAL_GECKODRIVER_NAMES:
        candidate = SCRIPT_DIR / name
        if candidate.is_file():
            return candidate
    return None


def create_driver(
    profile_path: Path | None,
    driver_path: Path | None,
    headless: bool,
    timeout: float,
) -> Any:
    try:
        from selenium import webdriver
        from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service as FirefoxService
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Falta Selenium en este Python ({sys.executable}). Instálalo con: "
            "python -m pip install -r requirements.txt, o ejecuta el programa "
            "con el Python del entorno virtual donde ya está instalado."
        ) from exc

    options = Options()
    if profile_path:
        options.profile = FirefoxProfile(str(profile_path))
    if headless:
        options.add_argument("--headless")
    options.set_preference("intl.accept_languages", "es-CO,es,es-419,es-ES")
    options.set_preference("intl.locale.requested", "es-CO")

    kwargs: dict[str, Any] = {"options": options}
    if driver_path:
        kwargs["service"] = FirefoxService(executable_path=str(driver_path))

    driver = webdriver.Firefox(**kwargs)
    driver.set_window_size(1920, 1080)
    driver.set_page_load_timeout(timeout)
    return driver


def own_elements(article: Any, selector: str) -> list[Any]:
    """Elementos del artículo que no pertenecen a otro artículo anidado dentro."""

    return article.parent.execute_script(OWN_ELEMENTS_JS, article, selector)


def article_kind(article: Any) -> str:
    """Clasifica un artículo: "post", "repost", "quote" o "wrapper".

    Desde 2026 X anida artículos. Un repost es un envoltorio ("Fulano
    reposteó") sin enlace propio que contiene la publicación; una cita es un
    artículo dentro del de quien cita, recortado y sin contadores. Los
    envoltorios y las citas no se leen: los primeros no son publicaciones y las
    segundas son datos a medias.
    """

    return article.parent.execute_script(ARTICLE_KIND_JS, article)


def is_readable_post(article: Any) -> bool:
    return article_kind(article) in ("post", "repost")


def snowflake_to_iso(tweet_id: str) -> str:
    """Fecha de publicación a partir del identificador, en UTC.

    Desde noviembre de 2010 los identificadores de X llevan en sus primeros
    bits los milisegundos transcurridos desde SNOWFLAKE_EPOCH_MS. Es la única
    fuente exacta desde que X quitó el elemento <time> de los resultados.
    """

    numeric_id = int(tweet_id)
    if numeric_id < FIRST_SNOWFLAKE_ID:
        raise ValueError(f"El identificador {tweet_id} es anterior a 2010-11 y no contiene fecha.")
    published = datetime.fromtimestamp(
        ((numeric_id >> 22) + SNOWFLAKE_EPOCH_MS) / 1000,
        timezone.utc,
    )
    return published.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def visible_status_ids(driver: Any) -> set[str]:
    from selenium.common.exceptions import StaleElementReferenceException

    ids: set[str] = set()
    for article in driver.find_elements("css selector", TWEET_SELECTOR):
        try:
            if not is_readable_post(article):
                continue
            _, tweet_id, _ = identity_from_article(article)
            ids.add(tweet_id)
        except (ValueError, StaleElementReferenceException):
            continue
    return ids


def identity_from_article(article: Any) -> tuple[str, str, str]:
    for href in article.parent.execute_script(OWN_STATUS_HREFS_JS, article):
        try:
            return extract_status_identity(href or "")
        except ValueError:
            continue
    raise ValueError("El artículo no contiene una URL /status/ propia.")


def find_article_by_id(driver: Any, tweet_id: str) -> Any | None:
    from selenium.common.exceptions import StaleElementReferenceException

    for article in driver.find_elements("css selector", TWEET_SELECTOR):
        try:
            if not is_readable_post(article):
                continue
            _, candidate_id, _ = identity_from_article(article)
            if candidate_id == tweet_id:
                return article
        except (ValueError, StaleElementReferenceException):
            continue
    return None


def labeled_controls(article: Any, labels: Iterable[str]) -> list[Any]:
    """Botones propios del artículo cuyo rótulo es uno de ``labels``."""

    return article.parent.execute_script(LABELED_CONTROLS_JS, article, list(labels))


def text_snapshot(article: Any) -> list[str]:
    return [
        element.get_attribute("textContent") or ""
        for element in article.parent.execute_script(TEXT_ELEMENTS_JS, article)
    ]


def click_original_text_if_present(driver: Any, article: Any, tweet_id: str) -> Any:
    from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
    from selenium.webdriver.support.ui import WebDriverWait

    controls = labeled_controls(article, SHOW_ORIGINAL_LABELS)
    if not controls:
        return article

    before = text_snapshot(article)
    driver.execute_script("arguments[0].click();", controls[0])

    def text_changed(current_driver: Any) -> bool:
        current_article = find_article_by_id(current_driver, tweet_id)
        if current_article is None:
            return False
        try:
            return text_snapshot(current_article) != before
        except StaleElementReferenceException:
            return False

    try:
        WebDriverWait(driver, 3).until(text_changed)
    except TimeoutException:
        logging.debug("La traducción de %s no reportó cambio de texto.", tweet_id)

    return find_article_by_id(driver, tweet_id) or article


def expand_long_text(driver: Any, article: Any) -> None:
    """Pulsa "Mostrar más" para que el artículo muestre la publicación completa.

    X recorta en la cronología las publicaciones largas y deja el resto fuera del
    DOM, así que sin este clic el texto se guarda truncado. El botón se busca por
    su rótulo y sólo entre los propios del artículo, para no confundirlo con
    "Mostrar esta cadena" ni abrir el texto de una cita.
    """

    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        controls = labeled_controls(article, SHOW_MORE_LABELS)
        if not controls:
            return
        for control in controls:
            driver.execute_script("arguments[0].click();", control)
        WebDriverWait(driver, 2, poll_frequency=0.1).until(
            lambda _: not labeled_controls(article, SHOW_MORE_LABELS)
        )
    except TimeoutException:
        logging.debug("El botón de texto largo no desapareció tras el clic.")
    except WebDriverException:
        logging.debug("No se pudo expandir el texto largo.", exc_info=True)


def extract_text(article: Any, driver: Any) -> str:
    expand_long_text(driver, article)

    for element in driver.execute_script(TEXT_ELEMENTS_JS, article):
        text = driver.execute_script(READ_TEXT_JS, element, list(SHOW_MORE_LABELS))
        if text and text.strip():
            return text.strip()
    return ""


def extract_real_name(article: Any, username: str) -> str:
    name = article.parent.execute_script(REAL_NAME_JS, article, username)
    return (name or "").strip() or "desconocido"


def extract_favorites(article: Any) -> tuple[str, int | None]:
    buttons = own_elements(article, LIKE_BUTTON_SELECTOR)
    if not buttons:
        return "", None

    label = (buttons[0].get_attribute("aria-label") or "").strip()
    raw = buttons[0].text.strip() or label
    # La etiqueta de accesibilidad trae el número exacto ("1959 Me gustan");
    # lo visible viene abreviado ("1 mil").
    exact = LIKE_LABEL_RE.match(label)
    if exact:
        return raw, int(re.sub(r"\D", "", exact.group(1)))
    return raw, parse_compact_number(raw)


def extract_published_at(article: Any, tweet_id: str) -> str:
    """Fecha ISO en UTC: la del elemento <time> si X lo sirve, si no la del id."""

    for time_element in own_elements(article, "time"):
        published_at = (time_element.get_attribute("datetime") or "").strip()
        if published_at:
            return published_at
    return snowflake_to_iso(tweet_id)


def extract_tweet_record(
    driver: Any,
    article: Any,
    query: str,
    constraints: QueryConstraints,
    match_terms: tuple[str, ...] = (),
) -> TweetRecord | None:
    username, tweet_id, canonical_url = identity_from_article(article)
    if constraints.accounts and username.casefold() not in constraints.accounts:
        logging.debug("Se omite %s: cuenta fuera de la consulta.", canonical_url)
        return None

    published_at = extract_published_at(article, tweet_id)
    if not timestamp_matches(published_at, constraints):
        logging.debug("Se omite %s: fecha fuera del intervalo.", canonical_url)
        return None

    article = click_original_text_if_present(driver, article, tweet_id)
    text = extract_text(article, driver)
    if not text:
        raise ValueError(f"La publicación {tweet_id} no contiene texto extraíble.")
    matched_terms = find_matching_terms(text, match_terms)
    if match_terms and not matched_terms:
        logging.debug("Se omite %s: no contiene los términos requeridos.", canonical_url)
        return None

    favorites_raw, favorites = extract_favorites(article)
    return TweetRecord(
        username=username,
        real_name=extract_real_name(article, username),
        date=published_at,
        text=text,
        matched_terms="|".join(matched_terms),
        favorites_raw=favorites_raw,
        favorites=favorites,
        tweet_id=tweet_id,
        url=canonical_url,
        scraped_at=utc_now_iso(),
        source_query=query,
    )


def page_state(driver: Any) -> str | bool:
    from selenium.webdriver.common.by import By

    current_url = driver.current_url.casefold()
    login_markers = ("/i/flow/login", "/i/jf/onboarding", "redirect_after_login", "mode=login")
    if (
        any(marker in current_url for marker in login_markers)
        or driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="username"]')
        or driver.get_cookie("auth_token") is None
    ):
        return "login"
    if driver.find_elements(By.CSS_SELECTOR, TWEET_SELECTOR):
        return "results"

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.casefold()
    except Exception:
        return False

    empty_markers = (
        "no results for",
        "no hay resultados para",
        "try searching for something else",
        "intenta buscar otra cosa",
    )
    error_markers = (
        "something went wrong",
        "algo salió mal",
        "rate limit exceeded",
        "límite de frecuencia",
    )
    if any(marker in body_text for marker in empty_markers):
        return "empty"
    if any(marker in body_text for marker in error_markers):
        return "error"
    return False


def wait_for_initial_state(driver: Any, timeout: float) -> str:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        return WebDriverWait(driver, timeout).until(page_state)
    except TimeoutException as exc:
        raise RuntimeError(
            "X no mostró resultados, estado vacío ni formulario de acceso dentro "
            f"de {timeout:g} segundos. URL final: {driver.current_url}"
        ) from exc


def scroll_and_wait_for_new_ids(
    driver: Any,
    known_ids: set[str],
    timeout: float,
    min_pause: float,
    max_pause: float,
) -> bool:
    from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
    from selenium.webdriver.support.ui import WebDriverWait

    articles = driver.find_elements("css selector", TWEET_SELECTOR)
    try:
        if articles:
            driver.execute_script(
                'arguments[0].scrollIntoView({block: "end"});',
                articles[-1],
            )
            driver.execute_script("window.scrollBy(0, 700);")
        else:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    except StaleElementReferenceException:
        driver.execute_script("window.scrollBy(0, 900);")

    time.sleep(random.uniform(min_pause, max_pause))
    try:
        WebDriverWait(driver, min(timeout, 5)).until(
            lambda current_driver: bool(visible_status_ids(current_driver) - known_ids)
        )
        return True
    except TimeoutException:
        return False


def record_from_legacy_row(
    row: dict[str, str],
    query: str,
    match_terms: tuple[str, ...] = (),
) -> TweetRecord | None:
    try:
        username, tweet_id, canonical_url = extract_status_identity(row.get("url", ""))
    except ValueError:
        return None

    raw_favorites = row.get("favorites_raw", "") or row.get("favorites", "")
    numeric_favorites = parse_compact_number(row.get("favorites", ""))
    if numeric_favorites is None:
        numeric_favorites = parse_compact_number(raw_favorites)
    return TweetRecord(
        username=row.get("username", "") or username,
        real_name=row.get("real_name", "") or "desconocido",
        date=row.get("date", ""),
        text=row.get("text", ""),
        matched_terms=row.get("matched_terms", "")
        or "|".join(find_matching_terms(row.get("text", ""), match_terms)),
        favorites_raw=raw_favorites,
        favorites=numeric_favorites,
        tweet_id=row.get("tweet_id", "") or tweet_id,
        url=canonical_url,
        scraped_at=row.get("scraped_at", "") or utc_now_iso(),
        source_query=row.get("source_query", "") or query,
    )


def load_existing_records(
    path: Path,
    query: str,
    match_terms: tuple[str, ...] = (),
) -> dict[str, TweetRecord]:
    if not path.is_file():
        return {}

    records: dict[str, TweetRecord] = {}
    skipped_queries: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            row_query = (row.get("source_query") or "").strip()
            if row_query and row_query != query:
                skipped_queries[row_query] += 1
                continue
            record = record_from_legacy_row(row, query, match_terms)
            if record:
                records[record.tweet_id] = record

    if skipped_queries:
        logging.warning(
            "Se omitieron %d filas pertenecientes a otras consultas. Usa otro --output para conservarlas.",
            sum(skipped_queries.values()),
        )
    return records


def save_records_atomic(records: Iterable[TweetRecord], path: Path) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda record: (record.date, record.tweet_id), reverse=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=CSV_FIELDS,
                delimiter=";",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(record.as_row() for record in ordered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def scrape(
    driver: Any,
    query: str,
    match_terms: tuple[str, ...],
    records: dict[str, TweetRecord],
    max_scrolls: int,
    no_new_limit: int,
    checkpoint_every: int,
    timeout: float,
    min_pause: float,
    max_pause: float,
    output: Path,
) -> Counter[str]:
    from selenium.common.exceptions import (
        NoSuchElementException,
        StaleElementReferenceException,
        WebDriverException,
    )

    constraints = parse_query_constraints(query)
    stats: Counter[str] = Counter()
    seen_page_ids: set[str] = set()
    completed_ids: set[str] = set()
    failures: Counter[str] = Counter()

    search_url = build_search_url(query)
    logging.info("Abriendo búsqueda: %s", search_url)
    driver.get(search_url)
    state = wait_for_initial_state(driver, timeout)
    if state == "login":
        raise RuntimeError(
            "X solicita iniciar sesión. Ejecuta con un perfil autenticado mediante --profile "
            "o configura X_FIREFOX_PROFILE."
        )
    if state == "error":
        raise RuntimeError("X mostró un error o un límite de frecuencia antes de cargar resultados.")
    if state == "empty":
        logging.info("La búsqueda no devolvió resultados.")
        return stats

    no_new_rounds = 0
    for scroll_number in range(1, max_scrolls + 1):
        articles = driver.find_elements("css selector", TWEET_SELECTOR)
        discovered_this_round = 0
        saved_this_round = 0

        for article in articles:
            try:
                if not is_readable_post(article):
                    continue
                _, tweet_id, _ = identity_from_article(article)
            except (ValueError, StaleElementReferenceException):
                failures["identity"] += 1
                continue

            if tweet_id not in seen_page_ids:
                seen_page_ids.add(tweet_id)
                discovered_this_round += 1
            if tweet_id in completed_ids:
                continue

            try:
                record = extract_tweet_record(
                    driver,
                    article,
                    query,
                    constraints,
                    match_terms,
                )
                completed_ids.add(tweet_id)
                if record is None:
                    stats["filtered"] += 1
                    continue

                previo = records.get(tweet_id)
                record = keep_longest_text(previo, record)
                records[tweet_id] = record
                stats["updated" if previo is not None else "new"] += 1
                saved_this_round += 1
                logging.info(
                    "@%s | %s | %s…",
                    record.username,
                    record.date[:10],
                    record.text[:70].replace("\n", " "),
                )
            except (NoSuchElementException, StaleElementReferenceException, ValueError) as exc:
                failures[type(exc).__name__] += 1
                logging.debug("No se pudo procesar %s: %s", tweet_id, exc)
            except WebDriverException as exc:
                failures[type(exc).__name__] += 1
                logging.warning("Fallo de WebDriver en %s: %s", tweet_id, exc.msg)

        if discovered_this_round:
            no_new_rounds = 0
        else:
            no_new_rounds += 1

        logging.info(
            "Scroll %d/%d | visibles=%d | IDs nuevos=%d | guardados=%d | total=%d | sin nuevos=%d/%d",
            scroll_number,
            max_scrolls,
            len(articles),
            discovered_this_round,
            saved_this_round,
            len(records),
            no_new_rounds,
            no_new_limit,
        )

        if scroll_number % checkpoint_every == 0 or saved_this_round:
            save_records_atomic(records.values(), output)

        if no_new_rounds >= no_new_limit:
            logging.info("Fin: %d rondas consecutivas sin IDs nuevos.", no_new_limit)
            stats["stopped_no_new"] += 1
            break

        found_after_scroll = scroll_and_wait_for_new_ids(
            driver,
            seen_page_ids,
            timeout,
            min_pause,
            max_pause,
        )
        if not found_after_scroll:
            logging.debug("El scroll no produjo IDs nuevos dentro del tiempo de espera.")
    else:
        logging.info("Fin: se alcanzó MAX_SCROLLS=%d.", max_scrolls)
        stats["stopped_max_scrolls"] += 1

    stats["seen_page_ids"] = len(seen_page_ids)
    stats["errors"] = sum(failures.values())
    if failures:
        logging.warning("Errores recuperables: %s", dict(failures))
    return stats


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Debe ser un entero mayor que cero.")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("Debe ser un número mayor o igual que cero.")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrae publicaciones de la búsqueda reciente de X y guarda checkpoints en CSV.",
    )
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Consulta completa de X.")
    parser.add_argument(
        "--match",
        action="append",
        default=[],
        help="Conserva únicamente textos que contengan este término; puede repetirse.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV de salida.")
    parser.add_argument("--profile", type=Path, help="Perfil autenticado de Firefox.")
    parser.add_argument("--driver", type=Path, help="Ruta opcional a geckodriver.")
    parser.add_argument("--max-scrolls", type=positive_int, default=100)
    parser.add_argument("--no-new-limit", type=positive_int, default=5)
    parser.add_argument("--checkpoint-every", type=positive_int, default=5)
    parser.add_argument("--timeout", type=nonnegative_float, default=25.0)
    parser.add_argument("--min-pause", type=nonnegative_float, default=1.5)
    parser.add_argument("--max-pause", type=nonnegative_float, default=3.0)
    parser.add_argument("--headed", action="store_true", help="Muestra la ventana de Firefox.")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignora el CSV existente en vez de reanudarlo.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Archivo de log; por defecto usa el mismo nombre del CSV con extensión .log.",
    )
    return parser.parse_args(argv)


def configure_logging(log_file: Path) -> None:
    log_file = log_file.expanduser().resolve()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.expanduser().resolve()
    log_file = (args.log_file or output.with_suffix(".log")).expanduser().resolve()
    configure_logging(log_file)

    if args.min_pause > args.max_pause:
        logging.error("--min-pause no puede ser mayor que --max-pause.")
        return 2

    try:
        constraints = parse_query_constraints(args.query)
        profile_path = discover_firefox_profile(args.profile)
        driver_path = resolve_driver_path(args.driver)
    except (FileNotFoundError, ValueError) as exc:
        logging.error("Configuración inválida: %s", exc)
        return 2

    match_terms = tuple(dict.fromkeys(term.strip() for term in args.match if term.strip()))
    records = (
        {}
        if args.fresh
        else load_existing_records(output, args.query, match_terms)
    )
    initial_records = {
        tweet_id: record.as_row()
        for tweet_id, record in records.items()
    }
    logging.info("Consulta: %s", args.query)
    logging.info("Cuentas esperadas: %s", sorted(constraints.accounts) or "sin filtro local")
    logging.info("Términos obligatorios: %s", match_terms or "sin filtro textual local")
    logging.info("Registros recuperados del CSV: %d", len(records))
    logging.info("Perfil Firefox: %s", profile_path or "perfil limpio")
    logging.info("Geckodriver: %s", driver_path or "Selenium Manager")

    driver = None
    exit_code = 0
    scrape_completed = False
    try:
        driver = create_driver(
            profile_path=profile_path,
            driver_path=driver_path,
            headless=not args.headed,
            timeout=args.timeout,
        )
        stats = scrape(
            driver=driver,
            query=args.query,
            match_terms=match_terms,
            records=records,
            max_scrolls=args.max_scrolls,
            no_new_limit=args.no_new_limit,
            checkpoint_every=args.checkpoint_every,
            timeout=args.timeout,
            min_pause=args.min_pause,
            max_pause=args.max_pause,
            output=output,
        )
        scrape_completed = True
        logging.info("Resumen: %s", dict(stats))
    except KeyboardInterrupt:
        exit_code = 130
        logging.warning("Ejecución interrumpida; se guardará el progreso obtenido.")
    except Exception:
        exit_code = 1
        logging.exception("La extracción terminó con un error; se conservará cualquier progreso obtenido.")
    finally:
        records_changed = initial_records != {
            tweet_id: record.as_row()
            for tweet_id, record in records.items()
        }
        if scrape_completed or records_changed:
            try:
                save_records_atomic(records.values(), output)
                logging.info("%d publicaciones guardadas en %s", len(records), output)
            except Exception:
                exit_code = exit_code or 1
                logging.exception("No fue posible guardar el CSV final.")
        else:
            logging.info("No hubo datos nuevos; el CSV existente no fue modificado.")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                logging.warning("Firefox no pudo cerrarse limpiamente.", exc_info=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
