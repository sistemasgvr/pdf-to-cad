"""Ejes de la red en IMAGEN en una hoja COMPUESTA (PURO: fitz, sin Qt).

El diseño (§7.2, «Hoja compuesta») manda: NO se lee la imagen de la hoja compuesta. Se toman los ejes de cada
hoja de ORIGEN (memorizados por hoja) y se llevan a la compuesta con la transformación de su pieza, recortados a
lo que se ve de ella. Así la compuesta da los MISMOS ejes que las hojas sueltas (leyendo la imagen de la compuesta,
la rejilla de las teselas y la paleta de las dos hojas juntas daban otros ejes: la pieza h.4 de Phoenix SD South
salía con 861 ejes contra 539 suelta).

De dónde sale la hoja de origen: `pdf_styles.drawings` solo recibe la hoja materializada (`composite.build_document`).
Cada pieza es ahí un XObject `fzFrmN` (lo crea `show_pdf_page`) con `/Matrix` = `piece_map` de la pieza (en el
espacio del PDF), `/BBox` = su recorte en la hoja de origen sin girar, y dentro `/fullpage` = la hoja de origen
ENTERA (su contenido tal cual: el mismo `read_contents()` de la hoja suelta, con sus imágenes). Con eso se arma, en
un documento en memoria, una página con solo `/fullpage` y la caja de la hoja de origen: sus ejes son los de la
hoja suelta (mismas coordenadas sin girar que `get_drawings`). El recorte con «esquinas libres» va en el contenido
de la compuesta («x y m … h W n» antes del `Do`).

Cada trazo llevado a la compuesta lleva el `seqno` del inicio de SU pieza (`leyenda_mapa_lectura.inicios_de_piezas`,
como los vectores de esa pieza) y `clip_polys`/`cut_pts` de su recorte (como los deja `gather_paths` en un trazo
recortado): `recognition_ink_lines` suelda las costuras de las tuberías de imagen como las de los vectores.

Si la hoja no tiene esa forma (otro productor, un `cm` antes del `Do`…), `piezas` da None y se lee la imagen de la
hoja como antes.
"""

from __future__ import annotations

import collections
import hashlib
import re

import fitz

_DO = re.compile(rb"/([^\s/\[\]()<>{}]+)\s+Do\b")
_POLIGONO = re.compile(rb"((?:-?[\d.]+\s+-?[\d.]+\s+[ml]\s+)+)h\s+W\s+n")
_NUM_REF = re.compile(r"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R")
_CACHE_MAX = 48                      # hojas de origen memorizadas en el proceso (una compuesta de 36 mapas entra)
_CACHE: "collections.OrderedDict" = collections.OrderedDict()
_TOL_BORDE = 0.25                    # = recognition_geom.CLIP_EDGE_TOL_PT


def _por(m1, m2) -> tuple:
    """m1 seguida de m2 (matrices (a, b, c, d, e, f) de PDF), en dobles: `fitz.Matrix` multiplica en float de C
    (hasta 3e-5 pt de diferencia a 6000 pt)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


def aplicar(m, x, y) -> tuple:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


class Pieza:
    """Una pieza de la hoja compuesta: nombre de su forma en los recursos de la hoja, la forma `/fullpage`
    (hoja de origen entera), su caja (`/BBox` = recorte en el espacio del PDF de origen), la matriz origen →
    compuesta (coordenadas de `get_drawings`) y el polígono de lo que se ve (coordenadas de la compuesta)."""

    def __init__(self, nombre, xref_forma, xref_hoja, caja, matriz, poligono):
        self.nombre = nombre
        self.xref_forma = xref_forma
        self.xref_hoja = xref_hoja
        self.caja = caja
        self.matriz = matriz
        self.poligono = poligono


def _ref(doc, xref, clave) -> int | None:
    t, v = doc.xref_get_key(xref, clave)
    if t != "xref":
        return None
    try:
        return int(v.split()[0])
    except (ValueError, IndexError):
        return None


def _nombres(doc, xref) -> dict:
    """{nombre: xref} de `/Resources/XObject` del objeto `xref`."""
    t, v = doc.xref_get_key(xref, "Resources/XObject")
    if t == "xref":
        v = doc.xref_object(int(v.split()[0]))
    elif t != "dict":
        return {}
    return {m.group(1): int(m.group(2)) for m in _NUM_REF.finditer(v)}


def _nums(doc, xref, clave) -> list[float] | None:
    t, v = doc.xref_get_key(xref, clave)
    if t != "array":
        return None
    try:
        return [float(x) for x in v.strip("[] ").split()]
    except ValueError:
        return None


def piezas(page) -> list[Pieza] | None:
    """Las piezas de una hoja compuesta materializada, en el orden de dibujo; None si la hoja no es una
    compuesta con piezas `fullpage` (o trae algo que no se sabe llevar)."""
    doc = page.parent
    recursos = _nombres(doc, page.xref)
    mb = page.mediabox
    a_fitz = (1.0, 0.0, 0.0, -1.0, -mb.x0, mb.y1)              # espacio del PDF → get_drawings (sin giro)
    out = []
    for xc in page.get_contents():
        flujo = doc.xref_stream(xc) or b""
        for m in _DO.finditer(flujo):
            nombre = m.group(1).decode("latin-1")
            xf = recursos.get(nombre)
            if xf is None:
                continue
            hoja = _nombres(doc, xf).get("fullpage")
            if hoja is None:
                continue                                      # otra forma (no es una pieza)
            antes = flujo[:m.start()]
            if b" cm" in antes or b"\ncm" in antes:
                return None
            caja, mat = _nums(doc, xf, "BBox"), _nums(doc, xf, "Matrix") or [1, 0, 0, 1, 0, 0]
            if not caja or len(caja) != 4 or len(mat) != 6:
                return None
            hb = _nums(doc, hoja, "BBox")
            if not hb or len(hb) != 4:
                return None
            de_origen = (1.0, 0.0, 0.0, -1.0, hb[0], hb[3])       # get_drawings de la hoja de origen → PDF
            matriz = _por(_por(de_origen, tuple(mat)), a_fitz)
            pg = _POLIGONO.search(antes)
            if pg:
                v = [float(x) for x in re.findall(rb"-?[\d.]+", pg.group(1))]
                poligono = [aplicar(a_fitz, v[i], v[i + 1]) for i in range(0, len(v), 2)]
            else:
                c = _por((1.0, 0.0, 0.0, -1.0, -hb[0], hb[3]), matriz)   # PDF de origen → compuesta
                poligono = [aplicar(c, x, y) for x, y in ((caja[0], caja[1]), (caja[2], caja[1]),
                                                           (caja[2], caja[3]), (caja[0], caja[3]))]
            out.append(Pieza(nombre, xf, hoja, hb, matriz, poligono))
    return out or None


def _huella(doc, contenido: bytes, caja, xref_recursos) -> str:
    """Huella de una hoja de origen: su contenido, su caja y los bytes de sus imágenes."""
    h = hashlib.sha1(contenido)
    h.update(repr([round(float(v), 4) for v in caja]).encode())
    for nombre, x in sorted(_nombres(doc, xref_recursos).items()):
        if doc.xref_get_key(x, "Subtype")[1] == "/Image":
            h.update(nombre.encode())
            h.update(doc.xref_stream_raw(x) or b"")
    return h.hexdigest()


def huella_hoja(page) -> str:
    """Huella de una hoja suelta (la misma que la de su `/fullpage` en una compuesta).

    `get_drawings` (y los ejes) van en coordenadas de la CROPBOX; la hoja de origen que arma `ejes_de_piezas` tiene
    CropBox = MediaBox. Si la hoja suelta trae otra CropBox, sus ejes van en otro sistema y su huella la incluye: con
    el mismo contenido no comparten la memoria (los de una quedaban corridos en la otra). Sin CropBox propia, la
    huella es la de siempre."""
    mb, cb = page.mediabox, page.cropbox
    h = _huella(page.parent, page.read_contents(), (mb.x0, mb.y0, mb.x1, mb.y1), page.xref)
    if max(abs(a - b) for a, b in zip(mb, cb)) > 1e-3:
        h += "|crop" + repr([round(float(v), 4) for v in cb])
    return h


def memo(clave: str, calcular):
    """Ejes de una hoja de origen memorizados en el proceso (LRU de `_CACHE_MAX`) y en disco (`imagen_cache`: no se
    vuelven a leer al reabrir el proyecto). Nadie modifica la lista."""
    if clave in _CACHE or _de_disco(clave):
        _CACHE.move_to_end(clave)
        return _CACHE[clave]
    v = calcular()
    from hoja import imagen_cache
    imagen_cache.guardar(clave, v)
    _CACHE[clave] = v
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return v


def _de_disco(clave: str) -> bool:
    """¿Estaba en disco? Si estaba, queda en la memoria del proceso."""
    from hoja import imagen_cache
    v = imagen_cache.leer(clave)
    if v is None:
        return False
    _CACHE[clave] = v
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return True


def candidatas(pzs, imgs, frac) -> list[bool]:
    """¿Puede la hoja de origen de cada pieza traer una red en imagen? Las imágenes de la compuesta (`imgs`, de
    `get_image_info`) cubren ≥ `frac` de lo que se ve de la pieza. Barato: sin esto, una compuesta de mapas con un
    logo o una leyenda en imagen copiaría la hoja entera solo para descubrir que no hay red."""
    cajas = [fitz.Rect(i["bbox"]) for i in imgs]
    out = []
    for pz in pzs:
        xs, ys = [q[0] for q in pz.poligono], [q[1] for q in pz.poligono]
        r = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
        area = r.get_area()
        cubre = sum((c & r).get_area() for c in cajas if c.intersects(r))
        out.append(area > 0 and cubre >= frac * area)
    return out


def ejes_de_piezas(page, pzs, calcular, usar=None, en_proceso=None) -> list[list[dict]]:
    """Por pieza, los trazos de su hoja de origen (`calcular(pagina_de_origen)`, memorizado por huella), en las
    coordenadas de la hoja de origen. La hoja de origen se arma en un documento en memoria con solo `/fullpage`.
    `usar` = [bool] por pieza (las que no, dan []). `en_proceso` = «módulo:función» que hace lo mismo que
    `calcular` (pedido 2026-11-19: una compuesta de 36 mapas leía las 36 imágenes de a una, ~20 min): las hojas de
    origen que faltan se reparten en varios procesos (`_repartir`); cada uno recibe su hoja como un PDF de una
    página. Mismo resultado; si no hay procesos, de a una como antes."""
    usar = [True] * len(pzs) if usar is None else list(usar)
    if not any(usar):
        return [[] for _ in pzs]
    tmp = fitz.open()
    try:
        from hoja.composite import vaciar_cache_mupdf
        vaciar_cache_mupdf()            # con la caché llena (ya se leyeron los dibujos) esta copia tardaba 24–46 s
        tmp.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
        recursos = _nombres(tmp, tmp[0].xref)
        hojas = []                                     # por pieza: (clave, número de página en `tmp`) o None
        for pz, u in zip(pzs, usar):
            xf = recursos.get(pz.nombre)
            hoja = _nombres(tmp, xf).get("fullpage") if xf is not None and u else None
            if hoja is None:
                hojas.append(None)
                continue
            clave = _huella(tmp, tmp.xref_stream(hoja) or b"", pz.caja, hoja)
            hojas.append((clave, _pagina_de_origen(tmp, hoja, pz.caja)))
        faltan = {}
        for h in hojas:
            if h is not None and h[0] not in _CACHE and h[0] not in faltan and not _de_disco(h[0]):
                faltan[h[0]] = h[1]
        if en_proceso and len(faltan) >= 2:
            _repartir(tmp, faltan, en_proceso)
        out = []
        for h in hojas:
            out.append([] if h is None else memo(h[0], lambda n=h[1]: calcular(tmp[n])))
        return out
    finally:
        tmp.close()


def _pagina_de_origen(tmp, hoja: int, caja) -> int:
    """Página nueva de `tmp` con solo la hoja de origen (`/fullpage`) y su caja; su número."""
    x0, y0, x1, y1 = caja
    p = tmp.new_page(width=x1 - x0, height=y1 - y0)
    tmp.xref_set_key(p.xref, "MediaBox", f"[{x0} {y0} {x1} {y1}]")
    tmp.xref_set_key(p.xref, "CropBox", f"[{x0} {y0} {x1} {y1}]")
    tmp.xref_set_key(p.xref, "Resources", f"<</XObject<</P {hoja} 0 R>>>>")
    xc = tmp.get_new_xref()
    tmp.update_object(xc, "<<>>")
    tmp.update_stream(xc, b"q /P Do Q")
    tmp.xref_set_key(p.xref, "Contents", f"{xc} 0 R")
    return p.number


# memoria de un proceso que lee la imagen de una hoja: pico medido 1.4–2.0 GB con `HoughCircles` en un hilo (2026-11-20, QS SD
# de Phoenix; con sus 12 hilos llegaba a 3.4–4.0 GB y 4 procesos llevaron el equipo a usar el disco como memoria)
MB_POR_HOJA = 2100
# leer la imagen de una hoja es cálculo puro (no relee el PDF de origen): hasta 6 a la vez si la RAM y los núcleos
# alcanzan (con 4: 36 mapas en 158 s; el tope general de `proceso_hijo.MAX_PARALELOS` es 4)
MAX_PROCESOS = 6


def de_bytes(datos: bytes, objetivo: str) -> list:
    """En un proceso del grupo: la hoja de origen (PDF de una página) por `objetivo` = «módulo:función»."""
    import importlib
    mod, fn = objetivo.split(":")
    with fitz.open(stream=datos, filetype="pdf") as d:
        return getattr(importlib.import_module(mod), fn)(d[0])


def _repartir(tmp, faltan: dict, objetivo: str) -> None:
    """Las hojas de origen de `faltan` {clave: página de `tmp`} en varios procesos; lo calculado entra a la memoria.
    Sin procesos (memoria, permisos) no hace nada: el llamador las calcula de a una."""
    from nucleo import avance
    from traduccion.i18n_core import t as _tr
    try:
        from ui.comun import proceso_hijo
        n_proc = proceso_hijo.paralelos(len(faltan), MB_POR_HOJA, maximo=MAX_PROCESOS)
    except Exception:
        return
    if n_proc < 2:
        return
    import concurrent.futures as cf
    import multiprocessing as mp
    datos = {}
    for clave, n in faltan.items():
        with fitz.open() as una:
            una.insert_pdf(tmp, from_page=n, to_page=n)
            datos[clave] = una.tobytes()
    texto = _tr("Leyendo la imagen de las hojas… {k} de {n}")
    hechas = 0
    try:
        with proceso_hijo.con_hijos():              # (el trabajador que lo pide es «daemon»)
            ex = cf.ProcessPoolExecutor(max_workers=n_proc, mp_context=mp.get_context("spawn"),
                                        initializer=proceso_hijo.morir_con_el_padre)
        with ex:
            with proceso_hijo.con_hijos():
                futuros = {ex.submit(de_bytes, b, objetivo): clave for clave, b in datos.items()}
            avance.avisar(texto.format(k=0, n=len(futuros)), 0, len(futuros))
            for fut in cf.as_completed(futuros):
                memo(futuros[fut], fut.result)
                hechas += 1
                avance.avisar(texto.format(k=hechas, n=len(futuros)), hechas, len(futuros))
    except Exception:
        return                                     # lo que no llegó se calcula de a una


# ── llevar a la compuesta ────────────────────────────────────────────────────────────────────

def _dentro(q, poli) -> bool:
    x, y = q
    dentro = False
    for (ax, ay), (bx, by) in zip(poli, poli[1:] + poli[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            dentro = not dentro
    return dentro


def _llevar_items(items, m):
    return [(it[0],) + tuple(fitz.Point(aplicar(m, q[0], q[1])) for q in it[1:]) for it in items]


def _caja(items):
    qs = [q for it in items for q in it[1:]]
    return fitz.Rect(min(q.x for q in qs), min(q.y for q in qs), max(q.x for q in qs), max(q.y for q in qs))


def llevar(trazos, pz: Pieza, seqno) -> list[dict]:
    """Los trazos de la hoja de origen llevados a la compuesta con la matriz de la pieza y recortados a su polígono.
    Línea: por el polígono (los cortes van en `cut_pts`, con `clip_polys` = el polígono); símbolo y relleno: si su
    centro cae dentro. El grosor se escala con la pieza."""
    from reconocimiento import recognition_geom as geom
    m = pz.matriz
    escala = abs(m[0] * m[3] - m[1] * m[2]) ** 0.5
    poli = [tuple(q) for q in pz.poligono]
    clave = tuple((float(x), float(y)) for x, y in poli)
    out = []
    for p in trazos:
        items = _llevar_items(p["items"], m)
        if not items:
            continue
        cerrado = bool(p.get("closePath")) or p.get("symbol") or p.get("imagen_relleno")
        if cerrado:
            c = _caja(items)
            if not _dentro(((c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2), poli):
                continue
            d = dict(p, items=items, rect=c, width=float(p["width"]) * escala)
            if seqno is not None:
                d["seqno"] = seqno
            out.append(d)
            continue
        cadena = [(items[0][1].x, items[0][1].y)] + [(it[-1].x, it[-1].y) for it in items]
        cortes: list = []
        for trozo in geom._clip_chain(cadena, poli, cortes):
            # cortes = las puntas del trozo creadas por el recorte o ya sobre su borde (como `geom.clip_path`)
            cortes_t = []
            for q in (trozo[0], trozo[-1]):
                corte = (any(abs(c[0] - q[0]) + abs(c[1] - q[1]) <= 1e-6 for c in cortes)
                         or geom._dist_to_polygon(q, poli) <= _TOL_BORDE)
                if corte and not any(abs(c[0] - q[0]) + abs(c[1] - q[1]) <= 1e-6 for c in cortes_t):
                    cortes_t.append(q)
            its = [("l", fitz.Point(a), fitz.Point(b)) for a, b in zip(trozo, trozo[1:])]
            d = dict(p, items=its, rect=_caja(its), width=float(p["width"]) * escala,
                     clip_polys=[clave], cut_pts=cortes_t)
            if seqno is not None:
                d["seqno"] = seqno
            out.append(d)
    return out


def seqno_de_piezas(page, pzs) -> list:
    """Por pieza, el `seqno` donde empieza su dibujo (`inicios_de_piezas`), emparejado por su recorte (el que más se
    superpone con el polígono de la pieza); None si no se encuentra."""
    from hoja import leyenda_mapa_lectura as LML
    inicios, cajas = LML.inicios_de_piezas(page), LML.recortes_de_piezas(page)
    out = []
    for pz in pzs:
        xs, ys = [q[0] for q in pz.poligono], [q[1] for q in pz.poligono]
        r = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
        mejor, area = None, 0.0
        for s, c in zip(inicios or (), cajas or ()):
            if c is None:
                continue
            a = (r & fitz.Rect(c)).get_area() if r.intersects(fitz.Rect(c)) else 0.0
            if a > area:
                mejor, area = s, a
        out.append(mejor)
    return out
