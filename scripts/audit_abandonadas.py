"""Auditoría del veredicto ABANDONADA (AB) por marcadores «/» y «//»: las 6 utilidades
en todas las hojas de los 4 PDFs de prueba.

Uso:
  python scripts/audit_abandonadas.py salida.json          foto de todas las rutas
  python scripts/audit_abandonadas.py --diff antes.json despues.json

Por ruta guarda capa, largo, extremos, periodo de la capa, marcadores (posición a lo
largo de la ruta, nº de barras: 2 = «//»), veredictos `verdict`/`double_verdict`, AB
final y aviso de «Revisar». El diff lista las rutas que cambian de AB o de aviso y
avisa si cambió alguna ruta (geometría). Correrlo antes y después de tocar
`marker_pattern` o el veredicto de `recognize_page` (~6 min con 11 procesos).
"""
import sys, os, json, math, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT + '/app', ROOT]
from concurrent.futures import ProcessPoolExecutor
D = r'C:/Users/bernu/OneDrive/Documentos/docs prueba/'
PDFS = ['DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf',
        'DU10 - APDU Seg B3 100_ Sewer DR_Verification.pdf',
        '03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf',
        'Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf']
UTILS = ["ELECTRICO", "DRENAJE", "AGUA", "ALCANTARILLADO", "GAS", "TELECOM"]


def run(job):
    pdf, pno = job
    import fitz, recognition as rec, recognition_geom as geom
    orig = geom.marker_pattern
    calls = []                                   # por capa: (rutas joined, raw)

    def wrap(pls, markers):
        mp = orig(pls, markers)
        calls.append((list(pls), mp, geom._marker_positions_n(pls, markers)))
        return mp
    geom.marker_pattern = wrap
    RP = rec.RecognizedPolyline
    pair_ocg = {}

    def mk(*a, **k):                             # capa de cada par de llamadas
        o = RP(*a, **k)
        pair_ocg.setdefault(len(calls) // 2 - 1, o.layer_ocg)
        return o
    rec.RecognizedPolyline = mk
    doc = fitz.open(D + pdf)
    out = []
    for U in UTILS:
        calls.clear(); pair_ocg.clear()
        dr = rec.recognize_page(D + pdf, pno, utility=U, zoom=1.0, doc=doc).drawable
        for ci in range(0, len(calls), 2):
            pls, mp, pos = calls[ci]
            ocg = pair_ocg.get(ci // 2)
            for i, pl in enumerate(pls):
                a, b = pl.pts[0], pl.pts[-1]
                fin = [p for p in dr if p.layer_ocg == ocg and math.dist(p.pts_pdf[0], a) < 1.5
                       and math.dist(p.pts_pdf[-1], b) < 1.5]
                if not fin:
                    continue
                p = fin[0]
                out.append(dict(pdf=pdf[:5], h=pno + 1, u=U, ocg=p.layer_ocg.split("|")[-1],
                                ocg_full=p.layer_ocg, L=round(pl.length, 1),
                                a=[round(a[0], 1), round(a[1], 1)], b=[round(b[0], 1), round(b[1], 1)],
                                per=round(mp.period, 1) if mp.period else None,
                                marks=[[round(t, 1), n] for t, n in pos[i]], v=mp.verdict[i],
                                dv=mp.double_verdict[i] if i < len(mp.double_verdict) else None,
                                ab=p.abandoned, review=p.review, nv=len(p.pts_pdf)))
    return out


def diff(fa, fb):
    key = lambda r: (r["pdf"], r["h"], r["u"], r["ocg_full"], tuple(r["a"]), tuple(r["b"]))  # noqa: E731
    ma = {key(r): r for r in json.load(open(fa))}
    mb = {key(r): r for r in json.load(open(fb))}
    print("rutas solo antes:", len(set(ma) - set(mb)), "| solo después:", len(set(mb) - set(ma)))
    n = collections.Counter()
    for k in sorted(set(ma) & set(mb)):
        r, s = ma[k], mb[k]
        if r["ab"] != s["ab"] or r["review"] != s["review"]:
            n[(r["u"], "AB" if s["ab"] else "activa") if r["ab"] != s["ab"] else (r["u"], "aviso")] += 1
            print("AB " if s["ab"] and not r["ab"] else "ACT" if r["ab"] != s["ab"] else "AVI",
                  r["pdf"], "h.%d" % r["h"], r["u"], r["ocg"], r["L"], r["a"], r["b"],
                  "barras", [m[1] for m in r["marks"]], "aviso", repr(r["review"]), "->", repr(s["review"]))
    print(dict(n))


if __name__ == "__main__":
    if sys.argv[1] == "--diff":
        diff(sys.argv[2], sys.argv[3])
        sys.exit(0)
    import fitz
    jobs = [(p, i) for p in PDFS for i in range(fitz.open(D + p).page_count)]
    with ProcessPoolExecutor(max(2, os.cpu_count() - 1)) as ex:
        rows = [r for lst in ex.map(run, jobs) for r in lst]
    json.dump(rows, open(sys.argv[1], "w"), ensure_ascii=False)
    print("rutas", len(rows), "| AB", sum(r["ab"] for r in rows))
