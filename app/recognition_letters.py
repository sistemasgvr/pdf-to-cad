"""recognition_letters.py — La utilidad de una línea por las LETRAS de su linetype (puro).

El nombre de la capa casi siempre dice la utilidad (`recognition.classify_ocg`), pero
hay líneas de utilidad en capas cuyo nombre no es de ninguna (pedido del usuario
2026-10-05, DU08 h.26: «la línea “TE” aparece en Otras y no se reconoce»):
  · `U-TRPW-DBNK-P` («—TE—»): según la leyenda de DU08 h.3/h.33 es el banco de ductos
    de ELECTRIFICACIÓN DE TRACCIÓN de Metro (eléctrico, no telecom);
  · `…PROP_WATER_PIPE_ALGN|C-ROAD` (LABOE): alineamiento de Civil 3D en su capa por
    defecto «C-ROAD» («—W—», «—T—», «—S—» según el xref);
  · `_Xref`, `G-XREF`: lo que un xref dibuja en la capa 0 hereda la capa del bloque y
    MEZCLA utilidades («—G—» y «—W—» en la misma capa, DU10 h.11).
Las letras son vectores SHX (no texto): `recognition_letter_shapes` las lee.

  1. `recognition_letter_lines.gaps`: huecos entre dos guiones COLINEALES enfrentados.
  2. `read_text`: trazos del hueco centrados en el eje → letras → texto, leído en los
     dos sentidos (AutoCAD gira el texto con la línea: «TE» al revés se ve «3⊥»).
  3. `read_layer`: votos por SITIO (`codes`, `utilities`) y, al pedirlo, el reparto
     LÍNEA POR LÍNEA (`by_path`): se une cada línea —guiones del mismo hueco, puntas
     que se tocan o forman esquina, guiones de una curva, sus letras y barras— y va a
     la utilidad de SUS letras (`LETTER_CODES`). `dedicated`: letras homogéneas y el
     reparto ya cubre ≥75 % de la tinta → la capa entera (lo que falta son tramos
     junto a cruces); si no (capa genérica), solo los trazos de cada línea con letras.
`recognition.letter_uses` decide qué capas se usan así: las que su nombre no hace de
ninguna utilidad y las de línea cuyo nombre contradicen letras unánimes.
Medido en los 4 PDFs de prueba (141 hojas): 190 líneas en 51 hojas —`U-TRPW-DBNK-P`
(«TE»), `_Xref` («G»/«W»), `G-XREF` («T»/«W»/«SE»/«SD»), `U-Rearr-Tel`, los
alineamientos «C-ROAD» de LABOE y la línea «—S—» de su capa «0»—, 0 tramos sin tinta;
35 nombres de capa confirmados y un desacuerdo: `N-COMM-DUCT-BANK-PL-SE` («SE» =
Station Electrification según la leyenda: eléctrico, su nombre dice telecom).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import recognition_letter_lines as lines
import recognition_letter_shapes as shapes
from recognition_letter_lines import path_key, site_count  # noqa: F401  (API)


AXIS_SEED_PT = 0.5       # trazos que cruzan el eje (±) = letras de ESTA línea; dan el alto del rótulo
AXIS_STROKE_PT = 0.3     # trazo sobre el eje (guión corto del patrón, brazo medio de la «E»)…
AXIS_DASH_RATIO = 0.9    # …que mide ≥ esto × alto del rótulo es un guión, no parte de una letra
LETTER_GAP_RATIO = 0.06  # dos trazos separados en x más que esto × alto = letras distintas
MIN_TEXT_PT = 1.0        # rótulo más bajo que esto: no hay letra
MAX_STROKES = 16         # un rótulo de linetype tiene pocos trazos (textos y logos no)
MAX_LETTERS = 8
MAX_SEGS = 120
DUP_STROKE_PT = 0.15     # el mismo trazo dos veces (xref duplicado): uno solo
ORIENT_TIE = 0.02        # los dos sentidos de lectura empatan: decide el código conocido o el guión
MIN_PATHS = 6            # capa con menos trazos: no se lee
MIN_SITES_LAYER = 3      # capa sin utilidad por su nombre: ≥3 sitios con letras para clasificarla
MIN_SITES_CODE = 2       # capa MEZCLADA: cada código necesita ≥2 sitios (si no, es ruido)
MAPPED_SHARE = 0.5       # los códigos de utilidad son ≥50 % de lo leído en la capa: si no, sus
                         # «letras» son dibujo (DU06 h.2 `W-Plantry`: 3 «G» entre ~70 lecturas basura)
LAYER_SHARE = 0.9        # código dominante ≥90 % de los sitios = capa homogénea…
DEDICATED_SHARE = 0.75   # …y si el reparto por línea cubre ≥75 % de su tinta, la capa ENTERA
OVERRIDE_MIN_SITES = 5   # el nombre de una capa de línea solo cede ante ≥5 sitios…
OVERRIDE_SHARE = 0.95    # …prácticamente unánimes

# Código del linetype (mayúsculas, sin «/», «-» ni lo que va entre paréntesis) →
# utilidad. Leyenda de DU08 h.3/h.33 (APDU/Metro): e/E eléctrico, g/G gas, ss/SS
# alcantarillado (S en las propuestas de LABOE y DU08), sd/SD drenaje, t/T telecom,
# w/W agua, «(oh)» aérea; Metro: SC «Signal & Communication», SE «Station
# Electrification», TE «Traction Electrification». Más los códigos usuales de otros
# planos (FO fibra óptica, TV/CATV cable, UE/UT subterráneas…). «UNK» (desconocida) y
# «O» (petróleo) no son utilidades de la app: quedan en «Otras».
LETTER_CODES: Dict[str, str] = {
    "E": "ELECTRICO", "SE": "ELECTRICO", "TE": "ELECTRICO", "UE": "ELECTRICO", "UGE": "ELECTRICO",
    "T": "TELECOM", "SC": "TELECOM", "TEL": "TELECOM", "UT": "TELECOM", "UGT": "TELECOM",
    "FO": "TELECOM", "TV": "TELECOM", "CATV": "TELECOM", "CTV": "TELECOM", "COMM": "TELECOM",
    "W": "AGUA", "WL": "AGUA", "WTR": "AGUA", "FW": "AGUA",
    "G": "GAS", "NG": "GAS", "GAS": "GAS",
    "SS": "ALCANTARILLADO", "S": "ALCANTARILLADO", "SAN": "ALCANTARILLADO", "FM": "ALCANTARILLADO",
    "SD": "DRENAJE", "STM": "DRENAJE",
}
# Capas que NO se leen: anotación, cajetín, cotas (la leyenda de DU08 h.33 dibuja
# muestras «—e—», «—TE—»… en `G-ANNO-TEXT`: no son líneas de la red) y las aéreas.
SKIP_LAYER_TOKENS = ("ANNO", "TEXT", "TEXL", "TTLB", "LOGO", "DIMS", "NOTE", "LEGN", "LEGD",
                     "OVHD")


def raw_core(text: str) -> str:
    """Las letras tal como se leyeron, sin marcas ni lo que va entre paréntesis:
    «/w» → «w», «e(oh)» → «e». Conserva mayúsculas/minúsculas (existente «e» /
    propuesta «E» en la leyenda de DU08; en «w»/«W» o «s»/«S» la forma no lo distingue)."""
    return "".join(ch for ch in (text or "").split("(")[0] if ch.isalpha())


def normalize_code(text: str) -> Tuple[str, bool]:
    """«e(oh)» → ("E", True); «/W» → ("W", False); «TE» → ("TE", False)."""
    up = (text or "").upper()
    overhead = "(OH" in up or "OH)" in up
    base = "".join(ch for ch in up.split("(")[0] if ch.isalpha())
    return base, overhead


def code_utility(code: str) -> Optional[str]:
    """Utilidad de un código YA normalizado («TE» → ELECTRICO), o None."""
    return LETTER_CODES.get(code)


def letters_candidate(name: str) -> bool:
    """¿Vale la pena leer las letras de esta capa? (no anotación, cajetín ni aérea)."""
    short = (name or "").split("|")[-1].upper()
    return bool(short) and not any(t in short for t in SKIP_LAYER_TOKENS)


@dataclass
class LayerLetters:
    """Lo que dicen las letras de los trazos de UNA capa."""
    codes: Counter = field(default_factory=Counter)       # «TE», «W», «E(OH)»… → sitios
    utilities: Counter = field(default_factory=Counter)   # utilidad → sitios (sin aéreas)
    sites: int = 0                                        # sitios con letras legibles (sin aéreas)
    raw: Dict[str, str] = field(default_factory=dict)     # código → como se lee más («G», «e»)
    _split: Optional[Tuple[Dict[tuple, str], float]] = field(default=None, repr=False)
    _splitter: Optional[Callable[[], Tuple[Dict[tuple, str], float]]] = field(default=None, repr=False)

    def _line_split(self) -> Tuple[Dict[tuple, str], float]:
        if self._split is None:
            ok = self._splitter is not None and self.utilities
            self._split = self._splitter() if ok else ({}, 0.0)
            self._splitter = None
        return self._split

    @property
    def by_path(self) -> Dict[tuple, str]:
        """Utilidad de cada trazo (clave `path_key`) según las letras de SU línea. Se
        calcula al pedirlo (solo hace falta en capas sin utilidad por su nombre)."""
        return self._line_split()[0]

    @property
    def coverage(self) -> float:
        """Fracción de la tinta de líneas de la capa que el reparto por línea asigna."""
        return self._line_split()[1]

    @property
    def dedicated(self) -> Optional[str]:
        """Utilidad de TODA la capa: letras homogéneas y su reparto por línea ya cubre
        ≥`DEDICATED_SHARE` de su tinta (`U-TRPW-DBNK-P`: 89–93 %; lo que falta son
        tramos junto a curvas y cruces). Una capa GENÉRICA con una sola línea con
        letras no lo es: la capa «0» de LABOE h.26 (comentarios de revisión, una vista
        de perfil y UNA línea «—S—»: 2 %) o `G-XREF` (9–18 %)."""
        u = self.utility
        return u if u is not None and self.coverage >= DEDICATED_SHARE else None

    @property
    def utility(self) -> Optional[str]:
        """La utilidad de TODA la capa (homogénea), o None."""
        if not self.utilities or self.sites < MIN_SITES_LAYER:
            return None
        key, n = self.utilities.most_common(1)[0]
        return key if n >= LAYER_SHARE * self.sites else None

    @property
    def unanimous(self) -> Optional[str]:
        """Utilidad prácticamente unánime y con muchos sitios (puede contradecir el nombre)."""
        if not self.utilities or self.sites < OVERRIDE_MIN_SITES:
            return None
        key, n = self.utilities.most_common(1)[0]
        return key if n >= OVERRIDE_SHARE * self.sites else None

    @property
    def mixed(self) -> List[str]:
        """Utilidades de una capa MEZCLADA (cada una con sus trazos en `by_path`)."""
        if self.utility is not None:
            return []
        return sorted(self.utilities)

    def label(self, utility: Optional[str] = None) -> str:
        """Códigos de utilidad leídos, para mostrar: «TE», «G · W»; con `utility`, solo
        los suyos (el ruido —«A», «IG»— no se muestra)."""
        keep = [c for c, n in self.codes.most_common()
                if (n >= MIN_SITES_CODE or self.utility) and code_utility(c)
                and (utility is None or code_utility(c) == utility)]
        return " · ".join(keep[:3])


# ─────────────────────────── lectura del rótulo ───────────────────────────
def _dedupe(strokes):
    out = []
    for s in strokes:
        if not any(len(s) == len(t) and (all(math.dist(a, b) <= DUP_STROKE_PT for a, b in zip(s, t)) or
                                         all(math.dist(a, b) <= DUP_STROKE_PT for a, b in zip(s, reversed(t))))
                   for t in out):
            out.append(s)
    return out


def _centered(strokes):
    """Solo los trazos del rótulo de ESTA línea: los que cruzan el eje dan el alto y
    entran los que caben en él (una línea paralela a 5 pt metía sus «w» en el hueco y
    se leía «t»: DU08 h.26, tres líneas de agua juntas)."""
    rng = [(min(y for _, y in s), max(y for _, y in s)) for s in strokes]
    seed = [r for r in rng if r[0] <= AXIS_SEED_PT and r[1] >= -AXIS_SEED_PT]
    if not seed:
        return []
    lo, hi = min(r[0] for r in seed) - 0.5, max(r[1] for r in seed) + 0.5
    return [s for s, r in zip(strokes, rng) if r[0] >= lo and r[1] <= hi]


def _split_letters(strokes, height):
    items = sorted(((min(x for x, _ in s), max(x for x, _ in s), s) for s in strokes), key=lambda t: t[0])
    letters = []
    for x0, x1, s in items:
        if letters and x0 <= letters[-1][1] + LETTER_GAP_RATIO * height:
            letters[-1][1] = max(letters[-1][1], x1)
            letters[-1][2].append(s)
        else:
            letters.append([x0, x1, [s]])
    return [it[2] for it in letters]


_TEXT_CACHE: Dict[tuple, Optional[Tuple[str, float]]] = {}


def read_text(strokes, sure: bool = False) -> Optional[Tuple[str, float]]:
    """Texto de un rótulo (trazos en el marco del hueco) y su peor puntaje de letra, o
    None si no se puede leer. Prueba los dos sentidos; si empatan, gana el que da un
    código conocido y, si no, el del sentido del guión (`sure`). El mismo rótulo se
    repite a lo largo de la línea: cada forma se lee una sola vez."""
    key = (sure, tuple(sorted(tuple((round(x * 4), round(y * 4)) for x, y in s) for s in strokes)))
    if key not in _TEXT_CACHE:
        if len(_TEXT_CACHE) > 20000:
            _TEXT_CACHE.clear()
        _TEXT_CACHE[key] = _read_text(strokes, sure)
    return _TEXT_CACHE[key]


def _read_text(strokes, sure: bool) -> Optional[Tuple[str, float]]:
    strokes = _dedupe(_centered(strokes))
    ink = [s for s in strokes if not all(abs(y) <= AXIS_STROKE_PT for _, y in s)]
    if not ink:
        return None
    height = max(y for s in ink for _, y in s) - min(y for s in ink for _, y in s)
    if height < MIN_TEXT_PT:
        return None
    strokes = [s for s in strokes if not (all(abs(y) <= AXIS_STROKE_PT for _, y in s)
                                          and max(x for x, _ in s) - min(x for x, _ in s) >= AXIS_DASH_RATIO * height)]
    if not strokes or len(strokes) > MAX_STROKES or sum(len(s) - 1 for s in strokes) > MAX_SEGS:
        return None
    cands = []
    for flip in (False, True):
        ss = [[(-x, -y) for x, y in s] for s in strokes] if flip else strokes
        letters = _split_letters(ss, height)
        if len(letters) > MAX_LETTERS:
            return None
        text, worst = "", 0.0
        for let in letters:
            ys = [y for s in let for _, y in s]
            if max(ys) - min(ys) < 0.15 * height:       # guión corto entre letras
                continue
            ch, sc = shapes.read_letter(let)
            text += ch
            worst = max(worst, sc)
        if text:
            cands.append((worst, flip, text))
    if not cands:
        return None
    cands.sort()
    best = cands[0]
    if len(cands) == 2 and cands[1][0] - best[0] < ORIENT_TIE:
        known = [c for c in cands if code_utility(normalize_code(c[2])[0])]
        if len(known) == 1:
            best = known[0]
        elif sure:
            best = next(c for c in cands if not c[1])
    return (best[2], best[0]) if best[0] <= shapes.GOOD_SCORE else None


def read_layer(paths: Sequence[dict]) -> Optional[LayerLetters]:
    """Lee las letras del linetype de los trazos de UNA capa (dicts de `get_drawings`).
    None si no hay ninguna lectura."""
    if len(paths) < MIN_PATHS:
        return None
    chains, owner = lines.stroke_chains(paths)
    ends = lines.dash_ends(chains)
    if not ends:
        return None
    gaps, touching = lines.gaps(ends)
    if not gaps:
        return None
    members_by_gap = lines.group_members(chains, gaps)
    readings = []                                  # (cadena del guión, sitio, código, aérea)
    raw_seen = defaultdict(Counter)
    for (origin, u, glen, sure, ca, _cb), members in zip(gaps, members_by_gap):
        if not members:
            continue
        got = read_text([loc for _ci, loc in members], sure)
        if got is None:
            continue
        code, overhead = normalize_code(got[0])
        if code:
            site = (origin[0] + u[0] * glen / 2.0, origin[1] + u[1] * glen / 2.0)
            readings.append((ca, site, code, overhead))
            raw_seen[code][raw_core(got[0])] += 1
    if not readings:
        return None
    out = LayerLetters()
    out.raw = {c: n.most_common(1)[0][0] for c, n in raw_seen.items()}
    by_code = defaultdict(list)
    for _ca, site, code, overhead in readings:
        by_code[code + ("(OH)" if overhead else "")].append(site)
    for code, sites in by_code.items():
        out.codes[code] = site_count(sites)
    noisy = {c for c, n in out.codes.items() if n < MIN_SITES_CODE}
    for code, n in out.codes.items():
        if code.endswith("(OH)"):
            continue
        out.sites += n
        util = code_utility(code)
        if util and code not in noisy:
            out.utilities[util] += n
    if sum(out.utilities.values()) < MAPPED_SHARE * out.sites:
        out.utilities.clear()           # casi todo lo «leído» no es un código: no es un linetype
    out._splitter = lambda: lines.split_by_line(
        paths, chains, owner, ends, gaps, touching, members_by_gap, readings,
        lambda code: None if code in noisy else code_utility(code))
    return out
