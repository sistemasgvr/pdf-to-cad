"""UNA barra para toda la exportación a DXF (pedido del usuario 2026-10-20: «un loader preciso, igual que
el de la Vista 3D», con el mapa de 16 761 utilidades la exportación tarda minutos).

La exportación pasa por varias etapas en hilos distintos: digitalizar el PDF (`PipelineWorker`), leer el
plano ya digitalizado (`en_hilo`), medir su recuadro, agregar las utilidades (hilo de la ventana) y guardar
el DXF (`en_hilo`). Cada una avisa por `nucleo.avance` con una CLAVE de etapa y, si la tiene, «i de n»
(trazos, bytes, entidades, utilidades); aquí cada clave pesa su costo estimado (`nucleo.avance_pesado.
Barra`: unidades × ms medidos con AGUA 2) y la capa «Cargando…» de la ventana muestra la etapa, el % y la
barra. Una etapa SIN «i de n» (leer los trazos del PDF, unir las líneas…) avanza sola según lo que se
estima que tarda, hasta el 90 % de su parte, y salta al terminar: la barra nunca se queda quieta ni
retrocede.
"""
from __future__ import annotations

from traduccion.i18n_core import N_
from ui.comun.barra_pesada import AvancePesado

# ms por unidad (medido 2026-10-20: AGUA 2 = 497 601 trazos del PDF, 597 634 entidades, 139 MB, 16 762
# utilidades; DU06 h.3 = 24 839 trazos da lo mismo por trazo)
MS_POR_TRAZO = {"trazos": 0.017, "escala": 0.017, "zonas": 0.010, "procesar": 0.012, "unir": 0.028,
                "textos": 0.022, "otros": 0.002, "guardar_base": 0.034, "validar": 0.001}
MS_RASTER = 5000.0                     # una hoja escaneada
MS_POR_BYTE_LEER = 0.00013             # leer el DXF base (1.ª mitad)…
MS_POR_ENTIDAD_ARMAR = 0.028           # …y armar sus entidades (2.ª mitad)
MS_POR_ENTIDAD_ENCUADRE = 0.069        # medir el recuadro del plano (la 1.ª vez)
MS_POR_ENTIDAD_GUARDAR = 0.028
MS_POR_UTILIDAD = 0.25                 # agregar utilidades, leaders, estructuras…
ENTIDADES_POR_TRAZO = 1.2
BYTES_POR_ENTIDAD = 233
TRAZOS_SUPUESTOS = 50_000              # hasta saber cuántos trazos tiene la hoja

TEXTOS = {
    "trazos": N_("Leyendo los trazos del PDF…"),
    "raster": N_("Digitalizando la imagen del plano…"),
    "escala": N_("Leyendo la escala del plano…"),
    "zonas": N_("Buscando el cajetín y las leyendas…"),
    "procesar": N_("Clasificando los trazos: {i} de {n}"),
    "unir": N_("Uniendo las líneas…"),
    "textos": N_("Pasando los textos…"),
    "otros": N_("Terminando el plano…"),
    "guardar_base": N_("Guardando el plano digitalizado: {i} de {n} entidades"),
    "validar": N_("Revisando el plano digitalizado…"),
    "leer": N_("Leyendo el plano digitalizado…"),
    "armar": N_("Armando el plano: {i} de {n} entidades"),
    "encuadre": N_("Midiendo el plano para encuadrarlo: {i} de {n} entidades"),
    "fusionar": N_("Agregando las utilidades: {i} de {n}"),
    "guardar": N_("Guardando el DXF: {i} de {n} entidades"),
}


def costos(digitalizar=False, leer_bytes=0, entidades=None, utilidades=0, medir=True):
    """Costo estimado (ms) de cada parte de esta exportación."""
    c = {}
    if digitalizar:
        c.update({k: TRAZOS_SUPUESTOS * ms for k, ms in MS_POR_TRAZO.items()})
        entidades = entidades if entidades is not None else TRAZOS_SUPUESTOS * ENTIDADES_POR_TRAZO
    if leer_bytes:
        c["leer"] = leer_bytes * MS_POR_BYTE_LEER
        entidades = entidades if entidades is not None else leer_bytes / BYTES_POR_ENTIDAD
        c["armar"] = entidades * MS_POR_ENTIDAD_ARMAR
    entidades = entidades or 0
    c["encuadre"] = entidades * MS_POR_ENTIDAD_ENCUADRE if medir else 0.0
    c["fusionar"] = utilidades * MS_POR_UTILIDAD
    c["guardar"] = (entidades + utilidades * 2) * MS_POR_ENTIDAD_GUARDAR
    return c


class AvanceExportacion(AvancePesado):
    """La barra de UNA exportación (`ui/comun/barra_pesada`): `abrir`, los avisos (`recibir`, o `escuchar()`
    para lo que corre en el hilo de la ventana), `entidades(n)` cuando se sabe y `cerrar` (siempre)."""

    def __init__(self, win, partes):
        super().__init__(win, partes, TEXTOS)
        self.win = win
        self.fase_digitalizar = "trazos" in partes

    # ── estimaciones ──
    def trazos(self, n):
        cambios = {k: n * ms for k, ms in MS_POR_TRAZO.items() if k in self.barra.costos}
        cambios.update(self._por_entidades(n * ENTIDADES_POR_TRAZO))
        self.barra.costos_nuevos(cambios)

    def entidades(self, n):
        self.barra.costos_nuevos(self._por_entidades(n))

    def _por_entidades(self, n):
        utilidades = self.barra.costos.get("fusionar", 0.0) / MS_POR_UTILIDAD
        c = {"guardar": (n + utilidades * 2) * MS_POR_ENTIDAD_GUARDAR}
        if self.barra.costos.get("encuadre"):
            c["encuadre"] = n * MS_POR_ENTIDAD_ENCUADRE
        if "armar" in self.barra.costos and self.barra.hecho.get("armar", 0.0) == 0.0:
            c["armar"] = n * MS_POR_ENTIDAD_ARMAR
        return c

    def fin_digitalizar(self):
        self.fase_digitalizar = False
        self.terminada(*MS_POR_TRAZO, "raster")

    # ── avisos ──
    def clave(self, etapa):
        return "guardar_base" if etapa == "guardar" and self.fase_digitalizar else etapa

    def _al_recibir(self, etapa, i, n):
        if etapa == "trazos" and i:
            self.trazos(i)
