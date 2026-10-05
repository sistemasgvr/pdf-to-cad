"""recognition_review_view.py — panel IZQUIERDO de la vista previa del reconocimiento:
«Para verificar» y «Detalles» (pedido del usuario 2026-10-03: el panel derecho
juntaba resumen, avisos y capas; la columna izquierda quedaba vacía).

NO son errores (2.º pedido, mismo día: «que el usuario no lo confunda como que son
errores… indicarle esto es lo que se ha encontrado»): la hoja se reconoció y estos
son puntos que conviene MIRAR antes de importar. Por eso:
  - una frase arriba lo dice («Todo se reconoció… no son errores»);
  - el icono es un ojo neutro (no el ⚠ ámbar); solo un PROBLEMA de verdad (sin
    líneas, hoja sin capas…) lleva el octágono rojo y borde rojo;
  - cada tarjeta lleva debajo su EXPLICACIÓN llana (`Notice.hint`): qué se encontró
    y qué se hizo con ello;
  - el avance habla de «vistos», no de «revisados».
Además: los puntos van AGRUPADOS por utilidad (cuadrito de color + nombre una vez),
clic = ir al lugar (1/N por clic), vistos todos sus casos queda ✔; clic derecho =
pendiente; Tab llega a cada tarjeta y Enter/Espacio = clic. «Detalles» (lo
informativo) va plegado y agrupado igual. El texto completo va en el tooltip. Los
datos salen de `recognition_summary` (puro); el panel solo emite `locate(QRectF)`.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from i18n import t as _tr
from icons import icon
from model import TIPOS
from ui_common import layer_qcolor
from recognition_summary_view import utility_swatch
import recognition_summary as rs
import theme as _theme

_UTILITY_LABEL = {key: label for label, key in TIPOS}
ROW_MIN_H = 40          # tarjeta de aviso: blanco cómodo para el clic (usuarios +60)


def _level_icon(level: str):
    t = _theme.tokens()
    if level == rs.PROBLEM:
        return icon("mdi:alert-octagon-outline", color=t.danger)
    if level == rs.REVIEW:                 # «para mirar», no un error
        return icon("mdi:eye-outline", color=t.text)
    return icon("mdi:information-outline", color=t.text_muted)


class _NoticeRow(QtWidgets.QFrame):
    """Un aviso como tarjeta. Si señala algo en la hoja (`targets`), es
    cliqueable: cada clic lleva la vista previa al siguiente caso (1/N).
    `reviewable` (avisos de «Revisar», pedido del usuario 2026-09-30): vistos
    TODOS sus casos —o con un clic, si no señala nada en la hoja— queda
    «revisado» (✔ verde, texto atenuado); clic derecho lo desmarca."""

    reviewedChanged = QtCore.Signal(bool)

    def __init__(self, n: rs.Notice, targets=None, on_locate=None, reviewable: bool = False):
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
        self.setObjectName("noticeRow")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(8)
        self.ic = QtWidgets.QLabel()
        lay.addWidget(self.ic, 0, QtCore.Qt.AlignTop)
        col = QtWidgets.QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(2)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setWordWrap(True)
        col.addWidget(self.lbl)
        # explicación llana debajo (qué se encontró y qué se hizo); solo en «Para verificar»
        self.hint = QtWidgets.QLabel(_tr(n.hint) if (reviewable and n.hint) else "")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{t.text_muted}; font-size:12px; background:transparent;")
        self.hint.setVisible(bool(self.hint.text()))
        col.addWidget(self.hint)
        lay.addLayout(col, 1)
        self.clickable = bool(targets and on_locate and targets())
        self.counter = QtWidgets.QLabel("")
        self.counter.setStyleSheet(f"color:{t.text_muted}; font-size:11px; background:transparent;")
        tip = _tr(n.text)
        if self.hint.text() and n.hint != n.text:
            tip = _tr(n.hint) + "\n\n" + tip
        if self.clickable:
            lay.addWidget(self.counter, 0, QtCore.Qt.AlignVCenter)
            go = QtWidgets.QLabel(); go.setPixmap(icon("mdi:crosshairs-gps", color=t.text_muted).pixmap(16, 16))
            lay.addWidget(go, 0, QtCore.Qt.AlignVCenter)
            tip += "\n\n" + _tr("Clic: ir al lugar en la hoja (cada clic, el siguiente).")
            if self.reviewable:
                tip += "\n" + _tr("Al ver todos los casos queda marcado como visto.")
        elif self.reviewable:
            tip += "\n\n" + _tr("Clic: marcar como visto.")
        self.interactive = self.clickable or self.reviewable
        if self.interactive:
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setFocusPolicy(QtCore.Qt.StrongFocus)     # Tab llega; Enter/Espacio = clic
            self.setMinimumHeight(ROW_MIN_H)
        self.setToolTip(tip)
        self._render()

    def _style(self):
        t = _theme.tokens()
        if not self.interactive:            # detalle informativo: fila plana
            return "#noticeRow { background:transparent; border:none; }"
        if self.reviewed:
            base = f"background:transparent; border:1px dashed {t.border};"
        elif self._notice.level == rs.PROBLEM:          # problema de verdad: borde rojo
            base = f"background:{t.surface_alt}; border:1px solid {t.danger};"
        else:
            base = f"background:{t.surface_alt}; border:1px solid {t.border_soft};"
        return (f"#noticeRow {{ {base} border-radius:6px; }}"
                f" #noticeRow:hover {{ border:1px solid {t.text_muted}; }}"
                f" #noticeRow:focus {{ border:2px solid {t.focus}; }}"
                " #noticeRow QLabel { background:transparent; border:none; }")

    def _render(self):
        t = _theme.tokens()
        n = self._notice
        if self.reviewed:
            self.ic.setPixmap(icon("mdi:check-circle-outline", color=t.success).pixmap(18, 18))
            ink = t.text_muted
        else:
            self.ic.setPixmap(_level_icon(n.level).pixmap(18, 18))
            ink = t.text if n.level != rs.INFO else t.text_muted
        self.lbl.setText(f"<span style='color:{ink}'>{_tr(n.label)}</span>")
        self.setStyleSheet(self._style())

    def set_reviewed(self, on: bool):
        on = bool(on)
        if on == self.reviewed:
            return
        self.reviewed = on
        if not on:
            self._seen.clear()
        self._render()
        self.reviewedChanged.emit(on)

    def activate(self):
        """Clic izquierdo (o Enter/Espacio): ir al siguiente caso, o marcar."""
        if self.clickable:
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
        if self.reviewable:
            self.set_reviewed(not self.reviewed)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self.interactive:
            self.activate()
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if self.interactive and e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space):
            self.activate()
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        if not self.reviewable:
            return super().contextMenuEvent(e)
        menu = QtWidgets.QMenu(self)
        act = menu.addAction(_tr("Marcar como pendiente") if self.reviewed else _tr("Marcar como visto"))
        if menu.exec(e.globalPos()) is act:
            self.set_reviewed(not self.reviewed)


def _utility_header(utility: str) -> QtWidgets.QWidget:
    """Cuadrito del color de la utilidad + su nombre (encabeza su grupo de avisos)."""
    t = _theme.tokens()
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(2, 6, 2, 0); lay.setSpacing(6)
    sw = QtWidgets.QLabel(); sw.setPixmap(utility_swatch(layer_qcolor(utility), 12))
    lay.addWidget(sw, 0)
    lb = QtWidgets.QLabel(_tr(_UTILITY_LABEL.get(utility, utility)))
    lb.setStyleSheet(f"color:{t.text}; font-weight:bold;")
    lay.addWidget(lb, 1)
    return w


class ReviewPanel(QtWidgets.QWidget):
    """«Para verificar» (frase + avance + puntos por utilidad) y «Detalles» plegado.

    `locate(QRectF)`: el usuario hizo clic en un aviso que señala algo de la
    hoja; el rectángulo va en coordenadas de la escena de la vista previa."""

    locate = QtCore.Signal(QtCore.QRectF)

    def __init__(self, results, parent=None):
        super().__init__(parent)
        self._results = list(results)
        multi = len(self._results) > 1
        t = _theme.tokens()
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(6)

        notices = rs.notices_for(self._results)
        act = [n for n in notices if n.level != rs.INFO]
        info = [n for n in notices if n.level == rs.INFO]
        self.lbl_reviewed = None
        self.progress = None
        self.problems = sum(1 for n in act if n.level == rs.PROBLEM)
        # qué es esta lista (en una frase): lo encontrado, no errores
        self.lbl_intro = QtWidgets.QLabel()
        self.lbl_intro.setWordWrap(True)
        self.lbl_intro.setStyleSheet(f"color:{t.text_muted};")
        if not act:
            self.lbl_intro.setText(_tr("Todo se reconoció sin dudas: no hay nada que mirar antes de importar."))
        elif self.problems:
            self.lbl_intro.setText(_tr("En rojo, lo que no se pudo reconocer. Lo demás se reconoció y "
                                       "conviene mirarlo en la hoja antes de importar."))
        else:
            self.lbl_intro.setText(_tr("Todo se reconoció. Estos puntos conviene mirarlos en la hoja antes "
                                       "de importar; no son errores. Clic en uno para verlo."))
        if act:
            root.addWidget(self.lbl_intro)
            self.lbl_reviewed = QtWidgets.QLabel()
            self.lbl_reviewed.setToolTip(_tr("Puntos ya vistos. Clic derecho en uno: marcarlo como pendiente."))
            root.addWidget(self.lbl_reviewed)
            self.progress = QtWidgets.QProgressBar()
            self.progress.setRange(0, len(act))
            self.progress.setTextVisible(False)
            self.progress.setFixedHeight(6)
            root.addWidget(self.progress)
        else:
            ok = QtWidgets.QHBoxLayout()
            ic = QtWidgets.QLabel(); ic.setPixmap(icon("mdi:check-circle-outline", color=t.success).pixmap(18, 18))
            lb = QtWidgets.QLabel(_tr("Nada que verificar"))
            lf = lb.font(); lf.setBold(True); lb.setFont(lf)
            ok.addWidget(ic); ok.addWidget(lb, 1)
            root.addLayout(ok)
            root.addWidget(self.lbl_intro)

        # avisos de «Revisar», agrupados por utilidad (primero la que tenga problemas)
        self.review = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(self.review); rl.setContentsMargins(0, 2, 0, 0); rl.setSpacing(6)
        self.review_rows = []
        for utility, rows in self._groups(act):
            if multi:
                rl.addWidget(_utility_header(utility))
            for n in rows:
                row = self._row(n, reviewable=True)
                row.reviewedChanged.connect(lambda _on: self._refresh_reviewed())
                self.review_rows.append(row)
                rl.addWidget(row)
        self.review.setVisible(bool(act))
        root.addWidget(self.review)
        self._refresh_reviewed()

        # «Detalles»: lo informativo, plegado y agrupado por utilidad
        root.addSpacing(6)
        self.btn_details = QtWidgets.QToolButton()
        self.btn_details.setCheckable(True)
        self.btn_details.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_details.setAutoRaise(True)
        self.btn_details.setText(_tr("Detalles ({n})").format(n=len(info)))
        self.btn_details.setIcon(icon("mdi:chevron-right", color=t.text_muted))
        self.btn_details.setVisible(bool(info))
        f = self.btn_details.font(); f.setBold(True); self.btn_details.setFont(f)
        root.addWidget(self.btn_details)
        self.details = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(self.details); dl.setContentsMargins(4, 0, 0, 0); dl.setSpacing(0)
        for utility, rows in self._groups(info):
            if multi:
                dl.addWidget(_utility_header(utility))
            for n in rows:
                dl.addWidget(self._row(n))
        self.details.setVisible(False)
        root.addWidget(self.details)
        self.btn_details.toggled.connect(self._toggle_details)
        root.addStretch(1)

    def _groups(self, notices):
        """[(utilidad, avisos)] en el orden de los resultados; primero los grupos con
        un problema (nivel más grave) y, dentro de cada grupo, por nivel."""
        order = {r.utility: i for i, r in enumerate(self._results)}
        groups: dict = {}
        for n in notices:
            groups.setdefault(n.utility, []).append(n)
        items = [(u, sorted(rows, key=lambda n: rs.LEVEL_ORDER[n.level])) for u, rows in groups.items()]
        items.sort(key=lambda it: (min(rs.LEVEL_ORDER[n.level] for n in it[1]), order.get(it[0], 99)))
        return items

    def _row(self, n: rs.Notice, reviewable: bool = False) -> _NoticeRow:
        result = next((r for r in self._results if r.utility == n.utility), None)
        targets = (lambda: rs.targets_for(n.key, result)) if (n.key and result is not None) else None
        return _NoticeRow(n, targets,
                          lambda r: self.locate.emit(QtCore.QRectF(QtCore.QPointF(r[0], r[1]),
                                                                    QtCore.QPointF(r[2], r[3]))),
                          reviewable=reviewable)

    def pending(self) -> int:
        return sum(1 for r in self.review_rows if not r.reviewed)

    def _refresh_reviewed(self):
        """«k de N vistos» y la barra de avance; en verde cuando no queda ninguno."""
        if self.lbl_reviewed is None:
            return
        t = _theme.tokens()
        done = len(self.review_rows) - self.pending()
        self.progress.setValue(done)
        chunk = t.success if done >= len(self.review_rows) else t.accent
        self.progress.setStyleSheet(
            f"QProgressBar {{ border:none; border-radius:3px; background:{t.border_soft}; }}"
            f"QProgressBar::chunk {{ background:{chunk}; border-radius:3px; }}")
        if done >= len(self.review_rows):
            self.lbl_reviewed.setText(_tr("✔ Todos vistos"))
            self.lbl_reviewed.setStyleSheet(f"color:{t.success}; font-weight:bold;")
        else:
            self.lbl_reviewed.setText(_tr("{k} de {n} vistos").format(k=done, n=len(self.review_rows)))
            self.lbl_reviewed.setStyleSheet(f"color:{t.text_muted};")

    def _toggle_details(self, on: bool):
        self.details.setVisible(on)
        self.btn_details.setIcon(icon("mdi:chevron-down" if on else "mdi:chevron-right",
                                      color=_theme.tokens().text_muted))
