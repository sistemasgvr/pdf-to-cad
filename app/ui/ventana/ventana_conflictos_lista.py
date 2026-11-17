"""Conflictos NUMERADOS de `Main` (mezcla): al final de `_draw_pipe_conflicts` se juntan
los cruces a la misma cota que el plugin no une y todas las alertas rojas en una lista
`self._conflictos` (`nucleo/conflictos.py`: conflictos C-1, C-2… cuando dos o más tuberías se tocan y
observaciones OC-1, OU-1, OG-1, OV-1… para lo demás) y se dibuja su número junto a cada marca. La misma lista va a la Tabla de datos, a su Excel y a la Vista 3D."""
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
        # Números FIJOS (2026-10-29): cada conflicto conserva el suyo; uno resuelto queda «resuelto» en el registro
        # y los demás no se renumeran.
        if getattr(self, "_conf_registro", None) is None:
            self._conf_registro = _conf.Registro()
        self._conflictos = _conf.numerar_fijo(items, self._conf_registro)
        self._avisar_panel_conflictos()
        from ui.comun import conflictos_view
        if not getattr(self, "_marcas_vigentes", False):  # si no, las mismas de antes siguen en su capa
            self._poner_marcas(conflictos_view.dibujar_iter(self.canvas.scene(), self._conflictos, poner=self._marca,
                                                            capa_de=self._capa_de_utilidad),
                               len(self._conflictos))
        return self._conflictos

    def _avisar_panel_conflictos(self):
        """El panel «Conflictos», si ya existe, al día (rehace su lista solo si cambió)."""
        dlg = getattr(self, "_dlg_soluciones", None)
        if dlg is not None:
            from PySide6 import QtCore
            QtCore.QTimer.singleShot(0, dlg, dlg.al_cambiar_conflictos)

    def _soltar_conflictos(self):
        """Otro proyecto (reporte 2026-11-14: tras uno muy grande, el panel Resolver seguía con sus 5 729 conflictos):
        los conflictos, sus resultados, el círculo que marca un lugar y el panel quedan vacíos hasta el primer
        redibujo del proyecto nuevo."""
        from ui.ventana.ventana_conflictos import _RESULTADOS_CONFLICTOS
        for k in _RESULTADOS_CONFLICTOS:
            setattr(self, k, [])
        self._conf_registro = None
        if hasattr(self, "_quitar_marca_lugar"):
            self._quitar_marca_lugar()
        dlg = getattr(self, "_dlg_soluciones", None)
        if dlg is not None:
            dlg.proyecto_cambiado()

    def codigos_avisos(self, avisos=None):
        """{id(aviso): «N-n» / «R-n»} FIJOS (2026-11-14): el mismo registro que los conflictos (`.digproj`), así
        resolver un aviso no renumera los demás en el informe, la IA ni la Tabla de datos."""
        if getattr(self, "_conf_registro", None) is None:
            self._conf_registro = _conf.Registro()
        avisos = getattr(self, "_normas_avisos", None) or [] if avisos is None else avisos
        from nucleo.informe_datos import CLASE_RECONOCIMIENTO
        return _conf.numerar_avisos(avisos, self._conf_registro, CLASE_RECONOCIMIENTO)

    def conflictos_resueltos(self):
        """Conflictos y observaciones que ya no están en el dibujo, con su número: [(«C-n» / «OC-n»…, título)]."""
        reg = getattr(self, "_conf_registro", None)
        if reg is None:
            return []
        vigentes = {c.id for c in getattr(self, "_conflictos", None) or []}
        return [(reg.codigo(e), _conf.TITULOS.get(e["clave"], e["clave"])) for e in reg.resueltos()
                if reg.codigo(e) not in vigentes]
