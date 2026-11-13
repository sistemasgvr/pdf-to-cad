"""Índice del TEXTO del plano (PURO: solo fitz): todo lo que dice la hoja de trabajo, para consultarlo.

Pedido del usuario 2026-11-13 («que se capture toda la información de cada plano: calles, todo lo que haya, y que la
IA sepa responder»): del plano solo quedaban como datos los rótulos que el reconocimiento une a una tubería; las calles,
lugares, números de servicio, notas… estaban en el PDF pero nadie los podía buscar (la IA solo miraba alrededor de una
utilidad que ya conocía). Aquí se lee TODO el texto de la hoja de trabajo una vez (en el proceso de trabajo, `trabajo`) y
queda en el proyecto (`Main.texto_plano`, .digproj) con, por línea: el texto, dónde está (px del lienzo), su tipo
(`categoria`) y la hoja de origen. A la IA NO va entero: la app busca en él lo que viene al caso de cada pregunta
(`ia.texto_plano`).

- Los glifos de las fuentes de SÍMBOLOS (ESRI, Wingdings…: válvulas, flechas) no son texto: se saltan.
- Mapas con fuente Type3 sin ToUnicode (Phoenix): el texto se lee por la forma (`texto_pdf`).
- Hoja compuesta: solo lo que queda dentro de alguna pieza (`piezas` = [(rect pt de la hoja, etiqueta)]); el resto
  de cada hoja de origen sigue en el PDF pero tapado por el recorte.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

import fitz

VERSION = 1
# fuentes de símbolos (no llevan letras: válvulas, flechas, marcas de mapa)
FUENTES_SIMBOLO = re.compile(r"ESRI|SYMBOL|WINGDING|WEBDING|DINGBAT|MARLETT|MIL2525|MAPINFO|CARTO", re.I)
MIN_ALNUM = 2

# tipo de cada línea de texto (el primero que encaja); las claves son DATO del proyecto (no se traducen)
CATEGORIAS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("celda", re.compile(r"^Q?\d{1,3}\s*-\s*\d{1,3}$")),
    ("estacion", re.compile(r"\bSTA\.?\s*\d+\s*\+\s*\d|\b\d{1,4}\+\d{2}(\.\d+)?\b")),
    ("tuberia", re.compile(r"\d+(\s*-?\s*\d/\d)?\s*(\"|IN\b|”)\s*[-\w]*\s*(PE|STL|STEEL|PVC|DIP|DI|CI|AC|ACP|RCP|VCP|HDPE|"
                           r"CU|COPPER|CMP|ST|MPE)\b|\b(PE|STL|MPE)\s*['’`]\s*\d\d\b|\b\d+(\.\d+)?\s*\"\s*(W|S|SS|G|SD|E|C)\b|"
                           # trozos de un rótulo en dos renglones: «1/2"», «30' 1/2"», «PE», «'04»
                           r"^(\d+(\.\d+)?\s*['’]\s*)?(\d+\s+)?\d+(/\d+)?\s*\"(\s*['’`]\d\d)?$|^(PE|STL|MPE|HDPE|PVC)$|"
                           r"^['’`]\d\d$")),
    ("calle", re.compile(r"\b(AVE|AVENUE|RD|ROAD|ST|STREET|BLVD|BOULEVARD|DR|DRIVE|LN|LANE|WAY|PKWY|PARKWAY|CIR|"
                         r"CIRCLE|CT|COURT|PL|PLACE|HWY|HIGHWAY|FREEWAY|FWY|LOOP|TER|TERRACE|TRL|TRAIL|ALY)\.?$|"
                         r"\b(AVE|AVENUE|RD|ROAD|BLVD|DRIVE|STREET|PARKWAY|FREEWAY)\b")),
    ("largo", re.compile(r"^\d+(\.\d+)?\s*['’]\s*(\d+(\.\d+)?\s*\"?)?$")),
    ("direccion", re.compile(r"^\d{3,5}(\s+[NSEW]\.?)?(\s+[A-Z0-9].*)?$")),
    ("servicio", re.compile(r"^(WR\s*|SVC\s*#?\s*|#\s*)?\d{6,}$|\bW\.?O\.?\s*#?\s*\d{4,}")),
    ("lugar", re.compile(r"\b(SCHOOL|PARK|CHURCH|CANAL|CENTER|CENTRE|PLAZA|HOSPITAL|MALL|STATION|LIBRARY|COLLEGE|"
                         r"UNIVERSITY|APARTMENTS|APTS|CEMETERY|STADIUM|AIRPORT|MARKET|STORE|R/W|ROW|EASEMENT|"
                         r"WAL-MART|WALMART|SUBDIVISION|TRACT|LOT)\b")),
    ("nota", re.compile(r"\b(NOTE|NOTES|SEE|PROTECT|ABANDON|ABAND|REMOVE|RELOCATE|INSTALL|CONNECT|EXIST|EXISTING|"
                        r"PROPOSED|PROP|VALVE|METER|RISER|REGULATOR|REG|CONV|SERV|SVC|TPSS|HYDRANT|MANHOLE|MH)\b")),
)


def categoria(texto: str) -> str:
    s = " ".join(str(texto or "").upper().split())
    for nombre, rx in CATEGORIAS:
        if rx.search(s):
            return nombre
    return "otro"


def _util(texto: str) -> bool:
    return sum(c.isalnum() for c in texto) >= MIN_ALNUM


def _trozos_pdf(page: fitz.Page):
    """[(texto, x0, y0, x1, y1, alto, (dx, dy))] por línea de MuPDF, en coords de la hoja SIN girar, sin los
    glifos de fuentes de símbolos."""
    out = []
    try:
        d = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
    except Exception:
        return out
    for b in d.get("blocks", ()):
        for ln in b.get("lines", ()):
            partes, cajas, alto = [], [], 0.0
            for s in ln.get("spans", ()):
                if FUENTES_SIMBOLO.search(s.get("font") or ""):
                    continue
                t = " ".join(str(s.get("text") or "").split())
                if not t:
                    continue
                partes.append(t)
                cajas.append(s["bbox"])
                alto = max(alto, float(s.get("size") or 0.0))
            texto = " ".join(partes).strip()
            if not texto:
                continue
            out.append((texto, min(c[0] for c in cajas), min(c[1] for c in cajas), max(c[2] for c in cajas),
                        max(c[3] for c in cajas), alto, tuple(round(v, 2) for v in ln.get("dir") or (1.0, 0.0))))
    return out


JUNTAR_HUECO = 0.9        # trozos de un mismo rótulo: separados a lo largo ≤ esto × el alto de letra
JUNTAR_LADO = 0.35        # …y desplazados de costado ≤ esto × el alto
RENGLON_PT = 2.0          # franjas del índice por renglón (solo para buscar candidatos: no cambia el resultado)


def _juntar(trozos):
    """ArcGIS escribe cada PALABRA como un texto aparte («1/2"» «PE» «'04», «92ND» «AVE»): los trozos en la misma
    línea base, con la misma dirección y tamaño, y separados menos de una letra son un solo rótulo."""
    import math
    grupos = {}
    for k, (t, x0, y0, x1, y1, h, dr) in enumerate(trozos):
        grupos.setdefault(dr, []).append(k)
    hechos = []
    for dr, ks in grupos.items():
        ux, uy = dr
        n = math.hypot(ux, uy) or 1.0
        ux, uy = ux / n, uy / n
        def a_lo_largo(k):
            t, x0, y0, x1, y1, h, _d = trozos[k]
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            return cx * ux + cy * uy, -cx * uy + cy * ux
        info = {k: a_lo_largo(k) for k in ks}
        orden = sorted(ks, key=lambda k: (round(info[k][1] / max(trozos[k][5], 1.0)), info[k][0]))
        # renglones (franjas de RENGLON_PT de costado) con los trozos por donde EMPIEZAN a lo largo: cada trozo
        # solo mira los de su renglón y a su alcance (antes, todos contra todos: 238 s con 55 mil trozos)
        import bisect
        pos = {k: n for n, k in enumerate(ks)}
        largo = {}
        renglones = {}
        for k in ks:
            tk = trozos[k]
            largo[k] = abs((tk[3] - tk[1]) * ux + (tk[4] - tk[2]) * uy)
            ini = info[k][0] - largo[k] / 2.0
            renglones.setdefault(int(info[k][1] // RENGLON_PT), []).append((ini, pos[k], k))
        for r in renglones.values():
            r.sort()
        claves = {r: [e[0] for e in lst] for r, lst in renglones.items()}
        usados = set()
        for k in orden:
            if k in usados:
                continue
            cadena = [k]
            usados.add(k)
            while True:
                u = cadena[-1]
                tu = trozos[u]
                h = max(tu[5], 1.0)
                fin_u = info[u][0] + largo[u] / 2.0
                lado_u = info[u][1]
                mejor = None
                r0 = int((lado_u - JUNTAR_LADO * h) // RENGLON_PT)
                r1 = int((lado_u + JUNTAR_LADO * h) // RENGLON_PT)
                for r in range(r0, r1 + 1):
                    lst = renglones.get(r)
                    if not lst:
                        continue
                    ks_r = claves[r]
                    a = bisect.bisect_left(ks_r, fin_u - 0.3 * h - 1e-9)
                    b = bisect.bisect_right(ks_r, fin_u + JUNTAR_HUECO * h + 1e-9)
                    for ini, pv, v in lst[a:b]:
                        if v in usados:
                            continue
                        tv = trozos[v]
                        if abs(tv[5] - tu[5]) > 0.2 * h or abs(info[v][1] - lado_u) > JUNTAR_LADO * h:
                            continue
                        hueco = ini - fin_u
                        if -0.3 * h <= hueco <= JUNTAR_HUECO * h and (mejor is None or (hueco, pv) < mejor[:2]):
                            mejor = (hueco, pv, v)
                if mejor is None:
                    break
                cadena.append(mejor[2])
                usados.add(mejor[2])
            hechos.append(cadena)
    out = []
    for cadena in hechos:
        ts = [trozos[k] for k in cadena]
        out.append((" ".join(t[0] for t in ts), min(t[1] for t in ts), min(t[2] for t in ts),
                    max(t[3] for t in ts), max(t[4] for t in ts), max(t[5] for t in ts)))
    return out


def _lineas_pdf(page: fitz.Page):
    """[(texto, x, y, alto)] de la hoja VISIBLE: rótulos ya juntados."""
    m = page.rotation_matrix
    out = []
    for texto, x0, y0, x1, y1, h in _juntar(_trozos_pdf(page)):
        if not _util(texto):
            continue
        p = fitz.Point((x0 + x1) / 2.0, (y0 + y1) / 2.0) * m
        out.append((texto, p.x, p.y, h))
    return out


def _lineas_type3(page: fitz.Page):
    try:
        from hoja import texto_pdf
        if not texto_pdf.necesita_decodificar(page):
            return []
        m = page.rotation_matrix
        out = []
        for c in texto_pdf.corridas(page):
            t = " ".join(str(c.texto).split())
            if t and _util(t):
                p = fitz.Point(*c.origen) * m
                out.append((t, p.x, p.y, float(c.tam)))
        return out
    except Exception:
        return []


def _pieza_de(x: float, y: float, piezas) -> Optional[int]:
    for k, (r, _et) in enumerate(piezas):
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return k
    return None


def leer(page: fitz.Page, zoom: float = 1.0, piezas: Optional[Sequence] = None, origen: str = "") -> dict:
    """El índice de la hoja de trabajo: {"version", "hojas": [etiqueta], "lineas": [[texto, x_px, y_px, tipo, hoja]]}.
    `zoom` = px del lienzo por pt; `piezas` = [((x0, y0, x1, y1) pt, etiqueta)] de una hoja compuesta (lo de fuera
    no se ve); sin piezas, todo con la etiqueta `origen`."""
    piezas = [(tuple(float(v) for v in r), str(et)) for r, et in (piezas or ())]
    hojas = [et for _r, et in piezas] if piezas else [origen]
    vistos = set()
    lineas: List[list] = []
    for texto, x, y, _alto in _lineas_pdf(page) + _lineas_type3(page):
        if piezas:
            k = _pieza_de(x, y, piezas)
            if k is None:
                continue                          # tapado por el recorte de su pieza
        else:
            k = 0
        clave = (texto, round(x), round(y))
        if clave in vistos:
            continue
        vistos.add(clave)
        lineas.append([texto, round(x * zoom, 1), round(y * zoom, 1), categoria(texto), k])
    return {"version": VERSION, "hojas": hojas, "lineas": lineas}


def trabajo(ruta_pdf: str, hoja: int, zoom: float = 1.0, piezas=None, origen: str = "", progreso=None) -> dict:
    """Lo que corre en el proceso de trabajo (`proceso.Tarea("hoja.indice_texto:trabajo")`)."""
    with fitz.open(ruta_pdf) as doc:
        return leer(doc[hoja], zoom, piezas, origen)


def resumen(indice: Optional[dict]) -> dict:
    """{tipo: cantidad} y las calles distintas (más nombradas primero)."""
    from collections import Counter
    cuenta, calles = Counter(), Counter()
    for t, _x, _y, cat, _k in (indice or {}).get("lineas") or ():
        cuenta[cat] += 1
        if cat == "calle":
            calles[nombre_calle(t)] += 1
    return {"tipos": dict(cuenta), "calles": [c for c, _n in calles.most_common()]}


def nombre_calle(texto: str) -> str:
    """«91ST  AVE.» → «91ST AVE» (para juntar las repeticiones de una misma calle)."""
    s = " ".join(str(texto).upper().replace('"', "").split())
    return re.sub(r"\.$", "", s)
