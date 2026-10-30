"""Seleccionar una familia de vectores desde su tinta visible en el PDF."""
import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from ui.asistente.layer_dialog_info import _qpath
from ui.comun.busy import busy
from traduccion.i18n import t as _tr


class StylePicker(QtCore.QObject):
    TOLERANCE = 6.0                 # píxeles de pantalla, independiente del zoom

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._press = None
        owner.view.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        dlg = self.owner
        if getattr(dlg, "_calib_filter", None) is not None:
            self._press = None
            return False
        if event.type() == QtCore.QEvent.MouseButtonPress:
            self._press = (event.position().toPoint()
                           if event.button() == QtCore.Qt.LeftButton else None)
        elif event.type() == QtCore.QEvent.MouseButtonRelease:
            start, self._press = self._press, None
            pos = event.position().toPoint()
            if (start is not None and event.button() == QtCore.Qt.LeftButton
                    and (pos - start).manhattanLength() < QtWidgets.QApplication.startDragDistance()):
                self.select_at(pos)
        return False

    def select_at(self, pos):
        dlg = self.owner
        if dlg._pix_item is None or getattr(dlg, "_dibujando", False):
            return
        names = {L['name'] for L in dlg._layers if L.get('source') == 'style'}
        if not names:
            return
        dlg._view_auto = False
        view = dlg.view
        scene_pos = view.mapToScene(pos)
        if not dlg._pix_item.sceneBoundingRect().contains(scene_pos):
            return
        # Misma lectura recortada que el resaltado: respeta clips, giros y
        # familias especiales (acometidas/símbolos), sin inferir por el color.
        z = dlg._render_zoom()
        matrix = dlg._page.rotation_matrix
        pdf_pos = fitz.Point(scene_pos.x() / z, scene_pos.y() / z) * ~matrix
        scale = max(1e-9, abs(view.transform().m11()))
        radius = self.TOLERANCE / (z * scale)
        screen_pos = QtCore.QPointF(pos)
        best, name = self.TOLERANCE + 1, None
        stroker = QtGui.QPainterPathStroker()
        stroker.setCapStyle(QtCore.Qt.RoundCap)
        stroker.setJoinStyle(QtCore.Qt.RoundJoin)
        if dlg._drawings is None:
            with busy(view, _tr("Leyendo las líneas de la hoja…")):
                dlg._all_drawings()
        for original, shown in dlg._all_drawings():
            candidate = original.get('layer')
            if candidate not in names:
                continue
            rect = original.get('rect')
            if rect is not None and not (rect.x0 - radius <= pdf_pos.x <= rect.x1 + radius
                                         and rect.y0 - radius <= pdf_pos.y <= rect.y1 + radius):
                continue
            path = view.viewportTransform().map(_qpath(shown, matrix, z))
            if not path.boundingRect().adjusted(-best, -best, best, best).contains(screen_pos):
                continue
            stroker.setWidth(2 * min(best, self.TOLERANCE))
            if not stroker.createStroke(path).contains(screen_pos):
                continue
            low, high = 0.0, min(best, self.TOLERANCE)
            for _ in range(7):
                mid = (low + high) / 2
                stroker.setWidth(max(.001, 2 * mid))
                if stroker.createStroke(path).contains(screen_pos):
                    high = mid
                else:
                    low = mid
            if high < best:
                best, name = high, candidate
        if name is None:
            return
        items = dlg._items_by_name.get(name, ())
        if not items:
            return
        # Un filtro previo no debe impedir encontrar la familia pulsada.
        if items[0].isHidden():
            dlg.search.clear()
        item = items[0]
        item.parent().setExpanded(True)
        # Evitar el encuadre automático del clic en el árbol: al buscar desde
        # el plano se conserva exactamente la cámara del usuario.
        blocker = QtCore.QSignalBlocker(dlg.tree)
        dlg.tree.setCurrentItem(item)
        del blocker
        dlg._assignment_selection_changed(item)
        dlg.tree.scrollToItem(item, QtWidgets.QAbstractItemView.EnsureVisible)
        dlg._focus_lines({'layers': [name]}, fit=False)
