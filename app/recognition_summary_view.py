"""recognition_summary_view.py — resumen VISUAL de la vista previa del reconocimiento.

Reemplaza el bloque de texto de avisos por:
  1. cuatro tarjetas con las cifras (tramos, abandonadas, codos, estructuras);
  2. una barra por utilidad (misma escala): activas en sólido, abandonadas (AB)
     rayadas del mismo color — el color es la utilidad, igual que en el lienzo;
  3. «Revisar»: solo los avisos que piden una decisión, en una línea con icono;
     el texto completo va en el tooltip. Lo informativo queda plegado en
     «Detalles».
Los datos salen de `recognition_summary` (puro).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr
from icons import icon
from model import TIPOS
from ui_common import layer_qcolor
import recognition_summary as rs
import theme as _theme

_UTILITY_LABEL = {key: label for label, key in TIPOS}
WARN_COLOR = "#e08a00"          # ámbar de «revisar» (el mismo del QA de cobertura)


def _needs_outline(color: QtGui.QColor) -> bool:
    """¿El color de la utilidad casi no se distingue del fondo del panel? (ACI 7
    = blanco en oscuro). Entonces la barra lleva contorno en tinta de texto."""
    bg = QtGui.QColor(_theme.tokens().surface)
    return abs(color.lightness() - bg.lightness()) < 60 or color.lightness() > 235 and bg.lightness() > 200


def _level_icon(level: str) -> QtGui.QIcon:
    t = _theme.tokens()
    if level == rs.PROBLEM:
        return icon("mdi:alert-octagon-outline", color=t.danger)
    if level == rs.REVIEW:
        return icon("mdi:alert-outline", color=WARN_COLOR)
    return icon("mdi:information-outline", color=t.text_muted)


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
        cap = QtWidgets.QLabel(_tr(label))
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
        bar_w = max(40, self.width() - name_w - num_w)
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
                       _tr(_UTILITY_LABEL.get(s.utility, s.utility)))
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


class _NoticeRow(QtWidgets.QWidget):
    """Una línea de aviso. Si el aviso señala algo en la hoja (`targets`), la fila
    es cliqueable: cada clic lleva la vista previa al siguiente caso (1/N)."""

    def __init__(self, n: rs.Notice, show_utility: bool, targets=None, on_locate=None):
        super().__init__()
        t = _theme.tokens()
        self._targets = targets            # callable → [Rect] (se recalcula: «Unir rutas» cambia tramos)
        self._on_locate = on_locate
        self._idx = -1
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1); lay.setSpacing(6)
        ic = QtWidgets.QLabel(); ic.setPixmap(_level_icon(n.level).pixmap(16, 16))
        lay.addWidget(ic, 0, QtCore.Qt.AlignTop)
        util = (f"<span style='color:{t.text_muted}'>{_tr(_UTILITY_LABEL.get(n.utility, n.utility))} · </span>"
                if show_utility else "")
        ink = t.text if n.level != rs.INFO else t.text_muted
        lbl = QtWidgets.QLabel(f"{util}<span style='color:{ink}'>{_tr(n.label)}</span>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        self.clickable = bool(targets and on_locate and targets())
        tip = _tr(n.text)
        if self.clickable:
            self.counter = QtWidgets.QLabel("")
            self.counter.setStyleSheet(f"color:{t.text_muted}; font-size:11px;")
            lay.addWidget(self.counter, 0, QtCore.Qt.AlignTop)
            go = QtWidgets.QLabel(); go.setPixmap(icon("mdi:crosshairs-gps", color=t.text_muted).pixmap(14, 14))
            lay.addWidget(go, 0, QtCore.Qt.AlignTop)
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setAttribute(QtCore.Qt.WA_Hover, True)
            self.setObjectName("noticeRow")
            self.setStyleSheet(f"#noticeRow {{ border-radius:4px; }}"
                               f" #noticeRow:hover {{ background:{t.surface_alt}; }}")
            self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            tip += "\n\n" + _tr("Clic: ir al lugar en la hoja (cada clic, el siguiente).")
        self.setToolTip(tip)

    def mouseReleaseEvent(self, e):
        if self.clickable and e.button() == QtCore.Qt.LeftButton:
            rects = self._targets() or []
            if rects:
                self._idx = (self._idx + 1) % len(rects)
                self.counter.setText(f"{self._idx + 1}/{len(rects)}")
                self._on_locate(rects[self._idx])
            return
        super().mouseReleaseEvent(e)


class SummaryPanel(QtWidgets.QWidget):
    """Resumen del reconocimiento: tarjetas + barras por utilidad + avisos.

    `locate(QRectF)`: el usuario hizo clic en un aviso que señala algo de la
    hoja; el rectángulo va en coordenadas de la escena de la vista previa."""

    locate = QtCore.Signal(QtCore.QRectF)

    def __init__(self, results, parent=None):
        super().__init__(parent)
        self._results = list(results)
        multi = len(self._results) > 1
        t = _theme.tokens()
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(8)

        tiles = QtWidgets.QGridLayout(); tiles.setSpacing(6)
        self.t_tramos = _Tile("Tramos", "Polilíneas que se importan al editor.")
        self.t_ab = _Tile("Abandonadas", "Tramos marcados (AB): capa «-A» + patrón «/», o patrón «//».")
        self.t_codos = _Tile("Codos", "Esquinas con radio (curvas reales del plano).")
        self.t_est = _Tile("Estructuras", "Bóvedas que quedan como nodos de las líneas.")
        for i, w in enumerate((self.t_tramos, self.t_ab, self.t_codos, self.t_est)):
            tiles.addWidget(w, 0, i)
        root.addLayout(tiles)

        self.bars = UtilityBars()
        root.addWidget(self.bars)
        leg = QtWidgets.QHBoxLayout(); leg.setSpacing(6)
        base = layer_qcolor(self._results[0].utility) if not multi else QtGui.QColor(t.text_muted)
        for hatched, text in ((False, "activas"), (True, "abandonadas (AB)")):
            sw = QtWidgets.QLabel(); sw.setPixmap(_legend_swatch(base, hatched))
            lb = QtWidgets.QLabel(_tr(text)); lb.setStyleSheet(f"color:{t.text_muted};")
            leg.addWidget(sw); leg.addWidget(lb); leg.addSpacing(8)
        leg.addStretch(1)
        root.addLayout(leg)

        notices = rs.notices_for(self._results)
        act = [n for n in notices if n.level != rs.INFO]
        info = [n for n in notices if n.level == rs.INFO]
        if act:
            head = QtWidgets.QLabel(_tr("Revisar ({n})").format(n=len(act)))
            hf = head.font(); hf.setBold(True); head.setFont(hf)
            root.addWidget(head)
        else:
            ok = QtWidgets.QHBoxLayout()
            ic = QtWidgets.QLabel(); ic.setPixmap(icon("mdi:check-circle-outline", color=t.success).pixmap(16, 16))
            lb = QtWidgets.QLabel(_tr("Nada que revisar"))
            lf = lb.font(); lf.setBold(True); lb.setFont(lf)
            ok.addWidget(ic); ok.addWidget(lb, 1)
            root.addLayout(ok)
        for n in act:
            root.addWidget(self._row(n, multi))

        self.btn_details = QtWidgets.QToolButton()
        self.btn_details.setCheckable(True)
        self.btn_details.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_details.setAutoRaise(True)
        self.btn_details.setText(_tr("Detalles ({n})").format(n=len(info)))
        self.btn_details.setIcon(icon("mdi:chevron-down", color=t.text_muted))
        self.btn_details.setVisible(bool(info))
        root.addWidget(self.btn_details)
        # «Detalles»: agrupado por utilidad y con scroll propio (no aplasta la
        # lista de capas de abajo).
        body = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(body); dl.setContentsMargins(4, 0, 4, 0); dl.setSpacing(0)
        for r in self._results:
            rows = [n for n in info if n.utility == r.utility]
            if not rows:
                continue
            if multi:
                hd = QtWidgets.QLabel(_tr(_UTILITY_LABEL.get(r.utility, r.utility)))
                hd.setStyleSheet(f"color:{t.text}; font-weight:bold; padding-top:4px;")
                dl.addWidget(hd)
            for n in rows:
                dl.addWidget(self._row(n, False))
        dl.addStretch(1)
        self.details = QtWidgets.QScrollArea()
        self.details.setWidget(body); self.details.setWidgetResizable(True)
        self.details.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.details.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.details.setMaximumHeight(200)
        self.details.setVisible(False)
        root.addWidget(self.details)
        self.btn_details.toggled.connect(self._toggle_details)
        self.refresh()

    def _row(self, n: rs.Notice, show_utility: bool) -> _NoticeRow:
        result = next((r for r in self._results if r.utility == n.utility), None)
        targets = (lambda: rs.targets_for(n.key, result)) if (n.key and result is not None) else None
        return _NoticeRow(n, show_utility, targets,
                          lambda r: self.locate.emit(QtCore.QRectF(QtCore.QPointF(r[0], r[1]),
                                                                    QtCore.QPointF(r[2], r[3]))))

    def _toggle_details(self, on: bool):
        self.details.setVisible(on)
        self.btn_details.setIcon(icon("mdi:chevron-up" if on else "mdi:chevron-down",
                                      color=_theme.tokens().text_muted))

    def refresh(self):
        """Recalcula cifras y barras (p. ej. al activar/desactivar «Unir tramos en rutas»)."""
        stats = [rs.stats_for(r) for r in self._results]
        tot = rs.totals(stats)
        self.t_tramos.set_value(tot.tramos)
        self.t_ab.set_value(tot.abandonadas)
        self.t_codos.set_value(tot.codos)
        self.t_est.set_value(tot.estructuras)
        self.bars.set_stats(stats)
