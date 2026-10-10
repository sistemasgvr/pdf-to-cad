"""Editar varias utilidades del mismo tipo a la vez y copiar/pegar propiedades:
lógica pura (edicion_bloque.py), la ventana del diálogo y la ventana real."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import edicion_bloque as E  # noqa: E402
from nucleo import xdata  # noqa: E402
from nucleo.model_ops import DIAM_DEFECTO_IN  # noqa: E402


def _p(layer="ELECTRICO", **k):
    d = dict(layer=layer, pts=[(0, 0), (100, 0)], name="", diam=DIAM_DEFECTO_IN, material="PVC")
    d.update(k)
    return d


def test_tipos_y_familia_comun():
    pipes = [_p(), _p(pipe_family="f1"), _p(layer="AGUA", pipe_family="f1")]
    assert E.tipos(pipes, [0, 1, 2]) == ["ELECTRICO", "AGUA"]
    assert E.mismo_tipo(pipes, [0, 1]) and not E.mismo_tipo(pipes, [0, 2])
    assert E.familia_comun(pipes, [1, 2]) == "f1" and E.familia_comun(pipes, [0, 1]) is None


def test_familia_y_tamano_dan_el_diametro():
    pipes = [_p(), _p(pipe_family="vieja", pipe_size="6 in", diam=6.0)]
    n = E.aplicar(pipes, [0, 1], {"familia": "f1", "tamano": "24 in"})
    assert n == 2
    assert all(p["pipe_family"] == "f1" and p["pipe_size"] == "24 in" and p["diam"] == 24.0 for p in pipes)


def test_cambiar_familia_sin_tamano_vuelve_al_diametro_por_defecto():
    pipes = [_p(pipe_family="vieja", pipe_size="6 in", diam=6.0)]
    E.aplicar(pipes, [0], {"familia": "f2"})
    assert pipes[0]["pipe_size"] == "" and pipes[0]["diam"] == DIAM_DEFECTO_IN


def test_solo_tamano_respeta_la_familia():
    pipes = [_p(pipe_family="f1", pipe_size="6 in", diam=6.0), _p(pipe_family="f1")]
    E.aplicar(pipes, [0, 1], {"tamano": "10 in"})
    assert [(p["pipe_family"], p["pipe_size"], p["diam"]) for p in pipes] == [("f1", "10 in", 10.0)] * 2


def test_con_bancoducto_no_cambia_familia_pero_si_lo_demas():
    pipes = [_p(), _p()]
    E.aplicar(pipes, [0, 1], {"familia": "f1", "tamano": "8 in", "ab": True, "net_type": "pressure"},
              sin_familia=[1])
    assert pipes[0]["pipe_family"] == "f1" and not pipes[1].get("pipe_family")
    assert pipes[1]["ab"] is True and pipes[1]["net_type"] == "pressure"


def test_lo_que_no_se_pide_no_cambia_y_se_cuentan_solo_las_cambiadas():
    pipes = [_p(material="HDPE", ab=False), _p(material="PVC", ab=True)]
    n = E.aplicar(pipes, [0, 1], {"ab": True})
    assert n == 1                                           # la segunda ya era abandonada
    assert [p["material"] for p in pipes] == ["HDPE", "PVC"]


def test_datos_del_usuario_se_suman():
    a = _p()
    xdata.set_user(a, {"Dueño": "Metro", "Notas": "vieja"})
    E.aplicar([a], [0], {"datos": {"Notas": "nueva", "Proyecto": "L2"}})
    assert xdata.get(a)[xdata.USER] == {"Dueño": "Metro", "Notas": "nueva", "Proyecto": "L2"}


def test_valores_de_y_copiar_entre_utilidades():
    src = _p(pipe_family="f1", pipe_size="12 in", diam=12.0, net_type="pipe", material="HDPE", ab=True)
    xdata.set_user(src, {"Dueño": "Metro"})
    dst = [_p(), _p()]
    v = E.valores_de(src)
    E.aplicar(dst, [0, 1], v)
    for p in dst:
        assert E.valores_de(p) == v and p["diam"] == 12.0


# ─────────────────────────── diálogo ───────────────────────────

@pytest.fixture
def qapp():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _dlg(familia_comun="f1", inicial=None, datos=None):
    from ui.dialogos.edicion_bloque_dialog import EdicionBloqueDialog
    tam = {"f1": ["6 in", "10 in"], "f2": ["8 in", "24 in"]}
    return EdicionBloqueDialog(None, "t", 3, "Eléctrico", [("f1", "Fam 1"), ("f2", "Fam 2")],
                               lambda fid: tam.get(fid, []), familia_comun,
                               [("PVC", "PVC"), ("HDPE", "HDPE")], [("Automático", ""), ("Presión", "pressure")],
                               inicial=inicial, datos=datos)


def test_dialogo_sin_cambios_no_pide_nada(qapp):
    assert _dlg().cambios() == {}


def test_dialogo_solo_tamano(qapp):
    d = _dlg()
    d.cmb_tamano.setCurrentIndex(d.cmb_tamano.findData("10 in"))
    assert d.cambios() == {"tamano": "10 in"}


def test_dialogo_familias_distintas_no_deja_elegir_tamano_sin_familia(qapp):
    d = _dlg(familia_comun=None)
    assert not d.cmb_tamano.isEnabled()
    d.cmb_familia.setCurrentIndex(d.cmb_familia.findData("f2"))
    assert d.cmb_tamano.isEnabled() and d.cambios() == {"familia": "f2", "tamano": ""}
    d.cmb_tamano.setCurrentIndex(d.cmb_tamano.findData("24 in"))
    d.cmb_estado.setCurrentIndex(d.cmb_estado.findData(True))
    assert d.cambios() == {"familia": "f2", "tamano": "24 in", "ab": True}


def test_dialogo_pegar_arranca_con_los_valores_copiados(qapp):
    v = {"familia": "f2", "tamano": "8 in", "net_type": "pressure", "material": "HDPE", "ab": False,
         "datos": {"Dueño": "Metro"}}
    d = _dlg(inicial=v, datos=v["datos"])
    assert d.cambios() == v


# ─────────────────────────── ventana ───────────────────────────

@pytest.fixture
def win(monkeypatch, qapp):
    from PySide6 import QtGui, QtWidgets
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    from nucleo.duct_bank import DuctBank
    w = Main()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.pipes = [_p(pts=[(100, 100 + 50 * i), (600, 100 + 50 * i)]) for i in range(3)]
    w.pipes.append(_p(layer="AGUA", pts=[(100, 400), (600, 400)]))
    db = DuctBank(name="DB"); db.assign([2]); w.duct_banks = [db]
    w._refresh_lists(); w._redraw()
    w.avisos = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda _p, _t, msg, *a: w.avisos.append(msg))
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _seleccionar(w, filas):
    w._show_tab(0)
    w.pipe_list.clearSelection()
    w.pipe_list.setCurrentRow(filas[0])
    w._reselect_pipes(filas)


def _dialogo_falso(monkeypatch, cambios, vistos):
    from ui.dialogos import edicion_bloque_dialog as D

    class Falso:
        def __init__(self, _parent, titulo, n, tipo, *a, **k):
            vistos.append(dict(titulo=titulo, n=n, tipo=tipo, **k))

        def exec(self):
            return 1

        def cambios(self):
            return dict(cambios)
    monkeypatch.setattr(D, "EdicionBloqueDialog", Falso)


def test_editar_en_bloque_y_deshacer(win, monkeypatch):
    vistos = []
    _dialogo_falso(monkeypatch, {"familia": "f1", "tamano": "8 in", "ab": True}, vistos)
    _seleccionar(win, [0, 1, 2])
    win.editar_en_bloque()
    assert vistos[0]["n"] == 3 and vistos[0]["con_bancoducto"] == 1
    assert [p.get("pipe_size") for p in win.pipes[:3]] == ["8 in", "8 in", None]   # la del bancoducto no
    assert all(p["ab"] for p in win.pipes[:3]) and not win.pipes[3].get("ab")
    win.undo()
    assert not any(p.get("pipe_size") for p in win.pipes)


def test_editar_en_bloque_exige_el_mismo_tipo(win, monkeypatch):
    vistos = []
    _dialogo_falso(monkeypatch, {"ab": True}, vistos)
    _seleccionar(win, [0, 3])
    win.editar_en_bloque()
    assert not vistos and win.avisos and "tipos distintos" in win.avisos[-1]
    assert not any(p.get("ab") for p in win.pipes)


def test_copiar_y_pegar_propiedades_solo_al_mismo_tipo(win, monkeypatch):
    vistos = []
    win.pipes[0].update(pipe_family="f1", pipe_size="10 in", diam=10.0)
    _seleccionar(win, [0])
    win.copiar_propiedades()
    _dialogo_falso(monkeypatch, E.valores_de(win.pipes[0]), vistos)
    _seleccionar(win, [1, 3])                               # una eléctrica y una de agua
    win.pegar_propiedades()
    assert vistos[0]["n"] == 1 and vistos[0]["saltadas"] == 1
    assert vistos[0]["inicial"]["tamano"] == "10 in"
    assert win.pipes[1]["pipe_size"] == "10 in" and not win.pipes[3].get("pipe_size")


def test_copiar_de_la_primera_a_las_demas(win, monkeypatch):
    vistos = []
    win.pipes[1].update(material="HDPE")
    _dialogo_falso(monkeypatch, {"material": "HDPE"}, vistos)
    win._show_tab(0)
    win.pipe_list.setCurrentRow(1)
    win._toggle_pipe_selection(0)                            # la 1.ª elegida (#2) es la base
    win.copiar_de_la_primera()
    assert vistos[0]["inicial"]["material"] == "HDPE" and vistos[0]["n"] == 1
    assert win.pipes[0]["material"] == "HDPE"


def test_tipo_y_amperaje_en_bloque():
    pipes = [_p(tipo="DISTRIBUCION PRINCIPAL"), _p(amperaje=200.0)]
    n = E.aplicar(pipes, [0, 1], {"tipo": "INSTALACION DOMICILIARIA", "amperaje": 350.0})
    assert n == 2 and all(p["tipo"] == "INSTALACION DOMICILIARIA" and p["amperaje"] == 350.0 for p in pipes)
    E.aplicar(pipes, [0], {"tipo": "", "amperaje": 0})
    assert pipes[0]["tipo"] == "" and pipes[0]["amperaje"] is None
    assert E.valores_de(pipes[1])["tipo"] == "INSTALACION DOMICILIARIA"


def test_dialogo_tipo_y_amperaje(qapp):
    from ui.dialogos.edicion_bloque_dialog import EdicionBloqueDialog
    d = EdicionBloqueDialog(None, "t", 2, "Eléctrico", [], lambda f: [], None, [], [],
                            tipos=["DISTRIBUCION PRINCIPAL", "INSTALACION DOMICILIARIA"], con_amperaje=True)
    assert d.cambios() == {}
    d.cmb_tipo.setCurrentIndex(d.cmb_tipo.findData("INSTALACION DOMICILIARIA"))
    d.spn_amp.setValue(320)
    assert d.cambios() == {"tipo": "INSTALACION DOMICILIARIA", "amperaje": 320.0}
