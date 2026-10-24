"""IA → «Pasar a producción» (pedido del usuario 2026-10-24): enseñanzas de desarrollo → produccion.json."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ia import memoria as M  # noqa: E402
from ia import produccion as PR  # noqa: E402


def _entorno(tmp_path, monkeypatch):
    prod = tmp_path / "entrenamiento_ia" / "produccion.json"
    monkeypatch.setenv("PDFCAD_ENTRENAMIENTO_IA_BASE", str(prod))
    return prod


def test_pasar_y_quitar_de_produccion(tmp_path, monkeypatch):
    prod = _entorno(tmp_path, monkeypatch)
    mem = M.Memoria(str(tmp_path / "Obra.digproj"))
    a = mem.ensenar(M.NOTA, "Los cruces con drenaje se resuelven bajando el agua")
    b = mem.ensenar(M.NOTA, "una prueba que no va")
    mem.agregar(M.CONVERSACIONES, pregunta="hola", respuesta="hola")
    mem.guardar_redaccion("norma1", "explicación", "m")
    mem.ambito = "normas"
    mem.guardar_redaccion("norma2", "explicación de una regla")
    dev, pro = PR.almacenes()
    assert [en for _r, en in PR.lista(dev, pro)] == [False, False]
    assert PR.redaccion_general(dev, pro) == ["norma2"]                     # «proyecto» no es general
    assert PR.pasar(dev, pro, [a["id"]], con_redaccion=True) == (1, 1)
    d = json.load(open(prod, encoding="utf-8"))
    assert [r["texto"] for r in d["ensenanzas"]] == [a["texto"]] and d["conversaciones"] == []
    assert list(d["redaccion"]) == ["norma2"]
    assert PR.pasar(dev, pro, [a["id"]]) == (0, 0)                           # repetir no duplica
    assert {r["id"]: en for r, en in PR.lista(dev, pro)} == {a["id"]: True, b["id"]: False}
    # el programa del cliente (producción) la usa
    cliente = M.Memoria(archivo=str(tmp_path / "cliente.json"))
    cliente.bases = [M.Almacen.de(str(prod))]
    assert cliente.buscar("cruce drenaje")[0]["texto"] == a["texto"]
    assert PR.quitar(pro, [a["id"]]) == 1
    assert json.load(open(prod, encoding="utf-8"))["ensenanzas"] == []


def test_dialogo_pasar_a_produccion(tmp_path, monkeypatch):
    from PySide6 import QtCore, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.dialogos.ia_produccion_dialog import ProduccionDialog
    prod = _entorno(tmp_path, monkeypatch)
    mem = M.Memoria()
    mem.ensenar(M.NOTA, "va a producción")
    mem.ensenar(M.CORRECCION, "la respuesta buena", pregunta="¿qué pasa?")
    dlg = ProduccionDialog(None)
    assert dlg.tabla.rowCount() == 2 and not dlg.btn_pasar.isEnabled()
    dlg.tabla.item(0, 0).setCheckState(QtCore.Qt.Checked)
    assert dlg.btn_pasar.isEnabled()
    dlg.pasar()
    assert len(json.load(open(prod, encoding="utf-8"))["ensenanzas"]) == 1
    assert dlg.tabla.rowCount() == 1                                         # «solo las que faltan»
    dlg.chk_faltan.setChecked(False)
    assert dlg.tabla.rowCount() == 2 and "✔" in {dlg.tabla.item(i, 5).text() for i in range(2)}
