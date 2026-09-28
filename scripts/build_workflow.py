#!/usr/bin/env python3
"""Construye los workflows de n8n a partir del código fuente.

    python scripts/build_workflow.py

Genera:
  workflows/facturas_demo.json        subir un PDF por webhook, SIN credenciales
  workflows/facturas_produccion.json  Gmail + lectura + IA de respaldo + Sheets

Los dos nodos Code salen de workflows/src/validar_factura.js; lo único que
cambia entre ellos son los marcadores MODO y REGISTRO.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "workflows" / "src" / "validar_factura.js"
OUT = ROOT / "workflows"

ID_HOJA = {"__rl": True, "value": "REEMPLAZAR_ID_HOJA", "mode": "id"}

ATRIBUTOS_IA = [
    ("ruc_emisor", "RUC de 11 dígitos de quien EMITE la factura (el primero que aparece)."),
    ("ruc_cliente", "RUC de 11 dígitos del cliente, junto a 'Señor(es)'."),
    ("serie", "Serie de la factura, 4 caracteres, por ejemplo F001."),
    ("numero", "Número correlativo que va después de la serie y el guion."),
    ("fecha", "Fecha de emisión en formato AAAA-MM-DD."),
    ("moneda", "PEN si está en soles, USD si está en dólares."),
    ("base", "Operación gravada o valor de venta, solo el número."),
    ("igv", "Monto del IGV, solo el número."),
    ("total", "Importe total a pagar, solo el número."),
]

PROMPT_IA = (
    "Lees facturas electrónicas peruanas. Copia cada dato tal como aparece en "
    "el texto. Si un dato no aparece, déjalo vacío: NO lo calcules ni lo "
    "deduzcas de otros montos. Una factura con datos inventados es peor que "
    "una factura que va a revisión manual.")


def codigo(modo: str, registro: str) -> str:
    js = JS.read_text(encoding="utf-8")
    for marca in ("'__MODO__'", "'__REGISTRO__'"):
        if js.count(marca) != 1:
            raise SystemExit(f"se esperaba una sola vez {marca} en {JS}")
    return js.replace("'__MODO__'", f"'{modo}'").replace("'__REGISTRO__'", f"'{registro}'")


def _node(nid, name, ntype, tv, pos, params, extra=None):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype,
         "typeVersion": tv, "position": pos}
    if extra:
        n.update(extra)
    return n


def _link(*destinos, tipo="main"):
    return [{"node": d, "type": tipo, "index": 0} for d in destinos]


def _regla(valor: str, cid: str) -> dict:
    return {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "strict", "version": 2},
            "conditions": [{"id": cid, "leftValue": "={{ $json.estado }}",
                            "rightValue": valor,
                            "operator": {"type": "string", "operation": "equals"}}],
            "combinator": "and"},
        "renameOutput": True, "outputKey": valor}


def _fila(nid, nombre, pos):
    """Deja solo las columnas de la hoja."""
    return _node(nid, nombre, "n8n-nodes-base.set", 3.4, pos,
                 {"mode": "raw", "jsonOutput": "={{ JSON.stringify($json.fila) }}",
                  "options": {}})


def _append(nid, nombre, pestana, pos):
    return _node(nid, nombre, "n8n-nodes-base.googleSheets", 4.5, pos,
                 {"operation": "append", "documentId": ID_HOJA,
                  "sheetName": {"__rl": True, "value": pestana, "mode": "name"},
                  "columns": {"mappingMode": "autoMapInputData", "value": {}},
                  "options": {}})


def build_demo() -> dict:
    nodes = [
        _node("wh-1", "Webhook · Subir factura", "n8n-nodes-base.webhook", 2,
              [0, 0],
              {"httpMethod": "POST", "path": "factura-demo",
               "responseMode": "responseNode",
               "options": {"allowedOrigins": "*"}},
              {"webhookId": "factura-demo",
               "notes": "Recibe el PDF en el campo 'factura' (multipart/form-data)."}),
        _node("pdf-1", "Extraer texto del PDF", "n8n-nodes-base.extractFromFile", 1,
              [240, 0], {"operation": "pdf", "binaryPropertyName": "factura",
                         "options": {}}),
        _node("code-1", "Leer y validar factura", "n8n-nodes-base.code", 2,
              [480, 0], {"jsCode": codigo("texto", "memoria")}),
        _node("resp-1", "Responder", "n8n-nodes-base.respondToWebhook", 1.1,
              [720, 0], {"respondWith": "firstIncomingItem", "options": {}}),
    ]
    connections = {
        "Webhook · Subir factura": {"main": [_link("Extraer texto del PDF")]},
        "Extraer texto del PDF": {"main": [_link("Leer y validar factura")]},
        "Leer y validar factura": {"main": [_link("Responder")]},
    }
    return {"id": "facturasdemo", "name": "Lectura de facturas · DEMO sin credenciales",
            "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {},
            "meta": {"instanceId": "facturas-demo"}, "tags": []}


def build_prod() -> dict:
    nodes = [
        _node("gm-in", "Gmail · Factura recibida", "n8n-nodes-base.gmailTrigger", 1.2,
              [0, 300],
              {"pollTimes": {"item": [{"mode": "everyMinute"}]},
               "simple": False,
               "filters": {"q": "has:attachment filename:pdf"},
               "options": {"downloadAttachments": True}},
              {"notes": "Conviene usar una casilla o etiqueta solo para facturas "
                        "(por ejemplo facturas@empresa.pe)."}),
        _node("pdf-1", "Extraer texto del PDF", "n8n-nodes-base.extractFromFile", 1,
              [240, 300], {"operation": "pdf", "binaryPropertyName": "attachment_0",
                           "options": {}}),
        _node("gs-leer", "Sheets · Leer facturas", "n8n-nodes-base.googleSheets", 4.5,
              [480, 300],
              {"documentId": ID_HOJA,
               "sheetName": {"__rl": True, "value": "Facturas", "mode": "name"},
               "options": {}},
              {"executeOnce": True, "alwaysOutputData": True,
               "notes": "Solo para saber qué facturas ya están registradas."}),
        _node("code-1", "Leer y validar factura", "n8n-nodes-base.code", 2,
              [720, 300], {"jsCode": codigo("texto", "sheets")}),
        _node("sw-1", "¿Resultado?", "n8n-nodes-base.switch", 3.2,
              [960, 300],
              {"rules": {"values": [_regla("registrada", "e1"), _regla("revision", "e2"),
                                    _regla("duplicada", "e3"), _regla("faltan_datos", "e4")]},
               "options": {}}),
        _fila("set-ok", "Fila · registrada", [1200, 0]),
        _append("gs-ok", "Sheets · Registrar factura", "Facturas", [1440, 0]),
        _fila("set-rev", "Fila · revisión", [1200, 200]),
        _append("gs-rev", "Sheets · Anotar para revisión", "Revision", [1440, 200]),
        _node("gm-rev", "Gmail · Avisar a contabilidad", "n8n-nodes-base.gmail", 2.1,
              [1440, 360],
              {"sendTo": "REEMPLAZAR_CORREO_CONTABILIDAD",
               "subject": "=Factura para revisar: {{ $json.clave || 'sin identificar' }}",
               "emailType": "text",
               "message": "=Una factura recibida por correo no se registró.\n\n"
                          "Motivo: {{ $json.errores.join('; ') }}\n"
                          "Proveedor (RUC): {{ $json.factura.ruc_emisor || '-' }}\n"
                          "Comprobante: {{ $json.factura.serie || '-' }}-{{ $json.factura.numero || '-' }}\n"
                          "Total leído: {{ $json.fila.total || '-' }} {{ $json.factura.moneda || '' }}\n\n"
                          "Está en la pestaña Revision de la hoja de facturas.",
               "options": {"appendAttribution": False}}),
        _node("noop-dup", "Ya registrada · ignorar", "n8n-nodes-base.noOp", 1,
              [1200, 520], {}),
        _node("ia-1", "IA · Leer factura", "@n8n/n8n-nodes-langchain.informationExtractor", 1.2,
              [1200, 700],
              {"text": "={{ $json.texto }}",
               "schemaType": "fromAttributes",
               "attributes": {"attributes": [
                   {"name": n, "type": "string", "description": d, "required": False}
                   for n, d in ATRIBUTOS_IA]},
               "options": {"systemPromptTemplate": PROMPT_IA}},
              {"onError": "continueErrorOutput",
               "notes": "Solo se usa cuando el PDF no trae alguna etiqueta. "
                        "Si la IA falla, la factura va a revisión manual. "
                        "Lo que lee se vuelve a validar con las mismas reglas."}),
        _node("ia-m", "Modelo de IA", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2,
              [1200, 900],
              {"model": {"__rl": True, "value": "gpt-4o-mini", "mode": "list"},
               "options": {"temperature": 0}}),
        _node("code-2", "Validar lectura de la IA", "n8n-nodes-base.code", 2,
              [1440, 700], {"jsCode": codigo("ia", "sheets")}),
    ]
    connections = {
        "Gmail · Factura recibida": {"main": [_link("Extraer texto del PDF")]},
        "Extraer texto del PDF": {"main": [_link("Sheets · Leer facturas")]},
        "Sheets · Leer facturas": {"main": [_link("Leer y validar factura")]},
        "Leer y validar factura": {"main": [_link("¿Resultado?")]},
        "¿Resultado?": {"main": [
            _link("Fila · registrada"),
            _link("Fila · revisión", "Gmail · Avisar a contabilidad"),
            _link("Ya registrada · ignorar"),
            _link("IA · Leer factura"),
        ]},
        "Fila · registrada": {"main": [_link("Sheets · Registrar factura")]},
        "Fila · revisión": {"main": [_link("Sheets · Anotar para revisión")]},
        "IA · Leer factura": {"main": [
            _link("Validar lectura de la IA"),
            _link("Validar lectura de la IA"),
        ]},
        "Modelo de IA": {"ai_languageModel": [
            _link("IA · Leer factura", tipo="ai_languageModel")]},
        # Lo leído por la IA vuelve al mismo reparto. No hay bucle infinito:
        # en modo 'ia' el código nunca devuelve faltan_datos.
        "Validar lectura de la IA": {"main": [_link("¿Resultado?")]},
    }
    return {"id": "facturasprod", "name": "Lectura de facturas · producción",
            "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {},
            "meta": {"instanceId": "facturas-prod"}, "tags": []}


def main():
    for nombre, wf in (("facturas_demo.json", build_demo()),
                       ("facturas_produccion.json", build_prod())):
        ruta = OUT / nombre
        ruta.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
        print(f"ok  {ruta.relative_to(ROOT)} — {len(wf['nodes'])} nodos")


if __name__ == "__main__":
    main()
