"""Línea base de tiempos del flujo ACTUAL «abrir PDF(s) → asistente → editor» por etapas
(`docs/rendimiento/GUIA.md`; plan 2026-11-16 «reconocimiento desde el editor», Tarea 0).

    python scripts/rendimiento/flujo_reconocer.py a.pdf b.pdf … [--hoja N] [--agregar c.pdf d.pdf …] \
        [--salida tiempos.json] [--pausa-pdf plano.pdf]

Etapas (cada una = el medidor que ya existe, UNA a la vez, su salida a `<carpeta>/<etapa>.log`):
  componer   `componer.py` (composición sugerida + materializar la hoja compuesta)
  capas      `capas.py` (lo que corre «Capas de la hoja» en el trabajador)
  reconocer  reconocer SOLO la utilidad pedida (`--utilidad`; mapas Phoenix: estilos de su leyenda) a zoom 3.5
  importar   `importar.py` (ventana real offscreen: vista previa + importar + editor quieto)
Con `--agregar`: `calcar` (`hoja_calcada.calcar_trabajo`, en este proceso) y las mismas cuatro etapas sobre el
PDF nuevo (la importación se mide sola, sin combinarla con la hoja del editor).
Con `--pausa-pdf`: `flujo.py` (asistente real con un PDF; da la pausa máxima de la ventana y la barra quieta).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import comun

AQUI = os.path.dirname(os.path.abspath(__file__))


def correr(nombre, args, carpeta):
    """Un medidor como proceso aparte; devuelve (segundos de pared, texto de su salida)."""
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8")
    ruta = os.path.join(carpeta, nombre + ".log")
    t0 = time.perf_counter()
    with open(ruta, "w", encoding="utf-8") as f:
        subprocess.run([sys.executable, os.path.join(AQUI, args[0])] + args[1:], stdout=f, stderr=subprocess.STDOUT,
                       env=env, cwd=comun.RAIZ)
    seg = time.perf_counter() - t0
    with open(ruta, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    print(f"{nombre:28s} {seg:8.1f} s   ({ruta})", flush=True)
    return seg, txt


def cifra(txt, patron):
    m = re.search(patron, txt)
    return float(m.group(1)) if m else None


def cadena(etiqueta, pdfs, hoja, utilidad, carpeta, datos):
    """componer → capas → reconocer → importar de un juego de PDF."""
    compuesta = os.path.join(carpeta, etiqueta + "-compuesta.pdf")
    seg, txt = correr(etiqueta + "-componer", ["componer.py"] + pdfs + ["--pdf-salida", compuesta], carpeta)
    datos[etiqueta + "-componer"] = {"s": seg, "analizar": cifra(txt, r"analizar .*?: ([\d.]+) s"),
                                      "materializar": cifra(txt, r"materializar .*?: ([\d.]+) s")}
    if not os.path.isfile(compuesta):
        datos[etiqueta + "-componer"]["error"] = "no se materializó (ver log)"
        return None
    seg, txt = correr(etiqueta + "-capas", ["capas.py", compuesta, str(hoja)], carpeta)
    datos[etiqueta + "-capas"] = {"s": seg, "interno": cifra(txt, r"capas de la hoja \d+: ([\d.]+) s")}
    # reconocer: lo mismo que `reconocer.py -u UTIL --zoom 3.5` y además deja el resultado donde `importar.py` lo
    # espera (`<pdf>.reconocido-<hoja>-3.5.pickle`), para no reconocer dos veces
    seg, txt = correr(etiqueta + "-reconocer", ["reconocer_y_guardar.py", compuesta, str(hoja), utilidad], carpeta)
    datos[etiqueta + "-reconocer"] = {"s": seg, "interno": cifra(txt, r"reconocer hoja \d+ .*?: ([\d.]+) s"),
                                       "lineas": cifra(txt, r"(\d+) líneas")}
    seg, txt = correr(etiqueta + "-importar", ["importar.py", compuesta, str(hoja)], carpeta)
    datos[etiqueta + "-importar"] = {"s": seg, "importar": cifra(txt, r"(?m)^importar\s+([\d.]+) s"),
                                      "quieto": cifra(txt, r"editor quieto.*?([\d.]+) s"),
                                      "vista_previa": cifra(txt, r"vista previa.*?([\d.]+) s")}
    return compuesta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--agregar", nargs="*", default=[])
    ap.add_argument("--hoja", type=int, default=0)
    ap.add_argument("--utilidad", default="AGUA"); ap.add_argument("--utilidad-nueva", default="ALCANTARILLADO")
    ap.add_argument("--salida"); ap.add_argument("--carpeta")
    ap.add_argument("--pausa-pdf")
    a = ap.parse_args()
    carpeta = a.carpeta or tempfile.mkdtemp(prefix="pdfcad_flujo")
    os.makedirs(carpeta, exist_ok=True)
    pdfs = [os.path.abspath(p) for p in a.pdf]
    datos = {"pdfs": [os.path.basename(p) for p in pdfs]}
    cadena("base", pdfs, a.hoja, a.utilidad, carpeta, datos)
    if a.agregar:
        nuevos = [os.path.abspath(p) for p in a.agregar]
        comun.preparar()
        from hoja import composicion_trabajo as CT
        from hoja import hoja_calcada as HC
        from ui.comun import proceso_hijo
        fuentes = [{"name": os.path.basename(p), "data": open(p, "rb").read(), "path": p} for p in pdfs]
        res = CT.calcular(fuentes, progreso=lambda *x: None, paralelo=proceso_hijo.paralelos(4, 600))
        grupos = sorted(res.analisis.grupos, key=lambda g: -len(g.nodos))
        comp = grupos[0].composite
        usadas = sorted({p.source for p in comp.pieces})
        d = comp.to_dict()
        for p in d["pieces"]:
            p["source"] = usadas.index(p["source"])
        nuevas = [open(p, "rb").read() for p in nuevos]
        t0 = time.perf_counter()
        r = HC.calcar_trabajo(d, [fuentes[i]["data"] for i in usadas], nuevas, [os.path.basename(p) for p in nuevos],
                              float(comp.target_scale()),
                              [fuentes[i]["name"] for i in usadas])
        seg = time.perf_counter() - t0
        datos["agregar-calcar"] = {"s": seg, "ubicadas": len(r["ubicaciones"]), "sin_pareja": len(r["sin_pareja"])}
        print(f"{'agregar-calcar':28s} {seg:8.1f} s   ({len(r['ubicaciones'])} ubicadas, {len(r['sin_pareja'])} sin pareja)",
              flush=True)
        cadena("agregar", nuevos, a.hoja, a.utilidad_nueva, carpeta, datos)
    if a.pausa_pdf:
        seg, txt = correr("pausas-flujo", ["flujo.py", os.path.abspath(a.pausa_pdf)], carpeta)
        datos["pausas-flujo"] = {"s": seg, "resumen": (re.findall(r"RESUMEN:.*", txt) or [""])[-1]}
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
    print(json.dumps(datos, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
