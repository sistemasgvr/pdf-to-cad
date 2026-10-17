"""Vértices de eléctrico y telecom: verlos, elegirlos y convertirlos en curva (pedidos 2026-10-15/16).

En las redes de conductos no hay caja automática en cada vértice, así que sus vértices no
se veían y no había cómo hacer una curva en uno. Con la utilidad seleccionada, sus vértices
interiores libres se ven como puntos. Dos caminos (`nucleo.vertice_curva`):
  · clic derecho sobre uno → «Convertir este vértice en curva»;
  · clic sobre uno → queda ELEGIDO (resaltado) y el panel de Utilidades muestra «Cambiar a
    curva» (`box_vertice`).
Clase mezcla de `Main` (app_window.py), como las demás.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import vertice_curva
from ui.comun import marcas_lienzo as ML

TOL_VERTICE_PX = 10.0          # px de PANTALLA para tomar un vértice con el clic


class VerticesMixin:
    def _vertices_libres(self, p):
        """Dibuja los vértices interiores libres de la utilidad de conductos seleccionada
        (el elegido, más grande y relleno del color de la utilidad)."""
        sc = self.canvas.scene()
        col = layer_qcolor(p.get("layer"))
        pen = QtGui.QPen(col, 1.6); pen.setCosmetic(True)
        relleno = QtGui.QColor(255, 255, 255, 230)
        elegido = self._vertice_elegido()
        for k in vertice_curva.vertices_libres(p, self.structures):
            x, y = p["pts"][k]
            if elegido is not None and elegido[1] == k:
                borde = QtGui.QPen(QtGui.QColor(255, 255, 255), 2.0); borde.setCosmetic(True)
                self._overlay.append(ML.agregar(sc, x, y, 7, borde, col, Z_MARK + 2, tope_px=ML.TOPE_PX))
            else:
                self._overlay.append(ML.agregar(sc, x, y, 4, pen, relleno, Z_MARK + 1, tope_px=ML.TOPE_PX * 0.6))

    def _vertice_libre_en(self, x, y):
        """(utilidad, vértice) libre de la utilidad seleccionada bajo el cursor, o None."""
        if not (0 <= self.sel_pipe < len(self.pipes)):
            return None
        p = self.pipes[self.sel_pipe]
        thr = TOL_VERTICE_PX / max(1e-6, self.canvas.transform().m11())
        k = vertice_curva.vertice_en(p, self.structures, x, y, thr)
        return None if k is None else (self.sel_pipe, k)

    def _vertice_bajo_clic(self, x, y):
        """Vértice libre de eléctrico/telecom bajo el clic: primero el de la utilidad
        seleccionada, si no el de cualquier otra. (utilidad, vértice) o None."""
        hit = self._vertice_libre_en(x, y)
        if hit is not None:
            return hit
        thr = TOL_VERTICE_PX / max(1e-6, self.canvas.transform().m11())
        for i in self._utilidades_cerca(x, y, thr):     # solo las que tienen un tramo cerca
            p = self.pipes[i]
            if i != self.sel_pipe and vertice_curva.es_conductos(p):
                k = vertice_curva.vertice_en(p, self.structures, x, y, thr)
                if k is not None:
                    return i, k
        return None

    def _elegir_vertice(self, i, k):
        """Clic sobre un vértice libre: elige su utilidad y ese vértice (panel → «Cambiar a curva»)."""
        if self.sel_pipe != i or self._current_tab() != TAB_PIPE:
            self._no_center = True
            try:
                self._show_tab(TAB_PIPE)
                self.pipe_list.clearSelection(); self.pipe_list.setCurrentRow(i)
            finally:
                self._no_center = False
        self._vertice_sel = (i, k)
        self._update_ui(); self._redraw()
        self._info(_tr("Vértice {k} elegido: «Cambiar a curva» en el panel (o clic derecho sobre él).").format(k=k + 1))

    def _vertice_elegido(self):
        """(utilidad, vértice) elegido si sigue siendo válido (misma utilidad y vértice libre)."""
        v = getattr(self, "_vertice_sel", None)
        if not v or v[0] != self.sel_pipe or not (0 <= v[0] < len(self.pipes)):
            return None
        return v if v[1] in vertice_curva.vertices_libres(self.pipes[v[0]], self.structures) else None

    def _sync_vertice_panel(self):
        box = getattr(self, "box_vertice", None)
        if box is None:
            return
        v = self._vertice_elegido() if self._current_tab() == TAB_PIPE else None
        if v is not None:
            self.lbl_vertice.setText(_tr("Vértice {k} de esta utilidad").format(k=v[1] + 1))
        box.setVisible(v is not None)

    def _cambiar_vertice_a_curva(self):
        v = self._vertice_elegido()
        if v is not None:
            self._vertice_sel = None
            self.convertir_vertice_en_curva(*v)

    def _menu_vertice(self, menu, x, y):
        """Clic derecho sobre un vértice libre de eléctrico/telecom: «Convertir este vértice en curva»."""
        hit = self._vertice_libre_en(x, y)
        if hit is None:
            return
        self._menu_act(menu, _tr("Convertir este vértice en curva"), lambda: self.convertir_vertice_en_curva(*hit))
        menu.addSeparator()

    def convertir_vertice_en_curva(self, i, k):
        """El vértice k de la utilidad i pasa a curva (radio automático) y queda elegida en Curvas."""
        if not (0 <= i < len(self.pipes)) or k not in vertice_curva.vertices_libres(self.pipes[i], self.structures):
            return
        self._push()
        self._vertice_sel = None
        x0, y0 = self.pipes[i]["pts"][k]
        vertice_curva.a_curva(self.structures, self.pipes[i], k)
        self._rebuild_structures()
        self._refresh_lists()
        idx = next((j for j, s in enumerate(self.structures) if s.get("curve")
                    and s.get("x") == float(x0) and s.get("y") == float(y0)), -1)
        if idx in self._curve_rows:
            self._no_center = True
            try:
                self._show_tab(TAB_CURVE)
                self.curve_list.setCurrentRow(self._curve_rows.index(idx))
            finally:
                self._no_center = False
        self._redraw()
        self._info(_tr("Vértice convertido en curva {cod} (radio automático: cámbialo en el panel).").format(
            cod=self.structures[idx].get("cod", "") if idx >= 0 else ""))

    def _quitar_curva_de_vertice(self, idx):
        """La curva de un vértice simple se borra: vuelve a ser un vértice (sin caja inventada)."""
        self._push()
        self.structures.pop(idx)
        self.sel_curve = -1
        self._refresh_lists()
        self._redraw()
        self._info(_tr("Curva quitada: vuelve a ser un vértice simple."))
