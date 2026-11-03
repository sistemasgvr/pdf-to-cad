"""Correr con el MISMO entorno de Python que la app; no cambia ningún ajuste.

python scripts/diagnostico_hardware.py [--pdf plan.pdf --hoja 1] [--modo auto|cpu|opencl|cuda]
Mide el filtro numérico y, si se pide, una hoja real.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--hoja", type=int, default=1, help="Número de hoja (desde 1)")
    parser.add_argument("--modo", choices=("auto", "cpu", "opencl", "cuda"), default="auto")
    args = parser.parse_args()
    os.environ["PDFCAD_ACELERACION"] = args.modo
    logging.basicConfig(level=logging.INFO)
    from nucleo.hardware import recursos
    from hoja import recorte_lotes as R
    import numpy as np

    report = {"python": sys.version, "ejecutable": sys.executable,
              "hardware": recursos(), "modo": args.modo, "lote": R.tamano_lote()}
    boxes = np.tile([[1., 1., 2., 2.], [-20., 1., -10., 2.], [9., 9., 11., 11.]], (21845, 1))
    start = time.perf_counter()
    actual = R.clasificar(boxes, (0., 0., 10., 10.), (0., 0., 10., 10.), .25)
    elapsed = time.perf_counter() - start
    expected = R._calcular(np, boxes, (0., 0., 10., 10.), (0., 0., 10., 10.), .25)
    if not np.array_equal(expected, actual):
        raise RuntimeError("El filtro acelerado difiere del resultado CPU")
    report["filtro"] = {"elementos": len(boxes), "segundos_con_arranque": elapsed,
                        "backend": R._ultimo, "igual_a_cpu": True}
    # Solo en este diagnóstico: el trabajo normal con el PDF nunca espera a la medición.
    start = time.perf_counter()
    for pending in tuple(R._sondeos.values()):
        pending.result()
    report["calibracion_espera_segundos"] = time.perf_counter() - start
    start = time.perf_counter()
    warm = R.clasificar(boxes, (0., 0., 10., 10.), (0., 0., 10., 10.), .25)
    if not np.array_equal(expected, warm):
        raise RuntimeError("El filtro caliente difiere del resultado CPU")
    report["filtro_caliente"] = {"segundos": time.perf_counter() - start, "backend": R._ultimo}
    report["gpu_seleccionada"] = R._dispositivo
    report["rutas_gpu"] = [{"id": k, "tipo": b.kind, "dispositivo": b.name,
                            "validada": k in R._validados, "fallida": k in R._fallidos}
                           for k, b in (R._backends or {}).items()]
    if R._cuda is not None:
        report["cuda"] = {"version_cupy": R._cuda.__version__,
                          "disponible": not R._sin_cuda,
                          "gpu": R._cuda.cuda.runtime.getDeviceProperties(
                              R._cuda.cuda.runtime.getDevice())["name"].decode()}
    else:
        report["cuda"] = {"disponible": False, "nota": "No cargado o no disponible; véase registro"}
    if args.pdf:
        import fitz
        from hoja import leyenda_trazos as T, pdf_styles
        start = time.perf_counter()
        with fitz.open(args.pdf) as doc, pdf_styles.lectura_unica(doc):
            page = doc[args.hoja - 1]
            paths = pdf_styles.drawings(page, extended=True)
            read_time = time.perf_counter() - start
            start = time.perf_counter()
            visible = T.capas_visibles(page)
            clip_time = time.perf_counter() - start
        report["pdf"] = {"archivo": str(args.pdf.resolve()), "hoja": args.hoja,
                         "elementos": len(paths), "lectura_segundos": read_time,
                         "recorte_segundos": clip_time, "capas_visibles": sorted(visible)}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
