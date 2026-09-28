"""Las facturas generadas cubren cada regla: todas deben dar el resultado esperado."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from evaluar_lectura import ESPERADO, evaluar  # noqa: E402


@pytest.mark.skipif(not ESPERADO.exists(), reason="corre antes: python scripts/generar_facturas.py")
def test_todas_las_facturas_generadas_dan_lo_esperado():
    r = evaluar()
    assert not r["fallos"], "\n".join(r["fallos"])


@pytest.mark.skipif(not ESPERADO.exists(), reason="corre antes: python scripts/generar_facturas.py")
def test_el_conjunto_de_prueba_cubre_todos_los_estados():
    estados = evaluar()["estados"]
    assert all(estados[e] >= 2 for e in ("registrada", "revision", "duplicada", "faltan_datos"))
