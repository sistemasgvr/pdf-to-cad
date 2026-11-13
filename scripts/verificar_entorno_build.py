"""¿El equipo que compila el instalador tiene el MISMO Python y las MISMAS bibliotecas que desarrollo?

Lo corre `1. build_all.bat` antes de PyInstaller. Lee `requirements-build.txt` (versiones exactas y la
línea `# python==X.Y`) y compara con lo instalado en el Python que va a compilar. Si algo no coincide,
lo dice con el comando para arreglarlo y sale con código 1: no se compila un .exe distinto del que se
probó (reporte 2026-11-13: el .exe del cliente traía Python 3.11.9 y otras bibliotecas; la composición
sugerida no encontraba nada y el reconocimiento cerraba el proceso, y en desarrollo andaba bien).

    python scripts/verificar_entorno_build.py
"""
from __future__ import annotations

import os
import re
import sys
from importlib import metadata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVO = os.path.join(RAIZ, "requirements-build.txt")


def leer(ruta=ARCHIVO):
    """(versión de Python pedida «X.Y» o None, {paquete: versión})."""
    python, paquetes = None, {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            s = linea.strip()
            m = re.match(r"#\s*python\s*==\s*([\d.]+)", s, re.I)
            if m:
                python = m.group(1)
                continue
            if not s or s.startswith("#"):
                continue
            m = re.match(r"([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)", s)
            if m:
                paquetes[m.group(1)] = m.group(2)
    return python, paquetes


def _norm(nombre):
    return re.sub(r"[-_.]+", "-", nombre).lower()


def revisar(python, paquetes, version_python=None, instalada=None):
    """Lista de problemas en palabras (vacia = todo coincide)."""
    version_python = version_python or "%d.%d.%d" % sys.version_info[:3]
    instalada = instalada or _instalada
    problemas = []
    if python and not (version_python == python or version_python.startswith(python + ".")):
        problemas.append(f"Python {version_python} - se necesita Python {python} "
                         f"(esta en {sys.executable})")
    for nombre, quiere in paquetes.items():
        tiene = instalada(nombre)
        if tiene is None:
            problemas.append(f"{nombre}: no esta instalado - se necesita {quiere}")
        elif tiene != quiere:
            problemas.append(f"{nombre} {tiene} - se necesita {quiere}")
    return problemas


def _instalada(nombre):
    try:
        return metadata.version(nombre)
    except metadata.PackageNotFoundError:
        n = _norm(nombre)
        for d in metadata.distributions():
            if _norm(d.metadata.get("Name") or "") == n:
                return d.version
        return None


def main():
    if not os.path.exists(ARCHIVO):
        print(f"[ERROR] No se encontro {ARCHIVO}.")
        return 1
    python, paquetes = leer()
    problemas = revisar(python, paquetes)
    if not problemas:
        print(f"[OK] Entorno de compilacion igual al de desarrollo: Python {sys.version.split()[0]}, "
              f"{len(paquetes)} bibliotecas con la version exacta.")
        return 0
    print("[ERROR] El equipo que compila NO tiene las mismas versiones que desarrollo.")
    print("        El .exe saldria distinto del que se probo (asi fallo en el cliente). Diferencias:")
    for p in problemas:
        print("          - " + p)
    print()
    print("  Para arreglarlo (una vez):")
    if python:
        print(f"    py install {python}")
        print(f"    py -{python} -m venv .venv")
    print("    .venv\\Scripts\\activate")
    print("    python -m pip install -r requirements-build.txt")
    print("  y vuelve a correr '1. build_all.bat' desde esa consola.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
