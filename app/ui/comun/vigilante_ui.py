"""vigilante_ui.py — la parte Qt del vigilante (`nucleo/vigilante.py`): el LATIDO de la ventana y los pasos medidos.

`iniciar(app, win)` (solo desde `app_window.main`, nunca en las pruebas):
  · crea la sesión de registro de la ventana (los procesos hijos escriben en la misma carpeta);
  · un QTimer late cada `LATIDO_MS` en el hilo de la interfaz y una `Guardia` (otro hilo) anota cada vez que la
    ventana pasa más de `UMBRAL_CONGELA_S` sin latir, con el perfil de lo que estaba corriendo;
  · envuelve con `medir` pasos internos de la ventana (`PASOS`) para tener su tiempo con nombre. Se envuelven
    DESPUÉS de construir la ventana (las señales ya conectadas siguen con el método de siempre) y solo métodos
    internos que se llaman directo: un envoltorio con `*args` conectado a una señal con argumentos recibiría
    argumentos de más.
"""
from __future__ import annotations

import threading

from PySide6 import QtCore

from nucleo import vigilante as V

PASOS = (
    # editor
    "_redraw", "_refresh_lists", "_rebuild_structures", "_restore", "_push", "_draw_pipe_conflicts",
    "_draw_accesorios", "_calcular_cruces", "_calcular_accesorios", "_perfil_al_dia",
    # abrir / guardar / hojas
    "open_path", "_open_project_path", "_write_project", "_load_page", "_change_page", "_reset_model",
    "_apply_composite", "_fondo_de", "_mostrar_plano", "_aplicar_capas",
    # reconocimiento e importación
    "_interpretar_hoja", "_import_recognized_pipes", "_importar_datos", "_guardar_valvulas",
    "_combinar_hojas", "_poner_hoja_combinada", "_georef_automatica",
    # exportar
    "_pipeline_done",
)

_estado = {}


def iniciar(app, win) -> bool:
    if not V.activar("ventana", nueva_sesion=True):
        return False
    g = V.Guardia(threading.main_thread().ident).iniciar()
    timer = QtCore.QTimer(app)
    timer.setTimerType(QtCore.Qt.PreciseTimer)
    timer.setInterval(V.LATIDO_MS)
    timer.timeout.connect(g.latido)
    timer.start()
    hechos = V.instrumentar(type(win), PASOS, prefijo="Ventana.")
    V.evento("pasos_medidos", pasos=hechos)

    def fin():
        V.evento("fin", congelamientos=g.congelamientos, peor_s=round(g.peor_s, 3))
        g.parar()
    app.aboutToQuit.connect(fin)
    _estado.update(guardia=g, timer=timer)
    return True


def guardia():
    return _estado.get("guardia")
