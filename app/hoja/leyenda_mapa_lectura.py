"""leyenda_mapa_lectura.py — LECTURA del cuadro de leyenda de un mapa sin capas (PURO).

Parte de `leyenda_mapa` (que da el significado: utilidad, rol, asignaciones): aquí se ubica el
cuadro y se arma cada fila = DESCRIPCIÓN + su MUESTRA (trazos con su estilo y símbolo de la
fuente) a la izquierda, en el marco de la leyenda (u a lo largo del texto, w hacia abajo):
encabezados de sección, columnas de descripciones a paso regular (partidas donde el paso se
corta, `_partir_columna`), zona de la muestra hasta el texto de la columna de la izquierda
que está a su altura, línea divisoria entre secciones, utilidad del plano y escala escrita.
`leyenda_mapa.leer` llama a `_leer` (con caché por documento).
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from hoja import pdf_styles, texto_pdf
from nucleo import avance
from traduccion.i18n_core import t as _tr
from hoja.leyenda_mapa import (ABANDONADA, ACCESORIO, ANOTACION, COLUMNA_TOL, DIVISOR_MIN, ENCABEZADO,
                               ESCALA, ESTRUCTURA, FILAS_MIN, MUESTRA_ANCHO, NOTA_DIAM_ACOMETIDA,
                               NOTA_MATERIAL, SALTO_COLUMNA, SIMBOLO_BANDA, FilaMapa, LeyendaMapa,
                               _color_claro, rol_de, utilidad_de)


# ── geometría en el marco de la leyenda ─────────────────────────────────────
class _Marco:
    """Coordenadas de la leyenda: u a lo largo del texto, w hacia abajo (siguiente fila)."""

    def __init__(self, d):
        self.e = (float(d[0]), float(d[1]))
        self.n = (-self.e[1], self.e[0])

    def uw(self, p):
        return (p[0] * self.e[0] + p[1] * self.e[1], p[0] * self.n[0] + p[1] * self.n[1])

    def caja(self, r):
        pts = [self.uw(q) for q in ((r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3]))]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))

    def a_hoja(self, u0, w0, u1, w1):
        pts = []
        for u in (u0, u1):
            for w in (w0, w1):
                pts.append((u * self.e[0] + w * self.n[0], u * self.e[1] + w * self.n[1]))
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _largo(d) -> float:
    r = d["rect"]
    return max(math.hypot(r.width, r.height), 0.05)


def _dibujos(page) -> List[dict]:
    """Trazos de la hoja con su capa virtual por estilo (sin los símbolos virtuales). La
    última hoja leída queda en caché (la piden la leyenda y las acometidas; ~0.7 s)."""
    doc = page.parent
    got = doc.__dict__.get("_pdfcad_dibujos")
    if got is not None and got[0] == page.number:
        return got[1]
    out = []
    for d in page.get_drawings():
        if d.get("type") in ("clip", "group") or d.get("layer"):
            continue
        nombre = pdf_styles.style_name(d)
        if nombre:
            out.append(dict(d, layer=nombre))
    doc.__dict__["_pdfcad_dibujos"] = (page.number, out)
    return out


def _fondos(dibujos) -> List[tuple]:
    """(seqno, caja) de los rellenos OPACOS (el fondo blanco del cuadro de la leyenda)."""
    return [(int(d.get("seqno", -1)), d["rect"]) for d in dibujos
            if d.get("type") in ("f", "fs") and d.get("fill") is not None
            and (d.get("fill_opacity") is None or float(d["fill_opacity"]) >= 0.99)]


def _tapado(d, a, b, marco, w_lo, w_hi, fondos) -> bool:
    """¿El tramo a–b de `d`, en la franja de los encabezados, queda DEBAJO de un relleno
    opaco dibujado después? (líneas del mapa que pasan bajo el cuadro: no se ven)."""
    if not fondos:
        return False
    wa, wb = marco.uw(a)[1], marco.uw(b)[1]
    w = min(max((w_lo + w_hi) / 2.0, min(wa, wb)), max(wa, wb))
    t = 0.0 if abs(wb - wa) < 1e-9 else (w - wa) / (wb - wa)
    x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
    s = int(d.get("seqno", -1))
    return any(sf > s and r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1 for sf, r in fondos)


def _divisores(dibujos, marco, w_lo, w_hi, largo_min) -> List[float]:
    """u de las líneas del cuadro que bajan de los encabezados (separan las secciones).
    Una línea del MAPA que pasa debajo del cuadro (dibujada antes que su fondo opaco) no
    cuenta: Water South h.15 (16-24) traía las de los lotes cada ~11 pt y partían la
    sección WATER (sus filas quedaban sin utilidad y la hoja sin tuberías)."""
    fondos = _fondos(dibujos)
    us = []
    for d in dibujos:
        for it in d.get("items") or ():
            if it[0] == "l":
                segs = [(it[1], it[2])]
            elif it[0] == "re":
                r = it[1]
                segs = [((r.x0, r.y0), (r.x0, r.y1)), ((r.x1, r.y0), (r.x1, r.y1)),
                        ((r.x0, r.y0), (r.x1, r.y0)), ((r.x0, r.y1), (r.x1, r.y1))]
            else:
                continue
            for a, b in segs:
                ua, wa = marco.uw(a)
                ub, wb = marco.uw(b)
                if abs(ua - ub) <= 0.3 and abs(wa - wb) >= largo_min and min(wa, wb) <= w_hi and max(wa, wb) >= w_lo:
                    if _tapado(d, a, b, marco, w_lo, w_hi, fondos):
                        continue
                    us.append((ua + ub) / 2.0)
    return sorted(us)


def _paso_regular(ws: Sequence[float]) -> bool:
    if len(ws) < FILAS_MIN:
        return False
    gaps = [b - a for a, b in zip(ws, ws[1:]) if b - a > 1e-3]
    if not gaps:
        return False
    paso = sorted(gaps)[len(gaps) // 2]
    return sum(1 for g in gaps if g <= 3.2 * paso) >= 0.7 * len(gaps)


def _partir_columna(col: List[tuple]) -> List[List[tuple]]:
    """Una «columna» (mismo inicio de texto) puede juntar filas de la leyenda con texto de
    más abajo alineado con ellas («Plotted On:» del cajetín bajo «Blow-Off Vlv»): se parte
    donde el salto entre filas pasa de `SALTO_COLUMNA` veces el paso."""
    gaps = [b[1] - a[1] for a, b in zip(col, col[1:]) if b[1] - a[1] > 1e-3]
    if not gaps:
        return [col]
    paso = sorted(gaps)[len(gaps) // 2]
    out = [[col[0]]]
    for a, b in zip(col, col[1:]):
        if b[1] - a[1] > SALTO_COLUMNA * paso:
            out.append([])
        out[-1].append(b)
    return out


# encabezados a más de esto (× su tamaño) son de OTRA leyenda: en una hoja compuesta cada
# hoja trae la suya (en una hoja sola los de su cuadro están a ≤ ~56×; entre hojas, ≥ ~250×)
GRUPO_HS = 100.0


def _grupos(heads) -> List[list]:
    """Encabezados agrupados por leyenda (cadena simple a ≤ `GRUPO_HS` × su tamaño), cada
    grupo en el orden original."""
    grupos: List[List[int]] = []
    for i, h in enumerate(heads):
        unir = [k for k, g in enumerate(grupos)
                if any(math.dist(h.origen, heads[j].origen) <= GRUPO_HS * max(h.tam, heads[j].tam) for j in g)]
        nuevo = sorted([i] + [j for k in unir for j in grupos[k]])
        grupos = [g for k, g in enumerate(grupos) if k not in unir] + [nuevo]
    grupos.sort(key=lambda g: g[0])
    return [[heads[j] for j in g] for g in grupos]


def inicios_de_piezas(page) -> Optional[List[int]]:
    """En una hoja COMPUESTA (cada pieza = un XObject que se dibuja seguido), el orden de
    dibujo (`seqno`) donde empieza cada pieza; None en una hoja normal. Así una leyenda y sus
    muestras se leen con lo de SU hoja: la de al lado puede dibujar el mapa justo encima (la
    leyenda de cada pieza queda fuera de su recorte, debajo de la vecina)."""
    cache = page.parent.__dict__.setdefault("_pdfcad_piezas", {})
    if page.number in cache:
        return cache[page.number]
    out = None
    try:
        if page.read_contents().count(b"/fzFrm") >= 2:
            starts, nuevo = [], False
            for d in page.get_cdrawings(extended=True):
                if d.get("type") == "clip" and d.get("level") == 0:
                    nuevo = True
                elif nuevo and d.get("type") not in ("clip", "group"):
                    starts.append(int(d["seqno"]))
                    nuevo = False
            out = starts if len(starts) >= 2 else None
    except Exception:
        out = None
    cache[page.number] = out
    return out


class _Pagina:
    """Lo que comparten las leyendas de la hoja, medido UNA vez en el marco de la leyenda
    (antes cada fila recorría todos los textos, símbolos y trazos de la hoja: en una hoja
    compuesta de 36 mapas, minutos). Los filtros por ventana son exactos: dejan pasar lo
    mismo que las comparaciones de siempre."""

    def __init__(self, page, corr, simbs, marco, dir_):
        import numpy as np
        self.np = np
        self.page, self.simbs, self.marco = page, simbs, marco
        self.inicios = None                  # hoja compuesta: `inicios_de_piezas` (ver `pieza_de`)
        self.etiquetas = []                  # (u, w, corrida) candidatas a descripción
        self.corr_uw = []
        for c in corr:
            if c.dir != dir_:
                continue
            uw = marco.uw(c.origen)
            self.corr_uw.append((uw, c))
            if len(re.findall(r"[A-Za-z]", c.texto)) >= 2:
                self.etiquetas.append((uw[0], uw[1], c))
        self.cu = np.array([q[0] for q, _o in self.corr_uw], float)
        self.cw = np.array([q[1] - 0.35 * o.tam for q, o in self.corr_uw], float)
        s_uw = [marco.uw(sm.centro) for sm in simbs]
        self.su = np.array([q[0] for q in s_uw], float)
        self.sw = np.array([q[1] for q in s_uw], float)
        self._dib = None

    def piezas_de(self, seqnos):
        """Pieza de cada `seqno` (matriz); -1 sin piezas."""
        np = self.np
        s = np.asarray(seqnos, dtype=np.int64)
        if not self.inicios:
            return np.full(len(s), -1, dtype=np.int64)
        return np.searchsorted(np.asarray(self.inicios, dtype=np.int64), s, side="right") - 1

    def preparar_piezas(self, inicios):
        """Pieza de cada texto, símbolo y trazo (solo en una hoja compuesta)."""
        self.inicios = inicios
        self.pz_corr = self.piezas_de([(o.glifos[0].seqno if o.glifos else -1) for _q, o in self.corr_uw])
        self.pz_etq = self.piezas_de([(c.glifos[0].seqno if c.glifos else -1) for _u, _w, c in self.etiquetas])
        self.pz_sim = self.piezas_de([(sm.glifos[0].seqno if sm.glifos else -1) for sm in self.simbs])
        self._pz_dib = None

    def piezas_dibujos(self):
        if self._pz_dib is None:
            dib, _B = self.dibujos()
            self._pz_dib = self.piezas_de([int(d.get("seqno", -1)) for d in dib])
        return self._pz_dib

    def dibujos(self):
        """(trazos de la hoja, sus cajas en el marco de la leyenda como matriz n×4)."""
        if self._dib is None:
            np = self.np
            dib = _dibujos(self.page)
            # `_Marco.caja` de cada trazo, en bloque (mismas cuentas, mismo orden: mismos números)
            r = np.array([tuple(d["rect"]) for d in dib], float).reshape(-1, 4)
            e, n = self.marco.e, self.marco.n
            us = [r[:, 0] * e[0] + r[:, 1] * e[1], r[:, 2] * e[0] + r[:, 1] * e[1],
                  r[:, 0] * e[0] + r[:, 3] * e[1], r[:, 2] * e[0] + r[:, 3] * e[1]]
            ws = [r[:, 0] * n[0] + r[:, 1] * n[1], r[:, 2] * n[0] + r[:, 1] * n[1],
                  r[:, 0] * n[0] + r[:, 3] * n[1], r[:, 2] * n[0] + r[:, 3] * n[1]]
            cajas = np.stack([np.minimum.reduce(us), np.minimum.reduce(ws),
                              np.maximum.reduce(us), np.maximum.reduce(ws)], axis=1) if len(r) else r
            self._dib = (dib, cajas)
        return self._dib


def _leer(page) -> Optional[LeyendaMapa]:
    corr = texto_pdf.corridas(page)
    simbs = texto_pdf.simbolos(page)
    utilidad = _utilidad_del_plano(corr)
    escala = _escala(corr)
    notas = _notas(corr)
    heads = [c for c in corr if c.texto.isupper() and ENCABEZADO.search(c.texto)
             and "RECORD" not in c.texto and "PROTECTED" not in c.texto]
    if not heads:
        return LeyendaMapa([], utilidad, escala, [], "", **notas)
    dir_ = max({h.dir for h in heads}, key=lambda d: sum(1 for h in heads if h.dir == d))
    heads = [h for h in heads if h.dir == dir_]
    pag = _Pagina(page, corr, simbs, _Marco(dir_), dir_)
    grupos = _grupos(heads)
    inicios = inicios_de_piezas(page) if len(grupos) > 1 else None
    if inicios:
        pag.preparar_piezas(inicios)
    # una leyenda por hoja: en una compuesta cada hoja trae la suya, con los grosores de SU
    # escala (North y South de Phoenix van a escalas distintas): las filas de todas, sin
    # repetir, y todas sus cajas fuera del mapa
    filas: List[FilaMapa] = []
    zonas: List[Tuple[float, float, float, float]] = []
    por_hoja: List[List[FilaMapa]] = []
    piezas: List[Optional[int]] = []
    vistas = set()
    for k, g in enumerate(grupos):
        avance.avisar(_tr("Leyendo la leyenda del plano…") if len(grupos) == 1
                      else _tr("Leyendo la leyenda de cada hoja…"), k + 1, len(grupos))
        pieza = None
        if inicios:
            pz = sorted(int(x) for x in pag.piezas_de([(h.glifos[0].seqno if h.glifos else -1) for h in g]))
            pieza = pz[len(pz) // 2]
        f, z = _leer_grupo(pag, g, varias=len(grupos) > 1, pieza=pieza)
        if len(grupos) > 1 and f:
            por_hoja.append(f)
            piezas.append(pieza if pieza is not None and pieza >= 0 else None)
        for fila in f:
            clave = (fila.texto, fila.seccion, tuple(sorted(fila.estilos)), fila.simbolo, fila.simbolo_fuente)
            if len(grupos) == 1 or clave not in vistas:
                vistas.add(clave)
                filas.append(fila)
        zonas += z
    _rotulos(page, filas, simbs)
    for f in por_hoja:                      # los rótulos también en las filas de cada hoja
        _rotulos(page, f, simbs)
    return LeyendaMapa(filas, utilidad, escala, zonas, "", por_hoja=por_hoja, piezas=piezas, **notas)


def _leer_grupo(pag: _Pagina, heads, varias: bool, pieza=None):
    """(filas, zonas) de la leyenda de esos encabezados. `pieza` (hoja compuesta): solo con
    los textos, símbolos y trazos de esa pieza."""
    np = pag.np
    marco = pag.marco
    de_la_pieza = pieza is not None and pieza >= 0
    hs = sorted(h.tam for h in heads)[len(heads) // 2]
    hw = [marco.uw(h.origen)[1] for h in heads]
    hu = [(marco.uw(h.origen)[0], marco.uw(h.fin)[0], h) for h in heads]
    w_top, w_bot = min(hw) - 0.5 * hs, max(hw) + 40.0 * hs
    u_lo, u_hi = min(u for u, _f, _h in hu) - 30.0 * hs, max(f for _u, f, _h in hu) + 60.0 * hs
    labels = []
    for k_e, (u, w, c) in enumerate(pag.etiquetas):
        if de_la_pieza and pag.pz_etq[k_e] != pieza:
            continue
        if not (0.3 * hs <= c.tam <= 0.95 * hs):
            continue
        if w_top < w <= w_bot and u_lo <= u <= u_hi:
            labels.append((u, w, c))
    # columnas: mismo inicio de texto, varias filas a paso regular
    labels.sort(key=lambda t: t[0])
    columnas: List[List[tuple]] = []
    for t in labels:
        if columnas and abs(t[0] - columnas[-1][0][0]) <= COLUMNA_TOL * t[2].tam:
            columnas[-1].append(t)
        else:
            columnas.append([t])
    columnas = [parte for col in columnas for parte in _partir_columna(sorted(col, key=lambda t: t[1]))]
    columnas = [col for col in columnas if _paso_regular([t[1] for t in col])]
    if not columnas:
        return [], []
    dibujos, B = pag.dibujos()
    # solo lo que cae en el cuadro de la leyenda (un mapa trae decenas de miles de trazos)
    lu0 = min(col[0][0] for col in columnas) - (MUESTRA_ANCHO + 1) * hs
    lu1 = max(marco.uw(t[2].fin)[0] for col in columnas for t in col) + hs
    lw0 = min(t[1] for col in columnas for t in col) - 3 * hs
    lw1 = max(t[1] for col in columnas for t in col) + 3 * hs
    m_dentro = (B[:, 2] >= lu0) & (B[:, 0] <= lu1) & (B[:, 3] >= lw0) & (B[:, 1] <= lw1)
    if de_la_pieza:
        m_dentro &= pag.piezas_dibujos() == pieza
    dentro = np.nonzero(m_dentro)[0]
    dib_uw = [(tuple(float(x) for x in B[i]), dibujos[i]) for i in dentro]
    # divisores: trazos cuya caja toca la franja de los encabezados (en una compuesta, solo
    # los de esta leyenda: las de las hojas vecinas pueden estar en la misma franja)
    w_lo, w_hi = min(hw) - hs, max(hw) + hs
    franja = (B[:, 3] >= w_lo) & (B[:, 1] <= w_hi)
    if varias:
        franja &= (B[:, 2] >= u_lo) & (B[:, 0] <= u_hi)
    if de_la_pieza:
        franja &= pag.piezas_dibujos() == pieza
    divs = _divisores([dibujos[i] for i in np.nonzero(franja)[0]], marco, w_lo, w_hi, DIVISOR_MIN * hs)
    fin_col = [max(marco.uw(t[2].fin)[0] for t in col) for col in columnas]
    alto_col = [(col[0][1] - col[0][2].tam, col[-1][1] + col[-1][2].tam) for col in columnas]
    # zona de la muestra de cada fila; y de la hoja, solo lo que puede caer en alguna
    zonas_fila = []
    for k, col in enumerate(columnas):
        u0 = col[0][0]
        paso = sorted(b[1] - a[1] for a, b in zip(col, col[1:]))[(len(col) - 1) // 2]
        # la muestra empieza tras el texto de la columna de la IZQUIERDA que está a su altura
        # (un párrafo de notas más abajo no cuenta: dejaba sin muestras a «As-Built Tap»)
        izq = max([fin_col[j] + 0.2 * col[0][2].tam for j in range(len(columnas))
                   if j != k and fin_col[j] < u0 and columnas[j][0][0] < u0
                   and alto_col[j][0] <= alto_col[k][1] and alto_col[k][0] <= alto_col[j][1]] + [-1e9])
        for u, w, c in col:
            s = c.tam
            zu0, zu1 = max(u - MUESTRA_ANCHO * s, izq), u - 0.1 * s
            wc = w - 0.35 * s
            zonas_fila.append((k, u, w, c, zu0, zu1, wc - 0.5 * paso, wc + 0.5 * paso, wc, paso))
    U0, U1 = min(z[4] for z in zonas_fila), max(z[5] for z in zonas_fila)
    W0, W1 = min(z[6] for z in zonas_fila), max(z[7] for z in zonas_fila)
    m_txt = (pag.cu >= U0) & (pag.cu <= U1) & (pag.cw >= W0) & (pag.cw <= W1)
    if de_la_pieza:
        m_txt &= pag.pz_corr == pieza
    txt = np.nonzero(m_txt)[0]
    banda = max(SIMBOLO_BANDA * z[9] for z in zonas_fila)
    m_sim = ((pag.su >= U0) & (pag.su <= U1) & (pag.sw >= min(z[8] for z in zonas_fila) - banda)
             & (pag.sw <= max(z[8] for z in zonas_fila) + banda))
    if de_la_pieza:
        m_sim &= pag.pz_sim == pieza
    sim_i = np.nonzero(m_sim)[0]
    filas: List[FilaMapa] = []
    cajas: List[Tuple[float, float, float, float]] = []
    secciones: Dict[int, str] = {}
    for k, u, w, c, zu0, zu1, zw0, zw1, wc, paso in zonas_fila:
        if k not in secciones:
            secciones[k] = _seccion(columnas[k][0][0], hu, divs)
        seccion = secciones[k]
        s = c.tam
        estilos: Dict[str, float] = {}
        caja = None
        for (bu0, bw0, bu1, bw1), d in dib_uw:
            cu, cw = (bu0 + bu1) / 2.0, (bw0 + bw1) / 2.0
            if zu0 <= cu <= zu1 and zw0 <= cw <= zw1 and bu1 - bu0 <= 1.5 * (zu1 - zu0) + 0.5:
                estilos[d["layer"]] = estilos.get(d["layer"], 0.0) + _largo(d)
                caja = _union(caja, (bu0, bw0, bu1, bw1))
        sim = None
        for i in sim_i:
            sm = pag.simbs[i]
            cu, cw = float(pag.su[i]), float(pag.sw[i])
            # el símbolo va CENTRADO en su fila: los puntos grises de la muestra tramada
            # de la fila de abajo («Water Detail Areas») no son el de «Water Vaults»
            if zu0 <= cu <= zu1 and abs(cw - wc) <= SIMBOLO_BANDA * paso and (sim is None or sm.radio > sim.radio):
                sim = sm
        if sim is not None:
            caja = _union(caja, marco.caja(sim.caja))
        letras = " ".join(pag.corr_uw[i][1].texto for i in txt
                          if zu0 <= pag.cu[i] <= zu1 and zw0 <= pag.cw[i] <= zw1)
        if caja is None:
            continue                          # una nota del cuadro, no una fila de leyenda
        nombra, u_texto = utilidad_de(c.texto)
        nombra_s, u_seccion = utilidad_de(seccion)
        filas.append(FilaMapa(c.texto.strip(), seccion, u_texto if nombra else u_seccion,
                              rol_de(c.texto), bool(ABANDONADA.search(c.texto.upper())),
                              marco.a_hoja(*caja), estilos,
                              sim.clave if sim is not None else None,
                              sim.fuente if sim is not None else "", letras))
        cajas.append(_union(caja, (u, w - s, marco.uw(c.fin)[0], w + 0.3 * s)))
    for _u, _f, h in hu:
        hu0, hw0 = marco.uw(h.origen)
        cajas.append((hu0, hw0 - h.tam, marco.uw(h.fin)[0], hw0 + 0.3 * h.tam))
    zona = None
    for cj in cajas:
        zona = _union(zona, cj)
    zonas = [marco.a_hoja(zona[0] - hs, zona[1] - hs, zona[2] + hs, zona[3] + hs)] if zona and filas else []
    return filas, zonas


ROTULO_CELDA_PT = 8.0       # celdas del índice de letras de `_rotulos`
ROTULO_CON_TEXTO = 0.5       # símbolo con texto DENTRO en ≥ esto de sus apariciones: es un rótulo


def _rotulos(page, filas: List[FilaMapa], simbs) -> None:
    """Un símbolo que en el mapa lleva texto DENTRO es el RÓTULO del número de una
    estructura, no la estructura: en el alcantarillado de Phoenix «Manhole» es el hexágono
    con el número del buzón (122 de 126 con número dentro), puesto al lado del buzón
    («Standard Manhole», el círculo chico: 2 de 141). Esas filas pasan a anotación."""
    import numpy as np
    letras = np.array([g.origen for g in texto_pdf.glifos(page) if g.letra not in (None, " ")], float)
    if not len(letras):
        return
    lx, ly = letras[:, 0], letras[:, 1]
    # letras por celdas: cada símbolo mira solo las de su caja (en una hoja compuesta de 36
    # mapas, todas contra todos eran minutos); mismo resultado
    celda = ROTULO_CELDA_PT
    por_celda: Dict[tuple, List[int]] = {}
    for i, (x, y) in enumerate(zip((lx // celda).astype(int), (ly // celda).astype(int))):
        por_celda.setdefault((int(x), int(y)), []).append(i)
    por_clave: Dict[tuple, List] = {}
    for s in simbs:
        por_clave.setdefault((s.fuente, s.clave), []).append(s)
    for f in filas:
        if f.rol not in (ESTRUCTURA, ACCESORIO) or not f.simbolo:
            continue
        ss = por_clave.get((f.simbolo_fuente, f.simbolo), [])
        con = 0
        for s in ss:
            x0, y0, x1, y1 = s.caja
            mx, my = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
            cand = [i for cx in range(int(math.floor((x0 + mx) / celda)), int(math.floor((x1 - mx) / celda)) + 1)
                    for cy in range(int(math.floor((y0 + my) / celda)), int(math.floor((y1 - my) / celda)) + 1)
                    for i in por_celda.get((cx, cy), ())]
            con += any(x0 + mx <= lx[i] <= x1 - mx and y0 + my <= ly[i] <= y1 - my for i in cand)
        if ss and con >= ROTULO_CON_TEXTO * len(ss):
            f.rol = ANOTACION


def _union(a, b):
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _seccion(u0, hu, divs) -> str:
    """Encabezado de la sección de una columna: el de la celda del cuadro (entre líneas
    divisorias) que la contiene; sin divisorias, el encabezado más cercano."""
    def celda(u):
        izq = max([d for d in divs if d < u] + [-1e9])
        der = min([d for d in divs if d > u] + [1e9])
        return izq, der
    cu = celda(u0 + 0.01)
    for a, f, h in hu:
        if divs and celda((a + f) / 2.0) == cu:
            return h.texto
    return min(hu, key=lambda t: abs((t[0] + t[1]) / 2.0 - u0))[2].texto


def _utilidad_del_plano(corr) -> Optional[str]:
    """La utilidad del plano: la que nombran sus textos más GRANDES (el título «WATER»,
    «SEWER») y los encabezados de la leyenda. «WATER SERVICES DEPARTMENT» es el nombre
    de la oficina (sale también en los planos de alcantarillado): no cuenta."""
    puntos: Dict[str, float] = {}
    for c in corr:
        up = c.texto.upper()
        if "DEPARTMENT" in up or "SERVICES" in up or "RECORD" in up or len(up) > 40:
            continue
        nombra, u = utilidad_de(up)
        if not nombra or u is None:
            continue
        peso = c.tam * c.tam * (3.0 if ENCABEZADO.search(up) else 1.0)
        if not ENCABEZADO.search(up) and len(up.split()) > 3:
            peso *= 0.1                           # una descripción («Water Vaults»), no un título
        puntos[u] = puntos.get(u, 0.0) + peso
    return max(puntos, key=puntos.get) if puntos else None


def _escala(corr) -> Optional[float]:
    for c in corr:
        m = ESCALA.search(c.texto)
        if m:
            return float(m.group(1)) / 72.0
    return None


def _notas(corr) -> dict:
    """Notas del cuadro: diámetro de las acometidas y material de la red («unless otherwise noted»)."""
    out = {}
    for c in corr:
        m = NOTA_DIAM_ACOMETIDA.search(c.texto)
        if m and "diam_acometida_in" not in out:
            try:
                out["diam_acometida_in"] = float(m.group(1))
            except ValueError:
                pass
        m = NOTA_MATERIAL.search(c.texto)
        if m and "material" not in out:
            out["material"] = m.group(1).upper() + (f" ({m.group(2).strip()})" if m.group(2) else "")
    return out
