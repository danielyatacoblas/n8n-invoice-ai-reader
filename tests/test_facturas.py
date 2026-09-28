"""Tests de la lectura y validación de facturas."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.facturas import (a_centimos, clave, desde_ia, fecha_iso,  # noqa: E402
                          fila_hoja, leer_texto, procesar, ruc_valido)

HOY = "2026-09-15"
FACTURA = """DISTRIBUIDORA ANDINA S.A.C.
RUC: 20555666773
FACTURA ELECTRÓNICA
F001-00001000
Fecha de emisión: 12/07/2026
Señor(es): COMERCIAL DEMO LIMA S.A.C.
RUC: 20601234565
Moneda: SOLES
3 Tóner HP 85A S/ 657.00
Op. Gravada: S/ 3,094.00
IGV (18%): S/ 556.92
Importe Total: S/ 3,650.92
"""


def correcta(**cambios):
    f = {"ruc_emisor": "20555666773", "ruc_cliente": "20601234565", "serie": "F001",
         "numero": "00001000", "fecha": "2026-07-12", "moneda": "PEN",
         "base": 309400, "igv": 55692, "total": 365092}
    f.update(cambios)
    return f


# ── montos ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,centimos", [
    ("3,650.92", 365092), ("1180", 118000), ("1180.5", 118050),
    ("0.07", 7), (1180.0, 118000), ("1,000,000.00", 100000000),
    ("1180.004", 118000),
])
def test_montos_a_centimos(texto, centimos):
    assert a_centimos(texto) == centimos


@pytest.mark.parametrize("texto", [None, "", "abc", "12,34,5.6.7", "-50"])
def test_montos_invalidos(texto):
    assert a_centimos(texto) is None


# ── RUC ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ruc", ["20555666773", "20601234565", "10456789124"])
def test_ruc_con_digito_verificador_correcto(ruc):
    assert ruc_valido(ruc)


@pytest.mark.parametrize("ruc,motivo", [
    ("20555666774", "dígito verificador"),
    ("2055566677", "10 dígitos"),
    ("30555666773", "prefijo que no existe"),
    ("", "vacío"), (None, "ausente"),
])
def test_ruc_invalido(ruc, motivo):
    assert not ruc_valido(ruc), motivo


# ── fechas ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,iso", [
    ("12/07/2026", "2026-07-12"), ("1-9-2026", "2026-09-01"),
    ("2026-09-01", "2026-09-01"), ("31/02/2026", None), ("hoy", None),
])
def test_fechas(texto, iso):
    assert fecha_iso(texto) == iso


# ── lectura ────────────────────────────────────────────────────────────────

def test_lee_todos_los_campos():
    f = leer_texto(FACTURA)
    assert f == correcta()


def test_el_primer_ruc_es_el_emisor_y_el_segundo_el_cliente():
    f = leer_texto(FACTURA)
    assert f["ruc_emisor"] == "20555666773"
    assert f["ruc_cliente"] == "20601234565"


def test_el_18_de_la_etiqueta_del_igv_no_se_toma_como_monto():
    assert leer_texto("IGV (18%): S/ 556.92")["igv"] == 55692


def test_subtotal_no_se_confunde_con_total():
    f = leer_texto("SUB TOTAL: S/ 100.00\nI.G.V.: S/ 18.00\nTOTAL: S/ 118.00")
    assert (f["base"], f["igv"], f["total"]) == (10000, 1800, 11800)


def test_dolares():
    assert leer_texto("Moneda: DÓLARES AMERICANOS\nTotal: US$ 10.00")["moneda"] == "USD"


def test_serie_se_completa_a_8_digitos():
    f = leer_texto("F002-123")
    assert (f["serie"], f["numero"]) == ("F002", "00000123")


# ── decisión ───────────────────────────────────────────────────────────────

def test_factura_correcta_se_registra_y_entra_al_registro():
    registro = []
    r = procesar(correcta(), registro, HOY, "texto")
    assert r["estado"] == "registrada"
    assert registro == ["20555666773-F001-00001000"]


def test_la_misma_factura_dos_veces_es_duplicada():
    registro = []
    procesar(correcta(), registro, HOY, "texto")
    assert procesar(correcta(), registro, HOY, "texto")["estado"] == "duplicada"


def test_una_factura_con_errores_no_entra_al_registro():
    """Si se corrige y se reenvía, no debe marcarse como duplicada."""
    registro = []
    procesar(correcta(igv=1), registro, HOY, "texto")
    assert registro == []


@pytest.mark.parametrize("cambios,error", [
    ({"ruc_emisor": "20555666774"}, "RUC del emisor inválido"),
    ({"ruc_cliente": "20555666773"}, "factura emitida a otro RUC"),
    ({"fecha": "2026-09-16"}, "fecha de emisión en el futuro"),
    ({"igv": 60000, "total": 369400}, "el IGV no es el 18 % de la base"),
    ({"total": 365000}, "el total no es base + IGV"),
])
def test_cada_regla_manda_a_revision(cambios, error):
    r = procesar(correcta(**cambios), [], HOY, "texto")
    assert r["estado"] == "revision"
    assert r["errores"] == [error]


def test_un_centimo_de_redondeo_se_acepta():
    assert procesar(correcta(igv=55693, total=365093), [], HOY, "texto")["estado"] == "registrada"


def test_si_el_pdf_no_trae_un_dato_lo_intenta_la_ia():
    r = procesar(correcta(total=None), [], HOY, "texto")
    assert r["estado"] == "faltan_datos"
    assert r["faltantes"] == ["total"]


def test_si_a_la_ia_tambien_le_falta_va_a_revision():
    r = procesar(correcta(total=None), [], HOY, "ia")
    assert r["estado"] == "revision"
    assert r["errores"] == ["faltan datos: total"]


def test_factura_sin_ruc_de_cliente_no_se_rechaza_por_eso():
    assert procesar(correcta(ruc_cliente=None), [], HOY, "texto")["estado"] == "registrada"


# ── IA ─────────────────────────────────────────────────────────────────────

def test_normaliza_la_salida_de_la_ia():
    f = desde_ia({"ruc_emisor": "20555666773 ", "ruc_cliente": "20601234565",
                  "serie": "f001", "numero": "1000", "fecha": "12/07/2026",
                  "moneda": "pen", "base": 3094, "igv": "556.92", "total": "3,650.92"})
    assert f == correcta()


def test_la_ia_con_moneda_desconocida_deja_el_campo_vacio():
    assert desde_ia({"moneda": "soles peruanos"})["moneda"] is None


# ── hoja ───────────────────────────────────────────────────────────────────

def test_fila_de_la_hoja_en_soles():
    fila = fila_hoja(procesar(correcta(), [], HOY, "texto"))
    assert fila["total"] == "3650.92"
    assert fila["clave"] == clave(correcta())
    assert fila["observaciones"] == ""
