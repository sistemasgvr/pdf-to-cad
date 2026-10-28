"""2.0.0 — Páginas del panel del riel (Hoja y PDF, Inventario, Revisión) y la pastilla flotante del plano.

Cada fila o interruptor llama a una acción o método que YA existía (`win._acc[...]`, `win.act_*`,
`win.compose_sheet`…): nada nuevo en la lógica. «Dibujar» es el acordeón de siempre (ventana_panel_izq).
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R


def _accion(win, clave_es):
    return win._acc.get(clave_es)


def _fila(win, icono, clave_es, detalle_es="", fn=None):
    a = _accion(win, clave_es)
    if a is None and fn is None:
        return None
    return R.FilaAccion(icono, clave_es, detalle_es, accion=a if fn is None else None, fn=fn)


def _pagina(widgets):
    cont, lay = R.columna((12, 6, 12, 12), 6)
    for w in widgets:
        if w is None:
            continue
        lay.addWidget(w)
    lay.addStretch(1)
    return R.AreaVertical(cont)


# ───────────────────────── Hoja y PDF ─────────────────────────
def panel_hoja(win):
    from ui.ventana.ventana_panel_hoja import PanelHoja
    win.panel_hoja = PanelHoja(win)
    return win.panel_hoja


# Inventario: ventana_inventario.py


# ───────────────────────── Revisión ─────────────────────────
class _Cifra(QtWidgets.QFrame):
    def __init__(self, clave_es, tono):
        super().__init__()
        self.setObjectName("tarjeta")
        self.tono = tono
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(0)
        self.num = QtWidgets.QLabel("0")
        self.num.setProperty("rol", "h1")
        lay.addWidget(self.num)
        lay.addWidget(R.texto(clave_es, "t3"))

    def poner(self, n):
        t = _theme.tokens()
        self.num.setText(str(n))
        color = {"error": t.danger, "warn": t.warning}.get(self.tono, t.soft_text) if n else t.text3
        self.num.setStyleSheet(f"color:{color};")


def panel_revision(win):
    win._cifra_conf = _Cifra("Conflictos", "error")
    win._cifra_norm = _Cifra("Normativa", "warn")
    win._cifra_rec = _Cifra("Reconocimiento", "accent")
    cifras = R.transparente(QtWidgets.QWidget())
    cl = QtWidgets.QHBoxLayout(cifras)
    cl.setContentsMargins(0, 4, 0, 4)
    cl.setSpacing(6)
    for c in (win._cifra_conf, win._cifra_norm, win._cifra_rec):
        cl.addWidget(c)
    mostrar = R.transparente(QtWidgets.QWidget())
    ml = QtWidgets.QHBoxLayout(mostrar)
    ml.setContentsMargins(0, 0, 0, 0)
    for clave in ("Mostrar todos", "Ocultar todos"):
        a = _accion(win, clave)
        if a is not None:
            b = QtWidgets.QPushButton()
            _bind(b, "setText", clave)
            b.setProperty("kind", "ghost")
            b.clicked.connect(a.trigger)
            ml.addWidget(b)
    ml.addStretch(1)
    # lista de conflictos (como el prototipo): clic = ir al lugar · doble clic = resolver con el asistente
    win.lista_conflictos = QtWidgets.QListWidget()
    win.lista_conflictos.setObjectName("listaConflictos")
    win.lista_conflictos.setFixedHeight(200)
    win.lista_conflictos.setStyleSheet("QListWidget#listaConflictos { background: transparent; border: none; }")
    win.lista_conflictos.itemClicked.connect(lambda it: win._ir_a_conflicto(it, resolver=False))
    win.lista_conflictos.itemDoubleClicked.connect(lambda it: win._ir_a_conflicto(it, resolver=True))
    _bind(win.lista_conflictos, "setToolTip", "Clic: ir al lugar · doble clic: resolver con el asistente")
    win._ids_conflictos = None
    filas = [
        cifras,
        win.lista_conflictos,
        _fila(win, "auto-fix", "Resolver conflictos…", "El asistente propone y prueba soluciones"),
        _fila(win, "broom", "Revisar y limpiar el dibujo…", "Puntas sueltas, repetidas y tramos diminutos"),
        _fila(win, "file-document-outline", "Informe automático…", "Word con zonas, capturas y explicación"),
        _fila(win, "playlist-check", "Normativas de diseño…", "Reglas y aprobación de avisos"),
        R.seccion("Mostrar en el plano"),
        R.fila_interruptor("Mostrar cruces/conflictos", "", getattr(win, "chk_show_conflicts", None)),
        R.fila_interruptor("Mostrar accesorios (tipo y ángulo)", "", getattr(win, "act_show_acc", None)),
        R.fila_interruptor("Mostrar avisos de normativa", "", getattr(win, "act_show_normas", None)),
        R.fila_interruptor("Mostrar avisos de reconocimiento", "", getattr(win, "act_show_reconocimiento", None)),
        mostrar,
    ]
    return _pagina(filas)


class RevisionMixin:
    def _actualizar_revision(self, n_normativa, n_reconocimiento):
        if not hasattr(self, "_cifra_conf"):
            return
        self._cifra_conf.poner(len(getattr(self, "_conflictos", None) or []))
        self._cifra_norm.poner(n_normativa)
        self._cifra_rec.poner(n_reconocimiento)
        from ui.ventana import ventana_flotantes
        ventana_flotantes.refrescar(self, len(getattr(self, "_conflictos", None) or []), n_normativa)
        conflictos = getattr(self, "_conflictos", None) or []
        ids = [c.id for c in conflictos]
        if ids == self._ids_conflictos:
            return
        self._ids_conflictos = ids
        lista = self.lista_conflictos
        lista.clear()
        t = _theme.tokens()
        icono = _icon("mdi:alert-octagon-outline", color=t.danger)
        for c in conflictos[:300]:                     # los primeros 300; el resto, en la Tabla de datos
            it = QtWidgets.QListWidgetItem(icono, f"{c.id} · {_tr(c.titulo)}")
            it.setData(QtCore.Qt.UserRole, c.id)
            it.setToolTip(c.mensaje or _tr(c.titulo))
            lista.addItem(it)
        lista.setVisible(bool(conflictos))

    def _ir_a_conflicto(self, it, resolver=False):
        cid = it.data(QtCore.Qt.UserRole)
        c = next((c for c in getattr(self, "_conflictos", None) or [] if c.id == cid), None)
        if c is None:
            return
        if resolver:
            self.abrir_soluciones(cid)
        else:
            self._ir_a_elemento(c.x, c.y)


# ───────────────────────── zoom en la barra de estado ─────────────────────────
def pastilla_del_plano(win):
    """Alejar / acercar (antes en la barra de herramientas) junto a la escala, en la barra de estado.
    NO flotan sobre el plano: un widget encima del lienzo obliga a repintarlo entero al desplazar y se
    pierde la caché de las marcas (test_capa_marcas::test_desplazar_reusa_piezas…)."""
    caja = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(caja)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for icono, accion in (("magnify-minus-outline", win._act_zoom_out), ("magnify-plus-outline", win._act_zoom_in)):
        b = R.boton_icono(icono, accion.toolTip() or "", accion.trigger, px=16)
        lay.addWidget(b)
    win._zoom_estado = caja
    win.status.insertPermanentWidget(0, caja)
