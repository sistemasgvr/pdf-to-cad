"""composicion_ficha.py — qué dice cada hoja del PDF para armar la composición sugerida.

Pedido del usuario 2026-10-14: al abrir un PDF vectorial, revisar TODAS sus hojas y
sugerir cómo se unen. La ficha de una hoja junta lo que el propio plano dice de su
lugar en el juego (sin tocar el reconocimiento):

  · Plano CAD: rótulos «MATCH LINE STA 551+75 SEE DWG UD-202» a los lados de la vista
    del plano (estación + hoja vecina) y el número de hoja del cajetín («UR-602A»; la
    serie «UR-#A» distingue juegos paralelos del mismo tramo, DU10/DU08).
  · Mapa por cuadrícula (Quarter Section de Phoenix): su número («17-10», «Q17-10») y el
    mapa índice 3×3 del cajetín con las vecinas y su dirección.
  · El recuadro de la VISTA (el clip del viewport en el PDF) y los trazos junto a sus
    bordes: con ellos `composicion_encaje` confirma la unión con el dibujo.

El texto solo PROPONE (los planos traen erratas: 359+00 contra 359+50); la geometría
decide. Todo en coordenadas de la hoja VISIBLE (con /Rotate aplicado), como el
compositor. PURO: solo fitz (y `texto_pdf` para el texto Type3 de los mapas SIG).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import fitz

from hoja import texto_pdf

Rect = Tuple[float, float, float, float]
# x0, y0, x1, y1, grosor, capa, color — hoja visible
Linea = Tuple[float, float, float, float, float, str, Tuple[float, ...]]

ESTACION_RX = re.compile(r"MATCH\s*-?\s*LINE.{0,40}?STA\.?\s*(\d+)\s*\+\s*(\d+(?:\.\d+)?)", re.I | re.S)
VER_RX = re.compile(r"SEE\s+(?:DWG|DRAWING|SHEET|SHT)\.?\s*(?:NO\.?\s*)?([A-Z]{1,4}-?\d{1,4}[A-Z]?)", re.I)
NUMERO_RX = re.compile(r"^[A-Z]{1,4}-?\d{1,4}[A-Z]?$")
CELDA_RX = re.compile(r"^Q?(\d{1,3})-(\d{1,3})$")

ROTULO_LADO_PT = 160.0      # un rótulo de match line queda a ≤ esto del lado de la vista (por fuera o dentro)
ROTULO_RANGO_PT = 40.0      # …y dentro de la extensión de ese lado (± esto)
VISTA_MIN_FRAC = 0.15       # una vista ocupa al menos esto de la hoja (no los detalles chicos)
VISTA_MAX_FRAC = 0.95       # …y no es la hoja entera
BANDA_CAD_PT = 110.0        # trazos que se guardan a cada lado de un borde de la vista (match line + franja)
BANDA_MAPA_FRAC = 0.35      # en un mapa, franja interior de cada borde (las hojas vecinas se solapan)
INDICE_MAX_FRAC = 0.7       # el mapa índice va en letra más chica que el número de la hoja
LINEA_MIN_PT = 2.0


@dataclass
class Rotulo:
    """Rótulo de match line: estación (pies) y hoja referida, en su lado de la vista."""
    estacion: float
    texto: str
    x: float
    y: float
    ver: str = ""               # «SEE DWG UD-202» → "UD-202"
    lado: str = ""              # left | right | top | bottom (de la vista)


@dataclass
class Ficha:
    doc: int
    hoja: int
    tam: Tuple[float, float]                       # hoja visible (pt)
    numero: str = ""                               # número de hoja del cajetín («UR-602A»)
    serie: str = ""                                # «UR-#A»
    rotulos: List[Rotulo] = field(default_factory=list)
    vista: Optional[Rect] = None                   # recuadro del plano (hoja visible)
    celda: Optional[Tuple[int, int]] = None        # (fila, columna) de la cuadrícula
    vecinas: Dict[Tuple[int, int], Tuple[int, int]] = field(default_factory=dict)  # celda → (dx, dy) en la hoja
    lineas: List[Linea] = field(default_factory=list)                              # trazos de los bordes
    titulo: str = ""                               # texto más grande del cajetín (para mostrar)

    @property
    def clave(self) -> Tuple[int, int]:
        return self.doc, self.hoja

    @property
    def tipo(self) -> str:
        """'estaciones' (plano CAD con match lines), 'cuadricula' (mapa) o ''."""
        if any(r.lado for r in self.rotulos) and self.vista is not None:
            return "estaciones"
        if self.celda is not None:
            return "cuadricula"
        return ""

    def lado(self, lado: str) -> List[Rotulo]:
        return [r for r in self.rotulos if r.lado == lado]

    def etiqueta(self) -> str:
        if self.celda is not None:
            return "%d-%d" % self.celda
        return self.numero or "%d" % (self.hoja + 1)


def serie_de(numero: str) -> str:
    """«UR-602A» → «UR-#A»: hojas de la misma serie solo cambian el número."""
    return re.sub(r"\d+", "#", numero.upper()) if numero else ""


def estacion_texto(pies: float) -> str:
    """55175.0 → «551+75»."""
    v = round(pies, 2)
    c, r = divmod(v, 100.0)
    rs = ("%05.2f" % r).rstrip("0").rstrip(".") if r % 1 else "%02d" % int(r)
    return "%d+%s" % (int(c), rs)


# ─────────────────────────── texto ───────────────────────────
@dataclass
class _Texto:
    texto: str
    x: float
    y: float
    alto: float


@dataclass
class _Bloque:
    texto: str
    lineas: List[Tuple[int, _Texto]]     # (posición en `texto` donde empieza la línea, línea)

    def donde(self, pos: int) -> _Texto:
        """La línea del bloque donde está el carácter `pos` (un bloque puede juntar dos
        rótulos de la misma altura: cada uno va con su propia posición)."""
        out = self.lineas[0][1]
        for ini, ln in self.lineas:
            if ini <= pos:
                out = ln
        return out


def _textos(page: fitz.Page) -> Tuple[List[_Texto], List[_Bloque]]:
    """(líneas, bloques) de texto en coords de la hoja VISIBLE. Las líneas traen el
    alto de letra (número de hoja, cuadrícula); los bloques juntan las líneas de un
    rótulo de varias líneas («MATCH LINE / STA 551+75 / SEE DWG UD-202»)."""
    m = page.rotation_matrix
    lineas: List[_Texto] = []
    bloques: List[_Bloque] = []
    try:
        d = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)   # sin imágenes: 50× más rápido en SIG
    except Exception:
        d = {"blocks": []}
    for b in d.get("blocks", ()):
        partes: List[Tuple[int, _Texto]] = []
        txt_b = ""
        for ln in b.get("lines", ()):
            spans = [s for s in ln.get("spans", ()) if s.get("text", "").strip()]
            if not spans:
                continue
            x0, y0, x1, y1 = ln["bbox"]
            p = fitz.Point((x0 + x1) / 2.0, (y0 + y1) / 2.0) * m
            for s in spans:                       # cada trozo con su posición (dos rótulos en una línea)
                sx0, sy0, sx1, sy1 = s["bbox"]
                q = fitz.Point((sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0) * m
                t = _Texto(" ".join(s["text"].split()), q.x, q.y, s.get("size", 0.0))
                if txt_b:
                    txt_b += " "
                partes.append((len(txt_b), t))
                txt_b += t.texto
            lineas.append(_Texto(" ".join(" ".join(s["text"].split()) for s in spans), p.x, p.y,
                                 max(s.get("size", 0.0) for s in spans)))
        if partes:
            bloques.append(_Bloque(txt_b, partes))
    # mapas SIG con fuente Type3 sin ToUnicode (Phoenix): el texto se lee por su forma
    try:
        if texto_pdf.necesita_decodificar(page):
            for c in texto_pdf.corridas(page):
                p = fitz.Point(*c.origen) * m
                lineas.append(_Texto(c.texto.strip(), p.x, p.y, float(c.tam)))
    except Exception:
        pass
    return lineas, bloques


def _rotulos(bloques: Sequence[_Bloque]) -> List[Rotulo]:
    out: List[Rotulo] = []
    for b in bloques:
        for mt in ESTACION_RX.finditer(b.texto):
            sta = int(mt.group(1)) * 100.0 + float(mt.group(2))
            # «SEE DWG …» del MISMO rótulo: entre esta match line y la siguiente
            sig = ESTACION_RX.search(b.texto, mt.end())
            cola = b.texto[mt.end():sig.start() if sig else len(b.texto)]
            antes = b.texto[max(0, mt.start() - 30):mt.start()]
            ver = VER_RX.search(cola) or VER_RX.search(antes)
            pos = b.donde(mt.start())
            out.append(Rotulo(sta, " ".join(mt.group(0).split()), pos.x, pos.y, ver.group(1).upper() if ver else ""))
    return out


def _numero(lineas: Sequence[_Texto], tam: Tuple[float, float]) -> str:
    """Número de hoja: el texto «XX-123A» más grande de la esquina inferior derecha."""
    W, H = tam
    cand = [t for t in lineas if NUMERO_RX.match(t.texto) and t.x > 0.5 * W and t.y > 0.6 * H]
    if not cand:
        return ""
    best = max(cand, key=lambda t: (round(t.alto, 1), t.x + t.y))
    return best.texto.upper()


def _celda(lineas: Sequence[_Texto]):
    """(celda propia, vecinas del mapa índice) o (None, {}). Solo cuenta un número
    con mapa índice (≥3 vecinas) o con el prefijo «Q» de Quarter Section: un «380-4»
    suelto de una portada o un «0-0» de una tabla no son una cuadrícula."""
    ids = []
    for t in lineas:
        mt = CELDA_RX.match(t.texto)
        if mt:
            ids.append((t, (int(mt.group(1)), int(mt.group(2)))))
    if not ids:
        return None, {}
    for big, propia in sorted(ids, key=lambda it: -it[0].alto):
        chicos = [(t, c) for t, c in ids if t.alto < INDICE_MAX_FRAC * big.alto]
        vecinas = _indice(chicos, propia, big.alto)
        if vecinas or big.texto.upper().startswith("Q"):
            return propia, vecinas
    return None, {}


def _indice(chicos, propia, alto_grande: float) -> Dict[Tuple[int, int], Tuple[int, int]]:
    """Mapa índice 3×3: la celda propia en el centro y sus vecinas alrededor →
    {celda vecina: (dx, dy)} en la hoja visible (x a la derecha, y hacia abajo)."""
    centro = [t for t, c in chicos if c == propia]
    for c0 in centro:
        cerca = [(t, c) for t, c in chicos
                 if abs(t.x - c0.x) <= 12 * alto_grande and abs(t.y - c0.y) <= 12 * alto_grande]
        dxs = sorted(abs(t.x - c0.x) for t, _ in cerca if abs(t.x - c0.x) > 0.5 * t.alto)
        dys = sorted(abs(t.y - c0.y) for t, _ in cerca if abs(t.y - c0.y) > 0.5 * t.alto)
        sx = dxs[0] if dxs else 0.0
        sy = dys[0] if dys else 0.0
        vecinas: Dict[Tuple[int, int], Tuple[int, int]] = {}
        for t, c in cerca:
            if c == propia:
                continue
            i = round((t.x - c0.x) / sx) if sx else 0
            j = round((t.y - c0.y) / sy) if sy else 0
            if (i, j) != (0, 0) and abs(i) <= 1 and abs(j) <= 1:
                vecinas[c] = (int(i), int(j))
        if len(vecinas) >= 3:
            return vecinas
    return {}


# ─────────────────────────── dibujo ───────────────────────────
def _recortes(paths, page: fitz.Page) -> List[Rect]:
    """Rectángulos de clip grandes (vistas candidatas) en la hoja visible."""
    m = page.rotation_matrix
    W, H = page.rect.width, page.rect.height
    clips: List[Rect] = []
    vistos = set()
    for p in paths:
        if p.get("type") != "clip":
            continue
        r = p.get("scissor")
        if not r:
            continue
        r = fitz.Rect(r) * m
        r.normalize()
        k = (round(r.x0), round(r.y0), round(r.x1), round(r.y1))
        if k in vistos:
            continue
        vistos.add(k)
        if VISTA_MIN_FRAC * W * H <= r.width * r.height <= VISTA_MAX_FRAC * W * H:
            clips.append((r.x0, r.y0, r.x1, r.y1))
    return clips


def _trazos(paths, page: fitz.Page, v: Optional[Rect], fuera: float, dentro: float) -> List[Linea]:
    """Segmentos rectos de la hoja visible. Con `v`, solo los que tienen los dos
    extremos a ≤ `fuera` del recuadro y a ≤ `dentro` de algún borde (franjas de
    los bordes: es lo único que mira la costura). Aritmética en línea, sin objetos
    fitz por trazo (una hoja CAD trae ~10⁵ segmentos)."""
    m = page.rotation_matrix
    ra, rb, rc, rd, re_, rf = m.a, m.b, m.c, m.d, m.e, m.f
    if v is not None:
        x0, y0, x1, y1 = v
        ox0, oy0, ox1, oy1 = x0 - fuera, y0 - fuera, x1 + fuera, y1 + fuera
        ix0, iy0, ix1, iy1 = x0 + dentro, y0 + dentro, x1 - dentro, y1 - dentro
    out: List[Linea] = []
    for p in paths:
        tp = p.get("type")
        if tp != "s" and tp != "fs":
            continue
        w = float(p.get("width") or 0.0)
        capa = p.get("layer") or ""
        col = None
        for it in p.get("items") or ():
            if it[0] != "l":
                continue
            a, b = it[1], it[2]
            ax, ay = a.x * ra + a.y * rc + re_, a.x * rb + a.y * rd + rf
            bx, by = b.x * ra + b.y * rc + re_, b.x * rb + b.y * rd + rf
            if abs(bx - ax) + abs(by - ay) < LINEA_MIN_PT:
                continue
            if v is not None:
                if not (ox0 <= ax <= ox1 and oy0 <= ay <= oy1 and ox0 <= bx <= ox1 and oy0 <= by <= oy1):
                    continue
                if (ix0 < ax < ix1 and iy0 < ay < iy1) or (ix0 < bx < ix1 and iy0 < by < iy1):
                    continue
            if col is None:
                col = tuple(round(c, 2) for c in (p.get("color") or ()))
            out.append((ax, ay, bx, by, w, capa, col))
    return out


def _lado_de(r: Rotulo, v: Rect) -> Tuple[str, float]:
    """Lado de la vista al que pertenece el rótulo y su distancia ('' si ninguno)."""
    x0, y0, x1, y1 = v
    best = ("", math.inf)
    for lado, d, dentro in (("left", abs(r.x - x0), y0 - ROTULO_RANGO_PT <= r.y <= y1 + ROTULO_RANGO_PT),
                            ("right", abs(r.x - x1), y0 - ROTULO_RANGO_PT <= r.y <= y1 + ROTULO_RANGO_PT),
                            ("top", abs(r.y - y0), x0 - ROTULO_RANGO_PT <= r.x <= x1 + ROTULO_RANGO_PT),
                            ("bottom", abs(r.y - y1), x0 - ROTULO_RANGO_PT <= r.x <= x1 + ROTULO_RANGO_PT)):
        if dentro and d <= ROTULO_LADO_PT and d < best[1]:
            best = (lado, d)
    return best


def _vista_cad(clips: Sequence[Rect], rotulos: Sequence[Rotulo]) -> Optional[Rect]:
    """La vista del plano = el recorte junto a cuyos lados están los rótulos (el que
    junta más; a igualdad, el más grande). Un perfil sin rótulos no compite."""
    best = None
    for v in clips:
        n = sum(1 for r in rotulos if _lado_de(r, v)[0])
        if not n:
            continue
        key = (n, (v[2] - v[0]) * (v[3] - v[1]))
        if best is None or key > best[0]:
            best = (key, v)
    return best and best[1]


def _vista_mapa(clips: Sequence[Rect]) -> Optional[Rect]:
    """En un mapa el marco del mapa es el recorte grande más INTERIOR (el exterior
    suele ser la zona imprimible de toda la hoja)."""
    if not clips:
        return None
    return min(clips, key=lambda v: (v[2] - v[0]) * (v[3] - v[1]))


def ficha(page: fitz.Page, doc_index: int = 0) -> Ficha:
    """Ficha de una hoja. El dibujo solo se lee si el texto dice que la hoja tiene
    match lines o número de cuadrícula (la mayoría de las demás no lo necesita)."""
    tam = (page.rect.width, page.rect.height)
    f = Ficha(doc_index, page.number, tam)
    lineas_t, bloques = _textos(page)
    f.rotulos = _rotulos(bloques)
    f.numero = _numero(lineas_t, tam)
    f.serie = serie_de(f.numero)
    f.celda, f.vecinas = _celda(lineas_t)
    if not f.rotulos and f.celda is None:
        return f
    paths = page.get_drawings(extended=True)
    clips = _recortes(paths, page)
    if f.rotulos:
        f.vista = _vista_cad(clips, f.rotulos)
        if f.vista is not None:
            for r in f.rotulos:
                r.lado = _lado_de(r, f.vista)[0]
            f.lineas = _trazos(paths, page, f.vista, BANDA_CAD_PT, BANDA_CAD_PT)
    if f.tipo != "estaciones" and f.celda is not None:
        f.vista = _vista_mapa(clips)
        if f.vista is not None:
            v = f.vista
            f.lineas = _trazos(paths, page, v, 2.0, BANDA_MAPA_FRAC * min(v[2] - v[0], v[3] - v[1]))
        else:
            f.lineas = _trazos(paths, page, None, 0.0, 0.0)  # sin marco (SD): la plantilla se quita después
    return f


def fichas(doc: fitz.Document, doc_index: int = 0, progreso=None, cancelado=None) -> List[Ficha]:
    """Ficha de TODAS las hojas. `progreso(i, n)` tras cada hoja; `cancelado()` corta."""
    out: List[Ficha] = []
    n = doc.page_count
    for i in range(n):
        if cancelado is not None and cancelado():
            break
        try:
            out.append(ficha(doc[i], doc_index))
        except Exception:
            out.append(Ficha(doc_index, i, (doc[i].rect.width, doc[i].rect.height)))
        if progreso is not None:
            progreso(i + 1, n)
    return out
