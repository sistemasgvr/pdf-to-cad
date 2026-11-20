"""recognition_imagen_rectas.py — la red que viene como IMAGEN, en RECTAS de buzón a buzón (PURO, sin Qt ni fitz).

Pedido del usuario (2026-11-19, Phoenix «QS SD_Indian School»): de las líneas de una red en imagen solo hace falta el
EJE, «todo recto»: nada de vértices que siguen el serrucho de la banda pixelada ni curvas en un quiebre mínimo; un
quiebre de verdad queda como quiebre y los buzones son buzones. Comparado con su trazo a mano (North h.1).

Solo toca las polilíneas de capas de imagen (`PDF_STYLE:["img",…]`); las vectoriales no cambian. Por cada una:

  1. Punta DENTRO de una bóveda (buzón, sumidero) → al CENTRO de la bóveda (vértice «vault»); los vértices que la
     línea tenía dentro de esa misma bóveda se van (el tramo de borde a centro que quedaba torcido).
  2. Fuera la MISMA tubería leída dos veces (los dos bordes de una banda ancha) y los TROZOS con una punta suelta
     que tocan una bóveda o son muy cortos: la rejilla de un sumidero y el borde de un símbolo dejan trocitos.
  3. Dos líneas que se tocan punta con punta sin nada más ahí (ni bóveda ni una tercera línea) = una sola.
  4. Douglas–Peucker con `TOL_PT` entre vértices DUROS (puntas, uniones, T, bóvedas): lo que se aparta menos que eso
     es el serrucho de la banda (≈3.3 pt de ancho en estos mapas) y se va; un quiebre real se aparta más y queda.
  5. Los CODOS que reconoció el núcleo (arco del plano con su radio, la regla de las otras utilidades) se conservan:
     su vértice es la esquina de las tangentes y se dibuja como arco (borrarlos dejaba esa esquina suelta, lejos de la
     tinta: SD South «24" RCP R=244.72»). Un quiebre sin codo queda como quiebre: la importación no lo vuelve curva
     (`pipe["solo_rectas"]`, ver `nucleo/quiebres_curvas`).
  3b. Dos puntas que se miran de frente sobre la misma recta con un hueco (`HUECO_MAX_PT`: texto encima de la línea,
     costura de dos piezas) son la misma tubería: se unen. Una «unión» interior a la que ya no llega otra línea no
     frena el enderezado.
  6. La punta de un ramal que llegaba SOBRE otra línea de imagen (T) se vuelve a poner sobre esa línea ya enderezada.

Una línea que va del borde al centro de la MISMA bóveda se quita. Todo se busca por celdas
(`recognition_imagen_indice`): comparar todo con todo tenía una compuesta de 36 mapas ~2 horas aquí.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from reconocimiento import recognition_imagen_piezas as img_piezas
from reconocimiento import recognition_vault_snap as vault_snap
from reconocimiento.recognition_imagen_indice import Bovedas, Rejilla, dist_en, dist_seg

Pt = Tuple[float, float]

TOL_PT = 1.75                # desvío máximo de la recta (pt): menos = serrucho de la banda (≈ ½ de su ancho de
                             # 3.3 pt), se endereza; con 1.25 quedaban quiebres de 1.3 pt (SD South h.4/h.5)
BOVEDA_PAD_PT = 2.0          # una punta a ≤ esto del contorno de una bóveda está «en» la bóveda (½ banda)
REPETIDA_PT = 2.5            # la misma tubería leída dos veces corre a ≤ esto de la otra …
REPETIDA_FRAC = 0.85         # … en esta fracción de su largo
TROZO_PT = 10.0              # una línea más corta con una punta suelta que toca una bóveda es un resto (rejilla) …
TROZO_MIN_PT = 5.0           # … y, aunque no toque ninguna, si mide menos que esto
T_SOBRE_PT = 0.5             # una punta a ≤ esto de otra línea estaba sobre ella (T)
HUECO_MAX_PT = 30.0          # dos puntas que se miran de frente a ≤ esto (texto encima de la línea, costura de
HUECO_LADO_PT = 1.5          #   dos piezas) y a ≤ esto de la recta de la otra = la MISMA tubería: se une
HUECO_GIRO_DEG = 10.0        #   (rumbos a ≤ esto, medidos en los últimos `RUMBO_PT` de cada una)
RUMBO_PT = 12.0
CELDA_PT = 8.0               # celda de los índices (`recognition_imagen_indice`)
# (pedido del usuario 2026-11-20, QS SD de Phoenix: «solo nos interesan las líneas de la red»)
PROLONGAR_PT = 15.0          # una punta SUELTA cuyo rumbo choca con otra línea a ≤ esto llega a ella (T): el ramal
PROLONGAR_GIRO_MIN_DEG = 25.0  #   que moría unos pt antes de la principal; con un ángulo de al menos esto (no paralelas)
AISLADA_PT = 12.0            # línea suelta por LAS DOS puntas y más corta = borde de un símbolo (la caja del sumidero)
SIMBOLO_PAD_PT = 1.0         # una punta a ≤ esto de la caja de un símbolo está «en» él
DUROS = {"junction", "tee", "vault"}
PUNTA_A_BOVEDA = {"stop", "edge", "end", "vault", "bend", "corner", "curve", "cut"}


def douglas(pts: Sequence[Pt], tol: float) -> List[int]:
    """Índices que deja Douglas–Peucker (siempre el primero y el último)."""
    n = len(pts)
    if n <= 2:
        return list(range(n))
    quedan = {0, n - 1}
    pila = [(0, n - 1)]
    while pila:
        i, j = pila.pop()
        peor, k_peor = -1.0, -1
        for k in range(i + 1, j):
            d = dist_seg(pts[k], pts[i], pts[j])[0]
            if d > peor:
                peor, k_peor = d, k
        if peor > tol:
            quedan.add(k_peor)
            pila += [(i, k_peor), (k_peor, j)]
    return sorted(quedan)


def _invertir(pts: list, kinds: list, fil: dict):
    """La polilínea al revés: sus codos cambian de índice y de lado (a ↔ b)."""
    n = len(pts)
    canje = {"a": "b", "b": "a", "node_a": "node_b", "node_b": "node_a", "split_a": "split_b", "split_b": "split_a"}
    nf = {n - 1 - i: {canje.get(k, k): v for k, v in f.items()} for i, f in fil.items()}
    return pts[::-1], kinds[::-1], nf


def _sin_vertice(pts: list, kinds: list, fil: dict, i: int) -> dict:
    """Quita el vértice i (EN SITIO pts/kinds); devuelve los codos con sus índices corridos."""
    del pts[i], kinds[i]
    return {(j - 1 if j > i else j): f for j, f in fil.items() if j != i}


def _boveda_de(q: Pt, bovedas: Bovedas, pad: float) -> Optional[dict]:
    dentro = [vg for vg in bovedas.en(q) if vault_snap.vault_contains(vg, q, pad=pad)]
    if not dentro:
        return None
    return min(dentro, key=lambda vg: math.dist(q, vault_snap.vault_centroid(vg)))


def _punta_al_centro(pts: List[Pt], kinds: List[str], fil: dict, bovedas: Bovedas, pad: float, al_final: bool):
    """Lleva la punta (al inicio o al final) al centro de su bóveda; quita los vértices que la línea tenía dentro de
    ella (no un codo). Devuelve (bóveda o None, pts, kinds, codos)."""
    if al_final:
        pts, kinds, fil = _invertir(pts, kinds, fil)
    vg = _boveda_de(pts[0], bovedas, pad) if kinds[0] in PUNTA_A_BOVEDA else None
    if vg is not None and 0 not in fil:
        while (len(pts) > 2 and kinds[1] not in ("junction", "tee") and 1 not in fil
               and vault_snap.vault_contains(vg, pts[1], pad)):
            fil = _sin_vertice(pts, kinds, fil, 1)
        pts[0] = tuple(vault_snap.vault_centroid(vg))
        kinds[0] = "vault"
    if al_final:
        pts, kinds, fil = _invertir(pts, kinds, fil)
    return vg, pts, kinds, fil


def _libre(pl, end: int, rej: Rejilla, tol: float) -> bool:
    """¿La punta no toca nada? (no es bóveda ni cae sobre otra línea de imagen)."""
    return pl.kinds[end] != "vault" and not rej.toca(pl.pts_pdf[end], tol, (pl,))


def _largo(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _sacar(imgs: list, fuera: list, rej: Rejilla) -> None:
    ids = {id(pl) for pl in fuera}
    imgs[:] = [pl for pl in imgs if id(pl) not in ids]
    for pl in fuera:
        rej.quitar(pl)


def _quitar_trocitos(imgs: list, bovedas: Bovedas, zoom: float, rej: Rejilla) -> list:
    """Trocitos (< `TROZO_PT`) con una punta suelta que son restos de la rejilla de un sumidero o del borde de un
    símbolo: tocan una bóveda, o miden menos de `TROZO_MIN_PT`. UNA pasada (repetirla se comía en cadena una tubería
    partida en piezas cortas)."""
    tol = T_SOBRE_PT * zoom
    pad = BOVEDA_PAD_PT * zoom
    malos = []
    for pl in imgs:
        largo = _largo(pl.pts_pdf)
        if largo >= TROZO_PT * zoom or not (_libre(pl, 0, rej, tol) or _libre(pl, -1, rej, tol)):
            continue
        if largo < TROZO_MIN_PT * zoom or any(vault_snap.vault_contains(vg, q, pad)
                                              for q in pl.pts_pdf for vg in bovedas.en(q)):
            malos.append(pl)
    _sacar(imgs, malos, rej)
    return malos


def _muestras(pts, paso: float):
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / paso))
        for i in range(n):
            yield a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
    yield pts[-1]


def _quitar_repetidas(imgs: list, zoom: float, rej: Rejilla) -> list:
    """La misma tubería leída dos veces (los dos bordes de una banda ancha dan dos «ejes» casi encimados): la más
    corta se va si ≥ `REPETIDA_FRAC` de ella corre a ≤ `REPETIDA_PT` de UNA línea más larga."""
    fuera, ids_fuera = [], set()
    r = REPETIDA_PT * zoom
    largos = {id(p): _largo(p.pts_pdf) for p in imgs}
    orden = {id(p): k for k, p in enumerate(imgs)}
    # (dos copias del MISMO largo: se va la primera; antes ninguna, por «más larga» estricto — QS SD North, la
    # conexión del buzón al sumidero salía dos veces en la capa «fino»)
    mayor = lambda b, a: largos[id(b)] > largos[id(a)] + 1e-6 or (  # noqa: E731
        abs(largos[id(b)] - largos[id(a)]) <= 1e-6 and orden[id(b)] > orden[id(a)])
    for a in sorted(imgs, key=lambda p: largos[id(p)]):
        qs = list(_muestras(a.pts_pdf, 0.5 * zoom))
        cerca: dict = {}                               # línea → muestras de `a` a ≤ r de ella
        for q in qs:
            for b, ks in rej.cerca(q, r):
                if b is not a and id(b) not in ids_fuera and mayor(b, a) and dist_en(q, b.pts_pdf, ks)[0] <= r:
                    cerca[id(b)] = cerca.get(id(b), 0) + 1
        if any(n >= REPETIDA_FRAC * len(qs) for n in cerca.values()):
            fuera.append(a)
            ids_fuera.add(id(a))
    _sacar(imgs, fuera, rej)
    return fuera


def _unibles(a, b) -> bool:
    """Misma capa, tipo y estado, y el mismo diámetro — o una de las dos sin diámetro leído: es la misma tubería que
    sigue (SD South, costura de dos piezas en una curva: un lado decía «24\" RCP» y el otro nada)."""
    if id(a) in _PENDIENTES or id(b) in _PENDIENTES:
        return False                       # su diámetro se pone al partirla al final: aún no se sabe (SD South h.4)
    da, db = getattr(a, "diam_in", None), getattr(b, "diam_in", None)
    return (a.layer_ocg == b.layer_ocg and a.kind == b.kind and bool(a.abandoned) == bool(b.abandoned)
            and (da == db or da is None or db is None))


def _unir_una(imgs: list, a, rej: Rejilla, tol: float):
    """La línea que se une de frente con `a` por alguna punta (la une a `a` y la devuelve), o None."""
    for ea in (0, -1):
        q = a.pts_pdf[ea]
        if a.kinds[ea] == "vault":
            continue
        toca = [(o, eo) for o, _ks in rej.cerca(q, tol) if o is not a for eo in (0, -1)
                if math.dist(q, o.pts_pdf[eo]) <= tol]
        if len(toca) != 1:
            continue
        b, eb = toca[0]
        if b.kinds[eb] == "vault" or not _unibles(a, b) or rej.toca(q, tol, (a, b)):
            continue                                   # (una T: la tercera línea pasa por ahí)
        _concatenar(a, ea, b, eb, hueco=False)
        _sacar(imgs, [b], rej)
        rej.poner(a)
        return b
    return None


def _concatenar(a, ea: int, b, eb: int, hueco: bool) -> None:
    """`a` = a + b por las puntas `ea`/`eb` (con sus codos). Sin `hueco`, las dos puntas son el mismo punto (uno solo,
    «bend»); con hueco, el tramo del hueco las une (las dos quedan «bend»)."""
    pa, ka, fa = list(a.pts_pdf), list(a.kinds), dict(a.fillets or {})
    pb, kb, fb = list(b.pts_pdf), list(b.kinds), dict(b.fillets or {})
    if ea == 0:
        pa, ka, fa = _invertir(pa, ka, fa)
    if eb != 0:
        pb, kb, fb = _invertir(pb, kb, fb)
    if hueco:
        off = len(pa)
        a.pts_pdf = pa + pb
        a.kinds = ka[:-1] + ["bend", "bend"] + kb[1:]
    else:
        off = len(pa) - 1
        a.pts_pdf = pa + pb[1:]
        a.kinds = ka[:-1] + ["bend"] + kb[1:]
    a.fillets = {**fa, **{i + off: f for i, f in fb.items()}}
    a.n_segments = getattr(a, "n_segments", 1) + getattr(b, "n_segments", 1)
    if getattr(a, "diam_in", None) is None and getattr(b, "diam_in", None) is not None:
        a.diam_in = b.diam_in                          # (la que no tenía diámetro toma el de la otra, con su grosor)
        a.grosor = getattr(b, "grosor", None)
    elif getattr(a, "grosor", None) is None and getattr(b, "grosor", None) is not None:
        a.grosor = b.grosor


def _rumbo(pts, end: int, largo: float):
    """Rumbo unitario hacia AFUERA de la punta `end`, medido con el punto de la línea a `largo` de ella (o la otra
    punta): el último tramo solo puede ser el serrucho de la banda (SD South «N 62ND DR»: 6 pt torcidos 11°)."""
    seq = pts if end == 0 else pts[::-1]
    p, q, acum = seq[0], seq[-1], 0.0
    for u, v in zip(seq, seq[1:]):
        L = math.dist(u, v)
        if acum + L >= largo:
            t = (largo - acum) / L
            q = (u[0] + t * (v[0] - u[0]), u[1] + t * (v[1] - u[1]))
            break
        acum += L
    L = math.dist(p, q)
    return None if L < 1e-9 else ((p[0] - q[0]) / L, (p[1] - q[1]) / L)


def _pareja_de_hueco(a, ea: int, rej: Rejilla, zoom: float):
    """(b, eb) cuya punta suelta mira de frente a la punta `ea` de `a` sobre su recta, con un hueco ≤ `HUECO_MAX_PT`;
    None si no hay o si dos candidatas están casi igual de cerca (ambigua: no se adivina)."""
    tol = T_SOBRE_PT * zoom
    hmax, lado = HUECO_MAX_PT * zoom, HUECO_LADO_PT * zoom
    cos_max = math.cos(math.radians(HUECO_GIRO_DEG))
    if a.kinds[ea] == "vault" or not _libre(a, ea, rej, tol):
        return None
    ua = _rumbo(a.pts_pdf, ea, RUMBO_PT * zoom)
    if ua is None:
        return None
    q = a.pts_pdf[ea]
    cands = []
    for b, _ks in rej.cerca(q, hmax):
        if b is a or not _unibles(a, b):
            continue
        for eb in (0, -1):
            pb = b.pts_pdf[eb]
            d = math.dist(q, pb)
            ub = _rumbo(b.pts_pdf, eb, RUMBO_PT * zoom)
            if d < 1e-9 or d > hmax or ub is None or b.kinds[eb] == "vault":
                continue
            adelante = ((pb[0] - q[0]) * ua[0] + (pb[1] - q[1]) * ua[1]) / d
            frente = -(ub[0] * ua[0] + ub[1] * ua[1])
            de_lado = abs((pb[0] - q[0]) * ua[1] - (pb[1] - q[1]) * ua[0])
            if adelante >= cos_max and frente >= cos_max and de_lado <= lado and _libre(b, eb, rej, tol):
                cands.append((d, b, eb))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    if len(cands) > 1 and cands[1][1] is not cands[0][1] and cands[1][0] < 1.5 * cands[0][0]:
        return None
    return cands[0][1], cands[0][2]


def _unir_huecos(imgs: list, zoom: float, rej: Rejilla) -> list:
    """Dos puntas SUELTAS que se miran de frente sobre la misma recta, con un hueco ≤ `HUECO_MAX_PT` (texto encima de
    la línea, costura de dos piezas de la compuesta), son la misma tubería: se unen con el tramo del hueco."""
    fuera = []
    i = 0
    while i < len(imgs):
        a = imgs[i]
        par = None
        for ea in (0, -1):
            par = _pareja_de_hueco(a, ea, rej, zoom)
            if par is not None:
                _concatenar(a, ea, par[0], par[1], hueco=True)
                fuera.append(par[0])
                _sacar(imgs, [par[0]], rej)
                rej.poner(a)
                break
        if par is not None:
            i = next(k for k, p in enumerate(imgs) if p is a)
        else:
            i += 1
    return fuera


def _unir_de_frente(imgs: list, zoom: float, rej: Rejilla) -> list:
    """Dos líneas que se tocan punta con punta y nada más pasa por ahí (ni bóveda, ni una tercera línea) son UNA:
    se concatenan (el vértice de la unión queda «bend» y Douglas–Peucker decide si es quiebre). Devuelve las que se
    fueron (absorbidas). Tras unir se sigue con la misma línea: las de antes ya no podían unirse."""
    tol = T_SOBRE_PT * zoom
    fuera = []
    i = 0
    while i < len(imgs):
        a = imgs[i]
        b = _unir_una(imgs, a, rej, tol)
        if b is None:
            i += 1
        else:
            fuera.append(b)
            i = next(k for k, p in enumerate(imgs) if p is a)
    return fuera


def _recta(pl, tol: float, rej: Rejilla, zoom: float) -> None:
    """Douglas–Peucker entre vértices DUROS: puntas, codos, bóvedas, y uniones/T a las que llega otra línea (una
    «unión» que quedó sin pareja ya no lo es)."""
    pts, kinds, fil = pl.pts_pdf, pl.kinds, dict(pl.fillets or {})
    r = T_SOBRE_PT * zoom

    def duro(i):
        if i in fil or kinds[i] == "vault":
            return True
        return kinds[i] in DUROS and rej.toca(pts[i], r, (pl,))
    duros = [0] + [i for i in range(1, len(pts) - 1) if duro(i)] + [len(pts) - 1]
    queda = []
    for a, b in zip(duros, duros[1:]):
        queda += [a + k for k in douglas(pts[a:b + 1], tol)][:-1]
    queda.append(len(pts) - 1)
    nuevo = {v: k for k, v in enumerate(queda)}
    pl.pts_pdf = [pts[i] for i in queda]
    pl.kinds = ["bend" if kinds[i] == "curve" and i not in fil else kinds[i] for i in queda]
    pl.fillets = {nuevo[i]: f for i, f in fil.items() if i in nuevo}


def _t_sobre_su_linea(imgs: list, zoom: float, tol_pt: float) -> None:
    rej = Rejilla(imgs, CELDA_PT * zoom)
    r_t, r_max = T_SOBRE_PT * zoom, (tol_pt + T_SOBRE_PT) * zoom
    for pl in imgs:
        for end in (0, -1):
            if pl.kinds[end] not in ("tee", "junction"):
                continue
            q = pl.pts_pdf[end]
            if any(o is not pl and min(math.dist(q, o.pts_pdf[0]), math.dist(q, o.pts_pdf[-1])) <= r_t
                   for o, _ks in rej.cerca(q, r_t)):
                continue                               # punta con punta: ya coinciden
            cerca = [(dist_en(q, o.pts_pdf, ks), o) for o, ks in rej.cerca(q, r_max) if o is not pl]
            if cerca:
                (d, p), _o = min(cerca, key=lambda c: c[0][0])
                if d <= r_max:
                    pl.pts_pdf[end] = p


def simbolos_de(page, polylines, px) -> list:
    """Cajas (px de la vista) de los SÍMBOLOS de la imagen (`PDF_STYLE:["img","sym",…]`) del color de las líneas de
    imagen de `polylines`, asignados o no a una utilidad: `_quitar_aisladas` deja la línea que va de un símbolo a OTRO
    (la conexión del buzón «M» al sumidero), no el borde de la caja de uno."""
    from hoja import imagen_ejes as IE, pdf_styles
    rgbs = {IE.rgb_de(pl.layer_ocg) for pl in polylines if img_piezas.es_capa_imagen(getattr(pl, "layer_ocg", "") or "")}
    rgbs.discard(None)
    if not rgbs:
        return []
    out = []
    for p in pdf_styles.drawings(page):
        ly = p.get("layer") or ""
        if not IE.es_imagen(ly) or IE.tipo_imagen(ly) != "sym" or IE.rgb_de(ly) not in rgbs:
            continue
        r = p["rect"]
        qs = [px((r[0], r[1])), px((r[2], r[1])), px((r[0], r[3])), px((r[2], r[3]))]
        out.append((min(q[0] for q in qs), min(q[1] for q in qs), max(q[0] for q in qs), max(q[1] for q in qs)))
    return out


def enderezar(polylines: list, vaults_geo: Sequence[dict], zoom: float, tol_pt: float = TOL_PT,
              simbolos: Sequence[tuple] = ()) -> int:
    """Endereza EN SITIO las polilíneas de imagen de `polylines` (ver el módulo). Devuelve cuántas quedan."""
    imgs = [p for p in polylines if img_piezas.es_capa_imagen(getattr(p, "layer_ocg", "") or "")
            and p.kind != "structure" and len(p.pts_pdf) >= 2 and len(p.kinds) == len(p.pts_pdf)]
    if not imgs:
        return 0
    pad = BOVEDA_PAD_PT * zoom
    bovedas = Bovedas(vaults_geo, pad, CELDA_PT * zoom)
    quitar = []
    for pl in imgs:                            # 1. puntas al centro de su bóveda
        pts = [tuple(map(float, q)) for q in pl.pts_pdf]
        v0, pts, kinds, fil = _punta_al_centro(pts, list(pl.kinds), dict(pl.fillets or {}), bovedas, pad, False)
        v1, pts, kinds, fil = _punta_al_centro(pts, kinds, fil, bovedas, pad, True)
        mismo = v0 is not None and v0 is v1 and _largo(pts) < 2 * TROZO_PT * zoom
        if mismo or (len(pts) == 2 and math.dist(pts[0], pts[1]) < 1e-9):
            quitar.append(pl)                  # de su borde al centro de la MISMA bóveda: no es un tramo
            continue
        pl.pts_pdf, pl.kinds, pl.fillets = pts, kinds, fil
    ids = {id(pl) for pl in quitar}
    imgs = [pl for pl in imgs if id(pl) not in ids]
    rej = Rejilla(imgs, CELDA_PT * zoom)
    quitar += _quitar_repetidas(imgs, zoom, rej)            # 2. la misma tubería dos veces
    from reconocimiento import recognition_imagen_nudos as nudos
    quitar += nudos.quitar_marcos(imgs, zoom, simbolos)     # 2b. el contorno de la caja de un símbolo
    quitar += nudos.limpiar_nudos(imgs, zoom, simbolos, bovedas, pad)  # 2c. enredos de trozos cortos (`nudos`)
    rej = Rejilla(imgs, CELDA_PT * zoom)
    quitar += _quitar_trocitos(imgs, bovedas, zoom, rej)    #    y restos de rejillas y bordes de símbolos
    quitar += _unir_de_frente(imgs, zoom, rej)              # 3. piezas de la misma tubería
    quitar += _unir_huecos(imgs, zoom, rej)                 #    también con un hueco entre ellas
    nudos.a_su_boveda(imgs, zoom, vaults_geo, pad)          # 3d. la punta que no llega a su buzón
    polylines += nudos.cadenas_de_simbolos(imgs, zoom, simbolos, vaults_geo, pad)  # 3e. símbolos apilados
    quitar += _absorbidas(imgs, nudos.cruzar_simbolos, zoom, simbolos, vaults_geo, pad)  # 3f. pasa por el símbolo
    rej = Rejilla(imgs, CELDA_PT * zoom)
    quitar += _unir_de_frente(imgs, zoom, rej)              # (lo que el nudo dejó punta con punta …
    quitar += _unir_huecos(imgs, zoom, rej)                 #  … o de frente con un hueco)
    rej = Rejilla(imgs, CELDA_PT * zoom)
    for pl in imgs:                                         # 4. rectas
        _recta(pl, tol_pt * zoom, rej, zoom)
        rej.poner(pl)                                       # (sus tramos de antes ya no existen: IndexError)
    _prolongar_ramales(imgs, zoom, rej, bovedas, pad)       # 5b. el ramal que muere unos pt antes de otra línea
    aisladas = _quitar_aisladas(imgs, zoom, rej, simbolos)  # 5c. bordes de símbolos que quedaron sueltos
    quitar += aisladas
    ids = {id(pl) for pl in quitar}
    polylines[:] = [pl for pl in polylines if id(pl) not in ids]
    nudos.a_su_buzon(imgs, zoom)                            # 5f. al buzón, no a la unión pegada a él
    nudos.llegar_recto(imgs, zoom)                          # 5e. el ramal llega en T por su recta
    _t_sobre_su_linea(imgs, zoom, tol_pt)                   # 5. la T sobre su línea ya enderezada
    _bovedas_sin_linea(imgs, vaults_geo, pad)               # 5d. un buzón de la imagen sin ninguna línea no se importa
    return len(imgs)


def _absorbidas(imgs: list, paso, *args) -> list:
    """Corre `paso(imgs, *args)` y devuelve las líneas que sacó de `imgs` (las que absorbió otra)."""
    antes = list(imgs)
    paso(imgs, *args)
    quedan = {id(pl) for pl in imgs}
    return [pl for pl in antes if id(pl) not in quedan]


def _cruce_rayo(q: Pt, u, a: Pt, b: Pt):
    """(s, t) del cruce de la semirrecta q + s·u (s > 0) con el tramo a–b (0 ≤ t ≤ 1), o None."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = u[0] * ey - u[1] * ex
    if abs(den) < 1e-12:
        return None
    wx, wy = a[0] - q[0], a[1] - q[1]
    s = (wx * ey - wy * ex) / den
    t = (wx * u[1] - wy * u[0]) / den
    return (s, t) if s > 1e-9 and -1e-9 <= t <= 1 + 1e-9 else None


def _prolongar_ramales(imgs: list, zoom: float, rej: Rejilla, bovedas: Bovedas, pad: float) -> int:
    """Una punta SUELTA (ni bóveda ni otra línea, ni dentro de un buzón) cuyo rumbo choca con otra línea de la red a
    ≤ `PROLONGAR_PT`, de costado (≥ `PROLONGAR_GIRO_MIN_DEG`), llega a ella: el ramal que el dibujo deja unos pt antes
    de la principal (QS SD North, «12\" PVC» contra «15\" PVC»). La punta pasa a «tee» (o «junction» si cae en la
    punta de la otra). Devuelve cuántas."""
    tol, rmax = T_SOBRE_PT * zoom, PROLONGAR_PT * zoom
    seno_min = math.sin(math.radians(PROLONGAR_GIRO_MIN_DEG))
    hechas = 0
    for pl in imgs:
        for end in (0, -1):
            if pl.kinds[end] in ("vault", "tee", "junction", "cut") or not _libre(pl, end, rej, tol):
                continue
            q = pl.pts_pdf[end]
            if _boveda_de(q, bovedas, pad) is not None:
                continue
            u = _rumbo(pl.pts_pdf, end, RUMBO_PT * zoom)
            if u is None:
                continue
            best = None
            for o, ks in rej.cerca(q, rmax):
                if o is pl:
                    continue
                for k in ks:
                    a, b = o.pts_pdf[k], o.pts_pdf[k + 1]
                    hit = _cruce_rayo(q, u, a, b)
                    if hit is None or hit[0] > rmax:
                        continue
                    L = math.dist(a, b)
                    if L < 1e-9 or abs(u[0] * (b[1] - a[1]) - u[1] * (b[0] - a[0])) / L < seno_min:
                        continue
                    if best is None or hit[0] < best[0]:
                        best = (hit[0], o, k, hit[1])
            if best is None:
                continue
            s_hit, o, k, t = best
            p = (q[0] + u[0] * s_hit, q[1] + u[1] * s_hit)
            medio = (q[0] + u[0] * s_hit / 2, q[1] + u[1] * s_hit / 2)
            if _boveda_de(medio, bovedas, pad) is not None:
                continue                                   # el camino pasa por un buzón: ahí ya termina en él
            extremo = min(math.dist(p, o.pts_pdf[0]), math.dist(p, o.pts_pdf[-1])) <= tol
            # la punta se corre por su rumbo (el último tramo ya es recto) o, si ese tramo tuerce, se agrega un vértice
            pts, kinds, fil = list(pl.pts_pdf), list(pl.kinds), dict(pl.fillets or {})
            vec = pts[1] if end == 0 else pts[-2]
            ul = (q[0] - vec[0], q[1] - vec[1])
            Ll = math.hypot(*ul)
            recto = Ll > 1e-9 and (ul[0] * u[0] + ul[1] * u[1]) / Ll >= math.cos(math.radians(3.0))
            nuevo = "junction" if extremo else "tee"
            if end == 0:
                if recto and 0 not in fil:
                    pts[0], kinds[0] = p, nuevo
                else:
                    kinds[0] = "bend"
                    pts.insert(0, p); kinds.insert(0, nuevo)
                    fil = {i + 1: f for i, f in fil.items()}
            else:
                n = len(pts) - 1
                if recto and n not in fil:
                    pts[-1], kinds[-1] = p, nuevo
                else:
                    kinds[-1] = "bend"
                    pts.append(p); kinds.append(nuevo)
            pl.pts_pdf, pl.kinds, pl.fillets = pts, kinds, fil
            rej.poner(pl)
            hechas += 1
    return hechas


def _quitar_aisladas(imgs: list, zoom: float, rej: Rejilla, simbolos: Sequence[tuple] = ()) -> list:
    """Líneas sueltas por LAS DOS puntas (ni bóveda ni otra línea) más cortas que `AISLADA_PT`: bordes de símbolos
    (la caja de un sumidero) que la imagen deja como trazo. Se quedan las más largas y la que va de un símbolo a OTRO
    distinto (la conexión del buzón «M» al sumidero cuando los símbolos no se asignaron como buzones: SD South h.7)."""
    tol = T_SOBRE_PT * zoom
    pad = SIMBOLO_PAD_PT * zoom
    malas = [pl for pl in imgs if _largo(pl.pts_pdf) < AISLADA_PT * zoom
             and _libre(pl, 0, rej, tol) and _libre(pl, -1, rej, tol)
             and pl.kinds[0] not in ("tee", "junction") and pl.kinds[-1] not in ("tee", "junction")
             and not _de_simbolo_a_simbolo(pl.pts_pdf[0], pl.pts_pdf[-1], simbolos, pad)]
    _sacar(imgs, malas, rej)
    return malas


def _de_simbolo_a_simbolo(p: Pt, q: Pt, simbolos: Sequence[tuple], pad: float) -> bool:
    """¿Una punta en un símbolo y la otra en OTRO distinto? (cajas agrandadas `pad`)"""
    def en(pt):
        return {i for i, (x0, y0, x1, y1) in enumerate(simbolos)
                if x0 - pad <= pt[0] <= x1 + pad and y0 - pad <= pt[1] <= y1 + pad}
    a, b = en(p), en(q)
    return bool(a) and bool(b) and bool(b - a) and bool(a - b)


def _bovedas_sin_linea(imgs: list, vaults_geo: Sequence[dict], pad: float) -> int:
    """Un buzón dibujado en la IMAGEN (capa de imagen) al que no llega ni atraviesa ninguna línea de la red no se importa
    (`importable` = False; marca `sin_linea`): solo interesan las líneas y los buzones donde llegan. Devuelve cuántos."""
    rej = Rejilla(imgs, CELDA_PT * 4) if imgs else None
    n = 0
    for vg in vaults_geo or ():
        if not img_piezas.es_capa_imagen(vg.get("layer") or "") or not vg.get("importable", False):
            continue
        c = vault_snap.vault_centroid(vg)
        alcance = _medio_lado(vg) + pad
        tiene = False
        if rej is not None:
            for pl, ks in rej.cerca(c, alcance):
                if any(vault_snap.vault_contains(vg, q, pad) for q in pl.pts_pdf) or \
                        dist_en(c, pl.pts_pdf, ks)[0] <= alcance:
                    tiene = True
                    break
        if not tiene:
            vg["importable"] = False
            vg["sin_linea"] = True
            n += 1
    return n


def _medio_lado(vg: dict) -> float:
    """Medio tamaño del buzón (radio del círculo o medio lado mayor del contorno)."""
    b = vault_snap.boundary(vg)
    if b is None:
        return 0.0
    kind, g = b
    if kind == "circle":
        return float(g[2])
    xs, ys = [p[0] for p in g], [p[1] for p in g]
    return 0.5 * max(max(xs) - min(xs), max(ys) - min(ys))


_PENDIENTES: set = set()      # ids de las líneas con diámetros por partir (entre `cortes_a_puntos` y `puntos_a_cortes`)


def cortes_a_puntos(cuenta) -> dict:
    """Los cortes por diámetro pendientes (`recognition_grosor_mapa.aplicar`: {id: (línea, índices, grosores)}) como
    PUNTOS, antes de enderezar: enderezar quita vértices y los índices quedaban fuera de rango (una pieza de UN punto,
    SD South h.4)."""
    partir = (cuenta or {}).get("partir") or {}
    _PENDIENTES.clear()
    _PENDIENTES.update(id(pl) for pl, _c, _g in partir.values())
    out = {}
    for k, (pl, cortes, _g) in partir.items():
        pts = pl.pts_pdf
        lim = [0] + [c for c in cortes if 0 < c < len(pts) - 1] + [len(pts) - 1]
        largos = [_largo(pts[a:b + 1]) for a, b in zip(lim, lim[1:])]
        out[k] = ([tuple(pts[c]) for c in cortes if 0 <= c < len(pts)], largos)
    return out


def puntos_a_cortes(cuenta, puntos: dict) -> None:
    """Después de enderezar: cada corte al vértice INTERIOR más cercano a su punto. Si dos cortes caen en el mismo
    vértice o la línea ya no tiene interiores, esa línea no se parte: queda entera con el grosor de su pieza más larga
    (SD South h.4 «24\" HDPE»: el trocito de 4 pt sin dato de la punta se fue al enderezar)."""
    _PENDIENTES.clear()
    partir = (cuenta or {}).get("partir") or {}
    for k in list(partir):
        pl, cortes, gs = partir[k]
        pts = pl.pts_pdf
        pp, largos = puntos.get(k, ([], []))
        nuevos = ([min(range(1, len(pts) - 1), key=lambda i, p=p: math.dist(pts[i], p)) for p in pp]
                  if len(pts) >= 3 and len(pp) == len(cortes) else [])
        if not nuevos or nuevos != sorted(set(nuevos)):
            del partir[k]                  # no se puede partir: el grosor de su pieza más larga
            if len(largos) == len(gs) and gs:
                g = gs[max(range(len(gs)), key=lambda i: largos[i])]
                pl.grosor = g
                pl.diam_in = g.get("diam_in")
            continue
        partir[k] = (pl, nuevos, gs)
