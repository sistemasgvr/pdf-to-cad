"""Centro de avisos: UN componente por ventana para todo lo que aparece abajo a la derecha.

Pedido del usuario 2026-11-18 (el aviso breve ⚠ y la tarjeta «Interpretando la hoja…» caían en el mismo lugar y
una tapaba a la otra): «un sistema de avisos… cada vez que el sistema necesite mandar un aviso o un estado de carga,
que lo llame, y ahí esté la lógica de que no se tapen, no se desborden».

Las tarjetas siguen siendo las de siempre; NINGUNA se ubica sola: se registran aquí (`centro(host).agregar(w, tipo)`)
y `colocar()` las pone. CARGAS: `tarjeta_avance.TarjetaAvance`, `progreso_reconocimiento.ProgresoReconocimiento` y
`cambio_tema.AvisoCambioTema` (estas dos son ventanitas propias: se ubican en coordenadas de pantalla); AVISOS:
`aviso_breve.AvisoBreve`. La tarjeta de «Cargando…» (`busy.BusyOverlay`) la dibuja su capa: el centro le RESERVA el
lugar de más abajo (es la que bloquea) y avisa con `recolocar(host)` cuando cambia.

  · sobre el área VISIBLE del plano, abajo a la derecha (sin sus barras de desplazamiento, nunca encima de los
    paneles desplegados; sin plano, abajo a la derecha de la ventana, sobre su barra de estado);
  · apiladas sin taparse, separadas por `SEPARACION`: abajo «Cargando…», luego las CARGAS (duran) y encima los
    AVISOS (se van solos); dentro de cada grupo, la más antigua abajo;
  · sin desbordar: si no caben en el alto disponible se cierran los avisos más viejos; como mucho `MAX_AVISOS` a la
    vez (uno nuevo igual a otro que se ve lo reemplaza).

Se recoloca al cambiar el tamaño de la ventana, al llegar o irse una tarjeta y cuando una cambia de alto.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6 import QtCore, QtWidgets

MARGEN = 14              # como «Cargando…» y la tarjeta del reconocimiento
SEPARACION = 8
MAX_AVISOS = 3
CARGA, AVISO = "carga", "aviso"
_ATRIBUTO = "_pdfcad_centro_avisos"


def _viva(w) -> bool:
    try:
        import shiboken6
        return shiboken6.isValid(w)
    except Exception:
        return True


class CentroAvisos(QtCore.QObject):
    def __init__(self, host: QtWidgets.QWidget):
        super().__init__(host)
        self.host = host
        self._tarjetas: List[tuple] = []          # (widget, tipo, clave) en orden de llegada
        self._pendiente = False
        host.installEventFilter(self)

    # ── registro ─────────────────────────────────────────────────────────
    def agregar(self, w: QtWidgets.QWidget, tipo: str = AVISO, clave: Optional[str] = None):
        """Una tarjeta nueva. `clave` (avisos): otra con la misma clave se cierra (no se repiten)."""
        self._limpiar()
        if tipo == AVISO:
            for x, t, c in list(self._tarjetas):
                if t == AVISO and clave is not None and c == clave:
                    self._cerrar(x)
            avisos = [x for x, t, _c in self._tarjetas if t == AVISO]
            for x in avisos[:max(0, len(avisos) - (MAX_AVISOS - 1))]:
                self._cerrar(x)
        if not any(x is w for x, _t, _c in self._tarjetas):
            self._tarjetas.append((w, tipo, clave))
            w.installEventFilter(self)
        self.colocar()

    def quitar(self, w):
        self._tarjetas = [(x, t, c) for x, t, c in self._tarjetas if x is not w and _viva(x)]
        self.colocar()

    def tarjetas(self, tipo: Optional[str] = None) -> list:
        """Las tarjetas a la vista (de un tipo o todas), de abajo hacia arriba."""
        self._limpiar()
        orden = [x for x, t, _c in self._tarjetas if t == CARGA] + [x for x, t, _c in self._tarjetas if t == AVISO]
        return [x for x in orden if (tipo is None or self._tipo(x) == tipo) and x.isVisible()]

    def _tipo(self, w):
        return next((t for x, t, _c in self._tarjetas if x is w), None)

    def _limpiar(self):
        self._tarjetas = [(x, t, c) for x, t, c in self._tarjetas if _viva(x)]

    def _cerrar(self, w):
        self._tarjetas = [(x, t, c) for x, t, c in self._tarjetas if x is not w]
        try:
            cerrar = getattr(w, "cerrar", None)
            cerrar() if callable(cerrar) else w.hide()
        except RuntimeError:
            pass

    # ── dónde ────────────────────────────────────────────────────────────
    def caja(self) -> QtCore.QRect:
        """El rectángulo libre (coords del host): el plano sin lo que tapan los paneles desplegados, o la ventana
        sin su barra de estado."""
        h = self.host
        cv = getattr(h, "canvas", None)
        vp = cv.viewport() if isinstance(cv, QtWidgets.QAbstractScrollArea) else cv
        if isinstance(vp, QtWidgets.QWidget) and vp.isVisible():
            try:
                caja = QtCore.QRect(vp.mapTo(h, QtCore.QPoint(0, 0)), vp.size())
                tapado = getattr(h, "_inicio_tapado", None)
                izq, der = tapado() if callable(tapado) else (0, 0)
                caja = caja.adjusted(izq, 0, -der, 0)
                ancho = max((x.width() for x, _t, _c in self._tarjetas if _viva(x)), default=0)
                if caja.width() >= ancho + 2 * MARGEN:
                    return caja
            except RuntimeError:
                pass
        caja = QtCore.QRect(0, 0, h.width(), h.height())
        sb = h.statusBar() if isinstance(h, QtWidgets.QMainWindow) else None
        if sb is not None and sb.isVisible():
            caja.setBottom(caja.bottom() - sb.height())
        return caja

    def _reservado(self) -> int:
        """Alto de la tarjeta de «Cargando…» de esta ventana (0 si no hay): va abajo de todo."""
        try:
            from ui.comun.busy import BusyOverlay
            ov = self.host.findChild(BusyOverlay, "", QtCore.Qt.FindDirectChildrenOnly)
            if ov is not None and ov.active:
                return int(round(ov.alto_tarjeta())) + SEPARACION
        except (RuntimeError, ImportError, AttributeError):
            pass
        return 0

    def _franja_barra(self, caja: QtCore.QRect) -> int:
        """La barra de herramientas del plano (ventanita centrada abajo, `ventana_flotantes`) se corre a la
        izquierda de las tarjetas; si en el ancho del plano no caben las dos, las tarjetas van ENCIMA de su franja."""
        barra = getattr(self.host, "_flot_barra_win", None)
        try:
            if barra is None or not barra.isVisible():
                return 0
            ancho = max((w.width() for w in self.tarjetas()), default=0)
            if not ancho or caja.width() >= ancho + barra.width() + 3 * MARGEN:
                return 0
            return barra.height() + MARGEN
        except RuntimeError:
            return 0

    def colocar(self):
        self._limpiar()
        caja = self.caja()
        caja.setBottom(caja.bottom() - self._reservado())
        caja.setBottom(caja.bottom() - self._franja_barra(caja))
        while True:
            visibles = self.tarjetas()
            for w in visibles:
                w.adjustSize()
            alto = sum(w.height() for w in visibles) + SEPARACION * max(0, len(visibles) - 1)
            avisos = [w for w in visibles if self._tipo(w) == AVISO]
            if alto <= caja.height() - 2 * MARGEN or not avisos:
                break
            self._cerrar(avisos[0])                    # no caben: se va el aviso más viejo
        y = caja.bottom() + 1 - MARGEN
        for w in visibles:
            y -= w.height()
            x = caja.right() + 1 - MARGEN - w.width()
            p = QtCore.QPoint(max(caja.left(), x), max(caja.top(), y))
            w.move(self.host.mapToGlobal(p) if w.isWindow() else p)
            w.raise_()
            y -= SEPARACION
        self._al_colocar()

    def _al_colocar(self):
        """La barra de herramientas del plano se corre a la izquierda de las tarjetas (`ventana_flotantes`). Solo si
        las tarjetas cambiaron de lugar: la tarjeta de carga se recoloca a menudo y mover lo flotante sobre el plano
        (el minimapa) le rompe la caché de desplazamiento."""
        lugar = tuple((w.x(), w.y(), w.width(), w.height()) for w in self.tarjetas())
        if lugar == getattr(self, "_lugar", None):
            return
        self._lugar = lugar
        if getattr(self.host, "barra_plano", None) is not None:
            try:
                from ui.ventana import ventana_flotantes
                ventana_flotantes.colocar(self.host)
            except Exception:
                pass

    def eventFilter(self, obj, ev):
        host = getattr(self, "host", None)
        if host is None:                               # (se está borrando: Qt aún reparte eventos)
            return False
        t = ev.type()
        if obj is host and t in (QtCore.QEvent.Resize, QtCore.QEvent.Move):
            self.colocar()
        elif obj is not host and t in (QtCore.QEvent.Show, QtCore.QEvent.Hide):
            self._programar()
        elif obj is not host and t == QtCore.QEvent.LayoutRequest:
            try:
                if obj.sizeHint().height() != obj.height():   # cambió de alto (texto nuevo)
                    self._programar()
            except RuntimeError:
                pass
        return False

    def _programar(self):
        if not self._pendiente:
            self._pendiente = True
            QtCore.QTimer.singleShot(0, self, self._colocar_pendiente)

    def _colocar_pendiente(self):
        self._pendiente = False
        self.colocar()


def centro(host) -> CentroAvisos:
    c = getattr(host, _ATRIBUTO, None)
    if c is None or not _viva(c):
        c = CentroAvisos(host)
        setattr(host, _ATRIBUTO, c)
    return c


def recolocar(host):
    """Algo que el centro no registra cambió (la tarjeta de «Cargando…»): recoloca, si la ventana ya tiene centro."""
    c = getattr(host, _ATRIBUTO, None)
    if c is not None and _viva(c):
        c._programar()
