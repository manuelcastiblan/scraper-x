#!/usr/bin/env python3
"""Descarga de X las cuentas del Pacto Histórico durante el período 2022-2026.

La ejecución se divide por cuenta y mes. Si un mes alcanza el límite de scroll,
se subdivide automáticamente hasta llegar a tramos de un día. Cada tramo
terminado deja un marcador ``.done``, por lo que Ctrl+C detiene la descarga sin
perder el avance y la siguiente ejecución continúa donde quedó.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import signal
import sys
import tempfile
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from scraper_x import (
    DEFAULT_TIMEOUT,
    CSV_FIELDS,
    SCRIPT_DIR,
    TweetRecord,
    create_driver,
    discover_firefox_profile,
    parse_iso_datetime,
    record_from_legacy_row,
    resolve_driver_path,
    save_records_atomic,
    scrape,
)


DEFAULT_ROSTER = SCRIPT_DIR / "censo.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "corpus.csv"
DEFAULT_PARTS = SCRIPT_DIR / "corpus_partes"

ENRICHED_FIELDS = [
    "corporation",
    "congressperson",
    "district",
    "roster_id",
    "queried_handle",
    "service_intervals",
    *CSV_FIELDS,
]


@dataclass(frozen=True)
class Account:
    id: str
    corporation: str
    name: str
    district: str
    x_handle: str
    account_url: str
    official_source_url: str
    service_intervals: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class Batch:
    account: Account
    start_local: datetime
    end_local: datetime

    @property
    def duration(self) -> timedelta:
        return self.end_local - self.start_local

    @property
    def stem(self) -> str:
        return f"{format_boundary(self.start_local)}__{format_boundary(self.end_local)}"


def parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"La fecha debe incluir zona horaria: {value!r}")
    return parsed


def validate_handle(value: str) -> str:
    handle = value.strip().lstrip("@")
    if not handle or len(handle) > 15 or not handle.replace("_", "a").isalnum():
        raise ValueError(f"Usuario de X inválido: {value!r}")
    return handle


def load_roster(path: Path) -> tuple[dict[str, Any], list[Account]]:
    with path.expanduser().resolve().open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if not isinstance(raw.get("scope"), dict) or not isinstance(raw.get("accounts"), list):
        raise ValueError("El censo debe contener los objetos 'scope' y 'accounts'.")

    required = {
        "id",
        "corporation",
        "name",
        "district",
        "x_handle",
        "account_url",
        "official_source_url",
        "service_intervals",
        "notes",
    }
    accounts: list[Account] = []
    for index, item in enumerate(raw["accounts"], start=1):
        missing = required - set(item)
        if missing:
            raise ValueError(f"Registro {index}: faltan {', '.join(sorted(missing))}.")
        accounts.append(
            Account(
                id=str(item["id"]).strip(),
                corporation=str(item["corporation"]).strip(),
                name=str(item["name"]).strip(),
                district=str(item["district"]).strip(),
                x_handle=validate_handle(str(item["x_handle"])),
                account_url=str(item["account_url"]).strip(),
                official_source_url=str(item["official_source_url"]).strip(),
                service_intervals=tuple(str(value) for value in item["service_intervals"]),
                notes=str(item["notes"]).strip(),
            )
        )

    if not accounts:
        raise ValueError("El censo no contiene cuentas.")
    duplicate_ids = duplicates(account.id for account in accounts)
    duplicate_handles = duplicates(account.x_handle.casefold() for account in accounts)
    if duplicate_ids or duplicate_handles:
        raise ValueError(
            "El censo contiene duplicados. "
            f"IDs={sorted(duplicate_ids)}; cuentas={sorted(duplicate_handles)}"
        )
    return raw["scope"], accounts


def duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def next_month(value: datetime, months: int = 1) -> datetime:
    if months < 1:
        raise ValueError("El número de meses debe ser mayor que cero.")
    total = value.month - 1 + months
    return value.replace(year=value.year + total // 12, month=total % 12 + 1, day=1)


def monthly_windows(
    start_local: datetime, end_local: datetime, months: int = 1
) -> list[tuple[datetime, datetime]]:
    if start_local.tzinfo is None or end_local.tzinfo is None:
        raise ValueError("Los límites deben incluir zona horaria.")
    if start_local >= end_local:
        raise ValueError("El inicio debe ser anterior al final.")

    windows: list[tuple[datetime, datetime]] = []
    cursor = start_local
    while cursor < end_local:
        boundary = next_month(cursor, months)
        window_end = min(boundary, end_local)
        windows.append((cursor, window_end))
        cursor = window_end
    return windows


def format_boundary(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H-%M-%S")


def query_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S_UTC")


def account_query(account: Account, start_local: datetime, end_local: datetime) -> str:
    if start_local >= end_local:
        raise ValueError("El inicio del lote debe ser anterior al final.")
    return (
        f"from:{account.x_handle} "
        f"since:{query_timestamp(start_local)} "
        f"until:{query_timestamp(end_local)}"
    )


def split_batch(batch: Batch, at: datetime | None = None) -> tuple[Batch, Batch]:
    if at is None:
        whole_days = batch.duration // timedelta(days=1)
        if whole_days <= 1:
            raise ValueError("Un lote de un día no puede subdividirse.")
        at = batch.start_local + timedelta(days=max(1, whole_days // 2))
    elif not batch.start_local < at < batch.end_local:
        raise ValueError("El punto de corte debe quedar dentro del lote.")
    return (
        Batch(batch.account, batch.start_local, at),
        Batch(batch.account, at, batch.end_local),
    )


def read_split_point(path: Path, batch: Batch) -> datetime | None:
    """Devuelve el corte guardado en el marcador ``.split`` (None = punto medio)."""

    raw = path.read_text(encoding="utf-8").strip()
    if not raw or raw == "subdividido":
        return None
    boundary = parse_aware_datetime(raw).astimezone(batch.start_local.tzinfo)
    if not batch.start_local < boundary < batch.end_local:
        raise ValueError(
            f"El corte {raw!r} no pertenece al lote {batch.account.id}/{batch.stem}."
        )
    return boundary


def earliest_record_time(
    records: Iterable[TweetRecord], start: datetime, end: datetime
) -> datetime | None:
    """Fecha de la publicación más antigua que cae dentro del lote."""

    moments: list[datetime] = []
    for record in records:
        try:
            moment = parse_iso_datetime(record.date)
        except (TypeError, ValueError):
            continue
        if start <= moment < end:
            moments.append(moment)
    return min(moments, default=None)


def batch_paths(parts_directory: Path, batch: Batch) -> dict[str, Path]:
    base = parts_directory / batch.account.id / batch.stem
    return {
        "csv": base.with_suffix(".csv"),
        "done": base.with_suffix(".done"),
        "split": base.with_suffix(".split"),
        "overflow": base.with_suffix(".overflow"),
        "refresh": base.with_suffix(".repasado"),
    }


def expand_split_batches(parts_directory: Path, batch: Batch) -> list[Batch]:
    paths = batch_paths(parts_directory, batch)
    if not paths["split"].exists():
        return [batch]
    left, right = split_batch(batch, read_split_point(paths["split"], batch))
    return [
        *expand_split_batches(parts_directory, left),
        *expand_split_batches(parts_directory, right),
    ]


def read_part(path: Path, query: str) -> dict[str, TweetRecord]:
    if not path.is_file():
        return {}
    records: dict[str, TweetRecord] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            record = record_from_legacy_row(row, row.get("source_query", "") or query)
            if record is not None:
                records[record.tweet_id] = record
    return records


def enriched_row(account: Account, record: TweetRecord) -> dict[str, Any]:
    return {
        "corporation": account.corporation,
        "congressperson": account.name,
        "district": account.district,
        "roster_id": account.id,
        "queried_handle": account.x_handle,
        "service_intervals": "|".join(account.service_intervals),
        **record.as_row(),
    }


def save_enriched_atomic(rows: Iterable[dict[str, Any]], output: Path) -> None:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (row.get("date", ""), row["tweet_id"]), reverse=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ENRICHED_FIELDS, delimiter=";")
            writer.writeheader()
            writer.writerows(ordered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)


def merge_parts(accounts: Iterable[Account], parts_directory: Path, output: Path) -> int:
    merged: dict[str, dict[str, Any]] = {}
    for account in accounts:
        account_directory = parts_directory / account.id
        for part in sorted(account_directory.glob("*.csv")):
            with part.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle, delimiter=";"):
                    record = record_from_legacy_row(
                        row, row.get("source_query", "") or f"from:{account.x_handle}"
                    )
                    if record is None:
                        continue
                    if record.username.casefold() != account.x_handle.casefold():
                        logging.warning(
                            "Se omite @%s en el lote de @%s (%s).",
                            record.username,
                            account.x_handle,
                            part.name,
                        )
                        continue
                    merged[record.tweet_id] = enriched_row(account, record)
    save_enriched_atomic(merged.values(), output)
    return len(merged)


def filter_accounts(
    accounts: list[Account], requested: list[str], corporation: str | None
) -> list[Account]:
    selected = accounts
    if corporation:
        needle = corporation.casefold()
        selected = [account for account in selected if needle in account.corporation.casefold()]
    if requested:
        needles = {value.strip().lstrip("@").casefold() for value in requested}
        selected = [
            account
            for account in selected
            if account.id.casefold() in needles or account.x_handle.casefold() in needles
        ]
        found = {
            value
            for account in selected
            for value in (account.id.casefold(), account.x_handle.casefold())
            if value in needles
        }
        missing = needles - found
        if missing:
            raise ValueError(f"No aparecen en el censo: {', '.join(sorted(missing))}")
    if not selected:
        raise ValueError("Los filtros no seleccionaron ninguna cuenta.")
    return selected


def write_progress(
    path: Path,
    accounts: list[Account],
    initial_batches: int,
    completed_batches: int,
    output_rows: int,
    status: str,
) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "accounts": len(accounts),
        "initial_batches": initial_batches,
        "completed_in_this_run": completed_batches,
        "combined_rows": output_rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def truncation_boundary(
    records: Iterable[TweetRecord],
    batch: Batch,
    minimum_records: int,
    minimum_expected: float = 5.0,
) -> datetime | None:
    """Punto hasta el que X paginó cuando cortó el lote antes de su fecha inicial.

    X suele detener la paginación tras 40-80 resultados sin mostrar ningún error,
    así que un umbral fijo de volumen deja pasar los truncamientos más comunes.
    La regla compara densidades: con el ritmo observado entre el corte y el final
    del lote se estima cuántas publicaciones deberían existir en el tramo sin
    revisar. Si esa estimación no llega a ``minimum_expected`` —cuentas poco
    activas con publicaciones concentradas al final—, el hueco se acepta como
    silencio real. Con menos de ``minimum_records`` resultados no hay densidad
    fiable y tampoco se considera truncado.
    """

    moments: list[datetime] = []
    for record in records:
        try:
            moment = parse_iso_datetime(record.date)
        except (TypeError, ValueError):
            continue
        if batch.start_local <= moment < batch.end_local:
            moments.append(moment)
    if len(moments) < minimum_records:
        return None
    earliest = min(moments)
    boundary = earliest.astimezone(batch.start_local.tzinfo).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if boundary - batch.start_local < timedelta(days=1):
        return None
    one_day = timedelta(days=1)
    covered_days = max((batch.end_local - boundary) / one_day, 1.0)
    uncovered_days = (boundary - batch.start_local) / one_day
    expected_missing = len(moments) * uncovered_days / covered_days
    if expected_missing < minimum_expected:
        return None
    return boundary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--start", type=parse_aware_datetime)
    parser.add_argument("--end", type=parse_aware_datetime, help="Límite exclusivo.")
    parser.add_argument("--account", action="append", default=[], help="ID del censo o @usuario.")
    parser.add_argument(
        "--corporation",
        help="Filtra por el campo corporation del censo (subcadena, sin acentos "
        "ni mayúsculas obligatorias): --corporation senado, --corporation ministerio.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--parts-directory",
        type=Path,
        help="Carpeta de lotes. Por omisión, el nombre del CSV de salida más '_partes'.",
    )
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--driver", type=Path)
    parser.add_argument(
        "--window-months",
        type=int,
        default=1,
        help="Meses por lote inicial. Ventanas amplias reducen el número de "
        "búsquedas; los lotes saturados se subdividen solos.",
    )
    parser.add_argument(
        "--truncation-min-records",
        type=int,
        default=5,
        help="Resultados mínimos para estimar la densidad de un lote y decidir "
        "si X lo truncó.",
    )
    parser.add_argument(
        "--truncation-min-expected",
        type=float,
        default=5.0,
        help="Publicaciones esperadas en el tramo no paginado a partir de las "
        "cuales el lote se considera truncado en vez de silencio de la cuenta.",
    )
    parser.add_argument("--max-scrolls", type=int, default=120)
    parser.add_argument("--no-new-limit", type=int, default=3)
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Segundos de espera por página (por omisión, %(default)g).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Intentos por lote. El valor predeterminado 1 desactiva reintentos automáticos.",
    )
    parser.add_argument("--retry-backoff", type=float, default=0.0)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Con --force, repasa cada lote una sola vez: deja la marca .repasado "
        "y omite los que ya la tienen, de modo que la ejecución se pueda reanudar.",
    )
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args(argv)


def stop_gracefully(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt(f"Señal {signal.Signals(signum).name}")


def main(argv: list[str] | None = None) -> int:
    # Un proceso lanzado en segundo plano hereda SIGINT ignorada: se restablece y
    # SIGTERM sigue la misma ruta de pausa ordenada que Ctrl+C.
    signal.signal(signal.SIGINT, stop_gracefully)
    signal.signal(signal.SIGTERM, stop_gracefully)
    args = parse_args(argv)
    scope, all_accounts = load_roster(args.roster)
    accounts = filter_accounts(all_accounts, args.account, args.corporation)
    start_local = args.start or parse_aware_datetime(scope["scrape_start_local"])
    end_local = args.end or parse_aware_datetime(scope["scrape_end_local_exclusive"])
    windows = monthly_windows(start_local, end_local, args.window_months)
    if args.truncation_min_records <= 0 or args.truncation_min_expected <= 0:
        raise ValueError("Los umbrales de truncamiento deben ser mayores que cero.")
    if args.max_scrolls <= 0 or args.no_new_limit <= 0 or args.retries <= 0:
        raise ValueError("Los límites y el número de intentos deben ser mayores que cero.")
    if args.timeout <= 0 or args.retry_backoff < 0:
        raise ValueError("--timeout debe ser positivo y --retry-backoff no puede ser negativo.")

    output = args.output.expanduser().resolve()
    parts_directory = (
        args.parts_directory.expanduser().resolve()
        if args.parts_directory
        else output.with_name(f"{output.stem}_partes")
    )
    initial_batches = len(accounts) * len(windows)
    by_corporation = Counter(account.corporation for account in accounts)
    print(
        f"Cuentas: {len(accounts)} | lotes iniciales de {args.window_months} mes(es): "
        f"{initial_batches} | "
        f"periodo local: {start_local.isoformat()} .. {end_local.isoformat()} (exclusivo)"
    )
    for corporation, total in sorted(by_corporation.items()):
        print(f"  {corporation}: {total}")
    if args.plan_only:
        return 0

    parts_directory.mkdir(parents=True, exist_ok=True)
    log_path = output.with_name(f"{output.stem}_descarga.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    queue: deque[Batch] = deque()
    for account in accounts:
        for start, end in windows:
            queue.extend(expand_split_batches(parts_directory, Batch(account, start, end)))

    profile = discover_firefox_profile(args.profile)
    driver_path = resolve_driver_path(args.driver)
    driver: Any | None = None
    completed_batches = 0
    failures = 0
    combined_rows = merge_parts(all_accounts, parts_directory, output)
    progress_path = output.with_name(f"{output.stem}_progreso.json")
    write_progress(
        progress_path, accounts, initial_batches, completed_batches, combined_rows, "running"
    )

    try:
        while queue:
            batch = queue.popleft()
            paths = batch_paths(parts_directory, batch)
            if paths["done"].exists() and not args.force:
                logging.info("Ya completado: %s / %s", batch.account.id, batch.stem)
                continue
            if args.force and args.refresh and paths["refresh"].exists():
                logging.info("Ya repasado: %s / %s", batch.account.id, batch.stem)
                continue
            paths["csv"].parent.mkdir(parents=True, exist_ok=True)
            query = account_query(batch.account, batch.start_local, batch.end_local)
            records = read_part(paths["csv"], query)
            logging.info(
                "%s (@%s) | %s | checkpoint=%d",
                batch.account.name,
                batch.account.x_handle,
                batch.stem,
                len(records),
            )

            batch_finished = False
            for attempt in range(1, args.retries + 1):
                try:
                    if driver is None:
                        driver = create_driver(profile, driver_path, not args.headed, args.timeout)
                    stats = scrape(
                        driver=driver,
                        query=query,
                        match_terms=(),
                        records=records,
                        max_scrolls=args.max_scrolls,
                        no_new_limit=args.no_new_limit,
                        checkpoint_every=5,
                        timeout=args.timeout,
                        min_pause=1.2,
                        max_pause=2.2,
                        output=paths["csv"],
                    )
                    save_records_atomic(records.values(), paths["csv"])
                    if stats.get("stopped_max_scrolls"):
                        if batch.duration > timedelta(days=1):
                            paths["split"].write_text("subdividido\n", encoding="utf-8")
                            left, right = split_batch(batch)
                            queue.appendleft(right)
                            queue.appendleft(left)
                            logging.warning("Lote saturado; se subdivide: %s", batch.stem)
                        else:
                            paths["overflow"].write_text(
                                "Un día alcanzó max-scrolls; requiere revisión manual.\n",
                                encoding="utf-8",
                            )
                            raise RuntimeError(
                                f"El lote diario {batch.account.id}/{batch.stem} alcanzó max-scrolls."
                            )
                    else:
                        covered_from = truncation_boundary(
                            records.values(),
                            batch,
                            args.truncation_min_records,
                            args.truncation_min_expected,
                        )
                        if covered_from is None:
                            paths["done"].write_text("completado\n", encoding="utf-8")
                        else:
                            paths["split"].write_text(
                                covered_from.isoformat() + "\n", encoding="utf-8"
                            )
                            left, right = split_batch(batch, covered_from)
                            batch_paths(parts_directory, right)["done"].write_text(
                                "completado\n", encoding="utf-8"
                            )
                            queue.appendleft(left)
                            logging.warning(
                                "X dejó de paginar en %s dentro de %s/%s; "
                                "el tramo anterior se repetirá por separado.",
                                covered_from.isoformat(),
                                batch.account.id,
                                batch.stem,
                            )
                    if args.refresh:
                        paths["refresh"].write_text("repasado\n", encoding="utf-8")
                    batch_finished = True
                    completed_batches += 1
                    combined_rows = merge_parts(all_accounts, parts_directory, output)
                    write_progress(
                        progress_path,
                        accounts,
                        initial_batches,
                        completed_batches,
                        combined_rows,
                        "running",
                    )
                    break
                except Exception:
                    logging.exception(
                        "Falló %s/%s (intento %d/%d); se conserva el checkpoint.",
                        batch.account.id,
                        batch.stem,
                        attempt,
                        args.retries,
                    )
                    if records:
                        save_records_atomic(records.values(), paths["csv"])
                    try:
                        if driver is not None:
                            driver.quit()
                    except Exception:
                        pass
                    driver = None
                    if attempt < args.retries and args.retry_backoff:
                        time.sleep(args.retry_backoff)

            if not batch_finished:
                failures += 1
                combined_rows = merge_parts(all_accounts, parts_directory, output)
                write_progress(
                    progress_path,
                    accounts,
                    initial_batches,
                    completed_batches,
                    combined_rows,
                    "paused_on_error",
                )
                if not args.continue_on_error:
                    logging.error("Descarga pausada. Repite el comando para continuar.")
                    return 1
    except KeyboardInterrupt:
        logging.warning("Descarga pausada por el usuario; se conservaron los checkpoints.")
        status = "paused_by_user"
        return_code = 130
    else:
        status = "completed" if not failures else "completed_with_errors"
        return_code = 0 if not failures else 1
    finally:
        combined_rows = merge_parts(all_accounts, parts_directory, output)
        write_progress(
            progress_path,
            accounts,
            initial_batches,
            completed_batches,
            combined_rows,
            locals().get("status", "paused_on_error"),
        )
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                logging.warning("Firefox no pudo cerrarse limpiamente.", exc_info=True)

    return return_code


if __name__ == "__main__":
    sys.exit(main())
