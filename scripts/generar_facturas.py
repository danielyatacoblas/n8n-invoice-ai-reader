#!/usr/bin/env python3
"""Genera facturas PDF ficticias y el resultado que se espera de cada una.

    python scripts/generar_facturas.py

Salidas:
  data/facturas/*.pdf        30 facturas con distintos formatos de proveedor
  data/facturas/*.txt        el mismo texto, para los tests sin PDF
  data/esperado.csv          qué debe leer y decidir el flujo en cada una

Incluye a propósito facturas con problemas: RUC con dígito verificador
equivocado, IGV mal calculado, total que no cuadra, fecha futura, factura
dirigida a otra empresa, reenvíos duplicados y PDFs donde falta una etiqueta.
Semilla fija: siempre genera exactamente lo mismo.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.facturas import FACTORES_RUC, RUC_EMPRESA  # noqa: E402

SALIDA = ROOT / "data" / "facturas"
ESPERADO = ROOT / "data" / "esperado.csv"
HOY = "2026-09-15"   # fecha de referencia con la que se evalúa

PROVEEDORES = [
    ("DISTRIBUIDORA ANDINA S.A.C.", "2055566677"),
    ("SUMINISTROS DEL PACÍFICO E.I.R.L.", "2048899001"),
    ("TECNOLOGÍA Y REDES LIMA S.A.", "2051122334"),
    ("IMPRESIONES RÁPIDAS S.A.C.", "2060987654"),
    ("JUAN PÉREZ QUISPE", "1045678912"),
    ("LOGÍSTICA NORTE S.A.C.", "2070011223"),
]
PRODUCTOS = [("Papel bond A4 x 500", 1850), ("Tóner HP 85A", 21900),
             ("Servicio de mantenimiento de red", 45000),
             ("Silla ergonómica", 38990), ("Cable UTP cat6 x 305 m", 52000),
             ("Transporte de mercadería Lima-Trujillo", 120000),
             ("Impresión de volantes x 1000", 16500), ("Disco SSD 1 TB", 34900)]

# Cada proveedor usa su propio sistema de facturación: etiquetas distintas
FORMATOS = [
    {"base": "Op. Gravada", "igv": "IGV (18%)", "total": "Importe Total",
     "fecha": "Fecha de emisión"},
    {"base": "Valor de venta", "igv": "IGV", "total": "Total a pagar",
     "fecha": "Fecha Emisión"},
    {"base": "SUB TOTAL", "igv": "I.G.V.", "total": "TOTAL",
     "fecha": "FECHA DE EMISION"},
]


def ruc(base10: str, valido: bool = True) -> str:
    resto = 11 - sum(int(d) * f for d, f in zip(base10, FACTORES_RUC)) % 11
    dv = {10: 0, 11: 1}.get(resto, resto)
    return base10 + str(dv if valido else (dv + 3) % 10)


def soles(c: int) -> str:
    return f"{c // 100:,}.{c % 100:02d}"


# ── PDF mínimo, sin dependencias ───────────────────────────────────────────

def pdf(lineas: list[tuple[str, int, int]]) -> bytes:
    """Una página A4 con texto en Helvetica. lineas = (texto, x, y)."""
    def esc(t):
        return (t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                .encode("cp1252"))
    contenido = b"BT /F1 10 Tf\n"
    for texto, x, y in lineas:
        contenido += b"1 0 0 1 %d %d Tm (" % (x, y) + esc(texto) + b") Tj\n"
    contenido += b"ET"
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
    ]
    salida = b"%PDF-1.4\n"
    posiciones = []
    for i, obj in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for p in posiciones:
        salida += b"%010d 00000 n \n" % p
    salida += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(objetos) + 1, xref))
    return salida


# ── facturas ───────────────────────────────────────────────────────────────

def factura(rng: random.Random, n: int, **cambios) -> dict:
    nombre, base10 = PROVEEDORES[n % len(PROVEEDORES)]
    items = rng.sample(PRODUCTOS, rng.randint(1, 3))
    lineas = [(d, rng.randint(1, 6), p) for d, p in items]
    base = sum(c * p for _, c, p in lineas)
    igv = (base * 18 + 50) // 100
    f = {
        "proveedor": nombre, "ruc_emisor": ruc(base10), "ruc_cliente": RUC_EMPRESA,
        "serie": "F00" + str(1 + n % 3), "numero": str(1000 + n * 37).zfill(8),
        "fecha": f"2026-{rng.randint(6, 9):02d}-{rng.randint(1, 14):02d}",
        "moneda": "PEN", "lineas": lineas, "base": base, "igv": igv,
        "total": base + igv, "formato": FORMATOS[n % len(FORMATOS)],
        "omitir": None, "estado": "registrada", "errores": "",
    }
    f.update(cambios)
    return f


def texto_factura(f: dict) -> list[tuple[str, int, int]]:
    fmt = f["formato"]
    simbolo = "US$" if f["moneda"] == "USD" else "S/"
    a, m, d = f["fecha"].split("-")
    y = 790
    out = []

    def linea(t, x=50, salto=16):
        nonlocal y
        out.append((t, x, y))
        y -= salto

    linea(f["proveedor"])
    linea(f"RUC: {f['ruc_emisor']}")
    linea("Av. Ficticia 456, Lima", salto=28)
    linea("FACTURA ELECTRÓNICA")
    linea(f"{f['serie']}-{f['numero']}", salto=28)
    linea(f"{fmt['fecha']}: {d}/{m}/{a}")
    linea("Señor(es): COMERCIAL DEMO LIMA S.A.C.")
    linea(f"RUC: {f['ruc_cliente']}")
    linea("Moneda: " + ("DÓLARES AMERICANOS" if f["moneda"] == "USD" else "SOLES"), salto=28)
    linea("Cant.  Descripción")
    for desc, cant, precio in f["lineas"]:
        linea(f"{cant}  {desc}  {simbolo} {soles(cant * precio)}")
    y -= 12
    for campo in ("base", "igv", "total"):
        if f["omitir"] != campo:
            linea(f"{fmt[campo]}: {simbolo} {soles(f[campo])}")
    y -= 12
    linea("Representación impresa de la factura electrónica. Documento ficticio.")
    return out


def main():
    rng = random.Random(42)
    facturas = [factura(rng, n) for n in range(22)]

    # Casos con problemas, cada uno documentado con lo que debe pasar
    base10 = PROVEEDORES[1][1]
    facturas += [
        factura(rng, 22, ruc_emisor=ruc(base10, valido=False), estado="revision",
                errores="RUC del emisor inválido"),
        factura(rng, 23, estado="revision", errores="el IGV no es el 18 % de la base"),
        factura(rng, 24, estado="revision", errores="el total no es base + IGV"),
        factura(rng, 25, fecha="2026-10-03", estado="revision",
                errores="fecha de emisión en el futuro"),
        factura(rng, 26, ruc_cliente=ruc("2044433322"), estado="revision",
                errores="factura emitida a otro RUC"),
        factura(rng, 27, moneda="USD"),
        factura(rng, 28, omitir="total", estado="faltan_datos"),
        factura(rng, 29, omitir="igv", estado="faltan_datos"),
    ]
    facturas[23]["igv"] += 1500                       # IGV inflado y el total
    facturas[23]["total"] += 1500                     # sumado con ese IGV
    facturas[24]["total"] += 10000                    # total no cuadra
    # Reenvíos: el proveedor manda la misma factura otra vez
    facturas.append(dict(facturas[3], estado="duplicada"))
    facturas.append(dict(facturas[10], estado="duplicada"))

    SALIDA.mkdir(parents=True, exist_ok=True)
    for vieja in SALIDA.glob("*"):
        vieja.unlink()

    with ESPERADO.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["archivo", "estado", "errores", "ruc_emisor", "serie",
                    "numero", "fecha", "moneda", "base", "igv", "total"])
        for i, f in enumerate(facturas, 1):
            nombre = f"factura_{i:02d}"
            lineas = texto_factura(f)
            (SALIDA / f"{nombre}.pdf").write_bytes(pdf(lineas))
            (SALIDA / f"{nombre}.txt").write_text(
                "\n".join(t for t, _, _ in lineas) + "\n", encoding="utf-8", newline="\n")
            leido = {k: ("" if f["omitir"] == k else f[k]) for k in ("base", "igv", "total")}
            w.writerow([nombre, f["estado"], f["errores"], f["ruc_emisor"],
                        f["serie"], f["numero"], f["fecha"], f["moneda"],
                        leido["base"], leido["igv"], leido["total"]])
    print(f"{len(facturas)} facturas en {SALIDA.relative_to(ROOT)}")
    print(f"resultado esperado en {ESPERADO.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
