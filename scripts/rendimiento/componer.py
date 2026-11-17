"""Mide la COMPOSICIÓN: analizar los PDF (composición sugerida), armar y materializar la hoja compuesta.

    python scripts/rendimiento/componer.py a.pdf [b.pdf …]                 # tiempos por etapa
    python scripts/rendimiento/componer.py a.pdf --perfil                  # dónde se va el tiempo
    python scripts/rendimiento/componer.py a.pdf --foto antes.json         # guarda la composición
    python scripts/rendimiento/componer.py a.pdf --comparar antes.json     # 0 diferencias = misma composición
    python scripts/rendimiento/componer.py a.pdf --pdf salida.pdf          # deja la hoja compuesta (para reconocerla)

Las MISMAS funciones que usa la app: `composicion_trabajo.calcular` (fichas + uniones + armar) y
`composite_trabajo.materializar` (puentes + PDF de una hoja). Se materializa el grupo más grande.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time

import comun


def foto_de(resultado, pdf_bytes, layout) -> dict:
    grupos = []
    for g in resultado.analisis.grupos:
        comp = getattr(g, "composite", None)
        d = comp.to_dict() if comp is not None else {}
        d.pop("last_view", None)
        grupos.append({"tipo": getattr(g, "tipo", ""), "hojas": sorted(list(map(list, g.nodos))),
                       "composite": _redondo(d)})
    return {"grupos": grupos, "layout": _redondo(layout),
            "paginas_pdf": 1 if pdf_bytes else 0}


def _redondo(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {str(k): _redondo(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_redondo(x) for x in v]
    return v if isinstance(v, (int, str, bool, type(None))) else str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--paralelo", type=int, default=0, help="procesos para leer las hojas (0 = lo que decide la app)")
    ap.add_argument("--foto"); ap.add_argument("--comparar"); ap.add_argument("--pdf-salida", dest="salida")
    ap.add_argument("--perfil", action="store_true"); ap.add_argument("--filas", type=int, default=30)
    a = ap.parse_args()
    comun.preparar()
    from hoja import composicion_trabajo as CT
    from hoja import composite_trabajo as MT
    from ui.comun import proceso_hijo

    fuentes = []
    for ruta in a.pdf:
        with open(ruta, "rb") as f:
            fuentes.append({"name": os.path.basename(ruta), "data": f.read(), "path": os.path.abspath(ruta)})
    paralelo = a.paralelo or proceso_hijo.paralelos(4, 600)

    etapas, ultimo = [], [time.perf_counter(), "inicio"]

    def progreso(etapa, i=0, n=0):
        if etapa != ultimo[1]:
            ahora = time.perf_counter()
            etapas.append((ultimo[1], ahora - ultimo[0]))
            ultimo[0], ultimo[1] = ahora, etapa

    def analizar():
        r = CT.calcular(fuentes, progreso=progreso, paralelo=paralelo)
        progreso("fin")
        return r

    if a.perfil:
        res, seg, filas = comun.perfilar(analizar, a.filas)
    else:
        res, seg = comun.cronometro(analizar)
        filas = None
    print(f"\nanalizar {len(fuentes)} PDF ({paralelo} proceso(s)): {seg:.2f} s" + ("  (con perfil)" if a.perfil else ""))
    for nombre, d in etapas[1:]:
        print(f"    {d:7.2f} s  {nombre}")
    grupos = sorted(res.analisis.grupos, key=lambda g: -len(g.nodos)) if res is not None else []
    print(f"    grupos: {[len(g.nodos) for g in grupos]}")
    if filas:
        comun.imprimir_perfil(filas)

    datos, layout = b"", []
    comp = getattr(grupos[0], "composite", None) if grupos else None
    if comp is not None and len(comp.pieces) > 1:
        usadas = sorted({p.source for p in comp.pieces})
        d = comp.to_dict()
        for p in d["pieces"]:
            p["source"] = usadas.index(p["source"])

        def materializar():
            return MT.materializar(d, [fuentes[i]["data"] for i in usadas], {},
                                   [fuentes[i]["name"] for i in usadas])
        if a.perfil:
            (datos, layout), seg2, filas2 = comun.perfilar(materializar, a.filas)
        else:
            (datos, layout), seg2 = comun.cronometro(materializar)
            filas2 = None
        print(f"\nmaterializar {len(comp.pieces)} piezas: {seg2:.2f} s  ({len(datos) / 1e6:.1f} MB, "
              f"sha1 {hashlib.sha1(datos).hexdigest()[:10]})")
        if filas2:
            comun.imprimir_perfil(filas2)
        if a.salida:
            with open(a.salida, "wb") as f:
                f.write(datos)
            print("hoja compuesta en", a.salida)
    else:
        print("\nsin grupo de varias hojas que materializar")
    foto = foto_de(res, datos, layout) if res is not None else {}
    if a.foto:
        comun.guardar_foto(a.foto, foto)
    if a.comparar:
        sys.exit(1 if comun.comparar(a.comparar, foto) else 0)


if __name__ == "__main__":
    main()
