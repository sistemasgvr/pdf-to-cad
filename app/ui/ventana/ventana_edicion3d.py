"""Editar desde la Vista 3D las cotas y el diámetro de una utilidad (mezcla de `Main`; pedido del usuario
2026-10-20: «desde la vista 3D debe permitirme cambiar cotas por tramo, cota inicial, final y diámetro… y
que se actualice en la vista 2D también»).

Es EL MISMO dato que edita el panel del plano, con el mismo criterio:
  • rasante inicial / final = `inv_start` / `inv_end` (inicio del 1.er tramo y fin del último);
  • el inicio de un tramo intermedio = cota de SALIDA de su vértice (`vertex_inv_out`) y el fin = cota de
    LLEGADA (`vertex_inv_in`), independientes como en la tabla «Cotas por tramo»; antes de cambiar una se
    congelan las demás (`model_ops.snapshot_seg_values`: si no, las interpoladas se correrían) y la
    utilidad queda con la edición por tramo ACTIVADA (lo que hace el botón del plano), todo en UN paso de
    deshacer;
  • el diámetro, por el desplegable del panel (`prop_size` → `_prop_changed`): mismas opciones (familia y
    catálogo, o diámetros sin familia) y mismo efecto.
Después se refresca el panel del plano (si muestra esa utilidad) y se redibuja: el plano y la Vista 3D
quedan al día. Ctrl+Z lo deshace."""
from __future__ import annotations

import copy
import math

from nucleo import edicion3d, model_ops
from nucleo.model import TAB_PIPE


class Edicion3DMixin:
    def _ft_por_px(self):
        return self.scale / self.zoom if self.scale and self.zoom else 0.0

    def cotas_para_3d(self, i):
        """[(z inicio, z fin, largo en planta ft)] de cada tramo de la utilidad `i` (lo que muestra la tabla
        del plano)."""
        p = self.pipes[i]
        pts = p.get("pts") or []
        ft = self._ft_por_px()
        out = []
        for k in range(len(pts) - 1):
            zz = model_ops.cotas_tramo(p, k) or (0.0, 0.0)
            out.append((float(zz[0]), float(zz[1]), math.dist(pts[k], pts[k + 1]) * ft))
        return out

    def editar_cota_3d(self, i, tramo, lado, valor):
        """Cambia la cota del `lado` («inicio»/«fin») del `tramo` de la utilidad `i`. Devuelve True si cambió."""
        return self.editar_cotas_3d(i, [(tramo, lado, valor)])

    def editar_cotas_3d(self, i, cambios):
        """Varias cotas de la utilidad `i` en UN paso de deshacer: `cambios` = [(tramo, lado, valor)]
        (`nucleo/edicion3d.aplicar_cota`). Devuelve True si algo cambió."""
        if not (0 <= i < len(self.pipes)):
            return False
        prueba = copy.deepcopy(self.pipes[i])
        if not any([edicion3d.aplicar_cota(prueba, t, lado, v) for t, lado, v in cambios]):
            return False
        self._push()
        for t, lado, v in cambios:
            edicion3d.aplicar_cota(self.pipes[i], t, lado, v)
        self._tras_editar_3d(i)
        return True

    def opciones_diametro_3d(self, i):
        """([(texto, dato)], índice actual, se puede cambiar) del diámetro de la utilidad `i`: las del panel."""
        if not self._mostrar_en_panel(i):
            return [], -1, False
        cb = self.prop_size
        usable = cb.isVisibleTo(self.gprop) and cb.isEnabled()
        return [(cb.itemText(k), cb.itemData(k)) for k in range(cb.count())], cb.currentIndex(), usable

    def editar_diametro_3d(self, i, dato):
        """Elige `dato` en el desplegable de diámetro del panel (el mismo cambio que hacerlo en el plano)."""
        if not self._mostrar_en_panel(i):
            return False
        cb = self.prop_size
        k = cb.findData(dato)
        if k < 0 or k == cb.currentIndex() or not (cb.isVisibleTo(self.gprop) and cb.isEnabled()):
            return False
        cb.setCurrentIndex(k)                        # → _prop_changed: push, panel, lista y redibujo
        return True

    def _mostrar_en_panel(self, i):
        """El panel del plano con la utilidad `i` (la elige si no lo estaba, sin traer la ventana al frente)."""
        if not (0 <= i < len(self.pipes)):
            return False
        if self.sel_pipe != i or self._current_tab() != TAB_PIPE:
            pts = self.pipes[i]["pts"]
            self._ir_a_elemento(pts[len(pts) // 2][0], pts[len(pts) // 2][1], "pipe", i, activar=False)
        return self.sel_pipe == i

    def _tras_editar_3d(self, i):
        """Panel del plano al día (si muestra esa utilidad) y redibujo (que también pone al día la 3D)."""
        if self.sel_pipe == i and self._current_tab() == TAB_PIPE:
            p = self.pipes[i]
            self._prop_guard = True
            self.prop_inv0.setValue(p.get("inv_start") or 0.0)
            self.prop_inv1.setValue(p.get("inv_end") or 0.0)
            self._prop_guard = False
            self._rebuild_seg_inv_table(p)
        self._redraw()
