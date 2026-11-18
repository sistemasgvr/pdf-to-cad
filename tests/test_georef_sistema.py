"""«Georreferenciar…» en cualquier sistema de coordenadas (2026-11-18, `geo/georef_sistema.py`): el diálogo abre en
el sistema de la georreferencia del proyecto (p. ej. la automática de Phoenix, EPSG 2868), muestra sus pares, ajusta
y guarda en ese sistema; en EPSG 2229 (Los Ángeles) todo sigue como antes."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(RAIZ, "app"), RAIZ):
    if p not in sys.path:
        sys.path.insert(0, p)

from geo import georef  # noqa: E402
from geo import georef_sistema as GS  # noqa: E402

# Tres anclas de la georreferencia automática de Sewer North (px del lienzo → EPSG 2868)
PARES = [((1000.0, 2000.0), (612641.41, 907683.92)), ((4000.0, 2050.0), (615100.0, 907700.0)),
         ((2500.0, 500.0), (613900.0, 909000.0))]


def test_funciones_puras():
    assert GS.sistema_de(None) == 2229
    g = georef.Georef([[0.8, 0, 600000], [0, -0.8, 910000], [0, 0, 1]], 2868, "similarity")
    assert GS.sistema_de(g) == 2868
    assert GS.mundo_de({"world": [1, 2]}) == (1.0, 2.0) and GS.mundo_de({"utm": [3, 4]}) == (3.0, 4.0)
    assert GS.mundo_de({"px": [0, 0]}) is None
    assert "Arizona Central" in GS.nombre(2868) and GS.nombre(4326) is None and GS.nombre(1) is None
    assert GS.cs_sugerido(2868) == "AZHP-CIF"
    assert GS.con_calles(2229) and not GS.con_calles(2868)
    assert GS.extension([(0, 0), (10, 20)], 5) == (-5, -5, 15, 25) and GS.extension([]) is None


class _Main:
    """Lo que el diálogo usa de la ventana."""
    def __init__(self, g):
        self.georef = g; self.project_path = "x.digproj"; self._dirty = False; self.pushes = 0

    def _push(self):
        self.pushes += 1

    def _update_geo_status(self):
        pass

    def _redraw(self):
        pass

    def save_project(self):
        pass


@pytest.fixture
def dialogo(monkeypatch):
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from geo import georef_dialog as GD
    monkeypatch.setattr(GD, "HAS_CTX", False)                 # sin teselas de internet en las pruebas
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    hechos = []

    def abrir(g):
        img = QtGui.QImage(500, 300, QtGui.QImage.Format_RGB32); img.fill(0xFFFFFF)
        # QDialog necesita un padre QWidget o None; el diálogo usa `self._main` para guardar
        dlg = GD.GeorefDialog(None, img, [], None, g)
        dlg._main = _Main(g)
        hechos.append(dlg)
        return dlg
    yield abrir
    for d in hechos:
        d._dialog_dirty = False
        d.close()


def _georef_2868():
    px = [p for p, _ in PARES]; mundo = [w for _, w in PARES]
    M, rms, _ = georef.fit(px, mundo, "similarity")
    pts = [{"px": list(p), "world": list(w), "label": "17-12"} for p, w in PARES]
    return georef.Georef([list(map(float, f)) for f in M], 2868, "similarity", rms, pts, "AZHP-CIF")


def test_abre_en_el_sistema_del_proyecto_con_sus_pares_y_guarda_en_el(dialogo):
    dlg = dialogo(_georef_2868())
    assert dlg.epsg == 2868 and dlg.ed_epsg.text() == "2868"
    assert len(dlg.pairs) == 3 and dlg._fetch_thread is None          # nada de NavigateLA
    assert dlg._extension is not None and dlg.ed_cs_code.text() == "AZHP-CIF"
    assert dlg.pasos is not None and dlg._zona_txt                     # paso 1 hecho: la zona está a la vista
    dlg._compute()
    dlg._save()
    assert dlg.result_georef.epsg == 2868 and dlg.result_georef.cs_code == "AZHP-CIF"
    assert dlg._main.georef is dlg.result_georef and dlg._main.pushes == 1


def test_puntos_viejos_con_clave_utm_tambien_se_cargan(dialogo):
    g = _georef_2868()
    g.points = [{"px": p["px"], "utm": p["world"]} for p in g.points]
    assert len(dialogo(g).pairs) == 3


def test_clic_en_el_mapa_sin_calles_da_el_punto_tal_cual(dialogo):
    dlg = dialogo(_georef_2868())
    dlg._on_pdf_click(100.0, 100.0)
    dlg._on_map_click(613000.25, 908000.5)
    assert dlg.pairs[-1]["world"] == (613000.25, 908000.5)


def test_cambiar_de_sistema(dialogo):
    dlg = dialogo(None)
    assert dlg.epsg == 2229 and dlg.ed_addr.placeholderText().startswith("Dirección")
    dlg.ed_epsg.setText("2868"); dlg._cambiar_sistema()
    assert dlg.epsg == 2868 and dlg.ed_cs_code.text() == "AZHP-CIF"
    dlg.ed_epsg.setText("4326"); dlg._cambiar_sistema()                # geográfico: no se acepta
    assert dlg.epsg == 2868 and dlg.ed_epsg.text() == "2868"
    con_pares = dialogo(_georef_2868())
    con_pares.ed_epsg.setText("2229"); con_pares._cambiar_sistema()     # con pares: no se cambia
    assert con_pares.epsg == 2868


def test_sin_zona_el_clic_en_el_mapa_no_inventa_un_punto(dialogo):
    dlg = dialogo(None)
    dlg.ed_epsg.setText("2868"); dlg._cambiar_sistema()
    dlg._on_pdf_click(10.0, 10.0)
    dlg._on_map_click(0.5, 0.5)
    assert dlg.pairs == []
