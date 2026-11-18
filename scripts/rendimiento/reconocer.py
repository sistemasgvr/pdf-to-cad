"""Mide el RECONOCIMIENTO de una hoja y guarda/compara su resultado (`docs/rendimiento/GUIA.md`).

    python scripts/rendimiento/reconocer.py plano.pdf 3                       # hoja 3 (desde 0), las 6 utilidades
    python scripts/rendimiento/reconocer.py plano.pdf 3 -u ELECTRICO DRENAJE   # solo esas
    python scripts/rendimiento/reconocer.py mapa.pdf 0 --sugerir               # hoja SIN capas: estilos deducidos
    python scripts/rendimiento/reconocer.py compuesta.pdf 0 --sugerir --textos-de origen.pdf   # hoja compuesta sin capas
    python scripts/rendimiento/reconocer.py plano.pdf 3 --foto antes.json      # guarda el resultado
    python scripts/rendimiento/reconocer.py plano.pdf 3 --comparar antes.json  # 0 diferencias = mismo resultado
    python scripts/rendimiento/reconocer.py plano.pdf 3 --perfil               # dónde se va el tiempo

Es la MISMA función que usa la app (`recognition_trabajo.reconocer_hoja`), aquí en este proceso.
Sale con código 1 si `--comparar` encuentra diferencias.
"""
from __future__ import annotations

import argparse
import sys
import time

import comun


def foto_de(results) -> dict:
    """Todo lo que la importación usa de cada utilidad, redondeado a 1e-6 (el redondeo de coma flotante de dos
    caminos equivalentes no cuenta; un vértice movido sí)."""
    def r(v):
        return round(float(v), 6)

    out = {}
    for res in results:
        lineas = []
        for pl in res.polylines:
            lineas.append({
                "capa": getattr(pl, "layer_ocg", None), "ab": bool(getattr(pl, "abandoned", False)),
                "pts": [[r(x), r(y)] for x, y in pl.pts_pdf], "tipos": list(pl.kinds),
                "diam": getattr(pl, "diam_in", None),
                "codos": {str(k): sorted((kk, r(vv) if isinstance(vv, (int, float)) and not isinstance(vv, bool) else str(vv))
                                         for kk, vv in v.items())
                          for k, v in sorted((getattr(pl, "fillets", None) or {}).items())},
                "grosor": {k: str(v) for k, v in sorted((getattr(pl, "grosor", None) or {}).items())
                           if k in ("estado", "diam_in", "fuente")},
            })
        out[str(getattr(res, "utility", len(out)))] = {
            "lineas": lineas,
            "bovedas": [{k: (r(v) if isinstance(v, float) else str(v)) for k, v in sorted(b.items())
                         if k in ("shape", "width_ft", "length_ft", "rot_deg", "layer", "importable", "orphan")}
                        for b in (getattr(res, "vaults_geo", None) or [])],
            "avisos": sorted(str(w) for w in (res.warnings or [])),
            "valvulas": len(getattr(res, "valvulas", None) or []),
            "anotaciones": len(getattr(res, "anotaciones", None) or []),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("hoja", type=int, nargs="?", default=0)
    ap.add_argument("-u", "--utilidades", nargs="*")
    ap.add_argument("--zoom", type=float, default=1.0)
    ap.add_argument("--sugerir", action="store_true", help="hoja sin capas: utilidad y estilos de `estilos_sugeridos`")
    ap.add_argument("--textos-de", help="con --sugerir en una hoja COMPUESTA: el PDF de origen (su cajetín dice la utilidad)")
    ap.add_argument("--foto"); ap.add_argument("--comparar"); ap.add_argument("--perfil", action="store_true")
    ap.add_argument("--filas", type=int, default=30)
    a = ap.parse_args()
    comun.preparar()
    import pymupdf as fitz
    from reconocimiento import recognition as rec
    from reconocimiento import recognition_trabajo as RT

    utilidades = tuple(a.utilidades) if a.utilidades else tuple(rec.SUPPORTED_UTILITIES)
    roles = {}
    if a.sugerir:
        from hoja import estilos_sugeridos as ES
        with fitz.open(a.pdf) as d:
            t0 = time.perf_counter()
            with fitz.open(a.textos_de or a.pdf) as origen:
                textos = ES.textos_de_documento(origen)
            s = ES.sugerir(d[a.hoja], textos=textos)
            print(f"sugerir estilos: {time.perf_counter() - t0:.2f} s → {s.motivo} {s.utilidad} {len(s.lineas)} estilo(s)")
        if not s.utilidad or not s.lineas:
            sys.exit("No se pudo deducir la utilidad o sus estilos: pasa otra hoja o asigna roles en la app.")
        utilidades = (s.utilidad,)
        roles = {s.utilidad: {rec.ROLE_LINEAS: list(s.lineas), rec.ROLE_BUZONES: []}}

    etapas, ultimo = [], [time.perf_counter(), "inicio"]

    def progreso(clave, *resto):
        if clave in ("utilidad", "hecha"):
            ahora = time.perf_counter()
            etapas.append((ultimo[1], ahora - ultimo[0]))
            ultimo[0], ultimo[1] = ahora, f"{clave} {resto[2] if len(resto) > 2 else ''}"

    def correr():
        return RT.reconocer_hoja(a.pdf, a.hoja, zoom=a.zoom, utilities=utilidades, roles_by_utility=roles,
                                 progreso=progreso)

    if a.perfil:
        res, seg, filas = comun.perfilar(correr, a.filas)
    else:
        res, seg = comun.cronometro(correr)
        filas = None
    results = res[0] if isinstance(res, tuple) else res
    print(f"\nreconocer hoja {a.hoja} de {a.pdf}: {seg:.2f} s" + ("  (con perfil)" if a.perfil else ""))
    for nombre, d in etapas:
        if d >= 0.05:
            print(f"    {d:7.2f} s  hasta «{nombre.strip()}»")
    for r in results:
        largo = sum(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 for pl in r.polylines
                    for (x0, y0), (x1, y1) in zip(pl.pts_pdf, pl.pts_pdf[1:]))
        print(f"    {getattr(r, 'utility', '?'):15s} {len(r.polylines):6d} líneas  {largo:12.0f} pt  "
              f"{len(getattr(r, 'vaults_geo', None) or []):5d} bóvedas  {len(r.warnings or []):3d} avisos")
    if filas:
        comun.imprimir_perfil(filas)
    datos = foto_de(results)
    if a.foto:
        comun.guardar_foto(a.foto, datos)
    if a.comparar:
        sys.exit(1 if comun.comparar(a.comparar, datos) else 0)


if __name__ == "__main__":
    main()
