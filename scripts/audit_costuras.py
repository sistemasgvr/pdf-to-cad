"""Auditoría de costuras del compositor (2026-09-24): pares contiguos de los PDFs de prueba.

Uso (desde la raíz): python scripts/audit_costuras.py ["nombre.pdf" …]
Carpeta de los PDFs: variable PDFCAD_DOCS o «Documentos/docs prueba».
Cada par se prueba con 9 recortes (corto, justo, largo, con el imán del área)
× 2 alturas × 3 soltados (±30 pt) = 54 uniones; «MAL» = el mismo punto del
plano queda a >0.3 pt desde las dos piezas.

Verdad: vectores IDÉNTICOS que las dos hojas comparten junto a la costura
(mismo largo, rumbo y capa) → traslación t (página B = página A + t).
Se simula el flujo del usuario (recorte con «sin línea de borde» + soltar la
pieza cerca) y se mide el desfase de la costura contra esa verdad."""
import os, sys, re, math, time, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'app'), ROOT]
import fitz
from collections import Counter, defaultdict
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
import composite as C, composite_dialog

PD = os.environ.get("PDFCAD_DOCS", os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "docs prueba")) + os.sep
PDFS = sys.argv[1:] or ["DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf",
                        "DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf",
                        "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf",
                        "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf"]


def lsegs(page):
    out = []
    rot = page.rotation_matrix; ox, oy = page.rect.x0, page.rect.y0
    ra, rb, rc, rd, re_, rf = rot.a, rot.b, rot.c, rot.d, rot.e, rot.f
    for p in C.page_drawings(page):
        lay = p.get('layer') or ''; w = p.get('width') or 0
        for it in p.get('items') or ():
            if it[0] != 'l': continue
            ax, ay, bx, by = it[1].x, it[1].y, it[2].x, it[2].y
            ax, ay, bx, by = (ax*ra+ay*rc+re_-ox, ax*rb+ay*rd+rf-oy, bx*ra+by*rc+re_-ox, bx*rb+by*rd+rf-oy)
            L = math.hypot(bx-ax, by-ay)
            if L < 2: continue
            if (ax, ay) > (bx, by): ax, ay, bx, by = bx, by, ax, ay
            out.append((lay, L, math.degrees(math.atan2(by-ay, bx-ax)) % 180, ax, ay, bx, by, w))
    return out


def match_line(segs, near_x, vert=True):
    best = None
    cand = sorted(((s[3]+s[5])/2, min(s[4], s[6]), max(s[4], s[6]), s[0]) for s in segs
                  if s[7] >= 1.4 and abs(s[2]-90) <= 1.0)
    groups = []
    for c in cand:
        if groups and c[0]-groups[-1][-1][0] <= 1.0 and c[3] == groups[-1][-1][3]: groups[-1].append(c)
        else: groups.append([c])
    for g in groups:
        cov = sum(h-l for _, l, h, _ in g)
        if cov < 250 or len(g) < 4: continue
        x = sum(t[0] for t in g)/len(g)
        if abs(x-near_x) > 200: continue
        if best is None or abs(x-near_x) < abs(best[0]-near_x):
            # recta x = a + b·y
            n = len(g); my = sum((l+h)/2 for _, l, h, _ in g)/n
            b = sum(((l+h)/2-my)*(t-x) for t, l, h, _ in g) / max(1e-9, sum(((l+h)/2-my)**2 for _, l, h, _ in g))
            best = (x, min(t[1] for t in g), max(t[2] for t in g), b, my)
    return best


def truth(sa, sb, xa, xb, band=45.0, dxml=None):
    A = [s for s in sa if abs(s[3]-xa) <= band and abs(s[5]-xa) <= band]
    B = [s for s in sb if abs(s[3]-xb) <= band and abs(s[5]-xb) <= band]
    bk = defaultdict(list)
    for s in B: bk[(s[0], round(s[1]*5), round(s[2]*5))].append(s)
    votes = Counter(); ex = defaultdict(list)
    for s in A:
        for t in bk.get((s[0], round(s[1]*5), round(s[2]*5)), ()):
            dx = t[3]-s[3]; dy = t[4]-s[4]
            if abs(t[5]-s[5]-dx) > 0.05 or abs(t[6]-s[6]-dy) > 0.05: continue
            if dxml is not None and abs(dx-dxml) > 1.5: continue
            k = (round(dx*4), round(dy*4)); votes[k] += 1; ex[k].append((dx, dy))
    if not votes: return None
    top = votes.most_common(3)
    k, v = top[0]
    pts = [p for kk in ex for p in ex[kk] if abs(kk[0]-k[0]) <= 1 and abs(kk[1]-k[1]) <= 1]
    dx = sorted(p[0] for p in pts)[len(pts)//2]; dy = sorted(p[1] for p in pts)[len(pts)//2]
    second = next((vv for kk, vv in top[1:] if abs(kk[0]-k[0]) > 2 or abs(kk[1]-k[1]) > 2), 0)
    return dx, dy, len(pts), second


def truth_cont(sa, sb, mla, mlb, dxml):
    """dy por continuidad: líneas (no casi verticales) que llegan a la match line
    en A y salen de ella en B, misma capa y rumbo ±0.3°: prolongadas hasta la
    match line, su cruce en B = cruce en A + dy."""
    def crossings(segs, ml, inside_sign):
        out = []
        for s in segs:
            lay, L, ang = s[0], s[1], s[2]
            if L < 8 or abs(ang - 90) < 20: continue
            xs = (s[3], s[5])
            xml = ml[0]
            near = [abs(x - xml) for x in xs]
            if min(near) > 4: continue
            far = xs[0] if near[0] > near[1] else xs[1]
            if (far - xml) * inside_sign < 3: continue
            k = (s[6] - s[4]) / (s[5] - s[3])
            y = s[4] + k * (xml - s[3])
            out.append((lay, ang, y))
        return out
    ca = crossings(sa, mla, -1); cb = crossings(sb, mlb, +1)
    votes = Counter(); vals = defaultdict(list)
    for la, aa, ya in ca:
        for lb, ab, yb in cb:
            if la != lb or abs(aa - ab) > 0.3: continue
            d = yb - ya
            if abs(d) > 400: continue
            k = round(d * 2); votes[k] += 1; vals[k].append(d)
    if not votes: return None
    k, v = votes.most_common(1)[0]
    grp = [d for kk in (k-1, k, k+1) for d in vals.get(kk, [])]
    sec = max((vv for kk, vv in votes.items() if abs(kk-k) > 3), default=0)
    grp.sort()
    return dxml, grp[len(grp)//2], len(grp), sec


def pairs_of(doc):
    info = {}
    for pn, pg in enumerate(doc):
        for b in pg.get_text("blocks"):
            tx = " ".join(b[4].split())
            m = re.search(r"MATCH\s*LINE\s*STA\s*([\d+.]+)", tx, re.I)
            if not m: continue
            st = m.group(1)
            info.setdefault(pn, []).append((st, (b[0]+b[2])/2, (b[1]+b[3])/2))
    out = []
    for a in info:
        for b in info:
            if b <= a: continue
            for sa, xa, ya in info[a]:
                for sb, xb, yb in info[b]:
                    W = doc[a].rect.width
                    if sa == sb and ((xa > W/2) != (xb > W/2)):
                        out.append((a, b, sa, xa, xb) if xa > W/2 else (b, a, sa, xb, xa))
    return out


results = []
for f in PDFS:
    doc = fitz.open(PD+f)
    data = open(PD+f, 'rb').read()
    dlg = composite_dialog.CompositeDialog(None, [{"name": f, "data": data}], None, {}, 0)
    W, H = doc[0].rect.width, doc[0].rect.height
    segc = {}
    for a, b, st, txa, txb in pairs_of(doc):
        pa, pb = doc[a], doc[b]
        W, H = pa.rect.width, pa.rect.height
        if (pb.rect.width, pb.rect.height) != (W, H):
            print('tamaños distintos', a+1, b+1); continue
        if pa.rotation or pb.rotation:
            print('rot', a+1, b+1); continue
        sa = segc.get(a) or segc.setdefault(a, lsegs(pa)); sb = segc.get(b) or segc.setdefault(b, lsegs(pb))
        mla = match_line(sa, txa - 60); mlb = match_line(sb, txb + 60)
        if not mla or not mlb:
            print(f[:6], a+1, b+1, st, 'sin match line', mla, mlb, flush=True); continue
        tr = truth(sa, sb, mla[0], mlb[0], dxml=mlb[0]-mla[0])
        kind = 'vect'
        if not tr or tr[2] < 6 or tr[3]*1.5 > tr[2]:
            tr = truth_cont(sa, sb, mla, mlb, mlb[0]-mla[0]); kind = 'cont'
            if not tr or tr[2] < 5 or tr[3]*1.5 > tr[2]:
                print(f[:6], a+1, b+1, st, 'sin verdad', tr, flush=True); continue
        dx, dy, nv, sec = tr
        # control: la match line de A trasladada cae sobre la de B
        ml_err = (mla[0] + mla[3]*(mlb[4]-dy-mla[4]) + dx) - mlb[0]
        y0 = max(mla[1], mlb[1]-dy) ; y1 = min(mla[2], mlb[2]-dy)
        ga = C.guide_lines(pa)['x']; gb = C.guide_lines(pb)['x']
        for jit, snap in ((-4.0, 0), (0.0, 0), (3.0, 0), (12.0, 0), (25.0, 0), (-12.0, 1), (12.0, 1), (25.0, 1), (45.0, 1)):
            for top_off in (0.0, 40.0):
                dlg.comp.pieces.clear(); dlg.view.rebuild()
                xa = mla[0]+jit; xb = mlb[0]-jit
                if snap:
                    g = C.snap_edge(ga, xa, y0-10, y1+10, 30.0); xa = g[0] if g else xa
                    g = C.snap_edge(gb, xb, y0+dy-10+top_off, y1+dy+10, 30.0); xb = g[0] if g else xb
                for pno, rect in ((a, (mla[0]-700, y0-10, xa, y1+10)),
                                  (b, (xb, y0+dy-10+top_off, mlb[0]+700, y1+dy+10))):
                    dlg.btn_trim.setChecked(True)
                    dlg.lst_pages.setCurrentRow(pno)
                    r = dlg.crop._page_rect; sx, sy = r.width()/W, r.height()/H
                    x0, yy0, x1, yy1 = rect
                    dlg.crop._selection = QtCore.QRectF(x0*sx, yy0*sy, (x1-x0)*sx, (yy1-yy0)*sy)
                    dlg._take(full=False)
                p1, p2 = dlg.comp.pieces
                tgt = dlg.comp.target_scale()
                w1, _ = C.piece_size(p1, (W, H), tgt)
                # posición verdadera de p2 (a lo largo de la costura) y soltado a ±30 pt
                P = (mla[0]-100, (y0+y1)/2)
                for drop in (-30.0, 0.0, 30.0):
                    p2.x, p2.y = p1.x + w1 + 3.0, p1.y
                    m1 = C.piece_map(p1, (W, H), tgt)(*P); m2 = C.piece_map(p2, (W, H), tgt)(P[0]+dx, P[1]+dy)
                    ty = p2.y + (m1[1]-m2[1])
                    t0 = time.time()
                    s = dlg.view.snap_position(1, (p1.x + w1 + 3.0, ty + drop))
                    ms = (time.time()-t0)*1000
                    if s is None:
                        results.append((f[:6], a+1, b+1, (jit, snap), top_off, drop, None, None, ms)); continue
                    p2.x, p2.y = s
                    m2 = C.piece_map(p2, (W, H), tgt)(P[0]+dx, P[1]+dy)
                    ex, ey = m2[0]-m1[0], m2[1]-m1[1]
                    # hueco/solape real en la costura (pt): borde der. de p1 vs borde izq. de p2 en coords de A
                    ca = p1.clip[2]*W; cb = p2.clip[0]*W - dx
                    results.append((f[:6], a+1, b+1, (jit, snap), top_off, drop, round(ex, 2), round(ey, 2), round(ms), round(cb-ca, 2)))
        mine = [r for r in results if r[0] == f[:6] and r[1] == a+1 and r[2] == b+1]
        bad = [r for r in mine if r[6] is None or abs(r[6]) > 0.3 or abs(r[7]) > 0.3]
        slow = max(r[8] for r in mine)
        print(f[:6], a+1, b+1, st, kind, 't=(%.2f,%.2f) votos %d/%d ml_err %.2f' % (dx, dy, nv, sec, ml_err),
              'MAL %d/%d' % (len(bad), len(mine)), 'max %d ms' % slow, [r[3:] for r in bad[:4]], flush=True)
    dlg.close_docs()
