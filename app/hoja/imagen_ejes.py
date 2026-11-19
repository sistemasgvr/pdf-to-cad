"""Capas virtuales de los ejes de una red que viene como IMAGEN (PURO: fitz + numpy + cv2, sin Qt).

Los mapas «QS SD» de Phoenix traen la red en tiras de imagen indexada dentro de un PDF por lo demás
vectorial y SIN capas. `capas(page)` lee esas imágenes (`imagen_solo`), descubre sus colores UNA vez
por hoja (`imagen_paleta`), saca de cada color sus líneas, símbolos y rellenos (`imagen_trazos`) y los
devuelve como trazos con la forma de `page.get_drawings()` en capas virtuales:

  · línea   `PDF_STYLE:["img","line",[r,g,b]]`  — un trazo por eje: `type "s"`, `width` = grosor medido
    (pt), `items` = segmentos `("l", P, Q)`, `seqno` = `SEQNO` (−2: los nativos son ≥ 0 y los
    glifos de `simbolos_fuente`, −1), `imagen=True`;
  · símbolo `PDF_STYLE:["img","sym",[r,g,b],"<forma>"]` — un círculo virtual en su lugar (como
    `simbolos_fuente`), `symbol=True`;
  · relleno `PDF_STYLE:["img","fill",[r,g,b]]` — UN rectángulo por componente (para que la capa se
    liste), `imagen_relleno=True`.

Mismas coordenadas que `get_drawings` (las de la hoja SIN girar: `imagen_solo.pintar` ya trabaja en
ellas). Solo en hojas SIN capas cuyas imágenes cubren ≥ `COBERTURA_MIN` de la hoja y ninguna sola
≥ `ESCANEO_FRAC` (eso es un escaneo, como en `detect`); en cualquier otra hoja, [] sin decodificar
nada (logos, leyendas en imagen de Southwest Gas o del agua de Phoenix: <1–7 % de la hoja).

TESELAS (medido en Phoenix SD South h.4, 9 502 × 10 192 px a 4.17 px/pt): la hoja entera de una vez
pasaba de ~2.5 GB; por teselas de `LADO_PX` el pico es lo pintado (~0.3 GB) + una tesela. La paleta
se saca de TODAS las teselas juntas (nombres de capa estables en la hoja) y cada tesela se queda solo
con lo de su NÚCLEO (la tesela sin la mitad del solape con cada vecina): un símbolo o un rectángulo de
relleno es de la tesela cuyo núcleo tiene su centro; una línea se recorta al núcleo y las dos mitades
de la que cruza una costura se cosen de nuevo (`_coser`). El solape (`SOLAPE_PX`) deja la costura lejos
de los bordes de la tesela, donde el esqueleto, los puentes y las rejillas ya no se ven afectados.

Colores: se procesan los que cubren ≥ `PROCESAR_FRAC` de la tinta gráfica (y ≥ `PROCESAR_MIN_PX`): la
hoja h.4 trae ~60 tonos y la mayoría son restos de antialias de unos cientos de píxeles. Un color es
RELLENO si en la mayoría de su tinta `imagen_trazos` lo da por rayado; entonces no da líneas.
Lo usa `pdf_styles._drawings` (memorizado con `pdf_styles.memo` y en el documento, `_pdfcad_imagen_ejes`). La
copia de `imagen_solo` se suelta en cuanto se calculan los ejes. Compuesta: hojas de origen en procesos (`de_origen`).
"""

from __future__ import annotations

import collections
import colorsys
import json
import math

import cv2
import fitz
import numpy as np

from hoja import imagen_aros as IA
from hoja import imagen_compuesta as IC
from hoja import imagen_grosores as IG
from hoja import imagen_paleta as IP
from hoja import imagen_solo as IS
from hoja import imagen_trazos as IT
from hoja import pdf_styles
from nucleo import avance
from traduccion.i18n_core import t as _tr

SEQNO = -2                   # seqno de los trazos virtuales de imagen
COBERTURA_MIN = 0.15         # las imágenes deben cubrir al menos esto de la hoja
ESCANEO_FRAC = 0.60          # una sola imagen que cubre esto = escaneo (no se toca)
LADO_PX = 6144               # lado de una tesela (px)
SOLAPE_PX = 256              # solape entre teselas vecinas (px): la costura queda a 128 px de su borde
PROCESAR_FRAC = 0.0025       # colores con menos de esto de la tinta gráfica no se procesan …
PROCESAR_MIN_PX = 2000       # … ni con menos de estos píxeles
COSER_W = 1.5                # dos mitades se cosen si sus puntas en la costura distan ≤ esto × grosor …
COSER_MIN_PT = 0.5           # … (y al menos esto)
RADIO_MIN_PT = 0.5           # radio mínimo del círculo virtual de un símbolo
ACROMATICO_VECTORES_MIN = 500  # con tantos trazos vectoriales negros/grises, el negro/gris de la imagen no se procesa
ACROMATICO_TOL = 0.02        # acromático: max − min < esto (0–1), o max < esto (como `pdf_styles` «Negro»/«Gris»)
FORMA_TOL = 0.15             # símbolos del mismo tipo con ancho y alto a ±15 % = la misma capa
SIMBOLO_MIN_PIEZAS = 4       # una capa de símbolo con menos piezas va a «varios» de su color (Phoenix SD: 17–19
FORMA_VARIOS = "varios"      # de 23–28 capas tenían 1–3 piezas sueltas; la lista de capas no se llena de ruido)
_CACHE = "_pdfcad_imagen_ejes"
_TIPOS = ("line", "sym", "fill")
FINO = IG.FINO
partir_por_grosor = IG.partir_por_grosor
_INF = float("inf")


# ── nombres ──────────────────────────────────────────────────────────────────────────────────

def nombre(tipo: str, rgb, forma: str | None = None) -> str:
    """Nombre de la capa virtual de imagen (`tipo` «line» | «sym» | «fill»; `forma` solo en símbolos)."""
    k = ["img", tipo, [int(v) for v in rgb]] + ([forma] if forma is not None else [])
    return pdf_styles.PREFIX + json.dumps(k, separators=(",", ":"))


def _partes(name):
    if not (name or "").startswith(pdf_styles.PREFIX + '["img"'):
        return None
    try:
        k = json.loads(name[len(pdf_styles.PREFIX):])
    except (ValueError, TypeError):
        return None
    if not isinstance(k, list) or len(k) < 3 or k[1] not in _TIPOS or not isinstance(k[2], list):
        return None
    return k


def es_imagen(name) -> bool:
    return _partes(name) is not None


def tipo_imagen(name) -> str | None:
    k = _partes(name)
    return k[1] if k else None


def rgb_de(name) -> tuple[int, int, int] | None:
    k = _partes(name)
    return tuple(int(v) for v in k[2]) if k else None


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(v):02X}" for v in rgb)


def _nombre_color(rgb) -> str:
    r, g, b = (float(v) / 255.0 for v in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.15:
        return "Negro"
    if s < 0.15:
        return "Blanco" if v > 0.95 else "Gris"
    grados = h * 360.0
    for tope, nom in ((15, "Rojo"), (45, "Naranja"), (70, "Amarillo"), (165, "Verde"), (195, "Turquesa"),
                      (255, "Azul"), (290, "Morado"), (345, "Rosa"), (361, "Rojo")):
        if grados < tope:
            return nom
    return "Rojo"


def etiqueta(name) -> str:
    """Nombre legible: «Azul #004DA8 · imagen», «Símbolo #004DA8 (cuadro 4×4 pt) · imagen»,
    «Relleno #80A6D4 · imagen». (Lo usa `pdf_styles.style_label`.)"""
    k = _partes(name)
    if k is None:
        return ""
    rgb = k[2]
    if k[1] == "line":
        return f"{_nombre_color(rgb)} {_hex(rgb)}" + (f" ({k[3]})" if len(k) > 3 and k[3] else "") + " · imagen"
    if k[1] == "sym":
        forma = k[3] if len(k) > 3 else None
        if forma == FORMA_VARIOS:
            return f"Símbolo {_hex(rgb)} ({forma}) · imagen"
        return f"Símbolo {_hex(rgb)}" + (f" ({forma} pt)" if forma else "") + " · imagen"
    return f"Relleno {_hex(rgb)} · imagen"


# ── ¿hay red en imagen? ──────────────────────────────────────────────────────────────────────

def graficas(page, imgs=None) -> bool:
    """¿La hoja trae imágenes que pueden ser una red? Sin capas (lo mira `imagen_utiles`), cubren
    ≥ `COBERTURA_MIN` de la hoja y ninguna sola ≥ `ESCANEO_FRAC`. No decodifica nada."""
    imgs = IS.imagenes_utiles(page) if imgs is None else imgs
    if not imgs:
        return False
    hoja = IS.rect_sin_girar(page)
    area = hoja.get_area()
    if area <= 0:
        return False
    cajas = [fitz.Rect(i["bbox"]) & hoja for i in imgs]
    areas = [0.0 if c.is_empty else c.get_area() for c in cajas]
    return sum(areas) >= COBERTURA_MIN * area and max(areas) < ESCANEO_FRAC * area


# ── trazos virtuales ─────────────────────────────────────────────────────────────────────────

def _comun(layer, rgb, width, rect, items, **extra) -> dict:
    d = {"type": "s", "items": items, "closePath": False, "rect": rect,
         "color": tuple(float(v) / 255.0 for v in rgb), "fill": None, "width": float(width),
         "dashes": "[] 0", "even_odd": False, "stroke_opacity": 1.0, "fill_opacity": None,
         "lineCap": (0, 0, 0), "lineJoin": 0, "seqno": SEQNO, "level": 0, "imagen": True, "layer": layer}
    d.update(extra)
    return d


def _trazo_linea(rgb, pts, w, forma=None) -> dict:
    P = fitz.Point
    items = [("l", P(a), P(b)) for a, b in zip(pts, pts[1:])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return _comun(nombre("line", rgb, forma), rgb, w, fitz.Rect(min(xs), min(ys), max(xs), max(ys)), items)


def _trazo_simbolo(rgb, cx, cy, ancho, alto, forma) -> dict:
    from hoja import simbolos_fuente
    r = max(ancho / 2.0, alto / 2.0, RADIO_MIN_PT)
    return _comun(nombre("sym", rgb, forma), rgb, 0.1, fitz.Rect(cx - r, cy - r, cx + r, cy + r),
                  simbolos_fuente._circulo(cx, cy, r), closePath=True, symbol=True)


def _trazo_relleno(rgb, caja) -> dict:
    P = fitz.Point
    a, b, c, d = P(caja.x0, caja.y0), P(caja.x1, caja.y0), P(caja.x1, caja.y1), P(caja.x0, caja.y1)
    return _comun(nombre("fill", rgb), rgb, 0.1, fitz.Rect(caja),
                  [("l", a, b), ("l", b, c), ("l", c, d), ("l", d, a)], closePath=True, imagen_relleno=True)


# ── teselas: núcleo, recorte y costura ───────────────────────────────────────────────────────

def _nucleo(r: fitz.Rect, union: fitz.Rect, s_pt: float) -> tuple:
    """(x0, y0, x1, y1) del núcleo de la tesela `r`; ±inf en los lados que dan al borde."""
    x0 = -_INF if r.x0 <= union.x0 + 1e-9 else r.x0 + s_pt / 2
    y0 = -_INF if r.y0 <= union.y0 + 1e-9 else r.y0 + s_pt / 2
    x1 = _INF if r.x1 >= union.x1 - 1e-9 else r.x1 - s_pt / 2
    y1 = _INF if r.y1 >= union.y1 - 1e-9 else r.y1 - s_pt / 2
    return x0, y0, x1, y1


def _dentro(n, x, y) -> bool:
    return n[0] <= x < n[2] and n[1] <= y < n[3]


def _recortar(pts, n):
    """Trozos de la polilínea `pts` dentro del núcleo `n` (Liang–Barsky por tramo). Cada trozo =
    (puntos, ¿empieza en la costura?, ¿termina en la costura?)."""
    trozos, actual, ini_costura = [], [], False
    for a, b in zip(pts, pts[1:]):
        t0, t1 = 0.0, 1.0
        dx, dy = b[0] - a[0], b[1] - a[1]
        ok = True
        for p, q in ((-dx, a[0] - n[0]), (dx, n[2] - a[0]), (-dy, a[1] - n[1]), (dy, n[3] - a[1])):
            if p == 0:
                if q < 0:
                    ok = False
                    break
                continue
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
        if not ok or t0 > t1:
            if len(actual) >= 2:
                trozos.append((actual, ini_costura, True))
            actual = []
            continue
        pa = (a[0] + t0 * dx, a[1] + t0 * dy)
        pb = (a[0] + t1 * dx, a[1] + t1 * dy)
        if not actual:
            actual, ini_costura = [pa], t0 > 0.0
        actual.append(pb)
        if t1 < 1.0:
            if len(actual) >= 2:
                trozos.append((actual, ini_costura, True))
            actual = []
    if len(actual) >= 2:
        trozos.append((actual, ini_costura, False))
    return [t for t in trozos if math.dist(t[0][0], t[0][-1]) > 1e-6 or len(t[0]) > 2]


def _largo(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _coser(piezas):
    """Junta las mitades de las líneas que cruzan una costura. `piezas` = [[pts, w, (tesela de la
    punta inicial, de la final), (¿inicial en costura?, ¿final?)]]. Dos puntas en costura de
    teselas distintas se cosen si distan ≤ max(`COSER_MIN_PT`, `COSER_W` × grosor); la pareja más
    cercana primero, en orden (determinista)."""
    piezas = [list(p) for p in piezas]
    while True:
        puntas = [(i, lado) for i, p in enumerate(piezas) for lado in (0, 1) if p[3][lado]]
        mejor = None
        for x, (i, li) in enumerate(puntas):
            pi = piezas[i][0][-1 if li else 0]
            for j, lj in puntas[x + 1:]:
                if j == i or piezas[j][2][lj] == piezas[i][2][li]:
                    continue
                pj = piezas[j][0][-1 if lj else 0]
                d = math.dist(pi, pj)
                tope = max(COSER_MIN_PT, COSER_W * max(piezas[i][1], piezas[j][1]))
                if d <= tope and (mejor is None or d < mejor[0]):
                    mejor = (d, i, li, j, lj)
        if mejor is None:
            return piezas
        _d, i, li, j, lj = mejor
        a, b = piezas[i], piezas[j]
        # a orientada para TERMINAR en la costura; b para EMPEZAR en ella
        pa, ta, ca = (a[0], a[2][0], a[3][0]) if li else (a[0][::-1], a[2][1], a[3][1])
        pb, tb, cb = (b[0], b[2][1], b[3][1]) if not lj else (b[0][::-1], b[2][0], b[3][0])
        medio = ((pa[-1][0] + pb[0][0]) / 2, (pa[-1][1] + pb[0][1]) / 2)
        la, lb = _largo(a[0]), _largo(b[0])
        w = (a[1] * la + b[1] * lb) / (la + lb) if la + lb > 0 else a[1]
        nueva = [pa[:-1] + [medio] + pb[1:], w, (ta, tb), (ca, cb)]
        piezas = [p for k, p in enumerate(piezas) if k not in (i, j)]
        piezas.insert(min(i, j), nueva)


# ── la hoja ──────────────────────────────────────────────────────────────────────────────────

def _acromatico(c) -> bool:
    """¿Color (0–1) negro o gris?"""
    return max(c) - min(c) < ACROMATICO_TOL or max(c) < ACROMATICO_TOL


def vectores_acromaticos(nativos, tope: int = ACROMATICO_VECTORES_MIN) -> int:
    """Trazos vectoriales (con contorno) negros o grises de la hoja, contando hasta `tope`."""
    n = 0
    for p in nativos:
        c = p.get("color")
        if p.get("type") in ("clip", "group") or c is None or "s" not in (p.get("type") or ""):
            continue
        if len(c) >= 3 and _acromatico(c[:3]) or len(c) == 1:
            n += 1
            if n >= tope:
                break
    return n


def capas(page, nativos=None) -> list[dict]:
    """Trazos virtuales de los ejes, símbolos y rellenos de las imágenes de la hoja ([] si no hay
    red en imagen). `nativos` = lo que ya dio `get_drawings` (para no volver a leer la hoja; sin él,
    se lee solo si hace falta). Memorizado en el documento; nadie debe modificar la lista."""
    doc = page.parent
    cache = doc.__dict__.setdefault(_CACHE, {})
    clave = (page.number, page.rotation)
    if clave not in cache:
        try:
            cache[clave] = _capas_de(page, nativos)
        finally:
            IS.soltar(doc)                       # la copia filtrada ya no hace falta
    return cache[clave]


def _capas_de(page, nativos=None) -> list[dict]:
    imgs = IS.imagenes_utiles(page)
    if not imgs:
        return []
    # Hoja COMPUESTA: los ejes de cada hoja de ORIGEN llevados con su pieza (`imagen_compuesta`), nunca la imagen
    # de la compuesta (otra rejilla de teselas y otra paleta daban otros ejes).
    pzs = IC.piezas(page)
    if pzs:
        return _de_compuesta(page, pzs, imgs)
    if not graficas(page, imgs):
        return []
    # memorizado también por la HUELLA de la hoja (contenido + imágenes): la misma hoja de origen dentro de una
    # compuesta no se vuelve a leer
    return IC.memo(IC.huella_hoja(page), lambda: _capas_hoja(page, nativos, imgs))


def de_origen(pg) -> list[dict]:          # una hoja de ORIGEN de una compuesta (también en otro proceso)
    try:
        return _capas_hoja(pg, None, im) if graficas(pg, im := IS.imagenes_utiles(pg)) else []
    finally:
        IS.soltar(pg.parent)


def _de_compuesta(page, pzs, imgs) -> list[dict]:
    usar = IC.candidatas(pzs, imgs, 0.5 * COBERTURA_MIN)
    por_pieza = IC.ejes_de_piezas(page, pzs, de_origen, usar, en_proceso="hoja.imagen_ejes:de_origen")
    if not any(por_pieza):
        return []
    out: list[dict] = []
    for pz, trazos, seq in zip(pzs, por_pieza, IC.seqno_de_piezas(page, pzs)):
        out += IC.llevar(trazos, pz, seq)
    return out


def _capas_hoja(page, nativos, imgs) -> list[dict]:
    # En un PDF mixto el mapa base negro/gris es VECTOR: el negro de la imagen no aporta red y era ~80 %
    # del tiempo (Phoenix SD). Solo se procesa si la hoja casi no trae vectores acromáticos.
    if nativos is None:
        nativos = page.get_drawings()
    con_acromaticos = vectores_acromaticos(nativos) < ACROMATICO_VECTORES_MIN
    escala = IS.px_por_pt(imgs)
    if escala <= 0:
        return []
    texto = _tr("Leyendo la imagen de la hoja… {k} de {n}")
    teselas = list(IS.teselas(page, escala, LADO_PX, SOLAPE_PX))
    if not teselas:
        return []
    paleta = IP.paleta([img for _r, img in teselas], IP.indexada(page))
    total = sum(c.pixeles for c in paleta)
    usar = [c for c in paleta if c.pixeles >= max(PROCESAR_MIN_PX, PROCESAR_FRAC * total)
            and (con_acromaticos or not _acromatico([v / 255.0 for v in c.rgb]))]
    union = fitz.Rect(teselas[0][0])
    for r, _img in teselas[1:]:
        union |= r
    s_pt = SOLAPE_PX / escala
    datos = {c.rgb: {"lineas": [], "simbolos": [], "rellenos": [], "px_rel": 0, "px": 0} for c in usar}
    n_tes = len(teselas)
    for k in range(n_tes):
        avance.avisar(texto.format(k=k + 1, n=n_tes), k, n_tes)
        r, img = teselas[k]
        teselas[k] = (r, None)                    # lo pintado de esta tesela se suelta al terminarla
        nucleo = _nucleo(r, union, s_pt)
        with IP.misma_imagen(img):
            fams: dict = {}                       # familia de cada color en esta tesela (se calcula una vez)
            for c in usar:
                _tesela_color(img, c, paleta, escala, r, nucleo, k, datos[c.rgb], fams)
            del fams
        del img
    avance.avisar(texto.format(k=n_tes, n=n_tes), n_tes, n_tes)
    out: list[dict] = []
    for c in usar:
        out += _emitir(c.rgb, datos[c.rgb])
    return out


def _a_pt(r: fitz.Rect, escala: float, x: float, y: float) -> tuple[float, float]:
    """px de la tesela (centro del píxel = índice) → coordenadas de `get_drawings`."""
    return r.x0 + (x + 0.5) / escala, r.y0 + (y + 0.5) / escala


def _familia(img, color, paleta, fams) -> np.ndarray:
    if color.rgb not in fams:
        fams[color.rgb] = IP.familia(img, color, [o for o in paleta if o is not color])
    return fams[color.rgb]


def _tesela_color(img, color, paleta, escala, r, nucleo, k, d, fams=None) -> None:
    fams = {} if fams is None else fams
    m = IP.mascara(img, color)
    # Un TINTE de otro color (#80A6D4 = 50 % de #004DA8 con blanco) que es el borde de ese color (su familia
    # lo reclama: toca un tono más oscuro de él) no es tinta propia: el contorno de 1 px de la banda salía
    # como líneas finas de #80A6D4 pegadas a la tubería (Phoenix SD h.1).
    for o in paleta:
        if o is not color and IP._en_recta_al_blanco(np.array(color.rgb, float), np.array(o.rgb, float)):
            m &= ~_familia(img, o, paleta, fams)
    npx = int(m.sum())
    if npx == 0:
        return
    fam = _familia(img, color, paleta, fams)
    aros = IA.aros(img, m | fam, m, escala)               # buzones de aro fino con letra (`imagen_aros`)
    p = IT.trazos(m, escala, familia=fam)
    IA.sumar(p, aros, escala)
    d["px"] += npx
    if p.relleno:
        d["px_rel"] += npx
    for pts, w in zip(p.lineas, p.grosores):
        pt = [_a_pt(r, escala, x, y) for x, y in pts]
        for trozo, ci, cf in _recortar(pt, nucleo):
            d["lineas"].append([trozo, float(w), (k, k), (ci, cf)])
    for s in p.simbolos:
        cx, cy = _a_pt(r, escala, s.cx, s.cy)
        if _dentro(nucleo, cx, cy):
            d["simbolos"].append((cx, cy, s.ancho / escala, s.alto / escala, s.forma))
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(m.view(np.uint8), connectivity=8)
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < IT.RUIDO_PX:
            continue
        caja = fitz.Rect(r.x0 + x / escala, r.y0 + y / escala, r.x0 + (x + w) / escala, r.y0 + (y + h) / escala)
        if _dentro(nucleo, (caja.x0 + caja.x1) / 2, (caja.y0 + caja.y1) / 2):
            d["rellenos"].append(caja)


def _emitir(rgb, d) -> list[dict]:
    """Trazos de un color: relleno (si la mayoría de su tinta es rayado) o líneas, y sus símbolos."""
    out = []
    relleno = d["px"] > 0 and d["px_rel"] > 0.5 * d["px"]
    if relleno:
        out += [_trazo_relleno(rgb, caja) for caja in d["rellenos"]]
        return out                               # el rayado no da líneas ni símbolos
    gruesas, finas = IG.partir_por_grosor([(pts, w) for pts, w, *_ in _coser(d["lineas"])])
    if not finas:
        gruesas = IG.sin_trocitos_finos(gruesas)      # contornos de rejillas que no se reconocen: sin reconocer
    out += [_trazo_linea(rgb, pts, w) for pts, w in gruesas]
    out += [_trazo_linea(rgb, pts, w, FINO) for pts, w in finas]
    capa = formas_de_capa([(s[2], s[3], s[4]) for s in d["simbolos"]])
    for cx, cy, ancho, alto, forma in d["simbolos"]:
        out.append(_trazo_simbolo(rgb, cx, cy, ancho, alto, capa[forma]))
    return out


def _tipo_forma(forma: str) -> str:
    return (forma or "").split(" ", 1)[0]


def formas_de_capa(simbolos) -> dict:
    """{forma: forma de su capa} como `agrupar_formas`, pero las capas con menos de `SIMBOLO_MIN_PIEZAS` piezas
    van juntas a `FORMA_VARIOS`."""
    capa = agrupar_formas(simbolos)
    cuenta = collections.Counter(capa[f] for _a, _b, f in simbolos)
    return {f: (c if cuenta[c] >= SIMBOLO_MIN_PIEZAS else FORMA_VARIOS) for f, c in capa.items()}


def agrupar_formas(simbolos) -> dict:
    """{forma: forma de su capa}. `simbolos` = [(ancho_pt, alto_pt, forma)]. Las formas del mismo tipo
    (cuadro / círculo / otro) cuyo ancho y alto medios están a ±`FORMA_TOL` de los de la forma que
    encabeza un grupo van a ese grupo; encabeza la más frecuente (empate: por nombre). Determinista."""
    medidas: dict = {}
    for ancho, alto, forma in simbolos:
        m = medidas.setdefault(forma, [0, 0.0, 0.0])
        m[0] += 1
        m[1] += ancho
        m[2] += alto
    orden = sorted(medidas, key=lambda f: (-medidas[f][0], f))
    grupos = []                                  # (forma que encabeza, ancho, alto)
    capa = {}
    for f in orden:
        n, a, b = medidas[f]
        a, b = a / n, b / n
        for cab, ga, gb in grupos:
            if (_tipo_forma(cab) == _tipo_forma(f) and abs(a - ga) <= FORMA_TOL * max(a, ga)
                    and abs(b - gb) <= FORMA_TOL * max(b, gb)):
                capa[f] = cab
                break
        else:
            grupos.append((f, a, b))
            capa[f] = f
    return capa
