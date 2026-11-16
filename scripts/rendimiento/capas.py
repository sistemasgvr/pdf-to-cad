"""Mide «Capas de la hoja» (`hoja/capas_trabajo.leer`, lo que el asistente corre en el proceso trabajador) y
guarda/compara su resultado (`docs/rendimiento/GUIA.md`).

    python scripts/rendimiento/capas.py hoja.pdf 0                      # hoja 0
    python scripts/rendimiento/capas.py hoja.pdf 0 --foto antes.json    # guarda capas, visibles y estilos sugeridos
    python scripts/rendimiento/capas.py hoja.pdf 0 --comparar antes.json
    python scripts/rendimiento/capas.py hoja.pdf 0 --perfil

Sale con código 1 si `--comparar` encuentra diferencias.
"""
from __future__ import annotations

import argparse
import sys

import comun


def _plano(v):
    return v if isinstance(v, (int, float, str, bool, type(None))) else repr(v)


def foto_de(res) -> dict:
    s = res.get("sugeridos")
    return {"layers": [{k: _plano(v) for k, v in sorted(capa.items())} for capa in res["layers"]],
            "visibles": sorted(res["visibles"]),
            "sugeridos": None if s is None else {k: _plano(v) for k, v in sorted(s.__dict__.items())}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("hoja", type=int, nargs="?", default=0)
    ap.add_argument("--foto"); ap.add_argument("--comparar"); ap.add_argument("--perfil", action="store_true")
    ap.add_argument("--filas", type=int, default=30)
    a = ap.parse_args()
    comun.preparar()
    from hoja import capas_trabajo

    def correr():
        return capas_trabajo.leer(a.pdf, a.hoja)
    if a.perfil:
        res, seg, filas = comun.perfilar(correr, a.filas)
    else:
        (res, seg), filas = comun.cronometro(correr), None
    print(f"capas de la hoja {a.hoja}: {seg:.2f} s · {len(res['layers'])} capas · {len(res['visibles'])} con algo visible"
          + ("  (con perfil)" if a.perfil else ""))
    if filas:
        comun.imprimir_perfil(filas)
    datos = foto_de(res)
    if a.foto:
        comun.guardar_foto(a.foto, datos)
    if a.comparar:
        sys.exit(1 if comun.comparar(a.comparar, datos) else 0)


if __name__ == "__main__":
    main()
