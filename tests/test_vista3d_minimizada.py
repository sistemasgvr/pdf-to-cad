"""Vista 3D minimizada (reporte del usuario 2026-11-18): «Ver en el plano» la minimiza; el botón del riel / F3
no la restauraba (`show()` no saca una ventana del estado minimizado) y, en otro monitor, ni se veía. Ahora el
botón la restaura, «Ver en el plano» avisa con «Volver a la Vista 3D» y el riel marca que sigue abierta."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_vista3d import _esperar, win  # noqa: E402,F401


def _eventos():
    from PySide6 import QtWidgets
    for _ in range(5):
        QtWidgets.QApplication.processEvents()


def test_el_boton_restaura_la_vista_3d_minimizada(win):
    dlg = win.abrir_vista3d(); _esperar(dlg)
    dlg.showMinimized(); _eventos()
    assert dlg.isMinimized()
    assert win.abrir_vista3d() is dlg
    _eventos()
    assert dlg.isVisible() and not dlg.isMinimized()


def test_ver_en_el_plano_avisa_y_su_accion_vuelve_a_la_3d(win, monkeypatch):
    from ui.comun import aviso_breve
    avisos = []
    monkeypatch.setattr(aviso_breve, "mostrar", lambda w, titulo, detalle="", accion=None, tono="ok":
                        avisos.append((titulo, detalle, accion, tono)))
    monkeypatch.setattr(win, "_incrustar_ok", lambda: True)
    dlg = win.abrir_vista3d(); _esperar(dlg)
    dlg._ficha_al_plano(); _eventos()
    assert dlg.isMinimized()
    (titulo, detalle, accion, tono), = avisos
    assert titulo == "La Vista 3D sigue abierta" and "F3" in detalle and tono == "info"
    assert accion[0] == "Volver a la Vista 3D"
    accion[1](); _eventos()
    assert dlg.isVisible() and not dlg.isMinimized()


def test_el_riel_marca_la_vista_3d_abierta_aunque_este_minimizada(win):
    from PySide6 import QtWidgets
    boton = win._boton_riel_vista3d()
    assert boton is not None

    def punto():
        p = boton.findChild(QtWidgets.QWidget, "puntoAbierta")
        return p is not None and p.isVisibleTo(boton)
    assert not punto()
    dlg = win.abrir_vista3d(); _esperar(dlg)
    assert punto() and "abierta" in boton.toolTip()
    dlg.showMinimized(); _eventos()
    assert punto() and "minimizada" in boton.toolTip()
    dlg.close(); _eventos()
    assert not punto() and boton.toolTip() == "Vista 3D"


def test_la_vista_3d_lleva_boton_en_la_barra_de_tareas(win, monkeypatch):
    """Con DUEÑA, Windows no le da botón en la barra de tareas y minimizada «desaparecía» (2026-11-18)."""
    from ui.dialogos import vista3d_dialog as V
    assert V.estilo_con_barra(0x100) == 0x100 | V.WS_EX_APPWINDOW
    llamadas = []
    monkeypatch.setattr(V, "boton_en_barra", lambda w: llamadas.append(w) or True)
    win.winId()                                         # la principal con ventana nativa, como en pantalla
    dlg = win.abrir_vista3d(); _esperar(dlg)
    assert llamadas and llamadas[-1] is dlg


def test_reabrir_sin_cambios_no_rearma_ni_tapa_el_visor(win):
    """Cerrar y volver a abrir la 3D sin cambios: la escena ya está; la tarjeta «Preparando los datos…» quedaba
    encendida tapando el visor (no se podía mover el modelo) (reporte del usuario 2026-11-18)."""
    dlg = win.abrir_vista3d(); _esperar(dlg)
    escena = dlg.escena
    assert not dlg._cargando and dlg._firma
    dlg.close(); _eventos()
    assert win.abrir_vista3d() is dlg
    _esperar(dlg)
    assert not dlg._cargando and dlg._trabajo is None and dlg.escena is escena
