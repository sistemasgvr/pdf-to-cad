"""busy.py — indicador «Cargando…» de la app.

Pedido del usuario (2026-09-29): en el asistente (componer hoja, capas, vista
previa…) cuando un paso tarda, que se vea que la aplicación está trabajando y
no que se quedó congelada.

`BusyOverlay` es una capa HIJA del widget que tapa (una ventana entera o solo
una vista): atenúa lo de abajo, se come el ratón, el teclado y los atajos (y el
cierre de la ventana mientras dura) y muestra una tarjeta con un indicador
giratorio, el mensaje, un detalle opcional y, si se conoce, el avance (i / n).

Dos usos:
  · trabajo en el hilo de la UI (render de fitz, armar la hoja compuesta…):
        with busy(self, _tr("Armando la hoja compuesta…")) as b:
            …
            b.step(detail=_tr("Pieza {i} de {n}").format(…), done=i, total=n)
    La capa se pinta ANTES de empezar (repaint + processEvents sin entrada del
    usuario). fitz no suelta el hilo mientras renderiza, así que el indicador
    solo avanza en cada `step`; el mensaje queda a la vista todo el tiempo.
  · trabajo en otro hilo (reconocimiento): `overlay_for(w).begin(texto)` … y
    `end()` al terminar; ahí el indicador gira solo con el bucle de eventos.
Se puede anidar: cada `begin` apila su mensaje y `end` vuelve al anterior; la
capa desaparece con el último `end`.
"""
from __future__ import annotations

import contextlib
import math

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import theme as _theme

_TICK_MS = 33              # ~30 fps del indicador
_CARD_MAX_W = 440
_SPINNER = 30              # diámetro del indicador (px)
_INPUT_EVENTS = {
    QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease,
    QtCore.QEvent.MouseButtonDblClick, QtCore.QEvent.MouseMove, QtCore.QEvent.Wheel,
    QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease, QtCore.QEvent.ShortcutOverride,
    QtCore.QEvent.ContextMenu,
}


def _resized(font: QtGui.QFont, delta_px: int) -> QtGui.QFont:
    """Copia de `font` con `delta_px` píxeles más (o menos). El tema de la app pone
    la fuente en PÍXELES (`font-size: …px`), así que `pointSizeF()` vale −1: sumarle
    puntos dejaba el título en 0.5 pt (se veía como una rayita, reporte del usuario)."""
    f = QtGui.QFont(font)
    px = f.pixelSize()
    if px <= 0:
        px = QtGui.QFontInfo(font).pixelSize() or 13
    f.setPixelSize(max(9, px + delta_px))
    return f


class BusyOverlay(QtWidgets.QWidget):
    """Capa «Cargando…» sobre `host` (la cubre entera y sigue su tamaño)."""

    def __init__(self, host: QtWidgets.QWidget):
        super().__init__(host)
        self._host = host
        self._stack: list[dict] = []
        self._angle = 0.0
        self._prev_focus = None
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMouseTracking(True)
        self.hide()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        host.installEventFilter(self)

    # ── estado ──────────────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        return bool(self._stack)

    def text(self) -> str:
        return self._stack[-1]["text"] if self._stack else ""

    def detail(self) -> str:
        return self._stack[-1]["detail"] if self._stack else ""

    def begin(self, text: str, detail: str = ""):
        """Muestra (o apila) un mensaje y pinta la capa en el acto."""
        self._stack.append({"text": text, "detail": detail, "done": None, "total": None})
        if len(self._stack) == 1:
            self.setGeometry(self._host.rect())
            self.show()
            if self._host.isVisible():
                # el foco a la capa: así el teclado y los atajos no llegan a lo de abajo
                # (en una ventana aún sin mostrar no se toca: sería su foco inicial)
                self._prev_focus = QtWidgets.QApplication.focusWidget()
                self.setFocus(QtCore.Qt.OtherFocusReason)
            self._timer.start()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.raise_()                 # por si se agregaron hijos al host después
        self.pump()

    def step(self, text: str | None = None, detail: str | None = None,
             done: int | None = None, total: int | None = None, pump: bool = True):
        """Cambia el mensaje / avance del nivel actual y repinta. `pump=False`
        cuando el trabajo va en otro hilo (el bucle de eventos ya repinta; un
        processEvents aquí adentro podría entregar el «terminado» a mitad)."""
        if not self._stack:
            return
        top = self._stack[-1]
        if text is not None:
            top["text"] = text
        if detail is not None:
            top["detail"] = detail
        if total is not None:
            top["done"], top["total"] = done or 0, total
        if pump:
            self._angle = (self._angle + 40.0) % 360.0
            self.pump()
        else:
            self.update()

    def end(self):
        if not self._stack:
            return
        self._stack.pop()
        if self._stack:
            self.pump()
            return
        self._timer.stop()
        self.hide()
        QtWidgets.QApplication.restoreOverrideCursor()
        prev, self._prev_focus = self._prev_focus, None
        try:
            if prev is not None and prev.isVisible():
                prev.setFocus(QtCore.Qt.OtherFocusReason)
        except RuntimeError:          # el widget ya no existe
            pass

    def pump(self):
        """Pinta ya (se usa entre pasos de un trabajo que bloquea la UI). La
        entrada del usuario queda en cola: no puede lanzar otra cosa a medias."""
        if not self.isVisible():
            return
        self.repaint()
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)

    def _tick(self):
        self._angle = (self._angle + 12.0) % 360.0
        self.update()

    # ── eventos: tapar el host y bloquear la entrada ─────────────────────
    def eventFilter(self, obj, ev):
        if obj is self._host:
            et = ev.type()
            if et == QtCore.QEvent.Resize:
                self.setGeometry(self._host.rect())
            elif et == QtCore.QEvent.Close and self._stack:
                ev.ignore()           # no cerrar la ventana a mitad de un trabajo
                return True
            elif et == QtCore.QEvent.ChildAdded and self._stack:
                QtCore.QTimer.singleShot(0, self._raise_if_active)
        return False

    def _raise_if_active(self):
        if self._stack:
            self.raise_()

    def event(self, ev):
        if self._stack and ev.type() in _INPUT_EVENTS:
            ev.accept()               # también ShortcutOverride: así no salta ningún atajo
            return True
        return super().event(ev)

    # ── dibujo ──────────────────────────────────────────────────────────
    def paintEvent(self, _ev):
        if not self._stack:
            return
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        veil = QtGui.QColor(t.window)
        veil.setAlpha(165)
        p.fillRect(self.rect(), veil)

        top = self._stack[-1]
        has_bar = bool(top["total"])
        w = min(_CARD_MAX_W, max(160, self.width() - 32))
        pad = 16
        text_w = w - pad * 3 - _SPINNER
        f_title = _resized(self.font(), +3); f_title.setBold(True)
        f_detail = _resized(self.font(), -1)
        fl = QtGui.QFontMetrics(f_title).boundingRect(
            QtCore.QRect(0, 0, text_w, 1000), QtCore.Qt.TextWordWrap, top["text"])
        dl = (QtGui.QFontMetrics(f_detail).boundingRect(
            QtCore.QRect(0, 0, text_w, 1000), QtCore.Qt.TextWordWrap, top["detail"])
            if top["detail"] else QtCore.QRect())
        text_h = fl.height() + (dl.height() + 4 if top["detail"] else 0)
        h = max(_SPINNER, text_h) + pad * 2 + (14 if has_bar else 0)
        card = QtCore.QRectF((self.width() - w) / 2.0, (self.height() - h) / 2.0, w, h)

        for i, alpha in enumerate((28, 18, 10)):          # sombra suave
            shadow = QtGui.QColor(0, 0, 0, alpha)
            p.setPen(QtCore.Qt.NoPen); p.setBrush(shadow)
            p.drawRoundedRect(card.adjusted(-i - 1, -i + 1, i + 1, i + 3), 12, 12)
        p.setBrush(QtGui.QColor(t.surface))
        p.setPen(QtGui.QPen(QtGui.QColor(t.border), 1))
        p.drawRoundedRect(card, 10, 10)

        # indicador: aro tenue + arco del color de acento que gira
        body_h = max(_SPINNER, text_h)
        sp = QtCore.QRectF(card.left() + pad, card.top() + pad + (body_h - _SPINNER) / 2.0,
                           _SPINNER, _SPINNER).adjusted(2, 2, -2, -2)
        pen = QtGui.QPen(QtGui.QColor(t.border_soft), 4); pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen); p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(sp)
        pen.setColor(QtGui.QColor(t.accent)); p.setPen(pen)
        span = 100 + 60 * math.sin(math.radians(self._angle * 2))
        p.drawArc(sp, int(-self._angle * 16), int(span * 16))

        # textos
        x = card.left() + pad * 2 + _SPINNER
        y = card.top() + pad + (body_h - text_h) / 2.0
        p.setPen(QtGui.QColor(t.text)); p.setFont(f_title)
        p.drawText(QtCore.QRectF(x, y, text_w, fl.height()), QtCore.Qt.TextWordWrap, top["text"])
        if top["detail"]:
            p.setPen(QtGui.QColor(t.text_muted)); p.setFont(f_detail)
            p.drawText(QtCore.QRectF(x, y + fl.height() + 4, text_w, dl.height()),
                       QtCore.Qt.TextWordWrap, top["detail"])

        if has_bar:                                        # avance conocido: barra fina
            frac = max(0.0, min(1.0, float(top["done"]) / float(top["total"])))
            bar = QtCore.QRectF(card.left() + pad, card.bottom() - pad - 4, w - 2 * pad, 5)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(t.border_soft)); p.drawRoundedRect(bar, 2.5, 2.5)
            if frac > 0:
                p.setBrush(QtGui.QColor(t.accent))
                p.drawRoundedRect(QtCore.QRectF(bar.left(), bar.top(), bar.width() * frac, bar.height()),
                                  2.5, 2.5)
        p.end()


def overlay_for(host: QtWidgets.QWidget) -> BusyOverlay:
    """La capa de `host` (se crea la primera vez y se reutiliza)."""
    ov = host.findChild(BusyOverlay, "", QtCore.Qt.FindDirectChildrenOnly)
    return ov if ov is not None else BusyOverlay(host)


class _NoOverlay:
    """Sustituto sin UI cuando no hay a quién tapar (p. ej. parent=None en tests)."""
    active = False

    def step(self, *a, **k):
        pass

    def pump(self):
        pass


@contextlib.contextmanager
def busy(host, text: str, detail: str = ""):
    """`with busy(widget, texto):` — capa «Cargando…» mientras dura el bloque."""
    if not isinstance(host, QtWidgets.QWidget):
        yield _NoOverlay()
        return
    ov = overlay_for(host)
    ov.begin(text, detail)
    try:
        yield ov
    finally:
        ov.end()


class Toast(QtWidgets.QLabel):
    """Aviso breve de confirmación («✔ Proyecto guardado») centrado sobre `host`;
    desaparece solo. No bloquea nada ni se come el ratón."""

    def __init__(self, host: QtWidgets.QWidget):
        super().__init__(host)
        self.setObjectName("appToast")
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._timer = QtCore.QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_text(self, text: str, ms: int = 2000):
        t = _theme.tokens()
        self.setStyleSheet(f"#appToast {{ background:{t.success}; color:{t.text_on_accent};"
                           "font-size:16px; font-weight:700; padding:14px 28px;"
                           "border-radius:10px; }")
        self.setText(text)
        self.adjustSize()
        host = self.parentWidget()
        self.move((host.width() - self.width()) // 2, (host.height() - self.height()) // 2)
        self.show(); self.raise_()
        self._timer.start(ms)


def toast(host: QtWidgets.QWidget, text: str, ms: int = 2000):
    """Muestra `text` unos `ms` sobre `host` (reutiliza el mismo aviso)."""
    tw = host.findChild(Toast, "appToast", QtCore.Qt.FindDirectChildrenOnly)
    (tw or Toast(host)).show_text(text, ms)
