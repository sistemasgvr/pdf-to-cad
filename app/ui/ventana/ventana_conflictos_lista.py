"""Conflictos NUMERADOS de `Main` (mezcla): al final de `_draw_pipe_conflicts` se juntan
los cruces a la misma cota que el plugin no une y todas las alertas rojas en una lista
`self._conflictos` (C-1, C-2…, `nucleo/conflictos.py`) y se dibuja su número junto a cada
marca. La misma lista va a la Tabla de datos, a su Excel y a la Vista 3D."""
from __future__ import annotations

from nucleo import conflictos as _conf
from traduccion.i18n import t as _tr


class ConflictosListaMixin:
    def _numerar_conflictos(self):
        items = []
        for (cx, cy, ia, ib, _ka, _kb, za, zb, estado) in getattr(self, "_conflict_hits", []) or []:
            if estado != "conflicto" or self._union_civil(ia, ib, cx, cy, za, zb):
                continue                                 # sugerencia / aprobada / el plugin las une
            a, b = self._etq(self.pipes[ia]), self._etq(self.pipes[ib])
            if za is not None and zb is not None:
                msg = _tr("«{a}» y «{b}» se cruzan a la misma cota ({za:.2f} / {zb:.2f} ft) y no se unen: "
                          "las tuberías chocan. Cambia la cota de una de las dos o corrige el dibujo.").format(
                    a=a, b=b, za=za, zb=zb)
            else:
                msg = _tr("«{a}» y «{b}» se cruzan y a una de las dos le falta la cota: no se puede "
                          "confirmar que pasen a distinta altura.").format(a=a, b=b)
            items.append(dict(clave="cruce", x=cx, y=cy, mensaje=msg, pipes=[ia, ib], cotas=[za, zb]))
        for e in getattr(self, "_exceso_hits", []) or []:
            items.append(dict(clave="exceso", x=e["x"], y=e["y"], mensaje=self._msg_exceso(e)))
        for e in getattr(self, "_escalon_hits", []) or []:
            items.append(dict(clave="escalon", x=e["x"], y=e["y"], mensaje=self._msg_escalon(e),
                              pipes=[e.get("pipe")], cotas=[e.get("z_llega"), e.get("z_sale")]))
        for clave, lista, msg in (("codos", "_codos_hits", self._msg_codos),
                                  ("retorno", "_retorno_hits", self._msg_retorno)):
            for e in getattr(self, lista, []) or []:
                items.append(dict(clave=clave, x=e["x"], y=e["y"], mensaje=msg(e), pipes=[e.get("pipe")]))
        for e in getattr(self, "_pendiente_hits", []) or []:
            items.append(dict(clave="pendiente", x=e["x"], y=e["y"],
                              mensaje=self._msg_sin_espacio(e["ia"], e["ib"], e["r"]), pipes=[e["ia"], e["ib"]]))
        for e in getattr(self, "_inclinada_hits", []) or []:
            items.append(dict(clave="inclinada", x=e["x"], y=e["y"], mensaje=self._msg_inclinada(e)))
        for e in getattr(self, "_redes_hits", []) or []:
            items.append(dict(clave="redes", x=e["x"], y=e["y"], mensaje=self._msg_redes(e)))
        for e in getattr(self, "_choque_hits", []) or []:
            items.append(dict(clave="choque", x=e["x"], y=e["y"], mensaje=self._msg_choque(e),
                              pipes=[e["ia"], e["ib"]], cotas=[e.get("za"), e.get("zb")]))
        self._conflictos = _conf.numerar(items)
        from ui.comun import conflictos_view
        if not getattr(self, "_marcas_vigentes", False):  # si no, las mismas de antes siguen en su capa
            self._overlay += conflictos_view.dibujar(self.canvas.scene(), self._conflictos, poner=self._marca)
        return self._conflictos
