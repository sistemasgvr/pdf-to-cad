"""Lo común de los medidores de rendimiento (`docs/rendimiento/GUIA.md`).

- `preparar()`: rutas del proyecto y ajustes APARTE (ningún medidor toca los ajustes reales de la app ni sus
  carpetas de recuperación, recientes o diagnósticos).
- `perfilar(fn)`: (resultado, segundos, filas del perfil) con solo las funciones del proyecto.
- `foto` / `comparar`: guardar un resultado como JSON y decir en qué se diferencia de otro (la prueba de
  «mismo resultado» de toda optimización).
"""
from __future__ import annotations

import cProfile
import json
import os
import pstats
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def preparar(con_qt: bool = False):
    """Antes de importar nada de la app."""
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")          # como `main.py`
    os.environ.setdefault("PDFCAD_SUGERENCIA", "0")
    os.environ.setdefault("PDFCAD_AREA_SUGERIDA", "0")
    for flujo in (sys.stdout, sys.stderr):                      # acentos legibles en cualquier consola
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    carpeta = tempfile.mkdtemp(prefix="pdfcad_medir")
    for clave, nombre in (("PDFCAD_RECUPERACION", "recuperacion"), ("PDFCAD_RECIENTES", "recientes.json"),
                          ("PDFCAD_DIAGNOSTICOS", "diagnosticos"), ("PDFCAD_CACHE_DIGITALIZADO", "digitalizado")):
        os.environ.setdefault(clave, os.path.join(carpeta, nombre))
    for p in (RAIZ, os.path.join(RAIZ, "app")):
        if p not in sys.path:
            sys.path.insert(0, p)
    if con_qt:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6 import QtCore
        original = QtCore.QSettings

        class AjustesAparte(original):                          # como `tests/conftest.py`
            def __init__(self, *args, **kw):
                if len(args) == 2 and all(isinstance(a, str) for a in args):
                    args = (original.IniFormat, original.UserScope) + args
                super().__init__(*args, **kw)

        original.setPath(original.IniFormat, original.UserScope, carpeta)
        QtCore.QSettings = AjustesAparte
    return carpeta


def perfilar(fn, filas: int = 25):
    """(resultado, segundos, [(acumulado s, propio s, llamadas, «archivo:línea función»)]) — solo código del
    proyecto, ordenado por tiempo acumulado. El perfil suma ~30–60 % al tiempo: comparar siempre perfil con
    perfil o cronómetro con cronómetro."""
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    try:
        res = fn()
    finally:
        pr.disable()
    seg = time.perf_counter() - t0
    st = pstats.Stats(pr)
    out = []
    for (archivo, linea, nombre), (_cc, nc, tt, ct, _callers) in st.stats.items():
        a = archivo.replace("\\", "/")
        if "/pdf-to-cad/" not in a or "/scripts/rendimiento/" in a:
            continue
        out.append((ct, tt, nc, f"{a.split('/pdf-to-cad/')[-1]}:{linea} {nombre}"))
    out.sort(reverse=True)
    return res, seg, out[:filas]


def imprimir_perfil(filas):
    print(f"    {'acum s':>8} {'propio s':>9} {'llamadas':>9}  función")
    for ct, tt, nc, donde in filas:
        print(f"    {ct:8.3f} {tt:9.3f} {nc:9d}  {donde}")


def cronometro(fn, veces: int = 1):
    """El mejor de `veces` (segundos) y el último resultado."""
    mejor, res = None, None
    for _ in range(max(1, veces)):
        t0 = time.perf_counter()
        res = fn()
        d = time.perf_counter() - t0
        mejor = d if mejor is None else min(mejor, d)
    return res, mejor


# ── «mismo resultado» ───────────────────────────────────────────────────────────────────────────
def guardar_foto(ruta: str, datos) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, sort_keys=True, indent=0)
    print("foto guardada:", ruta)


def comparar(ruta: str, datos, maximo: int = 20) -> int:
    """Diferencias entre la foto de `ruta` y `datos` (0 = idénticos). Las imprime con su ruta dentro del JSON."""
    with open(ruta, encoding="utf-8") as f:
        viejo = json.load(f)
    nuevo = json.loads(json.dumps(datos, ensure_ascii=False, sort_keys=True))
    difs = []

    def ver(a, b, donde):
        if len(difs) >= maximo:
            return
        if type(a) is not type(b):
            difs.append(f"{donde}: {a!r} → {b!r}")
        elif isinstance(a, dict):
            for k in sorted(set(a) | set(b)):
                if k not in a or k not in b:
                    difs.append(f"{donde}/{k}: {'falta antes' if k not in a else 'falta ahora'}")
                else:
                    ver(a[k], b[k], f"{donde}/{k}")
        elif isinstance(a, list):
            if len(a) != len(b):
                difs.append(f"{donde}: {len(a)} → {len(b)} elementos")
            for i, (x, y) in enumerate(zip(a, b)):
                ver(x, y, f"{donde}[{i}]")
        elif a != b:
            difs.append(f"{donde}: {a!r} → {b!r}")

    ver(viejo, nuevo, "")
    if difs:
        print(f"DISTINTO de {ruta} ({len(difs)}{'+' if len(difs) >= maximo else ''} diferencias):")
        for d in difs:
            print("   ", d[:200])
    else:
        print("IDÉNTICO a", ruta)
    return len(difs)
