"""Paridad: los nodos Code de n8n (JS) y la lógica Python deben decidir igual.

Requiere Node.js; si no está instalado, se salta.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.facturas import desde_ia, fila_hoja, leer_texto, procesar  # noqa: E402

RUNNER = ROOT / "tests" / "correr_nodo_js.mjs"
FACTURAS = sorted((ROOT / "data" / "facturas").glob("*.txt"))
HOY = "2026-09-15"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="Node.js no está instalado")


def _js(modo: str, entrada: list, tmp_path: Path) -> list[dict]:
    ruta = tmp_path / "entrada.json"
    ruta.write_text(json.dumps(entrada, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(["node", str(RUNNER), modo, str(ruta), HOY],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        pytest.fail(f"el nodo JS falló:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _python(resultados: list[dict], textos: list[str]) -> list[dict]:
    return [dict(r, fila=fila_hoja(r), texto=t) for r, t in zip(resultados, textos)]


def test_lectura_de_pdf_igual_en_las_32_facturas(tmp_path):
    if not FACTURAS:
        pytest.skip("corre antes: python scripts/generar_facturas.py")
    textos = [p.read_text(encoding="utf-8") for p in FACTURAS]
    registro: list[str] = []
    py = _python([procesar(leer_texto(t), registro, HOY, "texto") for t in textos], textos)
    js = _js("texto", textos, tmp_path)
    for nombre, p, j in zip(FACTURAS, py, js):
        assert p == j, f"divergen en {nombre.name}\n python={p}\n js    ={j}"


def test_textos_raros(tmp_path):
    textos = [
        "RUC 20555666773\nF001 - 12\nFecha Emisión: 1/9/2026\nSOLES\nTotal: 1180",
        "R.U.C. N° 20555666773\nE001-00000099\nfecha de emision 2026-09-01\nUS$\n"
        "Sub Total: US$ 1,000\nI.G.V.: 180\nImporte Total: US$ 1,180.00",
        "RUC: 2055566677\nsin serie\nFecha de emisión: 31/02/2026",
        "", "Señor(es) º ª ¿?\nRUC:20555666773 fº01-1",
    ]
    py = _python([procesar(leer_texto(t), [], HOY, "texto") for t in textos], textos)
    assert py == _js("texto", textos, tmp_path)


def test_validacion_de_lo_que_lee_la_ia_igual(tmp_path):
    salidas = [
        {"ruc_emisor": "20555666773", "ruc_cliente": "20601234565", "serie": "f001",
         "numero": "123", "fecha": "2026-09-01", "moneda": "pen",
         "base": 1000, "igv": 180, "total": 1180},
        {"ruc_emisor": "20555666773", "serie": "F001", "numero": "124",
         "fecha": "01/09/2026", "moneda": "USD", "base": "1,000.00",
         "igv": "180.00", "total": 1180.5},
        {"ruc_emisor": "20555666773", "serie": "F001", "numero": "125",
         "fecha": "2026-09-01", "moneda": "PEN", "base": 3094.92,
         "igv": 557.09, "total": ""},
    ]
    registro: list[str] = []
    py = _python([procesar(desde_ia(s), registro, HOY, "ia") for s in salidas],
                 [""] * len(salidas))
    assert py == _js("ia", salidas, tmp_path)


def test_si_la_ia_falla_la_factura_va_a_revision_con_el_motivo(tmp_path):
    (r,) = _js("ia", [None], tmp_path)
    assert r["estado"] == "revision"
    assert r["errores"] == ["la IA no pudo leer la factura"]
    assert r["fila"]["observaciones"] == "la IA no pudo leer la factura"
    assert r["factura"]["ruc_emisor"] == "20555666773"   # conserva lo que sí se leyó
