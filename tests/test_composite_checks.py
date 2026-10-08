"""«Componer hoja» en pestañas: qué falta para continuar (puro) y la barra de pestañas."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hoja import composite_checks as CK  # noqa: E402


def test_sin_piezas_no_se_puede_continuar():
    found = CK.checks(0)
    assert [c.code for c in found] == ["no_pieces"] and not CK.ready(found)
    # la hoja elegida entra sola: sin piezas solo queda elegir una hoja (en «Origen»)
    assert found[0].tab == CK.TAB_SOURCE and "elige una hoja" in found[0].text


def test_area_marcada_sin_piezas_no_bloquea():
    """Con solo un área marcada, «Continuar» la toma: se avisa pero no bloquea."""
    found = CK.checks(0, untaken_area_page=3)
    assert [c.code for c in found] == ["untaken_area"] and CK.ready(found)
    assert found[0].page == 3 and found[0].level == CK.WARN


def test_avisos_con_piezas():
    assert CK.checks(2) == []
    found = CK.checks(2, untaken_area_page=None, pending_page=5)
    assert [c.code for c in found] == ["pending_page"] and CK.ready(found)
    # el área marcada en la misma hoja ya explica que la hoja falta: un solo aviso
    found = CK.checks(2, untaken_area_page=5, pending_page=5)
    assert [c.code for c in found] == ["untaken_area"]
    found = CK.checks(2, untaken_area_page=4, pending_page=5)
    assert [c.code for c in found] == ["untaken_area", "pending_page"]


def test_hoja_sin_tomar_sin_piezas_la_tapa_el_paso_siguiente():
    assert [c.code for c in CK.checks(0, pending_page=2)] == ["no_pieces"]


def test_pestanas_insignias_y_teclado():
    from PySide6 import QtCore, QtTest, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.asistente import composite_tabs as CT
    tabs = CT.WorkTabs([("mdi:file-document-outline", "Origen"), ("mdi:vector-rectangle", "Área a tomar"),
                        ("mdi:vector-combine", "Hoja compuesta")])
    seen = []
    tabs.currentChanged.connect(seen.append)
    tabs.set_current(0)
    tabs.show(); app.processEvents()
    tabs.tabs[2].click()
    assert tabs.current() == 2 and seen == [0, 2]
    tabs.set_current(1, emit=False)                       # la cambia el diálogo: sin señal
    assert tabs.current() == 1 and seen == [0, 2] and tabs.tabs[1].isChecked()
    w0 = tabs.tabs[2].sizeHint().width()
    tabs.set_badge(2, "3")
    assert tabs.tabs[2].badge == ("3", CT.BADGE_COUNT) and tabs.tabs[2].sizeHint().width() > w0
    tabs.set_badge(1, "!", CT.BADGE_WARN)
    assert tabs.tabs[1].badge == ("!", CT.BADGE_WARN)
    tabs.set_badge(1, None)
    assert tabs.tabs[1].badge is None
    QtTest.QTest.keyClick(tabs, QtCore.Qt.Key_Right)       # ← → recorren las pestañas
    assert tabs.current() == 2 and seen[-1] == 2
    QtTest.QTest.keyClick(tabs, QtCore.Qt.Key_Right)
    assert tabs.current() == 0
    tabs.close()
