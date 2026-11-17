"""Barra de 0 a 100 % para CUALQUIER carga, sin una tabla de costos por paso (PURO: sin Qt).

Pedido del usuario (2026-11-16): «cada acción, cada carga debe mostrar una barra de 0 a 100 %, pero también a
detalle; si no, el usuario cree que se quedó bugeado». Las barras con costos medidos (`avance_pesado.Barra`)
piden escribir, paso por paso, cuánto tarda cada parte. Esta APRENDE: cada carga anota qué etapas tuvo y cuánto
duró cada una (`Seguidor.cerrar` → perfil) y la vez siguiente la barra reparte el 0–100 % con esos pesos:

  · una etapa que avisa «i de n» avanza con su cuenta REAL (vale aunque el PDF sea mucho más grande que el de la
    vez anterior), y entre un aviso y el siguiente sigue un poco por tiempo: no se queda quieta;
  · una etapa sin cuenta avanza por tiempo según lo que duró la vez anterior, frenando al acercarse a su final;
  · una etapa que la vez anterior no estuvo, o la primera vez de todas (sin perfil), avanza por tiempo cada vez
    más despacio, sin llegar al final.

Nunca retrocede y nunca marca 100 % antes de terminar (`TOPE`). La etapa se reconoce por su texto sin números ni
nombres entre comillas (`clave_de`: «Hoja 3 de 36» y «Hoja 4 de 36» son la misma), o por la `clave` que dé quien
avisa. Quién guarda los perfiles lo decide la interfaz (`ui/comun/tiempos_carga`).
"""
from __future__ import annotations

import math
import re
import time
from typing import Callable, Dict, List, Optional

TOPE = 0.99                 # la barra no marca el final hasta que la carga termina
SIN_PERFIL_TAU_S = 12.0     # sin historia: 63 % de `SIN_PERFIL_TOPE` a los 12 s, y cada vez más despacio
SIN_PERFIL_TOPE = 0.9
FRENO = 0.9                 # etapa sin cuenta: lineal hasta aquí de lo que duró antes; después frena
ENTRE_AVISOS = 0.9          # entre «i de n» y el siguiente, por tiempo, hasta esta parte del paso
DURACION_MIN_S = 0.4        # una carga más corta no se guarda (ni necesita barra)
MAX_ETAPAS = 80
INICIO = "·inicio"

_RX_COMILLAS = re.compile(r"«[^»]*»|\"[^\"]*\"")
_RX_NUMERO = re.compile(r"\d+(?:[.,:]\d+)*")


def clave_de(texto: Optional[str]) -> str:
    """El texto de una etapa sin lo que cambia de una vez a otra (números, nombres entre comillas)."""
    t = _RX_COMILLAS.sub("«»", texto or "")
    t = _RX_NUMERO.sub("#", t)
    return " ".join(t.lower().split())[:160]


def perfil_valido(perfil) -> bool:
    try:
        return (isinstance(perfil, dict) and float(perfil["T"]) > 0 and len(perfil["etapas"]) >= 1
                and all(isinstance(k, str) and float(d) >= 0 for k, d in perfil["etapas"]))
    except (KeyError, TypeError, ValueError):
        return False


class _Etapa:
    __slots__ = ("t", "desde", "i", "n", "cambio")

    def __init__(self):
        self.t = 0.0              # segundos acumulados (sin el tramo abierto)
        self.desde = None         # cuándo se abrió el tramo de ahora
        self.i = self.n = None
        self.cambio = 0.0         # cuándo cambió su «i de n»


class Seguidor:
    """El avance de UNA carga. `etapa(...)` en cada aviso, `fraccion()` al pintar, `cerrar()` al terminar."""

    def __init__(self, perfil: Optional[dict] = None, reloj: Callable[[], float] = time.perf_counter):
        self.reloj = reloj
        self.t0 = reloj()
        self._dur: Dict[str, float] = {}
        self._orden: Dict[str, int] = {}
        if perfil_valido(perfil):
            for k, d in perfil["etapas"]:
                if k not in self._dur:
                    self._orden[k] = len(self._orden)
                self._dur[k] = self._dur.get(k, 0.0) + float(d)
        self._total = sum(self._dur.values())
        self.vistas: Dict[str, _Etapa] = {}
        self._primera: List[str] = []           # orden de aparición en ESTA carga
        self.actual: Optional[str] = None
        self._max = 0.0
        self._base = 0.0                        # de dónde parte una etapa que el perfil no conoce
        self._desde_base = self.t0
        self.etapa(clave=INICIO)

    # ── avisos ──
    def etapa(self, texto: Optional[str] = None, i=None, n=None, clave: Optional[str] = None) -> None:
        k = clave or clave_de(texto)
        if not k:
            return
        ahora = self.reloj()
        if k != self.actual:
            if self.actual is not None:
                self.fraccion()                 # (deja `_max` al día antes de cambiar de etapa)
            self._cerrar_tramo(ahora)
            e = self.vistas.get(k)
            if e is None:
                if len(self.vistas) >= MAX_ETAPAS:
                    k = self._primera[-1]       # demasiadas etapas distintas: la última las junta
                    e = self.vistas[k]
                else:
                    e = self.vistas[k] = _Etapa()
                    self._primera.append(k)
            e.desde = ahora
            e.cambio = ahora
            self.actual = k
            self._base, self._desde_base = self._max, ahora
        e = self.vistas[self.actual]
        try:
            n = int(n) if n else None
            i = max(0, min(int(i or 0), n)) if n else None
        except (TypeError, ValueError):
            i = n = None
        if n and (i, n) != (e.i, e.n):
            e.i, e.n, e.cambio = i, n, ahora

    def _cerrar_tramo(self, ahora: float) -> None:
        e = self.vistas.get(self.actual) if self.actual else None
        if e is not None and e.desde is not None:
            e.t += max(0.0, ahora - e.desde)
            e.desde = None

    # ── cuánto va ──
    def fraccion(self) -> float:
        v = self._estimar(self.reloj())
        if v > self._max:
            self._max = min(TOPE, v)
        return self._max

    def _estimar(self, ahora: float) -> float:
        if self._total <= 0:                                    # primera vez de esta carga
            return SIN_PERFIL_TOPE * (1.0 - math.exp(-(ahora - self.t0) / SIN_PERFIL_TAU_S))
        if self.actual not in self._dur:                        # etapa que la vez anterior no estuvo
            falta = max(3.0, self._total * (1.0 - self._base))
            return self._base + (0.97 - self._base) * (1.0 - math.exp(-(ahora - self._desde_base) / falta))
        lugar = self._orden[self.actual]
        hecho = 0.0
        for k, d in self._dur.items():
            if k == self.actual:
                hecho += d * self._parte_actual(k, d, ahora)
            elif self._orden[k] < lugar:
                hecho += d                                      # ya pasó (o esta vez no hizo falta)
            elif k in self.vistas and d > 0:
                hecho += d * min(1.0, self.vistas[k].t / d)
        return hecho / self._total

    def _parte_actual(self, k: str, d: float, ahora: float) -> float:
        e = self.vistas[k]
        if e.n:
            if e.i >= e.n:
                return 1.0
            por_paso = max(0.05, d / e.n)
            return (e.i + min(ENTRE_AVISOS, (ahora - e.cambio) / por_paso)) / e.n
        t = e.t + (ahora - e.desde if e.desde is not None else 0.0)
        r = t / d if d > 0 else 1.0
        return r if r < FRENO else FRENO + (0.99 - FRENO) * (1.0 - math.exp(-(r - FRENO) / 0.15))

    # ── al terminar ──
    def cerrar(self) -> Optional[dict]:
        """El perfil de esta carga (para la próxima) o None si fue demasiado corta."""
        ahora = self.reloj()
        self._cerrar_tramo(ahora)
        self.actual = None
        total = ahora - self.t0
        if total < DURACION_MIN_S:
            return None
        etapas = [[k, round(self.vistas[k].t, 4)] for k in self._primera if self.vistas[k].t > 0]
        if not etapas:
            return None
        return {"T": round(total, 4), "etapas": etapas}
