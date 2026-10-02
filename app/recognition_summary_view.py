"""recognition_summary_view.py — resumen VISUAL de la vista previa del reconocimiento.

Reemplaza el bloque de texto de avisos por:
  1. cuatro tarjetas con las cifras (tramos, abandonadas, codos, estructuras);
  2. una barra por utilidad (misma escala): activas en sólido, abandonadas (AB)
     rayadas del mismo color — el color es la utilidad, igual que en el lienzo;
  3. una leyenda en UNA fila (salta de línea si no cabe): activas, AB, lo que el
     QA pinta sobre la hoja (sin cubrir, fuera de patrón) y la escala; debajo la
     barra de cobertura (pedido del usuario 2026-09-30: juntar el QA con las cifras);
  4. «Revisar»: solo los avisos que piden una decisión, en una línea con icono,
     con alto máximo y scroll; el texto completo va en el tooltip. Clic = ir al
     lugar; vistos todos sus casos, el aviso queda «revisado» (✔). Lo
     informativo queda plegado en «Detalles».
Los datos salen de `recognition_summary` (puro).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import t as _tr, N_
from icons import icon
from model import TIPOS
from ui_common import layer_qcolor, swatch_icon
from widgets import FlowLayout
import recognition_summary as rs
import theme as _theme

_UTILITY_LABEL = {key: label for label, key in TIPOS}
WARN_COLOR = "#e08a00"          # ámbar de «revisar» (el mismo del QA de cobertura)
UNCOVERED_COLOR = "#ff8c00"     # guiones sin cubrir (así se pintan en la vista previa)
OFFPATTERN_COLOR = "#8a6cff"    # trazos fuera de patrón (leaders/flechas)
REVIEW_MAX_H = 170              # «Revisar»: ~6 avisos; más → scroll (no aplasta el panel)
DETAILS_MAX_H = 200


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


def _legend_item(pixmap: QtGui.QPixmap, text: str, ink: str) -> QtWidgets.QWidget:
    """Muestra de color + texto como UNA pieza de la leyenda (salta de línea entera)."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
    sw = QtWidgets.QLabel(); sw.setPixmap(pixmap)
    lb = QtWidgets.QLabel(text); lb.setStyleSheet(f"color:{ink}; font-size:12px;")
    lay.addWidget(sw); lay.addWidget(lb)
    return w


def _coverage_bar(t, cov: float, n_unc: int) -> QtWidgets.QLayout:
    """Cobertura como barra de avance 0–100 % (verde ≥98 % sin huecos, ámbar
    ≥90 %, rojo por debajo). Lo que quedó fuera va en la leyenda de arriba."""
    qa_ok = cov >= 0.98 and n_unc == 0
    bar_color = t.success if qa_ok else (WARN_COLOR if cov >= 0.90 else t.danger)
    top = QtWidgets.QHBoxLayout(); top.setSpacing(6)
    ic = QtWidgets.QLabel()
    ic.setPixmap(icon("mdi:check-circle-outline" if qa_ok else "mdi:alert-outline",
                      color=bar_color).pixmap(16, 16))
    top.addWidget(ic, 0)
    top.addWidget(QtWidgets.QLabel(_tr("Cobertura")), 0)
    bar = QtWidgets.QProgressBar()
    bar.setRange(0, 1000)
    bar.setValue(int(round(max(0.0, min(1.0, cov)) * 1000)))
    bar.setFormat(f"{cov * 100:.1f} %")
    bar.setTextVisible(True)
    bar.setAlignment(QtCore.Qt.AlignCenter)
    bar.setFixedHeight(18)
    bar.setStyleSheet(
        f"QProgressBar {{ border:1px solid {t.border}; border-radius:4px;"
        f" background:{t.surface_alt}; color:{t.text}; font-weight:bold; }}"
        f"QProgressBar::chunk {{ background:{bar_color}; border-radius:3px; }}")
    bar.setToolTip(_tr("Guiones del plano cubiertos por las líneas reconocidas. En el dibujo: "
                       "naranja = sin cubrir, violeta = trazos fuera de patrón (leaders/flechas)."))
    top.addWidget(bar, 1)
    return top


class _CappedScroll(QtWidgets.QScrollArea):
    """Lista con su alto natural hasta `cap` px; si hay más, scroll (el panel no
    crece sin límite con muchos avisos)."""

    def __init__(self, body: QtWidgets.QWidget, cap: int):
        super().__init__()
        self._cap = int(cap)
        self.setWidget(body)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.setFixedHeight(min(self._cap, body.sizeHint().height()))

    def natural_height(self, width: int) -> int:
        lay = self.widget().layout()
        if lay is not None and lay.hasHeightForWidth():
            return lay.totalHeightForWidth(width)
        return self.widget().sizeHint().height()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # las líneas largas se parten según el ancho: el alto se recalcula aquí
        h = min(self._cap, self.natural_height(self.viewport().width()))
        if h != self.height():
            self.setFixedHeight(h)


class _NoticeRow(QtWidgets.QWidget):
    """Una línea de aviso. Si el aviso señala algo en la hoja (`targets`), la fila
    es cliqueable: cada clic lleva la vista previa al siguiente caso (1/N).
    `reviewable` (avisos de «Revisar», pedido del usuario 2026-09-30): vistos
    TODOS sus casos —o con un clic, si no señala nada en la hoja— queda
    «revisado» (✔ verde, texto atenuado); clic derecho lo desmarca."""

    reviewedChanged = QtCore.Signal(bool)

    def __init__(self, n: rs.Notice, show_utility: bool, targets=None, on_locate=None,
                 reviewable: bool = False):
        super().__init__()
        t = _theme.tokens()
        self._notice = n
        self._targets = targets            # callable → [Rect] (se recalcula: «Unir rutas» cambia tramos)
        self._on_locate = on_locate
        self._idx = -1
        self._seen: set = set()            # casos ya vistos (índices en la lista de targets)
        self._n_targets = 0
        self.reviewable = bool(reviewable)
        self.reviewed = False
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1); lay.setSpacing(6)
        self.ic = QtWidgets.QLabel()
        lay.addWidget(self.ic, 0, QtCore.Qt.AlignTop)
        self._util = (f"<span style='color:{t.text_muted}'>{_tr(_UTILITY_LABEL.get(n.utility, n.utility))} · </span>"
                      if show_utility else "")
        self.lbl = QtWidgets.QLabel()
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl, 1)
        self.clickable = bool(targets and on_locate and targets())
        self.counter = QtWidgets.QLabel("")
        self.counter.setStyleSheet(f"color:{t.text_muted}; font-size:11px;")
        tip = _tr(n.text)
        if self.clickable:
            lay.addWidget(self.counter, 0, QtCore.Qt.AlignTop)
            go = QtWidgets.QLabel(); go.setPixmap(icon("mdi:crosshairs-gps", color=t.text_muted).pixmap(14, 14))
            lay.addWidget(go, 0, QtCore.Qt.AlignTop)
            tip += "\n\n" + _tr("Clic: ir al lugar en la hoja (cada clic, el siguiente).")
            if self.reviewable:
                tip += "\n" + _tr("Al ver todos los casos queda marcado como revisado.")
        elif self.reviewable:
            tip += "\n\n" + _tr("Clic: marcar como revisado.")
        if self.clickable or self.reviewable:
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setAttribute(QtCore.Qt.WA_Hover, True)
            self.setObjectName("noticeRow")
            self.setStyleSheet(f"#noticeRow {{ border-radius:4px; }}"
                               f" #noticeRow:hover {{ background:{t.surface_alt}; }}")
            self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setToolTip(tip)
        self._render()

    def _render(self):
        t = _theme.tokens()
        n = self._notice
        if self.reviewed:
            self.ic.setPixmap(icon("mdi:check-circle-outline", color=t.success).pixmap(16, 16))
            ink = t.text_muted
        else:
            self.ic.setPixmap(_level_icon(n.level).pixmap(16, 16))
            ink = t.text if n.level != rs.INFO else t.text_muted
        self.lbl.setText(f"{self._util}<span style='color:{ink}'>{_tr(n.label)}</span>")

    def set_reviewed(self, on: bool):
        on = bool(on)
        if on == self.reviewed:
            return
        self.reviewed = on
        if not on:
            self._seen.clear()
        self._render()
        self.reviewedChanged.emit(on)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self.clickable:
            rects = self._targets() or []
            if rects:
                if len(rects) != self._n_targets:        # «Unir rutas» cambió los casos
                    self._n_targets, self._idx = len(rects), -1
                    self._seen.clear()
                self._idx = (self._idx + 1) % len(rects)
                self._seen.add(self._idx)
                self.counter.setText(f"{self._idx + 1}/{len(rects)}")
                self._on_locate(rects[self._idx])
                if self.reviewable and len(self._seen) >= len(rects):
                    self.set_reviewed(True)
            return
        if e.button() == QtCore.Qt.LeftButton and self.reviewable:
            self.set_reviewed(not self.reviewed)
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        if not self.reviewable:
            return super().contextMenuEvent(e)
        menu = QtWidgets.QMenu(self)
        act = menu.addAction(_tr("Marcar como pendiente") if self.reviewed else _tr("Marcar como revisado"))
        if menu.exec(e.globalPos()) is act:
            self.set_reviewed(not self.reviewed)


class SummaryPanel(QtWidgets.QWidget):
    """Resumen del reconocimiento: tarjetas + barras por utilidad + leyenda y
    cobertura + avisos.

    `locate(QRectF)`: el usuario hizo clic en un aviso que señala algo de la
    hoja; el rectángulo va en coordenadas de la escena de la vista previa."""

    locate = QtCore.Signal(QtCore.QRectF)

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
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(8)

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
        root.addLayout(tiles)

        self.bars = UtilityBars()
        root.addWidget(self.bars)
        # Leyenda en UNA fila (salta de línea si no cabe): lo que muestran las
        # barras (activas / AB), lo que el QA pinta sobre la hoja y la escala.
        cov = min(float(getattr(r, "coverage", 1.0) or 0.0) for r in self._results)
        n_unc = sum(len(getattr(r, "uncovered_px", None) or []) for r in self._results)
        n_off = sum(len(getattr(r, "offpattern_px", None) or []) for r in self._results)
        legend = FlowLayout(h_spacing=14, v_spacing=4)
        base = layer_qcolor(self._results[0].utility) if not multi else QtGui.QColor(t.text_muted)
        legend.addWidget(_legend_item(_legend_swatch(base, False), _tr(N_("activas")), t.text_muted))
        legend.addWidget(_legend_item(_legend_swatch(base, True), _tr(N_("abandonadas (AB)")), t.text_muted))
        for n, color, text in ((n_unc, UNCOVERED_COLOR, _tr("{n} sin cubrir").format(n=n_unc)),
                               (n_off, OFFPATTERN_COLOR, _tr("{n} fuera de patrón").format(n=n_off))):
            legend.addWidget(_legend_item(swatch_icon(QtGui.QColor(color), 10).pixmap(10, 10), text,
                                          t.text if n else t.text_muted))
        scale = float(getattr(self._results[0], "scale_ft_per_pt", 0.0) or 0.0)
        self.lbl_scale = QtWidgets.QLabel(_tr("Escala 1\"={v}'").format(v=f"{round(scale * 72.0, 3):g}"))
        self.lbl_scale.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
        self.lbl_scale.setToolTip(_tr("Escala {s:.6f} pie/pt").format(s=scale))
        legend.addWidget(self.lbl_scale)
        root.addLayout(legend)
        root.addLayout(_coverage_bar(t, cov, n_unc))

        notices = rs.notices_for(self._results)
        act = [n for n in notices if n.level != rs.INFO]
        info = [n for n in notices if n.level == rs.INFO]
        self.lbl_reviewed = None
        if act:
            hrow = QtWidgets.QHBoxLayout()
            head = QtWidgets.QLabel(_tr("Revisar ({n})").format(n=len(act)))
            hf = head.font(); hf.setBold(True); head.setFont(hf)
            hrow.addWidget(head, 1)
            self.lbl_reviewed = QtWidgets.QLabel()
            self.lbl_reviewed.setToolTip(_tr("Avisos ya revisados. Clic derecho en un aviso: "
                                             "marcarlo como pendiente."))
            hrow.addWidget(self.lbl_reviewed, 0)
            root.addLayout(hrow)
        else:
            ok = QtWidgets.QHBoxLayout()
            ic = QtWidgets.QLabel(); ic.setPixmap(icon("mdi:check-circle-outline", color=t.success).pixmap(16, 16))
            lb = QtWidgets.QLabel(_tr("Nada que revisar"))
            lf = lb.font(); lf.setBold(True); lb.setFont(lf)
            ok.addWidget(ic); ok.addWidget(lb, 1)
            root.addLayout(ok)
        # «Revisar» con alto máximo: con muchos avisos, scroll (pedido del usuario)
        body = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(body); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(2)
        self.review_rows = [self._row(n, multi, reviewable=True) for n in act]
        for row in self.review_rows:
            row.reviewedChanged.connect(lambda _on: self._refresh_reviewed())
            rl.addWidget(row)
        self.review = _CappedScroll(body, REVIEW_MAX_H)
        self.review.setVisible(bool(act))
        root.addWidget(self.review)
        self._refresh_reviewed()

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
        self.details = _CappedScroll(body, DETAILS_MAX_H)
        self.details.setVisible(False)
        root.addWidget(self.details)
        self.btn_details.toggled.connect(self._toggle_details)
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.width() < 360 else 4
        if columns != self._tile_columns:
            self._tile_columns = columns
            for i, tile in enumerate(self.tiles):
                self.tiles_layout.removeWidget(tile)
                self.tiles_layout.addWidget(tile, i//columns, i%columns)
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

    def _row(self, n: rs.Notice, show_utility: bool, reviewable: bool = False) -> _NoticeRow:
        result = next((r for r in self._results if r.utility == n.utility), None)
        targets = (lambda: rs.targets_for(n.key, result)) if (n.key and result is not None) else None
        return _NoticeRow(n, show_utility, targets,
                          lambda r: self.locate.emit(QtCore.QRectF(QtCore.QPointF(r[0], r[1]),
                                                                    QtCore.QPointF(r[2], r[3]))),
                          reviewable=reviewable)

    def _refresh_reviewed(self):
        """«k de N revisados» junto a «Revisar»; en verde cuando no queda ninguno."""
        if self.lbl_reviewed is None:
            return
        t = _theme.tokens()
        done = sum(1 for r in self.review_rows if r.reviewed)
        if done >= len(self.review_rows):
            self.lbl_reviewed.setText(_tr("✔ Todo revisado"))
            self.lbl_reviewed.setStyleSheet(f"color:{t.success}; font-weight:bold; font-size:12px;")
        else:
            self.lbl_reviewed.setText(_tr("{k} de {n} revisados").format(k=done, n=len(self.review_rows)))
            self.lbl_reviewed.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")

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
