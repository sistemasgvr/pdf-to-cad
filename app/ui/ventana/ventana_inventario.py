"""2.0.0 — Panel «Inventario» del riel (como el prototipo).

Las 8 listas de siempre (`win.tabs`, con su desplegable `win.tab_combo`) con: buscador, filtros de utilidades
(Todas · Con avisos · Abandonadas), filas de DOS líneas con el punto de color de la utilidad y un aviso si tiene
avisos de normativa, y abajo los botones para varias a la vez. NO cambia ningún ítem: la fila N sigue siendo la
utilidad N (mismo texto, mismos índices); el delegado solo cambia cómo se DIBUJA y el filtro solo OCULTA filas.
"""
import re

from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R

FILTROS = ["Todas", "Con avisos", "Abandonadas"]
_RX = re.compile(r"^(\d+)\.\s*(.*?)\s*·\s*(.*)\s\(([^()]*)\)$")


class DelegadoUtilidad(QtWidgets.QStyledItemDelegate):
    """«12. Agua (AB) · AGUA-12 (4 vért.)» → punto de color · AGUA-12 / Agua · AB · 4 vért. · #12."""

    def __init__(self, win, lista):
        super().__init__(lista)
        self.win = win

    def sizeHint(self, option, index):                 # noqa: N802
        return QtCore.QSize(option.rect.width(), 46)

    def paint(self, p, option, index):
        t = _theme.tokens()
        r = option.rect.adjusted(2, 1, -2, -1)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if option.state & QtWidgets.QStyle.State_Selected:
            fondo = QtGui.QColor(t.soft)
        elif option.state & QtWidgets.QStyle.State_MouseOver:
            fondo = QtGui.QColor(t.hover)
        else:
            fondo = None
        if fondo is not None:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(fondo)
            p.drawRoundedRect(QtCore.QRectF(r), 8, 8)
        texto = index.data(QtCore.Qt.DisplayRole) or ""
        m = _RX.match(texto)
        num, tipo, nombre, info = (m.groups() if m else ("", "", texto, ""))
        fila = index.row()
        pipes = getattr(self.win, "pipes", [])
        capa = pipes[fila].get("layer") if 0 <= fila < len(pipes) else None
        gris = index.data(QtCore.Qt.ForegroundRole)       # apagada en «Capas»: en gris, como antes
        color = QtGui.QColor(t.text3) if gris is not None else (layer_qcolor(capa) if capa else QtGui.QColor(t.text3))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QtCore.QPointF(r.left() + 14, r.center().y()), 5, 5)
        x = r.left() + 30
        derecha = r.right() - 8
        if fila in getattr(self.win, "_utilidades_con_avisos", set()):
            ic = _icon("mdi:alert-outline", color=t.warning).pixmap(16, 16)
            p.drawPixmap(derecha - 16, r.center().y() - 8, ic)
            derecha -= 22
        f = QtGui.QFont(option.font)
        f.setWeight(QtGui.QFont.DemiBold)
        p.setFont(f)
        p.setPen(QtGui.QColor(t.text3 if gris is not None else t.text))
        arriba = QtCore.QRectF(x, r.top() + 5, derecha - x, r.height() / 2 - 3)
        p.drawText(arriba, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   QtGui.QFontMetrics(f).elidedText(nombre, QtCore.Qt.ElideRight, int(arriba.width())))
        f2 = QtGui.QFont(option.font)
        f2.setPixelSize(12)
        p.setFont(f2)
        p.setPen(QtGui.QColor(t.text3))
        detalle = " · ".join(x for x in (tipo, info, f"#{num}" if num else "") if x)
        abajo = QtCore.QRectF(x, r.center().y() + 1, derecha - x, r.height() / 2 - 4)
        p.drawText(abajo, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   QtGui.QFontMetrics(f2).elidedText(detalle, QtCore.Qt.ElideRight, int(abajo.width())))
        p.restore()


def panel_inventario(win):
    cont, lay = R.columna((12, 6, 12, 10), 8)
    lay.addWidget(win.tab_combo)
    win.buscar_inventario = R.CampoBuscar("Filtrar por nombre, tipo, diámetro…")
    win.buscar_inventario.textChanged.connect(lambda _t: win._filtrar_inventario())
    lay.addWidget(win.buscar_inventario)
    chips = R.transparente(QtWidgets.QWidget())
    cl = QtWidgets.QHBoxLayout(chips)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(6)
    win.filtro_inventario = QtWidgets.QButtonGroup(chips)
    for i, clave in enumerate(FILTROS):
        b = QtWidgets.QPushButton()
        _bind(b, "setText", clave)
        b.setProperty("kind", "chip")
        b.setCheckable(True)
        b.setChecked(i == 0)
        win.filtro_inventario.addButton(b, i)
        cl.addWidget(b)
    cl.addStretch(1)
    win.filtro_inventario.idClicked.connect(lambda _i: win._filtrar_inventario())
    win._chips_inventario = chips
    lay.addWidget(chips)
    win.pipe_list.setItemDelegate(DelegadoUtilidad(win, win.pipe_list))
    win.pipe_list.setMouseTracking(True)
    lay.addWidget(win.tabs, 1)
    barra = QtWidgets.QHBoxLayout()
    barra.setSpacing(2)
    rotulo = R.texto("Varias utilidades", "t3", True)
    rotulo.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
    barra.addWidget(rotulo, 1)
    for icono, clave in (("merge", "Unir utilidades seleccionadas"),
                         ("pencil-box-multiple-outline", "Editar utilidades seleccionadas en bloque…"),
                         ("content-copy", "Copiar propiedades de la utilidad"),
                         ("content-paste", "Pegar propiedades en las seleccionadas")):
        a = win._acc.get(clave)
        if a is None:
            continue
        b = R.boton_icono(icono, clave, a.trigger, px=16)
        sc = R.atajo_legible(a.shortcut())
        if sc:
            b.setToolTip(f"{_tr(clave)} ({sc})")
        barra.addWidget(b)
    lay.addLayout(barra)
    win.tabs.currentChanged.connect(lambda _i: win._filtrar_inventario())
    return cont


class InventarioMixin:
    def _filtrar_inventario(self):
        """Oculta (no quita) las filas que no pasan el buscador y, en Utilidades, el filtro elegido."""
        if not hasattr(self, "buscar_inventario"):
            return
        from nucleo.model import TAB_PIPE
        en_utilidades = self.tabs.currentIndex() == TAB_PIPE
        self._chips_inventario.setVisible(en_utilidades)
        from collections import Counter
        self._avisos_por_utilidad = Counter(a.pipe for a in (getattr(self, "_normas_avisos", None) or [])
                                            if getattr(a, "pipe", None) is not None
                                            and not getattr(a, "aprobado", False))
        self._utilidades_con_avisos = set(self._avisos_por_utilidad)
        q = self.buscar_inventario.text().strip().lower()
        filtro = self.filtro_inventario.checkedId() if en_utilidades else 0
        pagina = self.tabs.currentWidget()
        lista = pagina if isinstance(pagina, QtWidgets.QListWidget) else pagina.findChild(QtWidgets.QListWidget)
        if lista is None:
            return
        for fila in range(lista.count()):
            it = lista.item(fila)
            ok = not q or q in (it.text() or "").lower()
            if ok and lista is self.pipe_list and filtro:
                p = self.pipes[fila] if fila < len(self.pipes) else {}
                ok = (fila in self._utilidades_con_avisos) if filtro == 1 else bool(p.get("ab"))
            it.setHidden(not ok)
        lista.viewport().update()
