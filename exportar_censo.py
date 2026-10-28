#!/usr/bin/env python3
"""Exporta el censo del Pacto Histórico (JSON) a una hoja auditable en CSV.

El JSON sigue siendo la fuente única; esta hoja es la vista revisable, con una
fila por persona, su cuenta de X, la fuente institucional y los intervalos de
servicio ya separados en columnas de inicio y fin.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from descargar_cuentas import DEFAULT_ROSTER, load_roster

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SHEET = SCRIPT_DIR / "pacto_historico_2022_2026.csv"

SHEET_FIELDS = [
    "roster_id",
    "corporation",
    "name",
    "district",
    "x_handle",
    "account_url",
    "official_source_url",
    "service_intervals",
    "service_start",
    "service_end_exclusive",
    "service_segments",
    "notes",
]


def interval_bounds(intervals: tuple[str, ...]) -> tuple[str, str]:
    starts, ends = [], []
    for interval in intervals:
        start, _, end = interval.partition("/")
        if not end:
            raise ValueError(f"Intervalo sin final exclusivo: {interval!r}")
        starts.append(start.strip())
        ends.append(end.strip())
    return min(starts), max(ends)


def sheet_rows(accounts) -> list[dict[str, str]]:
    rows = []
    for account in accounts:
        start, end = interval_bounds(account.service_intervals)
        rows.append(
            {
                "roster_id": account.id,
                "corporation": account.corporation,
                "name": account.name,
                "district": account.district,
                "x_handle": account.x_handle,
                "account_url": account.account_url,
                "official_source_url": account.official_source_url,
                "service_intervals": "|".join(account.service_intervals),
                "service_start": start,
                "service_end_exclusive": end,
                "service_segments": str(len(account.service_intervals)),
                "notes": account.notes,
            }
        )
    return sorted(rows, key=lambda row: (row["corporation"], row["name"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_SHEET)
    args = parser.parse_args(argv)

    _, accounts = load_roster(args.roster)
    rows = sheet_rows(accounts)
    output = args.output.expanduser().resolve()
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} cuentas exportadas a {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
