"""2.0.0 — «Conexión vertical» (diseñado con el plugin design: el prototipo no lo traía).

Un cruce de dos utilidades a distinta cota: tarjeta con las dos (color, nombre, cota) y la diferencia, un
esquema chico (las dos tuberías a su altura y la vertical entre ellas: a trazos = sugerencia, continua =
aprobada) y UNA acción en color. Estados: «sugerencia» (Conectar / No conectar), «aprobado» (Quitar la
conexión / Mantener) y sin cota (solo Cerrar). Devuelve True si el usuario eligió la acción principal.
"""
from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon


class _Esquema(QtWidgets.QWidget):
    def __init__(self, ca, cb, za, zb, aprobado):
        super().__init__()
        self.ca, self.cb, self.za, self.zb, self.aprobado = ca, cb, za, zb, aprobado
        self.setFixedHeight(96)
        self.setAccessibleName(_tr("Esquema de las dos utilidades y la tubería vertical"))

    def paintEvent(self, _e):
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        arriba_a = (self.za or 0) >= (self.zb or 0)
        ya, yb = (22, h - 22) if arriba_a else (h - 22, 22)
        for y, c in ((ya, self.ca), (yb, self.cb)):
            p.setPen(QtGui.QPen(c, 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
            p.drawLine(QtCore.QPointF(24, y), QtCore.QPointF(w - 24, y))
        pen = QtGui.QPen(QtGui.QColor(t.accent), 3, QtCore.Qt.SolidLine if self.aprobado else QtCore.Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(w / 2, ya), QtCore.QPointF(w / 2, yb))
        p.setBrush(QtGui.QColor(t.accent))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(QtCore.QPointF(w / 2, (ya + yb) / 2), 5, 5)       # la válvula
        p.end()


def _fila(color, nombre, z):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    punto = QtWidgets.QLabel()
    pm = QtGui.QPixmap(12, 12)
    pm.fill(QtCore.Qt.transparent)
    pp = QtGui.QPainter(pm)
    pp.setRenderHint(QtGui.QPainter.Antialiasing)
    pp.setBrush(color); pp.setPen(QtCore.Qt.NoPen); pp.drawEllipse(0, 0, 12, 12); pp.end()
    punto.setPixmap(pm)
    lay.addWidget(punto)
    n = QtWidgets.QLabel(nombre)
    n.setProperty("rol", "h3")
    lay.addWidget(n, 1)
    c = QtWidgets.QLabel()
    c.setText("—" if z is None else _tr("{z} ft").format(z=f"{z:.2f}"))
    c.setProperty("rol", "mono")
    lay.addWidget(c)
    return w


def preguntar(parent, estado, la, lb, ca, cb, za, zb):
    """estado: «sugerencia» o «aprobado». True = conectar (sugerencia) o quitar (aprobado)."""
    t = _theme.tokens()
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(_tr("Conexión vertical"))
    dlg.setMinimumWidth(440)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.setContentsMargins(22, 18, 22, 16)
    lay.setSpacing(12)
    tit = QtWidgets.QLabel(_tr("Conexión vertical"))
    tit.setProperty("rol", "h1")
    lay.addWidget(tit)
    aprobado = estado == "aprobado"
    sin_cota = za is None or zb is None
    sub = QtWidgets.QLabel(_tr("Ya se conectan con una tubería vertical al importar.") if aprobado else
                           _tr("Se cruzan a distinta cota: una pasa por encima de la otra."))
    sub.setProperty("rol", "t2")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    tarjeta = QtWidgets.QFrame()
    tarjeta.setObjectName("tarjetaSuave")
    tl = QtWidgets.QVBoxLayout(tarjeta)
    tl.setContentsMargins(14, 12, 14, 12)
    tl.setSpacing(6)
    tl.addWidget(_fila(ca, la, za))
    tl.addWidget(_fila(cb, lb, zb))
    if not sin_cota:
        d = QtWidgets.QLabel(_tr("Diferencia: {dz} ft").format(dz=f"{abs(za - zb):.2f}"))
        d.setProperty("rol", "t3")
        tl.addWidget(d)
        tl.addWidget(_Esquema(ca, cb, za, zb, aprobado))
    lay.addWidget(tarjeta)
    if sin_cota:
        aviso = QtWidgets.QLabel(_tr("Falta la cota de al menos una de las dos: ponla para decidir si se conectan."))
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"background:{t.warning_soft}; color:{t.warning}; border-radius:8px; padding:8px;")
        lay.addWidget(aviso)
    else:
        nota = QtWidgets.QLabel(_tr("En Civil 3D se dibuja un tramo vertical con su válvula entre las dos cotas.")
                                if not aprobado else _tr("Quitarla deja las dos utilidades sin conectar."))
        nota.setProperty("rol", "t3")
        nota.setWordWrap(True)
        lay.addWidget(nota)
    fila = QtWidgets.QHBoxLayout()
    fila.addStretch(1)
    no = QtWidgets.QPushButton(_tr("Cerrar") if sin_cota else (_tr("Mantener") if aprobado else _tr("No conectar")))
    no.setProperty("kind", "ghost")
    no.clicked.connect(dlg.reject)
    fila.addWidget(no)
    if not sin_cota:
        si = QtWidgets.QPushButton(_tr("Quitar la conexión") if aprobado else _tr("Conectar en Civil 3D"))
        si.setProperty("kind", "danger" if aprobado else "primary")
        si.setIcon(_icon("mdi:trash-can-outline" if aprobado else "mdi:check", color=t.text_on_accent))
        si.setDefault(True)
        si.clicked.connect(dlg.accept)
        fila.addWidget(si)
    lay.addLayout(fila)
    return dlg.exec() == QtWidgets.QDialog.Accepted
