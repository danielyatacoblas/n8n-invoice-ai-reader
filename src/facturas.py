"""Lectura y validación de facturas electrónicas peruanas.

Es la misma lógica que corre en los nodos Code de n8n
(workflows/src/validar_factura.js); tests/test_paridad_js.py verifica que ambas
copias den el mismo resultado.

Los montos se manejan en céntimos enteros: con decimales, Python y JavaScript
pueden redondear distinto y 0.1 + 0.2 no siempre da 0.3.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

RUC_EMPRESA = "20601234565"        # a quién deben venir dirigidas las facturas
TASA_IGV = 18                      # por ciento
TOLERANCIA = 1                     # céntimos de diferencia aceptados por redondeo
FACTORES_RUC = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
CAMPOS = ["ruc_emisor", "serie", "numero", "fecha", "moneda",
          "base", "igv", "total"]

# Etiquetas que usan los distintos sistemas de facturación para cada monto.
# El orden importa: primero las más específicas.
ETIQUETAS = {
    "base": ["op. gravada", "op gravada", "operacion gravada", "valor de venta",
             "sub total", "subtotal"],
    "igv": ["igv", "i.g.v."],
    "total": ["importe total", "total a pagar", "total"],
}
MONTO = r"(?:s/|us\$|\$|pen|usd)?\s*(\d[\d,]*(?:\.\d{1,2})?)"


# ── utilidades ─────────────────────────────────────────────────────────────

def plano(texto: str) -> str:
    """Minúsculas y sin tildes, para buscar etiquetas escritas de cualquier forma."""
    t = unicodedata.normalize("NFD", texto or "")
    return re.sub("[̀-ͯ]", "", t).lower()


def a_centimos(valor) -> int | None:
    """'1,234.5' → 123450. Devuelve None si no es un monto válido."""
    if valor is None:
        return None
    t = str(valor).strip().replace(",", "")
    m = re.fullmatch(r"(\d+)(?:\.(\d{1,2}))?", t)
    if not m:
        m = re.fullmatch(r"(\d+)\.(\d+)", t)        # 1180.004 de un modelo de IA
        if not m:
            return None
    decimales = (m.group(2) or "").ljust(2, "0")[:2]
    return int(m.group(1)) * 100 + int(decimales)


def ruc_valido(ruc: str) -> bool:
    """Dígito verificador de SUNAT (módulo 11) y prefijo de contribuyente."""
    if not re.fullmatch(r"\d{11}", ruc or "") or ruc[:2] not in ("10", "15", "17", "20"):
        return False
    resto = 11 - sum(int(d) * f for d, f in zip(ruc, FACTORES_RUC)) % 11
    verificador = {10: 0, 11: 1}.get(resto, resto)
    return int(ruc[10]) == verificador


def fecha_iso(texto: str) -> str | None:
    """Acepta dd/mm/aaaa, dd-mm-aaaa o aaaa-mm-dd. None si la fecha no existe."""
    t = (texto or "").strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", t)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
        if not m:
            return None
        a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(a, mes, d).isoformat()
    except ValueError:
        return None


def clave(f: dict) -> str:
    """Identifica una factura: el mismo emisor no repite serie y número."""
    if not f.get("ruc_emisor") or not f.get("serie") or not f.get("numero"):
        return ""
    return f"{f['ruc_emisor']}-{f['serie']}-{f['numero']}"


# ── lectura del texto del PDF ──────────────────────────────────────────────

def _monto(texto_plano: str, etiquetas: list[str]) -> int | None:
    for etiqueta in etiquetas:
        patron = (r"(?:^|\n)[ \t]*" + re.escape(etiqueta) +
                  r"[^\n\d]*?(?:\(\s*18\s*%\s*\))?[ \t]*:?[ \t]*" + MONTO)
        m = re.search(patron, texto_plano)
        if m:
            return a_centimos(m.group(1))
    return None


def leer_texto(texto: str) -> dict:
    """Extrae los campos de una factura a partir del texto del PDF."""
    p = plano(texto)
    rucs = re.findall(r"r\.?\s*u\.?\s*c\.?[^\d\n]{0,6}(\d{11})", p)
    # Lookarounds en vez de \b: en Python \b entiende Unicode y en JavaScript
    # no, y la paridad con el nodo de n8n se rompería con símbolos como "º".
    serie = re.search(r"(?<![a-z0-9])([fe][a-z0-9]{3})\s*-\s*(\d{1,8})(?![0-9])", p)
    fecha = re.search(r"fecha\s*(?:de\s*)?emision[^\d\n]*"
                      r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{2}-\d{2})", p)
    if re.search(r"dolar|us\$|(?<![a-z])usd(?![a-z])", p):
        moneda = "USD"
    elif re.search(r"(?<![a-z])soles(?![a-z])|s/|(?<![a-z])pen(?![a-z])", p):
        moneda = "PEN"
    else:
        moneda = None
    return {
        "ruc_emisor": rucs[0] if rucs else None,
        "ruc_cliente": rucs[1] if len(rucs) > 1 else None,
        "serie": serie.group(1).upper() if serie else None,
        "numero": serie.group(2).zfill(8) if serie else None,
        "fecha": fecha_iso(fecha.group(1)) if fecha else None,
        "moneda": moneda,
        "base": _monto(p, ETIQUETAS["base"]),
        "igv": _monto(p, ETIQUETAS["igv"]),
        "total": _monto(p, ETIQUETAS["total"]),
    }


def desde_ia(salida: dict) -> dict:
    """Normaliza lo que devolvió el extractor de IA al mismo formato."""
    def texto(k):
        v = salida.get(k)
        return None if v in (None, "") else str(v).strip()
    moneda = (texto("moneda") or "").upper()
    numero = re.sub(r"\D", "", texto("numero") or "")
    ruc_e = re.sub(r"\D", "", texto("ruc_emisor") or "")
    ruc_c = re.sub(r"\D", "", texto("ruc_cliente") or "")
    return {
        "ruc_emisor": ruc_e or None,
        "ruc_cliente": ruc_c or None,
        "serie": (texto("serie") or "").upper() or None,
        "numero": numero.zfill(8) if numero else None,
        "fecha": fecha_iso(texto("fecha") or ""),
        "moneda": moneda if moneda in ("PEN", "USD") else None,
        "base": a_centimos(texto("base")),
        "igv": a_centimos(texto("igv")),
        "total": a_centimos(texto("total")),
    }


# ── validación ─────────────────────────────────────────────────────────────

def validar(f: dict, hoy: str) -> list[str]:
    """Reglas de negocio. Devuelve la lista de problemas (vacía si está bien)."""
    errores = []
    if not ruc_valido(f["ruc_emisor"]):
        errores.append("RUC del emisor inválido")
    if f.get("ruc_cliente") and f["ruc_cliente"] != RUC_EMPRESA:
        errores.append("factura emitida a otro RUC")
    if f["fecha"] > hoy:
        errores.append("fecha de emisión en el futuro")
    igv_esperado = (f["base"] * TASA_IGV + 50) // 100
    if abs(f["igv"] - igv_esperado) > TOLERANCIA:
        errores.append("el IGV no es el 18 % de la base")
    if abs(f["base"] + f["igv"] - f["total"]) > TOLERANCIA:
        errores.append("el total no es base + IGV")
    return errores


def procesar(f: dict, registro: list[str], hoy: str, origen: str) -> dict:
    """Decide el estado de una factura ya leída.

    origen = "texto" (leída del PDF) o "ia" (leída por el modelo).
    Estados: registrada, duplicada, revision, faltan_datos.
    """
    faltantes = [c for c in CAMPOS if f.get(c) in (None, "")]
    resultado = {"estado": "", "origen": origen, "factura": f,
                 "clave": clave(f), "faltantes": faltantes, "errores": []}

    if faltantes:
        if origen == "texto":
            # El PDF no se pudo leer completo: que lo intente la IA
            resultado["estado"] = "faltan_datos"
        else:
            resultado["estado"] = "revision"
            resultado["errores"] = ["faltan datos: " + ", ".join(faltantes)]
        return resultado

    if resultado["clave"] in registro:
        resultado["estado"] = "duplicada"
        return resultado

    errores = validar(f, hoy)
    resultado["errores"] = errores
    resultado["estado"] = "revision" if errores else "registrada"
    if not errores:
        registro.append(resultado["clave"])
    return resultado


def fila_hoja(r: dict) -> dict:
    """Lo que se escribe en Google Sheets (montos en soles, no en céntimos)."""
    f = r["factura"]
    def soles(c):
        return "" if c is None else f"{c // 100}.{c % 100:02d}"
    return {
        "clave": r["clave"], "estado": r["estado"],
        "ruc_emisor": f.get("ruc_emisor") or "", "serie": f.get("serie") or "",
        "numero": f.get("numero") or "", "fecha": f.get("fecha") or "",
        "moneda": f.get("moneda") or "", "base": soles(f.get("base")),
        "igv": soles(f.get("igv")), "total": soles(f.get("total")),
        "leida_por": r["origen"], "observaciones": "; ".join(r["errores"]),
    }
