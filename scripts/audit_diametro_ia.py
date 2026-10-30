"""Auditoría de la IA que sugiere el diámetro del plano (`ia/diametro_ia`) sobre DU06 con el modelo REAL.

Uso (desde la raíz):
    python scripts/audit_diametro_ia.py 3 4 10                 # hojas (índice) de DU06
    python scripts/audit_diametro_ia.py 3 --contar             # solo cuántas líneas se preguntarían
    python scripts/audit_diametro_ia.py 3 --modelo qwen3.5:latest --url http://localhost:11434 --pasadas 2
    python scripts/audit_diametro_ia.py 3 --salida out.json --verdad tests/escenarios/diametro_ia_du06.json

Por cada línea «dudoso»/«sin_dato» con rótulos cerca (`grosor["cerca"]`): ficha, imagen marcada, sugerencia y, si
hay VERDAD (revisada a la vista: {"hoja", "utilidad", "p0": [x, y], "diam_in": d|null}), si acertó. Resumen:
**sugerencias equivocadas mostradas** (objetivo 0), aciertos, null correctos y segundos por línea.
"""
import argparse
import base64
import json
import math
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(RAIZ, "app"), RAIZ]
os.environ.setdefault("PDFCAD_PROCESO", "0")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

DU06 = r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
UTILIDADES = ("DRENAJE", "AGUA", "ALCANTARILLADO", "GAS", "ELECTRICO", "TELECOM")


def lineas(pdf, hoja, **kw):
    """[(utilidad, polilínea)] con evidencia, de una hoja reconocida a zoom 1 (px = pt de la vista)."""
    from reconocimiento import recognition_trabajo as RT
    res = RT.reconocer_hoja(pdf, hoja, zoom=1.0, utilities=UTILIDADES, **kw)
    out = []
    for r in res:
        for pl in r.polylines:
            g = pl.grosor or {}
            if g.get("estado") in ("dudoso", "sin_dato") and g.get("cerca") and len(pl.pts_pdf) >= 2:
                out.append((r.utility, pl))
    return out, res


def compuesta(pdf, salida):
    """La composición sugerida MÁS GRANDE del PDF, como la arma la app (`composicion_sugerida.armar` +
    `composite.build_document` con puentes), guardada en `salida`. → (ruta, escala pies/pt, [(pdf, hoja) de origen])."""
    import fitz
    import vector_pipeline as VP
    from hoja import composicion_ficha as F, composicion_sugerida as G, composite as C
    doc = fitz.open(pdf)
    an = G.analizar([F.fichas(doc, 0)])
    g = max(an.grupos, key=lambda x: len(x.costuras))
    comp = G.armar(g, an, [doc], lambda d, h: VP.detect_scale(doc[h]), [os.path.basename(pdf)])
    built = C.build_document(comp, [doc], {}, C.compute_bridges(comp, [doc]))
    built.save(salida, deflate=True)
    built.close()
    origen = sorted({(pdf, pz.page) for pz in comp.pieces}, key=lambda x: x[1])
    print(f"compuesta: {len(comp.pieces)} hojas (índices {[h for _p, h in origen]})", flush=True)
    return salida, comp.target_scale(), origen


def _pipe(utilidad, pl):
    from nucleo import diametro_plano, xdata
    return {"layer": utilidad, "pts": [tuple(map(float, q)) for q in pl.pts_pdf], "diam": 12.0,
            "diam_plano": diametro_plano.de_grosor(pl.grosor), "xdata": xdata.make(pl.layer_ocg, None)}


def _verdad_de(verdad, hoja, utilidad, pts):
    for v in verdad:
        if v["hoja"] == hoja and v["utilidad"] == utilidad and math.dist(v["p0"], pts[0]) < 2.0:
            return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hojas", nargs="*", type=int)
    ap.add_argument("--compuesta", default="", help="ruta del PDF temporal: arma y mide la composición sugerida")
    ap.add_argument("--pdf", default=DU06)
    ap.add_argument("--contar", action="store_true")
    ap.add_argument("--modelo", default="qwen3.5:latest")
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--pasadas", type=int, default=2)
    ap.add_argument("--sin-imagen", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--salida", default="")
    ap.add_argument("--verdad", default="")
    ap.add_argument("--imagenes", default="", help="carpeta donde guardar el recorte de cada línea")
    a = ap.parse_args()

    import fitz
    from hoja import pdf_styles, recorte_diametro
    from ia import diametro_ia as DI, proveedor as P
    from nucleo import diametro_plano, normas_catalogo as nc
    from reconocimiento.recognition import utility_label
    cat = nc.nuevo()
    prov = P.crear({"proveedor": "ollama", "url": a.url, "modelo": a.modelo})
    verdad = json.load(open(a.verdad, encoding="utf-8")) if a.verdad and os.path.isfile(a.verdad) else []
    doc = fitz.open(a.pdf)
    filas, n = [], 0
    trabajos = [(a.pdf, hoja, {}, 20.0 / 72.0) for hoja in a.hojas]
    if a.compuesta:                             # la hoja compuesta: perfiles de las hojas de ORIGEN, como la app
        ruta, escala, origen = compuesta(a.pdf, a.compuesta)
        trabajos.append((ruta, 0, {"scale_ft_per_pt": escala, "perfiles_de": origen}, escala))
    for pdf, hoja, kw, ft_pt in trabajos:
        doc = fitz.open(pdf)
        with pdf_styles.lectura_unica(doc):
            ls, _res = lineas(pdf, hoja, **kw)
        print(f"hoja {hoja} de {os.path.basename(pdf)}: {len(ls)} líneas con rótulos cerca", flush=True)
        if a.contar:
            continue
        page = doc[hoja]
        for utilidad, pl in ls:
            if a.max and n >= a.max:
                break
            n += 1
            p = _pipe(utilidad, pl)
            permit = {e["id"]: diametro_plano.permitido(cat, p, e["diam_in"]) for e in p["diam_plano"]["cerca"]}
            largo = sum(math.dist(x, y) for x, y in zip(p["pts"], p["pts"][1:])) * ft_pt
            f = DI.ficha(p, utility_label(utilidad), permit, largo)
            orden = sorted(f["rotulos"], key=lambda e: not DI.elegible(e, f))      # = la ventana
            png = recorte_diametro.recorte(page, p["pts"], {e["id"]: tuple(e["caja"]) for e in orden},
                                           puntos=[tuple(q) for e in f["rotulos"] for q in e.get("puntas") or ()])
            if a.imagenes:
                os.makedirs(a.imagenes, exist_ok=True)
                with open(os.path.join(a.imagenes, f"h{hoja}_{n:03d}_{utilidad}.png"), "wb") as fh:
                    fh.write(png)
            img = None if a.sin_imagen else base64.b64encode(png).decode("ascii")
            t0 = time.perf_counter()
            try:
                s = DI.sugerir(prov, f, img, None, pasadas=a.pasadas)
            except P.ErrorIA as e:                   # p. ej. «token repeat limit»: esa línea queda sin respuesta
                print(f"  #{n} {utilidad:14s} IA sin respuesta: {e}", flush=True)
                continue
            seg = time.perf_counter() - t0
            v = _verdad_de(verdad, hoja, utilidad, p["pts"])
            ok = None if v is None else (s.diam_in == v["diam_in"] if s.diam_in else None)
            fila = {"hoja": hoja, "n": n, "utilidad": utilidad, "capa": pl.layer_ocg,
                    "p0": [round(c, 1) for c in p["pts"][0]], "estado": p["diam_plano"]["estado"],
                    "rotulos": [{k: e[k] for k in ("id", "texto", "diam_in", "util", "guia", "dist_pt", "es_de")}
                                for e in f["rotulos"]],
                    "sugerencia": s.a_dict(), "segundos": round(seg, 1),
                    "verdad": None if v is None else v["diam_in"], "acierta": ok}
            filas.append(fila)
            print(f"  #{n} {utilidad:14s} {pl.layer_ocg[-28:]:28s} → {s.diam_in!s:>5} {s.origen:11s} "
                  f"{s.rotulo or '-':3s} {seg:5.1f}s · {s.motivo[:70]}", flush=True)
    if a.contar:
        return 0
    mostradas = [f for f in filas if f["sugerencia"]["diam_in"]]
    con_verdad = [f for f in filas if f["verdad"] is not None or _verdad_de(verdad, f["hoja"], f["utilidad"], [f["p0"]])]
    mal = [f for f in mostradas if f["acierta"] is False]
    bien = [f for f in mostradas if f["acierta"] is True]
    null_ok = [f for f in filas if not f["sugerencia"]["diam_in"] and f["verdad"] is None and con_verdad]
    print(f"\nlíneas: {len(filas)} · sugerencias mostradas: {len(mostradas)} · con verdad: {len(con_verdad)}")
    print(f"EQUIVOCADAS MOSTRADAS: {len(mal)} · aciertos: {len(bien)} · null (sin verdad de diámetro): {len(null_ok)}")
    if filas:
        print(f"segundos por línea: {sum(f['segundos'] for f in filas) / len(filas):.1f}")
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as fh:
            json.dump(filas, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
