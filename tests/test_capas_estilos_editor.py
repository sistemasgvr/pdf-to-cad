"""«Capas y estilos…» del panel «Reconocer»: lo de «Capas de la hoja» como vista del centro del editor (plan
2026-11-16, «reconocimiento desde el editor», Tarea 8).

Ventana real (Qt offscreen, a la vista: la vista se INCRUSTA en el centro) sobre DU06 h.3 (índice 2) y una hoja
sin capas de Phoenix (Water South h.4). Aplicar cambia las capas, roles, letras y escala de la ventana y el estado de
las filas (bloquear / desbloquear / «desactualizada»); Cancelar no cambia nada. El diálogo de siempre (asistente)
sigue igual.
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
from PySide6 import QtWidgets  # noqa: E402

from hoja import interpretar_trabajo as IT, pdf_layers  # noqa: E402
from nucleo import reconocer_estado as RE  # noqa: E402
from reconocimiento import lectura_retenida as LR, recognition as rec  # noqa: E402
from ui.comun import fondo_trabajo  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
WATER_S = Path(r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/QS Water_Indian School_South.pdf")
AGUA_E = "PS89616000-A1-UW-REF-EXIST_WATER|C-WATR-UNGD-E"


def _ventana(monkeypatch, pdf, hoja):
    if not pdf.is_file():
        pytest.skip(f"falta {pdf.name}")
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    monkeypatch.setattr(app_window.Main, "_run_recognition_wizard", lambda self: None)
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    w = app_window.Main()
    w.resize(1400, 860)
    w.show()
    w._open_pdf_path(str(pdf))
    w._load_page(hoja)
    app.processEvents()
    # la interpretación de la hoja (Tarea 9 la hará al abrir), leída en OTRO documento (como el trabajador)
    w._interpretacion = IT.interpretar(fondo_trabajo.ruta_de(w.doc), w.page_idx, pdf_layers.encendidas(w.doc),
                                       firma="hoja", escala=w.scale)
    LR.soltar()
    w.reconocer_estado = RE.de_interpretacion(None, w._interpretacion, "hoja", hidden=w.hidden_ocgs,
                                              roles_by_utility=w._roles_de_la_hoja(w.page_idx))
    return app, w


@pytest.fixture
def du06(monkeypatch):
    app, w = _ventana(monkeypatch, DU06, 2)
    yield w
    _cerrar(app, w)


@pytest.fixture
def phoenix(monkeypatch):
    app, w = _ventana(monkeypatch, WATER_S, 3)
    yield w
    _cerrar(app, w)


def _cerrar(app, w):
    dlg = getattr(w, "_capas_estilos_dlg", None)
    if dlg is not None:
        dlg.reject()
    LR.soltar()
    w._dirty = False
    w.close()
    app.processEvents()


def _abrir(w, parte=None):
    w.abrir_capas_estilos(parte)
    dlg = w._capas_estilos_dlg
    assert dlg is not None
    assert w.centro.currentWidget() is dlg                  # incrustada en el centro de la ventana
    QtWidgets.QApplication.processEvents()
    return dlg


def _asignar(dlg, nombre, utilidad, rol):
    it = dlg._items_by_name[nombre][0]
    dlg.expandir_hasta(it)
    dlg.tree.setCurrentItem(it)
    dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData(utilidad))
    dlg.assignment_role.setCurrentIndex(dlg.assignment_role.findData(rol))


# ── el diálogo de siempre y el modo editor ──────────────────────────────────
def _hoja_con_capas():
    doc = fitz.open()
    capas = {n: doc.add_ocg(n) for n in ("C-WATR-UNGD-E", "C-ELEC-UNGD-E", "G-ROAD")}
    p = doc.new_page(width=800, height=600)
    for i, oc in enumerate(capas.values()):
        p.draw_line((30, 50 + i * 60), (700, 50 + i * 60), width=1, oc=oc)
    datos = doc.tobytes()
    doc.close()
    return fitz.open(stream=datos, filetype="pdf")


@pytest.mark.parametrize("editor", [False, True])
def test_el_asistente_sigue_igual_y_el_modo_editor_no_tiene_pasos(editor):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.asistente import layer_dialog
    doc = _hoja_con_capas()
    dlg = layer_dialog.SheetLayersDialog(None, doc, 0, editor=editor)
    try:
        assert dlg._cabecera.isVisibleTo(dlg) is not editor                # barra de pasos «Atrás»
        assert dlg.pastilla_hoja.isHidden() is editor                      # ◀ Hoja N / M ▶
        assert dlg._recog_box.isVisibleTo(dlg) is not editor               # tarjeta «Reconocer»
        assert dlg.tree.isColumnHidden(1) is editor                        # su interruptor en el árbol
        assert dlg.btn_ok.text() == ("Aplicar" if editor else "Continuar")
    finally:
        dlg.reject()
        dlg.deleteLater()
        doc.close()


# ── con la interpretación, no se relee la hoja en la ventana ────────────────
def test_con_la_interpretacion_no_lee_la_hoja_en_la_ventana(du06, monkeypatch):
    leidas = []
    for metodo in ("get_drawings", "get_cdrawings"):
        real = getattr(fitz.Page, metodo)

        def contar(self, *a, _real=real, **k):
            if self.parent is du06.doc:
                leidas.append(metodo)
            return _real(self, *a, **k)
        monkeypatch.setattr(fitz.Page, metodo, contar)
    monkeypatch.setattr(pdf_layers, "page_layers", lambda *a, **k: leidas.append("page_layers") or [])
    dlg = _abrir(du06, "AGUA")
    assert leidas == []
    assert dlg._groups["AGUA"].isExpanded()                     # abre en la utilidad de la fila
    assert {L["name"] for L in dlg._layers_raw} == {L["name"] for L in du06._interpretacion["layers"]}


# ── aplicar ─────────────────────────────────────────────────────────────────
def test_ocultar_todas_las_capas_de_agua_bloquea_su_fila_sin_tocar_el_editor(du06):
    assert du06.reconocer_estado.filas["AGUA"].estado == "pendiente"
    du06.pipes = [{"layer": "AGUA", "pts": [(5.0, 5.0), (45.0, 5.0)], "ab": False}]
    dlg = _abrir(du06, "AGUA")
    dlg.set_utility_visible("AGUA", False)
    dlg.btn_ok.click()
    QtWidgets.QApplication.processEvents()
    f = du06.reconocer_estado.filas["AGUA"]
    assert (f.estado, f.motivo) == ("bloqueada", RE.M_OCULTAS)
    assert du06.reconocer_estado.filas["ELECTRICO"].estado == "pendiente"
    assert AGUA_E in du06.hidden_ocgs and AGUA_E in pdf_layers.hidden_layers(du06.doc)
    assert len(du06.pipes) == 1                                 # el editor no se recarga
    assert du06.centro.currentWidget() is not dlg               # vuelve al plano
    assert du06._capas_estilos_dlg is None


def test_cancelar_no_cambia_nada(du06):
    antes = (list(du06.hidden_ocgs), set(pdf_layers.hidden_layers(du06.doc)),
             RE.a_dict(du06.reconocer_estado))
    dlg = _abrir(du06)
    dlg.set_utility_visible("AGUA", False)
    dlg.reject()
    QtWidgets.QApplication.processEvents()
    assert (list(du06.hidden_ocgs), set(pdf_layers.hidden_layers(du06.doc)),
            RE.a_dict(du06.reconocer_estado)) == antes


def test_cambiar_roles_de_agua_reconocida_solo_la_deja_desactualizada(du06):
    e = du06.reconocer_estado
    for u in ("AGUA", "ELECTRICO"):
        e.filas[u].estado, e.filas[u].firma = "reconocida", du06._firma_parte_actual(u)
    dlg = _abrir(du06, "AGUA")
    _asignar(dlg, AGUA_E, "AGUA", rec.ROLE_BUZONES)
    dlg.btn_ok.click()
    QtWidgets.QApplication.processEvents()
    assert AGUA_E in (du06._layer_roles_by_utility["AGUA"][rec.ROLE_BUZONES])
    assert e.filas["AGUA"].estado == "desactualizada"
    assert e.filas["ELECTRICO"].estado == "reconocida"


def test_hoja_sin_capas_asignar_un_estilo_desbloquea_la_fila(phoenix):
    f = phoenix.reconocer_estado.filas["TELECOM"]
    assert (f.estado, f.motivo) == ("bloqueada", RE.M_SIN_ESTILOS)
    dlg = _abrir(phoenix, "TELECOM")
    libre = next(L["name"] for L in dlg._layers_raw
                 if L.get("source") == "style" and L["name"] not in dlg._assignments and L.get("path_count"))
    _asignar(dlg, libre, "TELECOM", rec.ROLE_LINEAS)
    dlg.btn_ok.click()
    QtWidgets.QApplication.processEvents()
    assert libre in phoenix._layer_roles_by_utility["TELECOM"][rec.ROLE_LINEAS]
    assert phoenix.reconocer_estado.filas["TELECOM"].estado == "pendiente"
