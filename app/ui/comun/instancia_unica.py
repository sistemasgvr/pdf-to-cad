"""Una sola instancia de la app por usuario (pedido del usuario 2026-11-17: un cliente abrió dos por error,
cada una con sus procesos de trabajo y el mismo proyecto de 29 mil utilidades).

Al arrancar, `ya_abierta(ruta)` intenta hablar con la instancia que ya está abierta (QLocalSocket, canal
`nombre()`, propio del usuario de Windows): si responde, le manda la ruta del archivo que se quiso abrir
(vacía = solo traer la ventana al frente) y devuelve True → esta instancia termina sin abrir ventana.
Si no hay nadie, `escuchar(app, al_recibir)` abre el canal; `al_recibir(ruta)` corre en la ventana.
"""
from __future__ import annotations

import getpass
import hashlib
import os

from PySide6 import QtCore, QtNetwork

ESPERA_MS = 1500            # conectar / escribir a la instancia abierta
_SERVIDOR = None            # se guarda para que no lo borre el recolector


def nombre(usuario: str | None = None) -> str:
    """Canal local de la app para este usuario (dos usuarios del mismo equipo no se estorban)."""
    try:
        u = usuario if usuario is not None else getpass.getuser()
    except Exception:
        u = os.environ.get("USERNAME", "")
    return "pdfcad-instancia-" + hashlib.sha1(u.lower().encode("utf-8")).hexdigest()[:12]


def _permitir_primer_plano():
    """Windows solo deja traer una ventana al frente al proceso que tiene el foco (este, recién abierto):
    le cede ese permiso a la instancia abierta."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)        # ASFW_ANY
    except Exception:
        pass


def ya_abierta(ruta: str = "", canal: str | None = None) -> bool:
    """¿Hay otra instancia? Si la hay, le pasa `ruta` y devuelve True."""
    s = QtNetwork.QLocalSocket()
    s.connectToServer(canal or nombre())
    if not s.waitForConnected(ESPERA_MS):
        return False
    _permitir_primer_plano()
    s.write((os.path.abspath(ruta) if ruta else "").encode("utf-8") + b"\n")
    s.flush()
    s.waitForBytesWritten(ESPERA_MS)
    s.waitForReadyRead(ESPERA_MS)                # la otra confirma (o se cierra)
    s.disconnectFromServer()
    return True


def escuchar(app, al_recibir, canal: str | None = None):
    """Abre el canal de esta instancia. `al_recibir(ruta)` se llama en el hilo de la ventana."""
    global _SERVIDOR
    canal = canal or nombre()
    srv = QtNetwork.QLocalServer(app)
    srv.setSocketOptions(QtNetwork.QLocalServer.UserAccessOption)
    if not srv.listen(canal):
        QtNetwork.QLocalServer.removeServer(canal)              # canal viejo de una instancia que murió
        if not srv.listen(canal):
            return None

    def nueva():
        while srv.hasPendingConnections():
            c = srv.nextPendingConnection()
            datos = bytearray()

            def leer(c=c, datos=datos):
                datos.extend(bytes(c.readAll()))
                if b"\n" in datos:
                    ruta = bytes(datos).split(b"\n", 1)[0].decode("utf-8", "replace").strip()
                    c.write(b"ok\n")
                    c.flush()
                    c.disconnectFromServer()
                    QtCore.QTimer.singleShot(0, lambda r=ruta: al_recibir(r))

            c.readyRead.connect(leer)
            c.disconnected.connect(c.deleteLater)
            if c.bytesAvailable():
                leer()

    srv.newConnection.connect(nueva)
    _SERVIDOR = srv
    return srv


def traer_al_frente(win):
    """La ventana principal (o el diálogo que tenga abierto) al frente."""
    from PySide6 import QtWidgets
    if win.isMinimized():
        win.showMaximized()
    win.show()
    win.raise_()
    win.activateWindow()
    modal = QtWidgets.QApplication.activeModalWidget()
    if modal is not None and modal is not win:
        modal.raise_()
        modal.activateWindow()
