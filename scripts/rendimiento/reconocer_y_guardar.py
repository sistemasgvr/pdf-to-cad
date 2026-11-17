"""Auxiliar de `flujo_reconocer.py`: reconoce UNA utilidad de una hoja (zoom 3.5 como la ventana) y guarda el resultado
donde `importar.py` lo busca. Uso: reconocer_y_guardar.py hoja.pdf N UTILIDAD"""
import pickle
import sys
import time

import comun

pdf, hoja, util = sys.argv[1], int(sys.argv[2]), sys.argv[3]
comun.preparar()
from reconocimiento import recognition_trabajo as RT

t0 = time.perf_counter()
res = RT.reconocer_hoja(pdf, hoja, zoom=3.5, utilities=(util,), roles_by_utility={})
seg = time.perf_counter() - t0
resultados = res[0] if isinstance(res, tuple) else res
print(f"reconocer hoja {hoja} de {pdf}: {seg:.2f} s")
print(f"{sum(len(r.polylines) for r in resultados)} líneas")
with open(f"{pdf}.reconocido-{hoja}-3.5.pickle", "wb") as f:
    pickle.dump(res, f)
