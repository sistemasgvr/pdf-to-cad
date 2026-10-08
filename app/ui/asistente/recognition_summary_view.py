"""recognition_summary_view.py — resumen VISUAL de la vista previa del reconocimiento
(panel DERECHO).

  1. cuatro tarjetas con las cifras (tramos, abandonadas, codos, estructuras);
  2. una barra por utilidad (misma escala): activas en sólido, abandonadas (AB)
     rayadas del mismo color — el color es la utilidad, igual que en el lienzo —
     con su leyenda (activas / AB) justo debajo;
  3. «Cobertura»: la cifra, una barra fina NEUTRA (el estado lo dice el icono: una
     barra ámbar al lado de la de telecom se leía como otra utilidad) y lo que el
     control de calidad pinta sobre la hoja, solo si hay algo: sin cubrir (línea
     magenta), bóvedas sin línea (anillo magenta), fuera de patrón (turquesa a
     puntos). Ninguno es color de utilidad (`ui_common.QA_*`, 2026-10-03).
«Para verificar» y «Detalles» viven en el panel IZQUIERDO (`recognition_review_view`).
Los datos salen de `recognition_summary` (puro).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr, N_
from ui.comun.icons import icon
from nucleo.model import TIPOS
from ui.comun.ui_common import layer_qcolor, QA_UNCOVERED, QA_OFFPATTERN
from ui.comun.widgets import FlowLayout
from reconocimiento import recognition_summary as rs
from ui.comun import theme as _theme

_UTILITY_LABEL = {key: label for label, key in TIPOS}


def _needs_outline(color: QtGui.QColor) -> bool:
    """¿El color de la utilidad casi no se distingue del fondo del panel? (ACI 7
    = blanco en oscuro). Entonces la barra lleva contorno en tinta de texto."""
    bg = QtGui.QColor(_theme.tokens().surface)
    return abs(color.lightness() - bg.lightness()) < 60 or color.lightness() > 235 and bg.lightness() > 200


def utility_swatch(color: QtGui.QColor, size: int = 12) -> QtGui.QPixmap:
    """Cuadrito redondeado del color de la utilidad (con contorno si se pierde en
    el fondo, p. ej. el blanco del drenaje en el tema oscuro)."""
    dpr = 2.0
    pm = QtGui.QPixmap(int(size * dpr), int(size * dpr)); pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(QtGui.QColor(_theme.tokens().text_muted), 1) if _needs_outline(color)
             else QtCore.Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QtCore.QRectF(0.5, 0.5, size - 1, size - 1), 2.5, 2.5)
    p.end()
    return pm


class _Tile(QtWidgets.QFrame):
    """Cifra grande + etiqueta corta."""

    def __init__(self, label: str, tooltip: str = ""):
        super().__init__()
        self.setObjectName("sumTile")
        t = _theme.tokens()
        self.setStyleSheet(
            f"#sumTile {{ background:{t.surface_alt}; border:1px solid {t.border_soft}; border-radius:6px; }}")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(0)
        self.value = QtWidgets.QLabel("0")
        # el QSS global fija el tamaño de letra: la cifra grande va por QSS también
        self.value.setStyleSheet(
            f"color:{t.text}; background:transparent; border:none; font-size:20px; font-weight:bold;")
        cap = QtWidgets.QLabel(_tr(label))          # label/tooltip: claves marcadas con N_()
        cap.setStyleSheet(f"color:{t.text_muted}; background:transparent; border:none; font-size:11px;")
        lay.addWidget(self.value); lay.addWidget(cap)
        if tooltip:
            self.setToolTip(_tr(tooltip))

    def set_value(self, v: int):
        self.value.setText(str(v))


class UtilityBars(QtWidgets.QWidget):
    """Una fila por utilidad: nombre, barra (activas | AB rayadas) y cifras."""

    ROW_H = 24
    BAR_H = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stats: list[rs.UtilityStats] = []
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def set_stats(self, stats):
        self._stats = list(stats)
        self.setFixedHeight(self.ROW_H * max(1, len(self._stats)) + 2)
        self.update()

    def _geometry(self):
        fm = self.fontMetrics()
        name_w = max([fm.horizontalAdvance(_tr(_UTILITY_LABEL.get(s.utility, s.utility)))
                      for s in self._stats] + [40]) + 22
        num_w = max([fm.horizontalAdvance(self._numbers(s)) for s in self._stats] + [30]) + 10
        name_w = min(name_w, int(self.width() * 0.48))
        num_w = min(num_w, int(self.width() * 0.32))
        bar_w = max(20, self.width() - name_w - num_w)
        return name_w, bar_w, num_w

    @staticmethod
    def _numbers(s) -> str:
        return (f"{s.tramos}  ·  {s.abandonadas} AB" if s.abandonadas else f"{s.tramos}")

    def paintEvent(self, _e):
        if not self._stats:
            return
        t = _theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        name_w, bar_w, _ = self._geometry()
        vmax = max(1, max(s.tramos for s in self._stats))
        for i, s in enumerate(self._stats):
            y = i * self.ROW_H
            color = layer_qcolor(s.utility)
            # identidad: cuadrito del color de la utilidad + nombre en tinta de texto
            p.setPen(QtGui.QPen(QtGui.QColor(t.text_muted), 1) if _needs_outline(color) else QtCore.Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QtCore.QRectF(0.5, y + (self.ROW_H - 10) / 2, 10, 10), 2, 2)
            p.setPen(QtGui.QColor(t.text))
            p.drawText(QtCore.QRectF(16, y, name_w - 16, self.ROW_H), QtCore.Qt.AlignVCenter,
                       self.fontMetrics().elidedText(_tr(_UTILITY_LABEL.get(s.utility, s.utility)),
                           QtCore.Qt.ElideRight, max(1, name_w-18)))
            by = y + (self.ROW_H - self.BAR_H) / 2
            # carril tenue = escala común
            p.setPen(QtCore.Qt.NoPen); p.setBrush(QtGui.QColor(t.border_soft))
            p.drawRoundedRect(QtCore.QRectF(name_w, by + self.BAR_H / 2 - 1, bar_w, 2), 1, 1)
            w_all = bar_w * s.tramos / vmax
            w_act = w_all * s.activas / max(1, s.tramos)
            gap = 2.0 if s.activas and s.abandonadas else 0.0
            outline = QtGui.QPen(QtGui.QColor(t.text_muted), 1) if _needs_outline(color) else QtCore.Qt.NoPen
            p.setPen(outline)
            if s.activas:
                p.setBrush(color)
                p.drawRoundedRect(QtCore.QRectF(name_w, by, max(2.0, w_act - gap / 2), self.BAR_H), 3, 3)
            if s.abandonadas:
                r = QtCore.QRectF(name_w + w_act + gap / 2, by, max(3.0, w_all - w_act - gap / 2), self.BAR_H)
                tint = QtGui.QColor(color); tint.setAlpha(60)
                p.setBrush(tint); p.drawRoundedRect(r, 3, 3)
                p.setBrush(QtGui.QBrush(color, QtCore.Qt.BDiagPattern)); p.drawRoundedRect(r, 3, 3)
            p.setPen(QtGui.QColor(t.text_muted))
            p.drawText(QtCore.QRectF(name_w + w_all + 6, y, self.width(), self.ROW_H),
                       QtCore.Qt.AlignVCenter, self._numbers(s))
        p.end()

    def mouseMoveEvent(self, e):
        i = int(e.position().y() // self.ROW_H)
        if 0 <= i < len(self._stats):
            s = self._stats[i]
            tip = _tr("{u}: {n} tramos — {a} activos, {b} abandonados (AB)\n"
                      "{c} codos · {v} estructuras · cobertura {k:.1f} %").format(
                u=_tr(_UTILITY_LABEL.get(s.utility, s.utility)), n=s.tramos, a=s.activas,
                b=s.abandonadas, c=s.codos, v=s.estructuras, k=s.coverage * 100)
            QtWidgets.QToolTip.showText(e.globalPosition().toPoint(), tip, self)
        else:
            QtWidgets.QToolTip.hideText()


def _legend_swatch(color: QtGui.QColor, hatched: bool) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(18, 10); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing); p.setPen(QtCore.Qt.NoPen)
    if hatched:
        tint = QtGui.QColor(color); tint.setAlpha(60)
        p.setBrush(tint); p.drawRoundedRect(0, 0, 18, 10, 2, 2)
        p.setBrush(QtGui.QBrush(color, QtCore.Qt.BDiagPattern))
    else:
        p.setBrush(color)
    p.drawRoundedRect(0, 0, 18, 10, 2, 2); p.end()
    return pm


def qa_swatch(kind: str) -> QtGui.QPixmap:
    """Muestra de la leyenda con la MISMA forma que en la hoja: «uncovered» = línea
    gruesa magenta, «orphan» = anillo magenta, «offpattern» = puntos turquesa."""
    dpr = 2.0
    pm = QtGui.QPixmap(int(20 * dpr), int(12 * dpr)); pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing)
    if kind == "orphan":
        p.setPen(QtGui.QPen(QtGui.QColor(QA_UNCOVERED), 2.2)); p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(QtCore.QRectF(5, 1.5, 9, 9))
    elif kind == "offpattern":
        pen = QtGui.QPen(QtGui.QColor(QA_OFFPATTERN), 2.0, QtCore.Qt.CustomDashLine, QtCore.Qt.RoundCap)
        pen.setDashPattern([0.1, 2.0])
        p.setPen(pen); p.drawLine(QtCore.QPointF(2, 6), QtCore.QPointF(18, 6))
    else:
        p.setPen(QtGui.QPen(QtGui.QColor(QA_UNCOVERED), 4.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        p.drawLine(QtCore.QPointF(3, 6), QtCore.QPointF(17, 6))
    p.end()
    return pm


def _legend_item(pixmap: QtGui.QPixmap, text: str, ink: str) -> QtWidgets.QWidget:
    """Muestra de color + texto como UNA pieza de la leyenda (salta de línea entera)."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
    sw = QtWidgets.QLabel(); sw.setPixmap(pixmap)
    lb = QtWidgets.QLabel(text); lb.setStyleSheet(f"color:{ink}; font-size:12px;")
    lay.addWidget(sw); lay.addWidget(lb)
    return w


def separator() -> QtWidgets.QFrame:
    """Línea fina entre grupos del panel (en vez de títulos: menos texto)."""
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{_theme.tokens().border_soft}; border:none;")
    return line


def _coverage_block(t, cov: float, n_unc: int) -> QtWidgets.QLayout:
    """«Cobertura  99.9 %» con su icono de estado (✔ verde completa; ojo neutro si
    quedó algo para mirar —no es un error—; alerta roja por debajo del 90 %) y una
    barra fina neutra debajo."""
    qa_ok = cov >= 0.98 and n_unc == 0
    low = cov < 0.90
    col = QtWidgets.QVBoxLayout(); col.setSpacing(4)
    top = QtWidgets.QHBoxLayout(); top.setSpacing(6)
    ic = QtWidgets.QLabel()
    name, color = (("mdi:check-circle-outline", t.success) if qa_ok else
                   ("mdi:alert-outline", t.danger) if low else ("mdi:eye-outline", t.text))
    ic.setPixmap(icon(name, color=color).pixmap(16, 16))
    top.addWidget(ic, 0)
    top.addWidget(QtWidgets.QLabel(_tr("Cobertura")), 1)
    value = QtWidgets.QLabel(f"{cov * 100:.1f} %")
    value.setStyleSheet(f"color:{t.text}; font-weight:bold;")
    top.addWidget(value, 0)
    col.addLayout(top)
    bar = QtWidgets.QProgressBar()
    bar.setRange(0, 1000)
    bar.setValue(int(round(max(0.0, min(1.0, cov)) * 1000)))
    bar.setTextVisible(False)
    bar.setFixedHeight(6)
    bar.setStyleSheet(
        f"QProgressBar {{ border:none; border-radius:3px; background:{t.border_soft}; }}"
        f"QProgressBar::chunk {{ background:{t.text_muted}; border-radius:3px; }}")
    tip = _tr("Guiones del plano cubiertos por las líneas reconocidas. En el dibujo: magenta = sin "
              "cubrir, turquesa a puntos = trazos fuera de patrón (leaders/flechas).")
    for w in (bar, value):
        w.setToolTip(tip)
    col.addWidget(bar)
    return col


class SummaryPanel(QtWidgets.QWidget):
    """Resumen del reconocimiento: tarjetas + barras por utilidad (con su
    leyenda) + cobertura y lo que el control de calidad marcó en la hoja."""

    def __init__(self, results, parent=None):
        super().__init__(parent)
        self._results = list(results)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self._height_timer = QtCore.QTimer(self)
        self._height_timer.setSingleShot(True)
        self._height_timer.timeout.connect(self._sync_minimum_height)
        multi = len(self._results) > 1
        t = _theme.tokens()
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        tiles = QtWidgets.QGridLayout(); tiles.setSpacing(6)
        self.tiles_layout = tiles
        self.t_tramos = _Tile(N_("Tramos"), N_("Polilíneas que se importan al editor."))
        self.t_ab = _Tile(N_("Abandonadas"), N_("Tramos marcados (AB): capa «-A» + patrón «/», o patrón «//»."))
        self.t_codos = _Tile(N_("Codos"), N_("Esquinas con radio (curvas reales del plano)."))
        self.t_est = _Tile(N_("Estructuras"), N_("Bóvedas que quedan como nodos de las líneas."))
        self.tiles = (self.t_tramos, self.t_ab, self.t_codos, self.t_est)
        self._tile_columns = 4
        for i, w in enumerate(self.tiles):
            tiles.addWidget(w, 0, i)
            tiles.setColumnStretch(i, 1)            # tarjetas del mismo ancho
        root.addLayout(tiles)

        # barras por utilidad y, justo debajo, lo que significan (activas / AB)
        group = QtWidgets.QVBoxLayout(); group.setSpacing(4)
        self.bars = UtilityBars()
        group.addWidget(self.bars)
        legend = FlowLayout(h_spacing=14, v_spacing=4)
        base = layer_qcolor(self._results[0].utility) if not multi else QtGui.QColor(t.text_muted)
        legend.addWidget(_legend_item(_legend_swatch(base, False), _tr(N_("activas")), t.text_muted))
        legend.addWidget(_legend_item(_legend_swatch(base, True), _tr(N_("abandonadas (AB)")), t.text_muted))
        group.addLayout(legend)
        root.addLayout(group)

        root.addWidget(separator())
        # cobertura y marcas del control de calidad sobre la hoja (solo las que hay)
        cov = min(float(getattr(r, "coverage", 1.0) or 0.0) for r in self._results)
        n_unc = sum(len(getattr(r, "uncovered_px", None) or []) for r in self._results)
        n_orph = sum(len(getattr(r, "vault_orphans_px", None) or []) for r in self._results)
        n_off = sum(len(getattr(r, "offpattern_px", None) or []) for r in self._results)
        root.addLayout(_coverage_block(t, cov, n_unc))
        marks = [("uncovered", n_unc, _tr("{n} sin cubrir").format(n=n_unc)),
                 ("orphan", n_orph, _tr("1 bóveda sin línea") if n_orph == 1
                  else _tr("{n} bóvedas sin línea").format(n=n_orph)),
                 ("offpattern", n_off, _tr("{n} fuera de patrón").format(n=n_off))]
        self.qa_legend = FlowLayout(h_spacing=14, v_spacing=4)
        self.qa_kinds = [kind for kind, n, _ in marks if n]
        for kind, n, text in marks:
            if n:
                self.qa_legend.addWidget(_legend_item(qa_swatch(kind), text, t.text))
        root.addLayout(self.qa_legend)
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.width() < 340 else 4
        if columns != self._tile_columns:
            self._tile_columns = columns
            for i, tile in enumerate(self.tiles):
                self.tiles_layout.removeWidget(tile)
                self.tiles_layout.addWidget(tile, i//columns, i%columns)
            for c in range(4):
                self.tiles_layout.setColumnStretch(c, 1 if c < columns else 0)
        self._sync_minimum_height()

    def event(self, event):
        if event.type() == QtCore.QEvent.LayoutRequest and hasattr(self, "_height_timer"):
            self._height_timer.start(0)
        return super().event(event)

    def _sync_minimum_height(self):
        layout = self.layout()
        height = layout.totalHeightForWidth(self.width())
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)

    def refresh(self):
        """Recalcula cifras y barras (p. ej. al activar/desactivar «Unir tramos en rutas»)."""
        stats = [rs.stats_for(r) for r in self._results]
        tot = rs.totals(stats)
        self.t_tramos.set_value(tot.tramos)
        self.t_ab.set_value(tot.abandonadas)
        self.t_codos.set_value(tot.codos)
        self.t_est.set_value(tot.estructuras)
        self.bars.set_stats(stats)
