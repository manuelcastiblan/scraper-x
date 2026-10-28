import tempfile
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
    TweetRecord,
    build_search_url,
    extract_status_identity,
    find_matching_terms,
    load_existing_records,
    main,
    parse_compact_number,
    parse_query_constraints,
    save_records_atomic,
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


if __name__ == "__main__":
    unittest.main()
