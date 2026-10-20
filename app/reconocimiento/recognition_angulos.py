"""recognition_angulos.py — QUIEBRES a pasos de 0.25° (PURO: numpy, sin Qt ni fitz).

Pedido del usuario (2026-10-17): «en cada quiebre, en lugar de generar un ángulo con
decimales raros (45.648°), que se ajuste por pasos de 0.25°: sale más preciso el dibujo y
más real, también en los codos» — en una tubería real no hay codos de 45.648°; sí de
11.25°, 22.5°, 45°… (todos múltiplos de 0.25°). Vale para el PDF con capas y para el
vectorizado sin capas: es un paso APARTE al final de `recognize_page`.

No cambia ninguna decisión del reconocimiento (qué líneas, qué vértices y de qué tipo,
qué codos y con qué radio): solo lleva cada vértice lo MÍNIMO para que la deflexión en
cada quiebre —lo que gira la línea, el ángulo del codo— sea múltiplo exacto de `PASO_DEG`.

  · Rejilla de rumbos. Que todas las deflexiones de una línea sean múltiplos de s es lo
    mismo que todos sus tramos con rumbo φ + k·s (el mismo φ). φ se elige para que los
    rumbos se aparten lo menos posible (peso = largo², lo que se movería el tramo) y cada
    tramo va al rumbo más cercano de la rejilla (≤ s/2 = 0.125°). Las líneas que se tocan
    PUNTA CON PUNTA (tramos de una misma ruta, una «Y») comparten la rejilla: el ángulo
    entre ellas también es un quiebre (un codo en Civil 3D). Una deflexión que ya era
    múltiplo (90°, recta) queda igual.
  · Vértices nuevos = los más cercanos a los de antes (mínimos cuadrados con restricciones
    lineales: cada tramo con su rumbo nuevo). Un tramo de 300 pt que gira 0.06° mueve sus
    puntas ~0.15 pt.
  · Contactos: lo que tocaba otra línea la sigue tocando con el MISMO desfase de antes
    (punta sobre otra línea = T, vértice compartido, punta con punta); un vértice compartido
    sigue siendo el mismo punto, bit a bit. Las líneas se ajustan de una en una (`_orden`:
    la anfitriona de una T antes que sus ramas, después la que toca a una ya ajustada y la
    más larga), cada una apoyada en las que ya quedaron. Los rumbos son obligatorios; los
    contactos pesan muchísimo (exactos si se puede): dos contactos casi paralelos en un
    vértice (la misma línea dibujada dos veces) se promedian en vez de dispararse.
  · Punta en el borde de su bóveda («stop», imán) o en el corte de la vista («cut»): sigue
    SOBRE ese borde. Micro-tramo (< `MICRO_PT`) = un punto: el ángulo es el de los tramos a
    cada lado.
  · Codos: misma esquina C (con Δ múltiplo del paso) y mismo radio; A, B y el centro salen
    de `model_ops.fillet_geo` sin topes, y luego la regla de siempre (`fit_to_editor`). Si
    la tangencia caía justo en el vértice vecino (codo que muere en un nodo, ancla en la
    tangencia, mitades de un codo en «U»), sigue cayendo ahí.
  · Si así algún vértice se corre más de `MOVER_POCO_PT` (algo casi tangente o casi
    paralelo), se prueban otras variantes —radio que se ajusta, contacto con una centésima
    de holgura— y gana la que menos mueve. Una línea que se apartaría de su trazo más de
    `DESVIO_MAX_PT` (de lado: deslizar una punta por su propia recta no aparta el dibujo de
    la tinta), daría vuelta un tramo o se separaría de una línea que toca, queda como estaba
    —solo sigue a sus contactos— y se avisa.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from reconocimiento import recognition_indice as indice_mod
from reconocimiento import recognition_angulos_calc as C
from reconocimiento.recognition_angulos_calc import deflexion_deg, deflexiones_deg, fuera_de_paso_deg  # noqa: F401

Pt = Tuple[float, float]

PASO_DEG = 0.25        # paso de los ángulos en los quiebres (codos reales: 11.25°, 22.5°, 45°…)
TOCA_PT = 0.1          # dos puntos (o punta y línea) a ≤ esto se tocan (pt)
DESVIO_MAX_PT = 2.0    # apartarse más que esto de su línea → la línea queda como estaba (pt)
CONTACTO_MAX_PT = 0.05 # …o separar su punta más que esto de la línea donde termina (un lazo de la red
                       # cuyas líneas ya se ajustaron cada una a su manera): manda la unión
_MISMO_PUNTO_PT = 0.001  # un vértice compartido con otra línea: el mismo punto (se iguala bit a bit)
_PESO_COMPARTIDO = 1e3   # …y por eso pesa más que una punta sobre una línea
MOVER_POCO_PT = 0.5    # un intento que no mueve ningún vértice más que esto se acepta sin probar otros
PIN_PT = 0.01          # tangencia del codo a ≤ esto del vértice vecino = cae en él (pt)
MICRO_PT = 0.25        # tramo más corto = un PUNTO (dos vértices de buzón a 0.02–0.1 pt en los mapas
                       # de Phoenix): su rumbo es ruido; no se gira, y el ángulo exacto es el de los
                       # tramos de verdad a cada lado
_PESO_CONTACTO = 1e6   # un contacto con otra línea pesa esto frente a mover un vértice (exacto)
_PESO_CONTACTO_BLANDO = 1e3   # …o esto si así hay que deslizar un vértice (líneas casi tangentes):
                              # se acepta una centésima de px en el contacto antes que correr la unión
_COS_PARALELOS = math.cos(math.radians(10.0))   # dos contactos de un vértice a < 10°: uno solo
_DESLIZ_MAX = 1.0      # un vértice puede deslizarse por su recta hasta 1 × DESVIO_MAX_PT (más arrastraría
                       # a las líneas que nacen en él)
_SIN_TOPE = 1e9        # `fillet_geo` sin topes: el arco del plano tal cual
_PUNTAS_FIJAS = ("stop", "cut")   # punta en el borde de su bóveda / en el corte: sigue en él
_EN_BORDE_PT = 0.01    # una punta a ≤ esto de un borde está sobre él (pt)


@dataclass
class Ajuste:
    """Resultado de `ajustar_quiebres` (px del lienzo)."""
    quiebres: int = 0                      # vértices cuyo ángulo pasó a múltiplo del paso
    max_desvio_px: float = 0.0             # lo más que se apartó un vértice de su línea de antes
    max_contacto_px: float = 0.0           # lo más que quedó un contacto fuera de su lugar
    sin_ajustar: List[Pt] = field(default_factory=list)       # un punto por línea que quedó igual
    movidos: List[Tuple[Pt, Pt]] = field(default_factory=list)  # (antes, después) de cada vértice


def ajustar_quiebres(polilineas, zoom: float = 1.0, paso_deg: float = PASO_DEG, bordes=()) -> Ajuste:
    """Lleva cada quiebre de `polilineas` (`RecognizedPolyline`: `pts_pdf`, `kinds`,
    `fillets`, en px del lienzo a `zoom`) a un ángulo múltiplo de `paso_deg` moviendo lo
    mínimo sus vértices (ver arriba). `bordes` = contornos donde una punta «stop»/«cut» debe
    seguir: ("poly", [esquinas]) o ("circle", (cx, cy, r)) en px (bóvedas, corte de la vista).
    Modifica las polilíneas en el lugar."""
    out = Ajuste()
    idx = [n for n, pl in enumerate(polilineas) if len(pl.pts_pdf or ()) >= 2]
    if not idx or not paso_deg or paso_deg <= 0:
        return out
    s = math.radians(paso_deg)
    f = max(float(zoom), 1e-9)
    lineas = [np.asarray(polilineas[n].pts_pdf, float) for n in idx]
    V, S = C.contactos(lineas, TOCA_PT * f)

    # rejilla común a las líneas que se tocan punta con punta
    uf = C.Uf(len(lineas))
    vecinos: List[set] = [set() for _ in lineas]
    puntas = [{0, len(P) - 1} for P in lineas]
    for (i, k), otros in V.items():
        for j, l in otros:
            if j != i:
                vecinos[i].add(j); vecinos[j].add(i)
                if k in puntas[i] and l in puntas[j]:
                    uf.union(i, j)
    for (i, _k), (j, _l) in S:
        vecinos[i].add(j); vecinos[j].add(i)
    grupos: Dict[int, List[int]] = {}
    for i in range(len(lineas)):
        grupos.setdefault(uf.find(i), []).append(i)
    rumbo = [None] * len(lineas)
    for miembros in grupos.values():
        datos = [C.rumbos(lineas[i]) for i in miembros]
        # un tramo suelto (sin quiebre propio ni línea pegada punta con punta) no tiene
        # ningún ángulo que ajustar: conserva su rumbo
        if len(miembros) == 1 and len(lineas[miembros[0]]) == 2:
            rumbo[miembros[0]] = datos[0][0].copy()
            continue
        th = np.concatenate([d[0] for d in datos])
        L = np.concatenate([d[1] for d in datos])
        phi = C.rejilla(th, L * L, s)
        for i, (th_i, L_i) in zip(miembros, datos):
            rumbo[i] = C.objetivo(th_i, L_i, phi, s, MICRO_PT * f)

    S_de: Dict[int, list] = {}
    for (i, k), (j, l) in S:
        S_de.setdefault(i, []).append(("sobre", k, j, l))       # mi punta k sobre el tramo l de j
        S_de.setdefault(j, []).append(("pasa", l, i, k))        # la punta k de i sobre mi tramo l
    nuevo: List = [None] * len(lineas)
    # rama → anfitriona: su punta sobre el tramo de otra línea (S). (Con la punta en un vértice
    # INTERIOR de la otra también se probó: 20 líneas menos sin ajustar en los PDF de prueba, pero
    # curvas de DU08 h.22 a 0.18 pt de su tinta y uniones 0.15 pt corridas: no compensa.)
    ramas_de = [(i, j) for (i, _k), (j, _l) in S]
    for i in _orden(lineas, vecinos, ramas_de):
        nuevo[i] = _ajustar_linea(i, lineas, rumbo[i], V, S_de, nuevo, f, out, s, polilineas[idx[i]], bordes)
    for i, n in enumerate(idx):
        pl = polilineas[n]
        P, Q = lineas[i], nuevo[i]
        _rehacer_codos(pl, P, Q, f)
        for k in range(len(P)):
            d = float(math.hypot(*(Q[k] - P[k])))
            if d > 1e-9:
                out.movidos.append(((float(P[k][0]), float(P[k][1])), (float(Q[k][0]), float(Q[k][1]))))
        pl.pts_pdf = [(float(x), float(y)) for x, y in Q]
    return out


def _orden(lineas, vecinos, ramas_de) -> List[int]:
    """En qué orden se ajustan las líneas. Primero la ANFITRIONA —sobre cuyo tramo terminan
    otras (T; `ramas_de` = [(rama, anfitriona)])— y después sus ramas: una rama puede deslizar
    su punta sobre la anfitriona ya ajustada, pero una anfitriona recta no puede seguir a dos
    ramas que ya se movieron cada una a su manera (DU10 h.25 gas). Entre las listas, la que toca
    a una ya ajustada (así se apoya en ella) y la más larga (es la que menos debe moverse)."""
    largo = [float(C.rumbos(P)[1].sum()) for P in lineas]
    anfitrionas: List[set] = [set() for _ in lineas]   # i → líneas sobre las que termina i
    ramas: List[set] = [set() for _ in lineas]         # i → líneas que terminan sobre i
    for i, j in ramas_de:
        if i != j:
            anfitrionas[i].add(j)
            ramas[j].add(i)
    faltan = [len(a) for a in anfitrionas]
    tocada = [False] * len(lineas)
    hecho = [False] * len(lineas)

    def clave(i):
        return (faltan[i], 0 if tocada[i] else 1, -largo[i], i)
    heap = [clave(i) for i in range(len(lineas))]
    heapq.heapify(heap)
    out = []
    while heap:
        k = heapq.heappop(heap)
        i = k[-1]
        if hecho[i] or k != clave(i):
            continue                                   # entrada vieja: la línea cambió de clave
        hecho[i] = True
        out.append(i)
        for j in ramas[i]:
            faltan[j] -= 1
        for j in vecinos[i] | ramas[i]:
            if not hecho[j]:
                tocada[j] = True
                heapq.heappush(heap, clave(j))
    return out


def _ajustar_linea(i, lineas, t, V, S_de, nuevo, f, out: Ajuste, s, pl, bordes=()):
    """Vértices nuevos de la línea i: tramos con los rumbos `t` (exactos) y pegada a las
    líneas ya ajustadas con las que tenía contacto (mismo desfase que antes)."""
    P = lineas[i]
    m = len(P)
    th, L = C.rumbos(P)
    ex, ey = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    duras, rhs_d = [], []
    fijo: Dict[int, np.ndarray] = {}                  # vértice → punto donde va (vértice compartido)
    sobre: Dict[int, list] = {}                       # vértice → [[normal, Σb, n]] (punta sobre una línea)
    for k in range(m):
        for j, l in V.get((i, k), ()):
            if j == i:
                if l > k:                              # lazo cerrado: sigue cerrado igual
                    d = P[k] - P[l]
                    duras += [[(k, ex), (l, -ex)], [(k, ey), (l, -ey)]]
                    rhs_d += [float(d[0]), float(d[1])]
                continue
            if k not in fijo and nuevo[j] is not None:
                fijo[k] = nuevo[j][l] + (P[k] - lineas[j][l])   # el mismo punto (con su desfase de antes)

    def _sobre(k, n, b):
        # dos contactos casi paralelos en un vértice fijan mal el punto a lo largo de la
        # línea (se dispararía): se promedian como uno solo. Se promedia lo que cada uno pide
        # MOVER el vértice (b − n·P_k), no b: con normales que difieren unos grados, b depende
        # de dónde está el origen de la hoja.
        mover = b - float(n @ P[k])
        for fila in sobre.setdefault(k, []):
            c = float(fila[0] @ n)
            if abs(c) >= _COS_PARALELOS:
                fila[1] += mover if c > 0 else -mover
                fila[2] += 1
                return
        sobre[k].append([n, mover, 1])

    for tipo, a, j, b in S_de.get(i, ()):
        if nuevo[j] is None or a in fijo:
            continue
        if tipo == "sobre":                            # mi punta a sobre el tramo b de j (ya ajustado)
            n0 = C.unit_normal(lineas[j][b + 1] - lineas[j][b])
            n1 = C.unit_normal(nuevo[j][b + 1] - nuevo[j][b])
            if n0 is not None and n1 is not None:
                _sobre(a, n1, float(n1 @ nuevo[j][b]) + float(n0 @ (P[a] - lineas[j][b])))
        elif L[a] >= MICRO_PT * f:                     # la punta b de j (ya ajustada) sobre mi tramo a
            n = np.array(C.normal(float(t[a])))
            n0 = C.unit_normal(P[a + 1] - P[a])
            _sobre(a, n, float(n @ nuevo[j][b]) - float(n0 @ (lineas[j][b] - P[a])))
    kinds = list(getattr(pl, "kinds", None) or [])
    for k, seg in ((0, 0), (m - 1, m - 2)):
        # punta en el borde DIBUJADO de su bóveda (imán, `recognition_vault_snap`) o en el corte
        # de la vista / costura de la hoja compuesta: sigue SOBRE ese borde (puede correrse por
        # él unas centésimas, no salirse). Fijarla del todo dejaba mal puesto un vértice casi
        # recto entre dos puntas fijas (se deslizaba 5–10 pt y arrastraba a sus ramas). Sin el
        # borde a mano, no se corre a lo largo de su propia línea.
        if k in fijo or k >= len(kinds) or kinds[k] not in _PUNTAS_FIJAS or L[seg] < MICRO_PT * f:
            continue
        normales = C.normales_de_borde(P[k], bordes, _EN_BORDE_PT * f)
        if not normales:
            normales = [(P[seg + 1] - P[seg]) / L[seg]]
        for n in normales:
            _sobre(k, n, float(n @ P[k]))
    # (un vértice compartido pesa `_PESO_COMPARTIDO` veces más: si los contactos se contradicen,
    # lo absorben las puntas sobre una línea —toleran 0.05 pt—, no el vértice compartido)
    blandas = [(k, e, float(X[c]), _PESO_COMPARTIDO) for k, X in fijo.items() for c, e in ((0, ex), (1, ey))]
    blandas += [(k, n, float(n @ P[k]) + mov / c, 1.0) for k, filas in sobre.items() for n, mov, c in filas]
    micro = MICRO_PT * f
    for k in range(m - 1):
        if L[k] >= micro:
            n = np.array(C.normal(float(t[k])))
            duras.append([(k, -n), (k + 1, n)])
            rhs_d.append(0.0)
        else:                                          # micro-tramo = un punto: se mueve entero
            d = P[k + 1] - P[k]
            duras += [[(k + 1, ex), (k, -ex)], [(k + 1, ey), (k, -ey)]]
            rhs_d += [float(d[0]), float(d[1])]
    escala = 1e-12 * max(1.0, float(np.abs(P).max()))
    if (all(abs(sum(float(a @ P[k]) for k, a in fila) - r) <= escala for fila, r in zip(duras, rhs_d))
            and all(abs(float(a @ P[k]) - b) <= escala for k, a, b, _w in blandas)):
        return P.copy()                                # ya cumple todo: queda idéntica
    piernas, rhs_p = _piernas_de_codos(pl, P, t, L, f)
    gira = [d for d in deflexiones_deg(P, micro) if abs(C.wrap(math.radians(d), s)) > C.EXACTO]
    # intentos, del preferido al último recurso: el radio exacto de los codos y los contactos
    # exactos; si así algún vértice se corre más de `MOVER_POCO_PT` (algo casi tangente o casi
    # paralelo lo deja mal puesto), se prueban los demás y gana el que menos mueve
    intentos = [(piernas, rhs_p, _PESO_CONTACTO)]
    if piernas:
        intentos.append(([], [], _PESO_CONTACTO))
    intentos.append((piernas, rhs_p, _PESO_CONTACTO_BLANDO))
    if piernas:
        intentos.append(([], [], _PESO_CONTACTO_BLANDO))
    mejor = None
    for extra, rhs_e, peso in intentos:
        Q = C.resolver(P, duras + extra, rhs_d + rhs_e, blandas, peso)
        lat = _valida(P, Q, t, L, f)
        # se separaría de la línea que toca (lazo de la red): manda la unión. Un vértice
        # COMPARTIDO tiene que seguir siendo el mismo punto; una punta sobre una línea, a ≤ 0.05 pt
        if lat is not None and fijo and max(float(np.hypot(*(Q[k] - X))) for k, X in fijo.items()) > _MISMO_PUNTO_PT * f:
            lat = None
        if lat is not None and sobre and max(abs(float(n @ Q[k]) - float(n @ P[k]) - mov / c)
                                             for k, filas in sobre.items() for n, mov, c in filas) > CONTACTO_MAX_PT * f:
            lat = None
        if lat is None:
            continue
        mueve = float(np.hypot(*(Q - P).T).max())
        if mejor is None or mueve < mejor[0] - 1e-9:
            mejor = (mueve, lat, Q)
        if mueve <= MOVER_POCO_PT * f:
            break
    if mejor is not None:
        _mueve, lat, Q = mejor
        out.quiebres += len(gira)
        out.max_desvio_px = max(out.max_desvio_px, lat)
        if blandas:
            out.max_contacto_px = max(out.max_contacto_px, max(abs(float(a @ Q[k]) - b) for k, a, b, _w in blandas))
        for k, X in fijo.items():                      # el MISMO punto, bit a bit
            Q[k] = X
        return Q
    # no se puede sin moverla de más: queda como estaba, pegada a sus contactos
    if gira:
        k = int(np.argmax(L))
        out.sin_ajustar.append((float((P[k][0] + P[k + 1][0]) / 2), float((P[k][1] + P[k + 1][1]) / 2)))
    Q = C.resolver(P, [], [], blandas, _PESO_CONTACTO_BLANDO)
    for k, X in fijo.items():
        Q[k] = X
    out.max_desvio_px = max(out.max_desvio_px, float(C.lateral(P, Q).max()))
    return Q


def _piernas_de_codos(pl, P, t, L, f):
    """Codos cuya tangencia cae JUSTO en el vértice vecino (codo que muere en un nodo, ancla
    puesta en la tangencia, mitades de un codo en «U»): ese tramo debe medir r·tan(Δ/2) con
    el Δ nuevo, así el radio no cambia y la tangencia sigue en el vértice. Filas duras."""
    filas, rhs = [], []
    m = len(P)
    for i, fl in (getattr(pl, "fillets", None) or {}).items():
        if not (0 < i < m - 1) or "r_px" not in fl or L[i - 1] < MICRO_PT * f or L[i] < MICRO_PT * f:
            continue
        delta = abs(C.wrap_pi(float(t[i] - t[i - 1])))
        if not 0.0 < delta < math.radians(178.0):
            continue
        T = float(fl["r_px"]) * math.tan(delta / 2.0)
        for lado, j, seg in (("a", i - 1, i - 1), ("b", i + 1, i)):
            tp = fl.get(lado)
            if tp is not None and math.hypot(tp[0] - P[j][0], tp[1] - P[j][1]) <= PIN_PT * f:
                u = np.array([math.cos(float(t[seg])), math.sin(float(t[seg]))])
                filas.append([(seg, -u), (seg + 1, u)])
                rhs.append(T)
    return filas, rhs


def _valida(P, Q, t, L, f):
    """Desvío lateral máximo (px) si Q sirve —rumbos exactos, ningún tramo dado vuelta, no se
    aparta de su línea más de `DESVIO_MAX_PT`—; None si no."""
    dv = Q[1:] - Q[:-1]
    for k in range(len(P) - 1):
        if L[k] < MICRO_PT * f:
            continue
        c, sn = math.cos(t[k]), math.sin(t[k])
        if dv[k, 0] * c + dv[k, 1] * sn <= 0.0 or abs(dv[k, 1] * c - dv[k, 0] * sn) > 1e-6 * max(1.0, L[k]):
            return None
    lat = float(C.lateral(P, Q).max())
    if lat > DESVIO_MAX_PT * f or float(np.hypot(*(Q - P).T).max()) > _DESLIZ_MAX * DESVIO_MAX_PT * f:
        return None
    return lat


def _rehacer_codos(pl, P: np.ndarray, Q: np.ndarray, f: float = 1.0):
    """Cada codo de `pl.fillets` sobre los vértices nuevos Q (antes P): mismo radio, o la
    tangencia en el vértice vecino si ahí caía; A/B/centro de `fillet_geo` SIN sus topes (el
    arco es el del plano: si el editor lo recorta, lo avisa él, como antes) y al final la misma
    regla del reconocimiento (`recognition_arcs.fit_to_editor`: si el editor lo recortaría por
    ≤ 1.5 pt, el radio justo que entra)."""
    if not getattr(pl, "fillets", None):
        return
    from nucleo import model_ops as MO
    from reconocimiento import recognition_arcs as arcs_mod
    kinds = list(getattr(pl, "kinds", None) or [])
    for i, fl in list(pl.fillets.items()):
        if not (0 < i < len(Q) - 1) or "r_px" not in fl:
            continue
        tol = PIN_PT * f
        pins = []
        for lado, j in (("a", i - 1), ("b", i + 1)):
            t_old = fl.get(lado)
            if t_old is not None and math.hypot(t_old[0] - P[j][0], t_old[1] - P[j][1]) <= tol:
                pins.append(j)
        Ci, Qa, Qb = Q[i], Q[i - 1], Q[i + 1]
        delta = math.radians(abs(deflexion_deg(tuple(Qa), tuple(Ci), tuple(Qb))))
        r = r0 = float(fl["r_px"])
        if pins and 0.0 < delta < math.pi:
            # el tramo hasta el vértice ya mide r·tan(Δ/2) (`_piernas_de_codos`): mismo radio;
            # si la línea no pudo ajustarse así, el radio que deja la tangencia en el vértice
            T = min(float(math.hypot(*(Q[j] - Ci))) for j in pins)
            r = T / math.tan(delta / 2.0)
            if abs(r - r0) <= 1e-9 * max(1.0, r0):
                r = r0
        geo = MO.fillet_geo(tuple(Qa), tuple(Ci), tuple(Qb), r, max_frac=_SIN_TOPE, tol_r=0.0)
        if geo is None:
            continue
        fl.update(r_px=float(geo["r"]), a=tuple(geo["t1"]), b=tuple(geo["t2"]), center=tuple(geo["center"]))
    arcs_mod.fit_to_editor([tuple(q) for q in Q], kinds, pl.fillets, f)
    for i, fl in pl.fillets.items():
        if not (0 < i < len(Q) - 1) or "r_px" not in fl:
            continue
        for lado, j in (("a", i - 1), ("b", i + 1)):     # tangencia en el vértice vecino: ESE punto
            tp = fl.get(lado)
            if tp is not None and math.hypot(tp[0] - Q[j][0], tp[1] - Q[j][1]) <= 1e-6 * f:
                fl[lado] = (float(Q[j][0]), float(Q[j][1]))
    # codo en «U» partido en dos mitades del MISMO círculo (`recognition_trace.split_wide_fillets`)
    for i, fl in pl.fillets.items():
        otra = pl.fillets.get(i + 2)
        if fl.get("split_b") and otra is not None and otra.get("split_a") and abs(fl["r_px"] - otra["r_px"]) <= 1e-6:
            otra["center"], otra["r_px"] = fl["center"], fl["r_px"]


def reubicar(puntos, movidos, tol: float = 0.5):
    """Cada punto de `puntos` que coincidía (≤ tol px) con un vértice movido va a su lugar
    nuevo (bóvedas = vértices de las líneas, puntas unidas a su bóveda…)."""
    if not movidos or not puntos:
        return list(puntos)
    viejos = [a for a, _b in movidos]
    ip = indice_mod.IndicePuntos(viejos, max(tol, 1e-6))
    out = []
    for q in puntos:
        best = None
        for o in ip.cerca(q):
            d = math.hypot(viejos[o][0] - q[0], viejos[o][1] - q[1])
            if d <= tol and (best is None or d < best[0]):
                best = (d, o)
        if best is None:
            out.append(q)
        else:
            a, b = movidos[best[1]]
            out.append((b[0] + (q[0] - a[0]), b[1] + (q[1] - a[1])))
    return out
