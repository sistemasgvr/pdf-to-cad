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
    assert c("Cobertura de guiones: 97.2% (5 sin cubrir, en naranja).").level == rs.REVIEW
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
        "Cobertura de guiones: 97.2% (5 sin cubrir, en naranja).")}
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


def test_clic_en_aviso_lleva_la_vista_al_lugar():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import recognition_dialog as rd
    import recognition_summary_view as rsv
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
    rows = [w for w in dlg.summary.findChildren(rsv._NoticeRow) if w.clickable]
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
