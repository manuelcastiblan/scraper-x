import sqlite3
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from descargar_busqueda import (
    daily_query,
    earliest_record_day,
    range_query,
    search_expression,
)

# Términos de ejemplo: ahora se pasan por --term en vez de estar en el código.
TERMS = ("Prioridad Nacional", "#PrioridadNacional", "Primero la patria")
SEARCH_EXPRESSION = search_expression(TERMS)
from scraper_x import (
    keep_longest_text,
    DEFAULT_QUERY,
    LIKE_LABEL_RE,
    TweetRecord,
    build_search_url,
    choose_profile_from_ini,
    extract_status_identity,
    find_matching_terms,
    load_existing_records,
    main,
    parse_compact_number,
    parse_query_constraints,
    profile_has_x_session,
    save_records_atomic,
    snowflake_to_iso,
    timestamp_matches,
)


class ScraperUtilitiesTest(unittest.TestCase):
    def test_global_priority_query_has_no_candidate_filter(self):
        query = daily_query(date(2026, 3, 1), SEARCH_EXPRESSION)

        # Una búsqueda temática recorre todas las cuentas: no debe filtrar por autor.
        self.assertNotIn("from:", query.casefold())
        self.assertTrue(query.startswith(SEARCH_EXPRESSION))
        self.assertIn("since:2026-03-01_00:00:00_UTC", query)
        self.assertIn("until:2026-03-02_00:00:00_UTC", query)

    def test_search_expression_quotes_phrases_only(self) -> None:
        self.assertEqual(
            search_expression(("Prioridad Nacional", "#Hashtag", "palabra")),
            '("Prioridad Nacional" OR #Hashtag OR palabra)',
        )
        self.assertEqual(search_expression(("#Solo",)), "#Solo")
        with self.assertRaises(ValueError):
            search_expression(())

    def test_range_query_uses_exclusive_end_date(self):
        query = range_query(date(2026, 3, 25), date(2026, 3, 28), SEARCH_EXPRESSION)

        self.assertIn("since:2026-03-25_00:00:00_UTC", query)
        self.assertIn("until:2026-03-28_00:00:00_UTC", query)
        with self.assertRaises(ValueError):
            range_query(date(2026, 3, 28), date(2026, 3, 28), SEARCH_EXPRESSION)

    def test_earliest_record_day_detects_truncated_batch(self):
        records = [
            SimpleNamespace(date="2026-04-23T18:00:00.000Z"),
            SimpleNamespace(date="fecha-invalida"),
        ]

        self.assertEqual(
            earliest_record_day(records, date(2026, 4, 21), date(2026, 4, 24)),
            date(2026, 4, 23),
        )

    def test_build_search_url_encodes_query_without_duplicate_parameters(self):
        url = build_search_url(DEFAULT_QUERY)
        params = parse_qs(urlsplit(url).query)

        self.assertEqual(params["q"], [DEFAULT_QUERY])
        self.assertEqual(params["f"], ["live"])
        self.assertEqual(params["lang"], ["es"])

    def test_extract_status_identity_normalizes_url(self):
        username, tweet_id, url = extract_status_identity(
            "https://twitter.com/IvanCepedaCast/status/123456/photo/1?ref_src=test"
        )

        self.assertEqual(username, "IvanCepedaCast")
        self.assertEqual(tweet_id, "123456")
        self.assertEqual(url, "https://x.com/IvanCepedaCast/status/123456")

    def test_extract_status_identity_accepts_relative_href(self):
        # La interfaz de 2026 entrega los enlaces sin dominio.
        username, tweet_id, url = extract_status_identity(
            "/DCoronell/status/2119859987014942926/analytics"
        )

        self.assertEqual(username, "DCoronell")
        self.assertEqual(tweet_id, "2119859987014942926")
        self.assertEqual(url, "https://x.com/DCoronell/status/2119859987014942926")

    def test_snowflake_to_iso_reads_date_from_identifier(self):
        # Sin <time> en la página, la fecha sale del identificador.
        self.assertEqual(
            snowflake_to_iso("2119859987014942926"),
            "2026-11-09T18:29:40.655Z",
        )
        self.assertTrue(
            timestamp_matches(
                snowflake_to_iso("2119859987014942926"),
                parse_query_constraints("since:2026-11-09 until:2026-11-10"),
            )
        )
        # Los identificadores anteriores a noviembre de 2010 no llevan fecha.
        with self.assertRaises(ValueError):
            snowflake_to_iso("123456")

    def test_like_label_gives_exact_count(self):
        examples = {
            "1959 Me gustan. Gustar": "1959",
            "1 Me gusta. Gustar": "1",
            "36.860 Me gustan. Gustar": "36.860",
            "1,959 Likes. Like": "1,959",
        }
        for label, expected in examples.items():
            with self.subTest(label=label):
                self.assertEqual(LIKE_LABEL_RE.match(label).group(1), expected)
        # Sin número, o abreviado, se usa el texto visible del botón.
        self.assertIsNone(LIKE_LABEL_RE.match("Me gusta"))
        self.assertIsNone(LIKE_LABEL_RE.match("1,2 mil Me gustan"))

    def test_parse_compact_number(self):
        examples = {
            "10K": 10_000,
            "2.1K": 2_100,
            "2,1 mil": 2_100,
            "1,234 Likes": 1_234,
            "1.234 Me gusta": 1_234,
            "0": 0,
            "": None,
        }
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_compact_number(raw), expected)

    def test_query_constraints_are_case_insensitive_and_until_is_exclusive(self):
        constraints = parse_query_constraints(DEFAULT_QUERY)

        self.assertEqual(
            constraints.accounts,
            frozenset({"ivancepedacast", "abdelaespriella"}),
        )
        self.assertTrue(timestamp_matches("2026-06-21T23:59:59.000Z", constraints))
        self.assertFalse(timestamp_matches("2026-06-22T00:00:00.000Z", constraints))

    def test_query_constraints_accept_explicit_utc_times(self):
        constraints = parse_query_constraints(
            "tema since:2026-06-02_00:00:00_UTC until:2026-06-03_00:00:00_UTC"
        )

        self.assertTrue(timestamp_matches("2026-06-02T23:59:59.999Z", constraints))
        self.assertFalse(timestamp_matches("2026-06-03T00:00:00.000Z", constraints))

    def test_csv_round_trip_and_legacy_resume(self):
        record = TweetRecord(
            username="IvanCepedaCast",
            real_name="Iván Cepeda",
            date="2026-06-01T12:00:00.000Z",
            text="Texto con\nsegunda línea",
            matched_terms="",
            favorites_raw="2.1K",
            favorites=2100,
            tweet_id="123456",
            url="https://x.com/IvanCepedaCast/status/123456",
            scraped_at="2026-08-16T00:00:00Z",
            source_query=DEFAULT_QUERY,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resultado.csv"
            save_records_atomic([record], path)
            loaded = load_existing_records(path, DEFAULT_QUERY)

        self.assertEqual(set(loaded), {"123456"})
        self.assertEqual(loaded["123456"].text, "Texto con\nsegunda línea")
        self.assertEqual(loaded["123456"].favorites, 2100)

    def test_legacy_row_uses_raw_favorites_when_numeric_column_is_empty(self):
        record = TweetRecord(
            username="ABDELAESPRIELLA",
            real_name="Abelardo De La Espriella",
            date="2026-06-02T12:00:00.000Z",
            text="Texto",
            matched_terms="",
            favorites_raw="3.4K",
            favorites=None,
            tweet_id="789",
            url="https://x.com/ABDELAESPRIELLA/status/789",
            scraped_at="2026-08-16T00:00:00Z",
            source_query=DEFAULT_QUERY,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resultado.csv"
            save_records_atomic([record], path)
            loaded = load_existing_records(path, DEFAULT_QUERY)

        self.assertEqual(loaded["789"].favorites, 3400)

    def test_find_matching_terms_is_case_insensitive(self):
        terms = ("Prioridad Nacional", "#PrioridadNacional", "Primero la patria")

        self.assertEqual(
            find_matching_terms("La PRIORIDAD NACIONAL es el tema", terms),
            ["Prioridad Nacional"],
        )
        self.assertEqual(
            find_matching_terms("Mensaje #prioridadnacional", terms),
            ["#PrioridadNacional"],
        )

    def test_driver_start_failure_does_not_create_or_overwrite_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "resultado.csv"
            with (
                patch("scraper_x.configure_logging"),
                patch("scraper_x.create_driver", side_effect=RuntimeError("fallo")),
                patch("scraper_x.logging.exception"),
            ):
                exit_code = main(["--output", str(output), "--fresh"])

            self.assertEqual(exit_code, 1)
            self.assertFalse(output.exists())


    def test_keep_longest_text_protects_recovered_text(self) -> None:
        def registro(texto: str) -> TweetRecord:
            return TweetRecord("u", "U", "2024-01-01T00:00:00Z", texto, "", "1", 1, "1",
                               "https://x.com/u/status/1", "2026-09-18T00:00:00Z", "from:u")

        largo, corto = "texto completo y largo", "texto completo"
        # Un repaso que vuelve a recortar no debe borrar el texto ya recuperado.
        self.assertEqual(keep_longest_text(registro(largo), registro(corto)).text, largo)
        # Un repaso que recupera más texto sí reemplaza al guardado.
        self.assertEqual(keep_longest_text(registro(corto), registro(largo)).text, largo)
        # Sin registro previo se conserva lo leído.
        self.assertEqual(keep_longest_text(None, registro(corto)).text, corto)


class FirefoxProfileDiscoveryTest(unittest.TestCase):
    """Sin perfil declarado, se elige el que tiene sesión de X."""

    def crear(self, base: Path, nombre: str, expira: float | None = None) -> Path:
        perfil = base / "Profiles" / nombre
        perfil.mkdir(parents=True)
        conexion = sqlite3.connect(perfil / "cookies.sqlite")
        conexion.execute("CREATE TABLE moz_cookies (name TEXT, host TEXT, expiry INTEGER)")
        if expira is not None:
            conexion.execute(
                "INSERT INTO moz_cookies VALUES ('auth_token', '.x.com', ?)", (expira,)
            )
        conexion.commit()
        conexion.close()
        return perfil.resolve()

    def indice(self, base: Path, extra: str = "") -> Path:
        ruta = base / "profiles.ini"
        ruta.write_text(
            "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/aaaa.default\nDefault=1\n\n"
            "[Profile1]\nName=default-release\nIsRelative=1\nPath=Profiles/bbbb.default-release\n\n"
            "[Profile2]\nName=scraper\nIsRelative=1\nPath=Profiles/cccc.scraper\n\n" + extra,
            encoding="utf-8",
        )
        return ruta

    def test_profile_with_x_session_wins_over_default_flag(self):
        with tempfile.TemporaryDirectory() as carpeta:
            # La ruta lleva un espacio, como "Application Support" en macOS.
            base = Path(carpeta) / "Application Support" / "Firefox"
            self.crear(base, "aaaa.default")
            self.crear(base, "bbbb.default-release")
            con_sesion = self.crear(base, "cccc.scraper", expira=time.time() + 3600)

            self.assertTrue(profile_has_x_session(con_sesion))
            self.assertEqual(choose_profile_from_ini(self.indice(base)), con_sesion)

    def test_expired_session_does_not_count(self):
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            self.crear(base, "aaaa.default")
            en_uso = self.crear(base, "bbbb.default-release")
            vencido = self.crear(base, "cccc.scraper", expira=time.time() - 3600)
            # Firefox reciente guarda el vencimiento en milisegundos.
            en_ms = self.crear(base, "dddd.otro", expira=(time.time() + 3600) * 1000)

            self.assertFalse(profile_has_x_session(vencido))
            self.assertTrue(profile_has_x_session(en_ms))
            self.assertFalse(profile_has_x_session(base / "no-existe"))
            # dddd.otro no figura en profiles.ini, pero existe y tiene sesión.
            self.assertEqual(choose_profile_from_ini(self.indice(base)), en_ms)
            self.assertNotEqual(en_uso, en_ms)

    def test_without_session_prefers_install_default_over_legacy_flag(self):
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            legado = self.crear(base, "aaaa.default")
            en_uso = self.crear(base, "bbbb.default-release")
            self.crear(base, "cccc.scraper")

            instalacion = "[InstallABCDEF]\nDefault=Profiles/bbbb.default-release\nLocked=1\n"
            self.assertEqual(choose_profile_from_ini(self.indice(base, instalacion)), en_uso)
            # Sin sección [Install…] queda la marca antigua Default=1.
            self.assertEqual(choose_profile_from_ini(self.indice(base)), legado)


if __name__ == "__main__":
    unittest.main()
