"""recognition_valvulas.py — las VÁLVULAS de una hoja (PURO; pedido del usuario 2026-11-05).

Cuatro fuentes, de más a menos segura. Ninguna toca las líneas: es una lectura aparte, al final de `reconocer_hoja`.

  · CAPA (hoja con capas): `V-WATR-VALV`, `V-NGAS-VALV`, `C-WATR-GV-E`… Los recortes y las vistas de perfil los quita
    `gather_paths`, como a las líneas. En DU06 el símbolo no da el tipo: el nombre de la capa da solo la utilidad.
  · LEYENDA (mapa sin capas): las filas «Standard Vlv - Open», «Blow-Off Vlv», «Water PRVs» señalan su símbolo.
  · LEYENDA EN IMAGEN (Southwest Gas): `hoja/leyendas_imagen` la reconoce por su huella y da el glifo de cada fila.
  · FORMA (hoja sin capas ni leyenda; CAD aplanado, DU08 h.4–19): el moño de 4 lados que se cruzan. También lo son
    árboles y otros bloques, así que solo cuenta a ≤ `valvulas.EN_LINEA_PT` de una línea reconocida y queda «por
    confirmar».
  · MANUAL: lo que el usuario asignó con el rol «Válvulas» en «Capas de la hoja» (la única salida con una leyenda en
    imagen que no está en la tabla: sus símbolos son glifos de fuentes ESRI).

El tipo solo sale de un texto del plano (`tipo_de`, con los nombres del estándar LADWP PC9431); nunca de la forma.
"""
from __future__ import annotations

import bisect
import math
import re
from typing import Dict, List, Optional, Sequence

import fitz

from hoja import pdf_styles
from nucleo import valvulas as V
from reconocimiento import recognition as rec
from reconocimiento import recognition_geom as geom

MIN_PT = 1.2                # más chico = el plano índice de la hoja, a otra escala (DU06 h.2: 0.3 pt)
TOCA_PT = 0.25              # trazos de la misma capa a menos de esto = un mismo símbolo (DU06 h.13: dos válvulas a 0.6 pt)
MISMA_PT = 0.5              # el mismo símbolo en dos capas
ASTILLA_PT = 1.0            # un símbolo recortado que quedó más delgado que esto no se ubica bien
TINTA_TOL = 150             # suma de diferencias RGB: el suavizado del borde aclara el color del glifo
RAMAL_PUNTA_PT = 1.0        # las puntas de un ramal: sobre la válvula y sobre su tubería
RAMAL_MAX_PT = 30.0         # más largo ya no es un ramal que el reconocimiento descartó por corto
FORMA_MIN_PT, FORMA_MAX_PT = 2.0, 9.0
FORMA_ASPECTO = 2.2

_CAPA = re.compile(r"(?:^|[-_])(?:VALV|VLV|GV)(?:[-_]|$)")
_NO_CAPA = ("ANNO", "TEXT", "IDEN", "PROF")
_SISTEMAS = (("WATR", "AGUA"), ("WATER", "AGUA"), ("FIRE", "AGUA"), ("IRRG", "AGUA"), ("NGAS", "GAS"), ("GAS", "GAS"),
             ("SSWR", "ALCANTARILLADO"), ("SEWR", "ALCANTARILLADO"), ("STRM", "DRENAJE"))
_FILA = re.compile(r"VALVE|\bVLV\b|\bPRVS?\b|V[AÁ]LVULA", re.I)
_TIPOS = ((r"BLOW", "Purga"), (r"(DBL|DOUBLE)\s*CHECK", "Retención doble"), (r"CHECK", "Retención"),
          (r"\bPRVS?\b|REGULAT|PRESSURE\s*REDUC", "Reguladora de presión"), (r"BUTTERFLY|\bBFV\b", "Mariposa"),
          (r"\bAIR\b|\bARV\b|\bAVV\b|\bCAV\b", "Aire"), (r"GATE|\bGV\b", "Compuerta"),
          (r"STANDARD|\bLINE\b", "De línea"))


def tipo_de(texto: str) -> str:
    t = (texto or "").upper()
    return next((nombre for rx, nombre in _TIPOS if re.search(rx, t)), "")


def estado_de(texto: str) -> str:
    t = (texto or "").upper()
    if re.search(r"CLOSED|\bSHUT\b", t):
        return "cerrada"
    return "abierta" if re.search(r"\bOPEN\b", t) else ""


def es_capa_valvula(ocg: Optional[str]) -> bool:
    short = rec.standard_short_name(ocg)
    return bool(_CAPA.search(short)) and not any(t in short for t in _NO_CAPA)


def utilidad_de_capa(ocg: Optional[str]) -> str:
    partes = re.split(r"[-_]", rec.standard_short_name(ocg))
    return next((u for s, u in _SISTEMAS if s in partes), "")


def tipo_de_capa(ocg: Optional[str]) -> str:
    partes = re.split(r"[-_]", rec.standard_short_name(ocg))
    return "Compuerta" if "GV" in partes else "Riego" if "IRRG" in partes else ""


def _vertices(path) -> Optional[list]:
    """Los vértices en orden de dibujo de un trazo solo de rectas (o del cuadrilátero «qu» de `get_drawings`)."""
    items = path.get("items") or ()
    if len(items) == 1 and items[0][0] == "qu":
        q = items[0][1]
        return [tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)]
    if len(items) < 3 or any(it[0] != "l" for it in items):
        return None
    pts = [tuple(items[0][1])] + [tuple(it[2]) for it in items]
    return pts[:-1] if math.dist(pts[0], pts[-1]) < 0.05 else pts


def _cruzan(a, b, c, d) -> bool:
    def lado(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return lado(a, b, c) * lado(a, b, d) < 0 and lado(c, d, a) * lado(c, d, b) < 0


def _caja(path) -> tuple:
    return tuple(float(v) for v in geom._path_bbox(path))


def es_mono(path) -> bool:
    """El moño: cuatro lados en lazo con dos opuestos que se cruzan, del tamaño de un símbolo."""
    p = _vertices(path)
    if not p or len(p) != 4:
        return False
    xs, ys = [q[0] for q in p], [q[1] for q in p]
    ancho, alto = max(xs) - min(xs), max(ys) - min(ys)
    if not FORMA_MIN_PT <= max(ancho, alto) <= FORMA_MAX_PT or min(ancho, alto) * FORMA_ASPECTO < max(ancho, alto):
        return False
    return _cruzan(p[0], p[1], p[2], p[3]) or _cruzan(p[1], p[2], p[3], p[0])


def _grupos(paths: Sequence[dict]) -> List[dict]:
    """Trazos de la misma capa que se tocan = un símbolo → {capa, caja, recortado}."""
    por_capa: Dict[str, List[dict]] = {}
    for p in paths:
        por_capa.setdefault(p.get("layer") or "", []).append(p)
    out = []
    for capa, lista in por_capa.items():
        cajas = [_caja(p) for p in lista]
        padre = list(range(len(lista)))

        def raiz(i):
            while padre[i] != i:
                padre[i] = padre[padre[i]]
                i = padre[i]
            return i
        orden = sorted(range(len(lista)), key=lambda i: cajas[i][0])
        for n, i in enumerate(orden):
            for j in orden[n + 1:]:
                if cajas[j][0] > cajas[i][2] + TOCA_PT:
                    break
                if cajas[j][1] <= cajas[i][3] + TOCA_PT and cajas[i][1] <= cajas[j][3] + TOCA_PT:
                    padre[raiz(i)] = raiz(j)
        juntos: Dict[int, List[int]] = {}
        for i in range(len(lista)):
            juntos.setdefault(raiz(i), []).append(i)
        for ids in juntos.values():
            out.append(dict(capa=capa, recortado=any(lista[i].get("clipped") for i in ids),
                            caja=(min(cajas[i][0] for i in ids), min(cajas[i][1] for i in ids),
                                  max(cajas[i][2] for i in ids), max(cajas[i][3] for i in ids))))
    return out


def _centros(grupos: Sequence[dict]) -> List[dict]:
    """Sin plano índice, sin astillas del recorte y sin el mismo símbolo dos veces."""
    out: List[dict] = []
    for g in sorted(grupos, key=lambda g: (g["caja"][1], g["caja"][0])):
        x0, y0, x1, y1 = g["caja"]
        if max(x1 - x0, y1 - y0) < MIN_PT or (g["recortado"] and min(x1 - x0, y1 - y0) < ASTILLA_PT):
            continue
        c = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        if not any(math.dist(c, o["c"]) <= MISMA_PT for o in out):
            out.append(dict(g, c=c))
    return out


def _de_capas(page, hidden) -> List[dict]:
    _l, trazos, _n, _k = rec.gather_paths(page, lambda o: "structure" if es_capa_valvula(o) else None, hidden)
    return [dict(c=g["c"], caja=g["caja"], utilidad=utilidad_de_capa(g["capa"]), tipo=tipo_de_capa(g["capa"]),
                 capa=g["capa"], origen=V.CAPA_PDF, certeza=V.SEGURA) for g in _centros(_grupos(trazos))]


def _valvulas_en(s, claves: dict) -> List[tuple]:
    """[(fila, centro, caja)] de cada válvula de la leyenda dentro del símbolo `s`. `texto_pdf.simbolos` junta los
    glifos que se enciman: una válvula sobre un reductor o una marca tiene otra clave y su centro no es el de ella
    (Water South h.4: 18 de 218), y dos válvulas pegadas son un solo símbolo. Aquí cuentan solo SUS glifos, y cada
    copia de su primer glifo es una válvula."""
    tiene = set(s.clave)
    out = []
    for (fuente, clave), fila in claves.items():
        if fuente != s.fuente or not set(clave) <= tiene:
            continue
        por_tipo = {k: [g for g in s.glifos if (g.gid, g.color) == k] for k in clave}
        for ancla in por_tipo[clave[0]]:
            partes = [min(gs, key=lambda g: math.dist(g.origen, ancla.origen)) for gs in por_tipo.values()]
            caja = (min(g.tinta[0] for g in partes), min(g.tinta[1] for g in partes),
                    max(g.tinta[2] for g in partes), max(g.tinta[3] for g in partes))
            out.append((fila, (float(caja[0] + caja[2]) / 2.0, float(caja[1] + caja[3]) / 2.0), caja))
        break                                          # las claves van de la más larga a la más corta
    return out


def _se_ve(c, seqno, inicios, recortes) -> bool:
    """¿El punto cae en lo que se ve de SU pieza? En una hoja compuesta el texto de una pieza sigue ahí aunque su
    recorte lo tape: daba válvulas fantasma fuera de la hoja y repetidas en las uniones."""
    if not recortes:
        return True
    r = recortes[max(0, bisect.bisect_right(inicios, seqno) - 1)]
    return r is None or (r[0] <= c[0] <= r[2] and r[1] <= c[1] <= r[3])


def _de_leyenda(page) -> List[dict]:
    from hoja import leyenda_mapa, leyenda_mapa_lectura, texto_pdf
    ley = leyenda_mapa.leer(page.parent, page)
    filas: dict = {}
    for f in ley.filas:
        if f.simbolo and _FILA.search(f.texto):
            k = (f.simbolo_fuente, f.simbolo)
            if k not in filas or (f.utilidad and not filas[k].utilidad):
                filas[k] = f
    if not filas:
        return []
    filas = dict(sorted(filas.items(), key=lambda kv: -len(kv[0][1])))
    inicios = leyenda_mapa_lectura.inicios_de_piezas(page)
    recortes = leyenda_mapa_lectura.recortes_de_piezas(page)
    out: List[dict] = []
    for s in texto_pdf.simbolos(page):
        for f, c, caja in _valvulas_en(s, filas):
            if any(x0 <= c[0] <= x1 and y0 <= c[1] <= y1 for x0, y0, x1, y1 in ley.zonas) \
                    or not _se_ve(c, s.glifos[0].seqno, inicios, recortes) \
                    or any(math.dist(c, o["c"]) <= MISMA_PT for o in out):
                continue
            out.append(dict(c=c, caja=caja, utilidad=f.utilidad or ley.utilidad or "", tipo=tipo_de(f.texto),
                            estado=estado_de(f.texto), capa=f.texto, origen=V.LEYENDA, certeza=V.SEGURA))
    return out


def _se_dibuja(lista, page, caja, color) -> bool:
    """¿Se ve tinta del color del glifo en su lugar? El SIG deja glifos fuera del marco del mapa, tapados por su recorte
    (Southwest 37 (425, 247)): el texto sigue ahí, pero en la hoja no hay nada."""
    girar = rec.transformador_mupdf(page.rotation_matrix)
    a, b = girar(caja[0], caja[1]), girar(caja[2], caja[3])
    pix = lista.get_pixmap(matrix=fitz.Matrix(10, 10), clip=fitz.Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]),
                                                                    max(a[1], b[1])), alpha=False)
    rgb = [int(round(c * 255)) for c in (tuple(color) + (0, 0, 0))[:3]] if len(color) == 3 else [0, 0, 0]
    px = pix.samples
    n = pix.n
    return any(abs(px[i] - rgb[0]) + abs(px[i + 1] - rgb[1]) + abs(px[i + 2] - rgb[2]) < TINTA_TOL
               for i in range(0, len(px) - n + 1, n))


def _de_imagen(page, ley) -> List[dict]:
    """Los glifos que la leyenda en imagen dice que son válvulas (`dir` = cómo va el símbolo, para su estado)."""
    from hoja import leyenda_mapa_lectura
    inicios = leyenda_mapa_lectura.inicios_de_piezas(page)
    recortes = leyenda_mapa_lectura.recortes_de_piezas(page)
    lista = page.get_displaylist()
    out: List[dict] = []
    for sp in page.get_texttrace():
        fuente = (sp.get("font") or "").split("+")[-1]
        for ch in sp.get("chars") or ():
            s = ley.simbolos.get((fuente, ch[0]))
            if s is None:
                continue
            caja = tuple(float(v) for v in ch[3])
            c = ((caja[0] + caja[2]) / 2.0, (caja[1] + caja[3]) / 2.0)
            if not _se_ve(c, sp.get("seqno") or 0, inicios, recortes) \
                    or any(math.dist(c, o["c"]) <= MISMA_PT for o in out) \
                    or not _se_dibuja(lista, page, caja, sp.get("color") or ()):
                continue
            h = dict(c=c, caja=caja, utilidad=ley.utilidad, tipo=s.tipo, capa=s.texto, origen=V.LEYENDA, certeza=V.SEGURA)
            if s.por_rumbo:
                d = sp.get("dir") or (1.0, 0.0)
                h["dir"] = math.degrees(math.atan2(d[1], d[0]))
            out.append(h)
    return out


def _de_forma(page, hidden) -> List[dict]:
    _l, trazos, _n, _k = rec.gather_paths(
        page, lambda o: "structure" if (o or "").startswith(pdf_styles.PREFIX) else None, hidden,
        keep=lambda _o, p: es_mono(p))
    return [dict(c=g["c"], caja=g["caja"], utilidad="", capa=g["capa"], origen=V.FORMA, certeza=V.POR_CONFIRMAR)
            for g in _centros(_grupos(trazos))]


def _manuales(page, hidden, roles_by_utility) -> List[dict]:
    out = []
    for utilidad, roles in (roles_by_utility or {}).items():
        nombres = set((roles or {}).get(rec.ROLE_VALVULAS) or ())
        if nombres:
            _l, trazos, _n, _k = rec.gather_paths(page, lambda o: "structure" if o in nombres else None, hidden)
            out += [dict(c=g["c"], caja=g["caja"], utilidad=utilidad, capa=g["capa"], origen=V.MANUAL, certeza=V.SEGURA)
                    for g in _centros(_grupos(trazos))]
    return out


def leer_hoja(page, zoom, hidden=(), roles_by_utility=None) -> List[dict]:
    """Candidatas de la hoja (px de la vista); `completar` las cruza con las líneas."""
    from hoja import leyenda_mapa, leyendas_imagen
    con_capas = any((p.get("layer") or "") and not p["layer"].startswith(pdf_styles.PREFIX)
                    for p in pdf_styles.drawings(page) if p.get("type") not in ("clip", "group"))
    leyenda = not con_capas and leyenda_mapa.aplica(page)
    imagen = None if con_capas or leyenda else leyendas_imagen.conocida(page)
    hallazgos = _de_capas(page, hidden) if con_capas else _de_leyenda(page) if leyenda else \
        _de_imagen(page, imagen) if imagen else _de_forma(page, hidden)
    hallazgos += [m for m in _manuales(page, hidden, roles_by_utility)
                  if not any(math.dist(m["c"], h["c"]) <= MISMA_PT for h in hallazgos)]
    girar = rec.transformador_mupdf(page.rotation_matrix)
    crop = rec.crop_page_rect(page, None)
    out = []
    for h in hallazgos:
        x, y = girar(*h["c"])
        v = V.nueva(x * zoom - crop.x0 * zoom, y * zoom - crop.y0 * zoom, h.get("utilidad"), h.get("tipo"),
                    h.get("estado"), h["origen"], h["certeza"], h.get("capa"))
        a, b = girar(*h["caja"][:2]), girar(*h["caja"][2:])
        v["sim_w"], v["sim_h"] = abs(a[0] - b[0]) * zoom, abs(a[1] - b[1]) * zoom
        if "dir" in h:
            v["dir_sim"] = (h["dir"] + page.rotation) % 180.0
        out.append(v)
    return out


def _punta_sobre(p, lineas, cerca, tol) -> Optional[tuple]:
    """El pie de `p` sobre la línea más cercana a ≤ tol."""
    mejor = None
    for i in cerca(p[0], p[1], tol):
        pts = lineas[i]["pts"]
        for a, b in zip(pts, pts[1:]):
            q = V.pie_en(p[0], p[1], a, b)
            d = math.dist(p, q)
            if d <= tol and (mejor is None or d < mejor[0]):
                mejor = (d, q)
    return mejor[1] if mejor else None


def ramales(page, valvulas: Sequence[dict], results: Sequence, zoom: float, hidden=()) -> None:
    """Una válvula lejos de su tubería con un ramal corto dibujado que la une a ella (DU06 h.4 (374.6, 1333.3): un trazo
    de 6.4 pt de `C-WATR-UNGD-E`, que el reconocimiento descarta por corto): anota `ramal` = [pie, válvula], en px. No
    cambia ninguna línea reconocida; la tubería corta la agrega la importación (y la dibuja la vista previa)."""
    from nucleo.indice_plano import IndiceUtilidades
    sueltas = [v for v in valvulas if v.get("utilidad") and not v.get("en_linea")]
    if not sueltas:
        return
    girar = rec.transformador_mupdf(page.rotation_matrix)
    crop = rec.crop_page_rect(page, None)

    def px(q):
        x, y = girar(q[0], q[1])
        return ((x - crop.x0) * zoom, (y - crop.y0) * zoom)
    for r in results:
        propias = [v for v in sueltas if v["utilidad"] == r.utility]
        lineas = [dict(layer=r.utility, pts=pl.pts_pdf) for pl in r.drawable]
        if not propias or not lineas:
            continue
        tramos = [(px(it[1]), px(it[2])) for t in _trazos_cortos(page, r.utility, hidden) for it in t["items"]]
        indice = IndiceUtilidades(lineas)
        for v in propias:
            c = (v["x"], v["y"])
            for a, b in tramos:
                lejos, cerca_v = (a, b) if math.dist(b, c) <= math.dist(a, c) else (b, a)
                if math.dist(cerca_v, c) > RAMAL_PUNTA_PT * zoom or math.dist(a, b) > RAMAL_MAX_PT * zoom:
                    continue
                pie = _punta_sobre(lejos, lineas, indice.cerca, RAMAL_PUNTA_PT * zoom)
                if pie is not None:
                    v["ramal"] = [pie, cerca_v]
                    v["en_linea"] = True
                    break


def _trazos_cortos(page, utilidad: str, hidden) -> List[dict]:
    """Los trazos rectos sueltos de las capas de línea de `utilidad`, sin lo que el usuario apagó."""
    tapadas = set(hidden or ())
    out = []
    for p in pdf_styles.drawings(page):
        capa = p.get("layer") or ""
        items = p.get("items") or ()
        if p.get("type") in ("clip", "group") or capa in tapadas or len(items) != 1 or items[0][0] != "l":
            continue
        if rec.classify_ocg(capa, utilidad) == rec.utility_line_kind(utilidad):
            out.append(p)
    return out


def _estado_por_rumbo(giro: float, rumbo: float) -> str:
    """Leyenda de Southwest Gas: abierta = el borde del medio círculo va a lo largo de la tubería, y el `dir` del glifo
    sale perpendicular a ella. `giro` va con la y hacia abajo y `rumbo` (`valvulas._pie`) con la y hacia arriba."""
    entre = abs((giro + rumbo + 90.0) % 180.0 - 90.0)
    return "abierta" if entre > 45.0 else "cerrada"


def _lineas(results) -> List[dict]:
    return [dict(layer=r.utility, pts=pl.pts_pdf) for r in results for pl in r.drawable]


def completar(valvulas: Sequence[dict], results: Sequence, zoom: float) -> List[dict]:
    """Con las líneas reconocidas: las de forma solo sobre una línea; la utilidad que falta, de su línea; fuera las de
    una utilidad que no se reconoció."""
    from nucleo.indice_plano import IndiceUtilidades
    lineas = _lineas(results)
    indice = IndiceUtilidades(lineas) if lineas else None
    tol = V.EN_LINEA_PT * zoom
    elegidas = {r.utility for r in results}
    out = []
    for v in valvulas:
        v = dict(v)
        hay = V.relacion(dict(v, utilidad=""), lineas, tol, indice.cerca) if indice else None
        if v["origen"] == V.FORMA and hay is None:
            continue
        if not v["utilidad"] and hay is not None:
            v["utilidad"] = lineas[hay[0]]["layer"]
        if v["utilidad"] and v["utilidad"] not in elegidas:
            continue
        rel = V.relacion(v, lineas, V.tol_pt(v) * zoom, indice.cerca) if lineas else None
        v["en_linea"] = rel is not None
        if rel is not None and "dir_sim" in v and not v["estado"]:
            v["estado"] = _estado_por_rumbo(v["dir_sim"], rel[2])
        out.append(v)
    return out


def avisos(valvulas: Sequence[dict]) -> List[str]:
    por_confirmar = sum(1 for v in valvulas if v["certeza"] == V.POR_CONFIRMAR)
    sueltas = sum(1 for v in valvulas if not v.get("en_linea"))
    out = []
    if por_confirmar:
        out.append(f"Válvulas por confirmar (halladas por su forma): {por_confirmar}")
    if sueltas:
        out.append(f"Válvulas sin línea cerca: {sueltas}")
    return out
