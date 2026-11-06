"""Qué le falta al proyecto para exportar (PURO): lo que muestra el Copiloto al preguntar «¿Cómo vamos?».

Las cifras salen de los conflictos y avisos que ya calculó la app; no interviene la IA.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nucleo.normas_validar import CLASES
from traduccion.i18n_core import N_

CONFLICTOS = "conflictos"
PRIMERO = ("grosor", "tipo")           # lo que más trabajo ahorra revisar antes
OCULTAS = ("angulo",)                  # se valida pero no se muestra (decisión del usuario)
CONFLICTOS_OCULTOS, SIN_ESCALA = "conflictos_ocultos", "sin_escala"   # lo que impide saber si falta algo


@dataclass
class Grupo:
    clave: str
    titulo: str                        # sin traducir
    pendientes: int
    aprobados: int = 0


@dataclass
class Estado:
    grupos: list = field(default_factory=list)
    notas: list = field(default_factory=list)

    @property
    def listo(self):
        return not self.notas and not any(g.pendientes for g in self.grupos)


def armar(conflictos, avisos, conflictos_ocultos=False, sin_escala=False):
    """`conflictos_ocultos`: con «Mostrar cruces/conflictos» apagado no se calculan. `sin_escala`: sin escala no se
    calculan los avisos. En los dos casos no se sabe si falta algo: nunca es «listo»."""
    notas = [n for n, si in ((CONFLICTOS_OCULTOS, conflictos_ocultos), (SIN_ESCALA, sin_escala)) if si]
    grupos = []
    if conflictos:
        grupos.append(Grupo(CONFLICTOS, N_("Conflictos"), len(conflictos)))
    por_clase = {}
    for a in avisos or []:
        if a.info or a.clase in OCULTAS:
            continue
        g = por_clase.setdefault(a.clase, Grupo(a.clase, CLASES.get(a.clase, a.clase), 0))
        if getattr(a, "aprobado", None):
            g.aprobados += 1
        else:
            g.pendientes += 1
    orden = list(PRIMERO) + [c for c in CLASES if c not in PRIMERO]
    grupos += [por_clase[c] for c in orden if c in por_clase]
    grupos += [g for c, g in por_clase.items() if c not in orden]
    return Estado(grupos, notas)
