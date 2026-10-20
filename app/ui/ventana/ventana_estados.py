"""Volver a un estado del modelo ya dibujado (deshacer / rehacer) sin rearmar su dibujo (pedido del usuario
2026-10-19: con 16 761 utilidades deshacer tardaba ~2 s, casi todo en volver a armar las ~54 mil marcas, la
capa de líneas y los resultados de cruces y avisos que ese mismo estado ya había tenido).

Se recuerdan los `MAX_ESTADOS` estados anteriores, cada uno con la MISMA clave que decide si lo de la ventana
sigue valiendo (firma del modelo y lo que se muestra): el grupo de capas de marcas (con el globo de cada marca,
porque las marcas iguales se comparten entre redibujos y el redibujo siguiente les pone el suyo), la capa de
líneas y los resultados de `_draw_pipe_conflicts` / `_draw_accesorios`. Volver a esa clave = lo mismo que se
había dibujado con ella. Los avisos de normativa se vuelven a marcar con sus aprobaciones (`marcar`): aprobar
o quitar una aprobación cambia esos mismos objetos.
"""
from __future__ import annotations

from collections import OrderedDict

MAX_ESTADOS = 2


class EstadosPreviosMixin:
    def _recuerdos(self, nombre):
        d = getattr(self, nombre, None)
        if d is None:
            d = OrderedDict()
            setattr(self, nombre, d)
        return d

    def _recordar(self, nombre, clave, valor, maximo=MAX_ESTADOS):
        d = self._recuerdos(nombre)
        d[clave] = valor
        d.move_to_end(clave)
        while len(d) > maximo:
            d.popitem(last=False)

    def _recuerdo(self, nombre, clave, sacar=False):
        d = self._recuerdos(nombre)
        if clave not in d:
            return None
        return d.pop(clave) if sacar else d[clave]

    # ── marcas ────────────────────────────────────────────────────────────
    def _guardar_grupo_marcas(self, grupo, sc):
        """El grupo de marcas que se va a reemplazar, con el globo de cada marca (antes de que el redibujo
        nuevo les ponga el suyo)."""
        firma = getattr(grupo, "firma", None)
        if grupo is None or firma is None or firma[0] is None or not grupo.vivo(sc):
            return
        marcas = grupo.todas()                           # (globos en lista de textos: una lista de tuplas
        grupo._globos = (marcas, [it.toolTip() for it in marcas])   # de 54 mil disparaba el recolector)
        self._recordar("_grupos_previos", firma, grupo)

    def _revivir_grupo_marcas(self, firma_m, sc):
        """El grupo guardado para `firma_m`, otra vez en la escena con sus globos, o None."""
        if firma_m[0] is None:
            return None
        grupo = self._recuerdo("_grupos_previos", firma_m, sacar=True)
        if grupo is None or grupo.scene is not sc:
            return None
        try:
            for c in grupo.capas.values():
                if c.scene() is not None and c.scene() is not sc:
                    return None
        except RuntimeError:                             # la escena se vació: ya no existen
            return None
        marcas, globos = getattr(grupo, "_globos", ((), ()))
        for it, globo in zip(marcas, globos):
            it.setToolTip(globo)
        for c in grupo.capas.values():
            if c.scene() is None:
                sc.addItem(c)
        return grupo

    # ── capa de líneas ────────────────────────────────────────────────────
    def _guardar_capa_lineas(self, capa_prev, sc):
        if capa_prev is None or capa_prev[0][0] is None:
            return
        try:
            if capa_prev[1].scene() is not sc:
                return
        except RuntimeError:
            return
        self._recordar("_capas_lineas_previas", capa_prev[0], capa_prev)

    def _revivir_capa_lineas(self, clave_capa, sc):
        if clave_capa[0] is None:
            return None
        guardada = self._recuerdo("_capas_lineas_previas", clave_capa, sacar=True)
        if guardada is None:
            return None
        try:
            if guardada[1].scene() not in (None, sc):
                return None
        except RuntimeError:
            return None
        return guardada

    # ── resultados ────────────────────────────────────────────────────────
    def _resultados_previos(self, nombre, clave):
        """Resultado guardado con `clave` (el último o uno de los estados anteriores), o None."""
        return self._recuerdo(nombre, clave)

    def _guardar_resultados(self, nombre, clave, valor):
        self._recordar(nombre, clave, valor, maximo=MAX_ESTADOS + 1)
