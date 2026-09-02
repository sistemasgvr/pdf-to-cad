"""project_io.py — Serialización del proyecto (.digproj), separada de la UI.

Lógica PURA (sin Qt) de:
  - build_model_dict(win): lee el estado del proyecto (utilidades, buzones, georref,
    versión de Civil 3D, transformación de vista…) y arma el dict que se guarda como
    `model.json` dentro del .digproj.
  - parse_model(model): toma ese dict al abrir y devuelve los valores YA
    normalizados (castea las llaves de las cotas por vértice a int, envuelve las
    zonas de borrado antiguas, reconstruye el objeto Georef…), listos para que la
    ventana los asigne.

La ventana (`Main` en app_window.py) conserva TODO lo de Qt/PDF (guardar el PNG,
el zip, `set_image`, abrir el PDF, reponer combos), y solo delega aquí la parte de
datos. Así esta lógica —la que tenía los bugs sutiles de persistencia— es testeable
sin abrir la interfaz.
"""
import os

from model import VERSION
from geo import georef as georef_mod


def build_model_dict(win):
    """Arma el dict que se guarda como model.json. `win` es la ventana (o cualquier
    objeto con los mismos atributos). Lectura pura, sin efectos secundarios."""
    import civil_catalog as _cc
    return dict(
        pipes=win.pipes, leaders=win.leaders, text_marks=win.text_marks,
        erase_regions=win.erase_regions, structures=win.structures,
        ref_centerlines=win.ref_centerlines,
        georef=win.georef.to_dict(),
        work_unit=win.work_unit,                 # unidad de trabajo del proyecto
        # Versión/idioma de Civil 3D elegidos en el toolbar: se guardan para
        # reabrir el proyecto con la MISMA selección.
        civil_year=win.civil_year,
        civil_lang=_cc._current_lang,
        tf=dict(scale=win.scale, zoom=win.zoom, rot=win.rot, W=win.W, H=win.H,
                derot=[win.derot.a, win.derot.b, win.derot.c,
                       win.derot.d, win.derot.e, win.derot.f]),
        pdf_name=os.path.basename(win.pdf_path or ""), version=VERSION)


def parse_model(model):
    """Normaliza el dict leído del .digproj y devuelve un dict de valores listos
    para asignar en la ventana. NO toca Qt ni la ventana.

    Devuelve las llaves: scale, zoom, rot, W, H, derot (lista de 6), pipes,
    leaders, text_marks, erase_regions, structures, ref_centerlines, georef
    (objeto Georef), work_unit, civil_year, civil_lang."""
    tf = model["tf"]

    pipes = model.get("pipes", [])
    for p in pipes:
        # Tres diccionarios distintos guardan cotas por vertice:
        #   vertex_inv     — legado, cota unica por vertice
        #   vertex_inv_out — cota de SALIDA del vertice (start del segmento siguiente)
        #   vertex_inv_in  — cota de ENTRADA al vertice (end del segmento anterior)
        # json.dumps convierte SIEMPRE las llaves a str. Si no se re-castean a int
        # aca, los lookups por indice (que son int) fallan silenciosamente y la
        # edicion por tramo aparece vacia al reabrir el proyecto.
        for k in ("vertex_inv", "vertex_inv_out", "vertex_inv_in"):
            d = p.get(k)
            if isinstance(d, dict) and d:
                p[k] = {int(kk): float(vv) for kk, vv in d.items()}
        # Unidad de trabajo SIEMPRE pies (los diámetros van en pulgadas, por campo).
        p["unit"] = "ft"

    erase_regions = [r if isinstance(r, dict) else {"pts": r, "enabled": True}
                     for r in model.get("erase_regions", [])]

    return dict(
        scale=tf["scale"], zoom=tf["zoom"], rot=tf["rot"], W=tf["W"], H=tf["H"],
        derot=tf["derot"],
        pipes=pipes,
        leaders=model.get("leaders", []),
        text_marks=model.get("text_marks", []),
        erase_regions=erase_regions,
        structures=model.get("structures", []),          # retrocompat: proyectos viejos sin buzones
        ref_centerlines=model.get("ref_centerlines", []),  # retrocompat: sin centerlines
        georef=georef_mod.Georef.from_dict(model.get("georef")),  # retrocompat: sin georref → escala
        work_unit="ft",
        civil_year=model.get("civil_year"),
        civil_lang=model.get("civil_lang"),
    )
