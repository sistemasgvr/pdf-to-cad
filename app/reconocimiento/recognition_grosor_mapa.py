"""recognition_grosor_mapa.py — el GROSOR (diámetro) de cada tubería en un mapa SIN capas (PURO).

Pedido del usuario 2026-10-23 (QS Water South de Phoenix): lo mismo que el grosor del plano CAD
(`recognition_grosor`), ahora en los PDF vectoriales SIN capas (mapas SIG aplanados): leer todo
lo que el plano dice del diámetro y ponerlo SOLO si es seguro; lo demás queda por defecto con un
aviso en el editor (`nucleo/diametro_plano`, mismo `grosor["estado"]` que el CAD). Es un
complemento: ningún vértice se mueve (una ruta con dos diámetros se parte en un nodo, como en el
CAD) y las líneas, bóvedas y acometidas no cambian.

Cómo lo dice un mapa de Phoenix: cada tramo lleva su rótulo PARALELO y pegado a la línea (el
texto se lee por la forma de las letras, `hoja.texto_pdf`):
  · tubería: «8"», «12" DIP», «12" DIP (CP)», «6" DIP FL», «8" Unk», «18" RGRCP»… (`leer`): el
    diámetro y, si lo dice, el material. NO son de la tubería: «72" STEEL CASING» (la camisa),
    «2" ARV» / «2" BLOW OFF» (accesorios), «MH 48"»;
  · acometida: «278' 2"» / «2" 62'» (estación y diámetro), «6" TAP», «TAP IN MH 6"»; la nota de
    la leyenda «All water taps are .75" in diameter unless otherwise noted» da el resto.

`asignar`: cada rótulo va a la línea MÁS CERCANA que corre paralela a él (≤ `DIST_MAX` × tamaño
de letra, ±25°); un rótulo de acometida solo a acometidas. Se mide de COSTADO: un rótulo junto a
la línea, por su distancia a ella; uno escrito pasada la punta, en su prolongación («FIRELINE /
8" DIP» bajo cada una de dos líneas contra incendios a 2 pt), solo si va alineado con ella
(≤ `COLINEAL` × letra de costado). Si OTRA línea paralela está casi igual de cerca (< `AMBIGUO` ×
la distancia: dos tuberías pegadas, la de 54" PCCP y una de 12" a 2.5 pt) el rótulo no se sabe
de cuál es: no cuenta para ninguna y queda como duda de las dos (solo si el texto queda ENTRE las dos:
si las dos quedan del mismo lado, es de la de más cerca).

`aplicar`, por línea: todos sus rótulos dicen lo mismo → «leido» (se pone); dicen cosas distintas
→ si forman ZONAS a lo largo de ella se parte en el nodo entre zonas (`recognition_grosor_partir`:
donde se une otra tubería > fin de un tramo del SIG > quiebre; uno solo de la mejor clase), si no
«dudoso» (`candidatos`); sin rótulos → «dudoso» si un rótulo ambiguo la nombra, «sin_dato» si no.
Una acometida sin rótulo toma la nota de la leyenda («leido», fuente «leyenda»).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reconocimiento import recognition_grosor_partir as P
from reconocimiento import recognition_grosor_tramos as T
from reconocimiento import recognition_indice as indice_mod

Pt = Tuple[float, float]

DIST_MAX = 4.0               # × tamaño de letra: el rótulo va pegado a su línea
PARALELO_MIN = 0.9           # |cos| entre el texto y el tramo (±25°)
AMBIGUO = 1.5                # otra línea paralela a < esto × la distancia: no se sabe de cuál es
AMBIGUO_MIN = 0.25           # …o a menos de esto × letra más que ella
COLINEAL = 0.75              # rótulo pasada la punta: de costado ≤ esto × letra (en su prolongación)
NODO_TOL_PT = 0.6            # otra tubería termina en un vértice: ahí se une (= `recognition_ink_lines`)
DIAM_MIN_IN, DIAM_MAX_IN = 0.5, 144.0
ACOMETIDA_MAX_IN = 12.0      # «MH 48"» no es una acometida de 48"
ACOMETIDA_PLANA_IN = 2.0     # un rótulo sin estación («2"») va a una acometida solo hasta esto (o la nota
                             # de la leyenda): «12" DIP» junto a un trocito de acometida es de una tubería
MAX_TEXTOS = 6
LETRA_MIN = 0.5              # × letra típica de los rótulos de la hoja: más chico es la referencia a un
                             # detalle («W-16-19-1»: el mapa en miniatura con sus rótulos), no la hoja

# Lo que puede seguir al diámetro en el rótulo de una tubería (en mayúsculas). MATERIALES se
# guarda; CALIFICATIVOS no cambia nada (catódica, línea contra incendios, «per» + plano…).
MATERIALES = {"DIP", "CIP", "PCCP", "PCPP", "ACP", "RCP", "RGRCP", "CP", "CCP", "STL", "STEEL", "PVC",
              "HDPE", "CU", "GALV", "VCP", "CMP", "CIPP", "ADS", "UNK", "TRANS", "MODPSD"}
CALIFICATIVOS = {"(CP)", "FL", "FIRELINE", "PIPE", "LINE", "PER", "FORCE", "MAIN", "MOD", "PSD"}
NO_TUBO = {"CASING", "ARV", "BLOW", "OFF", "BO", "MH", "CO", "VALVE", "VLV", "HYD", "FH", "METER", "SLEEVE",
           "TAP", "STUB", "PLUG", "CAP", "REDUCER", "RED", "BEND", "TEE"}
_NUM = r"(\d{1,3}(?:\.\d+)?)"
RX_TUBO = re.compile(r'^\s*' + _NUM + r'\s*"\s*(.*?)\s*$')
RX_CODIGO = re.compile(r"^[\d-]+$")                                       # «DIP PER 15-1989-0039»
RX_TAP = [re.compile(p) for p in (
    r"""^\s*\d+\s*'\s*""" + _NUM + r'''\s*"\s*(?:TAP)?\s*$''',             # «278' 2"», «12' 4" TAP»
    r'''^\s*''' + _NUM + r'''\s*"\s*(?:TAP)?\s*\d+\s*'\s*$''',             # «2" 62'», «4" TAP 12'»
    r'''^\s*''' + _NUM + r'''\s*"\s*TAP(?:\s+IN\s+(?:MH|CO))?\s*$''',      # «6" TAP», «6" TAP IN MH»
    r'''^\s*(?:TAP\s+)?IN\s+(?:MH|CO)\s+''' + _NUM + r'''\s*"\s*([A-Z]{2,6})?\s*$''',   # «TAP IN MH 6"»
)]


@dataclass
class RotuloMapa:
    centro: Pt
    dir: Pt
    tam: float                  # tamaño de letra (pt de la hoja o px)
    largo: float                # largo del texto (mismas unidades)
    pulg: float
    material: str
    acometida: bool
    texto: str
    pieza: int = 0              # pieza de una hoja compuesta (por el orden de dibujo); 0 en una suelta


def leer(texto: str) -> Optional[Tuple[float, str, bool]]:
    """(pulgadas, material, es_de_acometida) de un rótulo de diámetro, o None si no lo es."""
    t = " ".join((texto or "").upper().split())
    for rx in RX_TAP:
        m = rx.match(t)
        if m:
            d = float(m.group(1))
            ok = DIAM_MIN_IN <= d <= ACOMETIDA_MAX_IN
            return (d, (m.group(2) or "") if m.lastindex and m.lastindex >= 2 else "", True) if ok else None
    m = RX_TUBO.match(t)
    if not m:
        return None
    d = float(m.group(1))
    if not DIAM_MIN_IN <= d <= DIAM_MAX_IN:
        return None
    material = ""
    for w in m.group(2).split():
        if w in MATERIALES and not material:
            material = w
        elif w in NO_TUBO or not (w in MATERIALES or w in CALIFICATIVOS or RX_CODIGO.match(w)):
            return None                   # la camisa, un accesorio o algo que no se entiende
    return d, material, False


def _caja(c) -> Tuple[Pt, float]:
    """(centro, largo) del texto por la TINTA de sus letras (el origen de una letra Type3 no
    siempre está sobre su línea base: un rótulo vertical de acometida salía 1.4 pt corrido); sin
    tinta, por la línea base subida media altura de letra."""
    d = c.dir
    up = (d[1], -d[0])
    esq = [(x, y) for g in c.glifos if g.tinta is not None and (g.letra or " ").strip()
           for x in (g.tinta[0], g.tinta[2]) for y in (g.tinta[1], g.tinta[3])]
    if not esq:
        L = math.hypot(c.fin[0] - c.origen[0], c.fin[1] - c.origen[1])
        return ((c.origen[0] + c.fin[0]) / 2.0 + d[1] * 0.35 * c.tam,
                (c.origen[1] + c.fin[1]) / 2.0 - d[0] * 0.35 * c.tam), L
    us = [x * d[0] + y * d[1] for x, y in esq]
    vs = [x * up[0] + y * up[1] for x, y in esq]
    # las cajas de tinta están alineadas a los ejes: en un texto inclinado incluyen algo de más
    # a cada lado, igual en los dos: el centro no cambia
    u, v = (min(us) + max(us)) / 2.0, (min(vs) + max(vs)) / 2.0
    return (u * d[0] + v * up[0], u * d[1] + v * up[1]), max(us) - min(us)


def rotulos(page) -> List[RotuloMapa]:
    """Rótulos de diámetro de la hoja, en coordenadas de la hoja sin girar."""
    import bisect
    from hoja import texto_pdf
    from hoja.leyenda_mapa_lectura import inicios_de_piezas
    inicios = inicios_de_piezas(page) or []
    out: List[RotuloMapa] = []
    for c in texto_pdf.corridas(page):
        got = leer(c.texto)
        if got is None:
            continue
        centro, largo = _caja(c)
        seq = c.glifos[0].seqno if c.glifos else -1
        out.append(RotuloMapa(centro, (float(c.dir[0]), float(c.dir[1])), float(c.tam), largo, got[0],
                              got[1], got[2], c.texto, bisect.bisect_right(inicios, seq) if inicios else 0))
    return sin_miniaturas(out)


def sin_miniaturas(rots: Sequence[RotuloMapa]) -> List[RotuloMapa]:
    """Sin los rótulos de letra mucho más chica que la típica de su hoja (`LETRA_MIN`; en una hoja
    compuesta, la de su pieza: dos mapas pueden ir a escalas distintas)."""
    tipica = {}
    for pz in {r.pieza for r in rots}:
        tams = sorted(r.tam for r in rots if r.pieza == pz)
        tipica[pz] = tams[len(tams) // 2]
    return [r for r in rots if r.tam >= LETRA_MIN * tipica[r.pieza]]


def a_px(rots: Sequence[RotuloMapa], px: Callable[[Pt], Pt], zoom: float) -> List[RotuloMapa]:
    out = []
    for r in rots:
        q, e = px(r.centro), px((r.centro[0] + r.dir[0], r.centro[1] + r.dir[1]))
        L = math.hypot(e[0] - q[0], e[1] - q[1]) or 1.0
        out.append(replace(r, centro=q, dir=((e[0] - q[0]) / L, (e[1] - q[1]) / L), tam=r.tam * zoom,
                           largo=r.largo * zoom))
    return out


def _cerca(r: RotuloMapa, pts: Sequence[Pt]) -> Optional[Tuple[float, float, float, bool, int]]:
    """(distancia del centro del rótulo a la polilínea, distancia de COSTADO, |cos| con el tramo
    más cercano, ¿alineado?, lado). De costado = la distancia, salvo pasada una punta (el texto no
    alcanza la línea): ahí, la distancia a la recta del último tramo, y solo está «alineado» (en
    su prolongación) si es ≤ `COLINEAL` × letra. Lado = de qué lado del texto queda la línea (±1;
    0 si pasa por él)."""
    c, d = r.centro, r.dir
    best = None
    n = len(pts)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(vx, vy)
        if L < 1e-9:
            continue
        u = ((c[0] - a[0]) * vx + (c[1] - a[1]) * vy) / (L * L)
        t = max(0.0, min(1.0, u))
        dist = math.hypot(a[0] + t * vx - c[0], a[1] + t * vy - c[1])
        if best is None or dist < best[0]:
            pasa = ((-u if i == 0 and u < 0 else 0.0) + (u - 1.0 if i == n - 2 and u > 1 else 0.0)) * L
            lado = abs((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / L if pasa > 0 else dist
            # el texto llega a la punta (o empieza a menos de una letra de ella: la acometida
            # reconocida termina antes que su trazo y el rótulo va al costado de lo que sigue)
            junto = pasa <= r.largo / 2.0 + r.tam
            qx, qy = a[0] + t * vx, a[1] + t * vy
            cruz = d[0] * (qy - c[1]) - d[1] * (qx - c[0])
            signo = 0 if abs(cruz) < 1e-6 * max(1.0, r.tam) else (1 if cruz > 0 else -1)
            best = (dist, lado, abs(vx * d[0] + vy * d[1]) / L, junto or lado <= COLINEAL * r.tam, signo)
    return best


def asignar(lineas: Sequence, rots: Sequence[RotuloMapa], es_acometida: Callable[[object], bool],
            diam_acometida_in: Optional[float] = None):
    """({k: rótulos de la línea k}, {k: rótulos que quizá son de k}, {id(rótulo): líneas a su alcance
    en cualquier rumbo}); ver el docstring. Un rótulo
    que no es SEGURO de ninguna (otra línea casi igual de cerca, o pasado la punta sin ir alineado
    con ella) queda como duda de todas las que podría ser: ninguna toma por defecto lo que el plano
    quizá dice de ella."""
    pts = [pl.pts_pdf for pl in lineas]
    acometida = [bool(es_acometida(pl)) for pl in lineas]
    alcance = DIST_MAX * max((r.tam for r in rots), default=0.0)
    indice = indice_mod.IndiceTramos([list(zip(p, p[1:])) for p in pts], alcance)
    suyos: Dict[int, List[RotuloMapa]] = {}
    dudas: Dict[int, List[RotuloMapa]] = {}
    alcance_de: Dict[int, List[int]] = {}
    tope_plano = max(ACOMETIDA_PLANA_IN, diam_acometida_in or 0.0)
    for r in rots:
        lim = DIST_MAX * r.tam
        cand, sueltas, cruzadas = [], [], []
        for k in sorted({k for k, _j in indice.cerca(r.centro)}):
            if (not acometida[k] and r.acometida) or (acometida[k] and r.pulg > tope_plano and not r.acometida):
                continue
            got = _cerca(r, pts[k])
            if got is None or got[0] > lim:
                continue
            alcance_de.setdefault(id(r), []).append(k)
            if got[2] < PARALELO_MIN:
                if not acometida[k]:
                    cruzadas.append((got[0], k))
                continue
            (cand if got[3] else sueltas).append((got[1], k, got[4]))
        cand.sort()
        otras = []
        if cand:
            d1, _k1, s1 = cand[0]
            # otra línea paralela casi igual de cerca AL OTRO LADO del texto (el rótulo entre dos
            # tuberías pegadas; si las dos quedan del mismo lado, es de la de más cerca: dos de 8" a
            # 1.3 pt con su rótulo cada una por fuera, QS Sewer North h.3), o una de la red en otro
            # rumbo MÁS cerca (el «12" CIP» escrito en horizontal junto a una tubería vertical corta,
            # a 5 pt de la principal de 54"; un ramal que nace en la línea nunca está más cerca)
            otras = [k for d, k, sg in cand[1:] if d - d1 < max((AMBIGUO - 1.0) * d1, AMBIGUO_MIN * r.tam)
                     and (sg != s1 or sg == 0)]
            otras += [k for d, k in cruzadas if k != cand[0][1] and d < d1 and k not in otras]
        if cand and not otras:
            suyos.setdefault(cand[0][1], []).append(r)
            continue
        for k in [k for _d, k, _s in cand[:1]] + otras + ([] if cand else [k for _d, k, _s in sueltas]):
            dudas.setdefault(k, []).append(r)
    return suyos, dudas, alcance_de


def _clases(lineas: Sequence, red: Sequence[int], zoom: float) -> Dict[int, List[str]]:
    """Tipo de cada vértice para partir (en los términos de `recognition_grosor_partir.NODOS`):
    «vault» = buzón; «junction» = otra tubería de la red termina o pasa por ahí (unión); «corner» =
    fin de un tramo del SIG (dos trazos seguidos); «bend» = vértice del trazo."""
    tol = NODO_TOL_PT * zoom
    puntas = [q for k in red for q in lineas[k].pts_pdf]       # puntas y vértices (un cruce)
    duenos = [k for k in red for _ in lineas[k].pts_pdf]
    ip = indice_mod.IndicePuntos(puntas, tol)
    out = {}
    for k in red:
        pl = lineas[k]
        cl = []
        for i, (q, kind) in enumerate(zip(pl.pts_pdf, pl.kinds)):
            if kind == "vault":
                cl.append("vault")
            elif 0 < i < len(pl.pts_pdf) - 1 and any(duenos[j] != k and math.dist(q, puntas[j]) <= tol
                                                     for j in ip.cerca(q)):
                cl.append("junction")
            elif kind in ("junction", "tee", "corner"):
                cl.append("corner")
            else:
                cl.append("bend")
        out[k] = cl
    return out


def _textos(rots) -> List[str]:
    return list(dict.fromkeys(r.texto.strip() for r in rots))[:MAX_TEXTOS]


def _grosor(st, rots: Sequence[RotuloMapa], dudas: Sequence[RotuloMapa], partida: bool) -> dict:
    """`grosor` de una línea (o pieza) con estado `st` (`recognition_grosor_tramos.estados`)."""
    extra = {"partida": True} if partida else {}
    if st[0] == "leido":
        mats = {r.material for r in rots if r.material and r.pulg == st[1]}
        return {"estado": "leido", "diam_in": st[1], "fuente": "rotulo",
                "textos": _textos([r for r in rots if r.pulg == st[1]]),
                "material": mats.pop() if len(mats) == 1 else "", **extra}
    if st[0] == "dudoso":
        return {"estado": "dudoso", "diam_in": None, "fuente": st[2], "textos": _textos(list(rots) + list(dudas)),
                "material": "", "candidatos": [float(v) for v in st[1]], **extra}
    return {"estado": "sin_dato", **extra}


class _Tramos:
    """Los tramos de una línea de la red con sus rótulos (`recognition_grosor_tramos`)."""

    def __init__(self, pl, clases: List[str], rs, ds):
        self.pl = pl
        self.lims = T.limites(pl, clases)
        nt = len(self.lims) - 1
        self.por, self.dud = [[] for _ in range(nt)], [[] for _ in range(nt)]
        for r in rs:
            self.por[self.de(r.centro)].append(r)
        for r in ds:
            self.dud[self.de(r.centro)].append(r)
        self.valores = [T.valor([r.pulg for r in x]) for x in self.por]
        # el diámetro de cada tramo antes de resolver conflictos (con el de sus vecinos): lo que
        # «ya dice» esta línea junto a un rótulo de otra (`_explicados`)
        self.antes = T.estados(self.valores, [[r.pulg for r in x] for x in self.por], [[] for _ in self.por])

    def de(self, p) -> int:
        return T.tramo_de(self.pl.pts_pdf, self.lims, p)


def _explicados(tr: "_Tramos", k: int, alcance_de, tramos: Dict[int, "_Tramos"]) -> None:
    """En cada tramo en conflicto, quita los rótulos que el tramo de OTRA línea de la red junto a
    ellos ya dice (por sus rótulos o los de sus vecinos): el «6"» escrito en horizontal en la punta de una tubería
    vertical de 6", junto a la principal de 8"; el «30" RCP» que el SIG imprimió encima de la línea de
    24" que corre a 1.3 pt de la de 30" (QS Sewer South h.2). Si se irían todos, quedan todos."""
    for f, v in enumerate(tr.valores):
        if v is not T.CONFLICTO:
            continue
        quedan = []
        for r in tr.por[f]:
            otros = [tramos[j] for j in alcance_de.get(id(r), ()) if j != k and j in tramos]
            if not any(o.antes[o.de(r.centro)] == ("leido", r.pulg) for o in otros):
                quedan.append(r)
        if quedan and len(quedan) < len(tr.por[f]):
            tr.por[f] = quedan
            tr.valores[f] = T.valor([r.pulg for r in quedan])


def _red(tr: "_Tramos"):
    """[(vértice inicial, final, grosor)] de una línea de la red, tramo por tramo."""
    ests = T.estados(tr.valores, [[r.pulg for r in x] for x in tr.por], [[r.pulg for r in x] for x in tr.dud])
    partes = T.piezas(tr.lims, ests)
    out = []
    for a, b, st, fs in partes:
        rots = [r for f in fs for r in tr.por[f]]
        dudas = [r for f in fs for r in tr.dud[f]]
        out.append((a, b, _grosor(st, rots, dudas, len(partes) > 1)))
    return out


def _acometida(pl, rs, ds, diam_leyenda: Optional[float]) -> dict:
    """`grosor` de una acometida: su rótulo, o la nota de la leyenda («taps are .75 in»)."""
    v = T.valor([r.pulg for r in rs])
    if v is T.CONFLICTO:
        return _grosor(("dudoso", tuple(sorted({r.pulg for r in rs})), "mezcla"), rs, ds, False)
    if v is not None:
        return _grosor(("leido", v), rs, ds, False)
    otros = sorted({r.pulg for r in ds if r.pulg != diam_leyenda})
    if otros:              # un rótulo que quizá es suyo dice otra cosa que la leyenda
        return _grosor(("dudoso", tuple(sorted(set(otros) | ({diam_leyenda} if diam_leyenda else set()))),
                        "cerca"), rs, ds, False)
    if diam_leyenda:
        return {"estado": "leido", "diam_in": diam_leyenda, "fuente": "leyenda", "textos": [], "material": ""}
    return {"estado": "sin_dato"}


def aplicar(lineas: Sequence, rots: Sequence[RotuloMapa], es_acometida: Callable[[object], bool],
            zoom: float, diam_acometida_in: Optional[float] = None) -> dict:
    """Pone `grosor` (y `diam_in` cuando es seguro) a cada línea. Una ruta que cruza tuberías de
    distinto diámetro NO se parte aquí: queda en `cuenta["partir"]` = {id(línea): (línea, vértices de
    corte, [grosor de cada pieza])} y se parte al final del reconocimiento (`partir`), después de los
    pasos que mueven vértices (los ángulos a 0.25° ven la ruta entera: la geometría no cambia).
    Devuelve {"con", "revisar", "sin" (por pieza), "partidas", "partir", "acometidas": {estado: n}}.
    Las cuentas son de la RED; las acometidas van aparte."""
    cuenta = {"con": 0, "revisar": 0, "sin": 0, "partidas": 0, "partir": {}, "acometidas": Counter()}
    lineas = [pl for pl in lineas if len(pl.pts_pdf) >= 2]
    if not lineas:
        return cuenta
    suyos, dudas, alcance_de = asignar(lineas, rots, es_acometida, diam_acometida_in)
    tap = [bool(es_acometida(pl)) for pl in lineas]
    red = [k for k in range(len(lineas)) if not tap[k]]
    clases = _clases(lineas, red, zoom)
    tramos = {k: _Tramos(lineas[k], clases[k], suyos.get(k, []), dudas.get(k, [])) for k in red}
    for k in red:
        _explicados(tramos[k], k, alcance_de, tramos)
    llave = {"leido": "con", "dudoso": "revisar", "sin_dato": "sin"}
    for k, pl in enumerate(lineas):
        if tap[k]:
            pl.grosor = _acometida(pl, suyos.get(k, []), dudas.get(k, []), diam_acometida_in)
            pl.diam_in = pl.grosor.get("diam_in")
            cuenta["acometidas"][pl.grosor["estado"]] += 1
            continue
        partes = _red(tramos[k])
        for _a, _b, g in partes:
            cuenta[llave[g["estado"]]] += 1
        if len(partes) > 1:
            cuenta["partir"][id(pl)] = (pl, [b for _a, b, _g in partes[:-1]], [g for _a, _b, g in partes])
            cuenta["partidas"] += 1
            pl.grosor, pl.diam_in = {}, None        # cada pieza tendrá el suyo
        else:
            pl.grosor = partes[0][2]
            pl.diam_in = pl.grosor.get("diam_in")
    return cuenta


def partir(lista: list, pendientes: dict) -> None:
    """Pone en `lista`, en lugar de cada línea de `pendientes` (`aplicar`), sus piezas con su grosor.
    Las piezas comparten el vértice de corte (`recognition_grosor_partir.partir`): nada se mueve."""
    if not pendientes:
        return
    out = []
    for pl in lista:
        got = pendientes.get(id(pl))
        if got is None or got[0] is not pl:
            out.append(pl)
            continue
        _pl, cortes, gs = got
        for q, g in zip(P.partir(pl, cortes), gs):
            q.grosor = g
            q.diam_in = g.get("diam_in")
            out.append(q)
    lista[:] = out


def grosor_en(pl, j: int, pendientes: dict) -> dict:
    """El grosor del tramo j (vértices j → j+1) de una línea, partida o no."""
    got = pendientes.get(id(pl))
    if got is None or got[0] is not pl:
        return getattr(pl, "grosor", None) or {}
    import bisect
    return got[2][bisect.bisect_right(got[1], j)]
