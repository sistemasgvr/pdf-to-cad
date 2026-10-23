"""recognition_grosor_guias.py — las GUÍAS (flechas) de los rótulos de diámetro (PURO; ver
`recognition_grosor`).

Un MLeader de AutoCAD ploteado son rectas sueltas en la capa del texto: la raya bajo una línea
del rótulo (o, sin raya, una recta que nace en el borde del bloque), uno o varios tramos y la
punta — una flecha rellena (triángulo), dos rayitas «>» o nada. `Guias` arma el grafo de esos
tramos (nudo = puntas que coinciden; la misma recta de ida y vuelta cuenta una vez) y `seguir`
camina de la raya a cada punta libre; una raya puede tener varias guías. Si el camino se
ramifica de más es un dibujo (cajas, rejas), no una guía.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reconocimiento.recognition_grosor_texto import Rotulo

Pt = Tuple[float, float]

FLECHA_MAX_PT = 15.0          # una punta de flecha cabe en esto
FLECHA_UNE_PT = 2.5           # la guía termina en la base de su flecha
NUDO_PT = 0.3                 # dos puntas de tramo a menos de esto son el mismo nudo
GUIA_MAX_TRAMOS = 8
GUIA_MAX_RAMAS = 4
GUIA_MIN_PT = 6.0
LANDING_TOL = 0.6             # × tamaño de letra: la raya va pegada al texto
LANDING_HUECO = 1.0           # × tamaño de letra: hueco entre el texto y su raya (MLeader)
RAYA_EMPATE_PT = 1.0          # dos bloques así de igual de cerca de una raya: decide su altura
MEDIA_ALTURA = 0.2            # una guía que llega entre el 20 % y el 80 % del alto de una línea es suya


def capas_de_texto(page) -> set:
    """Capas (OCG) que llevan texto en la hoja: ahí van las guías de los rótulos."""
    def leer():
        out = set()
        try:
            for t in page.get_texttrace():
                if t.get("layer"):
                    out.add(t["layer"])
        except Exception:
            pass
        return out
    from hoja import pdf_styles
    return pdf_styles.memo(page, "grosor_capas_texto", leer)


def _clave(p: Pt) -> Tuple[int, int]:
    return (int(round(p[0] / NUDO_PT)), int(round(p[1] / NUDO_PT)))


def guias(page, px: Callable[[Pt], Pt], zoom: float = 1.0, ocultas=(), dibujos=None) -> "Guias":
    """Tramos rectos y flechas de las capas con texto (la materia de las guías). `dibujos` = la
    lectura de la hoja ya hecha (`pdf_styles.drawings`)."""
    from hoja import pdf_styles
    capas = capas_de_texto(page)
    ocultas = set(ocultas or ())
    tramos: List[Tuple[Pt, Pt]] = []
    flechas: List[List[Pt]] = []
    for d in (pdf_styles.drawings(page) if dibujos is None else dibujos):
        capa = d.get("layer") or ""
        if (capas and capa not in capas) or capa in ocultas:
            continue
        items = d.get("items") or ()
        if not items or any(it[0] != "l" for it in items):
            continue
        r = d.get("rect")
        if d.get("fill") is not None:
            if len(items) == 3 and r is not None and max(r.width, r.height) <= FLECHA_MAX_PT:
                flechas.append([px((it[1].x, it[1].y)) for it in items])
            continue
        for it in items:
            a, b = px((it[1].x, it[1].y)), px((it[2].x, it[2].y))
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 0.3 * zoom:
                tramos.append((a, b))
    return Guias(tramos, flechas, zoom)


class Guias:
    """Grafo de tramos (nudos = puntas que coinciden) para seguir una guía de su raya a su punta."""

    def __init__(self, tramos, flechas, zoom):
        unicos, vistos = [], set()
        for a, b in tramos:                         # la misma recta de ida y vuelta = una
            k = tuple(sorted(((round(a[0] / zoom, 1), round(a[1] / zoom, 1)),
                              (round(b[0] / zoom, 1), round(b[1] / zoom, 1)))))
            if k not in vistos:
                vistos.add(k)
                unicos.append((a, b))
        self.tramos, self.flechas, self.zoom = unicos, flechas, zoom
        self.nudos: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for k, (a, b) in enumerate(self.tramos):
            for p in (a, b):
                ck = _clave((p[0] / zoom, p[1] / zoom))
                if k not in self.nudos[ck]:
                    self.nudos[ck].append(k)
        # flechas por celdas (en la hoja compuesta de DU06 hay miles: recorrerlas todas en cada
        # nudo de cada guía tardaba más de un minuto); mismo orden → misma flecha
        self._celda = (FLECHA_MAX_PT + 2.0 * FLECHA_UNE_PT) * zoom
        self._flechas_en: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for k, f in enumerate(flechas):
            m = FLECHA_UNE_PT * zoom
            x0, x1 = min(v[0] for v in f) - m, max(v[0] for v in f) + m
            y0, y1 = min(v[1] for v in f) - m, max(v[1] for v in f) + m
            for cx in range(int(math.floor(x0 / self._celda)), int(math.floor(x1 / self._celda)) + 1):
                for cy in range(int(math.floor(y0 / self._celda)), int(math.floor(y1 / self._celda)) + 1):
                    self._flechas_en[(cx, cy)].append(k)

    def vecinos(self, p: Pt, menos: int) -> List[int]:
        cx, cy = _clave((p[0] / self.zoom, p[1] / self.zoom))
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self.nudos.get((cx + dx, cy + dy), ()):
                    if k != menos and k not in out:
                        a, b = self.tramos[k]
                        if min(math.hypot(a[0] - p[0], a[1] - p[1]),
                               math.hypot(b[0] - p[0], b[1] - p[1])) <= NUDO_PT * self.zoom:
                            out.append(k)
        return out

    def seguir(self, k0: int, desde: Pt) -> List[Tuple[List[Pt], Pt]]:
        """Desde el tramo k0 entrando por `desde`: cada cadena hasta una punta libre (con su
        flecha). Una raya con VARIAS guías (MLeader de varias flechas) da varias; si se ramifica
        de más (un dibujo, no una guía) no da ninguna."""
        out: List[Tuple[List[Pt], Pt]] = []
        pila = [([desde], k0, desde)]
        while pila:
            pts, k, p = pila.pop()
            if len(pts) > GUIA_MAX_TRAMOS:
                continue
            a, b = self.tramos[k]
            q = b if math.hypot(a[0] - p[0], a[1] - p[1]) <= math.hypot(b[0] - p[0], b[1] - p[1]) else a
            pts = pts + [q]
            sig = [j for j in self.vecinos(q, k)
                   if not any(math.dist(self.tramos[j][0], v) < 1e-6 or math.dist(self.tramos[j][1], v) < 1e-6
                              for v in pts[:-1])]
            if not sig or (len(pts) > 2 and self._flecha_en(q) is not None):
                # punta libre, o su FLECHA: ahí termina aunque sigan otras rectas (dos guías que
                # apuntan al mismo lugar —la unión de un lateral— se tocan en sus flechas; DU06 h.6)
                out.append((pts, self._punta(pts)))
            elif len(sig) > 1 and self._flecha_abierta(q, sig):
                out.append((pts, q))                 # «>» de dos rayitas: aquí está la punta
            else:
                pila.extend((pts, j, q) for j in sig)
            if len(out) > GUIA_MAX_RAMAS:
                return []
        return out

    def _flecha_abierta(self, q: Pt, sig: List[int]) -> bool:
        """Dos rayitas cortas que nacen en q y terminan libres = punta de flecha abierta."""
        if len(sig) != 2:
            return False
        for k in sig:
            a, b = self.tramos[k]
            otra = b if math.hypot(a[0] - q[0], a[1] - q[1]) <= math.hypot(b[0] - q[0], b[1] - q[1]) else a
            if math.hypot(otra[0] - q[0], otra[1] - q[1]) > FLECHA_MAX_PT * self.zoom or self.vecinos(otra, k):
                return False
        return True

    def _flecha_en(self, p: Pt):
        """La flecha rellena cuya base (o punta) está en p, o None."""
        tol = FLECHA_UNE_PT * self.zoom
        celda = (int(math.floor(p[0] / self._celda)), int(math.floor(p[1] / self._celda)))
        for k in self._flechas_en.get(celda, ()):
            f = self.flechas[k]
            cx, cy = sum(v[0] for v in f) / 3.0, sum(v[1] for v in f) / 3.0
            if min(math.hypot(v[0] - p[0], v[1] - p[1]) for v in f) <= tol or math.hypot(cx - p[0], cy - p[1]) <= tol:
                return f
        return None

    def _punta(self, pts: List[Pt]) -> Pt:
        fin, antes = pts[-1], pts[-2]
        ux, uy = fin[0] - antes[0], fin[1] - antes[1]
        f = self._flecha_en(fin)
        if f is None:
            return fin
        # la guía llega a la BASE de la flecha: la punta es el vértice de adelante
        ap = max(f, key=lambda v: (v[0] - fin[0]) * ux + (v[1] - fin[1]) * uy)
        if (ap[0] - fin[0]) * ux + (ap[1] - fin[1]) * uy > 0.5 * self.zoom:
            return ap
        return fin                                  # llega a la punta misma


class _Cajas:
    """Las cajas de los bloques de texto por franjas de altura (con su margen `LANDING_TOL`):
    `en(y)` = las que pueden tocar una raya o un arranque a esa altura."""

    def __init__(self, cajas: Dict[int, Tuple]):
        self.cajas = cajas
        self.alto = max([c[3] - c[1] + 2 * LANDING_TOL * c[4] for c in cajas.values()] + [1.0])
        self.franjas: Dict[int, List[int]] = defaultdict(list)
        for k, (x0, y0, x1, y1, tam) in cajas.items():
            tol = LANDING_TOL * tam
            for f in range(int(math.floor((y0 - tol) / self.alto)), int(math.floor((y1 + tol) / self.alto)) + 1):
                self.franjas[f].append(k)

    def en(self, y: float):
        return ((k, self.cajas[k]) for k in self.franjas.get(int(math.floor(y / self.alto)), ()))


def _bloque_de_raya(a: Pt, b: Pt, cajas, zoom: float) -> Optional[int]:
    """El bloque de texto al que pertenece una raya horizontal: el más cercano que la toca; entre
    dos casi igual de cerca (±`RAYA_EMPATE_PT`), el que tiene su centro a la altura de la raya
    (LABOE h.26: la raya a media altura de «EX. 4" GAS» quedaba a 3.4 pt de la línea de arriba y a
    3.5 pt de la suya)."""
    y = (a[1] + b[1]) / 2.0
    lo, hi = min(a[0], b[0]), max(a[0], b[0])
    cands = []
    for k, (x0, y0, x1, y1, tam) in cajas.en(y):
        tol = LANDING_TOL * tam
        if not (y0 - tol <= y <= y1 + tol):
            continue
        hueco = max(x0 - hi, lo - x1, 0.0)        # 0 = la raya corre bajo el texto
        if hueco > LANDING_HUECO * tam:
            continue
        dy = 0.0 if y0 <= y <= y1 else min(abs(y - y0), abs(y - y1))
        cands.append((hueco + dy, abs(y - (y0 + y1) / 2.0), k))
    if not cands:
        return None
    mejor = min(c[0] for c in cands)
    return min((c[1], c[0], c[2]) for c in cands if c[0] <= mejor + RAYA_EMPATE_PT * zoom)[2]


def _bloque_de_arranque(e: Pt, otro: Pt, cajas, zoom: float) -> Optional[int]:
    """Guía SIN raya (MLeader sin «landing»): nace en el borde izquierdo o derecho de un bloque,
    a la altura del texto, y se ALEJA de él."""
    mejor = None
    for k, (x0, y0, x1, y1, tam) in cajas.en(e[1]):
        tol = LANDING_TOL * tam
        if not (y0 - tol <= e[1] <= y1 + tol):
            continue
        for borde, sale in ((x1, 1.0), (x0, -1.0)):
            hueco = (e[0] - borde) * sale
            if not (-0.5 * tam <= hueco <= LANDING_HUECO * tam):
                continue
            if (otro[0] - e[0]) * sale <= 0:       # vuelve hacia el texto
                continue
            clave = (abs(hueco), k)
            if mejor is None or clave < mejor:
                mejor = clave
    return mejor[1] if mejor else None


def puntas_de_rotulos(rots: Sequence[Rotulo], cajas: Dict[int, Tuple],
                      gs: Guias) -> List[Tuple[Rotulo, List[Pt], Pt]]:
    """(rótulo, cadena, punta) de cada guía que sale de un bloque con diámetro: por su raya
    (horizontal, bajo una línea del bloque) o, sin raya, por el borde del bloque."""
    por_bloque: Dict[int, List[Rotulo]] = defaultdict(list)
    for r in rots:
        por_bloque[r.bloque].append(r)
    out = []
    vistos = set()

    def _de_su_linea(blq, y):
        """La guía que llega a MEDIA ALTURA de una línea es de esa línea (columnas de rótulos de
        una línea: la de «EX. COMM OVERHEAD» no es de «EX. 30" STORM DRAIN», justo arriba, LABOE
        h.28; la de «PROP FH DWPWS 6" D.I.» no es de «PROP DWPPS 2-6"P CONDUIT», justo abajo, DU08
        h.22): su rótulo, el de la línea de abajo si esa nombra el dueño y la de abajo da el
        diámetro («SCG AM-17, / 2" STL», DU08), o False (la línea no da diámetro). None = la guía
        no llega a media altura de ninguna (raya bajo el texto, como en DU06)."""
        lins = (getattr(cajas, "lineas", None) or {}).get(blq) or []
        medias = [(abs(y - (l[0][1] + l[0][3]) / 2.0), n) for n, l in enumerate(lins)
                  if l[0][1] + MEDIA_ALTURA * (l[0][3] - l[0][1]) <= y <= l[0][3] - MEDIA_ALTURA * (l[0][3] - l[0][1])]
        if not medias:
            return None
        caja, r, util, abajo = lins[min(medias)[1]]
        if r is None and util and abajo is not None:
            r = lins[abajo][1]
            if r is not None and r.utilidad not in ("", util):
                r = None
        return r if r is not None and any(r is o for o in por_bloque[blq]) else False

    def probar(blq, k, desde, minimo):
        if blq is None or not por_bloque.get(blq):
            return
        x0, y0, x1, y1, tam = cajas[blq]
        tol = LANDING_TOL * tam
        r = _de_su_linea(blq, desde[1])
        if r is False:
            return
        if r is None:
            # el rótulo de diámetro más cercano por ENCIMA de la raya (o en ella): en un bloque de
            # rótulos apilados cada raya es del suyo. Primero las líneas que empiezan arriba de la
            # raya; si no hay, las de la holgura
            arriba = [o for o in por_bloque[blq] if o.bbox[1] - tol <= desde[1]]
            if not arriba:
                return
            r = max([o for o in arriba if o.bbox[1] <= desde[1]] or arriba, key=lambda o: o.bbox[1])
        for cadena, punta in gs.seguir(k, desde):
            if x0 - tol <= punta[0] <= x1 + tol and y0 - tol <= punta[1] <= y1 + tol:
                continue
            largo = sum(math.dist(p, q) for p, q in zip(cadena, cadena[1:]))
            if largo < GUIA_MIN_PT * gs.zoom or len(cadena) < minimo:
                continue
            clave = (id(r), _clave(punta))
            if clave not in vistos:
                vistos.add(clave)
                out.append((r, cadena, punta))

    indice = _Cajas(cajas)
    for k, (a, b) in enumerate(gs.tramos):
        if abs(b[1] - a[1]) <= 0.05 * max(abs(b[0] - a[0]), 1e-9):
            blq = _bloque_de_raya(a, b, indice, gs.zoom)
            for desde in (a, b):                    # sale por la punta de afuera del texto
                probar(blq, k, desde, 3)
            continue
        for e, otro in ((a, b), (b, a)):
            if gs.vecinos(e, k):                    # en medio de una cadena: no es su arranque
                continue
            probar(_bloque_de_arranque(e, otro, indice, gs.zoom), k, e, 2)
    return out
