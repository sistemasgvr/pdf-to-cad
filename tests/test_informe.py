"""Informe automático en Word (pedido del usuario 2026-10-23): fichas y zonas (puro), redacción con plantillas
(la IA, después: `docs/pendientes_ia.md`), el Word y el flujo en la ventana con su barra precisa."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import avance, informe_datos, informe_redaccion  # noqa: E402
from nucleo.conflictos import Conflicto  # noqa: E402
from nucleo.informe_datos import Opciones  # noqa: E402
from nucleo.normas_validar import Aviso  # noqa: E402

docx = pytest.importorskip("docx")

AQUI = os.path.dirname(os.path.abspath(__file__))
ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")
FT = 0.1                                  # pies por px


def _pipes():
    return [{"layer": "AGUA", "pts": [(0, 0), (5000, 0)], "diam": 8, "tipo": "DISTRIBUCION", "material": "PVC"},
            {"layer": "ALCANTARILLADO", "pts": [(100, -50), (100, 50)], "diam": 12},
            {"layer": "AGUA", "pts": [(4000, 0), (4000, 900)], "name": "Ramal"}]


def _datos():
    conflictos = [Conflicto("C-1", "cruce", 100.0, 0.0, "Cruce sin conexión entre dos utilidades.", [0, 1],
                            [101.0, 100.5]),
                  Conflicto("C-2", "codos", 4000.0, 10.0, "Dos codos demasiado juntos", [2])]
    avisos = [Aviso(4010.0, 400.0, "diametro", "Diámetro 6\" no permitido", pipe=2),
              Aviso(120.0, 5.0, "tipo", "Sin tipo", pipe=1),
              Aviso(130.0, 6.0, "nota", "Solo se permite en zonas residenciales", pipe=0, info=True),
              Aviso(4020.0, 410.0, "material", "Material no permitido", pipe=2,
                    aprobado={"usuario": "ana", "fecha": "2026-10-22", "nota": "lo pidió el cliente"})]
    return conflictos, avisos


def test_fichas_zonas_y_resumen():
    conflictos, avisos = _datos()
    inf = informe_datos.armar(conflictos, avisos, _pipes(), FT, Opciones())
    assert [f["id"] for f in inf.fichas][:2] == ["C-1", "C-2"]                 # conflictos primero
    assert all(f["clase"] != "tipo" for f in inf.fichas)                       # «sin tipo» solo se cuenta
    r = inf.resumen
    assert (r["conflictos"], r["avisos"], r["sin_tipo"]) == (2, 3, 1)
    assert (r["aprobados"], r["info"], r["avisos_pendientes"]) == (1, 1, 1)
    assert r["utilidades"] == 3
    # dos lugares a ~390 ft: dos zonas, numeradas de izquierda a derecha, con todas sus fichas
    assert len(inf.zonas) == 2 and [z.numero for z in inf.zonas] == [1, 2]
    assert {f["id"] for f in inf.zonas[0].fichas} == {"C-1", "N-1"}
    assert all(f["zona"] in (1, 2) for f in inf.fichas)
    for z in inf.zonas:                                                        # cada caja contiene sus fichas
        x0, y0, x1, y1 = z.caja
        assert all(x0 <= f["x"] <= x1 and y0 <= f["y"] <= y1 for f in z.fichas)
        assert (x1 - x0) / (y1 - y0) == pytest.approx(informe_datos.ASPECTO)
    u = inf.fichas[0]["utilidades"][0]
    assert (u["codigo"], u["diametro_in"], u["cota_ft"]) == ("AGUA-1", 8.0, 101.0)


def test_solo_conflictos_o_solo_normativas():
    conflictos, avisos = _datos()
    solo_c = informe_datos.armar(conflictos, avisos, _pipes(), FT, Opciones(normativas=False))
    assert {f["tipo"] for f in solo_c.fichas} == {"conflicto"} and solo_c.resumen["sin_tipo"] == 0
    solo_n = informe_datos.armar(conflictos, avisos, _pipes(), FT, Opciones(conflictos=False))
    assert {f["tipo"] for f in solo_n.fichas} == {"aviso"}


def test_la_celda_crece_si_hay_demasiadas_zonas():
    lista = [{"x": i * 2000.0, "y": 0.0} for i in range(100)]                  # 100 lugares a 200 ft
    zs = informe_datos.zonas(lista, FT, maximo=10)
    assert len(zs) <= 10 and sum(len(z.fichas) for z in zs) == 100


def test_plantilla_y_datos_para_la_ia():
    conflictos, avisos = _datos()
    inf = informe_datos.armar(conflictos, avisos, _pipes(), FT, Opciones())
    red, motivo = informe_redaccion.crear({"proveedor": "plantilla"})
    assert motivo == "" and red.nombre == "plantilla"
    f = {x["clase"]: x for x in inf.fichas}
    assert "Qué hacer:" in red.ficha(f["cruce"]) and "Qué hacer:" in red.ficha(f["diametro"])
    assert "AGUA-3 (Ramal):" in red.ficha(f["diametro"])
    assert "Aprobado por ana" in red.ficha(f["material"]) and "Qué hacer" not in red.ficha(f["material"])
    assert "Qué hacer" not in red.ficha(f["nota"])                             # informativo
    assert "Conflictos en el dibujo: 2." in red.resumen(inf)
    assert "Agua" in red.zona(inf.zonas[1])
    # proveedor que aún no existe → plantilla, con el motivo
    red2, motivo2 = informe_redaccion.crear({"proveedor": "ollama"})
    assert isinstance(red2, informe_redaccion.RedactorPlantilla) and "ollama" in motivo2
    d = json.loads(informe_redaccion.datos_para_ia(f["cruce"]))
    assert "x" not in d and "y" not in d and d["id"] == "C-1" and d["utilidades"][0]["codigo"] == "AGUA-1"


def _textos(ruta):
    d = docx.Document(ruta)
    return "\n".join(p.text for p in d.paragraphs), d


def test_word_se_escribe_y_avisa_su_avance(tmp_path, monkeypatch):
    from exportar import informe_word
    conflictos, avisos = _datos()
    inf = informe_datos.armar(conflictos, avisos, _pipes(), FT, Opciones(), titulo="Prueba")
    red, _ = informe_redaccion.crear()
    ruta = str(tmp_path / "inf.docx")
    vistos = []
    with avance.escuchar(lambda t, i, n: vistos.append(t)):
        informe_word.escribir(inf, red, ruta, {}, notas=["una nota"])
    texto, d = _textos(ruta)
    assert "Proyecto: Prueba" in texto and "una nota" in texto and "Zona 2" in texto and "C-1 · " in texto
    anexo = d.tables[-1]
    assert len(anexo.rows) == 1 + len(inf.fichas)
    assert {"informe_zonas", "informe_anexo", "informe_guardar"} <= set(vistos)
    # anexo con tope
    monkeypatch.setattr(informe_word, "ANEXO_MAX", 2)
    informe_word.escribir(inf, red, ruta, {})
    texto, d = _textos(ruta)
    assert len(d.tables[-1].rows) == 3 and "Se muestran 2 de 5" in texto


def test_informe_desde_la_ventana_con_capturas_2d_y_su_barra(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import barra_pesada
    from ui.ventana.app_window import Main
    vistos = []
    original = barra_pesada.AvancePesado._mostrar
    monkeypatch.setattr(barra_pesada.AvancePesado, "_mostrar",
                        lambda self, pump: vistos.append(self.barra.milesimas) or original(self, pump))
    w = Main()
    w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    w._resultados_al_dia()
    n_conf = len(w._conflictos)
    assert n_conf > 0
    ruta = str(tmp_path / "informe.docx")
    vistos.clear()
    assert w.generar_informe(ruta, Opciones(True, True, True, True)) == ruta
    texto, d = _textos(ruta)
    assert "no lleva capturas 3D" in texto                                   # sin pantalla no hay 3D
    imagenes = [r for r in d.part.rels.values() if "image" in r.reltype]
    zonas = texto.count("en el plano.")
    assert zonas >= 1 and len(imagenes) == zonas + 1                         # mapa + una 2D por zona
    assert vistos and vistos == sorted(vistos) and vistos[-1] == 1000
    w._dirty = False
