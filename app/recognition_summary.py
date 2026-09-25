"""recognition_summary.py — resumen del reconocimiento como DATOS (puro, sin Qt).

La vista previa mostraba los avisos de `recognize_page` como un bloque de texto
largo. Aquí cada aviso se clasifica en un nivel y una etiqueta corta, y se
calculan las cifras por utilidad; `recognition_summary_view` los dibuja como
tarjetas, barras y una lista corta de «Revisar» (el texto completo queda en el
tooltip). Los textos de `recognition.py` no cambian: si aparece uno nuevo sin
regla, cae en «Revisar» para que nunca quede escondido.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

PROBLEM, REVIEW, INFO = "problema", "revisar", "info"
LEVEL_ORDER = {PROBLEM: 0, REVIEW: 1, INFO: 2}


@dataclass
class Notice:
    utility: str          # clave de la utilidad (ELECTRICO, DRENAJE, AGUA…)
    level: str            # PROBLEM | REVIEW | INFO
    label: str            # etiqueta corta para la lista
    text: str             # aviso completo (tooltip)


@dataclass
class UtilityStats:
    utility: str
    tramos: int           # polilíneas que se importan
    abandonadas: int      # …de ellas, abandonadas (AB)
    codos: int            # esquinas + radio
    estructuras: int      # bóvedas que son vértices de las líneas
    coverage: float       # cobertura de guiones 0..1

    @property
    def activas(self) -> int:
        return self.tramos - self.abandonadas


def _n(m, i=1) -> int:
    return int(m.group(i))


def _pl(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# (patrón, nivel, etiqueta). La etiqueta es una función del match; el nivel
# puede ser una función del match (codos aproximados, cobertura con huecos).
_RULES = [
    (r"^No se encontraron líneas", PROBLEM, lambda m: "Sin líneas en esta hoja"),
    (r"^Esta hoja no tiene capas", PROBLEM, lambda m: "Hoja aplanada: sin capas"),
    (r"^Ninguna capa OCG coincidió", PROBLEM, lambda m: "Ninguna capa coincide"),
    (r"^Capa «-A» sin el patrón[^:]*: (\d+)", REVIEW,
     lambda m: f"{_n(m)} en capa «-A» sin «/» (van activas)"),
    (r"^Existentes A ABANDONAR[^:]*: (\d+)", REVIEW,
     lambda m: f"{_n(m)} «a abandonar» (-D) van activas"),
    (r"^Patrón de marcadores «/» en una capa ACTIVA: (\d+)", REVIEW,
     lambda m: f"{_n(m)} con «/» en capa activa"),
    (r"^Curvas que quedan como polilínea: (\d+)", REVIEW,
     lambda m: _pl(_n(m), "curva queda", "curvas quedan") + " como polilínea"),
    (r"^Bóvedas sin línea cercana: (\d+)", REVIEW,
     lambda m: _pl(_n(m), "bóveda", "bóvedas") + " sin línea"),
    (r"^Codos como esquina \+ radio: (\d+)(?: \((\d+) aproximado)?",
     lambda m: REVIEW if m.group(2) else INFO,
     lambda m: (f"{_n(m, 2)} de {_n(m)} codos aproximados" if m.group(2)
                else f"{_n(m)} codos (esquina + radio)")),
    (r"^Cobertura de guiones: ([\d.]+)%(?: \((\d+) sin cubrir)?",
     lambda m: REVIEW if m.group(2) else INFO,
     lambda m: (f"{_n(m, 2)} guiones sin cubrir (naranja)" if m.group(2)
                else f"Cobertura {m.group(1)} %")),
    (r"^Trazos repetidos[^:]*: (\d+)", INFO, lambda m: f"{_n(m)} trazos repetidos (usados una vez)"),
    (r"^Capas repetidas por otro xref[^:]*: (\d+)", INFO, lambda m: f"{_n(m)} capas repetidas por xref"),
    (r"^Se excluyeron (\d+) trazo\(s\) dentro de una vista de PERFIL", INFO,
     lambda m: f"{_n(m)} trazos de la vista de perfil excluidos"),
    (r"^Utilidades abandonadas[^:]*: (\d+)", INFO, lambda m: f"{_n(m)} abandonadas (AB)"),
    (r"^Patrón «//» en una capa que no es «-A»: (\d+)", INFO,
     lambda m: f"{_n(m)} abandonadas por «//» fuera de «-A»"),
    (r"^Rutas: (\d+) \(unen (\d+)", INFO, lambda m: f"{_n(m)} rutas unen {_n(m, 2)} tramos"),
    (r"^Se omitieron (\d+) trazos de marcador", INFO, lambda m: f"{_n(m)} letras/barras omitidas"),
    (r"^Trazos continuos fuera de patrón[^:]*: (\d+)", INFO,
     lambda m: f"{_n(m)} leaders/flechas (violeta, no se importan)"),
    (r"^Bóvedas detectadas: (\d+)", INFO, lambda m: _pl(_n(m), "bóveda", "bóvedas") + " en las líneas"),
]
_COMPILED = [(re.compile(p), lvl, lab) for p, lvl, lab in _RULES]


def classify_warning(text: str, utility: str = "") -> Notice:
    """Aviso de `recognize_page` → `Notice`. Sin regla: REVIEW con el texto tal cual."""
    for rx, lvl, lab in _COMPILED:
        m = rx.search(text)
        if m:
            level = lvl(m) if callable(lvl) else lvl
            return Notice(utility, level, lab(m), text)
    short = text if len(text) <= 60 else text[:57].rstrip() + "…"
    return Notice(utility, REVIEW, short, text)


def notices_for(results: Sequence) -> List[Notice]:
    """Todos los avisos de los resultados, ordenados: problemas, revisar, info
    (dentro de cada nivel se conserva el orden de la utilidad y del aviso)."""
    out = [classify_warning(w, r.utility) for r in results for w in (r.warnings or [])]
    return sorted(out, key=lambda n: LEVEL_ORDER[n.level])


def stats_for(result) -> UtilityStats:
    drawable = list(result.drawable)
    return UtilityStats(
        utility=result.utility,
        tramos=len(drawable),
        abandonadas=sum(1 for p in drawable if getattr(p, "abandoned", False)),
        codos=sum(len(getattr(p, "fillets", None) or {}) for p in drawable),
        estructuras=len(getattr(result, "vault_pts", None) or []),
        coverage=float(getattr(result, "coverage", 1.0) or 0.0),
    )


def totals(stats: Sequence[UtilityStats]) -> Optional[UtilityStats]:
    if not stats:
        return None
    return UtilityStats(
        utility="",
        tramos=sum(s.tramos for s in stats),
        abandonadas=sum(s.abandonadas for s in stats),
        codos=sum(s.codos for s in stats),
        estructuras=sum(s.estructuras for s in stats),
        coverage=min(s.coverage for s in stats),
    )
