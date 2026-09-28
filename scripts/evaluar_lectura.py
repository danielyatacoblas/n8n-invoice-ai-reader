#!/usr/bin/env python3
"""Pasa las facturas generadas por el flujo y compara con lo esperado.

    python scripts/generar_facturas.py    # primero genera las facturas
    python scripts/evaluar_lectura.py

Mide dos cosas: si cada campo se leyó bien y si la decisión (registrar,
revisar, duplicada, pedir a la IA) es la correcta, con el motivo correcto.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.facturas import leer_texto, procesar  # noqa: E402

ESPERADO = ROOT / "data" / "esperado.csv"
FACTURAS = ROOT / "data" / "facturas"
HOY = "2026-09-15"
CAMPOS = ["ruc_emisor", "serie", "numero", "fecha", "moneda", "base", "igv", "total"]


def evaluar():
    if not ESPERADO.exists():
        raise SystemExit("Primero corre: python scripts/generar_facturas.py")
    registro: list[str] = []
    campos_ok = campos_total = decisiones_ok = 0
    fallos, estados = [], Counter()
    filas = list(csv.DictReader(ESPERADO.open(encoding="utf-8")))
    for fila in filas:
        texto = (FACTURAS / f"{fila['archivo']}.txt").read_text(encoding="utf-8")
        r = procesar(leer_texto(texto), registro, HOY, "texto")
        estados[r["estado"]] += 1
        for c in CAMPOS:
            leido = r["factura"][c]
            campos_total += 1
            if ("" if leido is None else str(leido)) == fila[c]:
                campos_ok += 1
            else:
                fallos.append(f"{fila['archivo']}: {c} leído={leido} esperado={fila[c]}")
        motivo = "; ".join(r["errores"])
        if r["estado"] == fila["estado"] and motivo == fila["errores"]:
            decisiones_ok += 1
        else:
            fallos.append(f"{fila['archivo']}: {r['estado']} ({motivo}) "
                          f"esperado {fila['estado']} ({fila['errores']})")
    return {"facturas": len(filas), "campos_ok": campos_ok, "campos_total": campos_total,
            "decisiones_ok": decisiones_ok, "estados": estados, "fallos": fallos}


def main():
    r = evaluar()
    print(f"Facturas procesadas: {r['facturas']}")
    print(f"Campos bien leídos:  {r['campos_ok']}/{r['campos_total']}")
    print(f"Decisiones correctas: {r['decisiones_ok']}/{r['facturas']}")
    print("\nResultado:")
    for estado in ("registrada", "revision", "duplicada", "faltan_datos"):
        print(f"  {estado:<13} {r['estados'][estado]}")
    for f in r["fallos"]:
        print("  FALLO", f)


if __name__ == "__main__":
    main()
