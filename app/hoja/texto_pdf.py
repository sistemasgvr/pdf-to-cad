"""texto_pdf.py — El TEXTO de una hoja aunque su fuente Type3 no traiga mapa de caracteres (PURO).

Pedido del usuario (2026-10-13, mapas «Quarter Section» de Phoenix, PDF sin capas):
interpretar la LEYENDA del plano. Sus textos van en una fuente Type3 SIN ToUnicode:
`get_text` da basura («Eater» por «Water», MuPDF toma el nombre del glifo como letra) y la
escala leída era cualquier cosa. Pero cada glifo Type3 es el CONTORNO de su letra: aquí se
dibuja cada glifo y se compara con las letras de Arial (regular, negrita, cursiva y negrita
cursiva) dibujadas igual → tabla glifo → letra. En los mapas de Phoenix los contornos son
EXACTAMENTE los de Arial (puntaje 1.0); un glifo que no se parece a ninguna letra
(≥`PUNTAJE_MIN`) es un SÍMBOLO de la fuente (válvula, hidrante, buzón).

  · `tabla(doc, page)`: {nombre de fuente en `get_texttrace`: {gid: letra | " " | None}} de
    las fuentes Type3 sin ToUnicode de la hoja (caché por documento y fuente).
  · `corridas(page)`: [Corrida] = texto seguido (misma línea base, letras contiguas) con su
    origen, dirección y tamaño; las letras de las demás fuentes salen como las da MuPDF.
  · `simbolos(page)`: [Simbolo] = glifos sin letra, juntando los SUPERPUESTOS (un símbolo de
    la leyenda son 2–3 glifos dibujados uno sobre otro: fondo blanco + figura), con su
    centro y radio de TINTA y su `clave` (glifos + color) para reconocerlo en todo el mapa.
  · `textos(page)`: el texto de la hoja, legible (lo usa la lectura de la escala).
Las coordenadas son las de `get_texttrace`/`get_drawings` (la hoja SIN girar). Nada se
modifica en el PDF.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import fitz
import numpy as np

EM = 48                      # px por em al comparar glifos
CELDA = 72                   # celda de cada glifo (px); el origen del glifo en (OX, OY)
OX, OY = 12, 54
COLS = 20
PUNTAJE_MIN = 0.9            # coseno mínimo con la letra de referencia (Phoenix: 1.0)
LETRAS = [chr(c) for c in range(33, 127)] + ["°", "±", "½", "¼", "¾", "Ø"]
# Arial de Windows (los mapas de Phoenix usan sus contornos); si no está, las Helvetica
# incluidas en MuPDF (mismas medidas, algunas letras distintas: puntaje algo menor).
_ARIAL = (("R", "arial.ttf", "helv"), ("B", "arialbd.ttf", "hebo"),
          ("I", "ariali.ttf", "heit"), ("BI", "arialbi.ttf", "hebi"))
JUNTAR_SIMBOLO = 0.45        # glifos-símbolo a ≤ esto × tamaño: el mismo símbolo


@dataclass
class Glifo:
    letra: Optional[str]      # None = símbolo; " " = glifo vacío (espacio)
    gid: int
    origen: Tuple[float, float]
    tam: float
    dir: Tuple[float, float]
    color: Tuple[float, ...]
    fuente: str
    tinta: Optional[Tuple[float, float, float, float]] = None   # caja de tinta (pt de la hoja)


@dataclass
class Corrida:
    texto: str
    origen: Tuple[float, float]
    dir: Tuple[float, float]
    tam: float
    glifos: List[Glifo] = field(default_factory=list)

    @property
    def fin(self) -> Tuple[float, float]:
        """Punto donde termina la corrida sobre su línea base (≈ avance de la última letra)."""
        o = self.glifos[-1].origen if self.glifos else self.origen
        return (o[0] + self.dir[0] * 0.6 * self.tam, o[1] + self.dir[1] * 0.6 * self.tam)


@dataclass
class Simbolo:
    clave: Tuple[Tuple[int, Tuple[float, ...]], ...]    # ((gid, color), …) ordenado
    centro: Tuple[float, float]
    radio: float
    caja: Tuple[float, float, float, float]
    fuente: str
    glifos: List[Glifo] = field(default_factory=list)


# ── referencias (Arial) ─────────────────────────────────────────────────────
_REF = None


def _celdas(page, n) -> np.ndarray:
    pix = page.get_pixmap(alpha=False, colorspace=fitz.csGRAY)
    a = 255 - np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    out = np.empty((n, CELDA, CELDA), np.float32)
    for i in range(n):
        r, c = divmod(i, COLS)
        out[i] = a[r * CELDA:(r + 1) * CELDA, c * CELDA:(c + 1) * CELDA] / 255.0
    return out


def _referencias():
    """(letras, matriz normalizada) de las letras de Arial dibujadas a `EM` px por em."""
    global _REF
    if _REF is not None:
        return _REF
    fdir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    items = [(k, ch) for k, _f, _b in _ARIAL for ch in LETRAS]
    filas = (len(items) + COLS - 1) // COLS
    doc = fitz.open()
    page = doc.new_page(width=COLS * CELDA, height=filas * CELDA)
    for k, archivo, interna in _ARIAL:
        ruta = os.path.join(fdir, archivo)
        try:
            page.insert_font(fontname="F" + k, fontfile=ruta) if os.path.isfile(ruta) else None
            nombre = "F" + k if os.path.isfile(ruta) else interna
        except Exception:
            nombre = interna
        for i, (kk, ch) in enumerate(items):
            if kk == k:
                r, c = divmod(i, COLS)
                page.insert_text((c * CELDA + OX, r * CELDA + OY), ch, fontsize=EM, fontname=nombre)
    R = _celdas(page, len(items)).reshape(len(items), -1)
    _REF = ([ch for _k, ch in items], R / (np.linalg.norm(R, axis=1, keepdims=True) + 1e-9))
    return _REF


# ── glifos Type3 ────────────────────────────────────────────────────────────
def _obj(doc, kv) -> str:
    kind, val = kv
    if kind == "xref":
        return doc.xref_object(int(val.split()[0]), compressed=True)
    return val if kind in ("dict", "array") else ""


def _numeros(texto: str) -> List[float]:
    return [float(v) for v in re.findall(r"-?\d*\.?\d+(?:[eE]-?\d+)?", texto or "")]


def _charprocs(doc, fx: int) -> Dict[int, bytes]:
    """{código: contenido del glifo (sin d0/d1)} de la fuente Type3 `fx`."""
    enc = _obj(doc, doc.xref_get_key(fx, "Encoding"))
    m = re.search(r"/Differences\s*\[(.*?)\]", enc, re.S)
    nombres, code = {}, 0
    for tok in re.findall(r"/[^\s/\[\]<>()]+|\d+", m.group(1) if m else ""):
        if tok.startswith("/"):
            nombres[code] = tok[1:]
            code += 1
        else:
            code = int(tok)
    procs = dict(re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", _obj(doc, doc.xref_get_key(fx, "CharProcs"))))
    out = {}
    for c, nombre in nombres.items():
        if nombre in procs:
            s = doc.xref_stream(int(procs[nombre])) or b""
            out[c] = re.sub(rb"^[^\n]*?\bd[01]\b[^\n]*\n?", b"", s, count=1)
    return out


def _sin_tounicode(doc, f) -> bool:
    return f[2] == "Type3" and doc.xref_get_key(f[0], "ToUnicode")[0] in ("null", "")


def _nombres(f) -> List[str]:
    """Nombres con que `get_texttrace` puede llamar a la fuente `f` de `get_fonts`."""
    xref, _ext, _tipo, base, nombre = f[:5]
    out = [f"Type3 ({xref} 0 R)"]
    for n in (base, nombre):
        if n:
            out += [n, n.split("+", 1)[-1]]
    return out


def _decodificar(doc, f):
    """({gid: letra|" "|None}, {gid: caja de tinta en em (x0, y0, x1, y1), y hacia ARRIBA})."""
    procs = _charprocs(doc, f[0])
    if not procs:
        return {}, {}
    fm = _numeros(_obj(doc, doc.xref_get_key(f[0], "FontMatrix"))) or [0.001, 0, 0, 0.001, 0, 0]
    a, b, c, d = (fm + [0, 0, 0, 0])[:4]
    codes = sorted(procs)
    filas = (len(codes) + COLS - 1) // COLS
    tmp = fitz.open()
    W, H = COLS * CELDA, filas * CELDA
    page = tmp.new_page(width=W, height=H)
    partes = []
    for i, code in enumerate(codes):
        r, col = divmod(i, COLS)
        # cada glifo recortado a SU celda: un símbolo grande (la flecha del «Valve #») se
        # metía en la celda de arriba y el «4» y el «6» de Phoenix no se leían (0.79/0.87)
        partes.append(b"q %d %d %d %d re W n %f %f %f %f %d %d cm 0 g 0 G " % (
                          col * CELDA, H - (r + 1) * CELDA, CELDA, CELDA,
                          EM * a, EM * b, EM * c, EM * d, col * CELDA + OX, H - (r * CELDA + OY))
                      + procs[code] + b"\nQ\n")
    x = tmp.get_new_xref()
    tmp.update_object(x, "<<>>")
    tmp.update_stream(x, b"".join(partes))
    tmp.xref_set_key(page.xref, "Contents", f"{x} 0 R")
    G = _celdas(page, len(codes))
    letras, Rn = _referencias()
    Gf = G.reshape(len(codes), -1)
    norma = np.linalg.norm(Gf, axis=1)
    S = (Gf / (norma[:, None] + 1e-9)) @ Rn.T
    mejor = S.argmax(axis=1)
    tabla, tinta = {}, {}
    for i, code in enumerate(codes):
        if norma[i] < 1e-6:
            tabla[code] = " "
            continue
        tabla[code] = letras[mejor[i]] if S[i, mejor[i]] >= PUNTAJE_MIN else None
        ys, xs = np.nonzero(G[i] > 0.15)
        if len(xs):
            tinta[code] = ((xs.min() - OX) / EM, (OY - ys.max() - 1) / EM,
                           (xs.max() + 1 - OX) / EM, (OY - ys.min()) / EM)
    return tabla, tinta


def tabla(doc, page) -> Dict[str, Tuple[dict, dict]]:
    """{nombre de fuente: (letras, cajas de tinta)} de las fuentes Type3 sin ToUnicode."""
    cache = doc.__dict__.setdefault("_pdfcad_type3", {})
    out = {}
    try:
        fuentes = page.get_fonts(full=True)
    except Exception:
        return out
    for f in fuentes:
        if not _sin_tounicode(doc, f):
            continue
        if f[0] not in cache:
            try:
                cache[f[0]] = _decodificar(doc, f)
            except Exception:
                cache[f[0]] = ({}, {})
        for n in _nombres(f):
            out.setdefault(n, cache[f[0]])
    return out


def necesita_decodificar(page) -> bool:
    """¿La hoja tiene texto en una fuente Type3 sin mapa de caracteres?"""
    try:
        return any(_sin_tounicode(page.parent, f) for f in page.get_fonts(full=True))
    except Exception:
        return False


# ── texto y símbolos de la hoja ─────────────────────────────────────────────
def _arriba(d):
    """Dirección «hacia arriba» del glifo en la hoja (y hacia abajo)."""
    return (d[1], -d[0])


def _caja_tinta(o, d, tam, caja_em):
    if caja_em is None:
        return None
    up = _arriba(d)
    pts = [(o[0] + (x * d[0] + y * up[0]) * tam, o[1] + (x * d[1] + y * up[1]) * tam)
           for x in (caja_em[0], caja_em[2]) for y in (caja_em[1], caja_em[3])]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def glifos(page) -> List[Glifo]:
    """Todos los glifos de la hoja con su letra (decodificada si hace falta)."""
    cache = page.parent.__dict__.setdefault("_pdfcad_glifos", {})
    if page.number in cache:
        return cache[page.number]
    tablas = tabla(page.parent, page)
    out: List[Glifo] = []
    try:
        traza = page.get_texttrace()
    except Exception:
        traza = []
    for s in traza:
        d = tuple(s.get("dir") or (1.0, 0.0))
        tam = float(s.get("size") or 0.0)
        color = tuple(round(float(v), 2) for v in (s.get("color") or ()))
        t = tablas.get(s.get("font") or "")
        for ucs, gid, o, _bb in s.get("chars") or ():
            if t is not None:
                letra = t[0].get(gid)
                caja = _caja_tinta(o, d, tam, t[1].get(gid))
            else:
                letra = None if ucs in (0xFFFD, 0) else chr(ucs)
                caja = None
            out.append(Glifo(letra, gid, (float(o[0]), float(o[1])), tam, d, color, s.get("font") or "", caja))
    cache[page.number] = out
    return out


def corridas(page) -> List[Corrida]:
    """Texto seguido: letras de la misma línea base, una tras otra (ver el docstring)."""
    out: List[Corrida] = []
    cur: Optional[Corrida] = None
    last = None
    for g in glifos(page):
        if g.letra is None:
            if cur is not None:
                out.append(cur)
            cur, last = None, None
            continue
        if cur is not None:
            dx, dy = g.origen[0] - last[0], g.origen[1] - last[1]
            along = dx * cur.dir[0] + dy * cur.dir[1]
            across = abs(-dx * cur.dir[1] + dy * cur.dir[0])
            if (g.dir != cur.dir or abs(g.tam - cur.tam) > 0.05 * cur.tam or across > 0.3 * cur.tam
                    or along < -0.2 * cur.tam or along > 1.6 * cur.tam):
                out.append(cur)
                cur = None
        if cur is None:
            cur = Corrida("", g.origen, g.dir, g.tam)
        cur.texto += g.letra
        cur.glifos.append(g)
        last = g.origen
    if cur is not None:
        out.append(cur)
    for c in out:
        c.texto = c.texto.rstrip()
    return [c for c in out if c.texto.strip()]


def simbolos(page) -> List[Simbolo]:
    """Glifos sin letra agrupados (los superpuestos son un mismo símbolo)."""
    cache = page.parent.__dict__.setdefault("_pdfcad_simbolos", {})
    if page.number in cache:
        return cache[page.number]
    gs = [g for g in glifos(page) if g.letra is None and g.tinta is not None]
    padre = list(range(len(gs)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i
    centros = [((g.tinta[0] + g.tinta[2]) / 2.0, (g.tinta[1] + g.tinta[3]) / 2.0) for g in gs]
    celdas: Dict[Tuple[int, int], List[int]] = {}
    for i, (x, y) in enumerate(centros):
        celdas.setdefault((int(x // 4), int(y // 4)), []).append(i)
    for i, (x, y) in enumerate(centros):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in celdas.get((int(x // 4) + dx, int(y // 4) + dy), ()):
                    if j > i and np.hypot(x - centros[j][0], y - centros[j][1]) <= \
                            JUNTAR_SIMBOLO * max(gs[i].tam, gs[j].tam):
                        padre[raiz(j)] = raiz(i)
    grupos: Dict[int, List[int]] = {}
    for i in range(len(gs)):
        grupos.setdefault(raiz(i), []).append(i)
    out = []
    for idx in grupos.values():
        miembros = [gs[i] for i in idx]
        x0 = min(g.tinta[0] for g in miembros); y0 = min(g.tinta[1] for g in miembros)
        x1 = max(g.tinta[2] for g in miembros); y1 = max(g.tinta[3] for g in miembros)
        clave = tuple(sorted({(g.gid, g.color) for g in miembros}))
        out.append(Simbolo(clave, ((x0 + x1) / 2.0, (y0 + y1) / 2.0), max(x1 - x0, y1 - y0) / 2.0,
                           (x0, y0, x1, y1), miembros[0].fuente, miembros))
    cache[page.number] = out
    return out


def textos(page) -> List[str]:
    """El texto legible de la hoja (una cadena por corrida)."""
    return [c.texto for c in corridas(page)]
