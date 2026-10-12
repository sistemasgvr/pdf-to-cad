"""layer_dialog_scale.py — «Escala» en «Capas de la hoja»: calibrarla ANTES de reconocer.

Pedido del usuario 2026-10-10 (mapas de Phoenix sin capas): la escala se lee del texto del
plano (`vector_pipeline.detect_scale`); si no se puede leer (fuente sin mapa de caracteres)
queda 1"=20', y un PDF impreso reducido dice 1"=100' cuando es ~1"=160'. Los radios de los
codos y las curvas se calculan en pies AL RECONOCER: corregirla después en el editor ya no
los arregla. El botón del pie (solo con una hoja: `scale_ft_per_pt` dado) ofrece:
  · «Calibrar con una distancia conocida…»: dos clics en la hoja (Esc sale) y la distancia
    real en pies → pies/pt = real / (distancia en px / zoom del render);
  · «Escribir la escala…»: 1" = X'.
`scale_ft_per_pt()` = la nueva (None si no se tocó). El diálogo aporta `self.view`,
`_render_zoom()`, `_pix_item` y `info.set_focus_status`.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import theme as _theme


def scale_text(ft_per_pt: float) -> str:
    return _tr("Escala 1\"={v}'").format(v=f"{round(ft_per_pt * 72.0, 2):g}")


class _ClickCatcher(QtCore.QObject):
    """Clics y movimiento sobre la vista mientras se calibra."""

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            self._owner._calib_click(self._owner.view.mapToScene(event.position().toPoint()))
            return True
        if et == QtCore.QEvent.MouseMove:
            self._owner._calib_move(self._owner.view.mapToScene(event.position().toPoint()))
        return False


class ScaleCalibrationMixin:
    """Botón «Escala» del pie de «Capas de la hoja» (ver el docstring del módulo)."""

    def _build_scale_control(self, scale_ft_per_pt) -> list:
        self._scale = scale_ft_per_pt
        self._scale_changed = False
        self._calib_pts: list = []
        self._calib_items: list = []
        self._calib_filter = None
        if not scale_ft_per_pt:
            return []
        self.btn_scale = QtWidgets.QPushButton(scale_text(scale_ft_per_pt))
        self.btn_scale.setProperty("options", True)
        self.btn_scale.setToolTip(_tr("Escala del plano (pies por pulgada del PDF). Los radios y largos "
                                      "se calculan con ella al reconocer: si el PDF está impreso "
                                      "reducido, calíbrala aquí."))
        menu = QtWidgets.QMenu(self.btn_scale)
        menu.addAction(_tr("Calibrar con una distancia conocida…"), self._start_calibration)
        menu.addAction(_tr("Escribir la escala…"), self._type_scale)
        self.btn_scale.setMenu(menu)
        return [self.btn_scale]

    def scale_ft_per_pt(self):
        """La escala elegida aquí (pies/pt), o None si no se cambió."""
        return self._scale if self._scale_changed else None

    def _set_scale(self, ft_per_pt: float):
        self._scale = float(ft_per_pt)
        self._scale_changed = True
        self.btn_scale.setText(scale_text(self._scale))

    def _type_scale(self):
        val, ok = QtWidgets.QInputDialog.getDouble(
            self, _tr("Escala del plano"), _tr("1 pulgada del PDF equivale a X pies reales:"),
            round(self._scale * 72.0, 2), 0.01, 100000.0, 2)
        if ok and val > 0:
            self._set_scale(val / 72.0)

    # ── calibrar con dos clics ──
    def _start_calibration(self):
        if self._pix_item is None:
            return
        self._stop_calibration()
        self._calib_filter = _ClickCatcher(self)
        self.view.viewport().installEventFilter(self._calib_filter)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().setCursor(QtCore.Qt.CrossCursor)
        self._calib_prev_status = self.info.lbl_focus.text()
        self.info.set_focus_status(_tr("Calibrar escala: clic en dos puntos de una distancia conocida "
                                       "· Esc = salir"))

    def _stop_calibration(self):
        sc = self.view.scene()
        for it in self._calib_items:
            sc.removeItem(it)
        self._calib_items, self._calib_pts = [], []
        if self._calib_filter is not None:
            self.view.viewport().removeEventFilter(self._calib_filter)
            self._calib_filter.deleteLater()
            self._calib_filter = None
            self.view.viewport().unsetCursor()
            self.info.set_focus_status(getattr(self, "_calib_prev_status", ""))

    def calibrating(self) -> bool:
        return self._calib_filter is not None

    def _calib_pen(self) -> QtGui.QPen:
        pen = QtGui.QPen(QtGui.QColor(_theme.tokens().accent), 2.0)
        pen.setCosmetic(True)
        return pen

    def _calib_click(self, p: QtCore.QPointF):
        sc = self.view.scene()
        mark = sc.addEllipse(QtCore.QRectF(p.x() - 4, p.y() - 4, 8, 8), self._calib_pen())
        mark.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, False)
        mark.setZValue(20)
        self._calib_items.append(mark)
        self._calib_pts.append(p)
        if len(self._calib_pts) == 2:
            a, b = self._calib_pts
            QtCore.QTimer.singleShot(0, lambda: self._finish_calibration(a, b))

    def _calib_move(self, p: QtCore.QPointF):
        if len(self._calib_pts) != 1:
            return
        sc = self.view.scene()
        a = self._calib_pts[0]
        if len(self._calib_items) > 1:
            self._calib_items[1].setLine(a.x(), a.y(), p.x(), p.y())
        else:
            line = sc.addLine(a.x(), a.y(), p.x(), p.y(), self._calib_pen())
            line.setZValue(20)
            self._calib_items.append(line)

    def _finish_calibration(self, a: QtCore.QPointF, b: QtCore.QPointF):
        dist_pt = math.hypot(b.x() - a.x(), b.y() - a.y()) / max(self._render_zoom(), 1e-9)
        self._stop_calibration()
        if dist_pt < 1.0:
            return
        val, ok = QtWidgets.QInputDialog.getDouble(
            self, _tr("Calibrar escala"),
            _tr("Distancia real entre los dos puntos (pies):"),
            round(dist_pt * self._scale, 2), 0.01, 1000000.0, 2)
        if ok and val > 0:
            self._set_scale(val / dist_pt)

    def _escape(self) -> bool:
        """Esc sale de la calibración; si no, lo de siempre (quitar el resaltado)."""
        if self.calibrating():
            self._stop_calibration()
            return True
        return super()._escape()
