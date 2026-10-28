#!/usr/bin/env python3
"""Vuelve a leer el texto completo de las publicaciones que quedaron truncadas.

El descargador leía el texto tal como X lo muestra en la cronología, donde las
publicaciones largas aparecen recortadas tras "Mostrar más". Ese clic ya se
restauró en ``scraper_x_mejorado.extract_text``, pero las publicaciones bajadas
antes conservan el texto cortado. Este script abre cada publicación afectada por
su URL, expande el texto y reescribe el registro en el CSV del lote que lo
contiene; el CSV combinado se regenera después con el propio descargador.

Guarda su avance en un archivo de reanudación, así que puede detenerse y
continuar sin repetir trabajo. Nunca borra registros: sólo sustituye el texto
cuando el nuevo es más largo que el guardado.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

from descargar_cuentas_pacto_historico import DEFAULT_PARTS, DEFAULT_ROSTER, load_roster
from scraper_x_mejorado import (
    create_driver,
    discover_firefox_profile,
    extract_text,
    find_article_by_id,
    page_state,
    record_from_legacy_row,
    resolve_driver_path,
    save_records_atomic,
)

PALABRA_FINAL = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}$")


def parece_truncado(text: str, minimo: int) -> bool:
    limpio = text.rstrip()
    if not limpio.endswith(("…", "...")):
        return False
    if len(limpio) < minimo:
        return False
    sin_puntos = limpio[:-1] if limpio.endswith("…") else limpio[:-3]
    partes = sin_puntos.split()
    return bool(partes) and bool(PALABRA_FINAL.search(partes[-1]))


def indexar_lotes(parts: Path, minimo: int) -> dict[str, list[tuple[Path, str]]]:
    """Agrupa por archivo de lote los identificadores con texto truncado."""

    pendientes: dict[str, list[tuple[Path, str]]] = {}
    for parte in sorted(parts.glob("*/*.csv")):
        with parte.open("r", encoding="utf-8-sig", newline="") as handle:
            for fila in csv.DictReader(handle, delimiter=";"):
                if parece_truncado(fila.get("text", ""), minimo):
                    pendientes.setdefault(str(parte), []).append(
                        (parte, fila["tweet_id"])
                    )
    return pendientes


def detener(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt(f"Señal {signal.Signals(signum).name}")


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGINT, detener)
    signal.signal(signal.SIGTERM, detener)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--parts-directory", type=Path, default=DEFAULT_PARTS)
    parser.add_argument("--state", type=Path, default=Path("reparacion_textos_estado.json"))
    parser.add_argument("--min-length", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--pause", type=float, default=1.5)
    parser.add_argument("--retry-backoff", type=float, default=600.0)
    parser.add_argument("--retries", type=int, default=12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("reparacion_textos.log", encoding="utf-8")],
        force=True,
    )
    load_roster(args.roster)
    parts = args.parts_directory.expanduser().resolve()
    estado_path = args.state.expanduser().resolve()
    estado = json.loads(estado_path.read_text(encoding="utf-8")) if estado_path.is_file() else {}
    hechos: set[str] = set(estado.get("listos", []))

    pendientes = indexar_lotes(parts, args.min_length)
    total = sum(len(v) for v in pendientes.values())
    restantes = [
        (parte, tid) for grupo in pendientes.values() for parte, tid in grupo if tid not in hechos
    ]
    if args.limit:
        restantes = restantes[: args.limit]
    logging.info("Truncados detectados: %d | ya reparados: %d | a revisar ahora: %d",
                 total, len(hechos), len(restantes))
    if not restantes:
        return 0

    driver: Any = None
    ampliados = iguales = fallidos = 0
    por_lote: dict[Path, list[tuple[str, str]]] = {}
    for parte, tid in restantes:
        por_lote.setdefault(parte, []).append((tid, ""))

    try:
        driver = create_driver(
            discover_firefox_profile(None), resolve_driver_path(None), not args.headed, args.timeout
        )
        for parte, items in por_lote.items():
            registros = {}
            with parte.open("r", encoding="utf-8-sig", newline="") as handle:
                for fila in csv.DictReader(handle, delimiter=";"):
                    registro = record_from_legacy_row(fila, fila.get("source_query", ""))
                    if registro is not None:
                        registros[registro.tweet_id] = registro
            cambiado = False
            for tid, _ in items:
                registro = registros.get(tid)
                if registro is None:
                    hechos.add(tid)
                    continue
                for intento in range(1, args.retries + 1):
                    try:
                        if driver is None:
                            driver = create_driver(
                                discover_firefox_profile(None), resolve_driver_path(None),
                                not args.headed, args.timeout,
                            )
                        driver.get(registro.url)
                        time.sleep(args.pause)
                        # "results" es el único estado con la publicación cargada;
                        # "login", "error" o False indican bloqueo de X.
                        estado_pagina = page_state(driver)
                        if estado_pagina != "results":
                            raise RuntimeError(f"X respondió: {estado_pagina}")
                        articulo = find_article_by_id(driver, tid)
                        if articulo is None:
                            raise RuntimeError("no se encontró el artículo")
                        texto = extract_text(articulo, driver)
                        if texto and len(texto) > len(registro.text):
                            registro.text = texto
                            ampliados += 1
                            cambiado = True
                        else:
                            iguales += 1
                        hechos.add(tid)
                        break
                    except KeyboardInterrupt:
                        raise
                    except Exception as error:
                        logging.warning("%s falló (intento %d/%d): %s", tid, intento, args.retries, error)
                        try:
                            if driver is not None:
                                driver.quit()
                        except Exception:
                            pass
                        driver = None
                        if intento < args.retries:
                            time.sleep(args.retry_backoff)
                        else:
                            fallidos += 1
                            hechos.add(tid)
            if cambiado:
                save_records_atomic(registros.values(), parte)
            estado_path.write_text(
                json.dumps({"listos": sorted(hechos)}, ensure_ascii=False), encoding="utf-8"
            )
            logging.info("Lote %s | ampliados=%d iguales=%d fallidos=%d | progreso %d/%d",
                         parte.name, ampliados, iguales, fallidos, len(hechos), total)
    except KeyboardInterrupt:
        logging.warning("Reparación pausada; el avance quedó guardado.")
    finally:
        estado_path.write_text(json.dumps({"listos": sorted(hechos)}, ensure_ascii=False), encoding="utf-8")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    logging.info("Fin. Ampliados=%d | sin cambio=%d | fallidos=%d", ampliados, iguales, fallidos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
