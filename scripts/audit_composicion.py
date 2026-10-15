"""Auditoría de la composición sugerida (2026-10-14): todas las hojas de los PDFs de prueba.

Uso (desde la raíz):
    python scripts/audit_composicion.py [--fotos] [--reconocer] [juego …]
Juegos: du06 du10 du08 laboe agua cloaca sd (sin nombres = todos). PDFs en
`PDFCAD_DOCS` / `PDFCAD_DOCS_IND` o «Documentos/docs prueba» y «DOCS DE PRUEBA IND».

Por cada juego: fichas de TODAS las hojas, parejas, grupos y la hoja compuesta de
cada grupo (`composicion_sugerida.armar`). Por cada unión:

  · CAD: error contra una VERDAD independiente (vectores idénticos a ambos lados de
    la match line, o continuidad de las líneas que la cruzan; mismo criterio que
    `audit_costuras.py`): «MAL» si el mismo punto del plano queda a >0.3 pt.
  · Mapa: RMS del ajuste y, ya armada, qué fracción de los trazos de la franja común
    de una pieza tiene su gemelo en la otra a ≤0.3 pt; residuo de los ciclos.
  · --fotos: recortes de cada costura (PDF materializado de las dos piezas) en
    output/audit_composicion/<juego>/ para revisar a la vista.
  · --reconocer (solo CAD): reconoce las 6 utilidades en cada par de piezas y cuenta
    las puntas de línea pegadas a la costura (una línea que se corta ahí) frente a
    las que la cruzan."""
import math
import os
import sys
import time
from collections import Counter, defaultdict

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "app"), ROOT]

import fitz  # noqa: E402
import vector_pipeline as VP  # noqa: E402
from hoja import composite as C  # noqa: E402
from hoja import composicion_ficha as F  # noqa: E402
from hoja import composicion_sugerida as G  # noqa: E402

HOME = os.path.expanduser("~")
PD = os.environ.get("PDFCAD_DOCS", os.path.join(HOME, "OneDrive", "Documentos", "docs prueba"))
PI = os.environ.get("PDFCAD_DOCS_IND", os.path.join(HOME, "OneDrive", "Documentos", "DOCS DE PRUEBA IND"))
JUEGOS = {
    "du06": [os.path.join(PD, "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")],
    "du10": [os.path.join(PD, "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf")],
    "du08": [os.path.join(PD, "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")],
    "laboe": [os.path.join(PD, "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf")],
    "agua": [os.path.join(PI, "QS Water_Indian School_North.pdf"), os.path.join(PI, "QS Water_Indian School_South.pdf")],
    "cloaca": [os.path.join(PI, "QS Sewer_Indian School_North.pdf"), os.path.join(PI, "QS Sewer_Indian School_South.pdf")],
    "sd": [os.path.join(PI, "QS SD_Indian School_North.pdf"), os.path.join(PI, "QS SD_Indian School_South.pdf")],
}
OUT = os.path.join(ROOT, "output", "audit_composicion")


# ── verdad CAD (independiente del compositor: copia de audit_costuras) ──────────
def lsegs(page):
    out = []
    rot = page.rotation_matrix
    for p in C.page_drawings(page):
        lay = p.get("layer") or ""
        w = p.get("width") or 0
        for it in p.get("items") or ():
            if it[0] != "l":
                continue
            a = it[1] * rot; b = it[2] * rot
            L = math.hypot(b.x - a.x, b.y - a.y)
            if L < 2:
                continue
            ax, ay, bx, by = a.x, a.y, b.x, b.y
            if (ax, ay) > (bx, by):
                ax, ay, bx, by = bx, by, ax, ay
            out.append((lay, L, math.degrees(math.atan2(by - ay, bx - ax)) % 180, ax, ay, bx, by, w))
    return out


def match_line(segs, near_x):
    cand = sorted(((s[3] + s[5]) / 2, min(s[4], s[6]), max(s[4], s[6]), s[0]) for s in segs
                  if s[7] >= 1.4 and abs(s[2] - 90) <= 1.0)
    groups = []
    for c in cand:
        if groups and c[0] - groups[-1][-1][0] <= 1.0 and c[3] == groups[-1][-1][3]:
            groups[-1].append(c)
        else:
            groups.append([c])
    best = None
    for g in groups:
        cov = sum(h - l for _, l, h, _ in g)
        if cov < 150 or len(g) < 3:
            continue
        x = sum(t[0] for t in g) / len(g)
        if abs(x - near_x) > 120:
            continue
        if best is None or abs(x - near_x) < abs(best[0] - near_x):
            best = (x, min(t[1] for t in g), max(t[2] for t in g))
    return best


def truth(sa, sb, xa, xb, band=45.0, dxml=None):
    A = [s for s in sa if abs(s[3] - xa) <= band and abs(s[5] - xa) <= band]
    B = [s for s in sb if abs(s[3] - xb) <= band and abs(s[5] - xb) <= band]
    bk = defaultdict(list)
    for s in B:
        bk[(s[0], round(s[1] * 5), round(s[2] * 5))].append(s)
    votes = Counter(); ex = defaultdict(list)
    for s in A:
        for t in bk.get((s[0], round(s[1] * 5), round(s[2] * 5)), ()):
            dx = t[3] - s[3]; dy = t[4] - s[4]
            if abs(t[5] - s[5] - dx) > 0.05 or abs(t[6] - s[6] - dy) > 0.05:
                continue
            if dxml is not None and abs(dx - dxml) > 1.5:
                continue
            k = (round(dx * 4), round(dy * 4)); votes[k] += 1; ex[k].append((dx, dy))
    if not votes:
        return None
    top = votes.most_common(3)
    k, _v = top[0]
    pts = [p for kk in ex for p in ex[kk] if abs(kk[0] - k[0]) <= 1 and abs(kk[1] - k[1]) <= 1]
    dx = sorted(p[0] for p in pts)[len(pts) // 2]; dy = sorted(p[1] for p in pts)[len(pts) // 2]
    second = next((vv for kk, vv in top[1:] if abs(kk[0] - k[0]) > 2 or abs(kk[1] - k[1]) > 2), 0)
    return dx, dy, len(pts), second


def truth_cont(sa, sb, xa, xb, dxml):
    def crossings(segs, xml, inside):
        out = []
        for s in segs:
            if s[1] < 8 or abs(s[2] - 90) < 20:
                continue
            xs = (s[3], s[5]); near = [abs(x - xml) for x in xs]
            if min(near) > 4:
                continue
            far = xs[0] if near[0] > near[1] else xs[1]
            if (far - xml) * inside < 3:
                continue
            k = (s[6] - s[4]) / (s[5] - s[3])
            out.append((s[0], s[2], s[4] + k * (xml - s[3])))
        return out
    ca = crossings(sa, xa, -1); cb = crossings(sb, xb, +1)
    votes = Counter(); vals = defaultdict(list)
    for la, aa, ya in ca:
        for lb, ab, yb in cb:
            if la != lb or abs(aa - ab) > 0.3:
                continue
            d = yb - ya
            if abs(d) > 400:
                continue
            k = round(d * 2); votes[k] += 1; vals[k].append(d)
    if not votes:
        return None
    k, _v = votes.most_common(1)[0]
    grp = sorted(d for kk in (k - 1, k, k + 1) for d in vals.get(kk, []))
    sec = max((vv for kk, vv in votes.items() if abs(kk - k) > 3), default=0)
    return dxml, grp[len(grp) // 2], len(grp), sec


# ── medidas sobre la hoja compuesta ─────────────────────────────────────────
def pieza_de(comp, nodo):
    for i, p in enumerate(comp.pieces):
        if (p.source, p.page) == nodo:
            return i, p
    return None, None


def error_cad(c, comp, docs, segc):
    """Error de la costura armada contra la verdad independiente (pt)."""
    ia, pa = pieza_de(comp, c.a); ib, pb = pieza_de(comp, c.b)
    da, db = docs[c.a[0]][c.a[1]], docs[c.b[0]][c.b[1]]
    sa = segc.setdefault(c.a, lsegs(da)); sb = segc.setdefault(c.b, lsegs(db))
    mla = match_line(sa, c.corte_a); mlb = match_line(sb, c.corte_b)
    if not mla or not mlb:
        return None, "sin match line"
    tr = truth(sa, sb, mla[0], mlb[0], dxml=mlb[0] - mla[0]); kind = "vect"
    if not tr or tr[2] < 6 or tr[3] * 1.5 > tr[2]:
        tr = truth_cont(sa, sb, mla[0], mlb[0], mlb[0] - mla[0]); kind = "cont"
        if not tr or tr[2] < 5 or tr[3] * 1.5 > tr[2]:
            return None, "sin verdad"
    tgt = comp.target_scale()
    P = (mla[0] - 100, (mla[1] + mla[2]) / 2)
    m1 = C.piece_map(pa, (da.rect.width, da.rect.height), tgt)(*P)
    m2 = C.piece_map(pb, (db.rect.width, db.rect.height), tgt)(P[0] + tr[0], P[1] + tr[1])
    return math.hypot(m2[0] - m1[0], m2[1] - m1[1]), kind


def coincidencia_mapa(c, g, an):
    """De los trazos de a que caen DENTRO de la vista de b (el solape), qué fracción
    tiene su gemelo en b a ≤0.3 pt una vez llevados los dos a la hoja compuesta."""
    from hoja import composicion_encaje as E
    fa, fb = an.fichas[c.a], an.fichas[c.b]
    ca, cb = E.caja(fa), E.caja(fb)
    A = E.segmentos(fa.lineas, ca, c.lado, 0.3)
    B = E.segmentos(fb.lineas, cb, E.OPUESTO[c.lado], 0.3)
    a1, bx1, by1 = g.transf[c.a]; a2, bx2, by2 = g.transf[c.b]
    idx = defaultdict(list)
    for s in B:
        X0, Y0 = a2 * s[3] + bx2, a2 * s[4] + by2
        idx[(round(X0), round(Y0))].append((X0, Y0, a2 * s[5] + bx2, a2 * s[6] + by2))
    ok = n = 0
    for s in A:
        if s[1] < 8:
            continue
        pb0, pb1 = c.mapa(s[3], s[4]), c.mapa(s[5], s[6])
        if not all(cb[0] + 1 <= p[0] <= cb[2] - 1 and cb[1] + 1 <= p[1] <= cb[3] - 1 for p in (pb0, pb1)):
            continue
        X0, Y0, X1, Y1 = a1 * s[3] + bx1, a1 * s[4] + by1, a1 * s[5] + bx1, a1 * s[6] + by1
        n += 1
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in idx.get((round(X0) + dx, round(Y0) + dy), ()):
                    if math.hypot(q[0] - X0, q[1] - Y0) <= 0.3 and math.hypot(q[2] - X1, q[3] - Y1) <= 0.3:
                        hit = True
        ok += hit
    return ok / n if n else None, n


def sub_composite(comp, nodos):
    sub = C.Composite(scale_ft_per_pt=comp.target_scale())
    for p in comp.pieces:
        if (p.source, p.page) in nodos:
            sub.pieces.append(C.Piece.from_dict(p.to_dict()))
    mx = min(p.x for p in sub.pieces); my = min(p.y for p in sub.pieces)
    for p in sub.pieces:
        p.x -= mx; p.y -= my
    return sub


def materializar(sub, docs):
    """Como la app (`Main._build_composite_doc`): puentes, PDF de una hoja y reabrirlo."""
    puentes = C.compute_bridges(sub, docs)
    built = C.build_document(sub, docs, {}, puentes)
    data = built.tobytes(deflate=True)
    built.close()
    return fitz.open(stream=data, filetype="pdf"), len(puentes)


def costura_en_compuesta(c, sub, docs):
    """Recta de la costura en la hoja MATERIALIZADA (con su margen): (eje, coord, desde, hasta)."""
    ia, pa = pieza_de(sub, c.a)
    da = docs[c.a[0]][c.a[1]]
    sizes = lambda p: (docs[p.source][p.page].rect.width, docs[p.source][p.page].rect.height)
    _w, _h, dx, dy = C.sheet_geometry(sub, sizes)
    x0, y0, x1, y1 = C.piece_rect(pa, (da.rect.width, da.rect.height), sub.target_scale())
    x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
    return {"right": ("x", x1, y0, y1), "left": ("x", x0, y0, y1),
            "bottom": ("y", y1, x0, x1), "top": ("y", y0, x0, x1)}[c.lado]


def fotos(nombre, c, sub, docs, k):
    os.makedirs(os.path.join(OUT, nombre), exist_ok=True)
    work, _n = materializar(sub, docs)
    page = work[0]
    eje, v, lo, hi = costura_en_compuesta(c, sub, docs)
    rutas = []
    for f in (0.3, 0.7):
        u = lo + (hi - lo) * f
        r = fitz.Rect(v - 60, u - 45, v + 60, u + 45) if eje == "x" else fitz.Rect(u - 60, v - 45, u + 60, v + 45)
        ruta = os.path.join(OUT, nombre, "%02d_h%d-h%d_%d.png" % (k, c.a[1] + 1, c.b[1] + 1, int(f * 10)))
        page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=r & page.rect).save(ruta)
        rutas.append(ruta)
    return work, rutas


def reconocer(c, sub, work, docs):
    """Puntas de línea a ≤3 pt de la costura (cortes) y líneas que la cruzan."""
    from reconocimiento import recognition as R
    eje, v, lo, hi = costura_en_compuesta(c, sub, docs)
    cortes = cruzan = 0
    for util in R.SUPPORTED_UTILITIES:
        try:
            res = R.recognize_page(None, 0, utility=util, doc=work, zoom=1.0, scale_ft_per_pt=sub.target_scale())
        except Exception:
            continue
        for pl in res.polylines:
            pts = pl.pts_pdf
            if len(pts) < 2:
                continue
            k = 0 if eje == "x" else 1
            for p in (pts[0], pts[-1]):
                if abs(p[k] - v) <= 3.0 and lo <= p[1 - k] <= hi:
                    cortes += 1
            if any((a[k] - v) * (b[k] - v) < 0 for a, b in zip(pts, pts[1:])):
                cruzan += 1
    return cortes, cruzan


UTIL_JUEGO = {"agua": "AGUA", "cloaca": "ALCANTARILLADO", "sd": "DRENAJE"}
_ESTILOS = {}


def reconocer_mapa(c, sub, work, docs, util):
    """Mapa sin capas: el estilo de la red lo da la leyenda de la hoja de origen (como en la
    app); en la hoja compuesta de las dos piezas, líneas que cruzan la costura y puntas
    pegadas a ella (sin contar los bordes exteriores del par)."""
    from reconocimiento import recognition as R
    from hoja import acometidas_mapa
    clave = (docs[c.a[0]].name, c.a[1], util)
    if clave not in _ESTILOS:
        r0 = R.recognize_page(docs[c.a[0]].name, page_index=c.a[1], utility=util, zoom=1.0)
        _ESTILOS[clave] = sorted({pl.layer_ocg for pl in r0.drawable if not acometidas_mapa.es_capa(pl.layer_ocg)})
    estilos = _ESTILOS[clave]
    if not estilos:
        return None
    eje, v, lo, hi = costura_en_compuesta(c, sub, docs)
    k = 0 if eje == "x" else 1
    r = R.recognize_page(None, 0, utility=util, doc=work, zoom=1.0, scale_ft_per_pt=sub.target_scale(),
                         layer_roles={R.ROLE_LINEAS: estilos, R.ROLE_BUZONES: []})
    cortes = cruzan = 0
    for pl in r.drawable:
        pts = pl.pts_pdf
        if len(pts) < 2:
            continue
        for p in (pts[0], pts[-1]):
            if abs(p[k] - v) <= 1.5 and lo + 3 < p[1 - k] < hi - 3:
                cortes += 1
        cruzan += sum(1 for a, b in zip(pts, pts[1:]) if (a[k] - v) * (b[k] - v) < 0)
    return cortes, cruzan


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    con_fotos = "--fotos" in sys.argv
    con_rec = "--reconocer" in sys.argv
    for nombre in args or list(JUEGOS):
        paths = JUEGOS[nombre]
        if not all(os.path.exists(p) for p in paths):
            print(nombre, "— faltan PDFs"); continue
        docs = [fitz.open(p) for p in paths]
        t0 = time.time()
        fpd = [F.fichas(d, i) for i, d in enumerate(docs)]
        t1 = time.time()
        an = G.analizar(fpd)
        t2 = time.time()
        print("=== %s  fichas %.1fs  análisis %.1fs  grupos %d  descartadas %d" % (
            nombre, t1 - t0, t2 - t1, len(an.grupos), an.descartadas), flush=True)
        segc = {}
        k = 0
        for g in an.grupos:
            comp = G.armar(g, an, docs, lambda d, h: VP.detect_scale(docs[d][h]),
                           [os.path.basename(p) for p in paths])
            d = G.resumen_datos(g, an.fichas)
            print("  grupo %s: %d hojas %s→%s %s series=%s residuo ciclos %.3f pt" % (
                g.tipo, d["n"], d["desde"], d["hasta"], d.get("sta", ""), d["series"], g.residuo), flush=True)
            for c in sorted(g.costuras, key=lambda c: (c.a, c.b)):
                if g.tipo == "estaciones":
                    err, kind = error_cad(c, comp, docs, segc)
                    estado = "sin verdad" if err is None else ("OK" if err <= 0.3 else "MAL")
                    linea = "    h%d→h%d %-11s %s err %s (%s)" % (c.a[1] + 1, c.b[1] + 1, c.metodo, estado,
                                                                "-" if err is None else "%.2f" % err, kind)
                else:
                    frac, n = coincidencia_mapa(c, g, an)
                    linea = "    %s→%s %-7s %-6s rms %.3f coinciden %s de %d" % (
                        an.fichas[c.a].etiqueta(), an.fichas[c.b].etiqueta(), c.lado, c.metodo, c.rms,
                        "-" if frac is None else "%.0f%%" % (frac * 100), n)
                if con_fotos or con_rec:
                    sub = sub_composite(comp, {c.a, c.b})
                    work, _r = fotos(nombre, c, sub, docs, k) if con_fotos else (materializar(sub, docs)[0], [])
                    if con_rec and g.tipo == "estaciones":
                        cortes, cruzan = reconocer(c, sub, work, docs)
                        linea += "  líneas: cruzan %d, cortadas en la costura %d" % (cruzan, cortes)
                    elif con_rec and nombre in UTIL_JUEGO:
                        rr = reconocer_mapa(c, sub, work, docs, UTIL_JUEGO[nombre])
                        if rr is not None:
                            linea += "  red: cruzan %d, puntas en la costura %d" % (rr[1], rr[0])
                    k += 1
                print(linea, flush=True)


if __name__ == "__main__":
    main()
