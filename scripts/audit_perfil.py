"""Auditoría «no inventar / precisión» de UN perfil de reconocimiento en los 4 PDFs de prueba.

Uso: python scripts/audit_perfil.py UTILIDAD [config] [salida.json]
  UTILIDAD: TELECOM | GAS | AGUA | ALCANTARILLADO | DRENAJE | ELECTRICO
  config: profile (las reglas que tiene recognition hoy) | none | drain | water | sewer | gas
          (las `GeomOptions` de ese perfil aplicadas a esta utilidad) | profile+regla[+regla…]
          (el perfil de hoy con reglas extra, p. ej. profile+precise_junctions)
Misma métrica que `audit_alcantarillado.py` (del que sale): por hoja, tramos, largo,
cobertura, sin cubrir, fuera de patrón, segmentos SIN TINTA (>6 pt fuera de bóveda
con <50 % de muestras a ≤2 pt; no cuentan los que llegan a la esquina C de un codo
`fillet`: el editor y el plugin los dibujan con su arco), vértices en «V» (<73°, no fillet), IMPRECISOS (p90 de
la distancia perpendicular a los guiones paralelos de su propia capa > 0.75 pt), AB,
codos.
"""
import sys, os, json, math
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT + '/app', ROOT]
from concurrent.futures import ProcessPoolExecutor
D = r'C:/Users/bernu/OneDrive/Documentos/docs prueba/'
PDFS = ['DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf',
        'DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf',
        '03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf',
        'Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf']
Z = 2.0


cfg_utility = [None]


def _opts(cfg):
    import recognition_geom as geom, recognition as rec, dataclasses
    if cfg.startswith("profile+"):                # el perfil de hoy + reglas extra
        extra = {k: True for k in cfg.split("+")[1:]}
        return dataclasses.replace(rec.UTILITY_GEOM_OPTIONS.get(cfg_utility[0], geom.GeomOptions()), **extra)
    if cfg == "none":
        return geom.GeomOptions()
    return {"drain": rec.UTILITY_GEOM_OPTIONS["DRENAJE"], "water": rec.UTILITY_GEOM_OPTIONS["AGUA"],
            "sewer": rec.UTILITY_GEOM_OPTIONS["ALCANTARILLADO"],
            "gas": rec.UTILITY_GEOM_OPTIONS["GAS"]}.get(cfg)


def run(job):
    U, cfg, pdf, pno = job
    cfg_utility[0] = U
    import fitz, recognition as rec
    o = _opts(cfg)
    if o is not None:
        rec.UTILITY_GEOM_OPTIONS[U] = o
    doc = fitz.open(D + pdf)
    res = rec.recognize_page(D + pdf, pno, utility=U, zoom=Z, doc=doc)
    out = {"pdf": pdf[:5], "h": pno + 1, "n": len(res.drawable)}
    if not res.drawable:
        return out
    page = doc[pno]
    lp, _vp, _c, _k = rec.gather_paths(page, lambda n: rec.classify_ocg(n, U), set(), None)
    px = lambda q: (q[0] * Z, q[1] * Z)  # noqa: E731
    by = {}
    for p_ in lp:
        by.setdefault(p_.get("layer") or "", []).append(p_)
    ink = []
    for v in by.values():
        ink += [(q[0], q[1]) for q in rec.ink_samples(rec.ink_strokes(v, px))]
    cell = 12.0
    grid = {}
    for q in ink:
        grid.setdefault((int(q[0] // cell), int(q[1] // cell)), []).append(q)

    def near(q, tol=2.0 * Z):
        cx, cy = int(q[0] // cell), int(q[1] // cell)
        return any(math.dist(q, i) <= tol for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                   for i in grid.get((cx + dx, cy + dy), ()))
    boxes = []
    for vg in (res.vaults_geo or []):
        if vg.get("corners"):
            xs = [c[0] for c in vg["corners"]]; ys = [c[1] for c in vg["corners"]]
            boxes.append((min(xs) - 3 * Z, min(ys) - 3 * Z, max(xs) + 3 * Z, max(ys) + 3 * Z))
        elif vg.get("center") and vg.get("width_ft"):
            c = vg["center"]; r = vg["width_ft"] / res.scale_ft_per_pt * Z / 2 + 3 * Z
            boxes.append((c[0] - r, c[1] - r, c[0] + r, c[1] + r))
    in_vault = lambda q: any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in boxes)  # noqa: E731
    # precisión: distancia de los puntos del tramo a los TRAZOS de la capa
    segs, seg_lay = [], []
    for lay_, v in by.items():
        for st in rec.ink_strokes(v, px):
            xs = [q[0] for q in st]; ys = [q[1] for q in st]
            if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) < 6.0 * Z:
                continue                                   # letra / marca del linetype
            nw = [(a, b) for a, b in zip(st, st[1:]) if math.dist(a, b) >= 3.0 * Z]   # guiones, no letras
            segs += nw; seg_lay += [lay_] * len(nw)
    sgrid = {}
    C2 = 8.0 * Z
    for k, (a, b) in enumerate(segs):
        for gx in range(int(min(a[0], b[0]) // C2), int(max(a[0], b[0]) // C2) + 1):
            for gy in range(int(min(a[1], b[1]) // C2), int(max(a[1], b[1]) // C2) + 1):
                sgrid.setdefault((gx, gy), []).append(k)

    def dseg(q, u=None, lay=None):
        best = 1e9
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in sgrid.get((int(q[0] // C2) + dx, int(q[1] // C2) + dy), ()):
                    if lay is not None and seg_lay[k] != lay:
                        continue
                    a, b = segs[k]
                    vx, vy = b[0] - a[0], b[1] - a[1]
                    if u is not None and abs(vx * u[1] - vy * u[0]) > 0.174 * math.hypot(vx, vy):
                        continue                               # no paralelo (letra, otra línea)
                    t = ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / (vx * vx + vy * vy)
                    if not (0.0 < t < 1.0):
                        continue                               # en un hueco: no es distancia perpendicular
                    best = min(best, math.dist(q, (a[0] + t * vx, a[1] + t * vy)))
        return best
    imprec = []
    noink, vees, length = [], 0, 0.0
    for pl in res.drawable:
        pts = pl.pts_pdf
        for si, (a, b) in enumerate(zip(pts, pts[1:])):
            L = math.dist(a, b); length += L / Z
            if "fillet" in (pl.kinds[si:si + 2] if pl.kinds else ()):
                continue        # tramo hasta la esquina C de un codo: se dibuja con su arco
            if L <= 6 * Z:
                continue
            n = max(2, int(L / (1.5 * Z)))
            samples = [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
            samples = [q for q in samples if not in_vault(q)]
            uu = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            ds = [dseg(q, uu, pl.layer_ocg) for q in samples[1:-1]]
            ds = sorted(x for x in ds if x <= 3.0 * Z)          # solo donde hay tinta a tiro
            if len(ds) >= 3 and ds[int(0.9 * (len(ds) - 1))] > 0.75 * Z:
                imprec.append([round(a[0] / Z, 1), round(a[1] / Z, 1), round(b[0] / Z, 1), round(b[1] / Z, 1),
                               round(ds[int(0.9 * (len(ds) - 1))] / Z, 2)])
            if len(samples) >= 3 and sum(near(q) for q in samples) < 0.5 * len(samples):
                noink.append([round(a[0] / Z, 1), round(a[1] / Z, 1), round(b[0] / Z, 1), round(b[1] / Z, 1)])
        for i in range(1, len(pts) - 1):
            if (pl.kinds[i] if i < len(pl.kinds) else "") == "fillet":
                continue
            u = (pts[i - 1][0] - pts[i][0], pts[i - 1][1] - pts[i][1])
            w = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            nu, nw = math.hypot(*u), math.hypot(*w)
            if nu > 1e-6 and nw > 1e-6:
                ang = math.degrees(math.acos(max(-1, min(1, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))))
                if ang < 73:
                    vees += 1
    out.update(len=round(length), cov=round(res.coverage, 4), unc=len(res.uncovered_px),
               off=len(res.offpattern_px), noink=noink, vees=vees, imprec=imprec,
               ab=sum(1 for p in res.drawable if p.abandoned),
               codos=sum(len(p.fillets or {}) for p in res.drawable),
               vaults=len(res.vault_pts), warn=res.warnings,
               vgeo=[[vg.get("shape"), vg.get("width_ft"), vg.get("length_ft"), vg.get("importable"),
                      (vg.get("layer") or "").split("|")[-1]] for vg in (res.vaults_geo or [])],
               pls=[[p.layer_ocg.split("|")[-1], [[round(x / Z, 1), round(y / Z, 1)] for x, y in p.pts_pdf],
                     p.kinds, p.abandoned] for p in res.drawable])
    return out


if __name__ == "__main__":
    import fitz
    U = sys.argv[1].upper()
    cfg = sys.argv[2] if len(sys.argv) > 2 else "profile"
    outp = sys.argv[3] if len(sys.argv) > 3 else f"audit_{U.lower()}_{cfg}.json"
    jobs = [(U, cfg, p, i) for p in PDFS for i in range(fitz.open(D + p).page_count)]
    with ProcessPoolExecutor(max(2, os.cpu_count() - 1)) as ex:
        rows = list(ex.map(run, jobs))
    json.dump(rows, open(outp, "w"), ensure_ascii=False)
    act = [r for r in rows if r["n"]]
    print(U, cfg, "hojas con líneas:", len(act), "/", len(rows),
          "| tramos", sum(r["n"] for r in act), "| largo", sum(r["len"] for r in act),
          "| sin tinta", sum(len(r["noink"]) for r in act), "| V", sum(r["vees"] for r in act),
          "| sin cubrir", sum(r["unc"] for r in act), "| cov min", min((r["cov"] for r in act), default=None),
          "| AB", sum(r["ab"] for r in act), "| codos", sum(r["codos"] for r in act),
          "| IMPRECISOS", sum(len(r["imprec"]) for r in act))
