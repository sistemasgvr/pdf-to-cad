"""Copiloto: conflictos en tanda. La app prueba la solución de cada uno; el usuario marca cuáles aplicar.

Resolver un conflicto suele cambiar la cota de una red existente: la app prueba que queda limpio, no que la tubería esté
a esa cota. Por eso nada viene marcado. Antes de aplicar cada una se vuelve a probar sobre lo ya cambiado.
"""
from __future__ import annotations

from dataclasses import dataclass

from nucleo import bitacora, soluciones
from traduccion.i18n import t as _tr
from ui.ventana.ventana_copiloto import CADUCADO
from ui.ventana.ventana_soluciones import _cerca, _es


@dataclass
class Fila:
    c: object                                         # el conflicto
    prop: object = None                               # la mejor solución limpia, o None
    motivo: str = ""                                  # por qué no lleva casilla


class ConflictosTandaMixin:
    def copiloto_probar_conflictos(self, al_paso=None, al_terminar=None):
        """Prueba cada conflicto, uno por vuelta del bucle de eventos: `al_terminar(filas, error)`."""
        from ui.comun.trabajo_pasos import TrabajoPasos
        self._resultados_al_dia()
        ids = [c.id for c in getattr(self, "_conflictos", None) or []]

        def pasos():
            filas = []
            for k, cid in enumerate(ids):
                if al_paso is not None:
                    al_paso(k, len(ids))
                fila = self._copiloto_fila(cid)
                if fila is not None:                   # ya no está: el usuario editó mientras se probaba
                    filas.append(fila)
                yield
            return filas
        return TrabajoPasos(self, pasos(), al_terminar=al_terminar).empezar()

    def _copiloto_fila(self, cid):
        c, props = self.soluciones_de(cid)
        if c is None:
            return None
        if self.accesorio_de_conflicto(cid) is not None:
            return Fila(c, None, _tr("Lo causa un accesorio: solo tú sabes si existe."))
        p = next((x for x in props if x.valida), None)
        return Fila(c, p, "" if p else _tr("Sin una solución automática limpia."))

    def _copiloto_sigue_conflicto(self, c, prop):
        """Tras `_validar_propuesta`: ¿el conflicto seguía ahí antes de esta propuesta?"""
        objetivo = (c.clave if c.clave != "redes" else "cruce", frozenset(i for i in c.pipes or [] if i is not None))
        return any(_es(f, objetivo, c) or (f[0] == "redes" and _cerca(f, c))
                   for antes in self._sol_antes.values() for f in antes)

    def copiloto_aplicar_conflictos(self, filas, firma, sesion):
        """(aplicadas, [(fila, motivo)] saltadas) en un paso de deshacer; ([], `CADUCADO`) si el proyecto cambió."""
        if not self._copiloto_vigente(firma, sesion):
            return [], CADUCADO
        aplicadas, saltadas, con_paso = [], [], False
        try:
            for f in filas:
                self._sol_antes = {}
                self._validar_propuesta(f.c, f.prop)
                if not self._copiloto_sigue_conflicto(f.c, f.prop):
                    saltadas.append((f, _tr("Ya se resolvió con otra de esta tanda.")))
                elif not f.prop.valida:
                    saltadas.append((f, _tr("Dejó de quedar limpia tras los cambios anteriores.")))
                else:
                    if not con_paso:
                        self._push()
                        con_paso = True
                    soluciones.aplicar(self.pipes, f.prop)
                    aplicadas.append(f)
        except Exception:
            if con_paso:                               # no quedan cambios a medias
                self._restore(self._undo.pop())
            raise
        if aplicadas:
            bitacora.agregar(self.bitacora, "conflictos", _tr("{n} conflicto(s) resuelto(s)").format(n=len(aplicadas)),
                             [dict(codigo=f.prop.codigo, antes=f.c.id, despues=f.prop.texto,
                                   por_que=_tr("La app lo probó: queda limpio."), evidencia=f.c.mensaje or "")
                              for f in aplicadas], paso=len(self._undo))
            self._tras_editar_3d(aplicadas[-1].prop.pipe)
        return aplicadas, saltadas
