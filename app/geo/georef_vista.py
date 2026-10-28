"""2.0.0 — aspecto de «Georreferenciar» (prototipo «faltante»). Solo interfaz: el diálogo sigue con sus mismos
widgets, el mismo flujo (buscar la zona → marcar pares → ajustar y guardar) y el mismo ajuste por similaridad.

- `pasos_georref()`: los 3 pasos de siempre como tarjetas con su estado (`Pasos.actualizar`).
- `titulo_vista`, `flotar_en`: título de cada vista y sus herramientas flotando encima.
- `columna_pares`, `tarjeta_ajuste`, `tarjeta_huso`: la columna derecha (pares, ajuste y sistema de coordenadas).
"""
import math

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

# Códigos CS-MAP más usados (sugerencias del campo Huso; se puede escribir cualquiera)
HUSOS = ["CA83-IF", "CA83-IIF", "CA83-IIIF", "CA83IVF", "CA83VF", "CA83-VIF", "AZ83-CF", "AZ83-EF", "AZ83-WF",
         "NV83-EF", "NV83-CF", "NV83-WF", "TX83-CF", "TX83-NCF", "TX83-SCF"]


def _texto(t, rol=None, ajustar=False):
    lbl = QtWidgets.QLabel(t)
    if rol:
        lbl.setProperty("rol", rol)
    lbl.setWordWrap(ajustar)
    return lbl


def _tarjeta(nombre="tarjeta", margen=12, espacio=6):
    f = QtWidgets.QFrame()
    f.setObjectName(nombre)
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(margen, margen, margen, margen)
    lay.setSpacing(espacio)
    return f, lay


class Pasos(QtWidgets.QWidget):
    """«1 Buscar la zona · 2 Marcar pares · 3 Ajustar y guardar», cada uno con su estado."""

    def __init__(self):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._tarjetas = []
        for i, titulo in enumerate((_tr("Buscar la zona"), _tr("Marcar pares"), _tr("Ajustar y guardar"))):
            f, fl = _tarjeta("tarjetaSuave", 10, 2)
            fila = QtWidgets.QHBoxLayout()
            fila.setSpacing(6)
            ic = QtWidgets.QLabel()
            fila.addWidget(ic)
            fila.addWidget(_texto(f"{i + 1}  {titulo}", "h3"))
            fila.addStretch(1)
            fl.addLayout(fila)
            det = _texto("—", "t3")
            fl.addWidget(det)
            lay.addWidget(f, 1)
            self._tarjetas.append((f, ic, det))
        self.actualizar()

    def actualizar(self, zona="", pares=0, rms=None):
        hechos = [bool(zona), pares >= 3, rms is not None]
        detalles = [zona or _tr("Escribe una dirección y descarga las calles"),
                    (_tr("{n} pares · mínimo 3").format(n=pares) if pares >= 3 else
                     _tr("{n} de 3 pares como mínimo").format(n=pares)),
                    (_tr("Error medio {e} ft").format(e=f"{rms:.2f}") if rms is not None else
                     _tr("Pulsa «Ajustar» con 3 pares o más"))]
        actual = hechos.index(False) if False in hechos else -1
        t = _theme.tokens()
        for i, (f, ic, det) in enumerate(self._tarjetas):
            ok = hechos[i]
            ic.setPixmap(_icon("mdi:check-circle-outline" if ok else "mdi:circle-outline",
                               color=t.success if ok else (t.accent if i == actual else t.text3)).pixmap(16, 16))
            det.setText(detalles[i])
            f.setStyleSheet(f"QFrame#tarjetaSuave {{ border:1px solid {t.accent}; }}" if i == actual else "")


def pasos_georref():
    return Pasos()


def titulo_vista(titulo, detalle):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 4)
    lay.setSpacing(6)
    lay.addWidget(_texto(titulo, "h3"))
    lay.addWidget(_texto("· " + detalle, "t3"))
    lay.addStretch(1)
    return w


def flotar_en(vista, widgets, donde="abajo"):
    """Los widgets de siempre en una pastilla flotando sobre la vista (como en el asistente)."""
    from ui.asistente.wizard_widgets import flotar, pastilla
    p = pastilla(widgets)
    flotar(vista, p, donde)
    return p


def tarjeta_ajuste(lbl_rms, lbl_ajuste, b_fit):
    f, lay = _tarjeta()
    cab = QtWidgets.QHBoxLayout()
    cab.addWidget(_texto(_tr("Ajuste"), "h3"))
    cab.addStretch(1)
    cab.addWidget(lbl_rms)
    lay.addLayout(cab)
    lay.addWidget(lbl_ajuste)
    lay.addWidget(b_fit)
    return f


def detalle_ajuste(matrix, pares, errores=None):
    """Texto «Giro · Escala · Par con más error» de una similaridad (solo para mostrar)."""
    a, b = matrix[0][0], matrix[1][0]
    escala = math.hypot(a, b)
    giro = math.degrees(math.atan2(b, a))
    txt = _tr("Giro {g}° · Escala {e}").format(g=f"{giro:.3f}", e=f"{escala:.5f}")
    if errores:
        k = max(range(len(errores)), key=lambda i: errores[i])
        txt += "\n" + _tr("Par con más error: {n} · {e} ft").format(n=k + 1, e=f"{errores[k]:.2f}")
    return txt


def tarjeta_huso(ed_cs_code):
    f, lay = _tarjeta()
    lay.addWidget(_texto(_tr("Sistema de coordenadas (Huso)"), "h3"))
    comp = QtWidgets.QCompleter(HUSOS, ed_cs_code)
    comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
    ed_cs_code.setCompleter(comp)
    lay.addWidget(ed_cs_code)
    lay.addWidget(_texto(_tr("Código CS-MAP (EPSG:2229 = CA83VF). Se aplica al dibujo de Civil 3D al importar."),
                         "t3", True))
    return f


def columna_pares(lst, b_del, b_clear, ajuste, huso):
    w = QtWidgets.QWidget()
    w.setFixedWidth(380)
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    lay.addWidget(_texto(_tr("Pares de puntos"), "h3"))
    lay.addWidget(lst, 1)
    fila = QtWidgets.QHBoxLayout()
    fila.addWidget(b_del)
    fila.addWidget(b_clear)
    fila.addStretch(1)
    lay.addLayout(fila)
    lay.addWidget(ajuste)
    lay.addWidget(huso)
    return w
