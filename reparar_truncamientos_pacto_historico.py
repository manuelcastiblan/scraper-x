#!/usr/bin/env python3
"""Reabre lotes certificados que X truncó sin superar el antiguo umbral de volumen.

La primera versión del descargador sólo consideraba truncado un lote con 80 o más
resultados, pero X corta la paginación con frecuencia entre 40 y 80. Este script
revisa cada lote ``.done`` con la regla por densidad de ``truncation_boundary``:
cuando detecta un corte, escribe el marcador ``.split`` con el punto de corte,
certifica el tramo realmente paginado y retira el ``.done`` del lote completo,
de modo que la siguiente ejecución del descargador vuelva a pedir sólo el tramo
que falta. Ninguna publicación se borra: los CSV de cada lote se conservan.

Por defecto sólo informa; ``--apply`` escribe los cambios.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from descargar_cuentas_pacto_historico import (
    DEFAULT_PARTS,
    DEFAULT_ROSTER,
    Batch,
    account_query,
    batch_paths,
    load_roster,
    parse_aware_datetime,
    read_part,
    split_batch,
    truncation_boundary,
)


def parse_stem(stem: str, tzinfo) -> tuple[datetime, datetime]:
    start_raw, end_raw = stem.split("__")
    fmt = "%Y-%m-%dT%H-%M-%S"
    return (
        datetime.strptime(start_raw, fmt).replace(tzinfo=tzinfo),
        datetime.strptime(end_raw, fmt).replace(tzinfo=tzinfo),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--parts-directory", type=Path, default=DEFAULT_PARTS)
    parser.add_argument("--min-records", type=int, default=5)
    parser.add_argument("--min-expected", type=float, default=5.0)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    scope, accounts = load_roster(args.roster)
    tzinfo = parse_aware_datetime(scope["scrape_start_local"]).tzinfo
    parts = args.parts_directory.expanduser().resolve()
    reopened = 0
    for account in accounts:
        directory = parts / account.id
        if not directory.is_dir():
            continue
        for part in sorted(directory.glob("*.csv")):
            try:
                start, end = parse_stem(part.stem, tzinfo)
            except ValueError:
                # Copias de conflicto de iCloud ("... 2.csv"): no son lotes propios.
                print(f"Se ignora {account.id}/{part.name}: no es un lote del descargador.")
                continue
            batch = Batch(account, start, end)
            paths = batch_paths(parts, batch)
            if not paths["done"].exists() or paths["split"].exists():
                continue
            records = read_part(part, account_query(account, start, end))
            boundary = truncation_boundary(
                records.values(), batch, args.min_records, args.min_expected
            )
            if boundary is None:
                continue
            left, right = split_batch(batch, boundary)
            reopened += 1
            print(
                f"@{account.x_handle:17} {part.stem}  {len(records):4d} pubs desde "
                f"{boundary.date()} -> falta {left.start_local.date()}..{boundary.date()}"
            )
            if args.apply:
                paths["split"].write_text(boundary.isoformat() + "\n", encoding="utf-8")
                batch_paths(parts, right)["done"].write_text("completado\n", encoding="utf-8")
                paths["done"].unlink()
    action = "reabiertos" if args.apply else "a reabrir (simulación; usa --apply)"
    print(f"Lotes {action}: {reopened}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
