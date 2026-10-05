"""Resumen visual de la vista previa: clasificación PURA de los avisos."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import recognition_summary as rs  # noqa: E402


def test_avisos_se_clasifican_con_etiqueta_corta():
    c = rs.classify_warning
    assert c("No se encontraron líneas de drenaje en esta hoja.").level == rs.PROBLEM
    n = c("Bóvedas sin línea cercana: 2.")
    assert (n.level, n.label) == (rs.REVIEW, "2 bóvedas sin línea")
    n = c("Curvas que quedan como polilínea: 1 tramo(s) — curva compuesta (radio variable) o …")
    assert (n.level, n.label) == (rs.REVIEW, "1 curva queda como polilínea")
    assert c("Codos como esquina + radio: 16.").level == rs.INFO
    n = c("Codos como esquina + radio: 5 (2 aproximado(s), a trazos: …; desvío máx. 2.1 pt).")
    assert (n.level, n.label) == (rs.REVIEW, "2 de 5 codos aproximados")
    assert c("Cobertura de guiones: 100.0%.").level == rs.INFO
    assert c("Cobertura de guiones: 97.2% (5 sin cubrir, en magenta).").level == rs.REVIEW
    assert c("Trazos repetidos (idénticos, en la misma capa): 404 — se usan una sola vez.").label \
        == "404 trazos repetidos (usados una vez)"
    assert c("Patrón «//» en una capa que no es «-A»: 2 línea(s) — …").level == rs.INFO
    assert c("Existentes A ABANDONAR (capa «-D», …): 3 línea(s) — hoy se importan activas; revisar.").level \
        == rs.REVIEW


def test_aviso_desconocido_no_se_esconde():
    n = rs.classify_warning("Algo nuevo que nadie clasificó todavía.", "AGUA")
    assert n.level == rs.REVIEW and n.utility == "AGUA"


def test_orden_y_cifras():
    pl = lambda ab=False, fil=0: SimpleNamespace(abandoned=ab, fillets={i: {} for i in range(fil)})
    r1 = SimpleNamespace(utility="ELECTRICO", drawable=[pl(), pl(True), pl(fil=2)], vault_pts=[(0, 0)],
                         coverage=1.0, warnings=["Codos como esquina + radio: 2.", "Bóvedas sin línea cercana: 1."])
    r2 = SimpleNamespace(utility="AGUA", drawable=[pl(True)], vault_pts=[], coverage=0.97,
                         warnings=["Esta hoja no tiene capas: …"])
    ns = rs.notices_for([r1, r2])
    assert [n.level for n in ns] == [rs.PROBLEM, rs.REVIEW, rs.INFO]
    st = [rs.stats_for(r) for r in (r1, r2)]
    assert (st[0].tramos, st[0].abandonadas, st[0].activas, st[0].codos, st[0].estructuras) == (3, 1, 2, 2, 1)
    tot = rs.totals(st)
    assert (tot.tramos, tot.abandonadas, tot.coverage) == (4, 2, 0.97)


# ─────────── clic en un aviso → ir al lugar de la hoja (2026-09-25) ───────────
def _pl(pts, kinds=None, **kw):
    return SimpleNamespace(pts_pdf=pts, kinds=kinds or ["end"] * len(pts), abandoned=False,
                           fillets={}, review="", **kw)


def test_cada_aviso_de_revisar_sabe_que_ubicar():
    keys = {rs.classify_warning(w).key for w in (
        "Capa «-A» sin el patrón de marcadores «/» a lo largo de la línea: 1 — …",
        "Existentes A ABANDONAR (capa «-D», …): 3 línea(s) — …",
        "Patrón de marcadores «/» en una capa ACTIVA: 1 línea(s) — …",
        "Curvas que quedan como polilínea: 1 tramo(s) — …",
        "Bóvedas sin línea cercana: 2.",
        "Codos como esquina + radio: 5 (2 aproximado(s), …).",
        "Cobertura de guiones: 97.2% (5 sin cubrir, en magenta).")}
    assert "" not in keys and len(keys) == 7
    assert rs.classify_warning("Rutas: 4 (unen 6 tramos de la misma capa).").key == ""


def test_targets_de_cada_aviso():
    curva = _pl([(0, 0), (10, 0), (20, 5), (30, 15), (40, 40)], ["end", "corner", "curve", "curve", "end"])
    codo = _pl([(100, 0), (200, 0), (200, 100)])
    codo.fillets = {1: {"a": (180, 0), "b": (200, 20), "loose": True}, }
    ab = _pl([(0, 500), (300, 500)]); ab.abandoned = True
    marca = _pl([(0, 900), (50, 900)]); marca.review = "to_abandon"
    r = SimpleNamespace(drawable=[curva, codo, ab, marca], polylines_joined=[curva, codo, ab, marca],
                        uncovered_px=[((5, 5), (6, 6))], vault_orphans_px=[(700, 700)],
                        vault_pts=[], offpattern_px=[])
    assert rs.targets_for("curvy", r) == [(10, 0, 40, 40)]                 # la ristra curva + vecinos
    (x0, y0, x1, y1), = rs.targets_for("fillets", r)                       # solo el aproximado
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == (190, 10)                     # (chico → con margen)
    assert rs.targets_for("abandoned", r) == [(0, 500, 300, 500)]
    assert rs.targets_for("to_abandon", r) == [(0, 900, 50, 900)]
    (x0, y0, x1, y1), = rs.targets_for("orphans", r)                       # un punto → recuadro visible
    assert (x0 + x1) / 2 == 700 and x1 - x0 >= 2 * rs.POINT_PAD_PX
    assert rs.targets_for("uncovered", r)[0][2] - rs.targets_for("uncovered", r)[0][0] >= 2 * rs.POINT_PAD_PX
    assert rs.targets_for("", r) == [] and rs.targets_for("offpattern", r) == []


def test_puntas_unidas_a_su_boveda_es_info_y_ubica_cada_punta():
    n = rs.classify_warning("Puntas unidas a su bóveda (imán): 3 — quedaban a menos de 3 pt de su "
                            "contorno y se llevaron hasta él por su propia recta.")
    assert (n.level, n.label, n.key) == (rs.INFO, "3 puntas unidas a su bóveda", "vault_snaps")
    r = SimpleNamespace(drawable=[], vault_snaps_px=[(300.0, 40.0), (10.0, 40.0)])
    boxes = rs.targets_for("vault_snaps", r)
    assert [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes] == [(10.0, 40.0), (300.0, 40.0)]


def test_clic_en_aviso_lleva_la_vista_al_lugar():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import recognition_dialog as rd
    import recognition_review_view as rrv
    curva = _pl([(0, 0), (10, 0), (20, 5), (30, 15), (40, 40)], ["end", "corner", "curve", "curve", "end"])
    lejos = _pl([(1500, 1500), (1900, 1900)])
    res = SimpleNamespace(
        utility="ELECTRICO", page_index=0, scale_ft_per_pt=20 / 72, polylines=[curva, lejos],
        drawable=[curva, lejos], polylines_joined=[curva, lejos], polylines_raw=[curva, lejos],
        warnings=["Curvas que quedan como polilínea: 1 tramo(s) — …", "Bóvedas sin línea cercana: 1."],
        vault_orphans_px=[(1800, 300)], vault_pts=[], vaults_geo=[], uncovered_px=[], offpattern_px=[],
        coverage=1.0, hidden_ocgs=[], ocg_summary=[], join_routes=True)
    img = QtGui.QImage(2000, 2000, QtGui.QImage.Format_RGB32); img.fill(QtCore.Qt.white)
    dlg = rd.RecognitionPreviewDialog(None, img, [res])
    dlg.resize(1200, 800); dlg.show(); app.processEvents()
    rows = [w for w in dlg.review_panel.findChildren(rrv._NoticeRow) if w.clickable]
    assert len(rows) == 2
    for row, (cx, cy) in zip(rows, ((25, 20), (1800, 300))):
        ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(3, 3), QtCore.QPointF(3, 3),
                               QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
        row.mouseReleaseEvent(ev); app.processEvents()
        vis = dlg.view.mapToScene(dlg.view.viewport().rect()).boundingRect()
        assert vis.contains(QtCore.QPointF(cx, cy)) and vis.width() < 1200      # hizo zoom ahí
        assert dlg._marker is not None and dlg._marker.rect().contains(QtCore.QPointF(cx, cy))
        assert row.counter.text() == "1/1"
    dlg.close()


# ─────────── «Revisar»: panel izquierdo y marca de revisado (2026-09-30 / 10-03) ───────────
def _preview(warnings, polylines, orphans=(), utility="ELECTRICO", extra=()):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import recognition_dialog as rd

    def _res(utility, warnings, polylines, orphans=()):
        return SimpleNamespace(
            utility=utility, page_index=0, scale_ft_per_pt=20 / 72, polylines=list(polylines),
            drawable=list(polylines), polylines_joined=list(polylines), polylines_raw=list(polylines),
            warnings=list(warnings), vault_orphans_px=list(orphans), vault_pts=[], vaults_geo=[],
            uncovered_px=[], offpattern_px=[], coverage=1.0, hidden_ocgs=[], ocg_summary=[], join_routes=True)
    results = [_res(utility, warnings, polylines, orphans)] + [_res(*e) for e in extra]
    img = QtGui.QImage(2000, 2000, QtGui.QImage.Format_RGB32); img.fill(QtCore.Qt.white)
    dlg = rd.RecognitionPreviewDialog(None, img, results)
    dlg.resize(1200, 800); dlg.show(); app.processEvents()
    return app, dlg


def _click(row, button=None):
    from PySide6 import QtCore, QtGui
    button = button or QtCore.Qt.LeftButton
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(3, 3), QtCore.QPointF(3, 3),
                           button, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
    row.mouseReleaseEvent(ev)


def test_revisar_y_detalles_van_en_el_panel_izquierdo():
    """Pedido del usuario 2026-10-03: «Revisar» y «Detalles» a la izquierda de la
    hoja; a la derecha quedan el resumen y las capas."""
    app, dlg = _preview(["Bóvedas sin línea cercana: 1.", "Codos como esquina + radio: 4."],
                        [_pl([(0, 0), (100, 0)])], orphans=[(500, 500)])
    try:
        assert dlg.split.count() == 3
        assert dlg.split.widget(0) is dlg.review_box and dlg.split.widget(2) is dlg.side_panel
        left = dlg.review_box
        for w in (dlg.review_panel, dlg.review_panel.btn_details, *dlg.review_panel.review_rows):
            assert left.isAncestorOf(w) and not dlg.side_panel.isAncestorOf(w)
        for w in (dlg.summary, dlg.used_layers, dlg.btn_roles, dlg.lbl_sheet):
            assert dlg.side_panel.isAncestorOf(w)
        from PySide6 import QtCore
        dlg.setWindowState(QtCore.Qt.WindowNoState)
        for width in (1400, 1920, 1100):
            dlg.resize(width, 800)
            for _ in range(4):
                app.processEvents()
            w = dlg.split.width()                                # los anchos siguen a la ventana
            left, view, right = dlg.split.sizes()
            assert left == max(240, min(300, int(w * 0.20))), (width, left)
            assert abs(right - max(300, min(400, int(w * 0.28)))) <= 2, (width, right)
            assert view > right                                  # la hoja, la columna más ancha
    finally:
        dlg.close()


def test_revisar_se_pliega_y_le_da_su_ancho_a_la_hoja():
    from widgets import CollapsiblePanel
    app, dlg = _preview(["Bóvedas sin línea cercana: 1."], [_pl([(0, 0), (100, 0)])], orphans=[(500, 500)])
    try:
        w_left, w_view, _ = dlg.split.sizes()
        dlg.review_box.set_collapsed(True); app.processEvents()
        left, view, _ = dlg.split.sizes()
        assert left == CollapsiblePanel.STRIP_W and view >= w_view + w_left - left - 2
        dlg.review_box.set_collapsed(False); app.processEvents()
        assert abs(dlg.split.sizes()[0] - w_left) <= 2
    finally:
        dlg.close()


def test_revisar_con_muchos_avisos_hace_scroll_en_su_panel():
    """Con muchos avisos el panel izquierdo hace scroll; el resumen no se mueve."""
    warnings = [f"Aviso nuevo número {i} que nadie clasificó todavía." for i in range(25)]
    app, dlg = _preview(warnings, [_pl([(0, 0), (100, 0)])])
    try:
        assert len(dlg.review_panel.review_rows) == 25
        assert dlg.review_scroll.verticalScrollBar().maximum() > 0
        assert not dlg.side_panel.isAncestorOf(dlg.review_panel)
    finally:
        dlg.close()
    app, dlg = _preview(warnings[:2], [_pl([(0, 0), (100, 0)])])
    try:                                                         # pocos: sin scroll
        assert dlg.review_scroll.verticalScrollBar().maximum() == 0
    finally:
        dlg.close()


def test_revisar_agrupa_por_utilidad_y_empieza_por_los_problemas():
    """Con varias utilidades cada grupo lleva su nombre UNA vez (antes «Eléctrico (E) ·»
    en cada fila); el grupo con un problema va primero."""
    from PySide6 import QtWidgets
    app, dlg = _preview(["Bóvedas sin línea cercana: 1."], [_pl([(0, 0), (100, 0)])], orphans=[(500, 500)],
                        extra=[("TELECOM", ["Curvas que quedan como polilínea: 1 tramo(s) — …",
                                            "No se encontraron líneas de telecomunicaciones en esta hoja."],
                                [_pl([(0, 50), (100, 50)])])])
    try:
        rows = dlg.review_panel.review_rows
        assert [r._notice.utility for r in rows] == ["TELECOM", "TELECOM", "ELECTRICO"]
        assert rows[0]._notice.label == "Sin líneas en esta hoja"
        texts = [w.text() for w in dlg.review_panel.findChildren(QtWidgets.QLabel)]
        assert texts.count("Telecomunicaciones (T)") == 1 and texts.count("Eléctrico (E)") == 1
        assert not any("·" in r.lbl.text() for r in rows)          # sin el prefijo repetido
    finally:
        dlg.close()


def test_aviso_se_usa_con_el_teclado():
    """Tab llega a la tarjeta del aviso y Enter hace lo mismo que el clic."""
    from PySide6 import QtCore, QtTest
    app, dlg = _preview(["Bóvedas sin línea cercana: 1."], [_pl([(0, 0), (100, 0)])], orphans=[(1800, 300)])
    try:
        row, = dlg.review_panel.review_rows
        assert row.focusPolicy() & QtCore.Qt.TabFocus
        QtTest.QTest.keyClick(row, QtCore.Qt.Key_Return); app.processEvents()
        assert row.counter.text() == "1/1" and row.reviewed
        assert dlg._marker.rect().contains(QtCore.QPointF(1800, 300))
    finally:
        dlg.close()


def test_aviso_revisado_al_ver_todos_sus_casos():
    """Clic en un aviso → va al lugar; vistos todos sus casos queda «revisado»
    (✔) y en la hoja cada lugar visitado conserva un recuadro verde."""
    from PySide6 import QtCore
    curva = _pl([(0, 0), (10, 0), (20, 5), (30, 15), (40, 40)], ["end", "corner", "curve", "curve", "end"])
    app, dlg = _preview(["Bóvedas sin línea cercana: 2.", "Aviso nuevo que nadie clasificó todavía."],
                        [curva], orphans=[(1800, 300), (300, 1800)])
    try:
        panel = dlg.review_panel
        rows = panel.review_rows
        orph = next(r for r in rows if r.clickable)
        other = next(r for r in rows if not r.clickable)
        assert panel.lbl_reviewed.text() == "0 de 2 vistos" and panel.progress.value() == 0
        _click(orph); app.processEvents()
        assert not orph.reviewed and orph.counter.text() == "1/2"
        _click(orph); app.processEvents()
        assert orph.reviewed and panel.lbl_reviewed.text() == "1 de 2 vistos"
        assert panel.progress.value() == 1
        assert len(dlg._reviewed) == 2
        _click(other)                                            # sin lugar: el clic lo marca
        assert other.reviewed and panel.lbl_reviewed.text() == "✔ Todos vistos"
        _click(other)                                            # y otro clic lo desmarca
        assert not other.reviewed
        dlg.chk_routes.setChecked(False); app.processEvents()   # redibujo: los recuadros siguen
        greens = [it for it in dlg.view.scene().items()
                  if it.toolTip() == "Visto"]
        assert len(greens) == 2
        assert all(it.rect().contains(QtCore.QPointF(*p)) for it, p in
                   zip(sorted(greens, key=lambda i: i.rect().x()), ((300, 1800), (1800, 300))))
    finally:
        dlg.close()


def test_unir_tramos_va_en_el_pie():
    """«Unir tramos en rutas» dejó el panel del resumen: es un botón del pie."""
    app, dlg = _preview([], [_pl([(0, 0), (100, 0)])])
    try:
        assert not dlg.side_panel.isAncestorOf(dlg.chk_routes)
        assert not dlg.review_box.isAncestorOf(dlg.chk_routes)
        assert dlg.chk_routes.isCheckable() and dlg.chk_routes.isChecked()
        assert dlg.lbl_scale.text() == "Escala 1\"=20'"
    finally:
        dlg.close()


# ─────────── colores del control de calidad (2026-10-03) ───────────
def _hue_gap(a, b) -> float:
    d = abs(a.hsvHueF() - b.hsvHueF()) * 360.0
    return min(d, 360.0 - d)


def test_colores_de_calidad_no_son_de_ninguna_utilidad():
    """«Sin cubrir» era naranja como telecom: los colores del control de calidad
    quedan lejos (≥30° de tono) de todas las utilidades con color."""
    from PySide6 import QtGui
    from model import TIPOS
    from ui_common import layer_qcolor, QA_UNCOVERED, QA_OFFPATTERN
    for qa in (QA_UNCOVERED, QA_OFFPATTERN):
        q = QtGui.QColor(qa)
        for _label, key in TIPOS:
            u = layer_qcolor(key)
            if u.hsvSaturationF() < 0.2:                         # blanco/gris del drenaje: sin tono
                continue
            assert _hue_gap(q, u) >= 30, (qa, key)
    assert _hue_gap(QtGui.QColor(QA_UNCOVERED), QtGui.QColor(QA_OFFPATTERN)) >= 90


def test_vista_previa_pinta_el_control_de_calidad_con_sus_colores_y_formas():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from ui_common import QA_UNCOVERED, QA_OFFPATTERN
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import recognition_dialog as rd
    res = SimpleNamespace(
        utility="TELECOM", page_index=0, scale_ft_per_pt=20 / 72, polylines=[], drawable=[],
        polylines_joined=[], polylines_raw=[], warnings=[], vault_orphans_px=[(300, 300)], vault_pts=[],
        vaults_geo=[], uncovered_px=[((10, 10), (60, 10))], offpattern_px=[[(0, 100), (80, 100)]],
        coverage=0.99, hidden_ocgs=[], ocg_summary=[], join_routes=True)
    img = QtGui.QImage(500, 500, QtGui.QImage.Format_RGB32); img.fill(QtCore.Qt.white)
    dlg = rd.RecognitionPreviewDialog(None, img, [res])
    try:
        items = dlg.view.scene().items()
        lines = [it for it in items if isinstance(it, QtWidgets.QGraphicsLineItem)]
        unc = [it for it in lines if it.pen().color().name() == QA_UNCOVERED]
        off = [it for it in lines if it.pen().color().name() == QA_OFFPATTERN]
        assert len(unc) == 1 and unc[0].pen().widthF() >= 4
        assert len(off) == 1 and off[0].pen().style() == QtCore.Qt.CustomDashLine     # a puntos
        ring, = [it for it in items if isinstance(it, QtWidgets.QGraphicsEllipseItem)
                 and it.pen().color().name() == QA_UNCOVERED]
        assert ring.brush().style() == QtCore.Qt.NoBrush                              # anillo, no punto
        assert {"uncovered", "orphan", "offpattern"} == set(dlg.summary.qa_kinds)     # en la leyenda
    finally:
        dlg.close()


def test_esquina_del_codo_queda_en_su_lugar_con_cualquier_zoom():
    """El cuadrito de la esquina C (tamaño fijo en pantalla) va en la esquina: antes
    se medía desde el origen de la hoja y salía corrido si el zoom no era 1."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import recognition_dialog as rd
    codo = _pl([(0, 0), (300, 0), (300, 300)])
    codo.fillets = {1: {"a": (250, 0), "b": (300, 50), "center": (250, 50), "r_px": 50.0}}
    res = SimpleNamespace(
        utility="ELECTRICO", page_index=0, scale_ft_per_pt=20 / 72, polylines=[codo], drawable=[codo],
        polylines_joined=[codo], polylines_raw=[codo], warnings=[], vault_orphans_px=[], vault_pts=[],
        vaults_geo=[], uncovered_px=[], offpattern_px=[], coverage=1.0, hidden_ocgs=[], ocg_summary=[],
        join_routes=True)
    img = QtGui.QImage(600, 600, QtGui.QImage.Format_RGB32); img.fill(QtCore.Qt.white)
    dlg = rd.RecognitionPreviewDialog(None, img, [res])
    try:
        dlg.resize(1000, 700); dlg.show(); app.processEvents()
        dlg.view.resetTransform(); dlg.view.scale(0.4, 0.4); app.processEvents()
        mark, = [it for it in dlg.view.scene().items()
                 if it.flags() & QtWidgets.QGraphicsItem.ItemIgnoresTransformations
                 and isinstance(it, QtWidgets.QGraphicsRectItem)]
        assert (mark.pos().x(), mark.pos().y()) == (300, 0)
        on_screen = dlg.view.mapFromScene(mark.mapToScene(mark.rect().center()))
        assert (on_screen - dlg.view.mapFromScene(QtCore.QPointF(300, 0))).manhattanLength() <= 1
    finally:
        dlg.close()


# ─────────── «Para verificar»: lo encontrado, no errores (2026-10-03, 2.º pedido) ───────────
def test_cada_punto_para_verificar_trae_su_explicacion():
    """Todo aviso que se muestra en «Para verificar» explica en lenguaje llano qué se
    encontró y qué se hizo; lo informativo («Detalles») no la necesita."""
    for w in ("No se encontraron líneas de drenaje en esta hoja.", "Esta hoja no tiene capas: …",
              "Ninguna capa OCG coincidió con …",
              "Capa «-A» sin el patrón de marcadores «/» a lo largo de la línea: 1 — …",
              "Existentes A ABANDONAR (capa «-D», …): 3 línea(s) — …",
              "Patrón de marcadores «/» en una capa ACTIVA: 1 línea(s) — …",
              "Curvas que quedan como polilínea: 1 tramo(s) — …", "Bóvedas sin línea cercana: 2.",
              "Codos como esquina + radio: 5 (2 aproximado(s), …).",
              "Cobertura de guiones: 97.2% (5 sin cubrir, en magenta)."):
        n = rs.classify_warning(w)
        assert n.level != rs.INFO and len(n.hint) > 40, w
    assert rs.classify_warning("Codos como esquina + radio: 16.").hint == ""
    largo = "Aviso nuevo que nadie clasificó todavía y que es bastante más largo que sesenta letras."
    n = rs.classify_warning(largo)
    assert n.label.endswith("…") and n.hint == largo                 # el resto, a la vista


def test_para_verificar_dice_que_no_son_errores():
    from PySide6 import QtWidgets
    app, dlg = _preview(["Bóvedas sin línea cercana: 1."], [_pl([(0, 0), (100, 0)])], orphans=[(500, 500)])
    try:
        texts = [w.text() for w in dlg.review_box.findChildren(QtWidgets.QLabel)]
        assert "Para verificar (1)" in texts
        assert "no son errores" in dlg.review_panel.lbl_intro.text()
        row, = dlg.review_panel.review_rows
        assert not row.hint.isHidden() and "ninguna línea llega" in row.hint.text()
        assert dlg.review_panel.lbl_reviewed.text() == "0 de 1 vistos"
    finally:
        dlg.close()
    app, dlg = _preview(["No se encontraron líneas eléctricas subterráneas en esta hoja.",
                         "Bóvedas sin línea cercana: 1."], [], orphans=[(500, 500)])
    try:                                                          # un problema de verdad: en rojo
        assert dlg.review_panel.problems == 1 and "En rojo" in dlg.review_panel.lbl_intro.text()
        assert dlg.review_panel.review_rows[0]._notice.level == rs.PROBLEM
    finally:
        dlg.close()
    app, dlg = _preview([], [_pl([(0, 0), (100, 0)])])
    try:
        texts = [w.text() for w in dlg.review_box.findChildren(QtWidgets.QLabel)]
        assert "Nada que verificar" in texts and not dlg.review_panel.review_rows
    finally:
        dlg.close()


# ─────────── «Capas usadas»: clic = ver esa capa en la hoja (2026-10-03) ───────────
def _layers_preview():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import recognition_dialog as rd
    a = _pl([(100, 100), (300, 100)], layer_ocg="X|C-ELEC-UNGD-E")
    b = _pl([(1500, 1500), (1800, 1500)], layer_ocg="X|C-ELEC-UNGD-N")
    vault = {"center": (1650, 400), "corners": [(1600, 380), (1700, 380), (1700, 420), (1600, 420)],
             "width_ft": 5.0, "length_ft": 9.0, "layer": "X|C-ELEC-VALT-E", "orphan": False, "importable": True}
    elec = SimpleNamespace(
        utility="ELECTRICO", page_index=0, scale_ft_per_pt=20 / 72, polylines=[a, b], drawable=[a, b],
        polylines_joined=[a, b], polylines_raw=[a, b], warnings=[], vault_orphans_px=[], vault_pts=[],
        vaults_geo=[vault], uncovered_px=[], offpattern_px=[], coverage=1.0, hidden_ocgs=[], join_routes=True,
        ocg_summary=[{"ocg": "X|C-ELEC-UNGD-E", "kind": "elec_ungd", "path_count": 10},
                     {"ocg": "X|C-ELEC-UNGD-N", "kind": "elec_ungd", "path_count": 8},
                     {"ocg": "X|C-ELEC-VALT-E", "kind": "structure", "path_count": 4},
                     {"ocg": "X|V-ELEC-POLE", "kind": "structure", "path_count": 163}])
    c = _pl([(900, 900), (1000, 900)], layer_ocg="X|C-SSWR-UNGD-E")
    sewer = SimpleNamespace(
        utility="ALCANTARILLADO", page_index=0, scale_ft_per_pt=20 / 72, polylines=[c], drawable=[c],
        polylines_joined=[c], polylines_raw=[c], warnings=[], vault_orphans_px=[], vault_pts=[], vaults_geo=[],
        uncovered_px=[], offpattern_px=[], coverage=1.0, hidden_ocgs=[], join_routes=True,
        ocg_summary=[{"ocg": "X|C-SSWR-UNGD-E", "kind": "sewer_ungd", "path_count": 3}])
    img = QtGui.QImage(2000, 2000, QtGui.QImage.Format_RGB32); img.fill(QtCore.Qt.white)
    dlg = rd.RecognitionPreviewDialog(None, img, [elec, sewer])
    dlg.resize(1400, 900); dlg.show(); app.processEvents()
    return app, dlg


def _item(dlg, text):
    lst = dlg.layers_panel.list
    return next(lst.item(i) for i in range(lst.count()) if lst.item(i).text().strip().startswith(text))


def _line_items(dlg, color_name):
    from PySide6 import QtWidgets
    return [it for it in dlg.view.scene().items() if isinstance(it, QtWidgets.QGraphicsLineItem)
            and it.pen().color().name() == color_name]


def test_clic_en_una_capa_la_resalta_y_lleva_la_vista_ahi():
    from PySide6 import QtCore, QtWidgets
    from ui_common import layer_qcolor
    import recognition_preview_draw as rpd
    app, dlg = _layers_preview()
    try:
        red, green = layer_qcolor("ELECTRICO").name(), layer_qcolor("ALCANTARILLADO").name()
        lst = dlg.layers_panel.list
        lst.itemClicked.emit(_item(dlg, "C-ELEC-UNGD-E")); app.processEvents()
        assert dlg._focus["ocg"] == "X|C-ELEC-UNGD-E" and not dlg.layers_panel.btn_all.isHidden()
        halos = [it for it in dlg.view.scene().items() if isinstance(it, QtWidgets.QGraphicsPathItem)
                 and it.pen().widthF() == rpd.HALO_PX]
        assert len(halos) == 1                                    # solo la línea de esa capa
        lines = _line_items(dlg, red)
        bright = [it for it in lines if it.opacity() == 1.0]
        assert len(bright) == 1 and bright[0].line().x1() == 100              # la de la capa
        assert all(it.opacity() == rpd.DIM_OPACITY for it in _line_items(dlg, green))   # lo demás, tenue
        vis = dlg.view.mapToScene(dlg.view.viewport().rect()).boundingRect()
        assert vis.contains(QtCore.QRectF(100, 100, 200, 1)) and vis.width() < 1500    # encuadró la capa
        assert dlg.layers_panel.lbl_status.text() == "Resaltado: C-ELEC-UNGD-E · 1 línea"
        lst.itemClicked.emit(_item(dlg, "C-ELEC-UNGD-E")); app.processEvents()   # otro clic: se quita
        assert dlg._focus is None and dlg.layers_panel.btn_all.isHidden()
        assert all(it.opacity() == 1.0 for it in _line_items(dlg, red) + _line_items(dlg, green))
    finally:
        dlg.close()


def test_clic_en_encabezados_y_capa_de_bovedas():
    from PySide6 import QtCore, QtTest
    app, dlg = _layers_preview()
    try:
        lst = dlg.layers_panel.list
        lst.itemClicked.emit(_item(dlg, "Eléctrico (E)")); app.processEvents()        # la utilidad entera
        assert dlg.layers_panel.lbl_status.text() == "Resaltado: Eléctrico (E) · 2 líneas, 1 bóveda"
        lst.itemClicked.emit(_item(dlg, "Bóvedas")); app.processEvents()              # «Bóvedas» de eléctrico
        assert dlg.layers_panel.lbl_status.text() == "Resaltado: Bóvedas · Eléctrico (E) · 1 bóveda"
        lst.itemClicked.emit(_item(dlg, "C-ELEC-VALT-E")); app.processEvents()        # una capa de bóvedas
        vis = dlg.view.mapToScene(dlg.view.viewport().rect()).boundingRect()
        assert vis.contains(QtCore.QPointF(1650, 400))
        lst.itemClicked.emit(_item(dlg, "V-ELEC-POLE")); app.processEvents()          # postes: nada que ver
        assert "no hay nada reconocido" in dlg.layers_panel.lbl_status.text()
        dlg.layers_panel.btn_all.click(); app.processEvents()                          # «Ver todo»
        assert dlg._focus is None and lst.selectedItems() == []
        lst.setCurrentItem(_item(dlg, "C-SSWR-UNGD-E"))                                # con el teclado
        QtTest.QTest.keyClick(lst, QtCore.Qt.Key_Return); app.processEvents()
        assert dlg._focus["ocg"] == "X|C-SSWR-UNGD-E"
    finally:
        dlg.close()
