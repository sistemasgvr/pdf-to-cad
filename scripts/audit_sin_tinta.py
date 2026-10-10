"""Auditoría «nada sin tinta»: lo que se DIBUJA de cada línea, punto por punto, contra su tinta.

Uso: python scripts/audit_sin_tinta.py salida.json [UTILIDAD …]
     python scripts/audit_sin_tinta.py --diff antes.json despues.json

Reporte del usuario (2026-10-09, DU06 h.10 y h.12): una línea estirada hasta una bóveda
sin tinta debajo y una vuelta en U hasta el borde de una caja. `audit_perfil.py` no los
veía: salta los tramos que tocan la esquina de un codo y mira si la MITAD del tramo
tiene tinta. Aquí, en los 4 PDFs de prueba (rutas unidas = lo que se importa):
  · «hueco»: el tramo CONTINUO más largo sin tinta de su utilidad a ≤ `NEAR_PT` (letras
    incluidas: son tinta del linetype), sobre lo que se dibuja de verdad: las rectas
    entre las tangencias de los codos y el ARCO de cada codo. Fuera de las bóvedas
    (+3 pt, donde la línea va al nodo sin tinta). Se guarda todo hueco ≥ `MIN_GAP_PT`.
  · «retroceso»: dos rutas de la misma capa que salen del MISMO punto una encima de la
    otra (≤ `BACK_DEG`) en un vértice SUELTO (end/curve/bend/corner: la vuelta en U que
    `_split_sharp` parte en dos): la línea vuelve sobre sí misma. En un nodo (bóveda,
    T) dos líneas paralelas que llegan juntas son normales: van aparte («en nodo»).
Los huecos normales del linetype también salen: lo que importa es la comparación
(--diff): huecos y retrocesos nuevos o que desaparecen, por hoja y utilidad.
"""
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT + '/app', ROOT]
D = r'C:/Users/bernu/OneDrive/Documentos/docs prueba/'
PDFS = ['DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf',
        'DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf',
        '03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf',
        'Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf']
UTILS = ['ELECTRICO', 'DRENAJE', 'AGUA', 'ALCANTARILLADO', 'GAS', 'TELECOM']
Z = 2.0
NEAR_PT = 2.0         # tinta a esta distancia = hay tinta
STEP_PT = 0.5         # paso del muestreo
MIN_GAP_PT = 8.0      # huecos que se guardan
BACK_DEG = 20.0       # dos rutas que salen del mismo punto con menos que esto = retroceso
SHARED_PT = 0.6
NODE_KINDS = ("vault", "edge", "stop", "tee", "junction", "cut")


def _drawn(pl):
    """Lo que se dibuja de la polilínea: [(«recta»|«arco», muestras)]."""
    pts, fl = pl.pts_pdf, pl.fillets or {}
    out = []
    for k in range(len(pts) - 1):
        s = tuple(fl[k]["b"]) if k in fl else tuple(pts[k])
        e = tuple(fl[k + 1]["a"]) if k + 1 in fl else tuple(pts[k + 1])
        L = math.dist(s, e)
        n = max(1, int(L / (STEP_PT * Z)))
        out.append(("recta", [(s[0] + (e[0] - s[0]) * i / n, s[1] + (e[1] - s[1]) * i / n) for i in range(n + 1)]))
    for k, f in fl.items():
        c, r = f.get("center"), f.get("r_px")
        if not c or not r:
            continue
        a0 = math.atan2(f["a"][1] - c[1], f["a"][0] - c[0])
        a1 = math.atan2(f["b"][1] - c[1], f["b"][0] - c[0])
        sw = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        n = max(2, int(abs(sw) * r / (STEP_PT * Z)))
        out.append(("arco", [(c[0] + r * math.cos(a0 + sw * i / n), c[1] + r * math.sin(a0 + sw * i / n))
                             for i in range(n + 1)]))
    return out


def run(job):
    U, pdf, pno = job
    import fitz
    from reconocimiento import recognition as rec
    doc = fitz.open(D + pdf)
    res = rec.recognize_page(D + pdf, pno, utility=U, zoom=Z, doc=doc)
    out = {"pdf": pdf[:5], "h": pno + 1, "u": U, "n": len(res.drawable), "huecos": [], "retrocesos": [],
           "retrocesos_nodo": []}
    if not res.drawable:
        return out
    page = doc[pno]
    lp, _vp = rec.utility_line_paths(page, U)
    px = lambda q: (q[0] * Z, q[1] * Z)  # noqa: E731
    by = {}
    for p_ in lp:
        by.setdefault(p_.get("layer") or "", []).append(p_)
    cell = 6.0 * Z
    grid = {}
    for v in by.values():
        for q in rec.ink_samples(rec.ink_strokes(v, px)):
            grid.setdefault((int(q[0] // cell), int(q[1] // cell)), []).append((q[0], q[1]))
    tol = NEAR_PT * Z

    def inked(q):
        cx, cy = int(q[0] // cell), int(q[1] // cell)
        return any(math.dist(q, i) <= tol for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                   for i in grid.get((cx + dx, cy + dy), ()))
    boxes = []
    for vg in (res.vaults_geo or []):
        if vg.get("corners"):
            xs = [c[0] for c in vg["corners"]]; ys = [c[1] for c in vg["corners"]]
            boxes.append((min(xs) - 3 * Z, min(ys) - 3 * Z, max(xs) + 3 * Z, max(ys) + 3 * Z))
        elif vg.get("circle"):
            cx, cy, r = vg["circle"]
            boxes.append((cx - r - 3 * Z, cy - r - 3 * Z, cx + r + 3 * Z, cy + r + 3 * Z))
    in_vault = lambda q: any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in boxes)  # noqa: E731
    for pl in res.drawable:
        for tipo, smp in _drawn(pl):
            run_pts = []
            for q in smp + [None]:
                bad = q is not None and not in_vault(q) and not inked(q)
                if bad:
                    run_pts.append(q)
                    continue
                if len(run_pts) >= 2:
                    L = math.dist(run_pts[0], run_pts[-1]) / Z
                    if L >= MIN_GAP_PT:
                        out["huecos"].append([pl.layer_ocg.split("|")[-1], tipo, round(L, 1),
                                              [round(run_pts[0][0] / Z, 1), round(run_pts[0][1] / Z, 1)],
                                              [round(run_pts[-1][0] / Z, 1), round(run_pts[-1][1] / Z, 1)]])
                run_pts = []
    ends = []
    for i, pl in enumerate(res.drawable):
        p, k = pl.pts_pdf, pl.kinds or [""] * len(pl.pts_pdf)
        if len(p) >= 2:
            ends.append((i, pl.layer_ocg, p[0], p[1], k[0]))
            ends.append((i, pl.layer_ocg, p[-1], p[-2], k[-1]))
    for x in range(len(ends)):
        for y in range(x + 1, len(ends)):
            (i, la, a, a2, ka), (j, lb, b, b2, kb) = ends[x], ends[y]
            if i == j or la != lb or math.dist(a, b) > SHARED_PT * Z:
                continue
            u = (a2[0] - a[0], a2[1] - a[1]); w = (b2[0] - b[0], b2[1] - b[1])
            nu, nw = math.hypot(*u), math.hypot(*w)
            if nu < 1e-6 or nw < 1e-6:
                continue
            ang = math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))))
            if ang < BACK_DEG:
                nodo = ka in NODE_KINDS or kb in NODE_KINDS
                out["retrocesos_nodo" if nodo else "retrocesos"].append(
                    [la.split("|")[-1], round(ang, 1), [round(a[0] / Z, 1), round(a[1] / Z, 1)], ka, kb])
    return out


def _key(h):
    return (h[0], h[1], round(h[3][0] / 4), round(h[3][1] / 4), round(h[4][0] / 4), round(h[4][1] / 4))


def diff(a_path, b_path):
    A = {(r["pdf"], r["h"], r["u"]): r for r in json.load(open(a_path, encoding="utf-8"))}
    B = {(r["pdf"], r["h"], r["u"]): r for r in json.load(open(b_path, encoding="utf-8"))}
    for U in UTILS:
        nuevos, idos, rn, ri = [], [], [], []
        for key in sorted(set(A) | set(B)):
            if key[2] != U:
                continue
            ha = {_key(h): h for h in A.get(key, {}).get("huecos", [])}
            hb = {_key(h): h for h in B.get(key, {}).get("huecos", [])}
            nuevos += [(key[:2], hb[k]) for k in hb if k not in ha]
            idos += [(key[:2], ha[k]) for k in ha if k not in hb]
            ra = {tuple(r[2]) for r in A.get(key, {}).get("retrocesos", [])}
            rb = {tuple(r[2]) for r in B.get(key, {}).get("retrocesos", [])}
            rn += [(key[:2], r) for r in rb - ra]; ri += [(key[:2], r) for r in ra - rb]
        tot = lambda R: sum(len(r["huecos"]) for k, r in R.items() if k[2] == U)  # noqa: E731
        totr = lambda R: sum(len(r["retrocesos"]) for k, r in R.items() if k[2] == U)  # noqa: E731
        print(f"{U}: huecos {tot(A)} → {tot(B)} (nuevos {len(nuevos)}, quitados {len(idos)}) | "
              f"retrocesos {totr(A)} → {totr(B)}")
        for (pdf, h), g in sorted(nuevos, key=lambda t: -t[1][2])[:15]:
            print(f"   + {pdf} h.{h} {g}")
        for (pdf, h), g in sorted(idos, key=lambda t: -t[1][2])[:15]:
            print(f"   - {pdf} h.{h} {g}")
        for (pdf, h), r in rn:
            print(f"   + retroceso {pdf} h.{h} {r}")
        for (pdf, h), r in ri:
            print(f"   - retroceso {pdf} h.{h} {r}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "--diff":
        diff(sys.argv[2], sys.argv[3])
        sys.exit(0)
    import fitz
    utils = [u.upper() for u in sys.argv[2:]] or UTILS
    jobs = [(U, p, i) for U in utils for p in PDFS for i in range(fitz.open(D + p).page_count)]
    with ProcessPoolExecutor(max(2, os.cpu_count() - 1)) as ex:
        rows = list(ex.map(run, jobs))
    json.dump(rows, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
    for U in utils:
        R = [r for r in rows if r["u"] == U]
        hs = [h for r in R for h in r["huecos"]]
        print(f"{U}: huecos ≥{MIN_GAP_PT:g} pt {len(hs)} (≥15: {sum(h[2] >= 15 for h in hs)}, "
              f"≥30: {sum(h[2] >= 30 for h in hs)}) | retrocesos {sum(len(r['retrocesos']) for r in R)}"
              f" (en nodo {sum(len(r.get('retrocesos_nodo', [])) for r in R)})")
