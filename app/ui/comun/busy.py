"""busy.py — indicador «Cargando…» de la app.

Pedido del usuario (2026-09-29): en el asistente (componer hoja, capas, vista
previa…) cuando un paso tarda, que se vea que la aplicación está trabajando y
no que se quedó congelada.

`BusyOverlay` es una capa HIJA del widget que tapa (una ventana entera o solo
una vista): se come el ratón, el teclado y los atajos (y el cierre de la ventana
mientras dura) y muestra una tarjeta en la esquina inferior derecha, igual que la
del reconocimiento (`progreso_reconocimiento`, pedido del usuario 2026-11-02): el
mensaje, un detalle opcional y una barra (el avance i / n, si se conoce). Sin velo:
lo de abajo se sigue viendo tal cual. Solo se repinta el rectángulo de la tarjeta.

Dos usos:
  · trabajo en el hilo de la UI (render de fitz, armar la hoja compuesta…):
        with busy(self, _tr("Armando la hoja compuesta…")) as b:
            …
            b.step(detail=_tr("Pieza {i} de {n}").format(…), done=i, total=n)
    La capa se pinta ANTES de empezar (repaint + processEvents sin entrada del
    usuario). fitz no suelta el hilo mientras renderiza, así que la barra solo
    avanza en cada `step`; el mensaje queda a la vista todo el tiempo.
  · trabajo en otro hilo: `overlay_for(w).begin(texto)` … y `end()` al terminar;
    ahí la barra se mueve sola con el bucle de eventos.
Se puede anidar: cada `begin` apila su mensaje y `end` vuelve al anterior; la
capa desaparece con el último `end`.
"""
from __future__ import annotations

import contextlib
import threading
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import theme as _theme
from ui.comun import tiempos_carga, vigia_carga
from traduccion.i18n import t as _tr

_TICK_MS = 33              # ~30 fps de la barra sin avance conocido
_CARD_MAX_W = 340          # como la tarjeta del reconocimiento
_MARGEN = 14               # de la tarjeta a la esquina
_PAD = 12
_BAR_H = 5
_PCT_W = 44                # sitio del «100 %» a la derecha de la barra
_BTN_H = 26
ANCLA_PIE = "piePasos"     # pie de un paso del asistente: la tarjeta va encima (no tapa sus botones)
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
        self._caja = None              # lo último pintado de la tarjeta: al cambiar de alto, se repinta también
        self._cancel_rect = None
        self._prev_focus = None
        self._foto = None              # modo «foto» (`begin(foto=True)`): lo tapado, sin volver a dibujarlo
        self._seg = None               # la barra de 0 a 100 % de la carga en curso (`avance_aprendido.Seguidor`)
        self._mil = -1                 # lo último pintado de la barra, en milésimas
        self.latido = 0.0              # cuándo se pintó la tarjeta por última vez (`vigia_carga`)
        self._bombeando = False
        self._nivel = 0                # bucles de eventos anidados al empezar la carga
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

    def begin(self, text: str, detail: str = "", cancel=None, cursor: bool = True, foto: bool = False,
              modelo: bool = False, **_kw):
        """Muestra (o apila) un mensaje y pinta la capa en el acto. `cancel` = función:
        la tarjeta lleva «Cancelar» (trabajo en otro proceso, que se puede cortar).
        `cursor=False`: sin el reloj de arena en TODA la aplicación (la capa tapa solo su
        widget y lo demás sigue usable, p. ej. la Vista 3D armándose en otro hilo).
        `foto=True` (barras que avanzan seguido, 2026-10-20): al empezar se toma UNA imagen de lo tapado y se
        pinta esa; si no, cada repintado de la capa (semitransparente) volvía a dibujar debajo el plano entero
        (~0.09 s con 16 761 utilidades). Solo para trabajo que no cambia lo de abajo mientras dura.
        La barra va SIEMPRE de 0 a 100 % (pedido 2026-11-16): con `modelo=True` la pone quien llama con
        `step(done=, total=)` (`barra_pesada`, costos medidos); si no, se reparte sola con lo que duró cada etapa
        la vez anterior y el «i de n» de cada aviso (`nucleo/avance_aprendido`)."""
        self._stack.append({"text": text, "detail": detail, "done": None, "total": None,
                            "cancel": cancel, "modelo": bool(modelo)})
        if len(self._stack) == 1:
            self._seg = None if modelo else tiempos_carga.seguidor(text)
            self._mil = -1
            self._nivel = self._nivel_de_bucles()
            self.latido = time.perf_counter()
            vigia_carga.vigilar(self)
            self.setGeometry(self._host.rect())
            if foto and self._host.isVisible():
                self._foto = self._host.grab()
                self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
            self.show()
            if self._host.isVisible():
                # el foco a la capa: así el teclado y los atajos no llegan a lo de abajo
                # (en una ventana aún sin mostrar no se toca: sería su foco inicial)
                self._prev_focus = QtWidgets.QApplication.focusWidget()
                self.setFocus(QtCore.Qt.OtherFocusReason)
            self._timer.start()
            self._cursor_global = cursor
            if cursor:
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        if len(self._stack) > 1 and self._seg is not None:
            self._seg.etapa(text + (" · " + detail if detail else ""))
        self.raise_()                 # por si se agregaron hijos al host después
        self._avisar_centro()
        self.pump()

    def _avisar_centro(self):
        """Los avisos y cargas del rincón (`centro_avisos`) van ENCIMA de esta tarjeta: si cambió de alto (o
        apareció / se fue), se recolocan."""
        alto = self.alto_tarjeta() if self._stack else 0.0
        if abs(alto - getattr(self, "_alto_avisado", 0.0)) > 0.5:
            self._alto_avisado = alto
            from ui.comun import centro_avisos
            centro_avisos.recolocar(self._host)

    def step(self, text: str | None = None, detail: str | None = None,
             done: int | None = None, total: int | None = None, pump: bool = True, clave: str | None = None,
             estimado: bool | None = None):
        """Cambia el mensaje / avance del nivel actual y repinta. `pump=False`
        cuando el trabajo va en otro hilo (el bucle de eventos ya repinta; un
        processEvents aquí adentro podría entregar el «terminado» a mitad).
        `estimado=True` (barra con `modelo`, `barra_pesada`): la etapa de ahora no tiene cuenta y la barra la
        estima; la cifra lo dice («≈ 42 %», `medida`)."""
        if not self._stack:
            return
        top = self._stack[-1]
        if text is not None:
            top["text"] = text
        if detail is not None:
            top["detail"] = detail
        if total is not None:
            top["done"], top["total"] = done or 0, total
        if estimado is not None:
            top["estimado"] = bool(estimado)
        if self._seg is not None and (text is not None or detail is not None or total is not None):
            # una etapa de la carga: su texto (sin números) la reconoce; `clave` = la misma etapa aunque el
            # texto cambie (p. ej. el nombre de cada capa)
            self._seg.etapa(top["text"] + (" · " + top["detail"] if top["detail"] else ""),
                            done if total else None, total, clave=clave)
        if text is not None or detail is not None:
            self._avisar_centro()
        if pump:
            self._angle = (self._angle + 40.0) % 360.0
            self.pump()
        else:
            self.update(self._region())

    def end(self):
        if not self._stack:
            return
        self._stack.pop()
        if self._stack:
            if self._seg is not None:
                top = self._stack[-1]
                self._seg.etapa(top["text"] + (" · " + top["detail"] if top["detail"] else ""))
            self._avisar_centro()
            self.pump()
            return
        seg, self._seg = self._seg, None
        if seg is not None:
            tiempos_carga.guardar(seg)        # lo que duró cada etapa: la barra de la próxima vez
        self._timer.stop()
        self._caja = None
        self.hide()
        self._avisar_centro()
        if self._foto is not None:
            self._foto = None
            self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, False)
        if getattr(self, "_cursor_global", True):
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
        if not self.isVisible() or self._bombeando:
            return
        self._bombeando = True
        try:
            self.repaint(self._region())
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        finally:
            self._bombeando = False

    def _nivel_de_bucles(self) -> int:
        try:
            return int(self.thread().loopLevel())
        except (AttributeError, RuntimeError):
            return 0

    def fraccion(self) -> float:
        """Cuánto va la carga, de 0 a 1 (lo que marca la barra)."""
        if not self._stack:
            return 0.0
        if self._seg is not None:
            return self._seg.fraccion()
        top = self._stack[-1]
        if top["total"]:
            return max(0.0, min(1.0, float(top["done"]) / float(top["total"])))
        return 0.0

    def medida(self) -> str:
        """Cómo se mide la cifra: "cuenta" (real) o una estimación ("perfil"/"tiempo"; `avance_aprendido`)."""
        if not self._stack:
            return "tiempo"
        if self._seg is not None:
            return self._seg.medida()
        top = self._stack[-1]
        return "cuenta" if top["total"] and not top.get("estimado") else "tiempo"

    def _tick(self):
        self._angle = (self._angle + 12.0) % 360.0
        if self._stack and int(self.fraccion() * 1000) != self._mil:      # la barra avanzó
            self.update(self._region())

    # ── el vigía: pintar la tarjeta aunque el trabajo no avise ───────────
    def vigilada(self) -> bool:
        return bool(self._stack)

    def pintar_desde_el_vigia(self):
        """Lo llama `vigia_carga` en el hilo de la ventana, entre dos instrucciones de un trabajo que lleva un
        rato sin avisar. SOLO pinta la tarjeta (sin atender eventos), y solo si la ventana no está ya pintando,
        bombeando ni dentro de otro bucle de eventos (ahí la tarjeta se pinta sola)."""
        if not self._stack or self._bombeando or not self.isVisible():
            return
        if time.perf_counter() - self.latido < vigia_carga.QUIETA_S:
            return
        if threading.current_thread() is not threading.main_thread() or self._nivel_de_bucles() != self._nivel:
            return
        if self.testAttribute(QtCore.Qt.WA_WState_InPaintEvent) or vigia_carga.pintando_en_la_pila():
            return
        self._bombeando = True
        try:
            self.repaint(self._region())
        finally:
            self._bombeando = False
            self.latido = time.perf_counter()

    # ── eventos: tapar el host y bloquear la entrada ─────────────────────
    def eventFilter(self, obj, ev):
        if obj is getattr(self, "_host", None):       # (al cerrar Python el objeto ya no tiene atributos)
            et = ev.type()
            if et == QtCore.QEvent.Resize:
                self.setGeometry(self._host.rect())
            elif et == QtCore.QEvent.Close and self._stack:
                ev.ignore()           # no cerrar la ventana a mitad de un trabajo
                return True
            elif et == QtCore.QEvent.ChildAdded and self._stack:
                QtCore.QTimer.singleShot(0, self, self._raise_if_active)
        return False

    def _raise_if_active(self):
        if self._stack:
            self.raise_()

    def event(self, ev):
        if (self._stack and ev.type() == QtCore.QEvent.MouseButtonRelease
                and self._stack[-1].get("cancel") is not None and self._cancel_rect is not None
                and self._cancel_rect.contains(QtCore.QPointF(ev.position()))):
            fn = self._stack[-1]["cancel"]
            self._stack[-1]["cancel"] = None          # un clic basta
            self._stack[-1]["detail"] = _tr("Cancelando…")
            self.update(self._region())
            QtCore.QTimer.singleShot(0, self, fn)
            ev.accept()
            return True
        if self._stack and ev.type() in _INPUT_EVENTS:
            ev.accept()               # también ShortcutOverride: así no salta ningún atajo
            return True
        return super().event(ev)

    # ── dibujo ──────────────────────────────────────────────────────────
    def _zona(self) -> QtCore.QRectF:
        """Dónde se apoya la tarjeta: en la ventana principal, el lienzo (como la del reconocimiento);
        en un paso del asistente, encima de su pie; si no, todo el widget tapado."""
        zona = QtCore.QRectF(self.rect())
        canvas = getattr(self._host, "canvas", None)
        vp = canvas.viewport() if canvas is not None else None
        if vp is not None and vp.isVisible():
            esquina = vp.mapTo(self._host, QtCore.QPoint(0, 0))
            return QtCore.QRectF(esquina.x(), esquina.y(), vp.width(), vp.height()).intersected(zona)
        pie = self._host.findChild(QtWidgets.QWidget, ANCLA_PIE)
        if pie is not None and pie.isVisible():
            zona.setBottom(pie.mapTo(self._host, QtCore.QPoint(0, 0)).y())
        return zona

    def _fuentes(self):
        titulo = QtGui.QFont(self.font())
        titulo.setBold(True)
        return titulo, _resized(self.font(), -1)

    def _geometria(self):
        """(tarjeta, título, detalle, barra, botón o None) de lo que está arriba de la pila."""
        top = self._stack[-1]
        zona = self._zona()
        w = min(_CARD_MAX_W, max(140.0, zona.width() - 2 * _MARGEN))
        ancho = int(w - 2 * _PAD)
        f_titulo, f_detalle = self._fuentes()
        alto_t = QtGui.QFontMetrics(f_titulo).boundingRect(
            QtCore.QRect(0, 0, ancho, 1000), QtCore.Qt.TextWordWrap, top["text"]).height()
        alto_d = (QtGui.QFontMetrics(f_detalle).boundingRect(
            QtCore.QRect(0, 0, ancho, 1000), QtCore.Qt.TextWordWrap, top["detail"]).height() if top["detail"] else 0)
        boton = top.get("cancel") is not None
        h = (_PAD + alto_t + (4 + alto_d if alto_d else 0) + 10 + _BAR_H + 2 + (8 + _BTN_H if boton else 0) + _PAD)
        card = QtCore.QRectF(zona.right() - _MARGEN - w, zona.bottom() - _MARGEN - h, w, h)
        x, y = card.left() + _PAD, card.top() + _PAD
        r_titulo = QtCore.QRectF(x, y, ancho, alto_t)
        r_detalle = QtCore.QRectF(x, y + alto_t + 4, ancho, alto_d)
        y += alto_t + (4 + alto_d if alto_d else 0) + 10
        r_barra = QtCore.QRectF(x, y, ancho - _PCT_W, _BAR_H)
        r_boton = None
        if boton:
            bw = QtGui.QFontMetrics(self.font()).horizontalAdvance(_tr("Cancelar")) + 24
            r_boton = QtCore.QRectF(card.right() - _PAD - bw, r_barra.bottom() + 8, bw, _BTN_H)
        return card, r_titulo, r_detalle, r_barra, r_boton

    def alto_tarjeta(self) -> float:
        """El alto de la tarjeta a la vista (el centro de avisos apila las demás encima)."""
        return self._geometria()[0].height() if self._stack else 0.0

    def _region(self) -> QtGui.QRegion:
        """Lo que hay que repintar: la tarjeta de ahora y la de antes. Con toda la capa, cada repintado volvía a
        dibujar debajo el lienzo entero."""
        if not self._stack:
            return QtGui.QRegion(self.rect())
        caja = self._geometria()[0].adjusted(-5, -5, 5, 6).toAlignedRect()
        region = QtGui.QRegion(caja)
        if self._caja is not None:
            region = region.united(QtGui.QRegion(self._caja))
        self._caja = caja
        return region

    def paintEvent(self, _ev):
        if not self._stack:
            return
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if self._foto is not None:
            p.drawPixmap(self.rect(), self._foto)

        top = self._stack[-1]
        card, r_titulo, r_detalle, bar, r_boton = self._geometria()
        for i, alpha in enumerate((28, 18, 10)):          # sombra suave
            p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(0, 0, 0, alpha))
            p.drawRoundedRect(card.adjusted(-i - 1, -i + 1, i + 1, i + 3), 10, 10)
        p.setBrush(QtGui.QColor(t.surface))
        p.setPen(QtGui.QPen(QtGui.QColor(t.border), 1))
        p.drawRoundedRect(card, 8, 8)

        f_titulo, f_detalle = self._fuentes()
        p.setPen(QtGui.QColor(t.text)); p.setFont(f_titulo)
        p.drawText(r_titulo, QtCore.Qt.TextWordWrap, top["text"])
        if top["detail"]:
            p.setPen(QtGui.QColor(t.text_muted)); p.setFont(f_detalle)
            p.drawText(r_detalle, QtCore.Qt.TextWordWrap, top["detail"])

        # la barra: siempre de 0 a 100 %, con su cifra al lado
        frac = self.fraccion()
        self._mil = int(frac * 1000)
        self.latido = time.perf_counter()
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(t.border_soft)); p.drawRoundedRect(bar, 2.5, 2.5)
        p.setBrush(QtGui.QColor(t.accent))
        if frac > 0:
            p.drawRoundedRect(QtCore.QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * frac),
                                            bar.height()), 2.5, 2.5)
        p.setPen(QtGui.QColor(t.text_muted)); p.setFont(f_detalle)
        p.drawText(QtCore.QRectF(bar.right(), bar.center().y() - 9, _PCT_W, 18),
                   QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, cifra(frac, self.medida()))

        self._cancel_rect = r_boton
        if r_boton is not None:                           # «Cancelar», abajo: el texto va a todo el ancho
            p.setPen(QtGui.QPen(QtGui.QColor(t.border), 1))
            p.setBrush(QtGui.QColor(t.window))
            p.drawRoundedRect(r_boton, 6, 6)
            p.setPen(QtGui.QColor(t.text)); p.setFont(self.font())
            p.drawText(r_boton, QtCore.Qt.AlignCenter, _tr("Cancelar"))
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
        with escuchar_en(ov):
            yield ov
    finally:
        ov.end()


def cifra(frac: float, medida: str) -> str:
    """«42 %» si lo mide una cuenta real; «≈ 42 %» si es una estimación (`avance_aprendido.Seguidor.medida`)."""
    p = int(max(0.0, min(1.0, frac)) * 100)
    return _tr("{p} %").format(p=p) if medida == "cuenta" else _tr("≈ {p} %").format(p=p)


def detalle_de(texto: str, i=None, n=None) -> str:
    """Texto de una etapa (`nucleo.avance`) con su «i de n»."""
    return _tr("{texto} ({i} de {n})").format(texto=texto, i=i, n=n) if i and n and n > 1 else texto


def escuchar_en(ov):
    """Los avisos de etapa (`nucleo.avance`) de este hilo van al detalle de la capa `ov`
    (pedido del usuario 2026-10-14: ver QUÉ se está cargando, no solo «Cargando…»)."""
    from nucleo import avance
    return avance.escuchar(lambda t, i, n: ov.step(detail=detalle_de(t, i, n),
                                                   done=i if n else None, total=n if n else None))


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
