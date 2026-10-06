"""recognition_summary.py — resumen del reconocimiento como DATOS (puro, sin Qt).

La vista previa mostraba los avisos de `recognize_page` como un bloque de texto
largo. Aquí cada aviso se clasifica en un nivel y una etiqueta corta, y se
calculan las cifras por utilidad; `recognition_summary_view` los dibuja como
tarjetas, barras y la lista «Para verificar» (el texto completo queda en el
tooltip). Los textos de `recognition.py` no cambian: si aparece uno nuevo sin
regla, cae en «Para verificar» para que nunca quede escondido.

Cada aviso que se muestra en «Para verificar» lleva además una EXPLICACIÓN corta en
lenguaje llano (`Notice.hint`, `_HINTS`): qué se encontró y qué se hizo con ello. El
usuario pidió (2026-10-03) que no parezcan errores: la hoja SÍ se reconoció; son
puntos que conviene mirar antes de importar. Solo PROBLEM son problemas de verdad.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from i18n_core import N_

PROBLEM, REVIEW, INFO = "problema", "revisar", "info"
LEVEL_ORDER = {PROBLEM: 0, REVIEW: 1, INFO: 2}


@dataclass
class Notice:
    utility: str          # clave de la utilidad (ELECTRICO, DRENAJE, AGUA…)
    level: str            # PROBLEM | REVIEW | INFO
    label: str            # etiqueta corta para la lista
    text: str             # aviso completo (tooltip)
    key: str = ""         # qué ubica en la hoja (`targets_for`); "" = nada que ubicar
    hint: str = ""        # explicación llana (clave i18n; solo PROBLEM/REVIEW)


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


# (patrón, nivel, etiqueta, clave). La clave dice qué ubicar en la hoja
# (`targets_for`) al hacer clic en el aviso. La etiqueta es una función del match; el nivel
# puede ser una función del match (codos aproximados, cobertura con huecos).
_RULES = [
    (r"^No se encontraron líneas", PROBLEM, lambda m: "Sin líneas en esta hoja", ""),
    (r"^Esta hoja no tiene capas", PROBLEM, lambda m: "Hoja aplanada: sin capas", ""),
    (r"^Ninguna capa OCG coincidió", PROBLEM, lambda m: "Ninguna capa coincide", ""),
    (r"^Capa «-A» sin el patrón[^:]*: (\d+)", REVIEW,
     lambda m: f"{_n(m)} en capa «-A» sin «/» (van activas)", "a_no_pattern"),
    (r"^Existentes A ABANDONAR[^:]*: (\d+)", REVIEW,
     lambda m: f"{_n(m)} «a abandonar» (-D) van activas", "to_abandon"),
    (r"^Patrón de marcadores «/» en una capa ACTIVA: (\d+)", REVIEW,
     lambda m: f"{_n(m)} con «/» en capa activa", "marker_active"),
    (r"^Curvas que quedan como polilínea: (\d+)", REVIEW,
     lambda m: _pl(_n(m), "curva queda", "curvas quedan") + " como polilínea", "curvy"),
    (r"^Bóvedas sin línea cercana: (\d+)", REVIEW,
     lambda m: _pl(_n(m), "bóveda", "bóvedas") + " sin línea", "orphans"),
    (r"^Codos como esquina \+ radio: (\d+)(?: \((\d+) aproximado)?",
     lambda m: REVIEW if m.group(2) else INFO,
     lambda m: (f"{_n(m, 2)} de {_n(m)} codos aproximados" if m.group(2)
                else f"{_n(m)} codos (esquina + radio)"), "fillets"),
    (r"^Cobertura de guiones: ([\d.]+)%(?: \((\d+) sin cubrir)?",
     lambda m: REVIEW if m.group(2) else INFO,
     lambda m: (_pl(_n(m, 2), "guion sin cubrir", "guiones sin cubrir") + " (magenta)" if m.group(2)
                else f"Cobertura {m.group(1)} %"), "uncovered"),
    (r"^Trazos repetidos[^:]*: (\d+)", INFO, lambda m: f"{_n(m)} trazos repetidos (usados una vez)", ""),
    (r"^Capas repetidas por otro xref[^:]*: (\d+)", INFO, lambda m: f"{_n(m)} capas repetidas por xref", ""),
    (r"^Se excluyeron (\d+) trazo\(s\) dentro de una vista de PERFIL", INFO,
     lambda m: f"{_n(m)} trazos de la vista de perfil excluidos", ""),
    (r"^Utilidades abandonadas[^:]*: (\d+)", INFO, lambda m: f"{_n(m)} abandonadas (AB)", "abandoned"),
    (r"^Patrón «//» en una capa que no es «-A»: (\d+)", INFO,
     lambda m: f"{_n(m)} abandonadas por «//» fuera de «-A»", "double_active"),
    (r"^Rutas: (\d+) \(unen (\d+)", INFO, lambda m: f"{_n(m)} rutas unen {_n(m, 2)} tramos", ""),
    (r"^Se omitieron (\d+) trazos de marcador", INFO, lambda m: f"{_n(m)} letras/barras omitidas", ""),
    (r"^Trazos continuos fuera de patrón[^:]*: (\d+)", INFO,
     lambda m: f"{_n(m)} leaders/flechas (turquesa, no se importan)", "offpattern"),
    (r"^Tuberías dibujadas como contorno[^:]*: (\d+)", INFO,
     lambda m: _pl(_n(m), "tubería en contorno: se usa su eje", "tuberías en contorno: se usa su eje"), ""),
    (r"^Tuberías dibujadas con sus dos paredes: (\d+)", INFO,
     lambda m: _pl(_n(m), "tubería con dos paredes: se usa la línea del medio",
                   "tuberías con dos paredes: se usa la línea del medio"), "walls"),
    (r"^Tuberías dibujadas con paredes y eje: (\d+)", INFO,
     lambda m: _pl(_n(m), "tubería con paredes y eje: se usa el eje",
                   "tuberías con paredes y eje: se usa el eje"), "walls"),
    (r"^Anillos de buzón dibujados en la capa de la línea: (\d+)", INFO,
     lambda m: _pl(_n(m), "anillo de buzón", "anillos de buzón") + " en la capa de la línea", ""),
    (r"^Bóvedas detectadas: (\d+)", INFO, lambda m: _pl(_n(m), "bóveda", "bóvedas") + " en las líneas", "vaults"),
    (r"^Puntas unidas a su bóveda[^:]*: (\d+)", INFO,
     lambda m: _pl(_n(m), "punta unida a su bóveda", "puntas unidas a su bóveda"), "vault_snaps"),
    (r"^Reconocidas por las letras de su línea[^:]*: (\d+)", REVIEW,
     lambda m: _pl(_n(m), "línea reconocida por sus letras", "líneas reconocidas por sus letras"),
     "letters"),
]
# Explicación de cada aviso de «Para verificar»: qué se encontró y qué se hizo con
# ello, sin tono de error (la vista los traduce con `t()`). Clave = patrón de `_RULES`.
_HINTS = {
    r"^No se encontraron líneas": N_(
        "No hay líneas de esta utilidad en la hoja. Si el plano usa otros nombres de capa, "
        "indícalos con «Ajustar capas…»."),
    r"^Esta hoja no tiene capas": N_(
        "El PDF no trae capas en esta hoja y no se puede reconocer sola. Puedes dibujar a mano en "
        "el editor."),
    r"^Ninguna capa OCG coincidió": N_(
        "Ningún nombre de capa es conocido. Indica cuáles son las líneas con «Ajustar capas…»."),
    r"^Capa «-A» sin el patrón[^:]*: (\d+)": N_(
        "Su capa dice «abandonada» (-A), pero la línea no lleva las marcas «/». Se importan como "
        "activas: confirma si lo son."),
    r"^Existentes A ABANDONAR[^:]*: (\d+)": N_(
        "Su capa es «existente a abandonar» (-D). Se importan como activas hasta que tú decidas."),
    r"^Patrón de marcadores «/» en una capa ACTIVA: (\d+)": N_(
        "Llevan las marcas «/» de abandonada, pero su capa es activa. Se importan como activas."),
    r"^Curvas que quedan como polilínea: (\d+)": N_(
        "El plano no las dibuja como un arco exacto (radio que cambia o esquina cortada). Se "
        "importan como tramos rectos que siguen la curva."),
    r"^Bóvedas sin línea cercana: (\d+)": N_(
        "Están en el plano, pero ninguna línea llega a ellas (anillo magenta). Se importan igual, "
        "como cajas sueltas; mira si les falta una línea."),
    r"^Codos como esquina \+ radio: (\d+)(?: \((\d+) aproximado)?": N_(
        "La curva del plano no es un arco perfecto. Se importó el arco que mejor la sigue (a "
        "trazos en la hoja)."),
    r"^Cobertura de guiones: ([\d.]+)%(?: \((\d+) sin cubrir)?": N_(
        "Trozos de línea del plano que no quedaron dentro de ninguna línea reconocida (en "
        "magenta). Suelen ser restos sueltos del dibujo."),
    r"^Reconocidas por las letras de su línea[^:]*: (\d+)": N_(
        "El nombre de su capa no dice esta utilidad, pero las letras de la línea sí (por ejemplo "
        "«—TE—»). Confirma que es así; si no, cámbialo con «Ajustar capas…»."),
}
_COMPILED = [(re.compile(p), lvl, lab, key, _HINTS.get(p, "")) for p, lvl, lab, key in _RULES]


def classify_warning(text: str, utility: str = "") -> Notice:
    """Aviso de `recognize_page` → `Notice`. Sin regla: REVIEW con el texto tal cual."""
    for rx, lvl, lab, key, hint in _COMPILED:
        m = rx.search(text)
        if m:
            level = lvl(m) if callable(lvl) else lvl
            return Notice(utility, level, lab(m), text, key, hint if level != INFO else "")
    if len(text) <= 60:
        return Notice(utility, REVIEW, text, text)
    return Notice(utility, REVIEW, text[:57].rstrip() + "…", text, hint=text)    # el resto, a la vista


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


# ─────────────── ubicación de cada aviso en la hoja (clic → ir allí) ───────────────
Rect = Tuple[float, float, float, float]      # x0, y0, x1, y1 en px de la vista previa
POINT_PAD_PX = 12.0                            # un punto se muestra como un recuadro de ±12 px


def _bbox(pts) -> Optional[Rect]:
    pts = [p for p in pts if p is not None]
    if not pts:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _around(p, pad: float = POINT_PAD_PX) -> Rect:
    return (p[0] - pad, p[1] - pad, p[0] + pad, p[1] + pad)


def _curve_spans(pl) -> List[Rect]:
    """Cada ristra de vértices `curve` (con sus dos vecinos) = una curva que
    quedó como polilínea."""
    pts, kinds = list(pl.pts_pdf), list(pl.kinds or [])
    out, i = [], 0
    while i < len(kinds):
        if kinds[i] != "curve":
            i += 1
            continue
        j = i
        while j + 1 < len(kinds) and kinds[j + 1] == "curve":
            j += 1
        box = _bbox(pts[max(0, i - 1): min(len(pts), j + 2)])
        if box:
            out.append(box)
        i = j + 1
    return out


def targets_for(key: str, result) -> List[Rect]:
    """Recuadros (px de la vista previa) de lo que señala un aviso, en orden de
    lectura (arriba→abajo, izquierda→derecha). Vacío si no hay nada que ubicar."""
    lines = list(getattr(result, "drawable", None) or [])
    joined = [p for p in (getattr(result, "polylines_joined", None) or []) if p.pts_pdf] or lines
    out: List[Rect] = []
    if key == "fillets":
        fil = [(pl, idx, f) for pl in lines for idx, f in (getattr(pl, "fillets", None) or {}).items()]
        loose = [x for x in fil if x[2].get("loose")]
        for pl, idx, f in (loose or fil):
            box = _bbox([f.get("a"), f.get("b"), pl.pts_pdf[idx]])
            if box:
                out.append(box)
    elif key == "curvy":
        # una por TRAMO (el aviso cuenta tramos): el recuadro de sus curvas
        for pl in lines:
            spans = _curve_spans(pl)
            if spans:
                out.append((min(r[0] for r in spans), min(r[1] for r in spans),
                            max(r[2] for r in spans), max(r[3] for r in spans)))
    elif key == "uncovered":
        out = [b for a, c in (getattr(result, "uncovered_px", None) or []) if (b := _bbox([a, c]))]
    elif key == "orphans":
        out = [_around(p) for p in (getattr(result, "vault_orphans_px", None) or [])]
    elif key == "vaults":
        out = [_around(p) for p in (getattr(result, "vault_pts", None) or [])]
    elif key == "vault_snaps":
        out = [_around(p) for p in (getattr(result, "vault_snaps_px", None) or [])]
    elif key == "walls":
        out = [b for pts in (getattr(result, "walls_px", None) or []) if (b := _bbox(pts))]
    elif key == "offpattern":
        out = [b for pts in (getattr(result, "offpattern_px", None) or []) if (b := _bbox(pts))]
    elif key == "abandoned":
        out = [b for pl in lines if getattr(pl, "abandoned", False) and (b := _bbox(pl.pts_pdf))]
    elif key == "letters":
        out = [b for pl in lines if getattr(pl, "letters", "") and (b := _bbox(pl.pts_pdf))]
    elif key in ("a_no_pattern", "double_active", "to_abandon", "marker_active"):
        out = [b for pl in joined if getattr(pl, "review", "") == key and (b := _bbox(pl.pts_pdf))]
    # puntos/segmentos degenerados → recuadro mínimo visible
    out = [(x0 - POINT_PAD_PX, y0 - POINT_PAD_PX, x1 + POINT_PAD_PX, y1 + POINT_PAD_PX)
           if (x1 - x0) < 2 * POINT_PAD_PX and (y1 - y0) < 2 * POINT_PAD_PX else (x0, y0, x1, y1)
           for x0, y0, x1, y1 in out]
    return sorted(out, key=lambda r: (round((r[1] + r[3]) / 2 / 50.0), (r[0] + r[2]) / 2))
