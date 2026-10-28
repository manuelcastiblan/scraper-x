from __future__ import annotations

import csv
import tempfile
import unittest
from collections import Counter
from datetime import timedelta
from pathlib import Path

from descargar_cuentas import (
        Account,
    Batch,
    account_query,
    batch_paths,
    expand_split_batches,
    filter_accounts,
    load_roster,
    merge_parts,
    monthly_windows,
    parse_aware_datetime,
    split_batch,
    truncation_boundary,
)
from scraper_x import TweetRecord, save_records_atomic


class RosterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope, cls.accounts = load_roster(Path("ejemplo_pacto_historico.json"))

    def test_historical_roster_counts_and_uniqueness(self) -> None:
        counts = Counter(account.corporation for account in self.accounts)
        self.assertEqual(len(self.accounts), 54)
        self.assertEqual(counts["Cámara de Representantes"], 29)
        self.assertEqual(counts["Senado de la República"], 25)
        self.assertEqual(len({account.id for account in self.accounts}), 54)
        self.assertEqual(len({account.x_handle.casefold() for account in self.accounts}), 54)

    def test_constitutional_period_has_49_monthly_windows(self) -> None:
        start = parse_aware_datetime(self.scope["scrape_start_local"])
        end = parse_aware_datetime(self.scope["scrape_end_local_exclusive"])
        windows = monthly_windows(start, end)
        self.assertEqual(len(windows), 49)
        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[0][1].isoformat(), "2022-08-01T00:00:00-05:00")
        self.assertEqual(windows[-1][0].isoformat(), "2026-07-01T00:00:00-05:00")
        self.assertEqual(windows[-1][1], end)

    def test_query_converts_colombia_midnight_to_utc(self) -> None:
        account = self.accounts[0]
        query = account_query(
            account,
            parse_aware_datetime("2022-07-20T00:00:00-05:00"),
            parse_aware_datetime("2022-08-01T00:00:00-05:00"),
        )
        self.assertEqual(
            query,
            f"from:{account.x_handle} "
            "since:2022-07-20_05:00:00_UTC until:2022-08-01_05:00:00_UTC",
        )

    def test_filters_accept_roster_id_or_handle(self) -> None:
        account = self.accounts[0]
        self.assertEqual(filter_accounts(self.accounts, [account.id], None), [account])
        self.assertEqual(
            filter_accounts(self.accounts, [f"@{account.x_handle.upper()}"], None),
            [account],
        )
        senate = filter_accounts(self.accounts, [], "senado")
        self.assertEqual(len(senate), 25)


class BatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = Account(
            id="senado-prueba",
            corporation="Senado de la República",
            name="Persona Prueba",
            district="Nacional",
            x_handle="CuentaPrueba",
            account_url="https://x.com/CuentaPrueba",
            official_source_url="https://example.com",
            service_intervals=("2022-07-20/2026-07-20",),
            notes="",
        )

    def test_split_marker_is_expanded_on_resume(self) -> None:
        start = parse_aware_datetime("2023-01-01T00:00:00-05:00")
        batch = Batch(self.account, start, start + timedelta(days=8))
        with tempfile.TemporaryDirectory() as directory:
            parts = Path(directory)
            paths = batch_paths(parts, batch)
            paths["split"].parent.mkdir(parents=True)
            paths["split"].write_text("subdividido\n", encoding="utf-8")
            children = expand_split_batches(parts, batch)
        self.assertEqual(len(children), 2)
        self.assertEqual(children[0].duration, timedelta(days=4))
        self.assertEqual(children[1].duration, timedelta(days=4))

    def test_one_day_batch_cannot_be_split(self) -> None:
        start = parse_aware_datetime("2023-01-01T00:00:00-05:00")
        with self.assertRaises(ValueError):
            split_batch(Batch(self.account, start, start + timedelta(days=1)))

    def test_merge_enriches_and_deduplicates(self) -> None:
        record = TweetRecord(
            username="CuentaPrueba",
            real_name="Persona Prueba",
            date="2023-02-01T12:00:00Z",
            text="Publicación de prueba",
            matched_terms="",
            favorites_raw="7",
            favorites=7,
            tweet_id="123456",
            url="https://x.com/CuentaPrueba/status/123456",
            scraped_at="2026-08-31T00:00:00Z",
            source_query="from:CuentaPrueba",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            account_parts = root / "parts" / self.account.id
            save_records_atomic([record], account_parts / "uno.csv")
            save_records_atomic([record], account_parts / "dos.csv")
            output = root / "salida.csv"
            total = merge_parts([self.account], root / "parts", output)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter=";"))

        self.assertEqual(total, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["corporation"], "Senado de la República")
        self.assertEqual(rows[0]["congressperson"], "Persona Prueba")
        self.assertEqual(rows[0]["queried_handle"], "CuentaPrueba")


class CoverageTest(unittest.TestCase):
    account = Account(
        id="prueba-cobertura",
        corporation="Senado de la República",
        name="Persona Prueba",
        district="Nacional",
        x_handle="CuentaPrueba",
        account_url="https://x.com/CuentaPrueba",
        official_source_url="https://www.senado.gov.co/",
        service_intervals=("2022-07-20/2026-07-20",),
        notes="Registro de prueba.",
    )

    def batch(self, start: str, end: str) -> Batch:
        return Batch(self.account, parse_aware_datetime(start), parse_aware_datetime(end))

    def record(self, moment: str) -> TweetRecord:
        return TweetRecord(
            username="CuentaPrueba",
            real_name="Persona Prueba",
            date=moment,
            text="Publicación",
            matched_terms="",
            favorites_raw="1",
            favorites=1,
            tweet_id=moment,
            url=f"https://x.com/CuentaPrueba/status/{moment}",
            scraped_at="2026-09-02T00:00:00Z",
            source_query="from:CuentaPrueba",
        )

    def test_window_of_several_months_covers_the_period_without_gaps(self) -> None:
        start = parse_aware_datetime("2022-07-20T00:00:00-05:00")
        end = parse_aware_datetime("2026-07-20T00:00:00-05:00")
        windows = monthly_windows(start, end, 6)

        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[-1][1], end)
        for (_, previous_end), (next_start, _) in zip(windows, windows[1:]):
            self.assertEqual(previous_end, next_start)
        self.assertLess(len(windows), len(monthly_windows(start, end)))

    def test_few_results_are_not_treated_as_truncation(self) -> None:
        batch = self.batch("2023-01-01T00:00:00-05:00", "2023-02-01T00:00:00-05:00")
        records = [self.record("2023-01-28T12:00:00Z")] * 3

        self.assertIsNone(truncation_boundary(records, batch, 80))

    def test_large_batch_stopping_late_is_reported_as_truncated(self) -> None:
        batch = self.batch("2023-01-01T00:00:00-05:00", "2023-02-01T00:00:00-05:00")
        records = [self.record(f"2023-01-2{index % 10}T12:00:00Z") for index in range(120)]

        boundary = truncation_boundary(records, batch, 80)

        self.assertIsNotNone(boundary)
        assert boundary is not None
        self.assertEqual(boundary.isoformat(), "2023-01-20T00:00:00-05:00")
        left, right = split_batch(batch, boundary)
        self.assertEqual(left.start_local, batch.start_local)
        self.assertEqual(left.end_local, boundary)
        self.assertEqual(right.end_local, batch.end_local)

    def test_batch_reaching_its_first_day_is_complete(self) -> None:
        batch = self.batch("2023-01-01T00:00:00-05:00", "2023-02-01T00:00:00-05:00")
        records = [self.record(f"2023-01-0{index % 9 + 1}T12:00:00Z") for index in range(120)]

        self.assertIsNone(truncation_boundary(records, batch, 80))

    def test_truncation_below_old_volume_threshold_is_detected(self) -> None:
        # Caso real: 79 publicaciones desde el 21 de marzo en un trimestre que empieza el 1 de enero.
        batch = self.batch("2025-01-01T00:00:00-05:00", "2025-04-01T00:00:00-05:00")
        records = [
            self.record(f"2025-03-{21 + index % 10:02d}T{12 + index % 10:02d}:{index:02d}:00Z")
            for index in range(79)
        ]

        boundary = truncation_boundary(records, batch, 5, 5.0)

        self.assertIsNotNone(boundary)
        assert boundary is not None
        self.assertEqual(boundary.isoformat(), "2025-03-21T00:00:00-05:00")

    def test_sparse_account_with_late_posts_is_not_truncated(self) -> None:
        batch = self.batch("2025-01-01T00:00:00-05:00", "2025-04-01T00:00:00-05:00")
        moments = ["2025-02-01", "2025-02-15", "2025-03-01", "2025-03-10", "2025-03-20", "2025-03-30"]
        records = [self.record(f"{day}T15:00:00Z") for day in moments]

        self.assertIsNone(truncation_boundary(records, batch, 5, 5.0))

    def test_saved_split_point_is_reused_on_resume(self) -> None:
        batch = self.batch("2023-01-01T00:00:00-05:00", "2023-02-01T00:00:00-05:00")
        with tempfile.TemporaryDirectory() as directory:
            parts = Path(directory)
            paths = batch_paths(parts, batch)
            paths["csv"].parent.mkdir(parents=True, exist_ok=True)
            paths["split"].write_text("2023-01-20T00:00:00-05:00\n", encoding="utf-8")

            expanded = expand_split_batches(parts, batch)

        self.assertEqual(len(expanded), 2)
        self.assertEqual(expanded[0].end_local, parse_aware_datetime("2023-01-20T00:00:00-05:00"))
        self.assertEqual(expanded[1].start_local, parse_aware_datetime("2023-01-20T00:00:00-05:00"))


if __name__ == "__main__":
    unittest.main()
