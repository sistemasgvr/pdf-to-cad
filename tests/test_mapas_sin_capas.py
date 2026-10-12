"""Mapas SIG aplanados (sin capas OCG): capas por estilo → reconocer → importar → DXF.

Pedido del usuario 2026-10-10 con los Quarter Section de Phoenix («QS Sewer/Water/SD
Indian School», una utilidad por PDF, 0 capas). Cubre lo que se agregó sobre las capas
virtuales por estilo (`hoja.pdf_styles`, `ui.asistente.layer_assignments`):
  · la tinta continua es el eje (`recognition_ink_lines`), sin el zigzag del trazo y sin
    esquinas fuera de la tinta; un tipo de línea a guiones sigue por el núcleo;
  · buzones donde terminan las tuberías de una red por gravedad (`recognition_style_nodes`);
  · «Reconocer» solo lo que tiene estilo asignado y la escala calibrable antes de reconocer;
  · el dato extendido de la capa, legible.
"""
import math
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

fitz = pytest.importorskip("fitz")
from PySide6 import QtCore, QtWidgets  # noqa: E402

from hoja import pdf_layers, pdf_styles  # noqa: E402
from nucleo import xdata  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from reconocimiento import recognition_ink_lines as ink  # noqa: E402
from reconocimiento import recognition_style_nodes as nodes_mod  # noqa: E402

PHOENIX = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND")
SEWER = PHOENIX / "QS Sewer_Indian School_North.pdf"
needs_phoenix = pytest.mark.skipif(not SEWER.is_file(), reason="PDF de Phoenix no disponible")


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _line(page, pts, width=0.73):
    """Un trazo continuo de varias cuerdas (como lo exporta un SIG)."""
    sh = page.new_shape()
    sh.draw_polyline(pts)
    sh.finish(color=(0, 0, 0), width=width, closePath=False)
    sh.commit()


def _network_pdf(path):
    """Red de alcantarillado de mapa SIG: cada tubería un trazo de buzón a buzón (con zigzag
    de ±0.3 pt), dos colineales que se tocan en el buzón B, una que gira en el C, y el
    parcelario fino aparte."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    zig = lambda a, b, n: [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n + (0.3 if i % 2 else 0.0))
                           if 0 < i < n else (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
                           for i in range(n + 1)]
    A, B, C, D = (50, 200), (200, 200), (350, 200), (350, 60)
    _line(page, zig(A, B, 9))
    _line(page, zig(B, C, 9))
    _line(page, zig(C, D, 7))
    for x in range(60, 560, 40):                     # parcelario: otro estilo
        _line(page, [(x, 260), (x, 380)], width=0.36)
    doc.save(path)
    return (A, B, C, D)


def _style(doc, width):
    return next(L["name"] for L in pdf_layers.page_layers(doc, 0, letters=False)
                if L["short"].startswith("Negro {:.2f} pt".format(width)))


# ── puro ────────────────────────────────────────────────────────────────────
def test_trazo_continuo_vs_tipo_de_linea_a_guiones():
    def path(*chains):
        items = [("l", fitz.Point(a), fitz.Point(b)) for ch in chains for a, b in zip(ch, ch[1:])]
        return {"items": items}
    continuo = [path([(0, 0), (40, 1), (90, 0), (150, 2)]), path([(150, 2), (150, 120)])]
    # «—W—» explotado: guiones de 12 pt con huecos de 6 pt en la misma recta
    guiones = [path([(x, 0), (x + 12, 0)]) for x in range(0, 300, 18)]
    assert ink.continuous_layer(continuo)
    assert not ink.continuous_layer(guiones)


def test_la_tinta_es_el_eje_sin_zigzag_ni_esquinas_inventadas():
    pts = [(0, 0), (10, 0.3), (20, 0), (30, 0.3), (40, 0), (50, 0.3), (60, 0)]   # recta con zigzag
    curva = [(60 + 50 * math.sin(math.radians(a)), 50 - 50 * math.cos(math.radians(a))) for a in range(0, 91, 5)]
    g = ink.ink_reconstruct([{"items": [("l", fitz.Point(a), fitz.Point(b)) for a, b in zip(pts, pts[1:])]},
                             {"items": [("l", fitz.Point(a), fitz.Point(b)) for a, b in zip(curva, curva[1:])]}])
    recta, arco = g.polylines
    assert recta.pts == [(0.0, 0.0), (60.0, 0.0)]                  # el zigzag de ±0.3 pt no son quiebres
    assert recta.kinds == ["end", "junction"] and arco.kinds[0] == "junction"
    # la curva queda en cuerdas que no se apartan de la tinta más que la tolerancia
    for p in curva:
        d = min(ink._seg_dist(p, a, b)[1] for a, b in zip(arco.pts, arco.pts[1:]))
        assert d <= ink.SIMPLIFY_PT + 1e-6
    assert 2 < len(arco.pts) < len(curva)


def test_nodos_donde_terminan_dos_tuberias():
    def path(ch):
        return {"items": [("l", fitz.Point(a), fitz.Point(b)) for a, b in zip(ch, ch[1:])]}
    paths = [path([(0, 0), (100, 0)]), path([(100, 0), (200, 0)]), path([(200, 0), (200, 80)]),
             path([(300, 0), (304, 0)])]                         # flecha corta: no cuenta
    nodes = nodes_mod.feature_nodes(paths)
    assert sorted(nodes) == [(100.0, 0.0), (200.0, 0.0)]


def test_dato_extendido_de_una_capa_por_estilo_es_legible():
    name = pdf_styles.PREFIX + '["s",[0.0,0.0,0.0],0.73,"[] 0",null,null,null]'
    fields = xdata.parse_layer(name)
    assert fields[xdata.F_LAYER] == "Estilo Negro 0.73 pt · continuo"
    assert "PDF_STYLE" not in "".join(fields.values()) and xdata.F_DISC not in fields


# ── reconocer una hoja sin capas ────────────────────────────────────────────
def test_alcantarillado_de_mapa_sigue_la_tinta_y_pone_sus_buzones(tmp_path):
    target = tmp_path / "red.pdf"
    A, B, C, D = _network_pdf(target)
    with fitz.open(target) as doc:
        roles = {rec.ROLE_LINEAS: [_style(doc, 0.73)], rec.ROLE_BUZONES: []}
    r = rec.recognize_page(target, utility="ALCANTARILLADO", layer_roles=roles, zoom=1, scale_ft_per_pt=1)
    pts = [p for pl in r.drawable for p in pl.pts_pdf]
    assert all(abs(p[1] - 200) <= 0.5 or abs(p[0] - 350) <= 0.5 for p in pts)     # sobre la tinta
    vaults = {(round(x), round(y)) for x, y in r.vault_pts}
    assert {B, C} <= vaults                                      # buzones donde terminan las tuberías
    kinds = {(round(x), round(y)): k for pl in r.drawable for (x, y), k in zip(pl.pts_pdf, pl.kinds)}
    assert kinds[B] == "vault" and kinds[C] == "vault"
    assert not any(pl.abandoned for pl in r.drawable)
    assert any(w.startswith("Buzones donde terminan las tuberías del mapa") for w in r.warnings)
    # red a PRESIÓN: los cortes no son buzones (son accesorios)
    with fitz.open(target) as doc:
        roles = {rec.ROLE_LINEAS: [_style(doc, 0.73)], rec.ROLE_BUZONES: []}
    agua = rec.recognize_page(target, utility="AGUA", layer_roles=roles, zoom=1, scale_ft_per_pt=1)
    assert agua.drawable and not agua.vault_pts


def test_capa_cad_con_nombre_no_cambia(tmp_path):
    """Las reglas nuevas son solo para capas por ESTILO: una capa OCG con nombre sigue
    por el núcleo (aunque sus trazos sean continuos)."""
    doc = fitz.open()
    oc = doc.add_ocg("C-SSWR-UNGD-E")
    page = doc.new_page(width=600, height=400)
    sh = page.new_shape()
    sh.draw_polyline([(50, 200), (200, 200)]); sh.draw_polyline([(200, 200), (350, 200)])
    sh.finish(color=(0, 0, 0), width=0.73, closePath=False, oc=oc); sh.commit()
    target = tmp_path / "ocg.pdf"
    doc.save(target)
    r = rec.recognize_page(target, utility="ALCANTARILLADO", zoom=1, scale_ft_per_pt=1)
    assert r.drawable
    assert not any(w.startswith(("Buzones donde terminan", "Capas por estilo de trazo continuo")) for w in r.warnings)


# ── «Capas de la hoja» ──────────────────────────────────────────────────────
def test_hoja_sin_capas_reconoce_solo_lo_asignado(tmp_path):
    from ui.asistente.layer_dialog import SheetLayersDialog
    _app()
    target = tmp_path / "red.pdf"
    _network_pdf(target)
    doc = fitz.open(target)
    dlg = SheetLayersDialog(None, doc, 0)
    try:
        assert not dlg.btn_ok.isEnabled() and not dlg.lbl_recog_warn.isHidden()
        assert "Hoja sin capas" in dlg.lbl_recog_warn.text()
        assert not any(cb.isEnabled() for cb in dlg._recog_checks.values())
        name = _style(doc, 0.73)
        dlg.tree.setCurrentItem(dlg._items_by_name[name][0])
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("ALCANTARILLADO"))
        assert dlg.btn_ok.isEnabled() and dlg.lbl_recog_warn.isHidden()
        assert dlg.recognition_utilities() == ("ALCANTARILLADO",)
        assert [k for k, cb in dlg._recog_checks.items() if cb.isEnabled()] == ["ALCANTARILLADO"]
    finally:
        dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


def test_calibrar_la_escala_con_dos_clics(tmp_path, monkeypatch):
    from ui.asistente import layer_dialog
    _app()
    target = tmp_path / "red.pdf"
    A, B, _C, _D = _network_pdf(target)
    doc = fitz.open(target)
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0, scale_ft_per_pt=20 / 72.0)
    try:
        assert dlg.btn_scale.text() == "Escala 1\"=20'" and dlg.scale_ft_per_pt() is None
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", staticmethod(lambda *a, **k: (300.0, True)))
        dlg._start_calibration()
        assert dlg.calibrating()
        z = dlg._render_zoom()
        dlg._calib_click(QtCore.QPointF(A[0] * z, A[1] * z))
        dlg._calib_click(QtCore.QPointF(B[0] * z, B[1] * z))       # 150 pt entre A y B
        _app().processEvents()
        assert not dlg.calibrating()
        assert abs(dlg.scale_ft_per_pt() - 300.0 / 150.0) < 1e-9
        assert dlg.btn_scale.text() == "Escala 1\"=144'"
        dlg._start_calibration()
        assert dlg._escape() and not dlg.calibrating()              # Esc sale de la calibración
    finally:
        dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()
    # sin escala (hoja compuesta de varias piezas): no hay botón
    doc = fitz.open(target)
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0)
    try:
        assert not hasattr(dlg, "btn_scale") and dlg.scale_ft_per_pt() is None
    finally:
        dlg._timer.stop(); dlg._stop_legend(); dlg.deleteLater(); doc.close()


# ── punta a punta con el PDF real ───────────────────────────────────────────
@pytest.fixture
def win(monkeypatch):
    app = _app()
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    w = app_window.Main()
    yield w
    w._dirty = False
    w.close()
    app.processEvents()


@needs_phoenix
def test_phoenix_alcantarillado_de_pdf_sin_capas_a_dxf(win, tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    from ui.asistente import layer_dialog
    from ui.comun.workers import RecognitionWorker
    win._open_pdf_path(str(SEWER))
    win._load_page(0)
    assert abs(win.scale * 72 - 20.0) < 1e-6                      # el texto no se lee: 1"=20' por defecto
    dlg = layer_dialog.SheetLayersDialog(win, win.doc, 0, recognition_utilities=win._recognition_utilities,
                                         scale_ft_per_pt=win._scale_editable())
    name = _style(win.doc, 0.73)
    dlg.tree.setCurrentItem(dlg._items_by_name[name][0])
    dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("ALCANTARILLADO"))
    dlg._set_scale(160 / 72.0)
    roles, utils, scale = dlg.roles_by_utility(), dlg.recognition_utilities(), dlg.scale_ft_per_pt()
    dlg.accept(); dlg.deleteLater()
    assert utils == ("ALCANTARILLADO",)
    win._recognition_utilities, win._layer_roles_by_utility = utils, roles
    win._calibrated_scale(scale)
    win._load_page(0)
    assert abs(win.scale * 72 - 160.0) < 1e-6
    got = {}
    w = RecognitionWorker(win.work_pdf_path or win.pdf_path, 0, zoom=win.zoom, utilities=utils,
                          hidden_ocgs=win.hidden_ocgs, roles_by_utility=roles, letters_off=win._letters_off,
                          join_routes=True, scale_ft_per_pt=win._scale_override)
    w.done.connect(lambda r, e: got.update(r=r, e=e))
    w.run()
    assert not got["e"]
    res = got["r"] if isinstance(got["r"], list) else [got["r"]]
    assert [r.utility for r in res] == ["ALCANTARILLADO"]
    r = res[0]
    assert len(r.drawable) >= 60 and len(r.vault_pts) >= 90          # hoja 17-10: 69 líneas, 102 buzones
    # cada vértice sobre la tinta del estilo (≤ la tolerancia de simplificación)
    page = win.doc[0]
    ink_segs = [(fitz.Point(a) * page.rotation_matrix * win.zoom, fitz.Point(b) * page.rotation_matrix * win.zoom)
                for d in pdf_styles.drawings(page) if d.get("layer") == name
                for it in d["items"] if it[0] == "l" for a, b in [(it[1], it[2])]]
    for pl in r.drawable[:20]:
        for p in pl.pts_pdf:
            d = min(ink._seg_dist(p, (a.x, a.y), (b.x, b.y))[1] for a, b in ink_segs)
            assert d <= (ink.SIMPLIFY_PT + 0.05) * win.zoom, p
    n0 = len(win.pipes)
    win._import_recognized_pipes(res)
    new = win.pipes[n0:]
    assert len(new) == len(r.drawable) and {p["layer"] for p in new} == {"ALCANTARILLADO"}
    import config as C
    doc = ezdxf.new("R2010", setup=True)
    C.apply_imperial_header(doc)
    win._merge_into(doc, marks=True)
    out = tmp_path / "phoenix.dxf"
    doc.saveas(out)

    def xd(e):
        try:
            return {s.split("=", 1)[0]: s.split("=", 1)[1] for c, s in e.get_xdata("PDFCAD") if c == 1000 and "=" in s}
        except Exception:
            return {}
    pipes = [x for x in (xd(e) for e in ezdxf.readfile(out).modelspace()) if "NET_KIND" in x and "DIAMETER" in x]
    assert pipes and {x["NET_KIND"] for x in pipes} == {"gravity"}
    assert {x.get("XD_CAPA") for x in pipes} == {"Estilo Negro 0.73 pt · continuo"}
    assert not any(x.get("ABANDONED") == "1" for x in pipes)
