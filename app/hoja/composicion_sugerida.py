"""composicion_sugerida.py — revisar TODAS las hojas y sugerir la hoja compuesta.

Pedido del usuario 2026-10-14: al abrir un PDF vectorial (con capas o aplanado; los
escaneos siguen siendo manuales), analizar cada hoja y, si hay certeza, sugerir la
composición; si el usuario la acepta se toma tal cual, si no compone a mano.

  1. `composicion_ficha`: qué dice cada hoja (match lines, número y serie, cuadrícula).
  2. Parejas por el TEXTO: misma estación a un lado y otro (±60 ft: hay erratas), o
     celdas vecinas de la cuadrícula en la dirección del mapa índice.
  3. Cada pareja se CONFIRMA con el dibujo (`composicion_encaje`); lo no confirmado no
     se une. Entre series paralelas del mismo tramo (UR-602 / UR-602A) se une primero
     dentro de la serie.
  4. Grupos = componentes conexas; las transformaciones se encadenan por las uniones
     más fuertes y las demás se usan de control (ciclos): si no cierran, el grupo se
     parte (nunca una unión dudosa).
  5. `armar`: un `Composite` normal (el compositor lo muestra, edita y guarda):
     plano CAD → cada hoja recortada EN su match line, borde con borde; mapa → costuras
     rectas por el medio del solape (comunes a toda la fila/columna si cabe: sin
     huecos ni trazos dobles).

PURO: fitz + numpy. La escala de cada hoja la da quien llama (`escala_de`).
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import fitz

from hoja import composite as C
from hoja import borde_inclinado as BI
from hoja import composicion_costuras as K
from hoja import composicion_encaje as E
from hoja.composicion_ficha import Ficha, Rect, estacion_texto

Nodo = Tuple[int, int]                       # (pdf, hoja)

TOL_ESTACION_FT = 60.0       # rótulos de una misma costura: misma estación (las erratas medidas: 50 ft)
TOL_CICLO_PT = 1.0           # una unión de control que no cierra a ≤ esto parte el grupo
DOMINIO_CANDIDATO = 1.5      # varias vecinas confirmadas por el mismo lado: la mejor debe destacar
LADOS_ADELANTE = ("right", "bottom")
DIR_LADO = {(1, 0): "right", (-1, 0): "left", (0, 1): "bottom", (0, -1): "top"}
LADO_DIR = {v: k for k, v in DIR_LADO.items()}


@dataclass
class Grupo:
    tipo: str                                   # estaciones | cuadricula
    nodos: List[Nodo]
    costuras: List[E.Costura]
    series: List[str] = field(default_factory=list)
    transf: Dict[Nodo, Tuple[float, float, float]] = field(default_factory=dict)   # a, bx, by
    rejilla: Dict[Nodo, Tuple[int, int]] = field(default_factory=dict)           # (gx, gy) de cada hoja
    residuo: float = 0.0
    faltan: List[Tuple[int, int]] = field(default_factory=list)                 # celdas vecinas ausentes
    composite: Optional[C.Composite] = None

    def contiene(self, nodo: Nodo) -> bool:
        return nodo in self.nodos


@dataclass
class Analisis:
    fichas: Dict[Nodo, Ficha]
    grupos: List[Grupo]
    descartadas: int = 0                        # parejas del texto que el dibujo no confirmó

    def grupo_de(self, nodo: Nodo) -> Optional[Grupo]:
        g = [x for x in self.grupos if x.contiene(nodo)]
        return max(g, key=lambda x: len(x.nodos)) if g else None

    def faltan(self) -> List[Tuple[int, int]]:
        out = set()
        for g in self.grupos:
            out.update(g.faltan)
        return sorted(out)


# ─────────────────────────── parejas por el texto ───────────────────────────
def _parejas_cad(fichas: Dict[Nodo, Ficha]):
    """(A, lado, B, rótulo A, rótulo B, Δ estación) con A a la izquierda/arriba."""
    cad = [f for f in fichas.values() if f.tipo == "estaciones"]
    out = []
    for fa in cad:
        for lado in LADOS_ADELANTE:
            for ra in fa.lado(lado):
                for fb in cad:
                    if fb is fa:
                        continue
                    for rb in fb.lado(E.OPUESTO[lado]):
                        d = abs(ra.estacion - rb.estacion)
                        if d <= TOL_ESTACION_FT:
                            out.append((fa, lado, fb, ra, rb, d))
    return out


def _confirmar_cad(fichas: Dict[Nodo, Ficha], cancelado=None) -> Tuple[List[E.Costura], int]:
    """Confirma con el dibujo las parejas CAD. Por cada lado de una hoja: primero las
    de su misma serie (UR-602 → UR-603, no UR-603A); si ninguna confirma, las demás.
    Si dos vecinas confirman por el mismo lado, gana la de más votos solo si destaca."""
    por_lado: Dict[Tuple[Nodo, str], list] = defaultdict(list)
    for fa, lado, fb, ra, rb, d in _parejas_cad(fichas):
        por_lado[(fa.clave, lado)].append((fa, fb, ra, rb, d))
    hechas: List[E.Costura] = []
    descartadas = 0
    for (_n, lado), cands in por_lado.items():
        if cancelado is not None and cancelado():
            break
        fa = cands[0][0]
        misma = [c for c in cands if c[1].serie == fa.serie or not c[1].serie or not fa.serie]
        otras = [c for c in cands if c not in misma]
        conf: List[E.Costura] = []
        for grupo in (misma, otras):
            for _fa, fb, ra, rb, d in sorted(grupo, key=lambda c: c[4]):
                c = E.costura_cad(fa, fb, lado, ra, rb)
                if c is None:
                    descartadas += 1
                elif not any(x.b == c.b for x in conf):
                    conf.append(c)
            if conf:
                break
        if not conf:
            continue
        conf.sort(key=lambda c: -c.votos)
        if len(conf) > 1 and conf[0].votos < DOMINIO_CANDIDATO * conf[1].votos:
            continue                       # dos vecinas igual de buenas: no se adivina
        hechas.append(conf[0])
    # una hoja B tampoco puede quedar unida por el MISMO lado a dos hojas A
    por_b: Dict[Tuple[Nodo, str], List[E.Costura]] = defaultdict(list)
    for c in hechas:
        por_b[(c.b, E.OPUESTO[c.lado])].append(c)
    final = []
    for cs in por_b.values():
        cs.sort(key=lambda c: -c.votos)
        if len(cs) == 1 or cs[0].votos >= DOMINIO_CANDIDATO * cs[1].votos:
            final.append(cs[0])
    return final, descartadas


def convencion_rejilla(fichas: Dict[Nodo, Ficha]) -> Dict[Tuple[int, int], Tuple[int, int]]:
    """Dirección en la hoja de cada vecina según el cambio de celda (Δfila, Δcol),
    aprendida de los mapas índice (Phoenix: fila +1 = norte = arriba)."""
    votos: Dict[Tuple[int, int], Dict[Tuple[int, int], int]] = defaultdict(lambda: defaultdict(int))
    for f in fichas.values():
        if f.celda is None:
            continue
        for c, d in f.vecinas.items():
            dr, dc = c[0] - f.celda[0], c[1] - f.celda[1]
            if abs(dr) + abs(dc) == 1:
                votos[(dr, dc)][d] += 1
    return {k: max(v.items(), key=lambda it: it[1])[0] for k, v in votos.items()}


def _direccion(fa: Ficha, fb: Ficha, conv) -> Optional[Tuple[int, int]]:
    if fb.celda in fa.vecinas:
        return fa.vecinas[fb.celda]
    if fa.celda in fb.vecinas:
        d = fb.vecinas[fa.celda]
        return -d[0], -d[1]
    dr, dc = fb.celda[0] - fa.celda[0], fb.celda[1] - fa.celda[1]
    return conv.get((dr, dc))


def _parejas_mapa(fichas: Dict[Nodo, Ficha]):
    """(A, lado, B) de celdas vecinas, orientadas con A a la izquierda/arriba."""
    conv = convencion_rejilla(fichas)
    por_celda: Dict[Tuple[int, int], List[Ficha]] = defaultdict(list)
    for f in fichas.values():
        if f.tipo == "cuadricula":
            por_celda[f.celda].append(f)
    out = []
    vistos = set()
    for celda, fs in por_celda.items():
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for fa in fs:
                for fb in por_celda.get((celda[0] + dr, celda[1] + dc), ()):
                    k = tuple(sorted((fa.clave, fb.clave)))
                    if k in vistos:
                        continue
                    d = _direccion(fa, fb, conv)
                    if d not in DIR_LADO:
                        continue
                    vistos.add(k)
                    lado = DIR_LADO[d]
                    if lado in LADOS_ADELANTE:
                        out.append((fa, lado, fb))
                    else:
                        out.append((fb, E.OPUESTO[lado], fa))
    return out


def _mediana(vals: Sequence[float]) -> float:
    v = sorted(vals)
    return v[len(v) // 2]


def _confirmar_mapa(fichas: Dict[Nodo, Ficha], cancelado=None) -> Tuple[List[E.Costura], int]:
    """Solape de cada pareja de celdas vecinas; las que no dan un pico claro se
    reintentan GUIADAS por la traslación y escala de las parejas ya confirmadas
    entre los mismos PDF y por el mismo lado (casi constante en una fila de hojas)."""
    parejas = _parejas_mapa(fichas)
    hechas: List[E.Costura] = []
    pend = []
    for fa, lado, fb in parejas:
        if cancelado is not None and cancelado():
            return hechas, 0
        c = E.encaje_mapa(fa, fb, lado)
        if c is None:
            pend.append((fa, lado, fb))
        else:
            hechas.append(c)
    descartadas = 0
    for fa, lado, fb in pend:
        if cancelado is not None and cancelado():
            break
        ref = [c for c in hechas if c.lado == lado and c.a[0] == fa.doc and c.b[0] == fb.doc]
        c = None
        if len(ref) >= 2:
            guia = (_mediana([r.t[0] for r in ref]), _mediana([r.t[1] for r in ref]))
            c = E.encaje_mapa(fa, fb, lado, escala=_mediana([r.escala for r in ref]), guia=guia)
        if c is None:
            descartadas += 1
        else:
            hechas.append(c)
    return hechas, descartadas


# ─────────────────────────── grupos ───────────────────────────
def _encadenar(nodos: Sequence[Nodo], costuras: Sequence[E.Costura], fichas: Dict[Nodo, Ficha]):
    """Transformación de cada hoja a la hoja compuesta (global = a·p + b) por las
    uniones más fuertes (árbol de máximo peso) y el residuo de las demás uniones."""
    raiz = min(nodos)
    T: Dict[Nodo, Tuple[float, float, float]] = {raiz: (1.0, 0.0, 0.0)}
    rej: Dict[Nodo, Tuple[int, int]] = {raiz: (0, 0)}
    arbol = set()
    orden = sorted(costuras, key=lambda c: -c.votos)
    cambio = True
    while cambio:
        cambio = False
        for c in orden:
            if id(c) in arbol:
                continue
            s, (tx, ty) = c.escala, c.t
            dx, dy = LADO_DIR[c.lado]
            if c.a in T and c.b not in T:
                a, bx, by = T[c.a]
                T[c.b] = (a / s, bx - a * tx / s, by - a * ty / s)
                rej[c.b] = (rej[c.a][0] + dx, rej[c.a][1] + dy)
            elif c.b in T and c.a not in T:
                a, bx, by = T[c.b]
                T[c.a] = (a * s, bx + a * tx, by + a * ty)
                rej[c.a] = (rej[c.b][0] - dx, rej[c.b][1] - dy)
            else:
                continue
            arbol.add(id(c))
            cambio = True
            break
    malos = []
    peor = 0.0
    for c in costuras:
        if id(c) in arbol:
            continue
        r = _residuo(c, T, fichas)
        peor = max(peor, r)
        if r > TOL_CICLO_PT:
            malos.append(c)
    return T, rej, peor, malos


def _residuo(c: E.Costura, T, fichas: Dict[Nodo, Ficha]) -> float:
    """Distancia entre un punto de la hoja a llevado por su transformación y el mismo
    punto llevado por la unión + la transformación de b."""
    fa = fichas[c.a]
    v = E.caja(fa) or (0.0, 0.0, fa.tam[0], fa.tam[1])
    a1, bx1, by1 = T[c.a]
    a2, bx2, by2 = T[c.b]
    worst = 0.0
    for x, y in ((v[0], v[1]), (v[2], v[3]), ((v[0] + v[2]) / 2, (v[1] + v[3]) / 2)):
        p1 = (a1 * x + bx1, a1 * y + by1)
        xb, yb = c.mapa(x, y)
        p2 = (a2 * xb + bx2, a2 * yb + by2)
        worst = max(worst, math.hypot(p1[0] - p2[0], p1[1] - p2[1]))
    return worst


def _componentes(nodos: Sequence[Nodo], costuras: Sequence[E.Costura]) -> List[List[Nodo]]:
    padre = {n: n for n in nodos}

    def raiz(n):
        while padre[n] != n:
            padre[n] = padre[padre[n]]
            n = padre[n]
        return n
    for c in costuras:
        padre[raiz(c.a)] = raiz(c.b)
    grupos: Dict[Nodo, List[Nodo]] = defaultdict(list)
    for n in nodos:
        grupos[raiz(n)].append(n)
    return [sorted(g) for g in grupos.values() if len(g) > 1]


def _grupos(tipo: str, costuras: List[E.Costura], fichas: Dict[Nodo, Ficha]) -> List[Grupo]:
    """Componentes conexas con control de ciclos: una unión de control que no cierra
    saca del grupo la unión más débil de ese ciclo (y la de control), hasta que todo
    cierre. Así nunca se sugiere una unión contradicha por el resto del dibujo."""
    cost = list(costuras)
    for _ in range(50):
        nodos = sorted({c.a for c in cost} | {c.b for c in cost})
        malos_todos = []
        res: List[Grupo] = []
        for comp in _componentes(nodos, cost):
            cs = [c for c in cost if c.a in comp]
            T, rej, peor, malos = _encadenar(comp, cs, fichas)
            if malos:
                malos_todos.extend(malos)
                continue
            res.append(Grupo(tipo, comp, cs, transf=T, rejilla=rej, residuo=peor))
        if not malos_todos:
            return res
        quitar = set()
        for m in malos_todos:
            ciclo = [c for c in cost if {c.a, c.b} & {m.a, m.b}]
            quitar.add(id(min(ciclo + [m], key=lambda c: c.votos)))
            quitar.add(id(m))
        cost = [c for c in cost if id(c) not in quitar]
    return []


def _ordenar(g: Grupo) -> None:
    """Hojas en orden de lectura de la hoja compuesta (izquierda→derecha, arriba→abajo)."""
    g.nodos.sort(key=lambda n: (g.rejilla.get(n, (0, 0))[1], g.rejilla.get(n, (0, 0))[0], n))


def analizar(fichas_por_doc: Sequence[Sequence[Ficha]], cancelado=None, progreso=None) -> Analisis:
    """Todas las parejas confirmadas y sus grupos (sin armar: ver `armar`)."""
    fichas: Dict[Nodo, Ficha] = {}
    for fs in fichas_por_doc:
        mapa = [f for f in fs if f.tipo == "cuadricula"]
        if mapa:
            tpl = E.plantilla(mapa)
            for f in mapa:
                E.sin_plantilla(f, tpl)
        for f in fs:
            fichas[f.clave] = f
    if progreso is not None:
        progreso("cad")
    cad, d1 = _confirmar_cad(fichas, cancelado)
    if progreso is not None:
        progreso("mapa")
    mapa, d2 = _confirmar_mapa(fichas, cancelado)
    grupos = _grupos("estaciones", cad, fichas) + _grupos("cuadricula", mapa, fichas)
    presentes = {f.celda for f in fichas.values() if f.celda is not None}
    for g in grupos:
        _ordenar(g)
        g.series = sorted({fichas[n].serie for n in g.nodos if fichas[n].serie})
        if g.tipo == "cuadricula":
            ref = set()
            for n in g.nodos:
                ref.update(c for c in fichas[n].vecinas if (c[0] == fichas[n].celda[0]) != (c[1] == fichas[n].celda[1]))
            g.faltan = sorted(ref - presentes)
    grupos.sort(key=lambda g: -len(g.nodos))
    return Analisis(fichas, grupos, d1 + d2)


# ─────────────────────────── armar la hoja compuesta ───────────────────────────
def _norm(rect: Rect, tam: Tuple[float, float]) -> List[float]:
    W, H = tam
    return C.normalize_clip([rect[0] / W, rect[1] / H, rect[2] / W, rect[3] / H])


def _cortes_cad(g: Grupo, fichas: Dict[Nodo, Ficha]) -> Dict[Nodo, Rect]:
    """Vista de cada hoja recortada EN su match line por cada lado con vecina (y por
    los lados con rótulo aunque la vecina no esté: lo de más allá es de otra hoja)."""
    out: Dict[Nodo, Rect] = {}
    for n in g.nodos:
        f = fichas[n]
        x0, y0, x1, y1 = f.vista
        lados = {"left": x0, "top": y0, "right": x1, "bottom": y1}
        hechos = set()
        for c in g.costuras:
            if c.a == n and c.corte_a is not None:
                lados[c.lado] = c.corte_a; hechos.add(c.lado)
            elif c.b == n and c.corte_b is not None:
                lados[E.OPUESTO[c.lado]] = c.corte_b; hechos.add(E.OPUESTO[c.lado])
        for lado in ("left", "right", "top", "bottom"):
            if lado in hechos or not f.lado(lado):
                continue
            r = E.regla(f, lado)
            if r is not None:
                v = f.vista
                s = (v[1] + v[3]) / 2.0 if lado in ("left", "right") else (v[0] + v[2]) / 2.0
                lados[lado] = r.at(s)
        out[n] = (lados["left"], lados["top"], lados["right"], lados["bottom"])
    return out


def armar(g: Grupo, analisis: Analisis, docs: Sequence[fitz.Document],
          escala_de: Callable[[int, int], float], nombres: Sequence[str] = ()) -> C.Composite:
    """`Composite` de un grupo: piezas recortadas y colocadas como dice el dibujo."""
    fichas = analisis.fichas
    raiz = min(g.nodos)
    base = float(escala_de(*raiz))
    if g.tipo == "estaciones":
        rects_pag = _cortes_cad(g, fichas)
    else:
        R, T = {}, {}
        for n in g.nodos:
            a, bx, by = g.transf[n]
            v = E.caja(fichas[n])
            t = K.tinta(fichas[n], v)
            R[n] = (a * v[0] + bx, a * v[1] + by, a * v[2] + bx, a * v[3] + by)
            T[n] = (a * t[0] + bx, a * t[1] + by, a * t[2] + bx, a * t[3] + by)
        glob = K.costuras_rectas(g, R, fichas, T)
        rects_pag = {}
        for n, (gx0, gy0, gx1, gy1) in glob.items():
            a, bx, by = g.transf[n]
            rects_pag[n] = ((gx0 - bx) / a, (gy0 - by) / a, (gx1 - bx) / a, (gy1 - by) / a)
    comp = C.Composite()
    comp.scale_ft_per_pt = base
    # mapa: las dos piezas se cortan por la MISMA recta y sus líneas ya se tocan; los
    # puentes solo agregarían trazos de largo ~0 (en el plano CAD cruzan la franja blanca)
    comp.bridges = g.tipo == "estaciones"
    for n in g.nodos:
        f = fichas[n]
        page = docs[n[0]][n[1]]
        clip = _norm(rects_pag[n], f.tam)
        covers: Dict[str, float] = {}
        if g.tipo == "estaciones":
            clip, covers = C.trim_border(page, clip)
        # hoja cuyo marco no es recto con la hoja (2026-10-21): la pieza sigue su borde inclinado,
        # como «Esquinas libres» (fuera queda solo papel en blanco: el reconocimiento no cambia)
        poligono: List[List[float]] = []
        if f.lineas:
            # CAD: los vectores de la hoja que `trim_border` ya dejó en caché (también el marco
            # cerrado en UN elemento «qu»/«re»); mapa: las rectas de los bordes de su ficha
            segs = (BI._segmentos(C.page_drawings(page), page.rotation_matrix)
                    if g.tipo == "estaciones" else f.lineas)
            q = BI.cuadrilatero(page, tuple(C.clip_rect_pt(f.tam, clip)), segs=segs)
            if q:
                poligono = BI.normalizado(q, f.tam)
                xs, ys = [p[0] for p in q], [p[1] for p in q]
                clip = _norm((min(xs), min(ys), max(xs), max(ys)), f.tam)
                covers = {}
        a, bx, by = g.transf[n]
        x0, y0, _x1, _y1 = C.clip_rect_pt(f.tam, clip)
        nombre = nombres[n[0]] if n[0] < len(nombres) else ""
        etiqueta = f.etiqueta()
        label = " · ".join(p for p in (nombre, str(n[1] + 1), etiqueta if etiqueta != str(n[1] + 1) else "") if p)
        comp.pieces.append(C.Piece(n[0], n[1], clip, x=a * x0 + bx, y=a * y0 + by, rotation=0.0,
                                   src_scale=base * a, label=label, covers=covers, polygon=poligono))
    mx = min(p.x for p in comp.pieces)
    my = min(p.y for p in comp.pieces)
    for p in comp.pieces:
        p.x -= mx
        p.y -= my
    g.composite = comp
    return comp


def resumen_datos(g: Grupo, fichas: Dict[Nodo, Ficha]) -> dict:
    """Lo que la interfaz muestra de un grupo: hojas, primera/última, estaciones."""
    primera, ultima = fichas[g.nodos[0]], fichas[g.nodos[-1]]
    est = []
    for n in g.nodos:
        est.extend(r.estacion for r in fichas[n].rotulos if r.lado)
    datos = {"n": len(g.nodos), "desde": primera.etiqueta(), "hasta": ultima.etiqueta(),
             "series": g.series, "tipo": g.tipo, "pdfs": sorted({n[0] for n in g.nodos})}
    if est:
        datos["sta"] = (estacion_texto(max(est)), estacion_texto(min(est)))
    return datos
