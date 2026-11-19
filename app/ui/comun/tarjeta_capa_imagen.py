"""Tarjeta «¿de qué red es?» de una capa de red en IMAGEN dudosa (plan 2026-11-18 «Ejes de la red en imagen»,
Tarea 8; spec §7.6).

`certeza_capas` decide por cada capa de línea de imagen si es SEGURO asignarla sola; si no, el panel «Reconocer»
muestra una tarjeta por capa sin respuesta: la muestra de su color, «Hay líneas en la imagen de la hoja que no sé de
qué red son», el porqué en UNA frase (`porque`), y debajo los botones: las utilidades candidatas primero, «Otra…»
(menú con las demás; «Elegir la red…» si no hay candidatas) y «No es una red», más ⌖ (ver sus ejes).
Diseño (memoria «tarjetas»): el texto arriba a todo el ancho y los botones en fila debajo; solo tokens del tema (el
único color propio es la muestra de la capa).

`CajaDudosas` = la columna de tarjetas del panel (`PanelReconocer.poner_dudosas`). Elegir emite
`elegida(capa, utilidad | None)`; ⌖ emite `ubicar(capa)`.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from nucleo import reconocer_estado as RE
from traduccion.i18n import bind as _bind, t as _tr
from traduccion.i18n_core import N_
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon
from ui.comun.responsive import GridAdaptable

# de dónde salió una utilidad (las claves de `certeza_capas`), en minúscula: van detrás de «Asignada por:»
PISTAS = {"nombre": N_("nombre del PDF"), "leyenda": N_("leyenda"), "texto": N_("texto del plano"),
          "rotulos": N_("rótulos"), "trayectoria": N_("trayectoria de la red"), "respuesta": N_("tu respuesta")}
# la misma, como sujeto de la frase del porqué
_FUENTE = {"nombre": N_("El nombre del PDF"), "leyenda": N_("La leyenda"), "texto": N_("El texto del plano")}


def _util(u) -> str:
    return _tr(RE.ETIQUETAS.get(u, u)) if u else ""


def candidatas(c) -> list:
    """Las utilidades que alguna pista nombra: la de más peso primero, luego las que la contradicen."""
    from reconocimiento import recognition as rec
    out = [c.utilidad] if c.utilidad else []
    for e in c.en_contra or ():
        if e.startswith("contradice:"):
            u = e.split(":", 1)[1]
            if u not in out:
                out.append(u)
    return [u for u in out if u in rec.SUPPORTED_UTILITIES]


def pistas_texto(claves) -> str:
    """«nombre del PDF, rótulos» (solo las pistas conocidas, sin repetir)."""
    return ", ".join(_tr(PISTAS[k]) for k in dict.fromkeys(claves or ()) if k in PISTAS)


def porque(c) -> str:
    """Por qué la capa `c` (`certeza_capas.CapaCerteza`) no se asignó sola, en UNA frase."""
    contra = list(c.en_contra or ())
    fuente = next((k for k in c.a_favor or () if k in _FUENTE), None)
    dice = c.utilidad and fuente
    otras = [u for u in candidatas(c) if u != c.utilidad]
    if otras and c.utilidad:
        if dice:
            return _tr("{fuente} dice {u}, pero otras pistas dicen {x}.").format(
                fuente=_tr(_FUENTE[fuente]), u=_util(c.utilidad), x=", ".join(_util(u) for u in otras))
        return _tr("Las pistas no coinciden: unas dicen {u} y otras {x}.").format(
            u=_util(c.utilidad), x=", ".join(_util(u) for u in otras))
    if "varios_colores" in contra:
        if dice:
            return _tr("{fuente} dice {u}, pero hay varios colores de línea en la hoja.").format(
                fuente=_tr(_FUENTE[fuente]), u=_util(c.utilidad))
        return _tr("Hay varios colores de línea en la hoja y nada dice cuál es la red.")
    if "fino" in contra:
        return _tr("Es la línea fina de ese color y no tiene rótulos de tubería propios.")
    if "acromatico" in contra:
        return _tr("Es negra o gris y ni la leyenda ni los rótulos dicen que sea una red.")
    if "sin_evidencia" in contra:
        return _tr("Ni el nombre del PDF, ni la leyenda, ni el texto del plano dicen de qué red es.")
    return _tr("No hay pistas suficientes para saber de qué red es.")


def nombre_capa(capa) -> str:
    from hoja import pdf_styles
    try:
        return pdf_styles.style_label(capa)
    except Exception:                                     # noqa: BLE001 — un nombre raro nunca tumba el panel
        return str(capa)


def color_capa(capa) -> str:
    from hoja import imagen_ejes as IE
    rgb = IE.rgb_de(capa) or (128, 128, 128)
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


class TarjetaCapaImagen(QtWidgets.QFrame):
    elegida = QtCore.Signal(str, object)          # (capa, utilidad | None = «No es una red»)
    ubicar = QtCore.Signal(str)                   # ⌖: ver sus ejes

    def __init__(self, certeza, parent=None):
        super().__init__(parent)
        self.certeza, self.capa = certeza, certeza.capa
        self.setObjectName("tarjeta")                  # fondo y borde de la hoja de estilo global (tokens)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)
        cab = QtWidgets.QHBoxLayout()
        cab.setSpacing(8)
        self.muestra = QtWidgets.QLabel()              # el color de la capa (su propio color, no uno de estado)
        self.muestra.setFixedSize(14, 14)
        cab.addWidget(self.muestra, 0, QtCore.Qt.AlignTop)
        self.lbl_titulo = QtWidgets.QLabel()
        _bind(self.lbl_titulo, "setText", "Hay líneas en la imagen de la hoja que no sé de qué red son")
        self.lbl_titulo.setWordWrap(True)
        self.lbl_titulo.setProperty("rol", "h3")
        cab.addWidget(self.lbl_titulo, 1)
        self.btn_ubicar = QtWidgets.QToolButton()
        self.btn_ubicar.setFixedSize(28, 28)
        self.btn_ubicar.setIconSize(QtCore.QSize(18, 18))
        self.btn_ubicar.setCursor(QtCore.Qt.PointingHandCursor)
        _bind(self.btn_ubicar, "setToolTip", "Ver sus líneas en la hoja")
        _bind(self.btn_ubicar, "setAccessibleName", "Ver sus líneas en la hoja")
        self.btn_ubicar.clicked.connect(lambda: self.ubicar.emit(self.capa))
        cab.addWidget(self.btn_ubicar, 0, QtCore.Qt.AlignTop)
        lay.addLayout(cab)
        self.lbl_capa = QtWidgets.QLabel(nombre_capa(self.capa))
        self.lbl_capa.setProperty("rol", "t3")
        self.lbl_capa.setWordWrap(True)
        lay.addWidget(self.lbl_capa)
        self.lbl_porque = QtWidgets.QLabel(porque(certeza))
        self.lbl_porque.setProperty("rol", "t2")
        self.lbl_porque.setWordWrap(True)
        lay.addWidget(self.lbl_porque)
        caja = QtWidgets.QWidget()
        caja.setObjectName("sinFondo")
        caja.setStyleSheet("QWidget#sinFondo { background: transparent; }")
        grid = GridAdaptable(caja, max_cols=3)          # una fila si caben; si no, uno debajo del otro
        self.botones = []
        cands = candidatas(certeza)
        for u in cands:
            b = self._boton(_util(u), "soft")
            b.clicked.connect(lambda _=False, x=u: self.elegida.emit(self.capa, x))
        otra = self._boton(_tr("Otra…") if cands else _tr("Elegir la red…"), "options")
        menu = QtWidgets.QMenu(otra)
        from reconocimiento import recognition as rec
        for u in rec.SUPPORTED_UTILITIES:
            if u in cands:
                continue
            a = menu.addAction(_util(u))
            a.setData(u)
            a.triggered.connect(lambda _=False, x=u: self.elegida.emit(self.capa, x))
        otra.setMenu(menu)
        no = self._boton(_tr("No es una red"), None)
        no.clicked.connect(lambda: self.elegida.emit(self.capa, None))
        for b in self.botones:
            grid.addWidget(b)
        lay.addWidget(caja)
        self.setAccessibleName(self.lbl_titulo.text())
        _theme.al_tema(self, lambda _n: self._estilo())
        self._estilo()

    def _boton(self, texto, prop):
        b = QtWidgets.QPushButton(texto)
        b.setMinimumHeight(32)
        if prop:
            b.setProperty(prop, True)
        b.setCursor(QtCore.Qt.PointingHandCursor)
        self.botones.append(b)
        return b

    def _estilo(self):
        t = _theme.tokens()
        self.muestra.setStyleSheet(f"background:{color_capa(self.capa)}; border-radius:3px;"
                                   f" border:1px solid {t.border};")
        self.btn_ubicar.setIcon(_icon("mdi:crosshairs-gps", color=t.text_muted))
        self.btn_ubicar.setStyleSheet("QToolButton { border:none; background:transparent; border-radius:8px; }"
                                      f" QToolButton:hover {{ background:{t.surface_alt}; }}")


class CajaDudosas(QtWidgets.QWidget):
    """Columna de tarjetas, una por capa dudosa sin respuesta (el panel la llena con `poner`)."""
    elegida = QtCore.Signal(str, object)
    ubicar = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sinFondo")
        self.setStyleSheet("QWidget#sinFondo { background: transparent; }")
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._viejas = []                     # las quitadas: se borran después (una puede estar emitiendo)
        self._capas = []

    def poner(self, capas):
        capas = list(capas or ())
        nuevas = [c.capa for c in capas]
        if nuevas == self._capas and all(c == w.certeza for c, w in zip(capas, self.tarjetas())):
            return
        self._capas = nuevas
        viejas = self.tarjetas()
        for w in viejas:
            self._lay.removeWidget(w)
            w.hide()
            w.setParent(None)                 # fuera de findChildren ya; Qt la borra después
            w.deleteLater()
        self._viejas = viejas
        for c in capas:
            w = TarjetaCapaImagen(c, self)
            w.elegida.connect(self.elegida.emit)
            w.ubicar.connect(self.ubicar.emit)
            self._lay.addWidget(w)
        self.setVisible(bool(capas))

    def tarjetas(self) -> list:
        return [self._lay.itemAt(i).widget() for i in range(self._lay.count())
                if isinstance(self._lay.itemAt(i).widget(), TarjetaCapaImagen)]
