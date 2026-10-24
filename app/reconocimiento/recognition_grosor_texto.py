"""recognition_grosor_texto.py — los RÓTULOS de diámetro de un plano CAD (PURO; ver
`recognition_grosor`).

Cada línea de texto con UN diámetro de tubería («EX. 84" RCP SD», «18" RCP, LACFCD», «PROP 8"
WATER») es un `Rotulo`, con la utilidad que nombran sus palabras (SD, WATER, SSWR…) o, si no, su
material (RCP, VCP…). No lo son las escalas «1" = 20'», los rumbos «N89°47'33"W», las cotas de
armado «#4 @ 6"» ni «12" MIN». Las líneas se juntan en BLOQUES como un MText de AutoCAD: una bajo
otra y alineadas a la izquierda, a la derecha o al centro; la guía sale de la raya o del borde
de su bloque (`recognition_grosor_guias`).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

Pt = Tuple[float, float]

# «84"», «18" RCP», «8" WL», «EX.18" RCP» (el punto de la abreviatura pegado al número: 46 rótulos
# de DU06 se perdían); no «1" = 20'», ni rumbos «00' 56.07"», ni «#4 @ 6"», ni la parte decimal
# de otro número
RX_DIAM = re.compile(r"""(?<![\d#@'’])(?<!\d\.)(\d{1,3}(?:\.\d+)?)\s*(?:"|”|'')(?!\s*=)""")
RX_ESTACION = re.compile(r"\b\d{1,4}\+\d{2}(?:\.\d+)?\b")      # «557+72.74»: rótulo de un PUNTO
# … y de una UNIÓN: «JOIN (TO) EX. 84"», «CB LAT 208», «553+07.46 "VN"= EX.CB LAT 204, 1+00.00»
# el nombre de un lateral / sumidero («LAT CB-208», «CB-217, LACFCD», «CB # 208» en el perfil)
RX_NOMBRE = re.compile(r"\bCB\s*(?:#\s*)?-?\s*(\d+(?:\.\d+)?)\b")


def nombres_de(texto: str) -> List[str]:
    return ["CB-" + m.group(1) for m in RX_NOMBRE.finditer(texto.upper())]


RX_UNION = re.compile(r"\bJOIN\b|\bLAT\b|\bLATERAL\b|=")
RX_RUMBO = re.compile(r"""\d+\s*['’]\s*\d{1,2}(?:\.\d+)?\s*(?:"|”)""")
MATERIALES = ("RCP", "CMP", "PVC", "VCP", "DIP", "CIP", "ACP", "HDPE", "RCB", "CI", "DI", "STL", "CU", "PE", "CSP")
# «2-6"P CONDUIT», «2-4'' COMM», «2-24" DBL RCP CULVERT»: N conductos/tubos de ese diámetro en una
# línea (DU08: bancos de ductos de DWPPS y de telecom). El diámetro es el de cada uno; si el rótulo
# mezcla tamaños («12-4", 2-5", 1-3"», «6-6" & / 1-4"P CONDUIT») no hay un diámetro de la línea
RX_VARIOS = re.compile(r"(\d+)\s*-\s*$")
# fracciones de pulgada: «1-1/2" WS», «3/4" GS», «1/2" P» (acometidas de DU08; antes salían 2" y 4")
RX_FRACCION = re.compile(r"""(?<![\d#@'’./])(?:(\d+)\s*-\s*)?(\d{1,2})\s*/\s*(\d{1,2})\s*(?:"|”|'')(?!\s*=)""")
DIAM_MIN_IN = 0.5
# (también el DUEÑO de la red cuando es de una sola utilidad: SCG = SoCal Gas, DWPWS = agua de
# LADWP, DWPPS / SCE = energía, FRONTIER (GTE) = telecom; «PROP 2" SCG» no decía «GAS»; «6" HC» =
# conexión domiciliaria de alcantarillado, DU08)
UTIL_PALABRAS = {
    "DRENAJE": ("SD", "STORM", "DRAIN", "LACFCD", "CB"),
    "ALCANTARILLADO": ("SS", "SSWR", "SWR", "SEWER", "SAN", "SANITARY", "HC"),
    "AGUA": ("W", "WL", "WATER", "FH", "DWPWS", "WS"),
    "GAS": ("G", "GAS", "SCG", "GS"),
    "ELECTRICO": ("E", "ELEC", "ELECTRIC", "POWER", "DWPPS", "SCE"),
    "TELECOM": ("T", "TEL", "TELE", "COMM", "FO", "CATV", "FRONTIER", "FTR", "GTE", "ATT"),
}
# el CÓDIGO del cruce al final del rótulo (planos de reubicación de utilidades: DU08, DU10, LABOE)
# dice la utilidad aunque el texto no la nombre: «8" C.I., 20'W CL, W139C», «6-5" 2-4", 19'W CL,
# E168», «4" PE, 27'N CL, G053», «1-4" PVC, 49'W CL, C087». En los 4 PDF de prueba cada prefijo
# coincide con la utilidad escrita en todos los rótulos que la nombran (E 62, W 31, SS 111, G 37,
# C 9, SD 48, GS 16, SSL 8)
CODIGO_UTIL = {"E": "ELECTRICO", "W": "AGUA", "WS": "AGUA", "G": "GAS", "GS": "GAS", "C": "TELECOM",
               "SS": "ALCANTARILLADO", "SSL": "ALCANTARILLADO", "S": "ALCANTARILLADO", "SD": "DRENAJE"}
RX_CODIGO = re.compile(r"\b(SSL|SS|SD|GS|WS|E|W|G|C|S)\d{2,5}[A-Z]?\W*$")
# sin la utilidad escrita, el MATERIAL dice dónde puede ir («JOIN EX. 18" RCP»)
MATERIAL_UTIL = {
    "RCP": ("DRENAJE", "ALCANTARILLADO"), "RCB": ("DRENAJE",), "CMP": ("DRENAJE",), "CSP": ("DRENAJE",),
    "VCP": ("ALCANTARILLADO",), "PVC": ("AGUA", "ALCANTARILLADO", "DRENAJE", "ELECTRICO", "TELECOM"),
    "DIP": ("AGUA", "ALCANTARILLADO"), "CIP": ("AGUA", "ALCANTARILLADO"), "ACP": ("AGUA", "ALCANTARILLADO"),
    "CI": ("AGUA", "ALCANTARILLADO"), "DI": ("AGUA", "ALCANTARILLADO"), "HDPE": ("AGUA", "ALCANTARILLADO", "DRENAJE", "GAS", "TELECOM"),
    "PE": ("GAS", "AGUA"), "STL": ("GAS", "AGUA"), "CU": ("AGUA", "GAS"),
}
NO_TUBERIA = ("MIN", "MAX", "CLR", "CLEAR", "COVER", "THICK", "BOTH", "WAYS", "O.C.", "OC")
BLOQUE_SALTO = 0.9            # × tamaño de letra entre líneas de un mismo bloque
BLOQUE_ALINEADO = 0.5         # × tamaño de letra: líneas del mismo MText alineadas
BLOQUE_PASO_TOL = 0.03        # × tamaño de letra: el paso entre líneas de un MText es constante
                              # (4 PDF de prueba: 90 % varía ≤1 % del tamaño; los rótulos apilados, 7–70 %)
BLOQUE_HUECO_SOLO = 0.3       # × tamaño de letra: hueco máximo entre las dos primeras líneas
BLOQUE_PEGADAS = 0.05         # × tamaño de letra: líneas pegadas (sus cajas se tocan): mismo MText;
                              # si se SOLAPAN (paso menor que el alto) son rótulos distintos (DU08 h.25)


@dataclass
class Rotulo:
    """Una línea de texto con un diámetro."""
    texto: str
    pulg: float
    bbox: Tuple[float, float, float, float]   # en px (los de la vista)
    tam: float                                 # tamaño de letra en px
    utilidad: str = ""                         # por sus palabras; "" = no lo dice
    material: str = ""
    bloque: int = -1                           # índice del bloque de texto
    otros: int = 0                             # otros diámetros en el mismo bloque
    estacion: bool = False                     # sus líneas dan una estación: marca un PUNTO
    union: bool = False                        # … donde algo se une a la tubería que nombra (JOIN, LAT, «=»)
    varios: int = 1                            # «2-4"»: cuántos conductos/tubos de ese diámetro
    nombres: Tuple[str, ...] = ()              # «CB-208» de su bloque («LAT CB-208 / 18" RCP»): el lateral del perfil


def _palabras(texto: str) -> List[str]:
    return re.findall(r"[A-Z]+(?:\.[A-Z]+\.?)?", texto.upper())


def utilidad_de(texto: str) -> str:
    pal = _palabras(texto.upper().replace("AT&T", "ATT"))
    for u, toks in UTIL_PALABRAS.items():
        if any(t in pal for t in toks if len(t) > 1):
            return u
    m = RX_CODIGO.search(texto.upper().strip())
    if m:
        return CODIGO_UTIL[m.group(1)]
    # una letra sola («8" W», «4" G») solo justo después del diámetro
    m = re.search(r"""(?:"|”)\s*([A-Z]{1,2})\b""", texto.upper())
    if m:
        for u, toks in UTIL_PALABRAS.items():
            if m.group(1) in toks:
                return u
    return ""


def material_de(texto: str) -> str:
    pal = [w.replace(".", "") for w in _palabras(texto)]           # «C.I.», «D.I.» (DU08)
    return next((m for m in MATERIALES if m in pal), "")


def _no_tuberia(limpio: str, fin: int) -> bool:
    resto = limpio[fin:fin + 12].upper()
    return any(re.match(r"\s*" + re.escape(w) + r"\b", resto) for w in NO_TUBERIA)


def lecturas(texto: str) -> List[Tuple[float, int]]:
    """[(diámetro en pulgadas, cuántos)] de una línea de texto, en su orden: «2-6"» = (6, 2),
    «1-1/2"» = (1.5, 1). Sin rumbos, escalas, estaciones ni cotas de armado."""
    # sin rumbos ni estaciones: en «552+56.35 "VN"» las comillas del alineamiento siguen al número
    limpio = RX_ESTACION.sub(" ", RX_RUMBO.sub(" ", texto))
    out, tapado = [], []
    for m in RX_FRACCION.finditer(limpio):
        num, den = int(m.group(2)), int(m.group(3))
        tapado.append((m.start(), m.end()))
        if 0 < num < den and not _no_tuberia(limpio, m.end()):
            v = (int(m.group(1)) if m.group(1) else 0) + num / den
            if DIAM_MIN_IN <= v <= 200.0:
                out.append((m.start(), v, 1))
    for m in RX_DIAM.finditer(limpio):
        if any(a <= m.start() < b for a, b in tapado) or _no_tuberia(limpio, m.end()):
            continue
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        varios = RX_VARIOS.search(limpio[:m.start()])
        if DIAM_MIN_IN <= v <= 200.0:
            out.append((m.start(), v, int(varios.group(1)) if varios else 1))
    return [(v, n) for _p, v, n in sorted(out)]


def diametros_de(texto: str) -> List[float]:
    """Diámetros de tubería de una línea de texto (ver `lecturas`)."""
    return [v for v, _n in lecturas(texto)]


def es_de(r: Rotulo, utilidad: str) -> bool:
    """¿Puede este rótulo ser de esa utilidad? Por sus palabras o, si no, por su material."""
    if r.utilidad:
        return r.utilidad == utilidad
    return utilidad in MATERIAL_UTIL.get(r.material, ())


def _tramos(ln) -> List[list]:
    """Los spans de una línea de MuPDF agrupados por su línea base: MuPDF junta dos rótulos
    vecinos a distinta altura en una línea («EX. 8" SEWER EX. 10" GAS», bases a 7 pt, LABOE
    h.26). Solo en líneas horizontales (en las verticales la base avanza con el texto)."""
    spans = ln.get("spans") or ()
    d = ln.get("dir", (1.0, 0.0))
    if abs(d[1]) >= 0.05 or len(spans) < 2:
        return [list(spans)]
    grupos: List[list] = []
    for s in spans:
        y = s.get("origin", (0.0, 0.0))[1]
        if grupos and abs(y - grupos[-1][0].get("origin", (0.0, 0.0))[1]) <= 0.3 * max(s.get("size", 1.0), 1.0):
            grupos[-1].append(s)
        else:
            grupos.append([s])
    return grupos


def _lineas_pt(page) -> List[Tuple[str, Tuple, float, Tuple[float, float]]]:
    out = []
    for b in page.get_text("dict").get("blocks", ()):
        for ln in b.get("lines", ()):
            grupos = _tramos(ln)
            for spans in grupos:
                t = "".join(s.get("text", "") for s in spans).strip()
                if not t:
                    continue
                bb = tuple(ln["bbox"]) if len(grupos) == 1 else (
                    min(s["bbox"][0] for s in spans), min(s["bbox"][1] for s in spans),
                    max(s["bbox"][2] for s in spans), max(s["bbox"][3] for s in spans))
                out.append((t, bb, max(s.get("size", 0.0) for s in spans), tuple(ln.get("dir", (1.0, 0.0)))))
    return out


def lineas_texto(page, px: Callable[[Pt], Pt], zoom: float) -> List[Tuple[str, Tuple, float, Pt]]:
    """[(texto, bbox px, tamaño px, dirección)] de cada línea de texto de la hoja (una lectura por
    hoja dentro de `pdf_styles.lectura_unica`)."""
    from hoja import pdf_styles
    out = []
    q0 = px((0.0, 0.0))
    for t, (x0, y0, x1, y1), size, d in pdf_styles.memo(page, "grosor_texto", lambda: _lineas_pt(page)):
        cs = [px((x0, y0)), px((x1, y0)), px((x1, y1)), px((x0, y1))]
        bb = (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))
        q1 = px(d)
        L = math.hypot(q1[0] - q0[0], q1[1] - q0[1]) or 1.0
        out.append((t, bb, size * zoom, ((q1[0] - q0[0]) / L, (q1[1] - q0[1]) / L)))
    return out


class Cajas(dict):
    """{bloque: (x0, y0, x1, y1, tamaño)}; en `lineas`, las de cada bloque de arriba abajo:
    [(caja, su rótulo o None, la utilidad que nombra, índice de la de abajo en su MText o None)]."""
    lineas: Dict[int, list]


def _encima(lineas, horiz) -> Dict[int, int]:
    """{línea: la de ARRIBA alineada (izquierda, derecha o centro), del mismo tamaño de letra y a
    menos de `BLOQUE_SALTO`}: la que podría ser la anterior del mismo MText."""
    out = {}
    for k, i in enumerate(horiz):
        bb, tam = lineas[i][1], lineas[i][2]
        for j in reversed(horiz[:k]):
            bj, tj = lineas[j][1], lineas[j][2]
            if bb[1] - bj[3] > BLOQUE_SALTO * max(tam, tj):
                continue
            if bb[1] - bj[1] <= 0.1 * tam:            # en la misma fila: otro texto
                continue
            if abs(tam - tj) > 0.02 * max(tam, tj):   # otro estilo de texto (DU08 h.21: 12.57 / 12.95)
                continue
            al = BLOQUE_ALINEADO * max(tam, tj)
            if abs(bb[0] - bj[0]) <= al or abs(bb[2] - bj[2]) <= al \
                    or abs((bb[0] + bb[2]) - (bj[0] + bj[2])) <= 2 * al:
                out[i] = j
                break
    return out


def _huecos_mtext(lineas, encima) -> Dict[float, List[float]]:
    """{tamaño de letra: huecos entre líneas de un MText en esta hoja}: los de tres líneas
    seguidas a paso constante (un MText de 3+ líneas), que se repiten."""
    vistos: Dict[float, Dict[float, int]] = defaultdict(lambda: defaultdict(int))
    for i, j in encima.items():
        h = encima.get(j)
        if h is None:
            continue
        (bh, th), (bj, tj), (bi, ti) = (lineas[h][1], lineas[h][2]), (lineas[j][1], lineas[j][2]), (lineas[i][1], lineas[i][2])
        tam = max(th, tj, ti)
        if max(bi[1] - bj[3], bj[1] - bh[3]) > BLOQUE_HUECO_SOLO * tam:
            continue
        if abs((bi[1] - bj[1]) - (bj[1] - bh[1])) <= BLOQUE_PASO_TOL * tam:
            for g in (bi[1] - bj[3], bj[1] - bh[3]):
                vistos[round(tam, 1)][round(g, 1)] += 1
    return {t: [g for g, n in c.items() if n >= 2] for t, c in vistos.items() if any(n >= 2 for n in c.values())}


def rotulos(lineas: Sequence[Tuple[str, Tuple, float, Pt]]) -> Tuple[List[Rotulo], Dict[int, Tuple]]:
    """Rótulos de diámetro y las cajas de TODOS los bloques de texto horizontales:
    {bloque: (x0, y0, x1, y1, tamaño)}."""
    horiz = [i for i, l in enumerate(lineas) if abs(l[3][1]) < 0.05]
    horiz.sort(key=lambda i: (lineas[i][1][1], lineas[i][1][0]))
    encima = _encima(lineas, horiz)
    huecos = _huecos_mtext(lineas, encima)
    bloque = {}
    antes = {}                                   # línea de arriba en su bloque
    nb = 0
    for i in horiz:
        bb, tam = lineas[i][1], lineas[i][2]
        j = encima.get(i)
        une = False
        if j is not None:
            bj, tj = lineas[j][1], lineas[j][2]
            tol = BLOQUE_PASO_TOL * max(tam, tj)
            # un MText lleva sus líneas a paso CONSTANTE: dos rótulos apilados y alineados
            # («LAT CB-226 / 18" RCP SD» y debajo «CB-226, LACFCD / … / STA 69+17.24», DU06
            # h.10) dejan entre ellos un paso mayor y son dos bloques
            h = antes.get(j)
            if h is not None:
                une = abs((bb[1] - bj[1]) - (bj[1] - lineas[h][1][1])) <= tol
            else:
                # las dos primeras: pegadas (las cajas de las líneas se tocan), o con el hueco de
                # los MText de la hoja si se conoce (DU08 h.21: «COLA-SD UNV, CB» de una línea, 1.1 pt
                # sobre «*SCG AM-15, / 3" STL…», cuyas líneas van a −0.1 pt; DU06 h.10: «LAT CB-226 /
                # 18" RCP SD», a 2.5 pt como sus MText de 4 líneas); sin hueco conocido, cercanas
                hueco, t = bb[1] - bj[3], max(tam, tj)
                gs = huecos.get(round(t, 1))
                une = hueco <= BLOQUE_HUECO_SOLO * t and (
                    abs(hueco) <= BLOQUE_PEGADAS * t or not gs or any(abs(hueco - g) <= tol for g in gs))
        if une:
            bloque[i] = bloque[j]
            antes[i] = j
        else:
            bloque[i] = nb
            nb += 1
    def util_arriba(i):
        """La utilidad del dueño escrito ARRIBA en el mismo rótulo (DU08: «DWPWS W200-150, / 12"
        C.I., 23'S CL», «SCG AM-17, / 2" STL, 17'N CL»): la línea de arriba más cercana que nombra
        una, sin pasar por otra con diámetro (ahí empieza otro rótulo). Nunca de abajo: «3" STL,
        G086 / DWPPS OE / CHTR OH TEL» son tres rótulos con el mismo paso (DU08 h.21)."""
        j = antes.get(i)
        while j is not None:
            if lecturas(lineas[j][0]):
                return ""
            u = utilidad_de(lineas[j][0])
            if u:
                return u
            j = antes.get(j)
        return ""

    out: List[Rotulo] = []
    for i, (t, bb, tam, d) in enumerate(lineas):
        if i not in bloque:
            continue
        ls = lecturas(t)
        if len({v for v, _n in ls}) != 1:
            continue
        u, mat = utilidad_de(t) or util_arriba(i), material_de(t)
        if not (u or mat):                     # «12" MIN», «8"» suelto: no es de una tubería
            continue
        out.append(Rotulo(t, ls[0][0], bb, tam, u, mat, bloque[i], varios=max(n for _v, n in ls)))
    distintos: Dict[int, set] = defaultdict(set)
    for r in out:
        distintos[r.bloque].add(r.pulg)
    # un banco de conductos que sigue en la línea de abajo con otro tamaño («PROP DWPPS 6-6" & /
    # 1-4"P CONDUIT») no da un diámetro. Solo por el «&»: una columna de rótulos de una línea al
    # mismo paso («8" GAS / 10-4" ELEC / PROP 24" SD», DU08 h.46) queda en un solo bloque
    despues = {j: i for i, j in antes.items()}
    mezclados = set()
    for i in horiz:
        j = despues.get(i)
        if j is not None and lineas[i][0].rstrip().endswith("&"):
            if len({v for v, _n in lecturas(lineas[i][0]) + lecturas(lineas[j][0])}) > 1:
                mezclados.update((tuple(lineas[i][1]), tuple(lineas[j][1])))
    out = [r for r in out if tuple(r.bbox) not in mezclados]
    # las líneas de cada rótulo: de la suya hasta la del siguiente rótulo del bloque
    lineas_de: Dict[int, List[int]] = defaultdict(list)
    for i in horiz:
        lineas_de[bloque[i]].append(i)
    for r in out:
        r.otros = len(distintos[r.bloque]) - 1
        siguientes = [o.bbox[1] for o in out if o.bloque == r.bloque and o.bbox[1] > r.bbox[1] + 0.1 * r.tam]
        hasta = min(siguientes) if siguientes else math.inf
        previos = [o.bbox[1] for o in out if o.bloque == r.bloque and o.bbox[1] < r.bbox[1] - 0.1 * r.tam]
        desde = max(previos) if previos else -math.inf
        r.nombres = tuple(dict.fromkeys(n for i in lineas_de[r.bloque]
                                        if desde + 0.1 * r.tam < lineas[i][1][1] < hasta - 0.1 * r.tam
                                        for n in nombres_de(lineas[i][0])))
        suyas = [lineas[i][0] for i in lineas_de[r.bloque]
                 if r.bbox[1] - 0.1 * r.tam <= lineas[i][1][1] < hasta - 0.1 * r.tam]
        r.estacion = any(RX_ESTACION.search(t) for t in suyas)
        r.union = r.estacion and any(RX_UNION.search(t.upper()) for t in suyas)
    cajas: Dict[int, List[float]] = {}
    for i, b in bloque.items():
        bb, tam = lineas[i][1], lineas[i][2]
        c = cajas.setdefault(b, [*bb, tam])
        c[0], c[1], c[2], c[3] = min(c[0], bb[0]), min(c[1], bb[1]), max(c[2], bb[2]), max(c[3], bb[3])
        c[4] = max(c[4], tam)
    res = Cajas({b: tuple(c) for b, c in cajas.items()})
    rot_de = {tuple(r.bbox): r for r in out}
    res.lineas, pos = defaultdict(list), {}
    for i in horiz:
        b = bloque[i]
        pos[i] = len(res.lineas[b])
        res.lineas[b].append([lineas[i][1], rot_de.get(tuple(lineas[i][1])), utilidad_de(lineas[i][0]), None])
    for i, j in antes.items():
        res.lineas[bloque[j]][pos[j]][3] = pos[i]
    return out, res
