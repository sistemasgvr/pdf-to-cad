"""«Capas de la hoja»: la lectura para resaltar una capa va al proceso trabajador (reporte del usuario 2026-11-19:
elegir una capa de una compuesta de 36 mapas con la red en imagen congelaba la ventana minutos, sin aviso). Debe dar
las MISMAS listas que se leían en la ventana y poder viajar entre procesos."""
import glob
import os
import pickle

import pytest

from hoja import capas_trabajo, leyenda_estandar as le, leyenda_trazos, pdf_layers, pdf_styles

HOME = os.path.expanduser("~")
CASOS = [(glob.glob(os.path.join(HOME, "OneDrive", "Documentos", "docs prueba", "DU06*.pdf")), 3),
         (glob.glob(os.path.join(HOME, "OneDrive", "Documentos", "DOCS DE PRUEBA IND", "QS SD_Indian School_North.pdf")), 13)]


def _foto(lista):
    return pickle.dumps([(dict(o, items=[tuple(map(str, it)) for it in o.get("items") or ()]),
                          [tuple(map(str, it)) for it in s.get("items") or ()]) for o, s in lista])


@pytest.mark.parametrize("rutas,hoja", CASOS)
def test_misma_lectura_en_el_trabajador(rutas, hoja):
    if not rutas:
        pytest.skip("falta el PDF")
    import fitz
    ruta = rutas[0]
    with fitz.open(ruta) as doc:
        with pdf_styles.lectura_unica(doc):
            layers = pdf_layers.page_layers(doc, hoja)
            ons = pdf_layers.encendidas(doc)
            pdf_layers.set_hidden(doc, ())
            page = doc[hoja]
            names = {L["name"] for L in layers}
            quiere = le.capas_de_utilidad(layers)
            ventana = leyenda_trazos.trazos_visibles(page, lambda n: n in names or quiere(n))
    proceso = capas_trabajo.trazos(ruta, hoja, ons, (), True, layers)
    assert _foto(proceso) == _foto(ventana)
    pick = capas_trabajo.trazos(ruta, hoja, ons, (), False)
    assert pick and all(o.get("layer") for o, _s in pick)
    pickle.loads(pickle.dumps(pick))                      # viaja entre procesos
