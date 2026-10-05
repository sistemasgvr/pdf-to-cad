"""Auditoría de CURVAS (codos) en las 6 utilidades × 4 PDFs de prueba.

Uso:
  python scripts/audit_curvas.py salida.json [PDF…] [--util U1,U2] [--pages 3,4] [--sin-tinta]
  python scripts/audit_curvas.py --diff antes.json despues.json
  python scripts/audit_curvas.py --list foto.json [--util U] [--pdf DU08]

Por hoja y utilidad (zoom de la app, 3.5):
- CODOS: esquina C, radio, A/B, giro, aproximado (`loose`), arco que muere en un nodo,
  RMS de la tinta y PRECISIÓN: desvío radial de la tinta CURVA de la capa dentro del
  sector del arco (p90 y máximo, pt) — el arco tiene que ir SOBRE el trazo del PDF.
- CURVAS QUE QUEDAN COMO POLILÍNEA: polilíneas con vértices `curve` sin codo y el
  motivo que dio `fit_fillets` (debug).
- TINTA CURVA SIN ARCO: trazos curvos de la capa (≥6 pt, suaves, giran ≥2°) que están
  SOBRE una línea reconocida (≤2 pt) pero lejos (>1.5 pt) de todo arco: curva del
  plano que no se reconoció como codo. Se agrupan por cercanía (una curva = un grupo).
- FOTO de la geometría (vértices y tipos) para `--diff`: fuera de los codos no debe
  cambiar nada; el diff separa los cambios «explicados» por un codo nuevo/quitado de
  los que no.
"""
import sys, os, json, math, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT + '/app', ROOT]
from concurrent.futures import ProcessPoolExecutor

D = r'C:/Users/bernu/OneDrive/Documentos/docs prueba/'
PDFS = {'DU06': 'DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf',
        'DU10': 'DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf',
        'DU08': '03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf',
        'LABOE': 'Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf'}
Z = 3.5
UTILS = ("ELECTRICO", "DRENAJE", "AGUA", "ALCANTARILLADO", "GAS", "TELECOM")


def _seg_d(q, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


def _turns(st):
    tot, mx = 0.0, 0.0
    for i in range(1, len(st) - 1):
        ux, uy = st[i][0] - st[i - 1][0], st[i][1] - st[i - 1][1]
        vx, vy = st[i + 1][0] - st[i][0], st[i + 1][1] - st[i][1]
        lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
        if lu < 1e-9 or lv < 1e-9:
            continue
        a = math.degrees(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))
        tot += a; mx = max(mx, abs(a))
    return tot, mx


def curved_stroke(st):
    """Trazo CURVO del plano (no letra, no guión recto): ≥6 pt de cuerda, ≥3
    puntos, suave (ningún vértice gira >35°), gira ≥2° en total y su flecha es
    ≥0.05 pt; no cerrado (anillo) ni en espiral (>200°)."""
    if len(st) < 3:
        return False
    L = math.dist(st[0], st[-1])
    if L < 6.0:
        return False
    tot, mx = _turns(st)
    if mx > 35.0 or abs(tot) < 2.0 or abs(tot) > 200.0:
        return False
    sag = max(_seg_d(q, st[0], st[-1]) for q in st[1:-1])
    return sag >= 0.05


class Grid:
    def __init__(self, cell):
        self.cell = cell; self.g = {}

    def add(self, key, a, b):
        c = self.cell
        for gx in range(int(min(a[0], b[0]) // c), int(max(a[0], b[0]) // c) + 1):
            for gy in range(int(min(a[1], b[1]) // c), int(max(a[1], b[1]) // c) + 1):
                self.g.setdefault((gx, gy), []).append(key)

    def near(self, q):
        c = self.cell
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out += self.g.get((int(q[0] // c) + dx, int(q[1] // c) + dy), ())
        return out


_CALLS = {}


def run(job):
    pdf, pno, utils, no_ink = job
    import warnings; warnings.filterwarnings("ignore")
    import fitz, recognition as rec
    if no_ink and not hasattr(rec, "_audit_no_ink"):
        # línea base: solo la 1.ª pasada (sin codos de la tinta ni reetiquetado)
        rec._audit_no_ink = True
        rec.arc_plan.ink_fillet_plan = lambda *a, **k: ([], {})
        rec.arcs_mod.relabel_false_curves = lambda pts, kinds, *a, **k: list(kinds)
    calls = _CALLS
    if not hasattr(rec, "_audit_orig_fit_fillets"):     # el proceso se reutiliza: envolver UNA vez
        rec._audit_orig_fit_fillets = rec.fit_fillets

        def wrap(pts, kinds, **kw):
            dbg = []
            kw.pop("debug", None)
            out = rec._audit_orig_fit_fillets(pts, kinds, debug=dbg, **kw)
            _CALLS[id(out[0])] = dbg
            return out
        rec.fit_fillets = wrap
    doc = fitz.open(D + PDFS[pdf])
    page = doc[pno]
    res_all = {}
    for U in utils:
        calls.clear()
        t0 = time.time()
        try:
            res = rec.recognize_page(D + PDFS[pdf], pno, utility=U, zoom=Z, doc=doc)
        except Exception as e:                       # noqa: BLE001
            res_all[U] = {"error": repr(e)}
            continue
        out = {"t": round(time.time() - t0, 2), "polys": [], "fillets": [], "residual": [], "missed": []}
        if not res.drawable:
            res_all[U] = out
            continue
        # tinta de la capa (pt), por capa: trozos de ARCO aplanado (misma detección
        # que la 2.ª pasada, `recognition_arcs.arc_pieces`)
        import recognition_arcs as ra
        lp, _vp = rec.utility_line_paths(page, U)        # por nombre y por las letras de sus líneas
        by = {}
        for p_ in lp:
            by.setdefault(p_.get("layer") or "", []).append(p_)
        pieces = {lay: ra.arc_pieces(rec.ink_strokes(v, lambda q: (q[0], q[1])), 1.0)[0] for lay, v in by.items()}
        # FORMA de cada polilínea (pt) con sus codos dibujados como arco: la tinta
        # de una curva vecina se mide contra SU arco, no contra la esquina C
        shapes, arcs = [], []                       # arcs: (k, i, layer, ctr, r, a0, sweep)
        for k, pl in enumerate(res.drawable):
            P = [(x / Z, y / Z) for x, y in pl.pts_pdf]
            sh = []
            for i, q in enumerate(P):
                f = (pl.fillets or {}).get(i)
                if f is None:
                    sh.append(("s", q)); continue
                ctr = (f["center"][0] / Z, f["center"][1] / Z); r = f["r_px"] / Z
                A = (f["a"][0] / Z, f["a"][1] / Z); B = (f["b"][0] / Z, f["b"][1] / Z)
                a0 = math.atan2(A[1] - ctr[1], A[0] - ctr[0]); a1 = math.atan2(B[1] - ctr[1], B[0] - ctr[0])
                sweep = (a1 - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
                arcs.append((k, i, pl.layer_ocg, ctr, r, a0, sweep))
                sh.append(("s", A))
                sh += [(("a", i), (ctr[0] + r * math.cos(a0 + sweep * t / 24), ctr[1] + r * math.sin(a0 + sweep * t / 24)))
                       for t in range(25)]
                sh.append(("s", B))
            shapes.append(sh)
        lay_grid = {}
        for k, pl in enumerate(res.drawable):
            g = lay_grid.setdefault(pl.layer_ocg, Grid(8.0))
            sh = shapes[k]
            for (ta, a), (tb, b) in zip(sh, sh[1:]):
                tag = ta if ta == tb else "s"
                g.add((k, tag, a, b), a, b)

        def d_other(q, lay, k, i):
            """Distancia a la forma de la capa SIN el arco (k, i)."""
            return min((_seg_d(q, a, b) for kk, tag, a, b in lay_grid[lay].near(q)
                        if not (kk == k and tag == ("a", i))), default=1e9)
        for k, pl in enumerate(res.drawable):
            pts = [(round(x / Z, 2), round(y / Z, 2)) for x, y in pl.pts_pdf]
            for (kk, i, lay, ctr, r, a0, sweep) in arcs:
                if kk != k:
                    continue
                f = pl.fillets[i]
                A = (f["a"][0] / Z, f["a"][1] / Z); B = (f["b"][0] / Z, f["b"][1] / Z)
                # precisión: tinta CURVA de la capa en el sector, a ≤3 pt del círculo,
                # cuyo objeto más cercano es este arco
                rad = []
                for pc in (p for p in pieces.get(lay, []) if p.r >= 4.0):   # sin letras (r < 4 pt)
                    for a, b in zip(pc.pts, pc.pts[1:]):
                        n = max(1, int(math.dist(a, b) / 0.5))
                        for t in range(n + 1):
                            q = (a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n)
                            ang = math.atan2(q[1] - ctr[1], q[0] - ctr[0])
                            da = (ang - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
                            if not (min(0, sweep) - 1e-6 <= da <= max(0, sweep) + 1e-6):
                                continue
                            d = abs(math.dist(q, ctr) - r)
                            if d <= 3.0 and d_other(q, lay, k, i) > d:
                                rad.append(d)
                rad.sort()
                out["fillets"].append({
                    "poly": k, "i": i, "layer": lay[-40:], "C": pts[i],
                    "r": round(r, 2), "r_ft": round(r * res.scale_ft_per_pt, 2),
                    "sweep": round(math.degrees(sweep), 1),
                    "A": [round(A[0], 2), round(A[1], 2)], "B": [round(B[0], 2), round(B[1], 2)],
                    "loose": bool(f.get("loose")), "node_a": bool(f.get("node_a")), "node_b": bool(f.get("node_b")),
                    "split": bool(f.get("split_a") or f.get("split_b")),
                    "dev": round(f.get("dev_px", 0.0) / Z, 2),
                    "ink_n": len(rad),
                    "p90": round(rad[int(0.9 * (len(rad) - 1))], 2) if rad else None,
                    "max": round(rad[-1], 2) if rad else None})
            out["polys"].append({"layer": pl.layer_ocg[-40:], "pts": pts, "kinds": list(pl.kinds)})
            if "curve" in (pl.kinds or []):
                cv = [pts[i] for i, kk in enumerate(pl.kinds) if kk == "curve"]
                xs = [q[0] for q in cv]; ys = [q[1] for q in cv]
                out["residual"].append({"poly": k, "layer": pl.layer_ocg[-40:],
                                        "bbox": [min(xs), min(ys), max(xs), max(ys)],
                                        "n_curve": len(cv),
                                        "why": sorted({("tinta: " + str(d[1])) if d[0] == "tinta" else str(d[2])
                                                       for d in calls.get(id(pl.pts_pdf), [])})})
        # tinta curva SIN arco: trozos de arco aplanado que corren sobre una línea
        # reconocida (≤2 pt de su forma) y que ningún codo dibuja (≥ la mitad de sus
        # puntos a ≤1.5 pt de un arco). Se agrupan por cercanía (una curva = un grupo).
        for lay, pcs in pieces.items():
            if lay not in lay_grid:
                continue
            arcs_l = [a for a in arcs if a[2] == lay]

            def on_arc(q):
                for (_k, _i, _l, ctr, r, a0, sweep) in arcs_l:
                    ang = math.atan2(q[1] - ctr[1], q[0] - ctr[0])
                    da = (ang - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
                    if min(0, sweep) - 0.05 <= da <= max(0, sweep) + 0.05 and abs(math.dist(q, ctr) - r) <= 1.5:
                        return True
                return False

            def on_line(q):
                return any(_seg_d(q, a, b) <= 2.0 for _k, _t, a, b in lay_grid[lay].near(q))
            miss = []
            for pc in pcs:
                P = pc.pts
                sw = abs(ra._sweep_deg(P, pc.cx, pc.cy))
                if math.dist(P[0], P[-1]) < 3.0 or sw < 1.0 or sw > 200.0 or pc.r < 4.0:
                    continue                         # astilla, letra chica o anillo de buzón: no decide
                if sum(on_line(q) for q in P) < 0.8 * len(P):
                    continue                         # letra / símbolo: no corre sobre la línea
                m = len(P) // 2
                tan = ra._unit(P[min(m + 1, len(P) - 1)][0] - P[max(m - 1, 0)][0],
                               P[min(m + 1, len(P) - 1)][1] - P[max(m - 1, 0)][1])
                segs = [(a, b) for _k, _t, a, b in lay_grid[lay].near(P[m]) if _seg_d(P[m], a, b) <= 2.0]
                if not any(abs(tan[0] * (b[0] - a[0]) + tan[1] * (b[1] - a[1])) >= math.cos(math.radians(30))
                           * math.dist(a, b) for a, b in segs if math.dist(a, b) > 1e-6):
                    continue                         # la cruza (letra «s», «W»…): no es la línea
                if sum(on_arc(q) for q in P) >= 0.5 * len(P):
                    continue
                miss.append(P)
            groups = []
            for P in miss:
                g = [P]
                for G in list(groups):
                    if any(min(math.dist(p, q) for p in (P[0], P[-1]) for q in (s[0], s[-1])) <= 12.0 for s in G):
                        g += G; groups.remove(G)
                groups.append(g)
            for G in groups:
                xs = [q[0] for s in G for q in s]; ys = [q[1] for s in G for q in s]
                turn = sum(_turns(s)[0] for s in G)
                out["missed"].append({"layer": lay[-40:], "bbox": [round(min(xs), 1), round(min(ys), 1),
                                                                   round(max(xs), 1), round(max(ys), 1)],
                                      "n": len(G), "turn": round(turn, 1),
                                      "len": round(sum(math.dist(a, b) for s in G for a, b in zip(s, s[1:])), 1)})
        res_all[U] = out
    return pdf, pno, res_all


def summarize(data, utils=UTILS):
    rows = {}
    for key, per in data.items():
        for U, o in per.items():
            if U not in utils or "error" in o:
                continue
            r = rows.setdefault(U, {"fil": 0, "loose": 0, "node": 0, "resid": 0, "missed": 0, "imprec": 0})
            r["fil"] += len(o["fillets"])
            r["loose"] += sum(1 for f in o["fillets"] if f["loose"])
            r["node"] += sum(1 for f in o["fillets"] if f["node_a"] or f["node_b"])
            r["resid"] += len(o["residual"])
            r["missed"] += len(o["missed"])
            r["imprec"] += sum(1 for f in o["fillets"] if f["p90"] is not None and f["p90"] > 0.5)
    print(f"{'utilidad':16s} codos aprox nodo  imprec(p90>0.5)  polilínea-curva  tinta-curva-sin-arco")
    for U in utils:
        r = rows.get(U)
        if r:
            print(f"{U:16s} {r['fil']:5d} {r['loose']:5d} {r['node']:4d}  {r['imprec']:15d}  {r['resid']:15d}  {r['missed']:20d}")


def _explained(q, fils, tol=3.0):
    for f in fils:
        xs = [f["A"][0], f["B"][0], f["C"][0]]; ys = [f["A"][1], f["B"][1], f["C"][1]]
        if min(xs) - tol <= q[0] <= max(xs) + tol and min(ys) - tol <= q[1] <= max(ys) + tol:
            return True
    return False


def diff(a, b):
    tot = {"add": 0, "rem": 0, "chg": 0, "unexpl": 0}
    for key in sorted(set(a) | set(b)):
        pa, pb = a.get(key, {}), b.get(key, {})
        for U in UTILS:
            oa, ob = pa.get(U), pb.get(U)
            if not oa or not ob or "error" in oa or "error" in ob:
                continue
            fa = {(round(f["C"][0]), round(f["C"][1]), f["layer"]): f for f in oa["fillets"]}
            fb = {(round(f["C"][0]), round(f["C"][1]), f["layer"]): f for f in ob["fillets"]}

            def find(f, other):
                for g in other:
                    if g["layer"] == f["layer"] and math.dist(g["C"], f["C"]) <= 1.0:
                        return g
                return None
            add = [f for f in ob["fillets"] if not find(f, oa["fillets"])]
            rem = [f for f in oa["fillets"] if not find(f, ob["fillets"])]
            chg = []
            for f in ob["fillets"]:
                g = find(f, oa["fillets"])
                if g and (abs(g["r"] - f["r"]) > 0.02 * max(1.0, g["r"]) or math.dist(g["C"], f["C"]) > 0.2):
                    chg.append((g, f))
            # geometría fuera de los codos
            va = {(round(q[0], 1), round(q[1], 1)) for p in oa["polys"] for q in p["pts"]}
            vb = {(round(q[0], 1), round(q[1], 1)) for p in ob["polys"] for q in p["pts"]}
            fil_all = oa["fillets"] + ob["fillets"]
            unexpl = [q for q in (va ^ vb) if not _explained(q, fil_all)]
            if add or rem or chg or unexpl:
                print(f"== {key} {U}: +{len(add)} −{len(rem)} ~{len(chg)}  vértices sin explicar {len(unexpl)}"
                      f"  (polilínea-curva {len(oa['residual'])}→{len(ob['residual'])},"
                      f" tinta-sin-arco {len(oa['missed'])}→{len(ob['missed'])})")
                for f in add:
                    print(f"   + C={f['C']} r={f['r']}pt ({f['r_ft']} ft) giro={f['sweep']} loose={f['loose']}"
                          f" nodo={f['node_a'] or f['node_b']} p90={f['p90']} max={f['max']} {f['layer']}")
                for f in rem:
                    print(f"   − C={f['C']} r={f['r']}pt giro={f['sweep']} {f['layer']}")
                for g, f in chg:
                    print(f"   ~ C={g['C']}→{f['C']} r={g['r']}→{f['r']} p90={g['p90']}→{f['p90']}")
                for q in sorted(unexpl)[:8]:
                    print(f"   ? vértice {q}")
            tot["add"] += len(add); tot["rem"] += len(rem); tot["chg"] += len(chg); tot["unexpl"] += len(unexpl)
    print("TOTAL", tot)


def listing(data, utils, pdf=None):
    for key in sorted(data, key=lambda k: (k.split("#")[0], int(k.split("#")[1]))):
        if pdf and not key.startswith(pdf):
            continue
        for U, o in data[key].items():
            if U not in utils or "error" in o:
                continue
            for r in o["residual"]:
                print(f"{key:9s} {U:14s} POLILÍNEA bbox={r['bbox']} n={r['n_curve']} {r['layer']} {r['why']}")
            for m in o["missed"]:
                print(f"{key:9s} {U:14s} SIN-ARCO  bbox={m['bbox']} trazos={m['n']} giro={m['turn']} largo={m['len']}"
                      f" {m['layer']}")
            for f in o["fillets"]:
                if f["p90"] is not None and f["p90"] > 0.5:
                    print(f"{key:9s} {U:14s} IMPRECISO C={f['C']} r={f['r']} p90={f['p90']} max={f['max']}"
                          f" loose={f['loose']} {f['layer']}")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--diff":
        a = json.load(open(args[1], encoding="utf-8")); b = json.load(open(args[2], encoding="utf-8"))
        diff(a, b)
        print("ANTES"); summarize(a)
        print("DESPUÉS"); summarize(b)
        return
    utils = UTILS
    if "--util" in args:
        utils = tuple(args[args.index("--util") + 1].split(","))
    if args and args[0] == "--list":
        data = json.load(open(args[1], encoding="utf-8"))
        listing(data, utils, args[args.index("--pdf") + 1] if "--pdf" in args else None)
        return
    out = args[0]
    pdfs = [p for p in args[1:] if p in PDFS] or list(PDFS)
    pages = None
    if "--pages" in args:
        pages = {int(x) for x in args[args.index("--pages") + 1].split(",")}
    import fitz
    jobs = []
    for p in pdfs:
        n = fitz.open(D + PDFS[p]).page_count
        jobs += [(p, i, utils, "--sin-tinta" in args) for i in range(n) if pages is None or (i + 1) in pages]
    data = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as ex:
        for pdf, pno, res in ex.map(run, jobs):
            data[f"{pdf}#{pno + 1}"] = res
    json.dump(data, open(out, "w", encoding="utf-8"))
    print(f"{len(jobs)} hojas en {time.time() - t0:.0f} s")
    summarize(data, utils)


if __name__ == "__main__":
    main()
