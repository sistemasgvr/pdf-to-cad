"""Informe de una sesión del vigilante (`app/nucleo/vigilante.py`): dónde se fue el tiempo.

    python scripts/rendimiento/vigilante.py                      # la última sesión
    python scripts/rendimiento/vigilante.py <carpeta> -o informe.md
    python scripts/rendimiento/vigilante.py <despues> --comparar <antes>
    python scripts/rendimiento/vigilante.py --lista              # sesiones guardadas

Las sesiones están en %LOCALAPPDATA%/pdf-to-cad/rendimiento/<fecha>-<pid>/ (una por cada vez que se abre la app).
"""
import argparse
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_RAIZ, "app"))

from nucleo import vigilante_informe as VI  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta", nargs="?")
    ap.add_argument("--comparar", metavar="ANTES")
    ap.add_argument("-o", "--salida")
    ap.add_argument("--lista", action="store_true")
    a = ap.parse_args(argv)
    if a.lista:
        for s in VI.sesiones():
            print(s)
        return 0
    carpeta = a.carpeta or VI.ultima()
    if not carpeta or not os.path.isdir(carpeta):
        print("No hay sesiones del vigilante.", file=sys.stderr)
        return 1
    r = VI.resumir(VI.leer(carpeta))
    texto = VI.comparar(VI.resumir(VI.leer(a.comparar)), r) if a.comparar else VI.markdown(r)
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            f.write(texto)
        print(a.salida)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
