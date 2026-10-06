"""Prueba del reconocimiento CAPA POR CAPA de un PDF (pedido del usuario 2026-09-29:
«capa agua, cómo se reconoció; capa tal, cómo se reconoció… sobre todo la continuidad»).

Uso: python scripts/audit_por_capa.py PDF [--hojas 3,4] [--util AGUA,DRENAJE]
                                          [--salida DIR] [--sin-imagenes]

Por cada utilidad y hoja corre `recognize_page` igual que la app (hoja entera, todas las
capas visibles) y reparte lo reconocido por su capa OCG. Por capa:
  · rutas, tramos, largo (ft), codos, AB;
  · TINTA RECONOCIDA: % del largo de los guiones de la capa (trazos ≥6 pt: sin letras ni
    las barras «/» que cruzan la línea) a ≤2 pt de una línea reconocida de ESA capa
    (los codos cuentan con su arco); lo que queda fuera, en manchas con coordenadas;
  · CONTINUIDAD: dos puntas de líneas distintas de la capa, enfrentadas y colineales
    (±20°, ≤2 pt de desvío) a ≤40 pt: «corte» si en el hueco hay guión de la capa (la
    línea sigue en el plano y quedó partida), «letra» si hay letra de la capa, «hueco»
    si no hay tinta (texto encima, fin real…); y «punta corta»: extremo libre con
    guiones de la capa que siguen de frente sin línea reconocida;
  · NO INVENTAR: tramos >6 pt sin tinta de su capa (fuera de bóvedas), vértices en «V»;
  · PRECISIÓN: p90 de la distancia a los guiones paralelos de la capa (>0.75 pt = impreciso).
Salida en DIR: resumen.json y, por capa y hoja, una vista (JPG) + recortes de cada
problema. Coordenadas en pt de la hoja (como el PDF).
"""
import sys, os, json, math, argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT + "/app", ROOT]
Z = 2.0                              # zoom del reconocimiento (px = pt · Z)
GAP_MAX_PT, GAP_LAT_PT, GAP_ANG = 40.0, 2.0, 20.0
COLORS = {"AGUA": (0, 110, 255), "ALCANTARILLADO": (0, 150, 60), "DRENAJE": (0, 170, 190),
          "GAS": (230, 170, 0), "ELECTRICO": (220, 30, 30), "TELECOM": (200, 60, 200)}
PROB = {"tinta_sin_linea": ((255, 0, 0), "tinta sin línea"), "corte": ((255, 120, 0), "corte"),
        "letra": ((255, 120, 0), "corte en letra"), "hueco": ((200, 170, 0), "hueco"),
        "punta_corta": ((255, 0, 0), "punta corta"), "sin_tinta": ((255, 0, 255), "sin tinta"),
        "impreciso": ((0, 190, 255), "impreciso"), "v": ((150, 0, 255), "vértice en V")}


def short(n):
    return (n or "").split("|")[-1]


class SegGrid:
    """Segmentos en una rejilla: distancia mínima de un punto a ellos."""
    def __init__(self, segs, cell=16.0):
        self.segs, self.cell, self.g = segs, cell, defaultdict(list)
        for k, (a, b) in enumerate(segs):
            for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                    self.g[(gx, gy)].append(k)

    def dist(self, q, u=None, inside=False):
        best, c = 1e9, self.cell
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self.g.get((int(q[0] // c) + dx, int(q[1] // c) + dy), ()):
                    a, b = self.segs[k]
                    vx, vy = b[0] - a[0], b[1] - a[1]
                    L2 = vx * vx + vy * vy
                    if L2 < 1e-9:
                        continue
                    if u is not None and abs(vx * u[1] - vy * u[0]) > 0.174 * math.sqrt(L2):
                        continue                          # no paralelo
                    t = ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2
                    if inside and not 0.0 < t < 1.0:
                        continue
                    t = max(0.0, min(1.0, t))
                    best = min(best, math.hypot(q[0] - a[0] - t * vx, q[1] - a[1] - t * vy))
        return best


def drawn_points(pl):
    """Geometría como la dibuja el editor: cada codo con su arco en vez de la esquina."""
    out = []
    for i, p in enumerate(pl.pts_pdf):
        f = (pl.fillets or {}).get(i)
        if not f:
            out.append(tuple(p)); continue
        a, b, c = f["a"], f["b"], f["center"]
        a0 = math.atan2(a[1] - c[1], a[0] - c[0]); a1 = math.atan2(b[1] - c[1], b[0] - c[0])
        d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        r = math.dist(a, c)
        n = max(2, int(abs(d) * r / 3.0))
        out += [(c[0] + r * math.cos(a0 + d * k / n), c[1] + r * math.sin(a0 + d * k / n)) for k in range(n + 1)]
    return out


def samples(a, b, step):
    L = math.dist(a, b)
    n = max(1, int(L / step))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def end_dir(pts, first):
    """Punta y dirección HACIA AFUERA (px), con el primer tramo de ≥2 pt."""
    seq = pts if first else pts[::-1]
    p = seq[0]
    for q in seq[1:]:
        L = math.dist(p, q)
        if L >= 2.0 * Z:
            return p, ((p[0] - q[0]) / L, (p[1] - q[1]) / L)
    return p, None


def analyze(job):
    pdf, pno, U, outdir, images = job
    import fitz, recognition as rec
    doc = fitz.open(pdf)
    res = rec.recognize_page(pdf, pno, utility=U, zoom=Z, doc=doc)
    page = doc[pno]
    lp, _vp = rec.utility_line_paths(page, U)        # por nombre y por las letras de sus líneas
    if not res.drawable and not lp:
        return []
    rm = page.rotation_matrix
    px = lambda q: (lambda P: (P.x * Z, P.y * Z))(fitz.Point(q[0], q[1]) * rm)  # noqa: E731
    paths_by = defaultdict(list)
    for p_ in lp:
        paths_by[p_.get("layer") or ""].append(p_)
    pls_by = defaultdict(list)
    for pl in res.drawable:
        pls_by[pl.layer_ocg].append(pl)
    boxes = []
    for vg in (res.vaults_geo or []):
        if vg.get("corners"):
            xs = [c[0] for c in vg["corners"]]; ys = [c[1] for c in vg["corners"]]
            boxes.append((min(xs) - 3 * Z, min(ys) - 3 * Z, max(xs) + 3 * Z, max(ys) + 3 * Z))
        elif vg.get("center") and vg.get("width_ft"):
            c = vg["center"]; r = vg["width_ft"] / res.scale_ft_per_pt * Z / 2 + 3 * Z
            boxes.append((c[0] - r, c[1] - r, c[0] + r, c[1] + r))
    in_vault = lambda q: any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in boxes)  # noqa: E731
    pt = lambda q: [round(q[0] / Z, 1), round(q[1] / Z, 1)]  # noqa: E731
    rows = []
    for layer in sorted(set(paths_by) | set(pls_by)):
        pls = pls_by.get(layer, [])
        strokes = rec.ink_strokes(paths_by.get(layer, []), px)
        dash_segs, all_segs = [], []
        for st in strokes:
            segs = list(zip(st, st[1:]))
            all_segs += segs
            xs = [q[0] for q in st]; ys = [q[1] for q in st]
            if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) >= 6.0 * Z:
                dash_segs += [(a, b) for a, b in segs if math.dist(a, b) >= 3.0 * Z]
        ink_all, ink_dash = SegGrid(all_segs), SegGrid(dash_segs)
        drawn = [drawn_points(pl) for pl in pls]
        line_segs = [(a, b) for d in drawn for a, b in zip(d, d[1:])]
        lines = SegGrid(line_segs)
        probs = []

        # ── tinta de la capa reconocida (guiones; barras «/» que cruzan, fuera) ──
        tot = ok = 0.0
        loose = []
        for st in strokes:
            xs = [q[0] for q in st]; ys = [q[1] for q in st]
            ext = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
            if ext < 6.0 * Z:
                continue                                   # letra / marca del linetype
            if len(st) == 2 and ext <= 18.0 * Z:          # «/»: corto, recto, cruza una línea
                mid = ((st[0][0] + st[1][0]) / 2, (st[0][1] + st[1][1]) / 2)
                if lines.dist(mid) <= 2.0 * Z and lines.dist(st[0]) > 2.0 * Z and lines.dist(st[1]) > 2.0 * Z:
                    continue
            for a, b in zip(st, st[1:]):
                for q in samples(a, b, 1.5 * Z)[:-1]:
                    if in_vault(q):
                        continue
                    tot += 1.5
                    if lines.dist(q) <= 2.0 * Z:
                        ok += 1.5
                    else:
                        loose.append(q)
        # manchas de tinta sin línea (vecinos a ≤6 pt)
        cell, grid = 6.0 * Z, defaultdict(list)
        for i, q in enumerate(loose):
            grid[(int(q[0] // cell), int(q[1] // cell))].append(i)
        seen = set()
        for i in range(len(loose)):
            if i in seen:
                continue
            comp, stack = [], [i]; seen.add(i)
            while stack:
                j = stack.pop(); comp.append(loose[j])
                cx, cy = int(loose[j][0] // cell), int(loose[j][1] // cell)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for k in grid.get((cx + dx, cy + dy), ()):
                            if k not in seen and math.dist(loose[j], loose[k]) <= cell:
                                seen.add(k); stack.append(k)
            if len(comp) * 1.5 >= 4.5:
                xs = [q[0] for q in comp]; ys = [q[1] for q in comp]
                probs.append({"tipo": "tinta_sin_linea", "pt": pt(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)),
                              "caja": [round(min(xs) / Z, 1), round(min(ys) / Z, 1), round(max(xs) / Z, 1),
                                       round(max(ys) / Z, 1)], "largo_pt": round(len(comp) * 1.5, 1)})

        # ── continuidad: puntas enfrentadas y puntas cortas ──
        ends = []
        for pi, pl in enumerate(pls):
            for first in (True, False):
                p, d = end_dir(drawn[pi], first)
                kinds = pl.kinds or []
                kind = (kinds[0] if first else kinds[-1]) if kinds else "end"
                ends.append((pi, p, d, kind))
        cos_g = math.cos(math.radians(GAP_ANG))
        used = set()
        for i, (pa, A, dA, ka) in enumerate(ends):
            if dA is None or ka in ("vault", "stop", "edge", "cut"):
                continue
            for j, (pb, B, dB, kb) in enumerate(ends):
                if j <= i or pb == pa or dB is None or kb in ("vault", "stop", "edge", "cut"):
                    continue
                if dA[0] * dB[0] + dA[1] * dB[1] > -cos_g:
                    continue
                v = (B[0] - A[0], B[1] - A[1])
                along = v[0] * dA[0] + v[1] * dA[1]
                lat = abs(v[0] * dA[1] - v[1] * dA[0])
                if not (-1.0 * Z <= along <= GAP_MAX_PT * Z) or lat > GAP_LAT_PT * Z + 0.05 * max(along, 0):
                    continue
                ss = samples(A, B, 1.0 * Z)[1:-1] or [A]
                dash = sum(ink_dash.dist(q) <= 1.0 * Z for q in ss) / len(ss)
                anyink = sum(ink_all.dist(q) <= 2.0 * Z for q in ss) / len(ss)
                tipo = "corte" if dash >= 0.5 else ("letra" if anyink >= 0.2 else "hueco")
                used |= {i, j}
                probs.append({"tipo": tipo, "pt": pt(((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)),
                              "hueco_pt": round(max(0.0, along) / Z, 1), "puntas": [ka, kb]})
        for i, (pa, A, dA, ka) in enumerate(ends):
            if dA is None or i in used or ka not in ("end",):
                continue
            beyond = [(A[0] + dA[0] * s * Z, A[1] + dA[1] * s * Z) for s in (1.5, 3, 4.5, 6, 7.5, 9, 10.5, 12)]
            free = [q for q in beyond if ink_dash.dist(q, dA) <= 1.0 * Z and lines.dist(q) > 2.0 * Z]
            if len(free) >= 3:
                probs.append({"tipo": "punta_corta", "pt": pt(A), "tinta_pt": round(1.5 * len(free), 1)})

        # ── no inventar + precisión + V ──
        length, p90s, vees = 0.0, [], 0
        for pi, pl in enumerate(pls):
            d = drawn[pi]
            for a, b in zip(d, d[1:]):
                L = math.dist(a, b); length += L / Z
                if L <= 6 * Z:
                    continue
                ss = [q for q in samples(a, b, 1.5 * Z) if not in_vault(q)]
                if len(ss) >= 3 and sum(ink_all.dist(q) <= 2.0 * Z for q in ss) < 0.5 * len(ss):
                    probs.append({"tipo": "sin_tinta", "pt": pt(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)),
                                  "tramo": [pt(a), pt(b)], "largo_pt": round(L / Z, 1)})
                u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                ds = sorted(x for x in (ink_dash.dist(q, u, inside=True) for q in ss[1:-1]) if x <= 3.0 * Z)
                if len(ds) >= 3:
                    p90 = ds[int(0.9 * (len(ds) - 1))] / Z
                    p90s.append(p90)
                    if p90 > 0.75:
                        probs.append({"tipo": "impreciso", "pt": pt(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)),
                                      "p90_pt": round(p90, 2), "largo_pt": round(L / Z, 1)})
            pts, kinds = pl.pts_pdf, pl.kinds or []
            for i in range(1, len(pts) - 1):
                if (kinds[i] if i < len(kinds) else "") == "fillet":
                    continue
                u = (pts[i - 1][0] - pts[i][0], pts[i - 1][1] - pts[i][1])
                w = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                nu, nw = math.hypot(*u), math.hypot(*w)
                if nu > 1e-6 and nw > 1e-6:
                    ang = math.degrees(math.acos(max(-1, min(1, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))))
                    if ang < 73:
                        vees += 1
                        probs.append({"tipo": "v", "pt": pt(pts[i]), "angulo": round(ang, 1)})
        row = {"util": U, "h": pno + 1, "capa": short(layer), "ocg": layer,
               "rutas": len(pls), "tramos": sum(int(p.n_segments or 1) for p in pls),
               "largo_ft": round(length * res.scale_ft_per_pt), "largo_pt": round(length),
               "codos": sum(len(p.fillets or {}) for p in pls), "ab": sum(1 for p in pls if p.abandoned),
               "tinta_pt": round(tot), "tinta_ok_pt": round(ok), "v": vees,
               "p90_mediana": round(sorted(p90s)[len(p90s) // 2], 3) if p90s else None,
               "problemas": probs, "imagenes": []}
        if images and (pls or tot > 0):
            row["imagenes"] = render(page, doc, U, layer, strokes, drawn, pls, probs, outdir, pno)
        rows.append(row)
    return rows


def render(page, doc, U, layer, strokes, drawn, pls, probs, outdir, pno):
    """Vista de la capa en la hoja (JPG) + recortes de cada problema."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return []
    import fitz
    xs, ys = [], []
    for st in strokes + drawn:
        xs += [q[0] / Z for q in st]; ys += [q[1] / Z for q in st]
    if not xs:
        return []
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in short(layer))
    folder = os.path.join(outdir, U.lower())
    os.makedirs(folder, exist_ok=True)
    col = COLORS.get(U, (0, 0, 0))

    def draw(box, zr, name, marks):
        x0, y0, x1, y1 = box
        clip = fitz.Rect(x0, y0, x1, y1) * ~page.rotation_matrix if page.rotation else fitz.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(matrix=fitz.Matrix(zr, zr), clip=clip, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L").convert("RGB")
        img = Image.blend(img, Image.new("RGB", img.size, (255, 255, 255)), 0.72)
        dr = ImageDraw.Draw(img, "RGBA")
        tf = lambda q: ((q[0] / Z - x0) * zr, (q[1] / Z - y0) * zr)  # noqa: E731
        for st in strokes:                                   # tinta de la capa
            dr.line([tf(q) for q in st], fill=(40, 40, 40, 255), width=max(1, int(zr * 0.8)))
        w = max(2, int(zr * 1.3))
        for d, pl in zip(drawn, pls):                        # lo reconocido
            c = (90, 90, 90, 170) if pl.abandoned else col + (150,)
            dr.line([tf(q) for q in d], fill=c, width=w)
            for q in pl.pts_pdf:
                x, y = tf(q); r = max(1.5, zr * 0.9)
                dr.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,))
            for q in (d[0], d[-1]):
                x, y = tf(q); r = max(3, zr * 2.2)
                dr.ellipse([x - r, y - r, x + r, y + r], outline=(0, 0, 0, 255), width=max(1, int(zr / 2)))
        for m in marks:
            x, y = tf((m["pt"][0] * Z, m["pt"][1] * Z)); r = max(9, zr * 7)
            dr.ellipse([x - r, y - r, x + r, y + r], outline=PROB[m["tipo"]][0] + (255,), width=max(2, int(zr)))
        path = os.path.join(folder, name)
        img.save(path, quality=82)
        return os.path.relpath(path, outdir).replace("\\", "/")

    m = 25.0
    box = (max(0, min(xs) - m), max(0, min(ys) - m), min(page.rect.width, max(xs) + m),
           min(page.rect.height, max(ys) + m))
    zr = min(1.6, 2200.0 / max(box[2] - box[0], box[3] - box[1], 1.0))
    out = [draw(box, zr, f"{safe}_h{pno + 1:02d}.jpg", probs)]
    for k, pr in enumerate(probs[:15]):
        cx, cy = pr["pt"]
        pbox = (cx - 70, cy - 45, cx + 70, cy + 45)
        pr["imagen"] = draw(pbox, 4.0, f"{safe}_h{pno + 1:02d}_p{k + 1:02d}_{pr['tipo']}.jpg", [pr])
    return out


def main():
    import fitz, recognition as rec
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--hojas", default="")
    ap.add_argument("--util", default="")
    ap.add_argument("--salida", default="")
    ap.add_argument("--sin-imagenes", action="store_true")
    a = ap.parse_args()
    n = fitz.open(a.pdf).page_count
    pages = [int(x) - 1 for x in a.hojas.split(",") if x.strip()] or list(range(n))
    utils = [u.strip().upper() for u in a.util.split(",") if u.strip()] or list(rec.SUPPORTED_UTILITIES)
    outdir = a.salida or os.path.join(ROOT, "output", "prueba_capas")
    os.makedirs(outdir, exist_ok=True)
    jobs = [(a.pdf, p, u, outdir, not a.sin_imagenes) for u in utils for p in pages]
    with ProcessPoolExecutor(max(2, (os.cpu_count() or 4) - 1)) as ex:
        rows = [r for rs in ex.map(analyze, jobs) for r in rs]
    json.dump(rows, open(os.path.join(outdir, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    agg = defaultdict(lambda: defaultdict(float))
    for r in rows:
        g = agg[(r["util"], r["capa"])]
        g["hojas"] += 1 if r["rutas"] else 0
        for k in ("rutas", "largo_ft", "codos", "ab", "tinta_pt", "tinta_ok_pt", "v"):
            g[k] += r[k]
        for p in r["problemas"]:
            g[p["tipo"]] += 1
    tipos = ["tinta_sin_linea", "corte", "letra", "hueco", "punta_corta", "sin_tinta", "impreciso"]
    print(f"{'utilidad':14s} {'capa':34s} hojas rutas largo_ft codos AB  %tinta  " + " ".join(t[:9] for t in tipos) + "  V")
    for (u, c), g in sorted(agg.items()):
        pct = 100.0 * g["tinta_ok_pt"] / g["tinta_pt"] if g["tinta_pt"] else float("nan")
        print(f"{u:14s} {c[:34]:34s} {int(g['hojas']):5d} {int(g['rutas']):5d} {int(g['largo_ft']):8d} "
              f"{int(g['codos']):5d} {int(g['ab']):3d} {pct:6.1f}  "
              + " ".join(f"{int(g[t]):9d}" for t in tipos) + f"  {int(g['v'])}")


if __name__ == "__main__":
    main()
