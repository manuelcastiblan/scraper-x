#!/usr/bin/env python3
"""Descarga de X todas las publicaciones que contienen ciertos términos.

Busca día por día (o en lotes de pocos días) en todas las cuentas, no sólo en
una lista. Cada día terminado deja un marcador, así que la descarga se puede
interrumpir y continuar. Además del filtro de la búsqueda, comprueba en local
que el texto contenga literalmente alguno de los términos: X devuelve
publicaciones de contexto que no los mencionan, y sin esa comprobación el corpus
queda contaminado.

Ejemplo:

    python descargar_busqueda.py --term "Prioridad Nacional" --term #PrioridadNacional \
        --start 2026-03-01 --end 2026-08-01 --output prioridad_nacional.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from scraper_x import (
    SCRIPT_DIR,
    TweetRecord,
    create_driver,
    discover_firefox_profile,
    find_matching_terms,
    record_from_legacy_row,
    resolve_driver_path,
    save_records_atomic,
    scrape,
)


def search_expression(terms: Sequence[str]) -> str:
    """Convierte una lista de términos en la expresión OR que entiende X.

    Las expresiones de varias palabras van entre comillas para que X las busque
    como frase; los hashtags y las palabras sueltas van tal cual.
    """

    if not terms:
        raise ValueError("Hay que indicar al menos un término de búsqueda.")
    partes = [term if term.startswith("#") or " " not in term else f'"{term}"' for term in terms]
    return "(" + " OR ".join(partes) + ")" if len(partes) > 1 else partes[0]


def range_query(start_day: date, end_day: date, expression: str) -> str:
    if start_day >= end_day:
        raise ValueError("El inicio del intervalo debe ser anterior al final.")
    return (
        f"{expression} "
        f"since:{start_day.isoformat()}_00:00:00_UTC "
        f"until:{end_day.isoformat()}_00:00:00_UTC"
    )


def daily_query(day: date, expression: str) -> str:
    return range_query(day, day + timedelta(days=1), expression)


def earliest_record_day(
    records: Iterable[TweetRecord],
    start_day: date,
    end_day: date,
) -> date | None:
    days: list[date] = []
    for record in records:
        try:
            record_day = date.fromisoformat(record.date[:10])
        except (TypeError, ValueError):
            continue
        if start_day <= record_day < end_day:
            days.append(record_day)
    return min(days, default=None)


def read_matching_records(path: Path, terms: Sequence[str], expression: str) -> dict[str, TweetRecord]:
    if not path.is_file():
        return {}

    records: dict[str, TweetRecord] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if not find_matching_terms(row.get("text", ""), terms):
                continue
            source_query = row.get("source_query", "") or expression
            record = record_from_legacy_row(row, source_query, terms)
            if record:
                records[record.tweet_id] = record
    return records


def merge_records(
    seed: dict[str, TweetRecord],
    parts_directory: Path,
    output: Path,
    terms: Sequence[str],
    expression: str,
) -> dict[str, TweetRecord]:
    merged = dict(seed)
    for part in sorted(parts_directory.glob("*.csv")):
        merged.update(read_matching_records(part, terms, expression))
    save_records_atomic(merged.values(), output)
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        required=True,
        help="Término o frase a buscar. Repetible: --term \"Prioridad Nacional\" --term #Hashtag",
    )
    parser.add_argument(
        "--query",
        help="Expresión de búsqueda completa de X, por si necesitas operadores "
        "(lang:, from:, -filter:replies). Reemplaza la que se arma con --term, "
        "pero el filtro local sigue exigiendo que el texto contenga algún --term.",
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="Primer día (AAAA-MM-DD).")
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        required=True,
        help="Límite exclusivo: 2026-08-01 incluye todo el 31 de julio.",
    )
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "busqueda.csv")
    parser.add_argument(
        "--parts-directory",
        type=Path,
        help="Carpeta de lotes diarios. Por omisión, el nombre del CSV más '_partes'.",
    )
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--max-scrolls", type=int, default=120)
    parser.add_argument("--no-new-limit", type=int, default=3)
    parser.add_argument(
        "--batch-days",
        type=int,
        default=3,
        help="Días consecutivos por búsqueda; reduce los límites de frecuencia de X.",
    )
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--retry-backoff", type=float, default=45.0)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--force", action="store_true", help="Repite también los días ya completados.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start >= args.end:
        raise ValueError("--start debe ser anterior a --end.")
    if (
        args.max_scrolls <= 0
        or args.no_new_limit <= 0
        or args.batch_days <= 0
        or args.retries <= 0
    ):
        raise ValueError("Los límites de scroll deben ser mayores que cero.")
    if args.retry_backoff < 0:
        raise ValueError("--retry-backoff no puede ser negativo.")

    terms = tuple(args.term)
    expression = args.query or search_expression(terms)
    output = args.output.expanduser().resolve()
    parts_directory = (
        args.parts_directory.expanduser().resolve()
        if args.parts_directory
        else output.with_name(f"{output.stem}_partes")
    )
    parts_directory.mkdir(parents=True, exist_ok=True)
    log_path = output.with_name(f"{output.stem}_descarga.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )

    backup = output.with_name(f"{output.stem}_checkpoint_inicial.csv")
    if output.is_file() and not backup.exists():
        shutil.copy2(output, backup)
        logging.info("Checkpoint inicial respaldado en %s", backup)

    logging.info("Búsqueda: %s", expression)
    seed = read_matching_records(output, terms, expression)
    logging.info("Coincidencias exactas recuperadas del primer checkpoint: %d", len(seed))

    profile = discover_firefox_profile(args.profile)
    driver_path = resolve_driver_path(args.driver)
    driver = None
    current_records: dict[str, TweetRecord] = {}
    current_part: Path | None = None
    failures = 0

    try:
        driver = create_driver(profile, driver_path, not args.headed, args.timeout)
        day = args.start
        while day < args.end:
            day_marker = parts_directory / f"{day.isoformat()}.done"
            if day_marker.exists() and not args.force:
                logging.info("Día %s ya completado; se omite.", day)
                day += timedelta(days=1)
                continue

            force_single_day = (parts_directory / f"{day.isoformat()}.single").exists()
            batch_end = day + timedelta(days=1)
            while (
                not force_single_day
                and batch_end < args.end
                and (batch_end - day).days < args.batch_days
                and (
                    args.force
                    or not (parts_directory / f"{batch_end.isoformat()}.done").exists()
                )
            ):
                batch_end += timedelta(days=1)

            query = range_query(day, batch_end, expression)
            last_day = batch_end - timedelta(days=1)
            period_label = day.isoformat()
            part_stem = day.isoformat()
            if last_day != day:
                period_label = f"{day.isoformat()}..{last_day.isoformat()}"
                part_stem = f"{day.isoformat()}__{last_day.isoformat()}"
            current_part = parts_directory / f"{part_stem}.csv"
            done_markers = [
                parts_directory / f"{(day + timedelta(days=offset)).isoformat()}.done"
                for offset in range((batch_end - day).days)
            ]
            current_records = read_matching_records(current_part, terms, expression)
            next_day = batch_end
            logging.info(
                "Periodo %s | registros recuperados=%d | consulta=%s",
                period_label,
                len(current_records),
                query,
            )

            day_completed = False
            for attempt in range(1, args.retries + 1):
                try:
                    stats = scrape(
                        driver=driver,
                        query=query,
                        match_terms=terms,
                        records=current_records,
                        max_scrolls=args.max_scrolls,
                        no_new_limit=args.no_new_limit,
                        checkpoint_every=5,
                        timeout=args.timeout,
                        min_pause=1.2,
                        max_pause=2.2,
                        output=current_part,
                    )
                    save_records_atomic(current_records.values(), current_part)
                    merged = merge_records(seed, parts_directory, output, terms, expression)
                    logging.info(
                        "Periodo %s terminado | parte=%d | total combinado=%d | %s",
                        period_label,
                        len(current_records),
                        len(merged),
                        dict(stats),
                    )
                    if stats.get("stopped_max_scrolls"):
                        logging.warning(
                            "El periodo %s alcanzó el máximo de scrolls; podría requerir otra pasada.",
                            period_label,
                        )
                        for offset in range((batch_end - day).days):
                            single_marker = parts_directory / (
                                f"{(day + timedelta(days=offset)).isoformat()}.single"
                            )
                            single_marker.write_text(
                                "requiere búsqueda diaria\n", encoding="utf-8"
                            )
                        if batch_end - day > timedelta(days=1):
                            next_day = day
                    else:
                        earliest_day = earliest_record_day(
                            current_records.values(), day, batch_end
                        )
                        if current_records and earliest_day is None:
                            raise RuntimeError(
                                "Las publicaciones recuperadas no tienen fechas válidas "
                                "dentro del intervalo solicitado."
                            )
                        covered_from = earliest_day if current_records else day
                        markers_to_write = done_markers[(covered_from - day).days :]
                        for done_marker in markers_to_write:
                            done_marker.write_text("completado\n", encoding="utf-8")
                            done_marker.with_suffix(".single").unlink(missing_ok=True)
                        if len(markers_to_write) < len(done_markers):
                            logging.warning(
                                "X sólo paginó hasta %s en el periodo %s; "
                                "las fechas anteriores se repetirán en lotes más pequeños.",
                                covered_from,
                                period_label,
                            )
                        for offset, done_marker in enumerate(done_markers):
                            if not done_marker.exists():
                                next_day = day + timedelta(days=offset)
                                break
                    day_completed = True
                    break
                except Exception:
                    logging.exception(
                        "Falló el periodo %s (intento %d/%d); el checkpoint se conservará.",
                        period_label,
                        attempt,
                        args.retries,
                    )
                    if current_records:
                        save_records_atomic(current_records.values(), current_part)
                        merge_records(seed, parts_directory, output, terms, expression)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    if attempt < args.retries:
                        logging.warning(
                            "Enfriamiento de %.0f segundos antes de reintentar.",
                            args.retry_backoff,
                        )
                        time.sleep(args.retry_backoff)
                    driver = create_driver(profile, driver_path, not args.headed, args.timeout)

            if not day_completed:
                failures += 1

            day = next_day
    except KeyboardInterrupt:
        logging.warning("Descarga interrumpida; se conservarán y combinarán los checkpoints.")
        return_code = 130
    else:
        return_code = 1 if failures else 0
    finally:
        if current_part and current_records:
            save_records_atomic(current_records.values(), current_part)
        merged = merge_records(seed, parts_directory, output, terms, expression)
        logging.info("Resultado combinado: %d publicaciones en %s", len(merged), output)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                logging.warning("Firefox no pudo cerrarse limpiamente.", exc_info=True)

    return return_code


if __name__ == "__main__":
    sys.exit(main())
