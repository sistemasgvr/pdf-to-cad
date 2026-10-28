"""2.0.0 — Paleta de comandos (Ctrl+K o «Buscar o ejecutar…» de la barra superior).

Lista TODAS las acciones de la app (las de los menús de antes, `win._acc`, y las de la barra: tabla, 3D,
asistente, agregar utilidad, zoom), agrupadas como estaban; escribir filtra y Enter / clic ejecuta la acción
(el MISMO QAction: mismo método y atajo). También va a una utilidad por su nombre o número.
"""
import unicodedata

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import theme as _theme
from ui.comun import rediseno as R
from traduccion.i18n import t as _tr


def _norm(s):
    s = unicodedata.normalize("NFD", s or "").lower()
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("&", "").replace("…", "")


class PaletaComandos(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win, QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog)
        self.win = win
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedWidth(600)
        ext = QtWidgets.QVBoxLayout(self)
        ext.setContentsMargins(20, 20, 20, 20)
        caja = QtWidgets.QFrame()
        caja.setObjectName("flotante")
        sombra = QtWidgets.QGraphicsDropShadowEffect(caja)
        sombra.setBlurRadius(40)
        sombra.setOffset(0, 12)
        sombra.setColor(QtGui.QColor(0, 0, 0, 70))
        caja.setGraphicsEffect(sombra)
        ext.addWidget(caja)
        lay = QtWidgets.QVBoxLayout(caja)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.campo = R.CampoBuscar("Buscar una acción, una utilidad o un conflicto…", "Esc")
        self.campo.setMinimumHeight(40)
        self.campo.textChanged.connect(self._filtrar)
        self.campo.installEventFilter(self)
        lay.addWidget(self.campo)
        self.lista = QtWidgets.QListWidget()
        self.lista.setFixedHeight(440)
        self.lista.setStyleSheet("QListWidget { background: transparent; border: none; }")
        self.lista.itemActivated.connect(self._ejecutar)
        self.lista.itemClicked.connect(self._ejecutar)
        lay.addWidget(self.lista)
        self._entradas = self._armar()
        self._filtrar("")
        g = win.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 70)
        self.campo.setFocus()

    def _armar(self):
        """[(grupo, texto, atajo, accion_o_fn)] con todas las acciones de la ventana."""
        w = self.win
        entradas = []
        for titulo, menu in getattr(w, "_menus", {}).items():
            for a in self._hojas(menu):
                entradas.append((_tr(titulo), a.text().replace("&", ""), a.shortcut().toString(), a))
        for a, clave in ((getattr(w, "_act_tabla", None), "Tabla de datos"),
                         (getattr(w, "_act_3d", None), "Vista 3D"),
                         (getattr(w, "_act_ia", None), "Pregúntale al proyecto…"),
                         (getattr(w, "_act_agregar", None), "Agregar utilidad desde otro PDF…"),
                         (getattr(w, "_act_zoom_in", None), "Acercar"), (getattr(w, "_act_zoom_out", None), "Alejar")):
            if a is not None and not any(e[3] is a for e in entradas):
                entradas.append((_tr("Vista"), _tr(clave), a.shortcut().toString(), a))
        vistos, unicas = set(), []
        for e in entradas:                              # una acción en dos menús, una sola vez
            if id(e[3]) not in vistos:
                vistos.add(id(e[3]))
                unicas.append(e)
        for i, p in enumerate(getattr(w, "pipes", []) or []):
            nombre = p.get("name") or ""
            unicas.append((_tr("Ir a"), f"{i + 1}. {_tr(p.get('layer', ''))} {nombre}".strip(), "",
                           lambda i=i: self._ir_a_utilidad(i)))
        for c in getattr(w, "_conflictos", None) or []:
            unicas.append((_tr("Ir a"), f"{c.id}", "", lambda c=c: w._ir_a_elemento(c.x, c.y)))
        return unicas

    def _hojas(self, menu):
        for a in R.acciones_de(menu):
            if a.text() and a.isVisible():
                yield a

    def _ir_a_utilidad(self, i):
        w = self.win
        try:
            w._show_tab(0)
            w.pipe_list.setCurrentRow(i)
        except Exception:                               # sin lista (proyecto vacío)
            pass

    def _filtrar(self, texto):
        t = _theme.tokens()
        q = _norm(texto).split()
        self.lista.clear()
        grupo = None
        for g, txt, atajo, obj in self._entradas:
            base = _norm(f"{g} {txt}")
            if q and not all(p in base for p in q):
                continue
            if g == _tr("Ir a") and not q:
                continue                                # las utilidades solo al buscar
            if g != grupo:
                grupo = g
                cab = QtWidgets.QListWidgetItem(g.upper())
                cab.setFlags(QtCore.Qt.NoItemFlags)
                f = cab.font()
                f.setPixelSize(11)
                f.setBold(True)
                cab.setFont(f)
                cab.setForeground(QtGui.QColor(t.text3))
                self.lista.addItem(cab)
            it = QtWidgets.QListWidgetItem(f"{txt}" + (f"      {atajo}" if atajo else ""))
            it.setData(QtCore.Qt.UserRole, obj)
            if isinstance(obj, QtGui.QAction) and not obj.icon().isNull():
                it.setIcon(obj.icon())
            if isinstance(obj, QtGui.QAction) and not obj.isEnabled():
                it.setFlags(QtCore.Qt.NoItemFlags)
            self.lista.addItem(it)
        for i in range(self.lista.count()):
            if self.lista.item(i).flags() & QtCore.Qt.ItemIsSelectable:
                self.lista.setCurrentRow(i)
                break

    def _ejecutar(self, it):
        obj = it.data(QtCore.Qt.UserRole) if it is not None else None
        if obj is None:
            return
        self.accept()
        QtCore.QTimer.singleShot(0, obj.trigger if isinstance(obj, QtGui.QAction) else obj)

    def eventFilter(self, o, e):                        # noqa: N802
        if o is self.campo and e.type() == QtCore.QEvent.KeyPress:
            if e.key() in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
                self._mover(1 if e.key() == QtCore.Qt.Key_Down else -1)
                return True
            if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self._ejecutar(self.lista.currentItem())
                return True
        return False

    def _mover(self, paso):
        i = self.lista.currentRow()
        for _ in range(self.lista.count()):
            i = (i + paso) % max(1, self.lista.count())
            if self.lista.item(i).flags() & QtCore.Qt.ItemIsSelectable:
                self.lista.setCurrentRow(i)
                return
