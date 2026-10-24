"""Avance de `modelo3d.construir` en UNA barra que sigue al trabajo real (PURO; pedido del usuario
2026-10-20: con 16 762 utilidades la Vista 3D tardaba ~30 s en armarse y parecía colgada).

Cada parte pesa lo que tarda: unidades × costo por unidad (medido con «PRUEBA AGUA 2»: buscar los
accesorios ~0.17 ms por utilidad, armar cada accesorio ~0.85 ms, cada utilidad ~0.52 ms; los buzones
casi nada; juntar y centrar las mallas al final ~8 % del total). La cantidad de accesorios solo se sabe
después de buscarlos: hasta entonces se estima y luego se corrige; la barra nunca retrocede.

Avisa por `nucleo.avance` (la ventana lo escucha en el hilo que arma la escena) con
`avisar(texto, milesimas, 1000)`, como mucho cada `CADA_S` (y siempre al cambiar de parte).
"""
from __future__ import annotations

import time

from nucleo import avance
from nucleo.avance_pesado import Barra
from traduccion.i18n_core import N_, t as _tr

MS_BUSCAR = 0.17            # por utilidad visible: buscar dónde van los accesorios
MS_ACCESORIO = 0.85         # por accesorio
MS_UTILIDAD = 0.52          # por utilidad
MS_ESTRUCTURA = 0.3         # por buzón / caja
ACC_POR_UTILIDAD = 1.2      # estimación de accesorios por utilidad mientras no se sabe
FIN = 0.08                  # parte final: juntar y centrar las mallas
CADA_S = 0.1

TEXTOS = {
    "buscar": N_("Buscando los accesorios: {i} de {n} utilidades"),
    "accesorios": N_("Armando los accesorios: {i} de {n}"),
    "utilidades": N_("Armando las utilidades: {i} de {n}"),
    "estructuras": N_("Armando los buzones y cajas: {i} de {n}"),
}


class Avance3D(Barra):
    """`avance_pesado.Barra` con las partes de `construir` y la parte final (`FIN` del total)."""

    def __init__(self, n_utilidades, n_estructuras, accesorios=True, estructuras=True):
        super().__init__({
            "buscar": n_utilidades * MS_BUSCAR,
            "accesorios": n_utilidades * ACC_POR_UTILIDAD * MS_ACCESORIO if accesorios else 0.0,
            "utilidades": n_utilidades * MS_UTILIDAD,
            "estructuras": n_estructuras * MS_ESTRUCTURA if estructuras else 0.0,
        })
        self._fin()
        self._parte = None
        self._cuando = 0.0

    def _fin(self, cambios=None):
        costos = dict(self.costos, **(cambios or {}))
        resto = sum(c for k, c in costos.items() if k != "fin")
        self.costos_nuevos(dict(cambios or {}, fin=resto * FIN / (1.0 - FIN)))   # juntos: la barra no se traba

    def accesorios_hallados(self, n):
        """Ya se sabe cuántos accesorios hay: la parte pesa lo real."""
        if self.costos["accesorios"]:
            self._fin({"accesorios": n * MS_ACCESORIO})

    def paso(self, parte, i, n):
        """Van `i` de `n` unidades de `parte`."""
        self.parte(parte, i / n if n else 1.0)
        ahora = time.perf_counter()
        if parte == self._parte and ahora - self._cuando < CADA_S and i < n:
            return
        self._parte, self._cuando = parte, ahora
        avance.avisar(_tr(TEXTOS[parte]).format(i=i, n=n), self.milesimas, 1000)

    def terminando(self):
        for k in self.costos:
            if k != "fin":
                self.lista(k)
        self._parte = None
        avance.avisar(_tr("Terminando la escena…"), self.milesimas, 1000)
