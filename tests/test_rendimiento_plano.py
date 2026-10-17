"""Redibujo del lienzo con índices espaciales y sin recalcular lo que no cambió (pedido del
usuario 2026-10-16: «los mismos resultados con menos recursos de PC», sobre todo con muchas
utilidades). Las celdas de `nucleo/indice_plano` solo proponen candidatos: con ellas o
comparando todo con todo el resultado es EL MISMO. `nucleo/memo_modelo` reusa lo que depende
solo del modelo mientras su firma no cambie; con cualquier cambio se recalcula."""
import copy
import math
import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import indice_plano, memo_modelo, model_ops  # noqa: E402


def _inter(p1, p2, p3, p4):
    """La prueba de cruce de `model_ops.choques_sin_conexion` y `_draw_pipe_conflicts`."""
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p1, p2, p3, p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    if not (-1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6):
        return None
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _todo_con_todo(monkeypatch):
    """Los índices sin filtrar: cada par de tramos y cada punto son candidatos (el código viejo)."""
    monkeypatch.setattr(indice_plano, "pares_tramos",
                        lambda segs: [(a, b) for a in range(len(segs)) for b in range(a + 1, len(segs))])
    monkeypatch.setattr(indice_plano.IndicePuntos, "en_caja", lambda self, x, y, r: list(range(len(self.puntos))))


# ─────────────────────────── núcleo puro ───────────────────────────

def test_pares_tramos_no_pierde_ningun_cruce():
    rng = random.Random(5)
    for prueba in range(30):
        q = (lambda v: round(v / 20) * 20) if prueba % 2 else (lambda v: v)   # puntas compartidas / libres
        segs = []
        for _ in range(rng.randint(2, 120)):
            a = (q(rng.uniform(0, 3000)), q(rng.uniform(0, 2000)))
            ang, L = rng.uniform(0, 2 * math.pi), rng.choice([0.0, 1e-4, rng.uniform(1, 600)])
            segs.append((a, (q(a[0] + L * math.cos(ang)), q(a[1] + L * math.sin(ang)))))
        segs += [((0.0, 0.0), (100.0, 0.0)), ((100.0, 0.0), (100.0, 50.0)),     # se tocan en la punta
                 ((50.0, -1e-7), (50.0, 30.0))]                                 # roza por 1e-7
        pares = indice_plano.pares_tramos(segs)
        assert pares == sorted(set(pares)) and all(a < b for a, b in pares)
        con_cruce = {(a, b) for a in range(len(segs)) for b in range(a + 1, len(segs))
                     if _inter(*segs[a], *segs[b]) is not None}
        assert con_cruce <= set(pares)


def test_indice_de_puntos_igual_que_recorrer_todos():
    rng = random.Random(8)
    pts = [(rng.uniform(-500, 500), rng.uniform(-500, 500)) for _ in range(400)] + [(0.0, 0.0), (3.0, 4.0)]
    ind = indice_plano.IndicePuntos(pts, 7.0)
    for x, y, r in [(0.0, 0.0, 5.0), (0.0, 0.0, 4.999)] + [(rng.uniform(-520, 520), rng.uniform(-520, 520),
                                                            rng.uniform(0, 90)) for _ in range(300)]:
        assert ind.en_radio(x, y, r) == [i for i, (px, py) in enumerate(pts)
                                         if (px - x) ** 2 + (py - y) ** 2 <= r * r]


def _estrellas(semilla, tol):
    """Uniones de 3–8 tramos de agua/gas con las puntas corridas hasta ~tol (grupos que se tocan)."""
    rng = random.Random(semilla)
    pipes = []
    for _ in range(40):
        cx, cy = rng.uniform(100, 2900), rng.uniform(100, 2100)
        for k in range(rng.randint(3, 8)):
            ang = rng.uniform(0, 2 * math.pi)
            a = (cx + rng.uniform(-0.9, 0.9) * tol, cy + rng.uniform(-0.9, 0.9) * tol)
            b = (cx + 120 * math.cos(ang), cy + 120 * math.sin(ang))
            z = -6.0 if k % 3 else rng.choice([-6.0, -6.05, -6.3])
            pipes.append(dict(layer="AGUA" if k % 4 else "GAS", pts=[a, b] if k % 2 else [b, a],
                              inv_start=z, inv_end=z, diam=8.0))
    return pipes


def _azar(semilla, n=120):
    rng = random.Random(semilla)
    capas = ["AGUA", "GAS", "ELECTRICO", "DRENAJE", "TELECOM", "ALCANTARILLADO"]
    pipes = []
    for i in range(n):
        q = lambda v: round(v / 40) * 40                           # noqa: E731 (vértices compartidos)
        x, y = q(rng.uniform(0, 2000)), q(rng.uniform(0, 1500))
        pts = [(x, y)]
        for _ in range(rng.randint(1, 6)):
            x, y = q(x + rng.uniform(-250, 250)), q(y + rng.uniform(-250, 250))
            pts.append((x, y))
        if len(set(pts)) < 2:
            continue
        z = rng.choice([-6.0, -4.0])
        pipes.append(dict(layer=capas[i % len(capas)], pts=pts, inv_start=z, inv_end=z, diam=8.0))
    return pipes


def _z_at(pipes):
    def z(i, k, x, y):
        p = pipes[i]
        return p.get("inv_start")
    return z


def test_juntas_y_choques_iguales_que_todo_con_todo(monkeypatch):
    casos = []
    for s in range(6):
        tol = random.Random(s).choice([3.15, 6.3, 0.0])
        for pipes in (_estrellas(s, max(tol, 1.0)), _azar(s)):
            casos.append((pipes, tol))
    nuevos = [(model_ops.junturas_excedidas(p, _z_at(p), tol), model_ops.choques_sin_conexion(p, _z_at(p), tol))
              for p, tol in casos]
    _todo_con_todo(monkeypatch)
    viejos = [(model_ops.junturas_excedidas(p, _z_at(p), tol), model_ops.choques_sin_conexion(p, _z_at(p), tol))
              for p, tol in casos]
    assert nuevos == viejos
    assert any(j for j, _c in nuevos) and any(c for _j, c in nuevos)    # los casos sí tienen juntas y choques


def test_memo_reusa_con_la_misma_firma_y_olvida_al_cambiar():
    m, llamadas = memo_modelo.Memo(), []

    def calc():
        llamadas.append(1)
        return [{"x": 1.0, "pts": [(0, 0)]}]
    m.usar(memo_modelo.firma([{"a": 1}], 2.0))
    v1 = m.obtener("k", calc)
    v1[0]["x"] = 99.0                                  # quien recibe una copia puede cambiarla
    assert m.obtener("k", calc) == [{"x": 1.0, "pts": [(0, 0)]}] and len(llamadas) == 1
    m.usar(memo_modelo.firma([{"a": 1}], 2.0))         # misma firma: sigue
    m.obtener("k", calc)
    assert len(llamadas) == 1
    m.usar(memo_modelo.firma([{"a": 2}], 2.0))         # cambió el modelo: se recalcula
    m.obtener("k", calc)
    assert len(llamadas) == 2
    m.usar(None)                                       # sin firma: nunca se reusa
    m.obtener("k", calc); m.obtener("k", calc)
    assert len(llamadas) == 4


def test_copia_igual_a_deepcopy():
    from nucleo.normas_validar import Aviso
    v = [Aviso(1.0, 2.0, "angulo", "m", 3, "i"), {"a": [1, (2, [3])], "b": (4, 5)}, (1, {"c": [2]}), "x", None]
    c = memo_modelo.copia(v)
    assert c == copy.deepcopy(v)
    c[0].aprobado = True; c[1]["a"][1][1].append(9); c[2][1]["c"].append(7)
    assert v == copy.deepcopy(memo_modelo.copia(v)) and not getattr(v[0], "aprobado", False)
    assert v[1]["a"][1][1] == [3] and v[2][1]["c"] == [2]


# ─────────────────────────── ventana real ───────────────────────────

@pytest.fixture
def win(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.resize(1400, 900)
    hoja = dict(name="ARCH E", w_pt=48 * 72.0, h_pt=36 * 72.0, ft_per_inch=40.0, scale_ft_per_pt=40 / 72.0,
                unit="in", landscape=True)
    w.blank_canvas = True
    w.paper = dict(hoja)
    w._load_blank_page(hoja)
    w._info = lambda *a, **k: None
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _foto(w):
    w._redraw()
    r = {k: list(getattr(w, k, [])) for k in ("_conflict_hits", "_exceso_hits", "_escalon_hits", "_codos_hits",
                                              "_retorno_hits", "_choque_hits")}
    r["conflictos"] = [(c.id, c.x, c.y, c.titulo, c.mensaje) for c in getattr(w, "_conflictos", [])]
    r["avisos"] = [(a.clase, a.mensaje, a.pipe, a.x, a.y, a.info) for a in w._normas_avisos]
    r["accesorios"] = [(a["tipo"], a["angulo"], a["pipes"], a["x"], a["y"]) for a in w._accesorios]
    items = []
    for it in w._overlay:
        try:
            items.append((type(it).__name__, round(it.pos().x(), 6), round(it.pos().y(), 6), it.toolTip()))
        except RuntimeError:
            pass
    r["items"] = sorted(items, key=repr)
    return r


def _cargar(w, pipes):
    w.pipes.extend(pipes)
    w._rebuild_structures()
    w._refresh_lists()


def test_lienzo_igual_con_indices_que_todo_con_todo(win, monkeypatch):
    tol = 0.5 / win.scale * win.zoom
    _cargar(win, _azar(3, 90) + _estrellas(4, tol)[:120])
    nuevo = _foto(win)
    assert nuevo["_conflict_hits"] and nuevo["_choque_hits"] and nuevo["_exceso_hits"] and nuevo["accesorios"]
    _todo_con_todo(monkeypatch)
    win._memo_redibujo = None
    assert _foto(win) == nuevo


def test_lienzo_no_recalcula_si_nada_cambio(win, monkeypatch):
    _cargar(win, _azar(7, 60))
    llamadas = []
    original = model_ops.choques_sin_conexion
    monkeypatch.setattr(model_ops, "choques_sin_conexion", lambda *a, **k: llamadas.append(1) or original(*a, **k))
    primero = _foto(win)
    win.sel_pipe = 3                                   # elegir otra utilidad: el modelo no cambió
    win._redraw()
    win.sel_pipe = -1
    assert _foto(win) == primero and len(llamadas) == 1
    p = next(p for p in win.pipes if len(p["pts"]) >= 2)
    p["inv_start"] = -9.37                             # un cambio del modelo: se recalcula
    x, y = p["pts"][-1]
    p["pts"][-1] = (x + 13.0, y - 7.0)
    cambiado = _foto(win)
    assert len(llamadas) == 2
    win._memo_redibujo = None                          # = calcular de cero
    assert _foto(win) == cambiado


# ───────────────── ratón (hover, imán, clic) y deshacer liviano ─────────────────

def test_indice_de_utilidades_no_pierde_ninguna():
    rng = random.Random(11)
    pipes = _azar(5, 150) + [dict(layer="AGUA", pts=[(10.0, 10.0)]), dict(layer="AGUA", pts=[]),
                             dict(layer="GAS", pts=[[500, 500], [500, 500]])]       # punto suelto, vacía, de largo 0
    ix = indice_plano.IndiceUtilidades(pipes)
    for _ in range(400):
        x, y, r = rng.uniform(-50, 2100), rng.uniform(-50, 1600), rng.choice([0.0, 3.0, 12.0, 40.0])
        cerca = set(ix.cerca(x, y, r))
        for i, p in enumerate(pipes):
            pts = p["pts"]
            if any(model_ops_dist(x, y, a, b) <= r for a, b in zip(pts, pts[1:])):
                assert i in cerca
    assert ix.vigente(pipes)
    pipes[3]["pts"][1] = (pipes[3]["pts"][1][0] + 0.001, pipes[3]["pts"][1][1])   # un punto movido
    assert not ix.vigente(pipes)


def model_ops_dist(x, y, a, b):
    import math as m
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
    return m.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def test_raton_igual_con_indice_que_recorriendo_todas(win, monkeypatch):
    from PySide6 import QtCore
    _cargar(win, _azar(9, 120) + [dict(layer="ELECTRICO", pts=[(300.0, 300.0), (420.0, 300.0), (420.0, 420.0),
                                                               (600.0, 450.0)], diam=4.0)])
    win._redraw()
    rng = random.Random(2)
    puntos = []
    for _ in range(250):                                   # cerca de vértices y tramos, y al azar
        p = rng.choice(win.pipes)
        a, b = rng.choice(list(zip(p["pts"], p["pts"][1:])))
        t = rng.random()
        puntos.append((a[0] + t * (b[0] - a[0]) + rng.uniform(-9, 9), a[1] + t * (b[1] - a[1]) + rng.uniform(-9, 9)))
        puntos.append((rng.uniform(0, 2000), rng.uniform(0, 1500)))

    def foto():
        r = []
        for x, y in puntos:
            win._update_hover_tooltip(x, y)
            r.append((win.canvas.toolTip(), win._pipe_at(x, y), win._vertice_bajo_clic(x, y),
                      [win._pipe_soft_snap(x, y, layer=c) for c in ("AGUA", "GAS", "ELECTRICO", "DRENAJE")]))
        return r
    win._pipe_at(0, 0); win._pipe_at(0, 0)                 # misma geometría dos veces: se arma el índice
    assert win._cache_raton.get("indice") is not None
    nuevo = foto()
    monkeypatch.setattr(indice_plano, "utilidades_cerca", lambda cache, pipes, x, y, r: range(len(pipes)))
    assert foto() == nuevo
    assert any(n[0] for n in nuevo) and any(n[1] >= 0 for n in nuevo) and any(n[2] for n in nuevo)
    assert any(h for n in nuevo for h in n[3])
    del QtCore


def test_raton_con_geometria_cambiada_sin_redibujar(win):
    _cargar(win, _azar(4, 40))
    p = win.pipes[0]
    win._pipe_at(*p["pts"][0]); win._pipe_at(*p["pts"][0])
    assert win._pipe_at(*p["pts"][0]) == 0
    x, y = 5000.0, 5000.0                                  # se mueve a un lugar vacío sin redibujar
    p["pts"][:] = [(x, y), (x + 50, y)]
    assert win._pipe_at(x + 25, y) == 0                    # el índice viejo no sirve: se nota y se rehace


def test_deshacer_liviano_mismo_estado_y_menos_memoria():
    import pickle
    from nucleo import deshacer
    from nucleo.duct_bank import DuctBank
    pipes = _azar(1, 300)
    estado = dict(cur_pts=[(1.0, 2.0)], pipes=pipes, structures=[{"x": 1.0, "y": 2.0, "xdata": {"a": [1]}}],
                  duct_banks=[DuctBank()], normas_aprobados=[], leaders=[], text_marks=[], erase_regions=[],
                  cross_connections=[{"x": 1.0, "pipe_a": 0, "pipe_b": 1}])
    pasos, anterior = [], None
    for k in range(30):
        pasos.append((copy.deepcopy(estado), deshacer.paso(estado, anterior)))
        anterior = pasos[-1][1]
        pipes[k % len(pipes)]["inv_start"] = -1.0 - k            # cada paso cambia UNA utilidad
    for viejo, p in pasos:
        assert deshacer.abrir(p) == viejo
    abierto = deshacer.abrir(pasos[0][1])
    abierto["pipes"][0]["pts"].append((0.0, 0.0))               # independiente del paso y del modelo
    assert deshacer.abrir(pasos[0][1]) == pasos[0][0]
    unicos = {id(b): len(b) for _v, p in pasos for b in p.blobs()}
    entero = sum(len(pickle.dumps(v)) for v, _p in pasos)
    assert sum(unicos.values()) * 10 < entero                   # ≥10× menos que copiar todo cada vez


def test_deshacer_con_objetos_compartidos_como_deepcopy():
    from nucleo import deshacer
    comun = [(0.0, 0.0), (5.0, 5.0)]
    estado = dict(pipes=[{"pts": comun}, {"pts": comun}], cur_pts=[])
    a = deshacer.abrir(deshacer.paso(estado))
    b = copy.deepcopy(estado)
    assert a == b and (a["pipes"][0]["pts"] is a["pipes"][1]["pts"]) == (b["pipes"][0]["pts"] is b["pipes"][1]["pts"])


def test_deshacer_en_la_ventana(win):
    _cargar(win, _azar(6, 50))
    antes = copy.deepcopy(win.pipes)
    win._push()
    win.pipes[3]["pts"][1] = (1.0, 1.0)
    del win.pipes[7]
    despues = copy.deepcopy(win.pipes)
    win.undo()
    assert win.pipes == antes
    win.redo()
    assert win.pipes == despues


def test_rebuild_structures_igual_que_todo_con_todo(monkeypatch):
    """Los buzones por vértice salen por celdas: mismos puntos (el primero gana) y las mismas
    ediciones reasignadas que comparando con todos."""
    rng = random.Random(4)
    pipes = []
    for i in range(160):
        x, y = round(rng.uniform(0, 2000) / 20) * 20, round(rng.uniform(0, 1500) / 20) * 20
        pts = [(x, y)]
        for _ in range(rng.randint(1, 6)):
            x, y = x + rng.choice([-13.9, -14.0, 7.0, 20.0, 40.0]), y + rng.choice([0.0, 14.0, -20.0])
            pts.append((x, y))
        pipes.append(dict(layer=["DRENAJE", "ALCANTARILLADO", "ELECTRICO"][i % 3], pts=pts))
    st = model_ops.rebuild_structures(pipes, [])
    tol = model_ops._TOL
    esperado = []                                          # el recorrido de siempre: el primero gana
    for p in pipes:
        if p["layer"] == "ELECTRICO":
            continue
        for pt in p["pts"]:
            if not any(math.hypot(pt[0] - q[0], pt[1] - q[1]) <= tol for q in esperado):
                esperado.append(pt)
    assert [(s["x"], s["y"]) for s in st if s.get("net") == "gravity"] == esperado
    for k, s in enumerate(st):
        s.update(rim=k, cod=f"BZ-{500 + k}")
        s["x"] += rng.uniform(-10, 10)
    nuevo = model_ops.rebuild_structures(pipes, st)
    monkeypatch.setattr(indice_plano.IndicePuntos, "en_caja", lambda self, x, y, r: list(range(len(self.puntos))))
    assert model_ops.rebuild_structures(pipes, st) == nuevo
