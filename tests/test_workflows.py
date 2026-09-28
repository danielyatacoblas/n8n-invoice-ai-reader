"""Revisa los workflows generados: que se puedan importar y no filtren secretos."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = {p.name: json.loads(p.read_text(encoding="utf-8"))
             for p in (ROOT / "workflows").glob("*.json")}


def _conexiones(wf):
    for origen, salidas in wf["connections"].items():
        for ramas in salidas.values():
            for i, rama in enumerate(ramas):
                for destino in rama:
                    yield origen, i, destino["node"]


def test_existen_los_dos_workflows():
    assert set(WORKFLOWS) == {"facturas_demo.json", "facturas_produccion.json"}


@pytest.mark.parametrize("nombre", sorted(WORKFLOWS))
def test_conexiones_apuntan_a_nodos_existentes(nombre):
    wf = WORKFLOWS[nombre]
    nodos = {n["name"] for n in wf["nodes"]}
    assert len(nodos) == len(wf["nodes"]), "hay nodos con nombre repetido"
    for origen, _, destino in _conexiones(wf):
        assert origen in nodos and destino in nodos, f"{origen} → {destino}"


@pytest.mark.parametrize("nombre", sorted(WORKFLOWS))
def test_todo_nodo_esta_conectado(nombre):
    wf = WORKFLOWS[nombre]
    tocados = set()
    for origen, _, destino in _conexiones(wf):
        tocados.update((origen, destino))
    assert {n["name"] for n in wf["nodes"]} == tocados


@pytest.mark.parametrize("nombre", sorted(WORKFLOWS))
def test_no_hay_credenciales_ni_claves(nombre):
    texto = json.dumps(WORKFLOWS[nombre])
    assert "credentials" not in texto
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", texto)
    correos = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", texto)) - {"facturas@empresa.pe"}
    assert not correos, f"correo real en el workflow: {correos}"


def test_demo_no_necesita_credenciales():
    tipos = {n["type"] for n in WORKFLOWS["facturas_demo.json"]["nodes"]}
    assert tipos <= {"n8n-nodes-base.webhook", "n8n-nodes-base.extractFromFile",
                     "n8n-nodes-base.code", "n8n-nodes-base.respondToWebhook"}


def test_los_nodos_code_tienen_sus_marcadores_resueltos():
    for wf in WORKFLOWS.values():
        for n in wf["nodes"]:
            if n["type"] == "n8n-nodes-base.code":
                js = n["parameters"]["jsCode"]
                assert "__MODO__" not in js and "__REGISTRO__" not in js


def test_produccion_usa_la_hoja_para_detectar_duplicados():
    wf = WORKFLOWS["facturas_produccion.json"]
    codigos = [n["parameters"]["jsCode"] for n in wf["nodes"]
               if n["type"] == "n8n-nodes-base.code"]
    assert all("const REGISTRO = 'sheets';" in c for c in codigos)


def test_lo_que_lee_la_ia_se_vuelve_a_validar():
    wf = WORKFLOWS["facturas_produccion.json"]
    destinos = {(o, i): d for o, i, d in _conexiones(wf)}
    assert destinos[("IA · Leer factura", 0)] == "Validar lectura de la IA"
    assert destinos[("IA · Leer factura", 1)] == "Validar lectura de la IA"
    assert destinos[("Validar lectura de la IA", 0)] == "¿Resultado?"


def test_la_ia_no_puede_inventar_datos():
    wf = WORKFLOWS["facturas_produccion.json"]
    ia = next(n for n in wf["nodes"] if n["name"] == "IA · Leer factura")
    assert "NO lo calcules" in ia["parameters"]["options"]["systemPromptTemplate"]
    assert all(not a["required"] for a in ia["parameters"]["attributes"]["attributes"])
