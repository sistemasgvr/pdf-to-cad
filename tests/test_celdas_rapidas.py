"""`model_ops._Celdas.en_caja` en recuadros ENORMES (reporte del usuario 2026-10-29: en la hoja compuesta de
DU06, elegir una utilidad tardaba ~1.5–5 s). El recuadro de una tubería larga abarca decenas de miles de celdas de
32 px casi todas vacías y cada curva del redibujo las recorría (`curve_vertex_indices`). Debe dar EXACTAMENTE lo
mismo que el recorrido celda por celda: mismos datos, mismo orden."""
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from nucleo import model_ops  # noqa: E402


def _celda_por_celda(cel, x0, y0, x1, y1):
    """El recorrido de antes (la referencia)."""
    c = cel.CELDA
    out = []
    for cx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
        for cy in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
            out.extend(cel.celdas.get((cx, cy), ()))
    out.sort(key=lambda e: e[0])
    return [d for _k, d in out]


def test_en_caja_igual_que_celda_por_celda():
    rnd = random.Random(7)
    entradas = [(rnd.uniform(-500, 20000), rnd.uniform(-300, 6000), k) for k in range(800)]
    cel = model_ops._Celdas(entradas)
    for _ in range(300):
        x0, y0 = rnd.uniform(-600, 20000), rnd.uniform(-400, 6000)
        ancho = rnd.choice((5.0, 60.0, 800.0, 25000.0))
        x1, y1 = x0 + ancho * rnd.random(), y0 + ancho * rnd.random()
        assert cel.en_caja(x0, y0, x1, y1) == _celda_por_celda(cel, x0, y0, x1, y1)


def test_curvas_en_recuadro_enorme_igual():
    rnd = random.Random(3)
    estr = [{"x": rnd.uniform(0, 30000), "y": rnd.uniform(0, 9000), "curve": rnd.random() < 0.7} for _ in range(400)]
    cvs = model_ops._Curvas(estr)
    caja = (-50.0, -50.0, 31000.0, 9100.0)
    esperado = [s for _k, s in sorted(_celda_por_celda(cvs, *caja), key=lambda e: e[0])]
    assert cvs.en_caja(*caja) == esperado


def test_recuadro_enorme_no_recorre_celdas_vacias():
    """Un recuadro de 10⁶ × 10⁶ px con pocas entradas: antes ~10⁹ celdas (no terminaba)."""
    import time
    cel = model_ops._Celdas([(10.0 * k, 5.0 * k, k) for k in range(50)])
    t = time.perf_counter()
    assert cel.en_caja(-1e6, -1e6, 1e6, 1e6) == list(range(50))
    assert time.perf_counter() - t < 0.05


def test_curve_vertex_indices_memorizado_en_el_redibujo_da_lo_mismo():
    """Dentro de `indice_vertices()` (el redibujo) el resultado se calcula una vez por tubería: el redibujo lo pedía
    una vez por CURVA (540 curvas → 16 mil búsquedas de vértice en la compuesta de DU06). Mismo resultado."""
    rnd = random.Random(11)
    pipes = [{"pts": [(rnd.uniform(0, 3000), rnd.uniform(0, 3000)) for _ in range(6)]} for _ in range(40)]
    estr = []
    for p in pipes[:30]:
        for q in p["pts"][1:-1]:
            estr.append({"x": q[0] + rnd.uniform(-3, 3), "y": q[1] + rnd.uniform(-3, 3), "curve": True})
    fuera = [model_ops.curve_vertex_indices(p, estr, pipes) for p in pipes]
    llamadas = []
    original = model_ops.nearest_vertex

    def contar(*a, **k):
        llamadas.append(1)
        return original(*a, **k)
    model_ops.nearest_vertex = contar
    try:
        with model_ops.indice_vertices():
            dentro = [model_ops.curve_vertex_indices(p, estr, pipes) for p in pipes]
            n1 = len(llamadas)
            otra_vez = [model_ops.curve_vertex_indices(p, estr, pipes) for p in pipes]
            assert len(llamadas) == n1                       # la 2.ª vez no busca nada
            otra_vez[0][999] = "x"                           # el que llama puede tocar su copia
            assert 999 not in model_ops.curve_vertex_indices(pipes[0], estr, pipes)
    finally:
        model_ops.nearest_vertex = original
    assert dentro == fuera and [dict((k, v) for k, v in d.items() if k != 999) for d in otra_vez] == fuera
