"""Autoprueba del EJECUTABLE (2026-11-11, pedido del usuario: «prevenir que todo funcione bien en el instalador»).

`Asistente C3D.exe --autoprueba salida.json` corre SIN abrir la ventana lo que solo puede fallar empaquetado y
escribe un informe JSON (código de salida 0 = todo bien, 1 = algo falla). Lo usa `scripts/verificar_instalador.py`
después de PyInstaller; en desarrollo `python app/main.py --autoprueba salida.json` da lo mismo y
`tests/test_instalador.py` lo corre.

Comprueba:
- cada módulo que se carga por NOMBRE (trabajos del proceso aparte, `hiddenimports` del spec) se importa;
- los datos que la app lee en ejecución: iconos, manual (es/en), entrenamiento de la IA de producción;
- un proceso hijo REAL (spawn, como `ui.comun.proceso`) arranca, importa esos módulos y responde: en el .exe el hijo
  vuelve a lanzar el propio programa y `freeze_support` lo desvía;
- dónde busca la app `PdfCadMcp.exe` (en el instalado va en `{app}/PdfCadMcp`; aquí solo se informa);
- las librerías de terceros que la app usa en ejecución (PySide6, fitz, numpy, ezdxf, docx, openpyxl, pyproj…).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time

# Los que se cargan por nombre (texto): PyInstaller no los ve si no van en `hiddenimports`.
MODULOS_POR_NOMBRE = (
    "hoja.area_sugerida", "hoja.capas_trabajo", "hoja.composicion_trabajo", "hoja.composite_trabajo",
    "hoja.hoja_calcada", "hoja.leyenda_trabajo", "hoja.planos_trabajo", "nucleo.modelo3d",
    "reconocimiento.recognition_trabajo", "ui.comun.fondo_trabajo", "ui.ventana.calculo_fondo",
)
# Lo que la ventana necesita para abrir y lo pesado de cada flujo (importarlos detecta un paquete que no viajó).
MODULOS_APP = (
    "ui.ventana.app_window", "exportar.dxf_export", "exportar.informe_word", "reconocimiento.recognition",
    "geo.georef_dialog", "ia.civil3d_agente", "ia.civil3d_mcp", "nucleo.normas_excel", "nucleo.tabla_excel",
    "digitize", "vector_pipeline", "raster_pipeline", "detect",
)
TERCEROS = ("PySide6.QtWidgets", "PySide6.QtOpenGLWidgets", "fitz", "numpy", "ezdxf", "docx", "openpyxl", "pyproj",
            "shiboken6")
# Terceros que solo usa una parte de la app (si faltan, esa parte avisa; no impiden abrir).
OPCIONALES = ("contextily", "rasterio", "mercantile", "cv2", "pytesseract", "PIL")


def _importar(nombre):
    try:
        importlib.import_module(nombre)
        return None
    except BaseException as e:                     # noqa: BLE001 (SystemExit de una librería también cuenta)
        return f"{type(e).__name__}: {e}"


def _en_hijo(modulos):
    """Lo que corre en el proceso hijo: importar y decir cuáles fallan."""
    return {m: err for m in modulos if (err := _importar(m))}


def _datos():
    """Archivos que la app lee en ejecución, por las MISMAS funciones que los buscan."""
    fallas = {}
    try:
        from ui.comun import icons
        base = icons._ICONS_DIR
        svgs = [f for f in os.listdir(os.path.join(base, "mdi"))] if os.path.isdir(os.path.join(base, "mdi")) else []
        if not any(f.endswith(".svg") for f in svgs):
            fallas["iconos"] = f"no hay iconos en {base}"
    except BaseException as e:                     # noqa: BLE001
        fallas["iconos"] = f"{type(e).__name__}: {e}"
    try:
        from traduccion import i18n
        for idioma in ("es", "en"):
            ruta = os.path.join(i18n._DOCS_DIR, f"manual.{idioma}.html")
            if not os.path.isfile(ruta) or os.path.getsize(ruta) < 200:
                fallas[f"manual.{idioma}"] = f"no encontrado en {i18n._DOCS_DIR}"
    except BaseException as e:                     # noqa: BLE001
        fallas["manual"] = f"{type(e).__name__}: {e}"
    try:
        from ia import memoria
        ruta = os.path.join(memoria._carpeta_programa(), "produccion.json")
        if not os.path.isfile(ruta):
            fallas["entrenamiento_ia"] = f"falta {ruta}"
    except BaseException as e:                     # noqa: BLE001
        fallas["entrenamiento_ia"] = f"{type(e).__name__}: {e}"
    return fallas


def _hijo(modulos, espera_s=90):
    """Un proceso hijo REAL, como los trabajadores de la app."""
    import multiprocessing as mp
    t0 = time.time()
    try:
        with mp.get_context("spawn").Pool(1) as pool:
            fallas = pool.apply_async(_en_hijo, (modulos,)).get(espera_s)
        return {"ok": not fallas, "fallas": fallas, "segundos": round(time.time() - t0, 1)}
    except BaseException as e:                     # noqa: BLE001
        return {"ok": False, "fallas": {"proceso": f"{type(e).__name__}: {e}"}, "segundos": round(time.time() - t0, 1)}


def correr(hijo=True):
    """El informe (dict). `ok` = todo lo obligatorio está bien."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")       # importar la ventana sin abrir nada
    inf = {"frozen": bool(getattr(sys, "frozen", False)), "ejecutable": sys.executable,
           "version": None, "modulos": {}, "terceros": {}, "opcionales": {}, "datos": {}, "hijo": None,
           "mcp": None}
    try:
        from nucleo import model
        inf["version"] = getattr(model, "VERSION", None)
    except BaseException as e:                     # noqa: BLE001
        inf["modulos"]["nucleo.model"] = f"{type(e).__name__}: {e}"
    for m in MODULOS_POR_NOMBRE + MODULOS_APP:
        if (err := _importar(m)):
            inf["modulos"][m] = err
    for m in TERCEROS:
        if (err := _importar(m)):
            inf["terceros"][m] = err
    for m in OPCIONALES:
        if (err := _importar(m)):
            inf["opcionales"][m] = err
    inf["datos"] = _datos()
    if hijo:
        inf["hijo"] = _hijo(MODULOS_POR_NOMBRE)
    try:
        from ia import civil3d_mcp
        ruta = civil3d_mcp.ruta_exe()
        inf["mcp"] = {"ruta": ruta, "encontrado": bool(ruta)}
    except BaseException as e:                     # noqa: BLE001
        inf["mcp"] = {"ruta": "", "encontrado": False, "error": f"{type(e).__name__}: {e}"}
    inf["ok"] = not (inf["modulos"] or inf["terceros"] or inf["datos"]
                     or (inf["hijo"] is not None and not inf["hijo"]["ok"]))
    return inf


def main(salida):
    """Punto de entrada de `--autoprueba`: escribe el informe y devuelve el código de salida."""
    try:
        inf = correr()
    except BaseException as e:                     # noqa: BLE001
        inf = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(inf, f, ensure_ascii=False, indent=2)
    return 0 if inf.get("ok") else 1
