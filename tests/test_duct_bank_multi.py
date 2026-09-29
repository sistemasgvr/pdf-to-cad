"""Bancoductos en varias utilidades + selección masiva + miniaturas (ventana
real, Qt offscreen)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import i18n  # noqa: E402
import i18n_core  # noqa: E402


@pytest.fixture
def win(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from app_window import Main
    from duct_bank import DuctBank, Conduit
    w = Main()
    w.pipes = [{"layer": "ELECTRICO", "pts": [(0, 100 * i), (200, 100 * i)], "name": ""}
               for i in range(5)]
    db = DuctBank(name="A", width_in=16, height_in=10,
                  conduits=[Conduit(cx=4, cy=4, diam=4, label="E1")])
    db.assign([1, 3])
    w.duct_banks = [db, DuctBank(name="B", pipe_idx=4)]
    w._refresh_lists()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def _select(w, rows, current):
    w.pipe_list.setCurrentRow(current)
    sm = w.pipe_list.selectionModel()
    for r in rows:
        sm.select(w.pipe_list.model().index(r, 0), QtCore.QItemSelectionModel.Select)


def test_lista_muestra_varias_utilidades(win):
    assert "#2, #4" in win.db_list.item(0).text()
    assert win._duct_bank_for_pipe(3) is win.duct_banks[0]
    assert win._duct_bank_for_pipe(0) is None


def test_seleccion_multiple_y_borrado_reindexa(win, monkeypatch):
    _select(win, [0, 2], current=0)
    assert win._selected_pipe_rows() == [0, 2]
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.Yes)
    win._show_tab(0)
    win.delete_selected()
    assert len(win.pipes) == 3
    # 1→0, 3→1, 4→2
    assert win.duct_banks[0].assigned() == [0, 1]
    assert win.duct_banks[1].assigned() == [2]
    win.undo()
    assert len(win.pipes) == 5
    assert win.duct_banks[0].assigned() == [1, 3]


def test_seleccion_vieja_no_cuenta_sin_la_actual(win):
    _select(win, [0, 2], current=0)
    win.sel_pipe = 4      # p. ej. clic en el lienzo sin pasar por la lista
    assert win._selected_pipe_rows() == [4]


def test_asignar_en_bloque_quita_de_otros(win):
    win._db_assign_to_pipes(0, [0, 4])
    assert win.duct_banks[0].assigned() == [0, 1, 3, 4]
    # «B» solo tenía la 4: se queda sin utilidades y se quita (como al rediseñar)
    assert [d.name for d in win.duct_banks] == ["A"]
    win._db_unassign_pipes([1, 3])
    assert win.duct_banks[0].assigned() == [0, 4]


def test_miniaturas(win):
    idx = win.db_list.model().index(0, 0)
    pix, cap = win._db_preview(idx)
    assert not pix.isNull() and "A" in cap
    assert win._pipe_thumbnail(2) is not None
    assert win._pipe_thumbnail(99) is None


def test_disenador_asigna_varias(win):
    from duct_bank_dialog import DuctBankDialog
    dlg = DuctBankDialog(win, initial=win.duct_banks[0], pipes=win.pipes,
                         pipe_thumb=win._pipe_thumbnail, taken={4: "B"})
    marcadas = [dlg.lst_pipes.item(r).checkState() == QtCore.Qt.Checked
                for r in range(dlg.lst_pipes.count())]
    assert marcadas == [False, True, False, True, False]
    assert dlg.result_model().assigned() == [1, 3]
    dlg.ed_pipe_filter.setText("#5")
    dlg._set_all_pipes(True)                 # solo la visible (#5)
    assert dlg.result_model().assigned() == [1, 3, 4]
    assert "reemplazar" in dlg.lbl_pipe_status.text()
    pix, cap = dlg._pipe_preview(dlg.lst_pipes.model().index(4, 0))
    assert pix is not None and "B" in cap           # ya tiene «B»: se avisa
    # Sin show(): mostrar el diseñador en el proceso de pytest deja un objeto
    # que revienta después en la recolección de basura (pasa igual con el
    # diseñador anterior); el globo se prueba abajo sobre una lista suelta.
    dlg.reject()


def test_globo_de_miniatura_reemplaza_tooltip(win):
    from thumbnails import HoverPreview
    lst = QtWidgets.QListWidget()
    lst.addItems(["a", "b"])
    pm = QtGui.QPixmap(40, 30); pm.fill(QtGui.QColor("red"))
    hp = HoverPreview(lst, lambda idx: (pm, "fila") if idx.row() == 0 else None)
    # Sin processEvents: los restos de test_composite_dialog reaccionan a él.
    lst.resize(200, 120); lst.show()
    vp = lst.viewport()

    def tip(row):
        c = lst.visualItemRect(lst.item(row)).center()
        return hp.eventFilter(vp, QtGui.QHelpEvent(QtCore.QEvent.ToolTip, c, vp.mapToGlobal(c)))
    assert tip(0) is True and hp._popup.isVisible()
    assert tip(1) is False and not hp._popup.isVisible()   # None → tooltip normal
    lst.close()
