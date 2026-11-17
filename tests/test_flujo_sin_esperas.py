"""Composición sugerida y reconocimiento de hojas compuestas grandes, sin trabajo repetido (pedido del usuario
2026-11-15, «Southwest Gas Combined 811 Records», 54 hojas: «que los tiempos de carga bajen… sin perder calidad»).

Cada atajo da EXACTAMENTE lo mismo que el camino de antes:
- las franjas del marco se dibujan de una sola lectura de la hoja (mismos píxeles que `page.get_pixmap`);
- `armar` usa el marco que ya calculó la ficha;
- `routes.join_emitted` mira «¿otra línea pasa por el nodo?» solo en las rutas de esa zona y, tras cada unión,
  solo los nodos de cerca (`_Pares`);
- `IndiceTramos` reparte los tramos cortos en sus celdas todos juntos (numpy), con las mismas cuentas;
- la punta de una línea solo mira los bordes (recortes, bóvedas) cuya caja la toca;
- «¿se ve el glifo de la válvula?» se dibuja igual, repartido en varios procesos cuando son muchos;
- un rótulo de diámetro de un mapa se mide solo contra los tramos de la línea que el índice da a su alcance;
- al importar y redibujar: válvulas repetidas, conflictos repetidos, números fijos y grupos de etiquetas por celdas;
- al exportar, cada rótulo del plano busca su utilidad solo entre las cercanas (`anotaciones.senala`);
- las piezas de un rótulo («81'» «3/4"» «STL» «`56») se buscan sin recorrer todas las de la hoja.
"""
import copy
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import fitz
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from hoja import borde_inclinado as BI  # noqa: E402
from hoja import texto_pdf  # noqa: E402
from reconocimiento import recognition_grosor_registros as GR  # noqa: E402
from reconocimiento import recognition_angulos_calc as AC  # noqa: E402
from reconocimiento import recognition_indice as RI  # noqa: E402
from reconocimiento import recognition_valvulas_tinta as VT  # noqa: E402
from reconocimiento import routes  # noqa: E402

RECT = (100.0, 100.0, 700.0, 500.0)


def _hoja_con_marco(abajo_izq=490.0, abajo_der=498.0):
    doc = fitz.open()
    pg = doc.new_page(width=800, height=600)
    for a, b in (((104, 104), (696, 104)), ((696, 104), (696, abajo_der)), ((696, abajo_der), (104, abajo_izq)),
                 ((104, abajo_izq), (104, 104))):
        pg.draw_line(a, b, color=(0, 0, 0), width=2.0)
    for k in range(12):                                   # algo de dibujo dentro
        pg.draw_line((150 + 40 * k, 150), (170 + 40 * k, 420), color=(0, 0.5, 0.5), width=0.5)
    doc = fitz.open(stream=doc.tobytes(), filetype="pdf")
    return doc, doc[0]


def test_franjas_de_una_sola_lectura_dan_los_mismos_pixeles():
    doc, page = _hoja_con_marco()
    for lado in ("top", "right", "bottom", "left"):
        directo = BI._franja(page, lado, RECT, 24.0, None)            # como antes: `page.get_pixmap`
        una = BI.franja(page, lado, RECT, 24.0)
        assert len(directo[0]) > 0
        assert np.array_equal(directo[0], una[0]) and np.array_equal(directo[1], una[1])
        assert BI.franja(page, lado, RECT, 24.0) is una               # la segunda vez no se dibuja
    hecho = doc.__dict__["_pdfcad_franjas"]
    assert hecho["dl"] is not None and len(hecho["franjas"]) == 4
    # otra hoja (u otras capas): lo guardado de la anterior no sirve y se suelta
    doc.new_page(width=800, height=600)
    BI.franja(doc[1], "top", RECT, 24.0)
    assert doc.__dict__["_pdfcad_franjas"]["clave"][0] == 1 and len(doc.__dict__["_pdfcad_franjas"]["franjas"]) == 1


@pytest.mark.parametrize("abajo", [(490.0, 498.0), (495.0, 495.0)])
def test_marco_calculado_es_lo_que_calculaba_armar(abajo):
    doc, page = _hoja_con_marco(*abajo)
    segs = BI._segmentos(page.get_drawings(extended=True), page.rotation_matrix)
    calc = BI.marco_calculado(page, RECT, segs)
    doc2, page2 = _hoja_con_marco(*abajo)                             # sin nada guardado
    anchos = {}
    q = BI.cuadrilatero(page2, RECT, segs=segs, anchos=anchos)
    assert calc["q"] == q and calc["anchos"] == anchos and calc["rect"] == RECT
    if q:
        assert calc["q_recto"] is None and calc["anchos_recto"] == {}
    else:                                                             # marco recto: la segunda llamada de `armar`
        anchos = {}
        qr = BI.cuadrilatero(page2, RECT, segs=segs, anchos=anchos, rectos=True)
        assert qr and calc["q_recto"] == qr and calc["anchos_recto"] == anchos and len(anchos) == 4


def test_armar_con_el_marco_de_la_ficha_da_la_misma_pieza():
    from hoja import composicion_ficha as F, composicion_sugerida as G

    def pieza(con_calc):
        doc, page = _hoja_con_marco()
        lineas = F._trazos(page.get_drawings(extended=True), page, RECT, 2.0, 40.0)
        f = F.Ficha(0, 0, (800.0, 600.0), vista=RECT, lineas=lineas, celda=(0, 0))
        if con_calc:
            f.marco_calc = BI.marco_calculado(page, RECT, lineas)
            doc.__dict__.pop("_pdfcad_franjas", None)
            BI.franja = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía dibujar franjas"))
        g = G.Grupo("mapa", [(0, 0)], [], transf={(0, 0): (1.0, 0.0, 0.0)})
        try:
            return G.armar(g, G.Analisis({(0, 0): f}, [g]), [doc], lambda *_a: 1.0).pieces[0]
        finally:
            BI.franja = franja_real
    franja_real = BI.franja
    a, b = pieza(False), pieza(True)
    assert len(a.polygon) == 4 and a.to_dict() == b.to_dict()


# ─────────────── rutas: «¿otra línea pasa por el nodo?» por zonas ───────────────
@dataclass
class _E:
    pts_pdf: list
    kinds: list
    fillets: dict = field(default_factory=dict)
    layer_ocg: str = "capa"
    abandoned: bool = False
    n_segments: int = 1
    review: str = ""


def _red(semilla):
    """Cadenas partidas en trozos (se unen), T (no se unen), «Y», lazos, cortes y dos capas mezcladas."""
    rnd = random.Random(semilla)
    out = []
    for k in range(40):
        x, y = rnd.uniform(0, 3000), rnd.uniform(0, 3000)
        ang = rnd.choice((0, 30, 90, 135)) * math.pi / 180
        capa = rnd.choice(("a", "a", "b"))
        pts = [(x, y)]
        for _ in range(rnd.randint(2, 7)):
            ang += rnd.uniform(-0.5, 0.5)
            L = rnd.uniform(15, 120)
            pts.append((pts[-1][0] + L * math.cos(ang), pts[-1][1] + L * math.sin(ang)))
        cortes = sorted(rnd.sample(range(1, len(pts) - 1), min(len(pts) - 2, rnd.randint(0, 2))))
        ini = 0
        for c in cortes + [len(pts) - 1]:
            trozo = pts[ini:c + 1]
            tipos = [rnd.choice(("end", "junction", "tee", "cut"))] + ["bend"] * (len(trozo) - 2) + \
                    [rnd.choice(("end", "junction", "junction", "cut"))]
            if rnd.random() < 0.3:
                trozo, tipos = trozo[::-1], tipos[::-1]
            out.append(_E([tuple(p) for p in trozo], tipos, layer_ocg=capa, abandoned=rnd.random() < 0.1))
            ini = c
        if rnd.random() < 0.5:                             # un ramal que muere sobre un vértice interior: T
            p = pts[rnd.randrange(1, len(pts) - 1)]
            out.append(_E([p, (p[0] + 40, p[1] - 60)], ["tee", "end"], layer_ocg=capa))
        if rnd.random() < 0.3:                             # otra que PASA por un nodo de corte
            p = pts[cortes[0]] if cortes else pts[1]
            out.append(_E([(p[0] - 50, p[1] - 3), p, (p[0] + 50, p[1] + 3)], ["end", "bend", "end"], layer_ocg=capa))
    rnd.shuffle(out)
    return out


def _foto_rutas(lines, gone):
    quedan = [pl for pl in lines if not any(pl is g for g in gone)]
    return ([(pl.pts_pdf, pl.kinds, pl.layer_ocg, pl.n_segments) for pl in quedan], len(gone))


@pytest.mark.parametrize("semilla", range(6))
def test_unir_rutas_por_zonas_igual_que_mirando_todas(semilla, monkeypatch):
    base = _red(semilla)
    a = copy.deepcopy(base)
    nuevo = _foto_rutas(a, routes.join_emitted(a))
    monkeypatch.setattr(routes._Pasos, "en", lambda self, q: [v[0] for v in self.vivas.values()])   # todas, como antes
    b = copy.deepcopy(base)
    viejo = _foto_rutas(b, routes.join_emitted(b))
    assert nuevo == viejo
    if semilla == 0:
        assert nuevo[1] > 5                                 # (sí hubo uniones que comparar)


def _unir_como_antes(lines):
    """`join_emitted` de antes de `_Pares`: en cada vuelta, el mejor par mirando TODA la capa."""
    live = [pl for pl in lines if len(pl.pts_pdf) >= 2]
    gone = []
    while True:
        best = routes._best_emitted_pair(live, routes.NODE_TOL_PT, routes.EMIT_HEADING_MIN_PT)
        if best is None:
            return gone
        _d, i, si, j, sj = best
        routes._absorb(live[i], si, live[j], sj)
        gone.append(live.pop(j))


@pytest.mark.parametrize("semilla", range(12))
def test_pares_tras_cada_union_igual_que_mirar_toda_la_capa(semilla):
    """Solo se vuelve a mirar cerca de cada unión: mismas uniones, en el mismo orden."""
    base = _red(semilla)
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    assert _foto_rutas(a, routes.join_emitted(a)) == _foto_rutas(b, _unir_como_antes(b))


def test_pares_en_cadenas_largas_y_empates():
    """Muchas uniones seguidas (cada pieza de una cadena se une a la anterior) y nodos con el mismo giro: el
    desempate por índice sigue siendo el de mirar toda la capa aunque las listas se corran al quitar líneas."""
    out = []
    for fila in range(6):
        y = fila * 40.0
        xs = [0.0, 30.0, 60.0, 61.0, 90.0, 120.0, 150.0, 151.5, 180.0]
        for k, (x0, x1) in enumerate(zip(xs, xs[1:])):
            hueco = 0.25 * ((k + fila) % 3)                   # extremos del nodo a 0–0.5 pt (tol 0.6), no encima
            pts = [(x0 + hueco, y + 0.2 * (k % 2)), (x1, y + (0.3 if k % 2 else 0.0))]
            out.append(_E(pts if (k + fila) % 3 else pts[::-1], ["junction", "junction"]))
    random.Random(7).shuffle(out)
    a, b = copy.deepcopy(out), copy.deepcopy(out)
    nuevo = _foto_rutas(a, routes.join_emitted(a))
    assert nuevo == _foto_rutas(b, _unir_como_antes(b)) and nuevo[1] > 20


# ─────────────── rótulos en piezas ───────────────
def _corridas(semilla):
    """Renglones de piezas («81'», «3/4"», «STL», «`56»…) en dos rumbos, con huecos chicos y grandes."""
    rnd = random.Random(semilla)
    out = []
    for fila in range(30):
        vertical = fila % 3 == 0
        base = rnd.uniform(0, 2000)
        u = rnd.uniform(0, 300)
        for _ in range(rnd.randint(3, 14)):
            texto = rnd.choice(("81'", "120'", '3/4"', '2"', '1/2"', "STL", "PE", "`56", "'88", "STL `57", "Main St", "X"))
            tam = rnd.choice((6.0, 6.0, 8.0))
            v = base + rnd.choice((0.0, 0.0, 0.5, 4.0))
            origen = (v, u) if vertical else (u, v)
            out.append(texto_pdf.Corrida(texto, origen, (0.0, 1.0) if vertical else (1.0, 0.0), tam))
            u += 0.6 * tam + rnd.choice((2.0, 6.0, 15.0, 30.0, 200.0))
    rnd.shuffle(out)
    return out


@pytest.mark.parametrize("semilla", range(6))
def test_piezas_del_rotulo_con_orden_guardado_igual_que_ordenando_cada_vez(semilla, monkeypatch):
    corridas = _corridas(semilla)
    nuevo = GR.de_corridas(corridas)
    original = GR._vecinas
    monkeypatch.setattr(GR, "_vecinas", lambda c, otras, usadas, sentido, orden=None: original(c, otras, usadas, sentido))
    viejo = GR.de_corridas(corridas)
    assert nuevo == viejo and len(nuevo) > 10
    assert any(" " in r.texto for r in nuevo)              # (hubo rótulos armados con varias piezas)


# ─────────────── índice de tramos: tramos cortos todos juntos ───────────────
def _celdas_como_antes(tramos, alcance, celda=0.0):
    """Las celdas de `IndiceTramos` armadas de a un tramo (el código de antes)."""
    al = float(alcance)
    c = float(celda) if celda > 0 else max(4.0 * al, 8.0)
    paso = c / 2.0
    r = al + paso / 2.0 + 1e-9
    celdas = {}
    for i, sg in enumerate(tramos):
        for j, (a, b) in enumerate(sg):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L <= c:
                for cx in range(int(math.floor((min(a[0], b[0]) - al) / c)), int(math.floor((max(a[0], b[0]) + al) / c)) + 1):
                    for cy in range(int(math.floor((min(a[1], b[1]) - al) / c)), int(math.floor((max(a[1], b[1]) + al) / c)) + 1):
                        celdas.setdefault((cx, cy), []).append((i, j))
                continue
            n = max(1, int(math.ceil(L / paso)))
            vistas = set()
            for k in range(n + 1):
                x = a[0] + (b[0] - a[0]) * k / n
                y = a[1] + (b[1] - a[1]) * k / n
                for cx in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
                    for cy in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                        if (cx, cy) not in vistas:
                            vistas.add((cx, cy))
                            celdas.setdefault((cx, cy), []).append((i, j))
    return {k: sorted(v) for k, v in celdas.items()}


@pytest.mark.parametrize("semilla", range(6))
@pytest.mark.parametrize("alcance,celda", [(1.0, 0.0), (0.25, 0.0), (2.5, 10.0), (7.0, 3.0)])
def test_indice_de_tramos_mismas_celdas(semilla, alcance, celda):
    """Coordenadas negativas, justo sobre el borde de una celda, tramos de largo 0, enteros y numpy, cortos y
    largos mezclados: cada celda tiene los mismos (polilínea, tramo) que armándolas de a uno."""
    rnd = random.Random(semilla)
    c = celda if celda > 0 else max(4.0 * alcance, 8.0)
    tramos = []
    for _ in range(60):
        x, y = rnd.uniform(-500, 500), rnd.uniform(-500, 500)
        if rnd.random() < 0.2:
            x, y = round(x / c) * c - alcance, round(y / c) * c + alcance        # sobre el borde de una celda
        pts = [(x, y)]
        for _k in range(rnd.randint(1, 8)):
            L = rnd.choice((0.0, rnd.uniform(0, c), rnd.uniform(c, 6 * c)))
            ang = rnd.uniform(0, 2 * math.pi)
            q = (pts[-1][0] + L * math.cos(ang), pts[-1][1] + L * math.sin(ang))
            pts.append(rnd.choice((q, (int(q[0]), int(q[1])), (np.float64(q[0]), np.float64(q[1])))))
        tramos.append(list(zip(pts, pts[1:])))
    tramos.append([])
    idx = RI.IndiceTramos(tramos, alcance, celda)
    antes = _celdas_como_antes(tramos, alcance, celda)
    assert {k: sorted(v) for k, v in idx._celdas.items()} == antes
    assert RI.IndiceTramos([], alcance, celda).cerca((0.0, 0.0)) == []
    for _ in range(200):
        p = (rnd.uniform(-600, 600), rnd.uniform(-600, 600))
        k = (int(math.floor(p[0] / idx.celda)), int(math.floor(p[1] / idx.celda)))
        assert idx.cerca(p) == antes.get(k, [])


# ─────────────── ángulos: bordes cerca de cada punta ───────────────
@pytest.mark.parametrize("semilla", range(6))
def test_normales_de_borde_mirando_solo_los_de_cerca(semilla, monkeypatch):
    """Puntas sobre lados, esquinas, anillos y lejos de todo: las mismas normales, en el mismo orden, que
    recorriendo todos los bordes (también la misma lista de bordes preguntada muchas veces, y otra después)."""
    rnd = random.Random(semilla)
    bordes = []
    for _ in range(80):
        x, y = rnd.uniform(0, 1000), rnd.uniform(0, 1000)
        tipo = rnd.random()
        if tipo < 0.3:
            bordes.append(("circle", (x, y, rnd.uniform(2, 20))))
        elif tipo < 0.35:
            bordes.append(None)
        else:
            w, h, g = rnd.uniform(5, 300), rnd.uniform(5, 300), rnd.uniform(0, math.pi)
            esq = [(0, 0), (w, 0), (w, h), (0, h)]
            bordes.append(("poly", [(x + a * math.cos(g) - b * math.sin(g), y + a * math.sin(g) + b * math.cos(g))
                                    for a, b in esq]))
    puntos = []
    for b in bordes:
        if not b:
            continue
        if b[0] == "circle":
            cx, cy, r = b[1]
            ang = rnd.uniform(0, 2 * math.pi)
            puntos.append((cx + (r + rnd.uniform(-0.6, 0.6)) * math.cos(ang), cy + (r + rnd.uniform(-0.6, 0.6)) * math.sin(ang)))
        else:
            a, c = b[1][0], b[1][1]
            t = rnd.choice((0.0, 1.0, rnd.random(), -1e-10, 1 + 1e-10))
            puntos.append((a[0] + t * (c[0] - a[0]) + rnd.uniform(-0.6, 0.6), a[1] + t * (c[1] - a[1]) + rnd.uniform(-0.6, 0.6)))
    puntos += [(rnd.uniform(-50, 1100), rnd.uniform(-50, 1100)) for _ in range(100)]
    nuevo = [AC.normales_de_borde(q, bordes, 0.5) for q in puntos]
    otra = list(bordes)                                               # otra lista: sus propias cajas
    assert [[tuple(n) for n in AC.normales_de_borde(q, otra, 0.5)] for q in puntos[:20]] == \
        [[tuple(n) for n in v] for v in nuevo[:20]]
    monkeypatch.setattr(AC, "_bordes_cerca", lambda b, q, tol: list(range(len(b))))     # todos, como antes
    viejo = [AC.normales_de_borde(q, bordes, 0.5) for q in puntos]
    assert [[tuple(n) for n in v] for v in nuevo] == [[tuple(n) for n in v] for v in viejo]
    assert sum(len(v) for v in viejo) > 40


# ─────────────── válvulas: «¿se ve el glifo?» en varios procesos ───────────────
def test_glifos_en_varios_procesos_igual_que_aqui(tmp_path, monkeypatch):
    """La misma hoja (con una capa apagada: el hijo la apaga igual), los mismos recuadros dibujados en dos procesos
    reales: mismas respuestas y en el mismo orden que dibujándolos aquí."""
    doc = fitz.open()
    pg = doc.new_page(width=600, height=400)
    oculta = doc.add_ocg("oculta", on=True)
    for k in range(40):
        x, y = 20 + 13 * k, 50 + (k % 7) * 40
        color = ((0, 0.52, 0.52), (1, 0.41, 0.13), (0, 0, 0))[k % 3]
        pg.insert_text((x, y), "S", fontsize=9, color=color, oc=oculta if k % 5 == 0 else 0)
    pg.draw_rect(fitz.Rect(300, 100, 400, 300), color=None, fill=(1, 1, 1))          # tapa algunos
    ruta = tmp_path / "glifos.pdf"
    doc.save(ruta)
    doc = fitz.open(ruta)
    num = next(c["number"] for c in doc.layer_ui_configs() if c["text"] == "oculta")
    doc.set_layer_ui_config(num, action=2)
    page = doc[0]
    lista = page.get_displaylist()
    pedidos = []
    for k in range(40):
        x, y = 20 + 13 * k, 50 + (k % 7) * 40
        color = ((0, 0.52, 0.52), (1, 0.41, 0.13), (0, 0, 0))[(k + (k % 2)) % 3]   # a veces otro color
        pedidos.append(((x - 1.0, y - 8.0, x + 7.0, y + 1.0), VT.rgb_de(color)))
    aqui = [VT.hay_tinta(lista, r, c) for r, c in pedidos]
    assert 5 < sum(aqui) < 35                                    # hay de los dos
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    monkeypatch.setattr(VT, "_procesos", lambda n: 2)
    llamado = []
    original = VT._en_procesos
    monkeypatch.setattr(VT, "_en_procesos", lambda *a: llamado.append(original(*a)) or llamado[-1])
    assert VT.se_ven(page, lista, pedidos) == aqui and llamado == [aqui]       # (de los procesos, sin caer aquí)


def test_glifos_adelantados_se_recogen_y_se_sueltan(tmp_path, monkeypatch):
    """`adelantar` lanza los dibujos al empezar; `se_ven` con los MISMOS pedidos toma esas respuestas sin lanzar
    otros; con otros pedidos las descarta y calcula; `soltar` termina lo que nadie recogió."""
    doc = fitz.open()
    pg = doc.new_page(width=300, height=200)
    for k in range(12):
        pg.insert_text((20 + 20 * k, 100), "S", fontsize=9, color=(0, 0.52, 0.52))
    ruta = tmp_path / "g.pdf"
    doc.save(ruta)
    doc = fitz.open(ruta)
    page = doc[0]
    pedidos = [((18.0 + 20 * k, 92.0, 27.0 + 20 * k, 101.0), (0, 133, 133) if k % 3 else (255, 0, 0)) for k in range(12)]
    aqui = [VT.hay_tinta(page.get_displaylist(), r, c) for r, c in pedidos]
    monkeypatch.setattr(VT, "_procesos", lambda n: 2)
    lanzados = []
    original = VT._lanzar
    monkeypatch.setattr(VT, "_lanzar", lambda *a: lanzados.append(1) or original(*a))
    VT.adelantar(page, pedidos)
    assert len(lanzados) == 1
    assert VT.se_ven(doc[0], None, pedidos) == aqui and len(lanzados) == 1      # recogidos, sin lanzar otra vez
    VT.adelantar(page, pedidos)
    assert VT.se_ven(page, None, pedidos[:5]) == aqui[:5] and len(lanzados) == 3  # otros pedidos: descartados
    VT.adelantar(page, pedidos)
    VT.soltar(doc)
    assert not doc.__dict__.get(VT._ADELANTADOS)


# ─────────────── grosor de los mapas: el rótulo contra los tramos a su alcance ───────────────
@dataclass
class _L:
    pts_pdf: list
    acometida: bool = False
    grosor: dict = field(default_factory=lambda: {"estado": "sin_dato"})


def _mapa(semilla):
    """Rutas largas (muchos tramos), acometidas cortas y rótulos encima, al costado, pasada la punta y lejos."""
    from reconocimiento import recognition_grosor_mapa as G
    rnd = random.Random(semilla)
    lineas = []
    for _ in range(25):
        x, y, ang = rnd.uniform(0, 800), rnd.uniform(0, 800), rnd.uniform(0, math.pi)
        pts = [(x, y)]
        for _k in range(rnd.randint(1, 40)):
            ang += rnd.uniform(-0.3, 0.3)
            L = rnd.choice((0.0, rnd.uniform(1, 30)))
            pts.append((pts[-1][0] + L * math.cos(ang), pts[-1][1] + L * math.sin(ang)))
        lineas.append(_L(pts, acometida=rnd.random() < 0.2))
    rots = []
    for _ in range(120):
        pl = rnd.choice(lineas).pts_pdf
        q = pl[rnd.randrange(len(pl))]
        ang = rnd.uniform(0, math.pi)
        rots.append(G.RotuloMapa(centro=(q[0] + rnd.uniform(-15, 15), q[1] + rnd.uniform(-15, 15)),
                                 dir=(math.cos(ang), math.sin(ang)), tam=rnd.choice((2.0, 3.0, 6.0)),
                                 largo=rnd.uniform(5, 30), pulg=rnd.choice((0.75, 2.0, 8.0, 12.0)), material="",
                                 acometida=rnd.random() < 0.2, texto="8\""))
    return lineas, rots


@pytest.mark.parametrize("semilla", range(6))
def test_rotulos_de_mapa_contra_los_tramos_a_su_alcance(semilla, monkeypatch):
    from reconocimiento import recognition_grosor_mapa as G, recognition_grosor_mapa_cerca as GC
    lineas, rots = _mapa(semilla)
    es_tap = lambda pl: pl.acometida                                   # noqa: E731
    nuevo = G.asignar(lineas, rots, es_tap)
    a = copy.deepcopy(lineas)
    GC.poner_cerca(a, rots, es_tap, 1.0)
    original = G._cerca
    monkeypatch.setattr(G, "_cerca", lambda r, pts, tramos=None: original(r, pts))     # todos los tramos, como antes
    viejo = G.asignar(lineas, rots, es_tap)
    b = copy.deepcopy(lineas)
    GC.poner_cerca(b, rots, es_tap, 1.0)
    clave = lambda d: {k: [id(r) for r in v] if isinstance(v, list) and v and hasattr(v[0], "centro") else v
                       for k, v in d.items()}                          # noqa: E731
    assert [clave(x) for x in nuevo] == [clave(x) for x in viejo]
    assert [pl.grosor for pl in a] == [pl.grosor for pl in b]
    assert sum(len(pl.grosor.get("cerca", ())) for pl in a) > 20


# ─────────────── importar y redibujar: «¿ya está?» por celdas ───────────────
def _sin_repetidos_antes(items):
    from nucleo import conflictos as CF
    out = []
    for c in items:
        clave = (c["clave"], frozenset(i for i in c.get("pipes") or [] if i is not None))
        if any((o["clave"], frozenset(i for i in o.get("pipes") or [] if i is not None)) == clave
               and (float(o["x"]) - float(c["x"])) ** 2 + (float(o["y"]) - float(c["y"])) ** 2 <= CF.MISMO_PX ** 2
               for o in out):
            continue
        out.append(c)
    return out


def _agrupar_antes(conflictos, tol):
    grupos = []
    for c in conflictos or []:
        g = next((g for g in grupos if (g[0].x - c.x) ** 2 + (g[0].y - c.y) ** 2 <= tol * tol), None)
        if g is None:
            grupos.append([c])
        else:
            g.append(c)
    return grupos


def _juntar_antes(existentes, nuevas):
    from nucleo import valvulas as V
    out = list(existentes)
    for v in nuevas:
        if not any(a.get("utilidad") == v.get("utilidad")
                   and math.hypot(a["x"] - v["x"], a["y"] - v["y"]) <= V.MISMA_PX for a in out):
            out.append(v)
    return out


def _puntos(rnd, n, paso):
    """Puntos amontonados, sobre bordes de celda exactos y algunos no finitos."""
    out = []
    for _ in range(n):
        x, y = rnd.uniform(0, 60), rnd.uniform(0, 60)
        if rnd.random() < 0.3:
            x, y = round(x / paso) * paso, round(y / paso) * paso + rnd.choice((0.0, paso, -paso))
        if rnd.random() < 0.02:
            x = rnd.choice((float("nan"), float("inf")))
        out.append((x, y))
    return out


@pytest.mark.parametrize("semilla", range(8))
def test_conflictos_repetidos_y_numeros_fijos_por_celdas(semilla, monkeypatch):
    from nucleo import conflictos as CF
    rnd = random.Random(semilla)
    items = [{"clave": rnd.choice(("cruce", "choque", "escalon")), "x": x, "y": y,
              "pipes": rnd.choice(([1, 2], [2, 1], [1, 3], [None, 4])), "mensaje": "", "cotas": []}
             for x, y in _puntos(rnd, 400, CF.MISMO_PX)]
    assert CF._sin_repetidos(items) == _sin_repetidos_antes(items)
    assert len(_sin_repetidos_antes(items)) < len(items)
    # números fijos: un registro hecho y luego otro modelo (corridos, quitados, nuevos)
    reg_a, reg_b = CF.Registro(), CF.Registro()
    CF.numerar_fijo(items, reg_a); CF.numerar_fijo(items, reg_b)
    otro = [dict(c, x=float(c["x"]) + rnd.uniform(-45, 45), y=float(c["y"]) + rnd.uniform(-45, 45))
            for c in items if rnd.random() < 0.8]
    nuevo = [(c.id, c.clave, c.x, c.y) for c in CF.numerar_fijo(otro, reg_a)]
    original = CF.math.floor
    monkeypatch.setattr(CF.math, "floor", lambda v: 0 if math.isfinite(v) else original(v))   # todos en una celda
    viejo = [(c.id, c.clave, c.x, c.y) for c in CF.numerar_fijo(otro, reg_b)]
    monkeypatch.setattr(CF.math, "floor", original)
    assert nuevo == viejo and reg_a.a_dict() == reg_b.a_dict()


@pytest.mark.parametrize("semilla", range(8))
def test_grupos_de_etiquetas_por_celdas(semilla):
    from nucleo import conflictos as CF
    rnd = random.Random(semilla)
    for tol in (0.0, 1.0, 3.5):
        cs = [CF.Conflicto(f"C-{k}", "cruce", x, y) for k, (x, y) in enumerate(_puntos(rnd, 300, max(tol, 1.0)))]
        assert [[c.id for c in g] for g in CF.agrupar(cs, tol)] == [[c.id for c in g] for g in _agrupar_antes(cs, tol)]


@pytest.mark.parametrize("semilla", range(8))
def test_valvulas_repetidas_por_celdas(semilla):
    from nucleo import valvulas as V
    rnd = random.Random(semilla)
    vs = [{"x": x, "y": y, "utilidad": rnd.choice(("GAS", "AGUA"))} for x, y in _puntos(rnd, 300, V.MISMA_PX)]
    antes, nuevas = vs[:100], vs[100:]
    assert V.juntar(antes, nuevas) == _juntar_antes(antes, nuevas)
    assert len(_juntar_antes(antes, nuevas)) < len(vs)



@pytest.mark.parametrize("semilla", range(8))
def test_rotulo_senala_la_misma_utilidad_mirando_solo_las_cercanas(semilla):
    """Puntas de guía sobre una línea, entre dos, en un vértice, lejos; rótulos sin guía (centro, 3× tol); utilidades
    de un solo punto: la misma utilidad (o ninguna) que recorriendo todas."""
    from nucleo import anotaciones as AN
    from nucleo.indice_plano import IndiceUtilidades
    rnd = random.Random(semilla)
    pipes = []
    for _ in range(120):
        x, y = rnd.uniform(0, 3000), rnd.uniform(0, 3000)
        pts = [(x, y)]
        for _k in range(rnd.choice((0, 1, 3, 12))):
            pts.append((pts[-1][0] + rnd.uniform(-200, 200), pts[-1][1] + rnd.uniform(-200, 200)))
        pipes.append({"pts": pts})
    cerca = IndiceUtilidades(pipes).cerca
    anots = []
    for _ in range(400):
        p = rnd.choice(pipes)["pts"]
        q = p[rnd.randrange(len(p))]
        ju = (q[0] + rnd.uniform(-40, 40), q[1] + rnd.uniform(-40, 40))
        if rnd.random() < 0.5:
            anots.append({"puntas": [ju] + ([(ju[0] + 30, ju[1])] if rnd.random() < 0.3 else [])})
        else:
            anots.append({"caja": (ju[0] - 20, ju[1] - 5, ju[0] + 20, ju[1] + 5)})
    nuevo = [AN.senala(a, pipes, cerca=cerca) for a in anots]
    assert nuevo == [AN.senala(a, pipes) for a in anots]
    assert sum(v is not None for v in nuevo) > 100 and None in nuevo
