"""area_sugerida.py — el área de la hoja que conviene tomar (pedido del usuario 2026-10-20).

En «Área a tomar» el compositor SUGIERE un área para la hoja a la vista; el usuario la usa,
la ajusta y la toma como siempre. La sugerencia es solo un rectángulo marcado: al tomarlo
pasa por el mismo camino que uno dibujado a mano («Sin línea de borde», escala, piezas),
así que el reconocimiento no cambia.

Qué se sugiere, de lo más seguro a lo menos:

  · Plano CAD con match lines («MATCH LINE STA 551+75 SEE DWG UD-202»): la vista del plano
    (`composicion_ficha`) cortada EN cada match line con rótulo — lo mismo que hace la
    composición sugerida con cada hoja (`composicion_sugerida._cortes_cad`).
  · Mapa por cuadrícula (Quarter Section de Phoenix): el marco del mapa, sin leyenda ni cajetín.
  · Si no: candidatos = recortes del PDF (viewports) y, en hojas con capas o mapas, marcos de
    cuatro líneas generales (`composite.guide_lines`); gana el que contiene más tinta VISIBLE
    de las utilidades (hoja con capas: solo capas de utilidad; sin capas: toda la tinta), sin
    las vistas de perfil (`recognition.profile_view_regions`), y entre dos anidados el más
    interior si conserva casi todo. Hoja sin tinta de utilidades (notas, portadas): nada.

Coordenadas de la hoja VISIBLE (con /Rotate), en pt — las del compositor. PURO: solo fitz.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import fitz

from hoja import composicion_ficha as F

Rect = Tuple[float, float, float, float]

FRAC_MIN = 0.05            # un candidato ocupa al menos esto de la hoja…
FRAC_MAX = 0.97            # …y no es la hoja entera
LINEA_MARCO_FRAC = 0.25    # una línea de marco cubre al menos esto del lado de la hoja
MARCO_TOL_PT = 4.0         # las cuatro líneas de un marco se tocan a ≤ esto
CONTENIDO_MIN = 0.05       # el ganador junta al menos esto de la tinta de utilidades de la hoja
INTERIOR_CONSERVA = 0.85   # un candidato interior gana si conserva esto del contenido del mayor
OTRA_MIN = 0.15            # otra vista se ofrece si tiene al menos esto del contenido del ganador
MAX_OTRAS = 2
EN_PERFIL_MAX = 0.5        # un candidato que es más de esto vista de perfil no compite
MARCO_MAX_FRAC = 0.8       # fuera de un mapa, un marco más grande es el borde del plano


@dataclass
class Area:
    """Área sugerida. `tipo`: «planta» (vista entre match lines), «mapa» (marco del mapa),
    «vista» (recorte del PDF con las utilidades) o «marco» (marco de cuatro líneas)."""
    rect: Rect
    tipo: str
    etiqueta: str = ""                                   # número de hoja / celda del mapa
    estaciones: List[str] = field(default_factory=list)  # «551+75» de las match lines del corte
    parte: Optional[float] = None                        # parte de la tinta de utilidades que junta
    # marco que no es recto con la hoja (`borde_inclinado`): sus 4 esquinas (sup-izq, sup-der,
    # inf-der, inf-izq) y `rect` = su caja; [] = el rectángulo
    poligono: List[Tuple[float, float]] = field(default_factory=list)

    def clip(self, tam: Tuple[float, float]) -> List[float]:
        """Clip normalizado (0..1) sobre la hoja visible de tamaño `tam`."""
        W, H = tam
        x0, y0, x1, y1 = self.rect
        return [max(0.0, min(1.0, x0 / W)), max(0.0, min(1.0, y0 / H)),
                max(0.0, min(1.0, x1 / W)), max(0.0, min(1.0, y1 / H))]


# ─────────────────────────── rectángulos ───────────────────────────
def _area(r: Rect) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _inter(a: Rect, b: Rect) -> Rect:
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def _dentro(a: Rect, b: Rect, frac: float = 0.95) -> bool:
    """¿`a` está (casi) dentro de `b`?"""
    return _area(a) > 0 and _area(_inter(a, b)) >= frac * _area(a)


def _iou(a: Rect, b: Rect) -> float:
    i = _area(_inter(a, b))
    u = _area(a) + _area(b) - i
    return i / u if u else 0.0


def iguales(a: Rect, b: Rect, tol: float = 1.0) -> bool:
    return all(abs(a[i] - b[i]) <= tol for i in range(4))


# ─────────────────────────── lo que dice la ficha ───────────────────────────
def _planta(f: F.Ficha) -> Area:
    """La vista del plano cortada en cada match line con rótulo (`_cortes_cad` de una hoja)."""
    from hoja import composicion_encaje as E
    x0, y0, x1, y1 = f.vista
    lados = {"left": x0, "top": y0, "right": x1, "bottom": y1}
    for lado in ("left", "right", "top", "bottom"):
        if not f.lado(lado):
            continue
        r = E.regla(f, lado)
        if r is not None:
            s = (y0 + y1) / 2.0 if lado in ("left", "right") else (x0 + x1) / 2.0
            lados[lado] = r.at(s)
    rect = (lados["left"], lados["top"], lados["right"], lados["bottom"])
    if rect[2] - rect[0] < 1.0 or rect[3] - rect[1] < 1.0:      # una regla rara: la vista tal cual
        rect = f.vista
    est = sorted({r.estacion for r in f.rotulos if r.lado}, reverse=True)
    return Area(rect, "planta", f.etiqueta(), [F.estacion_texto(e) for e in est])


def _es_perfil(r: Rect, perfiles: Sequence[Rect]) -> bool:
    return sum(_area(_inter(r, p)) for p in perfiles) > EN_PERFIL_MAX * _area(r)


def _sin_perfil(page: fitz.Page, f: F.Ficha) -> Optional[F.Ficha]:
    """La ficha con su vista de PLANTA. Los rótulos de la match line pueden quedar junto a DOS
    vistas (LABOE h.26: perfil arriba y planta abajo, un rótulo a la derecha de cada una) y la
    ficha toma la que más rótulos junta, o la más grande. Con capas, entre las vistas con
    rótulos gana la que tiene más tinta de utilidades (el perfil va en capas «PROF»); None si
    la vista es un perfil y no hay otra. Sin capas no se distingue un perfil: tal cual."""
    import dataclasses
    from hoja import pdf_layers
    if not pdf_layers.page_uses_layers(page.parent, page.number):
        return f
    paths = page.get_drawings(extended=True)
    con_rotulo = [c for c in F._recortes(paths, page) if any(F._lado_de(r, c)[0] for r in f.rotulos)]
    if len(con_rotulo) <= 1:
        return f
    perfiles = _perfiles(page)
    tinta = _tinta(paths, page, perfiles, True)
    if not any(_contenido(c, tinta) > 0 for c in con_rotulo):
        return f                          # sin capas de utilidad que lo digan: la de la ficha
    vistas = [(c, _contenido(c, tinta)) for c in con_rotulo if not _es_perfil(c, perfiles)]
    vistas = [(c, n) for c, n in vistas if n > 0]
    if not vistas:
        return None
    v = max(vistas, key=lambda cn: cn[1])[0]
    if iguales(v, f.vista, 2.0):
        return f
    rotulos = [dataclasses.replace(r, lado=F._lado_de(r, v)[0]) for r in f.rotulos]
    return dataclasses.replace(f, vista=v, rotulos=rotulos,
                               lineas=F._trazos(paths, page, v, F.BANDA_CAD_PT, F.BANDA_CAD_PT))


# ─────────────────────────── candidatos ───────────────────────────
def _recortes(paths, page: fitz.Page) -> List[Rect]:
    m = page.rotation_matrix
    W, H = page.rect.width, page.rect.height
    out: List[Rect] = []
    for p in paths:
        if p.get("type") != "clip" or not p.get("scissor"):
            continue
        r = fitz.Rect(p["scissor"]) * m
        r.normalize()
        rr = (r.x0, r.y0, r.x1, r.y1)
        if FRAC_MIN <= _area(rr) / (W * H) <= FRAC_MAX and not any(iguales(rr, q, 2.0) for q in out):
            out.append(rr)
    return out


def _marcos(guias: dict, W: float, H: float) -> List[Rect]:
    """Rectángulos cerrados por cuatro líneas generales (el marco de un mapa sin recorte):
    para cada par de horizontales, las verticales que van de una a la otra dentro de su
    extensión; el par más exterior."""
    xs = [g for g in guias.get("x", ()) if g[3] >= LINEA_MARCO_FRAC * H]
    ys = [g for g in guias.get("y", ()) if g[3] >= LINEA_MARCO_FRAC * W]
    tol = MARCO_TOL_PT
    out: List[Rect] = []
    for j, c in enumerate(ys):
        for d in ys[j + 1:]:
            yt, yb = c[0], d[0]
            alto = yb - yt
            if alto < 0.2 * H:
                continue
            lo, hi = max(c[1], d[1]) - tol, min(c[2], d[2]) + tol
            v = [a[0] for a in xs if a[1] <= yt + tol and a[2] >= yb - tol and a[3] >= 0.9 * alto
                 and lo <= a[0] <= hi]
            if len(v) < 2:
                continue
            xl, xr = min(v), max(v)
            ancho = xr - xl
            r = (xl, yt, xr, yb)
            if (ancho >= 0.2 * W and c[3] >= 0.9 * ancho and d[3] >= 0.9 * ancho
                    and FRAC_MIN <= _area(r) / (W * H) <= FRAC_MAX and not any(iguales(r, q, 2.0) for q in out)):
                out.append(r)
    return out


def _tinta(paths, page: fitz.Page, perfiles: Sequence[Rect], con_capas: bool):
    """Matriz n×3 (x, y del punto medio, largo) de cada trazo VISIBLE (dentro de sus
    recortes) de las utilidades: en una hoja con capas solo las capas de utilidad (sin
    perfil, anotación ni texto); sin capas, toda la tinta. Sin lo que cae en un perfil."""
    import numpy as np
    from hoja import pdf_layers
    m = page.rotation_matrix
    pesos: dict = {}
    pila: dict = {}
    out = []
    for p in paths:
        tipo = p.get("type")
        lvl = int(p.get("level", 0) or 0)
        if tipo == "clip":
            pila = {k: r for k, r in pila.items() if k < lvl}
            sc = p.get("scissor")
            if sc:
                r = fitz.Rect(sc) * m
                r.normalize()
                pila[lvl] = (r.x0, r.y0, r.x1, r.y1)
            continue
        if tipo == "group":
            pila = {k: r for k, r in pila.items() if k < lvl}
            continue
        if tipo == "f":
            continue
        if con_capas:
            capa = p.get("layer") or ""
            if capa not in pesos:
                corto = pdf_layers.short_name(capa).upper()
                pesos[capa] = not (pdf_layers.utility_of(capa) == pdf_layers.UTILITY_OTHER
                                   or "PROF" in corto or "ANNO" in corto or "TEXT" in corto)
            if not pesos[capa]:
                continue
        activos = [r for k, r in pila.items() if k < lvl]
        for it in p.get("items") or ():
            if it[0] == "l":
                a, b = it[1], it[2]
            elif it[0] == "c":
                a, b = it[1], it[4]
            else:
                continue
            a, b = a * m, b * m
            largo = math.hypot(b.x - a.x, b.y - a.y)
            if largo < 0.5:
                continue
            xm, ym = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
            if any(r[0] <= xm <= r[2] and r[1] <= ym <= r[3] for r in perfiles):
                continue
            if any(not (r[0] <= xm <= r[2] and r[1] <= ym <= r[3]) for r in activos):
                continue
            out.append((xm, ym, largo))
    return np.array(out, float).reshape(-1, 3)


def _contenido(r: Rect, tinta) -> float:
    x, y, largo = tinta[:, 0], tinta[:, 1], tinta[:, 2]
    return float(largo[(x >= r[0]) & (x <= r[2]) & (y >= r[1]) & (y <= r[3])].sum())


def _perfiles(page: fitz.Page) -> List[Rect]:
    from hoja import pdf_styles
    from reconocimiento import recognition as R
    m = page.rotation_matrix
    out = []
    with pdf_styles.lectura_unica(page.parent):
        for b in R.profile_view_regions(page):
            r = fitz.Rect(b) * m
            r.normalize()
            out.append((r.x0, r.y0, r.x1, r.y1))
    return out


def _por_contenido(page: fitz.Page, f: F.Ficha) -> List[Area]:
    from hoja import composite as C
    W, H = page.rect.width, page.rect.height
    paths = page.get_drawings(extended=True)
    con_capas = any(p.get("layer") for p in paths if p.get("type") not in ("clip", "group"))
    perfiles = _perfiles(page) if con_capas else []
    cands = [(r, "vista") for r in _recortes(paths, page)]
    # marcos dibujados con líneas sueltas: solo en hojas con capas (la tinta es la de las
    # utilidades) o mapas; en una hoja aplanada sin vista sería el marco de toda la hoja
    # (fuera de un mapa, un marco de casi toda la hoja es el borde del plano, no una vista)
    if con_capas or f.celda is not None:
        cands += [(r, "marco") for r in _marcos(C.guide_lines(page), W, H)
                  if not any(iguales(r, q, 2.0) for q, _t in cands)
                  and (f.celda is not None or _area(r) <= MARCO_MAX_FRAC * W * H)]
    tinta = _tinta(paths, page, perfiles, con_capas)
    total = float(tinta[:, 2].sum()) if len(tinta) else 0.0
    if not cands or total <= 0:
        return []
    punt = []
    for r, tipo in cands:
        if _es_perfil(r, perfiles):
            continue
        punt.append((_contenido(r, tinta), r, tipo))
    punt.sort(key=lambda t: (-t[0], _area(t[1])))
    if not punt or punt[0][0] < CONTENIDO_MIN * total:
        return []
    mejor = punt[0]
    for c in sorted(punt, key=lambda t: _area(t[1])):        # el más interior que conserva casi todo
        if c is mejor:
            break
        if _dentro(c[1], mejor[1]) and c[0] >= INTERIOR_CONSERVA * mejor[0]:
            mejor = c
            break
    etiqueta = f.etiqueta() if (f.numero or f.celda is not None) else ""
    out = [Area(mejor[1], "mapa" if f.celda is not None else mejor[2], etiqueta, parte=mejor[0] / total)]
    # otras vistas solo con capas: sin ellas no se distingue un perfil (DU10 h.34–37)
    for c in punt if con_capas else ():
        if len(out) > MAX_OTRAS:
            break
        if (c[2] == "vista" and c is not mejor and c[0] >= OTRA_MIN * mejor[0] and _iou(c[1], mejor[1]) < 0.3
                and not _dentro(c[1], mejor[1]) and not _dentro(mejor[1], c[1])
                and not any(_dentro(c[1], o.rect) or _dentro(o.rect, c[1]) for o in out)):
            out.append(Area(c[1], "vista", etiqueta, parte=c[0] / total))
    return out


# ─────────────────────────── API ───────────────────────────
def sugerir(page: fitz.Page, ficha: Optional[F.Ficha] = None) -> List[Area]:
    """Áreas sugeridas para la hoja, la mejor primero ([] = nada que sugerir). Si el marco del
    área no es recto con la hoja, el área va con sus esquinas (`Area.poligono`)."""
    areas = _sugerir(page, ficha)
    if areas:
        paths = page.get_drawings(extended=True)
        for a in areas:
            con_borde(page, a, paths)
    return areas


def con_borde(page: fitz.Page, a: Area, paths=None) -> Area:
    """`a` con el cuadrilátero de su marco si tiene un borde inclinado (`borde_inclinado`)."""
    from hoja import borde_inclinado as B
    q = B.cuadrilatero(page, a.rect, paths)
    if q:
        a.poligono = [(float(x), float(y)) for x, y in q]
        xs, ys = [p[0] for p in q], [p[1] for p in q]
        a.rect = (min(xs), min(ys), max(xs), max(ys))
    return a


def _sugerir(page: fitz.Page, ficha: Optional[F.Ficha] = None) -> List[Area]:
    f = ficha if ficha is not None else F.ficha(page)
    if f.tipo == "estaciones" and f.vista is not None:
        f = _sin_perfil(page, f)
        if f is not None:
            return [_planta(f)]
        f = ficha if ficha is not None else F.ficha(page)
        return _por_contenido(page, f)
    if f.celda is not None and f.vista is not None:
        return [Area(f.vista, "mapa", f.etiqueta())]
    return _por_contenido(page, f)


_DOCS: "OrderedDict[str, fitz.Document]" = OrderedDict()   # en el proceso trabajador
MAX_DOCS = 3


def _doc(clave: str, fuente) -> fitz.Document:
    doc = _DOCS.get(clave)
    if doc is None:
        doc = fitz.open(fuente) if isinstance(fuente, str) else fitz.open(stream=fuente, filetype="pdf")
        _DOCS[clave] = doc
        while len(_DOCS) > MAX_DOCS:
            _DOCS.popitem(last=False)[1].close()
    else:
        _DOCS.move_to_end(clave)
    return doc


def sugerir_en_pdf(clave: str, fuente, pagina: int, progreso=None) -> List[Area]:
    """El trabajo del proceso «area» (`ui.comun.proceso`): `fuente` = ruta o bytes del PDF;
    el documento queda abierto en el trabajador para las hojas siguientes."""
    return sugerir(_doc(clave, fuente)[pagina])
