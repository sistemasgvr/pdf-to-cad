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
        layers = {L['name']: L for L in dlg._layers}
        hidden = set(dlg.hidden_names())
        # Los estilos excluidos del reconocimiento siguen dibujados en el PDF;
        # las capas OCG apagadas sí desaparecen y no deben interceptar clics.
        dlg._view_auto = False
        view = dlg.view
        scene_pos = view.mapToScene(pos)
        camera = view.transform()
        center = view.mapToScene(view.viewport().rect().center())
        if getattr(dlg, '_pick_cache', None) is None:
            with busy(view, _tr("Leyendo las líneas de la hoja…")):
                dlg._pick_drawings()
            # El indicador procesa eventos: un encuadre diferido de Qt no debe
            # cambiar la cámara con la que se pulsó la línea.
            view.setTransform(camera)
            view.centerOn(center)
        if not dlg._pix_item.sceneBoundingRect().contains(scene_pos):
            return
        # Misma lectura recortada que el resaltado: respeta clips, giros y
        # familias especiales (acometidas/símbolos), sin inferir por el color.
        z = dlg._render_zoom()
        matrix = dlg._page.rotation_matrix
        pdf_pos = fitz.Point(scene_pos.x() / z, scene_pos.y() / z) * ~matrix
        scale = max(1e-9, abs(view.transform().m11()))
        radius = self.TOLERANCE / (z * scale)
        screen_pos = QtCore.QPointF(view.mapFromScene(scene_pos))
        best, name, picked = self.TOLERANCE + 1, None, None
        stroker = QtGui.QPainterPathStroker()
        stroker.setCapStyle(QtCore.Qt.RoundCap)
        stroker.setJoinStyle(QtCore.Qt.RoundJoin)
        drawings = dlg._pick_drawings()
        for original, shown in drawings:
            candidate = original.get('layer')
            if candidate in hidden and layers.get(candidate, {}).get('source') != 'style':
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
                best, name, picked = high, candidate, original
        if name is None:
            return
        dlg._mostrar_capa_identificada(name, drawings)
        layers = {L['name']: L for L in dlg._layers}
        items = dlg._items_by_name.get(name, ())
        if not items:
            return
        # Una capa compartida por varias redes se identifica por la línea
        # pulsada, igual que en la leyenda por letras (G-XREF, por ejemplo).
        from reconocimiento import recognition_letters
        from ui.asistente.layer_dialog import _ROLE_UTILITY
        utility = (layers[name].get('letter_paths') or {}).get(recognition_letters.path_key(picked))
        item = next((it for it in items if it.data(0, _ROLE_UTILITY) == utility), items[0])
        # Un filtro previo no debe impedir encontrar la familia pulsada.
        if item.isHidden():
            dlg.search.clear()
        item.parent().setExpanded(True)
        # Evitar el encuadre automático del clic en el árbol: al buscar desde
        # el plano se conserva exactamente la cámara del usuario.
        blocker = QtCore.QSignalBlocker(dlg.tree)
        dlg.tree.setCurrentItem(item)
        del blocker
        dlg._assignment_selection_changed(item)
        dlg.tree.scrollToItem(item, QtWidgets.QAbstractItemView.EnsureVisible)
        spec = {'layers': [name], 'identificar': True}
        if utility:
            spec['path_utility'] = utility
        dlg._focus_lines(spec, fit=False)
