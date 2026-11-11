"""2.0.0 — Pantalla de inicio sobre el lienzo VACÍO (pedido del usuario 2026-11-03).

Al abrir la app sin nada cargado, el lienzo en blanco muestra las tres acciones de siempre (Nuevo lienzo,
Abrir PDF, Abrir proyecto: los MISMOS métodos de la ventana) y debajo los proyectos recientes
(`ventana_recientes.leer`, abrir = `abrir_reciente`). Es un hijo del lienzo que se ve SOLO sin hoja
(`canvas.pixmap_item is None`): con un plano cargado está oculto, así no toca la caché de desplazamiento.
Acepta arrastrar un PDF o un .digproj (= `open_path`, como el lienzo).
"""
import os

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import LANG_BUS, bind as _bind
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon
from ui.comun.rediseno import Tecla, atajo_legible, seccion, texto
from ui.ventana import ventana_recientes as _rec

MAX_FILAS = 6
ANCHO_MAX = 760
SONDEO_MS = 300


class _Tarjeta(QtWidgets.QPushButton):
    """Acción principal: icono en un cuadrito suave, título, una línea de ayuda y su atajo."""

    def __init__(self, icono, titulo_es, detalle_es, fn, atajo=""):
        super().__init__()
        self.setObjectName("tarjetaInicio")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumSize(160, 128)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._icono = icono
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(4)
        arriba = QtWidgets.QHBoxLayout()
        self.ic = QtWidgets.QLabel()
        self.ic.setFixedSize(40, 40)
        self.ic.setAlignment(QtCore.Qt.AlignCenter)
        arriba.addWidget(self.ic)
        arriba.addStretch(1)
        if atajo:
            arriba.addWidget(Tecla(atajo_legible(atajo)), 0, QtCore.Qt.AlignTop)
        lay.addLayout(arriba)
        lay.addSpacing(6)
        self.lbl = texto(titulo_es, "h3")
        self.det = texto(detalle_es, "t3", True)
        for w in (self.lbl, self.det):
            w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.lbl)
        lay.addWidget(self.det)
        lay.addStretch(1)
        _bind(self, "setAccessibleName", titulo_es)
        _bind(self, "setToolTip", detalle_es)
        self.clicked.connect(lambda: fn())
        self._estilo()
        _theme.al_tema(self, lambda _n: self._estilo())

    # QPushButton no pregunta a su layout por el tamaño: el del contenido manda
    def sizeHint(self):                                # noqa: N802
        return self.layout().sizeHint().expandedTo(self.minimumSize())

    def minimumSizeHint(self):                         # noqa: N802
        return self.layout().minimumSize().expandedTo(self.minimumSize())

    def _estilo(self):
        t = _theme.tokens()
        self.setStyleSheet(
            f"QPushButton#tarjetaInicio {{ background:{t.surface}; border:1px solid {t.border};"
            f" border-radius:12px; text-align:left; padding:0; min-height:128px; }}"
            f"QPushButton#tarjetaInicio:hover {{ border-color:{t.accent}; background:{t.hover}; }}"
            f"QPushButton#tarjetaInicio:focus {{ border:2px solid {t.focus}; }}"
            f"QPushButton#tarjetaInicio:pressed {{ background:{t.soft}; }}")
        self.ic.setStyleSheet(f"background:{t.soft}; border-radius:10px;")
        self.ic.setPixmap(_icon("mdi:" + self._icono, color=t.soft_text).pixmap(22, 22))


class _FilaReciente(QtWidgets.QPushButton):
    """Un proyecto reciente: nombre, carpeta y hace cuánto."""

    def __init__(self, d, fn):
        super().__init__()
        self.setObjectName("filaReciente")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(48)
        ruta = d["ruta"]
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(12)
        self.ic = QtWidgets.QLabel()
        lay.addWidget(self.ic)
        tx = QtWidgets.QVBoxLayout()
        tx.setSpacing(0)
        nombre = texto(os.path.splitext(os.path.basename(ruta))[0], traducir=False)
        carpeta = texto(os.path.dirname(ruta), "t3", traducir=False)
        carpeta.setMinimumWidth(1)
        carpeta.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        tx.addWidget(nombre)
        tx.addWidget(carpeta)
        lay.addLayout(tx, 1)
        cuando = texto(_rec.hace(d.get("fecha")), "t3", traducir=False)
        lay.addWidget(cuando)
        for w in (self.ic, nombre, carpeta, cuando):
            w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setToolTip(ruta)
        self.setAccessibleName(os.path.basename(ruta))
        self.clicked.connect(lambda: fn(ruta))
        self._estilo()
        _theme.al_tema(self, lambda _n: self._estilo())

    # QPushButton no pregunta a su layout por el tamaño: el del contenido manda
    def sizeHint(self):                                # noqa: N802
        return self.layout().sizeHint().expandedTo(self.minimumSize())

    def minimumSizeHint(self):                         # noqa: N802
        return self.layout().minimumSize().expandedTo(self.minimumSize())

    def _estilo(self):
        t = _theme.tokens()
        self.setStyleSheet(
            f"QPushButton#filaReciente {{ background:transparent; border:1px solid transparent;"
            f" border-radius:8px; text-align:left; padding:0; min-height:48px; }}"
            f"QPushButton#filaReciente:hover {{ background:{t.hover}; }}"
            f"QPushButton#filaReciente:focus {{ border:2px solid {t.focus}; }}")
        self.ic.setPixmap(_icon("mdi:file-document-outline", color=t.text_muted).pixmap(20, 20))


class PantallaInicio(QtWidgets.QFrame):
    def __init__(self, win, parent):
        super().__init__(parent)
        self.win = win
        self.setObjectName("pantallaInicio")
        self.setAcceptDrops(True)
        fuera = QtWidgets.QVBoxLayout(self)
        fuera.setContentsMargins(24, 24, 24, 24)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("inicioScroll")
        fuera.addWidget(scroll)
        cuerpo = QtWidgets.QWidget()
        cuerpo.setObjectName("inicioCuerpo")
        scroll.setWidget(cuerpo)
        centro = QtWidgets.QHBoxLayout(cuerpo)
        centro.setContentsMargins(0, 0, 0, 0)
        col = QtWidgets.QWidget()
        col.setObjectName("inicioColumna")
        col.setMaximumWidth(ANCHO_MAX)
        centro.addStretch(1)
        centro.addWidget(col, 100)
        centro.addStretch(1)
        lay = QtWidgets.QVBoxLayout(col)
        lay.setContentsMargins(0, 32, 0, 24)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(texto("PDF a CAD", "h1", traducir=False))
        lay.addSpacing(4)
        lay.addWidget(texto("Empieza un trabajo nuevo o continúa uno reciente.", "t2", True))
        lay.addSpacing(24)

        self.rejilla = QtWidgets.QGridLayout()
        self.rejilla.setSpacing(12)
        acc = getattr(win, "_acc", {}) or {}
        sc = acc.get("Nuevo lienzo…")
        self.tarjetas = [
            _Tarjeta("file-plus-outline", "Nuevo lienzo", "Hoja en blanco para dibujar sin PDF",
                     win.new_blank_canvas, sc.shortcut() if sc is not None else "Ctrl+N"),
            _Tarjeta("file-pdf-box", "Abrir PDF", "Plano vectorial o escaneado", win.open_pdf),
            _Tarjeta("folder-open-outline", "Abrir proyecto", "Un proyecto .digproj guardado",
                     win.open_project),
        ]
        self._columnas = 0
        self._acomodar(3)
        lay.addLayout(self.rejilla)
        lay.addSpacing(32)

        lay.addWidget(seccion("Recientes"))
        lay.addSpacing(6)
        self.lista = QtWidgets.QVBoxLayout()
        self.lista.setSpacing(2)
        lay.addLayout(self.lista)
        lay.addSpacing(20)
        self.pista = texto("También puedes arrastrar un PDF o un proyecto aquí.", "t3", True)
        lay.addWidget(self.pista)
        lay.addStretch(2)
        self._firma = None
        self._estilo()
        _theme.al_tema(self, lambda _n: self._estilo())
        LANG_BUS.changed.connect(lambda *_a: self.refrescar(forzar=True))

    ANCHO_3_COLUMNAS = 3 * 160 + 2 * 12

    def _acomodar(self, n):
        """Tres tarjetas en fila; si el lienzo es angosto, una debajo de otra."""
        if n == self._columnas:
            return
        self._columnas = n
        for tj in self.tarjetas:
            self.rejilla.removeWidget(tj)
        for i, tj in enumerate(self.tarjetas):
            self.rejilla.addWidget(tj, *((0, i) if n == 3 else (i, 0)))

    def resizeEvent(self, e):                          # noqa: N802
        super().resizeEvent(e)
        m = self.layout().contentsMargins()
        libre = self.width() - m.left() - m.right()
        self._acomodar(3 if libre >= self.ANCHO_3_COLUMNAS else 1)

    def margenes(self, tapado):
        izq, der = tapado
        m = (24 + izq, 24, 24 + der, 24)
        if self.layout().contentsMargins() != QtCore.QMargins(*m):
            self.layout().setContentsMargins(*m)
            libre = self.width() - m[0] - m[2]
            self._acomodar(3 if libre >= self.ANCHO_3_COLUMNAS else 1)

    def _estilo(self):
        t = _theme.tokens()
        self.setStyleSheet(
            f"QFrame#pantallaInicio {{ background:{t.window}; }}"
            f"QScrollArea#inicioScroll, QWidget#inicioCuerpo, QWidget#inicioColumna"
            f" {{ background:transparent; }}")

    def refrescar(self, forzar=False):
        lista = [d for d in _rec.leer() if os.path.isfile(d["ruta"])][:MAX_FILAS]
        firma = [(d["ruta"], d.get("fecha")) for d in lista]
        if firma == self._firma and not forzar:
            return
        self._firma = firma
        while self.lista.count():
            w = self.lista.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        if not lista:
            vacio = texto("Aún no hay proyectos recientes. Los que abras o guardes aparecerán aquí.", "t3", True)
            vacio.setContentsMargins(12, 8, 12, 8)
            self.lista.addWidget(vacio)
            return
        for d in lista:
            self.lista.addWidget(_FilaReciente(d, self.win.abrir_reciente))

    # arrastrar y soltar = lo mismo que sobre el lienzo
    def dragEnterEvent(self, e):                       # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):                            # noqa: N802
        for u in e.mimeData().urls():
            self.win.open_path(u.toLocalFile())
            break


class _AlCambiarTamano(QtCore.QObject):
    """La pantalla cubre el lienzo entero (sigue su tamaño)."""

    def __init__(self, pantalla):
        super().__init__(pantalla)
        self._p = pantalla

    def eventFilter(self, obj, ev):                    # noqa: N802
        if ev.type() == QtCore.QEvent.Resize:
            self._p.setGeometry(obj.rect())
        return False


class InicioMixin:
    """Muestra `PantallaInicio` sobre el lienzo mientras no hay hoja cargada."""

    def _armar_inicio(self):
        self.pantalla_inicio = PantallaInicio(self, self.canvas)
        self.pantalla_inicio.hide()
        self._inicio_filtro = _AlCambiarTamano(self.pantalla_inicio)
        self.canvas.installEventFilter(self._inicio_filtro)
        self._inicio_timer = QtCore.QTimer(self)
        self._inicio_timer.setInterval(SONDEO_MS)
        self._inicio_timer.timeout.connect(self._inicio_al_dia)
        self._inicio_timer.start()
        self._inicio_al_dia()

    def _inicio_al_dia(self):
        p = getattr(self, "pantalla_inicio", None)
        if p is None:
            return
        ver = self.canvas.pixmap_item is None
        if ver:
            p.setGeometry(self.canvas.rect())
            p.margenes(self._inicio_tapado())
            p.refrescar()
            if not p.isVisible():
                p.show()
                p.raise_()
        elif p.isVisible():
            p.hide()

    def _inicio_tapado(self):
        """Ancho (izquierda, derecha) del lienzo que tapan los paneles flotantes desplegados."""
        izq = der = 0
        caja = QtCore.QRect(self.canvas.mapTo(self, QtCore.QPoint(0, 0)), self.canvas.size())
        for nombre in ("panel_izq", "panel_der"):
            ov = getattr(getattr(self, nombre, None), "overlay", None)
            if not isinstance(ov, QtWidgets.QWidget) or not ov.isVisible():
                continue
            g = QtCore.QRect(ov.mapTo(self, QtCore.QPoint(0, 0)), ov.size()).intersected(caja)
            if g.isEmpty():
                continue
            if g.center().x() < caja.center().x():
                izq = max(izq, g.right() + 1 - caja.left())
            else:
                der = max(der, caja.right() + 1 - g.left())
        return izq, der
