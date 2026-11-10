"""Terreno (superficie del suelo) del proyecto, PURO (2026-11-08, pedido del usuario: «por el momento no tenemos
terrenos… trabajamos en la cota 0… deja una variable para adaptarlo a futuro»).

Hoy el proyecto no tiene superficie: se supone el suelo PLANO en la cota 0 (`COTA_SIN_TERRENO`). Todo lo que
necesita saber dónde está el suelo pregunta aquí (`cota_en`), así que cuando haya terreno de verdad solo cambia
`ACTUAL` por otro `Terreno`: puntos, TIN o una superficie importada, como la Surface de Civil 3D (que da la
cota en un punto de planta, o nada fuera de su borde).

Hoy lo usan: la caja de la válvula (`valvulas.caja`: llega hasta el suelo), y con ella el perfil, la Vista 3D y
el DXF (`CAJA_TOPE_Z`). Las coordenadas son las del PLANO de la app (px de la hoja); un terreno real tendrá que
convertirlas (escala/georreferencia) a las suyas.
"""
from __future__ import annotations

COTA_SIN_TERRENO = 0.0           # ft: el «suelo» supuesto mientras no haya superficie


class Terreno:
    """Interfaz de una superficie: la cota (ft) del suelo en un punto del plano, o None si ahí no hay datos."""

    nombre = ""

    def cota(self, x, y):
        return None


class TerrenoPlano(Terreno):
    """Suelo horizontal a una cota fija (hoy, la cota 0)."""

    def __init__(self, z=COTA_SIN_TERRENO, nombre="Plano (cota 0)"):
        self.z = float(z)
        self.nombre = nombre

    def cota(self, x, y):
        return self.z


ACTUAL = TerrenoPlano()           # el terreno del proyecto; reemplazarlo con `usar(...)`


def usar(terreno):
    """Cambia el terreno del proyecto (None = vuelve al plano en la cota 0). Devuelve el anterior."""
    global ACTUAL
    anterior = ACTUAL
    ACTUAL = terreno if terreno is not None else TerrenoPlano()
    return anterior


def cota_en(x=None, y=None, terreno=None):
    """Cota del suelo (ft) en el punto (x, y) del plano. Sin datos ahí (o sin punto), la del terreno supuesto."""
    t = terreno if terreno is not None else ACTUAL
    z = t.cota(x, y) if x is not None and y is not None else None
    if z is None:
        z = getattr(t, "z", COTA_SIN_TERRENO)
    return float(z)
