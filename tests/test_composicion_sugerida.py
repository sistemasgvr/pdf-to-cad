"""Composición sugerida (2026-10-14): revisar todas las hojas y sugerir cómo se unen.

PDFs sintéticos que imitan los de prueba: plano CAD con match lines (estaciones,
«SEE DWG», series UR-n / UR-nA, erratas de estación) y mapas por cuadrícula de
Phoenix (número + mapa índice 3×3, hojas que se solapan, Norte/Sur a otra escala)."""
import math
import os
import random
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")

from hoja import composite as C  # noqa: E402
from hoja import composicion_ficha as F  # noqa: E402
from hoja import composicion_encaje as E  # noqa: E402
from hoja import composicion_hermanos as H  # noqa: E402
from hoja import composicion_sugerida as G  # noqa: E402

W, H_ = 1100.0, 600.0


# ─────────────────────────── plano CAD sintético ───────────────────────────
def _mundo_cad(seed=3, ys=(100, 160, 230, 300)):
    """Dibujo «real» de un tramo largo: líneas que cruzan las match lines, símbolos y
    cotas cortas (únicos), en coordenadas del mundo (x a lo largo del tramo)."""
    rnd = random.Random(seed)
    lineas = []
    for y, capa in zip(ys, ("C-STRM-UNGD-E", "C-ELEC-UNGD-E", "C-SSWR-UNGD-E", "V-ROAD-CURB")):
        x = 0.0
        while x < 3000:
            L = rnd.uniform(6, 14)
            lineas.append((x, y + rnd.uniform(-0.2, 0.2), x + L, y + rnd.uniform(-0.2, 0.2), capa))
            x += L + rnd.uniform(3, 6)
    for _ in range(900):           # trazos sueltos únicos (casas, cotas) en todo el tramo
        x, y = rnd.uniform(0, 3000), rnd.uniform(40, 360)
        a = math.radians(rnd.choice([0, 30, 45, 60, 90, 120, 135]) + rnd.uniform(-3, 3))
        L = rnd.uniform(4, 25)
        lineas.append((x, y, x + L * math.cos(a), y + L * math.sin(a), "V-BLDG"))
    return lineas


def _hoja_cad(doc, mundo, x0m, x1m, numero, izq=None, der=None, desfase=(0.0, 0.0), sobra=12.0,
              estacion_izq=None, estacion_der=None):
    """Una hoja de planta: la vista muestra el mundo de x0m a x1m (y unos pt de más,
    como un viewport real), con la match line gruesa en x0m/x1m y los rótulos fuera."""
    dx, dy = desfase
    vx0, vy0 = 120.0 + dx, 80.0 + dy
    vista = fitz.Rect(vx0 - sobra, vy0, vx0 + (x1m - x0m) + sobra, vy0 + 400)
    src = fitz.open()
    sp = src.new_page(width=W, height=H_)
    ocgs = {}

    def oc(capa):
        if capa not in ocgs:
            ocgs[capa] = doc.add_ocg(capa, on=True)
        return ocgs[capa]
    for ax, ay, bx, by, capa in mundo:
        if max(ax, bx) < x0m - sobra - 2 or min(ax, bx) > x1m + sobra + 2:
            continue
        sp.draw_line((vx0 + ax - x0m, vy0 + ay), (vx0 + bx - x0m, vy0 + by), width=0.5)
    for xm in (x0m, x1m):           # match line gruesa (a guiones), capa de anotación
        y = 10.0
        while y < 390:
            sp.draw_line((vx0 + xm - x0m, vy0 + y), (vx0 + xm - x0m, vy0 + y + 30), width=1.98)
            y += 40
    page = doc.new_page(width=W, height=H_)
    page.show_pdf_page(vista, src, 0, clip=vista)
    if izq is not None:
        page.insert_text((vista.x0 - 60, vy0 + 200), "MATCH LINE STA %s SEE DWG %s" % (estacion_izq, izq), fontsize=6)
    if der is not None:
        page.insert_text((vista.x1 + 8, vy0 + 260), "MATCH LINE STA %s" % estacion_der, fontsize=6)
    page.insert_text((W - 140, H_ - 30), numero, fontsize=18)
    page.draw_rect(fitz.Rect(20, 20, W - 20, H_ - 20), width=1.0)      # marco (plantilla)
    return page


def _plano_cad(series=("X-#",), errata=False, falsa=False):
    """3 hojas por serie: STA 30+00 → 20+00 → 10+00 → 0+00 (bajan a la derecha)."""
    mundo = _mundo_cad()
    doc = fitz.open()
    p = doc.new_page(width=W, height=H_)
    p.insert_text((100, 100), "COVER SHEET 380-4", fontsize=20)     # portada sin nada que unir
    tramos = [(0, 700, "30+00", "20+00"), (700, 1400, "20+00", "10+00"), (1400, 2100, "10+00", "0+00")]
    for serie in series:
        for k, (a, b, sa, sb) in enumerate(tramos):
            num = serie.replace("#", str(101 + k))
            izq = serie.replace("#", str(100 + k)) if k else None
            ei = sa
            if errata and k == 2:
                ei = "10+50"          # la hoja vecina dice 10+00: errata de 50 ft
            _hoja_cad(doc, mundo, a, b, num, izq=izq if k else None, der="x" if k < 2 else None,
                      desfase=((k * 37.0) % 60, (k * 23.0) % 40), estacion_izq=ei, estacion_der=sb)
    if falsa:
        # otra calle cuyo rótulo dice la MISMA estación pero el dibujo no tiene que ver
        _hoja_cad(doc, _mundo_cad(seed=99, ys=(70, 125, 205, 340)), 700, 1400, "X-201", izq="X-200",
                  estacion_izq="20+00")
    return fitz.open(stream=doc.tobytes(), filetype="pdf")


def _analizar(docs):
    fpd = [F.fichas(d, i) for i, d in enumerate(docs)]
    return G.analizar(fpd)


def _punto_continuo(comp, docs, c, an):
    """Un punto del plano junto a la costura cae en el mismo sitio desde las dos piezas."""
    pa = [p for p in comp.pieces if (p.source, p.page) == c.a][0]
    pb = [p for p in comp.pieces if (p.source, p.page) == c.b][0]
    da, db = docs[c.a[0]][c.a[1]], docs[c.b[0]][c.b[1]]
    v = an.fichas[c.a].vista
    P = (c.corte_a - 30.0, (v[1] + v[3]) / 2.0)
    m1 = C.piece_map(pa, (da.rect.width, da.rect.height), comp.target_scale())(*P)
    m2 = C.piece_map(pb, (db.rect.width, db.rect.height), comp.target_scale())(*c.mapa(*P))
    return math.hypot(m1[0] - m2[0], m1[1] - m2[1])


def test_ficha_lee_rotulos_numero_y_vista():
    doc = _plano_cad()
    fs = F.fichas(doc)
    assert fs[0].tipo == "" and fs[0].celda is None          # «380-4» de una portada no es cuadrícula
    f = fs[2]
    assert f.numero == "X-102" and f.serie == "X-#"
    assert f.tipo == "estaciones"
    lados = {r.lado: (F.estacion_texto(r.estacion), r.ver) for r in f.rotulos}
    assert lados["left"] == ("20+00", "X-101") and lados["right"][0] == "10+00"
    assert f.vista is not None and f.lineas


def test_cadena_cad_se_une_sola_y_exacta():
    doc = _plano_cad()
    an = _analizar([doc])
    assert len(an.grupos) == 1
    g = an.grupos[0]
    assert g.nodos == [(0, 1), (0, 2), (0, 3)]
    assert len(g.costuras) == 2 and g.residuo <= 0.01
    comp = G.armar(g, an, [doc], lambda d, h: 20 / 72.0, ["a.pdf"])
    assert len(comp.pieces) == 3
    for c in g.costuras:
        assert _punto_continuo(comp, [doc], c, an) <= 0.05
        # recortada EN la match line, borde con borde
        pa = [p for p in comp.pieces if (p.source, p.page) == c.a][0]
        pb = [p for p in comp.pieces if (p.source, p.page) == c.b][0]
        ra = C.piece_rect(pa, (W, H_), comp.target_scale())
        rb = C.piece_rect(pb, (W, H_), comp.target_scale())
        assert abs(ra[2] - rb[0]) <= 1.0


def test_errata_de_estacion_se_confirma_con_el_dibujo_y_la_falsa_no():
    doc = _plano_cad(errata=True, falsa=True)
    an = _analizar([doc])
    g = an.grupo_de((0, 1))
    assert g is not None and g.nodos == [(0, 1), (0, 2), (0, 3)]        # 10+50 / 10+00 se une igual
    assert all((0, 4) not in (c.a, c.b) for c in g.costuras)             # la «X-201» no se pega
    assert an.grupo_de((0, 4)) is None
    assert an.descartadas >= 1


def test_dos_series_del_mismo_tramo_no_se_mezclan():
    doc = _plano_cad(series=("UR-#", "UR-#A"))
    an = _analizar([doc])
    assert len(an.grupos) == 2
    for g in an.grupos:
        assert len(g.nodos) == 3 and len(g.series) == 1
    assert {g.series[0] for g in an.grupos} == {"UR-#", "UR-#A"}


# ─────────────────────────── mapas por cuadrícula ───────────────────────────
LADO = 400.0          # celda del mundo
SOBRA = 30.0          # cada hoja muestra esto de más alrededor (solape con la vecina)


def _mundo_mapa(seed=5):
    rnd = random.Random(seed)
    segs = []
    for _ in range(9000):
        x, y = rnd.uniform(-100, 1300), rnd.uniform(-100, 900)
        a = math.radians(rnd.choice([0, 90, 30, 120]) + rnd.uniform(-2, 2))
        L = rnd.uniform(10, 60)
        segs.append((x, y, x + L * math.cos(a), y + L * math.sin(a)))
    return segs


def _hoja_mapa(doc, mundo, fila, col, escala, jitter, indice=True, prefijo=""):
    """Hoja de la celda (fila, col): fila crece al norte (arriba), columna al este."""
    Wp, Hp = 700 * escala, 700 * escala
    cx0 = (col - 10) * LADO - SOBRA
    cy0 = (17 - fila) * LADO - SOBRA
    lado_p = (LADO + 2 * SOBRA) * escala
    ox, oy = 40 * escala + jitter[0], 40 * escala + jitter[1]
    vista = fitz.Rect(ox, oy, ox + lado_p, oy + lado_p)
    src = fitz.open()
    sp = src.new_page(width=Wp, height=Hp)
    for ax, ay, bx, by in mundo:
        if not (cx0 - 5 <= min(ax, bx) and max(ax, bx) <= cx0 + LADO + 2 * SOBRA + 5
                and cy0 - 5 <= min(ay, by) and max(ay, by) <= cy0 + LADO + 2 * SOBRA + 5):
            continue
        sp.draw_line((ox + (ax - cx0) * escala, oy + (ay - cy0) * escala),
                     (ox + (bx - cx0) * escala, oy + (by - cy0) * escala), width=0.4 * escala, color=(0, 0, 0))
    page = doc.new_page(width=Wp, height=Hp)
    page.show_pdf_page(vista, src, 0, clip=vista)
    page.draw_rect(fitz.Rect(10 * escala, 10 * escala, Wp - 10 * escala, Hp - 10 * escala), width=1.0)
    page.insert_text((Wp - 90 * escala, Hp - 20 * escala), "%s%d-%d" % (prefijo, fila, col), fontsize=14 * escala)
    if indice:
        bx, by = Wp - 200 * escala, Hp - 40 * escala
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                f, c = fila - j, col + i              # arriba = norte = fila + 1
                page.insert_text((bx + i * 22 * escala, by + j * 9 * escala), "%d-%d" % (f, c), fontsize=4 * escala)
    return page


def _mapas(filas, cols, escala=1.0, mundo=None, indice=True, prefijo=""):
    mundo = mundo or _mundo_mapa()
    rnd = random.Random(7)
    doc = fitz.open()
    for f in filas:
        for c in cols:
            _hoja_mapa(doc, mundo, f, c, escala, (rnd.uniform(-15, 15), rnd.uniform(-15, 15)), indice, prefijo)
    return fitz.open(stream=doc.tobytes(), filetype="pdf")


def test_ficha_de_mapa_lee_cuadricula_y_mapa_indice():
    doc = _mapas([17], [10, 11])
    f = F.fichas(doc)[0]
    assert f.celda == (17, 10)
    assert f.vecinas[(17, 11)] == (1, 0) and f.vecinas[(18, 10)] == (0, -1) and f.vecinas[(16, 10)] == (0, 1)
    assert f.tipo == "cuadricula" and f.vista is not None


def test_mapa_norte_y_sur_en_dos_pdf_con_otra_escala():
    mundo = _mundo_mapa()
    norte = _mapas([17], [10, 11, 12], 1.0, mundo)
    sur = _mapas([16], [10, 11, 12], 0.5, mundo)
    an = _analizar([norte, sur])
    assert len(an.grupos) == 1
    g = an.grupos[0]
    assert len(g.nodos) == 6
    assert g.residuo <= 0.5
    ns = [c for c in g.costuras if c.a[0] != c.b[0]]
    assert ns and all(abs(c.escala - 0.5) < 0.002 for c in ns)
    comp = G.armar(g, an, [norte, sur], lambda d, h: 1.0, ["n.pdf", "s.pdf"])
    tgt = comp.target_scale()
    # la misma esquina del mundo vista desde las dos hojas que la comparten cae en el mismo sitio
    for c in g.costuras:
        fa, fb = an.fichas[c.a], an.fichas[c.b]
        v = fa.vista
        P = ((v[0] + v[2]) / 2, v[3] - 10) if c.lado == "bottom" else (v[2] - 10, (v[1] + v[3]) / 2)
        pa = [p for p in comp.pieces if (p.source, p.page) == c.a][0]
        pb = [p for p in comp.pieces if (p.source, p.page) == c.b][0]
        da = [norte, sur][c.a[0]][c.a[1]]; db = [norte, sur][c.b[0]][c.b[1]]
        m1 = C.piece_map(pa, (da.rect.width, da.rect.height), tgt)(*P)
        m2 = C.piece_map(pb, (db.rect.width, db.rect.height), tgt)(*c.mapa(*P))
        assert math.hypot(m1[0] - m2[0], m1[1] - m2[1]) <= 0.5
    # costuras rectas: las piezas se tocan sin solaparse (fila de arriba con la de abajo)
    rects = {(p.source, p.page): C.piece_rect(p, ([norte, sur][p.source][p.page].rect.width,
                                                  [norte, sur][p.source][p.page].rect.height), tgt)
             for p in comp.pieces}
    for k in range(3):
        assert abs(rects[(0, k)][3] - rects[(1, k)][1]) <= 0.01


def test_sin_mapa_indice_con_prefijo_q_usa_la_convencion_aprendida():
    mundo = _mundo_mapa()
    con = _mapas([17], [10, 11], 1.0, mundo)
    sin = _mapas([16], [10, 11], 1.0, mundo, indice=False, prefijo="Q")
    fs = F.fichas(sin)
    assert fs[0].celda == (16, 10) and not fs[0].vecinas
    an = _analizar([con, sin])
    assert len(an.grupos) == 1 and len(an.grupos[0].nodos) == 4


def test_pdf_hermano_por_nombre_y_celdas(tmp_path):
    mundo = _mundo_mapa()
    _mapas([17], [10, 11], 1.0, mundo).save(str(tmp_path / "QS Water_Barrio_North.pdf"))
    _mapas([16], [10, 11], 0.5, mundo).save(str(tmp_path / "QS Water_Barrio_South.pdf"))
    _mapas([16], [10, 11], 0.5, mundo).save(str(tmp_path / "QS Sewer_Barrio_South.pdf"))
    _mapas([30], [5], 1.0, mundo).save(str(tmp_path / "QS Water_Otro_Lado.pdf"))
    norte = fitz.open(str(tmp_path / "QS Water_Barrio_North.pdf"))
    an = _analizar([norte])
    assert (16, 10) in an.faltan() and (16, 11) in an.faltan()
    h = H.buscar([str(tmp_path / "QS Water_Barrio_North.pdf")], an.faltan())
    assert h is not None and os.path.basename(h.ruta) == "QS Water_Barrio_South.pdf"
    assert h.celdas == [(16, 10), (16, 11)]


def _sin_memoria(T):
    for m in (T._UNIONES, T._ARMADAS, T._HERMANOS):
        m.clear()


def test_memoria_al_agregar_y_quitar_pdf_da_lo_mismo_sin_repetir(monkeypatch):
    """Pedido del usuario 2026-10-28: lo ya analizado de cada PDF queda en memoria. Agregar los mapas
    norte y sur a un plano CAD no vuelve a armar el juego del CAD, y quitar el CAD no repite ninguna
    unión ni rearma el juego de los mapas; el resultado es el MISMO que calcularlo de cero."""
    from hoja import composicion_trabajo as T
    mundo = _mundo_mapa()
    f = lambda n, d: {"name": n, "data": d.tobytes()}  # noqa: E731
    cad = f("cad.pdf", _plano_cad())
    norte = f("norte.pdf", _mapas([17], [10, 11], 1.0, mundo))
    sur = f("sur.pdf", _mapas([16], [10, 11], 0.5, mundo))

    def comps(res):
        return sorted(json_dumps(g.composite.to_dict()) for g in res.analisis.grupos)

    def json_dumps(d):
        import json
        return json.dumps(d, sort_keys=True)
    # de cero (sin memoria) para comparar
    refs = {}
    for nombre, fuentes in (("cad", [cad]), ("todo", [cad, norte, sur]), ("mapas", [norte, sur])):
        _sin_memoria(T)
        refs[nombre] = comps(T.calcular(fuentes, fichas_cache={}))
    _sin_memoria(T)
    cuenta = {"armar": 0, "union": 0}
    armar, cad_f, mapa_f = G.armar, E.costura_cad, E.encaje_mapa

    def contar(clave, fn):
        def envuelta(*a, **k):
            cuenta[clave] += 1
            return fn(*a, **k)
        return envuelta
    monkeypatch.setattr(G, "armar", contar("armar", armar))
    monkeypatch.setattr(E, "costura_cad", contar("union", cad_f))
    monkeypatch.setattr(E, "encaje_mapa", contar("union", mapa_f))
    fichas = {}
    assert comps(T.calcular([cad], fichas_cache=fichas)) == refs["cad"]
    cuenta.update(armar=0, union=0)
    assert comps(T.calcular([cad, norte, sur], fichas_cache=fichas)) == refs["todo"]
    assert cuenta["armar"] == 1                     # solo el juego de los mapas; el del CAD, de memoria
    cuenta.update(armar=0, union=0)
    assert comps(T.calcular([norte, sur], fichas_cache=fichas)) == refs["mapas"]
    assert cuenta == {"armar": 0, "union": 0}       # quitar el CAD no rehace nada


# ─────────────────────────── en el compositor ───────────────────────────
@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _esperar(dlg, timeout=60.0):
    import time
    from PySide6 import QtCore, QtWidgets
    t0 = time.time()
    while dlg._sug_res is None and time.time() - t0 < timeout:
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.02)
    return dlg._sug_res


def test_tarjeta_sugiere_usa_y_deshace(app, monkeypatch):
    monkeypatch.setenv("PDFCAD_SUGERENCIA", "1")
    from ui.asistente import composite_dialog
    data = _plano_cad().tobytes()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        res = _esperar(dlg)
        assert res is not None and res.analisis is not None and len(res.analisis.grupos) == 1
        assert not dlg.sug_card.isHidden()
        assert not dlg.btn_sug_usar.isHidden() and dlg.btn_sug_usar.isEnabled()
        assert "3" in dlg.lbl_sug.text()
        antes = [p.to_dict() for p in dlg.comp.pieces]           # la portada elegida al abrir
        dlg._sug_usar()
        assert len(dlg.comp.pieces) == 3
        assert dlg.tabs.current() == 2
        assert not dlg.btn_sug_deshacer.isHidden()
        # la hoja a la vista es de la composición: «Continuar» no pregunta por la portada
        assert not dlg._page_pending() and dlg.btn_ok.isEnabled()
        comp, fuentes, _ocultas = dlg.result_tuple()
        assert [(p.source, p.page) for p in comp.pieces] == [(0, 1), (0, 2), (0, 3)]
        dlg._sug_deshacer()
        assert [p.to_dict() for p in dlg.comp.pieces] == antes
        assert (dlg._cur_source, dlg._cur_page) == (0, 0) and not dlg._page_pending()
    finally:
        dlg.close_docs()


def test_tarjeta_pregunta_la_serie_si_la_hoja_abierta_no_esta_en_ninguna(app, monkeypatch):
    monkeypatch.setenv("PDFCAD_SUGERENCIA", "1")
    from ui.asistente import composite_dialog
    data = _plano_cad(series=("UR-#", "UR-#A")).tobytes()
    dlg = composite_dialog.CompositeDialog(None, [{"name": "a.pdf", "data": data}], None, {}, 0)
    try:
        assert _esperar(dlg) is not None
        # abierta en la portada: dos juegos → se pregunta, «Usar» apagado hasta elegir
        assert not dlg.cmb_sug.isHidden() and not dlg.btn_sug_usar.isEnabled()
        dlg.cmb_sug.setCurrentIndex(2)
        assert dlg.btn_sug_usar.isEnabled()
        # elegir en «Origen» una hoja de la serie A → esa serie queda elegida; la lista sigue a la
        # vista para elegir el otro juego (2026-10-28: los dos juegos se pueden elegir siempre)
        dlg.lst_pages.setCurrentRow(5)
        g, preguntar = dlg._sug_grupo()
        assert g.series == ["UR-#A"] and not dlg.cmb_sug.isHidden() and dlg.btn_sug_usar.isEnabled()
        assert "1 de 2" in dlg.lbl_sug.text() or "2 de 2" in dlg.lbl_sug.text()
        otro = next(i for i in range(1, dlg.cmb_sug.count()) if i != dlg.cmb_sug.currentIndex())
        dlg.cmb_sug.setCurrentIndex(otro)                  # el otro juego, con la hoja A a la vista
        g2, _ = dlg._sug_grupo()
        assert g2.series == ["UR-#"] and dlg.btn_sug_usar.isEnabled()
        dlg.lst_pages.setCurrentRow(0)                     # la portada (de ninguno): la elección sigue
        assert dlg._sug_grupo()[0] is g2
    finally:
        dlg.close_docs()


def test_agregar_pdf_a_mano_vuelve_a_sugerir_con_los_dos(app, monkeypatch, tmp_path):
    """Una utilidad partida en dos PDF: «Agregar PDF…» de la lista de hojas vuelve a analizar con
    los dos (antes solo lo hacía el «Agregar PDF» de la tarjeta), aunque la tarjeta estuviera oculta."""
    monkeypatch.setenv("PDFCAD_SUGERENCIA", "1")
    from ui.asistente import composite_dialog
    mundo = _mundo_mapa()
    norte, sur = tmp_path / "QS Water_Barrio_North.pdf", tmp_path / "QS Water_Barrio_South.pdf"
    _mapas([17], [10, 11], 1.0, mundo).save(str(norte))
    _mapas([16], [10, 11], 0.5, mundo).save(str(sur))
    dlg = composite_dialog.CompositeDialog(
        None, [{"name": norte.name, "data": norte.read_bytes(), "path": str(norte)}], None, {}, 0)
    try:
        res = _esperar(dlg)
        assert res is not None and res.analisis is not None
        clave_antes = dlg._sug_clave
        dlg._sug_ocultar()
        dlg._open_extra_pdf(str(sur))
        assert dlg._sug_clave != clave_antes and not dlg.sug_card.isHidden()
        res = _esperar(dlg)
        assert res is not None and res.analisis is not None
        assert any({p.source for p in g.composite.pieces} == {0, 1}
                   for g in res.analisis.grupos if g.composite is not None)
        assert not dlg.btn_sug_usar.isHidden()
    finally:
        dlg.close_docs()


def test_quitar_otro_pdf_deja_la_sugerencia_usada(app, monkeypatch):
    """Un plano CAD + los mapas norte y sur: con el juego de los mapas en la hoja compuesta, quitar
    el CAD no la toca ni la vuelve a ofrecer («Usar»): sigue usada, con sus PDF ya renumerados."""
    monkeypatch.setenv("PDFCAD_SUGERENCIA", "1")
    from PySide6 import QtWidgets
    from ui.asistente import composite_dialog
    mundo = _mundo_mapa()
    fuentes = [{"name": "cad.pdf", "data": _plano_cad().tobytes()},
               {"name": "norte.pdf", "data": _mapas([17], [10, 11], 1.0, mundo).tobytes()},
               {"name": "sur.pdf", "data": _mapas([16], [10, 11], 0.5, mundo).tobytes()}]
    dlg = composite_dialog.CompositeDialog(None, fuentes, None, {}, 0)
    try:
        res = _esperar(dlg)
        assert res is not None and len(res.analisis.grupos) == 2
        k = next(i for i in range(1, dlg.cmb_sug.count())
                 if res.analisis.grupos[dlg.cmb_sug.itemData(i)].tipo == "cuadricula")
        dlg.cmb_sug.setCurrentIndex(k)
        dlg._sug_usar()
        assert {p.source for p in dlg.comp.pieces} == {1, 2}
        monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **kw: QtWidgets.QMessageBox.Yes)
        dlg.cmb_source.setCurrentIndex(0)
        dlg._quitar_pdf()
        assert [s["name"] for s in dlg.sources] == ["norte.pdf", "sur.pdf"]
        assert {p.source for p in dlg.comp.pieces} == {0, 1}
        res = _esperar(dlg)
        assert res is not None and dlg._sug_usada is not None
        assert dlg.btn_sug_usar.isHidden() and "✔" in dlg.lbl_sug.text()
    finally:
        dlg.close_docs()


# ─────────────────────────── PDFs reales (si están) ───────────────────────────
DU06 = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "docs prueba",
                    "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


@pytest.mark.skipif(not os.path.exists(DU06), reason="PDF de prueba DU06 no disponible")
def test_du06_sugiere_el_tramo_entero():
    doc = fitz.open(DU06)
    an = _analizar([doc])
    assert len(an.grupos) == 1
    g = an.grupos[0]
    assert g.nodos == [(0, h) for h in range(2, 16)]               # UD-201 … UD-214
    assert len(g.costuras) == 13 and g.residuo <= 0.01
