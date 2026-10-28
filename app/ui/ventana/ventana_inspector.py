"""2.0.0 — Cabecera del inspector (panel derecho), como el prototipo: punto de color + nombre de lo elegido,
insignias (tipo, red, abandonada, avisos), acciones (centrar en el plano, ver en 3D, ⋯) y pestañas
Propiedades · Cotas · Datos.

Los campos de siempre NO se mueven (la lógica de guardar mira en qué grupo está cada uno: `isVisibleTo(gprop)`):
las pestañas llevan a su parte del panel (desplazan el scroll) y el menú ⋯ pulsa los botones de siempre
(Cambiar tipo, Editar/mover, Editar texto, Ver datos extendidos, Eliminar).
"""
import re

from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R

_RX = re.compile(r"^\d+\.\s*(.*?)\s*·\s*(.*)\s\(([^()]*)\)$")
PESTANAS = ["Propiedades", "Cotas", "Datos"]


class CabeceraInspector(QtWidgets.QFrame):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("cabeceraInspector")
        self.setStyleSheet("QFrame#cabeceraInspector { background: transparent; }")
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 8)
        lay.setSpacing(8)
        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(8)
        self.punto = QtWidgets.QLabel()
        fila.addWidget(self.punto)
        self.nombre = QtWidgets.QLabel()
        self.nombre.setProperty("rol", "h2")
        self.nombre.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        fila.addWidget(self.nombre, 1)
        self.btn_centrar = R.boton_icono("crosshairs-gps", "Centrar en el plano", self._centrar)
        self.btn_3d = R.boton_icono("cube-outline", "Ver en 3D", lambda: win.ver_en_3d())
        self.btn_mas = R.boton_icono("dots-horizontal", "Más acciones")
        self.btn_mas.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.btn_mas.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.menu = QtWidgets.QMenu(self.btn_mas)
        self.menu.aboutToShow.connect(self._llenar_menu)
        self.btn_mas.setMenu(self.menu)
        for b in (self.btn_centrar, self.btn_3d, self.btn_mas):
            fila.addWidget(b)
        lay.addLayout(fila)
        self.insignias = QtWidgets.QHBoxLayout()
        self.insignias.setSpacing(6)
        lay.addLayout(self.insignias)
        seg = QtWidgets.QFrame()
        seg.setObjectName("segmentado")
        sl = QtWidgets.QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.grupo = QtWidgets.QButtonGroup(seg)
        for i, clave in enumerate(PESTANAS):
            b = QtWidgets.QPushButton()
            _bind(b, "setText", clave)
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
            b.setMinimumWidth(40)
            self.grupo.addButton(b, i)
            sl.addWidget(b, 1)
        self.grupo.idClicked.connect(self._ir)
        seg.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.seg = seg
        lay.addWidget(seg)
        _theme.THEME_BUS.changed.connect(lambda _n: self.refrescar())

    # ── qué hay elegido ──
    def _elegido(self):
        """(tipo, texto de su fila) según el grupo de propiedades que está a la vista."""
        w = self.win
        for tipo, grupo in (("pipe", "gprop"), ("bz", "gprop_bz"), ("curva", "gprop_curve"), ("cl", "gprop_cl")):
            g = getattr(w, grupo, None)
            if g is not None and not g.isHidden():
                lista = w.tabs.currentWidget()
                if not isinstance(lista, QtWidgets.QListWidget):
                    lista = lista.findChild(QtWidgets.QListWidget) if lista is not None else None
                it = lista.currentItem() if lista is not None else None
                return tipo, (it.text() if it is not None else "")
        return None, ""

    def refrescar(self, desde_ui=False):
        t = _theme.tokens()
        tipo, texto = self._elegido()
        self.setVisible(bool(tipo and texto))          # nada elegido: sin cabecera
        self._botones(bool(tipo and texto), desde_ui)
        from ui.ventana import ventana_inspector_campos
        ventana_inspector_campos.refrescar(self.win)
        if not (tipo and texto):
            return
        w = self.win
        color = QtGui.QColor(t.text3)
        partes = []
        nombre = texto
        if tipo == "pipe" and 0 <= getattr(w, "sel_pipe", -1) < len(w.pipes):
            p = w.pipes[w.sel_pipe]
            color = layer_qcolor(p.get("layer"))
            m = _RX.match(texto)
            if m:
                nombre = m.group(2)
            partes.append((w._tipo(p.get("layer")), "accent"))
            if p.get("tipo"):
                partes.append((str(p.get("tipo")).capitalize(), "neutro"))
            if p.get("ab"):
                partes.append((_tr("Abandonada"), "neutro"))
            n = (getattr(w, "_avisos_por_utilidad", None) or {}).get(w.sel_pipe, 0)
            if n:
                partes.append((_tr("{n} avisos").format(n=n) if n > 1 else _tr("1 aviso"), "warn"))
        else:
            nombre = re.sub(r"^\d+\.\s*", "", texto)
        pm = QtGui.QPixmap(12, 12)
        pm.fill(QtCore.Qt.transparent)
        pinta = QtGui.QPainter(pm)
        pinta.setRenderHint(QtGui.QPainter.Antialiasing)
        pinta.setPen(QtCore.Qt.NoPen)
        pinta.setBrush(color)
        pinta.drawEllipse(0, 0, 12, 12)
        pinta.end()
        self.punto.setPixmap(pm)
        self.nombre.setText(nombre)
        self.nombre.setToolTip(texto)
        self.btn_3d.setVisible(tipo == "pipe")
        self.seg.setVisible(tipo == "pipe")
        while self.insignias.count():
            it = self.insignias.takeAt(0)
            if it.widget() is not None:
                it.widget().hide()
                it.widget().deleteLater()
        for txt, tono in partes:
            self.insignias.addWidget(_insignia(txt, tono, t))
        self.insignias.addStretch(1)

    def _botones(self, con_cabecera, desde_ui=False):
        """Con cabecera, las acciones van en su ⋯ (como el prototipo): los botones de siempre se ocultan, pero
        el menú recuerda cuáles estaban disponibles (`_disponibles`)."""
        w = self.win
        botones = (w.btn_ct, w.btn_mv, w.btn_edit, w.btn_xd, w.btn_del)
        if not con_cabecera:
            if getattr(self, "_ocultos", False) and not desde_ui:
                for b in botones:
                    b.setVisible(self._disponibles.get(b, False))
            self._ocultos = False
            return
        if desde_ui or not getattr(self, "_ocultos", False):
            self._disponibles = {b: not b.isHidden() for b in botones}
        for b in botones:
            b.setVisible(False)
        self._ocultos = True

    def _visible(self, b):
        return self._disponibles.get(b, False) if getattr(self, "_ocultos", False) else not b.isHidden()

    # ── acciones ──
    def _centrar(self):
        w = self.win
        if 0 <= getattr(w, "sel_pipe", -1) < len(w.pipes) and not w.gprop.isHidden():
            pts = w.pipes[w.sel_pipe].get("pts") or []
            if pts:
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                w.canvas.centerOn((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

    def _llenar_menu(self):
        self.menu.clear()
        w = self.win
        for b in (w.btn_ct, w.btn_mv, w.btn_edit, w.btn_xd):
            if self._visible(b) and b.isEnabled():
                self.menu.addAction(b.text().strip(), b.click)
        for clave in ("Copiar propiedades de la utilidad", "Pegar propiedades en las seleccionadas"):
            a = w._acc.get(clave)
            if a is not None and not w.gprop.isHidden():
                self.menu.addAction(a)
        self.menu.addSeparator()
        if self._visible(w.btn_del):
            self.menu.addAction(_icon("mdi:trash-can-outline", color=_theme.tokens().danger),
                                w.btn_del.text().strip(), w.btn_del.click)

    def _ir(self, i):
        """Las pestañas llevan a su parte del panel (los campos no se mueven)."""
        w = self.win
        area = w.pila_derecha.widget(0)
        destino = {0: w.gprop, 1: w.prop_inv0, 2: w.gprop}[i]
        if isinstance(area, QtWidgets.QScrollArea):
            if i == 0:
                area.verticalScrollBar().setValue(0)
            else:
                area.ensureWidgetVisible(destino, 0, 40)
        if i == 2:                                      # Datos = los datos extendidos de siempre
            self.grupo.button(0).setChecked(True)
            w.btn_xd.click()


def _insignia(txt, tono, t):
    fondo, letra = {"accent": (t.soft, t.soft_text), "warn": (t.warning_soft, t.warning)}.get(tono, (t.surface_alt,
                                                                                                    t.text_muted))
    lbl = QtWidgets.QLabel(txt)
    lbl.setStyleSheet(f"background:{fondo}; color:{letra}; border-radius:9px; padding:1px 8px; font-size:11px;"
                      f" font-weight:600;")
    lbl.setFixedHeight(20)
    return lbl


def poner_cabecera(win):
    """Encima del panel de propiedades de siempre."""
    area = win.pila_derecha.widget(0)
    contenido = area.widget() if isinstance(area, QtWidgets.QScrollArea) else area
    win.cabecera_inspector = CabeceraInspector(win)
    contenido.layout().insertWidget(0, win.cabecera_inspector)
    from ui.ventana import ventana_inspector_campos
    ventana_inspector_campos.reorganizar(win)
    win.cabecera_inspector.refrescar()
