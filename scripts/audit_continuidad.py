"""Auditoría de CONTINUIDAD de rutas: líneas cortadas donde siguen de frente.

Uso: python scripts/audit_continuidad.py salida.json [UTILIDAD …]
     python scripts/audit_continuidad.py --diff antes.json despues.json

Por hoja y utilidad (4 PDFs de prueba, rutas unidas = lo que se importa) busca
extremos de rutas DISTINTAS de la misma capa y estado (AB) que coinciden (≤0.6 pt):
  - «d2»: solo dos extremos y ninguna otra línea de la capa pasa por ahí. Si el giro
    local (primer tramo de cada una, que en un codo es la tangente del arco) es
    ≤ 35°, la línea sigue de frente y quedó cortada → «corte».
  - «nodo»: tres o más extremos (o dos + una línea que pasa): pares con giro ≤ 10°
    que no quedaron unidos → «corte_nodo» (a revisar: puede ser un empate real;
    p. ej. un banco de ductos que se abre en dos ramales tangentes).
  - «hueco»: dos puntas libres («end») enfrentadas a < 40 pt (rumbo ±20°).
Guarda además la geometría (capa, vértices, kinds, codos) para comparar con --diff:
codos (esquina + radio) idénticos, rutas y largo total por hoja.
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
UTILS = ['ELECTRICO', 'DRENAJE', 'AGUA', 'ALCANTARILLADO', 'GAS', 'TELECOM']
NODE_TOL = 0.6
D2_MAX_DEG = 35.0
NODE_MAX_DEG = 10.0
GAP_MAX_PT = 40.0
GAP_DEG = 20.0


def _unit(dx, dy):
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-9 else (1.0, 0.0)


def _heading_in(pts, first):
    """Rumbo con el que la ruta LLEGA a su extremo (apunta hacia el nodo)."""
    if first:
        return _unit(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
    return _unit(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])


def _defl(h1, h2):
    dot = max(-1.0, min(1.0, -(h1[0] * h2[0] + h1[1] * h2[1])))
    return math.degrees(math.acos(dot))


def _passes(pl, q, tol=NODE_TOL):
    """La polilínea pasa por q por su INTERIOR (no por un extremo)."""
    pts = pl.pts_pdf
    if math.dist(pts[0], q) <= tol or math.dist(pts[-1], q) <= tol:
        return False
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L < 1e-9:
            continue
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        t = (q[0] - a[0]) * u[0] + (q[1] - a[1]) * u[1]
        if -tol <= t <= L + tol and abs((q[0] - a[0]) * u[1] - (q[1] - a[1]) * u[0]) <= tol:
            return True
    return False


def run(job):
    U, pdf, pno = job
    import recognition as rec
    res = rec.recognize_page(D + pdf, pno, utility=U, zoom=1.0)
    pls = [p for p in res.drawable if len(p.pts_pdf) >= 2]
    out = {"u": U, "pdf": pdf[:5], "h": pno + 1, "n": len(pls),
           "len": round(sum(math.dist(a, b) for p in pls for a, b in zip(p.pts_pdf, p.pts_pdf[1:])), 1),
           "fil": sorted([p.layer_ocg.split("|")[-1], round(p.pts_pdf[i][0], 2), round(p.pts_pdf[i][1], 2),
                          round(f["r_px"], 2), bool(f.get("loose"))]
                         for p in pls for i, f in p.fillets.items()),
           "cortes": [], "cortes_nodo": []}
    ends = []                                   # (idx, first?, punto)
    for k, p in enumerate(pls):
        ends.append((k, True, p.pts_pdf[0]))
        ends.append((k, False, p.pts_pdf[-1]))
    used = set()
    for n, (k, fi, q) in enumerate(ends):
        if n in used:
            continue
        grp = [m for m, (k2, fi2, q2) in enumerate(ends)
               if math.dist(q, q2) <= NODE_TOL and pls[k2].layer_ocg == pls[k].layer_ocg
               and pls[k2].abandoned == pls[k].abandoned]
        used.update(grp)
        if len(grp) < 2:
            continue
        thru = any(_passes(p, q) for j, p in enumerate(pls)
                   if p.layer_ocg == pls[k].layer_ocg and p.abandoned == pls[k].abandoned)
        heads = [(m, _heading_in(pls[ends[m][0]].pts_pdf, ends[m][1])) for m in grp]
        kinds = [pls[ends[m][0]].kinds[0 if ends[m][1] else -1] for m in grp]
        row = {"xy": [round(q[0], 1), round(q[1], 1)], "capa": pls[k].layer_ocg.split("|")[-1],
               "kinds": kinds, "grado": len(grp) + (1 if thru else 0)}
        if len(grp) == 2 and not thru:
            d = _defl(heads[0][1], heads[1][1])
            if ends[grp[0]][0] != ends[grp[1]][0] and d <= D2_MAX_DEG:
                out["cortes"].append(dict(row, giro=round(d, 1)))
        else:
            best = []
            for i in range(len(heads)):
                for j in range(i + 1, len(heads)):
                    if ends[heads[i][0]][0] == ends[heads[j][0]][0]:
                        continue
                    d = _defl(heads[i][1], heads[j][1])
                    if d <= NODE_MAX_DEG:
                        best.append(round(d, 1))
            if best:
                out["cortes_nodo"].append(dict(row, giros=sorted(best)))
    # huecos: dos puntas LIBRES («end») de rutas distintas, enfrentadas (el hueco va
    # en el rumbo de las dos, ±20°) a < 40 pt: una línea que quizá debió seguir
    out["huecos"] = []
    free = [(k, fi, q) for k, fi, q in ends if pls[k].kinds[0 if fi else -1] == "end"]
    for n, (k, fi, q) in enumerate(free):
        for k2, fi2, q2 in free[n + 1:]:
            d = math.dist(q, q2)
            if (k2 == k or not NODE_TOL < d < GAP_MAX_PT or pls[k2].layer_ocg != pls[k].layer_ocg
                    or pls[k2].abandoned != pls[k].abandoned):
                continue
            h1, h2 = _heading_in(pls[k].pts_pdf, fi), _heading_in(pls[k2].pts_pdf, fi2)
            g = _unit(q2[0] - q[0], q2[1] - q[1])
            c = math.cos(math.radians(GAP_DEG))
            if h1[0] * g[0] + h1[1] * g[1] >= c and -(h2[0] * g[0] + h2[1] * g[1]) >= c:
                out["huecos"].append({"xy": [round(q[0], 1), round(q[1], 1)], "a": [round(q2[0], 1), round(q2[1], 1)],
                                      "capa": pls[k].layer_ocg.split("|")[-1], "d": round(d, 1)})
    return out


def _key(r):
    return (r["u"], r["pdf"], r["h"])


def diff(a_path, b_path):
    A = {_key(r): r for r in json.load(open(a_path, encoding="utf-8"))}
    B = {_key(r): r for r in json.load(open(b_path, encoding="utf-8"))}
    tot = {"cortes": [0, 0], "cortes_nodo": [0, 0], "huecos": [0, 0], "n": [0, 0]}
    fil_changed = []
    for k in sorted(set(A) | set(B)):
        a, b = A.get(k), B.get(k)
        if not a or not b:
            print("solo en uno:", k)
            continue
        for f in ("cortes", "cortes_nodo", "huecos"):
            tot[f][0] += len(a.get(f, ())); tot[f][1] += len(b.get(f, ()))
        tot["n"][0] += a["n"]; tot["n"][1] += b["n"]
        if a["fil"] != b["fil"]:
            fil_changed.append(k)
        if a["n"] != b["n"] or len(a["cortes"]) != len(b["cortes"]) or abs(a["len"] - b["len"]) > 0.5:
            print(k, "rutas", a["n"], "→", b["n"], "| cortes", len(a["cortes"]), "→", len(b["cortes"]),
                  "| largo", a["len"], "→", b["len"])
    print("TOTAL rutas", tot["n"], "| cortes d2", tot["cortes"], "| cortes en nodo", tot["cortes_nodo"],
          "| huecos", tot["huecos"])
    print("hojas con codos distintos:", len(fil_changed), fil_changed[:20])


if __name__ == "__main__":
    if sys.argv[1] == "--diff":
        diff(sys.argv[2], sys.argv[3])
        sys.exit()
    import fitz
    outp = sys.argv[1]
    utils = [u.upper() for u in sys.argv[2:]] or UTILS
    jobs = [(u, p, i) for u in utils for p in PDFS for i in range(fitz.open(D + p).page_count)]
    with ProcessPoolExecutor(max(2, os.cpu_count() - 1)) as ex:
        rows = list(ex.map(run, jobs, chunksize=1))
    json.dump(rows, open(outp, "w", encoding="utf-8"), ensure_ascii=False)
    for u in utils:
        rs = [r for r in rows if r["u"] == u]
        print(u, "rutas", sum(r["n"] for r in rs), "| cortes d2", sum(len(r["cortes"]) for r in rs),
              "| cortes en nodo", sum(len(r["cortes_nodo"]) for r in rs), "| huecos", sum(len(r["huecos"]) for r in rs),
              "| codos", sum(len(r["fil"]) for r in rs))
