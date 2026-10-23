"""recognition_grosor.py — el GROSOR (diámetro) de cada tubería en un PDF CAD bien ploteado (PURO).

Pedido del usuario 2026-10-21 (DU06 drenaje): «reconocer su grosor si el PDF dispone de esa
información… un complemento, que no afecte lo que ya hacemos». Ningún vértice se mueve: se
escribe `pl.grosor` (el porqué) y `pl.diam_in` si estaba vacío, en las líneas donde el plano lo
dice; y una ruta con DOS diámetros se parte en el nodo donde cambia (abajo). Solo en hojas con
capas (CAD); los mapas sin capas tienen `recognition_grosor_mapa`.

Cómo lo dice un plano CAD (DU06): el grosor de la PLUMA no — va por ESTADO de la capa (existente
0.72 pt, propuesta 1.44, a demoler 1.02). Lo dicen:

  1. RÓTULOS con GUÍA (MLeader): «EX. 84" RCP SD», «EX.18" RCP SD», «24" RCP SD, MTA», «18" RCP,
     LACFCD», «PROP 2" SCG» (`recognition_grosor_texto`), con su flecha
     (`recognition_grosor_guias`) sobre la tubería o su pared. `asignar_rotulos` lleva cada
     rótulo a la línea de SU utilidad donde cae la punta (o, si la flecha se pasó de largo, a la
     única que cruza la guía justo antes de ella); en la unión de un lateral con la principal la
     punta toca las dos y decide lo que ya se sabe de cada una; la misma tubería dibujada dos
     veces (existente + propuesta encimadas) lo recibe en las dos. Un rótulo con estación («JOIN
     EX. 84" RCP SD / STA 549+55.37 / CB LAT 208») marca un PUNTO, el diámetro de la tubería a la
     que algo se une ahí: solo CONFIRMA a la línea que ya dice ese diámetro.
  2. PAREDES dibujadas (capas `-WALL` de la utilidad): desde la línea de centro, la pared más
     cercana de cada lado es la INTERIOR (un 84" RCP trae además la exterior, a 8"). `paredes` da
     el ancho redondeado a un tamaño nominal si las muestras coinciden. Hay laterales dibujados
     solo con las paredes EXTERIORES (18" con las paredes a 24" en DU06): `exterior` lo acepta
     junto a su rótulo y `calibrar` lo aplica a las líneas solo con paredes de esa hoja.

`combinar`: el rótulo manda; las paredes lo confirman o, sin rótulo, lo dan. Rótulos distintos
en una misma línea: si forman ZONAS a lo largo de ella (84" hasta un pozo y 81" después en la
principal de DU06 h.5; dos laterales de 18" y 33" unidos en una «V» por una esquina en h.4) la
línea se parte en ese nodo (`recognition_grosor_partir`) y cada pieza lleva el suyo; si no, sin
diámetro y dudosa.

SOLO LO SEGURO (pedido del usuario 2026-10-22: «si no estamos 100 % seguros… no hay que ponerla
automáticamente, sino dejar una alerta»): cada línea queda «leido» (se pone el diámetro), «dudoso»
(rótulos distintos que no se separan, rótulo ≠ paredes, paredes sin un rótulo de la hoja que diga
si son las de adentro o las de afuera: no se pone, `candidatos` dice lo que dice el plano) o
«sin_dato» (`seguro`, `aplicar`). Las dudosas y las sin dato quedan con el diámetro por defecto y
el editor les pone un aviso (`nucleo/diametro_plano`). Rótulos girados 90° (verticales):
`recognition_grosor_marcos`; un rótulo que solo dice su material no va a la línea de una utilidad
si su guía cae sobre la tinta de otra: `recognition_grosor_tinta`.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reconocimiento.recognition_grosor_texto import (  # noqa: F401  (re-exportados)
    Rotulo, diametros_de, es_de, lecturas, lineas_texto, material_de, rotulos, utilidad_de)
from reconocimiento.recognition_grosor_guias import FLECHA_MAX_PT, Guias, guias, puntas_de_rotulos  # noqa: F401
from reconocimiento import recognition_grosor_partir as P

Pt = Tuple[float, float]

NOMINALES_IN = (4, 6, 8, 10, 12, 15, 18, 21, 24, 27, 30, 33, 36, 42, 48, 54, 60, 66, 72, 78, 84,
                90, 96, 102, 108, 114, 120, 132, 144)
PUNTA_HOLGURA_PT = 4.0        # la punta cae sobre la línea (o su pared: + medio diámetro)
PARED_MAX_PT = 80.0           # buscar paredes hasta aquí de la línea de centro
PARED_PARALELA = 0.995        # |cos| de una pared con su tramo (±5.7°)
PARED_SIMETRIA = 0.15         # los dos lados iguales ±15 % (+0.5 pt)
PARED_MUESTRAS_MIN = 3        # muestras de acuerdo para dar un diámetro
PARED_ACUERDO = 0.7           # fracción de muestras con el mismo nominal
NOMINAL_TOL_IN = 1.5          # medida → nominal
PARED_PASO_PT = 20.0          # una muestra de paredes cada tanto
JUNTO_PT = 30.0               # paredes «junto a la punta» de una guía: ± esto
SOLAPE_PT = 2.0               # dos líneas paralelas a menos de esto junto a la punta: la misma tubería
SOLAPE_COS = math.cos(math.radians(10.0))


@dataclass
class Grosor:
    diam_in: Optional[float] = None
    fuente: str = ""                           # rotulo | paredes | rotulo+paredes | rotulo≠paredes | mezcla
    textos: List[str] = field(default_factory=list)
    material: str = ""
    paredes_in: Optional[float] = None
    paredes: str = ""                          # interior | exterior (ancho de las paredes respecto al diámetro)
    rotulos_in: List[float] = field(default_factory=list)   # los diámetros de sus rótulos


def _dist_pl(p: Pt, pts: Sequence[Pt]) -> float:
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
        best = min(best, math.hypot(a[0] + t * vx - p[0], a[1] + t * vy - p[1]))
    return best


def _cabeza(cadena: Sequence[Pt], punta: Pt, zoom: float):
    """El final de la guía con flecha: desde `FLECHA_MAX_PT` antes de la base de la flecha hasta
    su punta; None si la guía no tiene flecha rellena."""
    if len(cadena) < 2 or math.hypot(cadena[-1][0] - punta[0], cadena[-1][1] - punta[1]) <= 0.5 * zoom:
        return None
    a, b = cadena[-2], cadena[-1]
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    k = min(1.0, FLECHA_MAX_PT * zoom / L)
    return (b[0] - (b[0] - a[0]) * k, b[1] - (b[1] - a[1]) * k), punta


def _encimadas(lineas_pl: Sequence, p: Pt, zoom: float) -> List[int]:
    """Las líneas (índices) que junto a p van paralelas y a menos de `SOLAPE_PT` de la primera:
    una tubería dibujada dos veces, no dos tuberías (no caben a esa distancia)."""
    if not lineas_pl:
        return []
    def pie(pl):
        _s, _d, i = P.proyeccion(pl, p)
        a, b = pl[i], pl[i + 1]
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy or 1.0
        t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
        return a[0] + t * vx, a[1] + t * vy
    u0, q0 = P.rumbo_en(lineas_pl[0], p), pie(lineas_pl[0])
    out = [0]
    for k, pl in enumerate(lineas_pl[1:], 1):
        u, q = P.rumbo_en(pl, p), pie(pl)
        if abs(u0[0] * u[0] + u0[1] * u[1]) >= SOLAPE_COS and \
                math.hypot(q[0] - q0[0], q[1] - q0[1]) <= SOLAPE_PT * zoom:
            out.append(k)
    return out


def asignar_rotulos(lineas_pl: Sequence, puntas, utilidad: str, px_por_in: float, zoom: float,
                    paredes_in: Optional[Sequence[Optional[float]]] = None,
                    paredes_junto: Optional[Callable[[int, Pt], Optional[float]]] = None,
                    tinta: Optional[Sequence[Optional[str]]] = None) -> Dict[int, List[Rotulo]]:
    """{índice de la línea: [rótulos]} — cada guía de un rótulo, a la línea donde cae su punta.

    Una punta en la UNIÓN de un lateral con la principal toca las dos. Primero van los rótulos
    sin duda (una sola línea a tiro, o una claramente más cerca); después los de una unión, a la
    línea que YA dice ese diámetro (por otros rótulos o por sus paredes) y nunca a la que dice
    otro. Si aun así quedan dos, el rótulo no se usa. Las paredes que deciden son las de JUNTO a
    la punta (`paredes_junto`): una principal que cambia de 84" a 81" no las tiene de un solo
    diámetro en toda su ruta. `tinta` = la utilidad de la tinta donde cae cada punta
    (`recognition_grosor_tinta`): un rótulo que no nombra su utilidad (solo su material) no va a
    una línea de esta si la punta cae sobre la de otra."""
    out: Dict[int, List[Rotulo]] = defaultdict(list)
    paredes_in = list(paredes_in or [None] * len(lineas_pl))
    junto = paredes_junto or (lambda i, _p: paredes_in[i])
    justo = PUNTA_HOLGURA_PT * zoom
    dudosos, estaciones = [], []
    for k, (r, cadena, punta) in enumerate(puntas):
        if not es_de(r, utilidad):
            continue
        if not r.utilidad and tinta and k < len(tinta) and tinta[k] not in (None, utilidad):
            continue
        tol = justo + 0.5 * r.pulg * px_por_in
        cands = sorted((d, i) for i, d in ((i, _dist_pl(punta, pl)) for i, pl in enumerate(lineas_pl))
                       if d <= tol)
        cabeza = _cabeza(cadena, punta, zoom) if not cands else None
        if cabeza:
            # la flecha PASADA de largo: la guía cruza la línea justo antes de su flecha y la punta
            # queda más allá (DU06 h.11, «EX.18" RCP SD, LACFCD (D-10469) REMOVE»: la punta a 11 pt
            # de su lateral); vale si es la ÚNICA línea que cruza
            cruzan = [i for i, pl in enumerate(lineas_pl) if P.dist_tramo_linea(*cabeza, pl) <= 0.5 * zoom]
            if len(cruzan) == 1:
                cands = [(0.0, cruzan[0])]
        if not cands:
            continue
        if r.union:
            # «JOIN EX. 84" RCP SD / STA 549+55.37 / CB LAT 208», «JOIN TO EX.78" RCP SD / STA
            # 40+63.38»: rótulo de una UNIÓN, el diámetro de la tubería EXISTENTE a la que se une
            # algo ahí. La flecha suele caer en el lateral que se une, no en esa tubería (DU06
            # h.14: en la punta de arriba del lateral de 18"), así que solo CONFIRMA: va a la
            # línea que ya dice ese diámetro (sus paredes junto a la punta u otros rótulos). Un
            # rótulo con estación que no es de unión («EXIST 18" VCP SEWER / STA 0+44.33 /
            # ENCASEMENT END», DU08 h.38) es de la tubería a la que apunta, como cualquier otro
            estaciones.append((r, cands, punta))
            continue
        if len(cands) == 1 or cands[1][0] - cands[0][0] > justo:
            if r not in out[cands[0][1]]:
                out[cands[0][1]].append(r)
        else:
            dudosos.append((r, cands, punta))
    def dice(i, punta):
        vals = {o.pulg for o in out.get(i, ())}
        w = junto(i, punta)
        if w is not None:
            vals.add(w)
        return vals

    for r, cands, punta in dudosos:
        # la MISMA tubería dibujada dos veces (la existente y la propuesta que la reemplaza, una
        # encima de la otra: DU06 h.12/h.13): el rótulo es de las dos si ninguna dice otro
        encima = _encimadas([lineas_pl[c[1]] for c in cands], punta, zoom)
        encima = [cands[k] for k in encima]
        if len(encima) > 1:
            for c in encima:
                if dice(c[1], punta) <= {r.pulg} and r not in out[c[1]]:
                    out[c[1]].append(r)
            continue
        # «ya dice ese diámetro» = entre lo que dice: antes de partirla, la principal que pasa de
        # 84" a 81" dice los dos y el rótulo de 84" de su unión se iba al lateral (compuesta DU06)
        iguales = [c for c in cands if r.pulg in dice(c[1], punta)]
        libres = [c for c in cands if not dice(c[1], punta)]
        elegido = iguales[0] if len(iguales) == 1 else (libres[0] if not iguales and len(libres) == 1 else None)
        if elegido is not None and r not in out[elegido[1]]:
            out[elegido[1]].append(r)
    for r, cands, punta in estaciones:
        iguales = [c for c in cands if r.pulg in dice(c[1], punta)]
        if len(iguales) == 1 and r not in out[iguales[0][1]]:
            out[iguales[0][1]].append(r)
    return out


def nominal(medida_in: float) -> Optional[float]:
    v = min(NOMINALES_IN, key=lambda n: abs(n - medida_in))
    return float(v) if abs(v - medida_in) <= NOMINAL_TOL_IN else None


def paredes(pts: Sequence[Pt], muros: Sequence[Tuple[Pt, Pt]], px_por_in: float,
            zoom: float, minimo: int = 3) -> Optional[float]:
    """Diámetro interior por las paredes a cada lado de la línea de centro (nominal), o None."""
    votos: Counter = Counter()
    n = 0
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(vx, vy)
        if L < 4.0 * zoom:
            continue
        ux, uy = vx / L, vy / L
        nx, ny = -uy, ux
        pasos = max(1, int(L // (PARED_PASO_PT * zoom)))
        for s in range(pasos):
            t = (s + 0.5) / pasos
            c = (a[0] + vx * t, a[1] + vy * t)
            lados = {1: math.inf, -1: math.inf}
            for p, q in muros:
                wx, wy = q[0] - p[0], q[1] - p[1]
                W = math.hypot(wx, wy)
                if W < 1e-9 or abs(wx * ux + wy * uy) / W < PARED_PARALELA:
                    continue
                # cruce del rayo normal c + k·n con la pared
                den = nx * wy - ny * wx
                if abs(den) < 1e-12:
                    continue
                k = ((p[0] - c[0]) * wy - (p[1] - c[1]) * wx) / den
                u = ((p[0] - c[0]) * ny - (p[1] - c[1]) * nx) / den
                if not (-1e-6 <= u <= 1 + 1e-6) or abs(k) > PARED_MAX_PT * zoom:
                    continue
                lado = 1 if k > 0 else -1
                if abs(k) > 0.2 * zoom and abs(k) < lados[lado]:
                    lados[lado] = abs(k)
            l1, l2 = lados[1], lados[-1]
            if math.isinf(l1) or math.isinf(l2):
                continue
            if abs(l1 - l2) > PARED_SIMETRIA * max(l1, l2) + 0.5:
                continue
            n += 1
            v = nominal((l1 + l2) / px_por_in)
            if v is not None:
                votos[v] += 1
    if not votos:
        return None
    v, c = votos.most_common(1)[0]
    if c >= min(minimo, PARED_MUESTRAS_MIN) and c >= PARED_ACUERDO * n:
        return v
    return None


def paredes_junto(pts: Sequence[Pt], punta: Pt, muros, px_por_in: float, zoom: float) -> Optional[float]:
    """`paredes` solo en el tramo de la línea junto a la punta (±`JUNTO_PT`)."""
    mejor = None
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        if L2 < 1e-12:
            continue
        t = max(0.0, min(1.0, ((punta[0] - a[0]) * vx + (punta[1] - a[1]) * vy) / L2))
        d = math.hypot(a[0] + t * vx - punta[0], a[1] + t * vy - punta[1])
        if mejor is None or d < mejor[0]:
            mejor = (d, a, b, t, math.sqrt(L2))
    if mejor is None:
        return None
    _d, a, b, t, L = mejor
    v = JUNTO_PT * zoom / L
    t0, t1 = max(0.0, t - v), min(1.0, t + v)
    p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
    p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
    return paredes([p0, p1], muros, px_por_in, zoom, minimo=2)


def exterior(paredes_in: float, diam_in: float) -> bool:
    """¿Es ese ancho de paredes el diámetro EXTERIOR de un tubo de `diam_in`? Pared de un tubo
    de concreto (ASTM C76, de la A a la C: D/12 a D/12 + 1¾"), con margen. DU06 dibuja varios
    laterales de 18" con las paredes a 24" (pared de 3"), y uno a 21"."""
    t = (paredes_in - diam_in) / 2.0
    return diam_in / 12.0 - 0.5 <= t <= diam_in / 12.0 + 2.0


def combinar(rots: Sequence[Rotulo], paredes_in: Optional[float]) -> Grosor:
    g = Grosor(paredes_in=paredes_in)
    if rots:
        vals = Counter(r.pulg for r in rots)
        g.textos = sorted({r.texto for r in rots})
        g.material = (Counter(r.material for r in rots if r.material).most_common(1)[0][0]
                      if any(r.material for r in rots) else "")
        g.rotulos_in = sorted(vals)
        if len(vals) > 1:
            g.fuente = "mezcla"
            return g
        g.diam_in = next(iter(vals))
        if paredes_in is None:
            g.fuente = "rotulo"
        elif abs(paredes_in - g.diam_in) < 0.01:
            g.fuente, g.paredes = "rotulo+paredes", "interior"
        elif exterior(paredes_in, g.diam_in):
            g.fuente, g.paredes = "rotulo+paredes", "exterior"
        else:
            g.fuente = "rotulo≠paredes"                 # manda el rótulo; queda para revisar
        return g
    if paredes_in is not None:
        g.diam_in, g.fuente = paredes_in, "paredes"
    return g


def calibrar(gs: Sequence[Grosor]) -> int:
    """Líneas SOLO con paredes: si en la hoja las paredes de ese ancho resultan siempre el
    diámetro EXTERIOR de un mismo diámetro rotulado (24" ↔ 18" en DU06) y nunca el interior, ese
    es su diámetro; si en la hoja hay un rótulo junto a paredes de ese ancho por DENTRO, quedan
    confirmadas como interiores (`paredes` = interior). Devuelve cuántas cambian."""
    ext: Dict[float, set] = defaultdict(set)
    inte = set()
    for g in gs:
        if g.fuente == "rotulo+paredes":
            if g.paredes == "exterior":
                ext[g.paredes_in].add(g.diam_in)
            else:
                inte.add(g.paredes_in)
    n = 0
    for g in gs:
        if g.fuente != "paredes":
            continue
        if g.paredes_in in inte:
            g.paredes = "interior"
        elif len(ext.get(g.paredes_in, ())) == 1:
            g.diam_in, g.paredes = next(iter(ext[g.paredes_in])), "exterior"
            n += 1
    return n


def seguro(g: Grosor) -> bool:
    """¿Se pone el diámetro sin dudas? (pedido del usuario 2026-10-22: lo que no es seguro no se
    pone; queda el de por defecto y un aviso en el editor). Un rótulo con su guía (sus paredes, si
    las tiene, coinciden por dentro o por fuera) sí; paredes solas, solo si la hoja confirma cómo
    las dibuja (`calibrar`): un rótulo junto a paredes de ese ancho por dentro, o por fuera de un
    mismo diámetro. Las paredes de 24" sin más pueden ser un 24" o las de afuera de un 18"."""
    if g.fuente in ("rotulo", "rotulo+paredes"):
        return True
    return g.fuente == "paredes" and g.paredes in ("interior", "exterior")


def candidatos(g: Grosor) -> List[float]:
    """Los diámetros que dice el plano para una línea dudosa (para el aviso)."""
    vals = list(g.rotulos_in)
    if g.paredes_in is not None and g.paredes_in not in vals:
        vals.append(g.paredes_in)
    return sorted(vals)


# ── en `recognize_page` ─────────────────────────────────────────────────
def muros(page, px: Callable[[Pt], Pt], utilidad: str, ocultas=(), dibujos=None) -> List[Tuple[Pt, Pt]]:
    """Rectas de las capas de PAREDES (`-WALL`) de la utilidad."""
    from hoja import pdf_layers, pdf_styles
    ocultas = set(ocultas or ())
    out = []
    for d in (pdf_styles.drawings(page) if dibujos is None else dibujos):
        capa = d.get("layer") or ""
        if capa in ocultas or "WALL" not in capa.upper() or pdf_layers.utility_of(capa) != utilidad:
            continue
        for it in d.get("items") or ():
            if it[0] == "l":
                out.append((px((it[1].x, it[1].y)), px((it[2].x, it[2].y))))
    return out


@dataclass
class Hoja:
    rotulos: List[Rotulo]
    puntas: list
    muros: List[Tuple[Pt, Pt]]
    tinta: list = field(default_factory=list)  # utilidad de la tinta en cada punta (o None)
    perfiles: list = field(default_factory=list)  # `recognition_grosor_perfiles.PerfilLateral` de la hoja


def leer_hoja(page, px: Callable[[Pt], Pt], zoom: float, utilidad: str, ocultas=(),
              perfiles: Sequence[Tuple[float, float, float, float]] = ()) -> Hoja:
    """Rótulos, guías y paredes de la hoja para una utilidad. `perfiles` = cajas (px) de las
    vistas de perfil: sus rótulos no son de la planta («L=29.77', 18" RCP SD» y los cruces).
    Rótulos horizontales y girados 90° (`recognition_grosor_marcos`)."""
    from hoja import pdf_styles
    from reconocimiento import recognition_grosor_marcos as marcos
    perfiles = tuple(tuple(round(float(v), 3) for v in b) for b in perfiles or ())
    dibujos = pdf_styles.drawings(page)

    def fuera(q):
        return any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in perfiles)

    def calcular():
        from reconocimiento import recognition_grosor_perfiles as perfiles_mod
        from reconocimiento.recognition_grosor_guias import capas_de_texto
        from reconocimiento.recognition_grosor_tinta import utilidades_en_puntas
        lineas = lineas_texto(page, px, zoom)
        gs = guias(page, px, zoom, ocultas, dibujos) if any(diametros_de(l[0]) for l in lineas) else None
        todos, puntas_todas = marcos.leer(lineas, gs, zoom)
        # los rótulos de las vistas de perfil no son de la planta: dicen los cruces de sus laterales
        en_perfil = {id(r) for r in todos if perfiles and fuera(((r.bbox[0] + r.bbox[2]) / 2.0,
                                                                  (r.bbox[1] + r.bbox[3]) / 2.0))}
        rots = [r for r in todos if id(r) not in en_perfil]
        puntas = [x for x in puntas_todas if id(x[0]) not in en_perfil]
        laterales = perfiles_mod.leer(lineas, [r for r in todos if id(r) in en_perfil],
                                      [x for x in puntas_todas if id(x[0]) in en_perfil], perfiles, zoom)
        tinta = utilidades_en_puntas(dibujos, px, zoom, [p for _r, _c, p in puntas], capas_de_texto(page), ocultas)
        return rots, puntas, tinta, laterales
    # rótulos y guías no dependen de la utilidad: una vez por hoja (y por transformación) para
    # todas dentro de `pdf_styles.lectura_unica`
    huella = tuple(round(v, 6) for q in (px((0.0, 0.0)), px((1000.0, 0.0)), px((0.0, 1000.0))) for v in q)
    rots, puntas, tinta, laterales = pdf_styles.memo(
        page, ("grosor_puntas", huella, tuple(sorted(ocultas or ())), perfiles), calcular)
    return Hoja(rots, puntas, muros(page, px, utilidad, ocultas, dibujos), tinta, laterales)


def _piezas(pl, rots: Sequence[Rotulo], puntas, zoom: float):
    """[(pieza, sus rótulos)] de una línea con rótulos de varios diámetros partida en el nodo
    donde cambia (`recognition_grosor_partir`), o None. Cada rótulo va a la pieza de su ZONA (un
    «JOIN EX. 18"» en la misma esquina donde se parte es de la zona de 18", aunque su punta caiga
    un pelo después)."""
    marcas, suyos = [], []
    for r in rots:
        cerca = [P.proyeccion(pl.pts_pdf, p) for rr, _c, p in puntas if rr is r]
        if cerca:
            marcas.append((min(cerca, key=lambda m: m[1])[0], r.pulg))
            suyos.append(r)
    cortes = P.vertices_de_corte(pl.pts_pdf, pl.kinds, marcas, zoom)
    if not cortes:
        return None
    out = [(q, []) for q in P.partir(pl, cortes)]
    for r, z in zip(suyos, P.zonas(marcas)):
        if r not in out[z][1]:
            out[z][1].append(r)
    return out


def aplicar(lineas: Sequence, hoja: Hoja, utilidad: str, zoom: float, scale_ft_per_pt: float) -> dict:
    """Pone `grosor` a cada línea (y `diam_in`, si no tenía, cuando el plano lo dice SIN dudas):
    `grosor["estado"]` = «leido» (el diámetro se pone), «dudoso» (el plano dice algo pero no es
    seguro: `candidatos`, el diámetro no se pone) o «sin_dato» (el plano no lo dice). Devuelve
    {"con": líneas con diámetro, "revisar": dudosas, "sin": sin dato, "partidas": rutas partidas
    donde cambia el diámetro, "piezas": {id(línea): [sus piezas]}}: quien llama pone las piezas en
    lugar de la línea."""
    cuenta = {"con": 0, "revisar": 0, "sin": 0, "partidas": 0, "piezas": {}}
    lineas = [pl for pl in lineas if len(pl.pts_pdf) >= 2]
    if not lineas:
        return cuenta
    if not (hoja.puntas or hoja.muros) or not scale_ft_per_pt:
        for pl in lineas:
            if pl.diam_in is None:
                pl.grosor = {"estado": "sin_dato"}
                cuenta["sin"] += 1
        return cuenta
    px_por_in = zoom / (scale_ft_per_pt * 12.0)
    pts = [pl.pts_pdf for pl in lineas]
    par = [paredes(p, hoja.muros, px_por_in, zoom) if hoja.muros else None for p in pts]
    def junto(i, punta):
        return paredes_junto(pts[i], punta, hoja.muros, px_por_in, zoom) if hoja.muros else None
    asig = asignar_rotulos(pts, hoja.puntas, utilidad, px_por_in, zoom, par, junto, hoja.tinta)
    trabajo = []
    for k, pl in enumerate(lineas):
        rots = asig.get(k, [])
        piezas = _piezas(pl, rots, hoja.puntas, zoom) if len({r.pulg for r in rots}) > 1 else None
        if piezas:
            cuenta["piezas"][id(pl)] = [q for q, _r in piezas]
            cuenta["partidas"] += 1
            trabajo += [(q, rq, paredes(q.pts_pdf, hoja.muros, px_por_in, zoom) if hoja.muros else None)
                        for q, rq in piezas]
        else:
            trabajo.append((pl, rots, par[k]))
    gs = [combinar(rots, w) for _pl, rots, w in trabajo]
    calibrar(gs)
    for (pl, rots, _w), g in zip(trabajo, gs):
        partida = id(pl) not in cuenta["piezas"] and any(pl is q for qs in cuenta["piezas"].values() for q in qs)
        # el nombre del lateral sale de SU rótulo («LAT CB-208 / 18" RCP»), no de uno de estación o unión
        # («JOIN EX. 84" RCP SD / STA … / CB LAT 201»: nombra al lateral que se une a la principal)
        nombres = sorted({n for r in rots if not r.estacion for n in r.nombres})
        if not g.fuente:
            if pl.diam_in is None:
                pl.grosor = {"estado": "sin_dato", **({"partida": True} if partida else {})}
                cuenta["sin"] += 1
            continue
        ok = seguro(g)
        pl.grosor = {"estado": "leido" if ok else "dudoso", "diam_in": g.diam_in if ok else None,
                     "fuente": g.fuente, "textos": g.textos, "material": g.material,
                     "paredes_in": g.paredes_in, "paredes": g.paredes}
        if not ok:
            pl.grosor["candidatos"] = candidatos(g)
            cuenta["revisar"] += 1
        if partida:
            pl.grosor["partida"] = True
        if nombres:                                 # «CB-208»: el lateral de un perfil
            pl.grosor["nombres"] = nombres
        if ok and g.diam_in and pl.diam_in is None:
            pl.diam_in = g.diam_in
            cuenta["con"] += 1
    return cuenta
