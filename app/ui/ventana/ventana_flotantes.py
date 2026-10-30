"""2.0.0 — Elementos que FLOTAN sobre el plano, como el prototipo.

    · arriba a la izquierda: «⚠ N conflictos · M avisos» (clic = Revisión);
    · abajo al centro: la barra de herramientas del plano (seleccionar, editar/mover vértices, alejar, el % de
      zoom, acercar y encuadrar todo) — las MISMAS acciones de siempre;
    · el minimapa de las hojas (si está encendido) arriba a la derecha.

El aviso y la barra van en VENTANITAS propias (sin marco, dueña la ventana principal, no toman el foco) puestas
encima del lienzo: un widget hijo encima del plano obliga a Qt a repintar la vista ENTERA en cada paso de
desplazamiento (se pierde la caché de marcas: `test_capa_marcas::test_desplazar_reusa_piezas…`); una ventana
aparte no. Se ven solo con el plano a la vista, la ventana sin minimizar y sin la capa «Cargando…».
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R

MARGEN = 14


class _Colocador(QtCore.QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, ev):
        if ev.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.Hide, QtCore.QEvent.Move,
                         QtCore.QEvent.WindowStateChange):
            colocar(self.win)
        return False


def _ventanita(win):
    w = QtWidgets.QWidget(win, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint
                          | QtCore.Qt.WindowDoesNotAcceptFocus)
    w.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    w.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    win._flot_ventanas.append(w)
    return w


def poner(win):
    cv = win.canvas
    # ── aviso de conflictos ──
    win._flot_ventanas = []
    caja_chip = _ventanita(win)
    b = QtWidgets.QPushButton(caja_chip)
    b.setObjectName("chipConflictos")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    _bind(b, "setToolTip", "Ver los conflictos y avisos en Revisión")
    b.clicked.connect(lambda: win._ir_riel(3) if hasattr(win, "_ir_riel") else None)
    caja_chip.layout().addWidget(b)
    win.chip_conflictos = b
    # ── barra de herramientas del plano ──
    caja_barra = _ventanita(win)
    barra = QtWidgets.QFrame(caja_barra)
    caja_barra.layout().addWidget(barra)
    barra.setObjectName("flotante")
    bl = QtWidgets.QHBoxLayout(barra)
    bl.setContentsMargins(6, 4, 6, 4)
    bl.setSpacing(2)
    win._flot_sel = R.boton_icono("cursor-default-outline", "Seleccionar (Esc)", lambda: win.set_mode("idle"),
                                  checkable=True)
    win._flot_mover = R.boton_icono("vector-polyline", "Editar / mover vértices", win.enter_move,
                                    checkable=True)
    for w_ in (win._flot_sel, win._flot_mover):
        bl.addWidget(w_)
    sep = QtWidgets.QFrame()
    sep.setFrameShape(QtWidgets.QFrame.VLine)
    sep.setFixedHeight(20)
    bl.addSpacing(4)
    bl.addWidget(sep)
    bl.addSpacing(4)
    bl.addWidget(R.boton_icono("magnify-minus-outline", win._act_zoom_out.toolTip() or "Alejar",
                               win._act_zoom_out.trigger))
    win._flot_zoom = QtWidgets.QLabel("100 %")
    win._flot_zoom.setProperty("rol", "t2")
    win._flot_zoom.setMinimumWidth(48)
    win._flot_zoom.setAlignment(QtCore.Qt.AlignCenter)
    bl.addWidget(win._flot_zoom)
    bl.addWidget(R.boton_icono("magnify-plus-outline", win._act_zoom_in.toolTip() or "Acercar",
                               win._act_zoom_in.trigger))
    bl.addWidget(R.boton_icono("fit-to-screen-outline", "Encuadrar todo", lambda: encuadrar(win)))
    win.barra_plano = barra
    win._flot_chip_win, win._flot_barra_win = caja_chip, caja_barra
    win._chip_hay = False
    cv.viewChanged.connect(lambda: _zoom(win))
    col = _Colocador(win)
    for obj in (cv, win):
        obj.installEventFilter(col)
    win._colocador_flotantes = col
    win._flot_timer = QtCore.QTimer(win, interval=250, timeout=lambda: colocar(win))   # paneles, capas, vistas
    win._flot_timer.start()
    _theme.THEME_BUS.changed.connect(lambda _n: estilo(win))
    estilo(win)
    refrescar(win)


def estilo(win):
    t = _theme.tokens()
    win.chip_conflictos.setStyleSheet(
        f"QPushButton#chipConflictos {{ background:{t.surface}; color:{t.text}; border:1px solid {t.border};"
        f" border-radius:8px; padding:5px 10px; }}"
        f"QPushButton#chipConflictos:hover {{ background:{t.hover}; }}")
    win.chip_conflictos.setIcon(_icon("mdi:alert-outline", color=t.warning))
    win.barra_plano.setStyleSheet(
        f"QFrame#flotante {{ background:{t.surface}; border:1px solid {t.border}; border-radius:12px; }}"
        # herramienta seleccionada: fondo del acento (el icono va en blanco: icono_conmutable)
        f"QFrame#flotante QToolButton:checked {{ background:{t.accent}; border-radius:8px; }}"
        f"QFrame#flotante QToolButton:checked:hover {{ background:{t.accent_hover}; }}")


def encuadrar(win):
    """Toda la hoja a la vista (lo mismo que al abrirla)."""
    cv = win.canvas
    if cv.pixmap_item is None:
        return
    cv.resetTransform()
    cv.fitInView(cv.sceneRect(), QtCore.Qt.KeepAspectRatio)
    cv._zoom_level = 1.0
    cv.viewChanged.emit()


def _zoom(win):
    lvl = getattr(win.canvas, "_zoom_level", 1.0) or 1.0
    win._flot_zoom.setText(f"{lvl * 100:.0f} %")


def refrescar(win, n_conf=None, n_avisos=None):
    """Hay hoja: la barra se ve; el aviso de conflictos solo si hay alguno."""
    if getattr(win, "barra_plano", None) is None:
        return
    if n_conf is not None:
        partes = []
        if n_conf:
            partes.append(_tr("{n} conflictos").format(n=n_conf) if n_conf != 1 else _tr("1 conflicto"))
        if n_avisos:
            partes.append(_tr("{n} avisos").format(n=n_avisos) if n_avisos != 1 else _tr("1 aviso"))
        win.chip_conflictos.setText("  " + " · ".join(partes))
        win._chip_hay = bool(partes)
    modo = getattr(win, "mode", "idle")
    for b, on in ((win._flot_sel, modo == "idle"), (win._flot_mover, modo == "move")):
        b.blockSignals(True)
        b.setChecked(on)
        b.blockSignals(False)
    _zoom(win)
    colocar(win)


def _a_la_vista(win):
    cv = win.canvas
    if cv.pixmap_item is None or not win.isVisible() or win.isMinimized() or not cv.isVisible():
        return False
    for ov in win.findChildren(QtWidgets.QWidget, options=QtCore.Qt.FindDirectChildrenOnly):
        if ov.__class__.__name__ == "BusyOverlay" and ov.isVisible():
            return False
    return True


def colocar(win):
    if getattr(win, "barra_plano", None) is None:
        return
    cv = win.canvas
    ver = _a_la_vista(win)
    vp = cv.viewport()
    o = vp.mapToGlobal(QtCore.QPoint(0, 0))
    W, H = vp.width(), vp.height()
    dx = 0
    panel = getattr(win, "panel_izq", None)               # el panel que se despliega encima del plano
    ov = getattr(panel, "overlay", None) if panel is not None else None
    if isinstance(ov, QtWidgets.QWidget) and ov.isVisible():
        dx = max(0, ov.mapToGlobal(QtCore.QPoint(ov.width(), 0)).x() - o.x())
    b = win._flot_barra_win
    b.adjustSize()
    bx, by = o.x() + (W - b.width()) // 2, o.y() + H - b.height() - MARGEN
    aviso = getattr(win, "_aviso_breve", None)            # el aviso breve abajo a la derecha: la barra se corre
    try:                                                   # a su izquierda si la taparía (2026-10-30)
        if aviso is not None and aviso.isVisible():
            ra = QtCore.QRect(aviso.mapToGlobal(QtCore.QPoint(0, 0)), aviso.size())
            if QtCore.QRect(bx, by, b.width(), b.height()).intersects(ra.adjusted(-MARGEN, 0, 0, 0)):
                bx = max(o.x() + dx + MARGEN, ra.left() - MARGEN - b.width())
    except RuntimeError:                                   # el aviso ya se borró
        pass
    _poner_en(b, ver, QtCore.QPoint(bx, by))
    c = win._flot_chip_win
    c.adjustSize()
    _poner_en(c, ver and win._chip_hay, QtCore.QPoint(o.x() + dx + MARGEN, o.y() + MARGEN))
    from ui.ventana import ventana_hojas
    ventana_hojas.colocar_minimapa(win)


def _poner_en(w, ver, pos):
    if not ver:
        if w.isVisible():
            w.hide()
        return
    if w.pos() != pos:
        w.move(pos)
    if not w.isVisible():
        w.show()
