"""Normativas de diseño: accesorios de presión (tipo + ángulo), motor de reglas,
guardado global / por proyecto y la ventana principal (etiquetas, barra de estado
y el puente de la ventana HTML, sin abrir el navegador)."""
import json
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import accesorios as A  # noqa: E402
import normativas as N  # noqa: E402

FT_PX = 0.5


def _p(pts, layer="AGUA", **k):
    return dict(layer=layer, pts=pts, name="", **k)


def _polar(o, ang_deg, largo):
    a = math.radians(ang_deg)
    return (o[0] + largo * math.cos(a), o[1] + largo * math.sin(a))


def _acc(pipes, z_at=None):
    return sorted((a["tipo"], round(a["angulo"], 2)) for a in A.accesorios(pipes, z_at, FT_PX))


# ─────────────────────────────── accesorios ───────────────────────────────

def test_codo_tee_wye_cruz_con_su_angulo():
    pipes = [
        _p([(0, 0), (100, 0), _polar((100, 0), 37, 100)]),                   # codo 37°
        _p([(0, 300), (200, 300)]), _p([(100, 300), (100, 400)]),              # tee 90° (punta a mitad)
        _p([(0, 600), (200, 600)]), _p([(100, 600), _polar((100, 600), 45, 90)]),  # wye 45°
        _p([(0, 900), (200, 900)]), _p([(100, 800), (100, 1000)]),             # cruce en X a mitad: NO
        _p([(0, 1200), (100, 1200), (200, 1200)]), _p([(100, 1100), (100, 1200), (100, 1300)]),  # cruz
    ]
    # codo = deflexión sobre el eje (2026-10-07): un giro de 37° da 37°
    assert _acc(pipes) == [("codo", 37.0), ("cruz", 90.0), ("tee", 90.0), ("wye", 45.0)]


def test_solo_redes_a_presion_y_union_recta_sin_accesorio():
    pipes = [_p([(0, 0), (100, 0), (100, 100)], "ELECTRICO"),
             _p([(0, 300), (100, 300), (100, 400)], "DRENAJE"),
             _p([(0, 600), (100, 600)]), _p([(100, 600), (200, 600.5)])]    # 0.3°: recta
    assert _acc(pipes) == []


def test_distinta_cota_no_se_une():
    pipes = [_p([(0, 0), (200, 0)]), _p([(100, 0), (100, 100)])]
    z = {0: 10.0, 1: 12.0}
    assert _acc(pipes, lambda i, k, x, y: z[i]) == []
    assert _acc(pipes, lambda i, k, x, y: 10.0) == [("tee", 90.0)]


def test_distinta_red_no_se_une():
    pipes = [_p([(0, 0), (200, 0)]), dict(_p([(100, 0), (100, 100)]), name="OTRA")]
    assert _acc(pipes) == []


def test_codos_seguidos_se_funden_como_en_el_plugin():
    # tramo de 0.27 ft entre dos giros de 45°: el plugin pone UN codo de 90°
    pipes = [_p([(0, 0), (100, 0), (100.4, 0.4), (100.4, 100)], diam=8)]
    r = A.accesorios(pipes, None, FT_PX)
    assert [(a["tipo"], round(a["angulo"])) for a in r] == [("codo", 90)] and r[0].get("fundido")


def test_texto_angulo():
    assert [A.texto_angulo(a) for a in (45, 11.25, 22.5, 89.999)] == ["45°", "11.25°", "22.5°", "90°"]


# ─────────────────────────────── motor ───────────────────────────────

def _reglas():
    return N.cargar_catalogo(os.path.join(os.path.dirname(__file__), "no_existe.json"))


def test_codo_fuera_de_norma_y_tolerancia():
    pipes = [_p([(0, 0), (100, 0), _polar((100, 0), 37, 100)]),           # deflexión 37°
             _p([(0, 300), (100, 300), _polar((100, 300), 45.8, 100)])]      # 45.8° ≤ ±1 de 45: cumple
    res = N.evaluar(_reglas(), {}, N.Contexto(pipes, None, None, FT_PX))
    codo = res["conex_codo"]
    assert codo.evaluados == 2 and len(codo.incumplimientos) == 1
    inc = codo.incumplimientos[0]
    assert round(inc.valor) == 37 and inc.esperado == 45.0 and "45°" in inc.mensaje


def test_desactivar_por_proyecto_y_utilidades():
    pipes = [_p([(0, 0), (100, 0), _polar((100, 0), 37, 100)], "GAS")]
    reglas = _reglas()
    assert N.evaluar(reglas, {"conex_codo": False}, N.Contexto(pipes, None, None, FT_PX))["conex_codo"].activa is False
    r = next(x for x in reglas if x["id"] == "conex_codo")
    assert N.aplicar_cambio(r, "utilidades", ["AGUA"]) is None
    assert N.evaluar(reglas, {}, N.Contexto(pipes, None, None, FT_PX))["conex_codo"].evaluados == 0


def test_validacion_de_cambios():
    r = next(x for x in _reglas() if x["id"] == "conex_codo")
    assert N.aplicar_cambio(r, "angulos", []) is not None
    assert N.aplicar_cambio(r, "angulos", [200]) is not None
    assert N.aplicar_cambio(r, "tolerancia", "x") is not None
    assert N.aplicar_cambio(r, "utilidades", []) is not None
    assert N.aplicar_cambio(r, "angulos", [45, 11.25, 45]) is None and r["params"]["angulos"] == [11.25, 45.0]
    assert N.aplicar_cambio(r, "obligatoria", False) is None and r["obligatoria"] is False


def test_guardado_global_solo_diferencias_y_restablecer(tmp_path):
    ruta = str(tmp_path / "n.json")
    reglas = N.cargar_catalogo(ruta)
    r = next(x for x in reglas if x["id"] == "conex_codo")
    N.aplicar_cambio(r, "angulos", [11.25, 22.5, 30, 45, 90])
    N.guardar_catalogo(reglas, ruta)
    datos = json.load(open(ruta, encoding="utf-8"))
    assert datos["version"] == 3
    assert datos["reglas"] == {"conex_codo": {"params": {"angulos": [11.25, 22.5, 30.0, 45.0, 90.0]}}}
    otra = N.cargar_catalogo(ruta)
    assert 30.0 in next(x for x in otra if x["id"] == "conex_codo")["params"]["angulos"]
    assert N.modificada(next(x for x in otra if x["id"] == "conex_codo"))
    N.restablecer(otra, "conex_codo")
    N.guardar_catalogo(otra, ruta)
    assert json.load(open(ruta, encoding="utf-8"))["reglas"] == {}


def test_catalogos_viejos_quedan_en_deflexion(tmp_path):
    # v1 guardaba GIROS (se quedan); v2 ángulos ENTRE tuberías (→ 180° − a)
    ruta = tmp_path / "v1.json"
    ruta.write_text(json.dumps({"version": 1, "reglas": {"conex_codo": {"params": {
        "angulos": [11.25, 22.5, 30.0, 45.0, 90.0]}}}}), encoding="utf-8")
    r = next(x for x in N.cargar_catalogo(str(ruta)) if x["id"] == "conex_codo")
    assert r["params"]["angulos"] == [11.25, 22.5, 30.0, 45.0, 90.0]
    ruta2 = tmp_path / "v2.json"
    ruta2.write_text(json.dumps({"version": 2, "reglas": {"conex_codo": {"params": {
        "angulos": [90.0, 135.0, 150.0, 157.5, 168.75]}}}}), encoding="utf-8")
    r = next(x for x in N.cargar_catalogo(str(ruta2)) if x["id"] == "conex_codo")
    assert r["params"]["angulos"] == [11.25, 22.5, 30.0, 45.0, 90.0]


def test_todo_tipo_de_regla_tiene_categoria_y_campos_editables():
    editables = {"grados_lista", "grados", "pies", "utilidades"}
    for tipo in N.TIPOS.values():
        assert tipo.categoria in N.CATEGORIAS
        assert all(c.tipo in editables for c in tipo.campos)
    assert all(r["tipo"] in N.TIPOS for r in N.REGLAS_BASE)


# ─────────────────────────────── ventana ───────────────────────────────

@pytest.fixture
def win(monkeypatch, tmp_path):
    from PySide6 import QtGui, QtWidgets
    import i18n
    import i18n_core
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setenv("PDFCAD_NORMATIVAS", str(tmp_path / "normativas.json"))
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from app_window import Main
    w = Main()
    w.normas = N.cargar_catalogo()
    img = QtGui.QImage(1500, 1500, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.pipes = [_p([(100, 100), (600, 100), (600, 600)]),
               _p([(100, 800), (600, 800), _polar((600, 800), 37, 400)])]
    w._refresh_lists(); w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo
    import gc; gc.collect()


def test_etiquetas_en_el_lienzo_y_barra_de_estado(win):
    import accesorios_view
    textos = sorted(it._texto for it in win._overlay if isinstance(it, accesorios_view.EtiquetaAccesorio))
    assert textos == ["Codo 37° ✗", "Codo 90°"]
    assert not win.btn_normas.isHidden() and "1" in win.btn_normas.text()
    win.act_show_acc.setChecked(False)
    assert not [it for it in win._overlay if isinstance(it, accesorios_view.EtiquetaAccesorio)]
    assert len(win._normas_lista) == 1                  # se sigue revisando aunque no se muestre
    win.act_show_acc.setChecked(True)


def test_puente_de_la_ventana(win):
    import normativas_dialog
    pu = normativas_dialog.PuenteNormas(win)
    e = json.loads(pu.estado())
    assert e["resumen"] == {"activas": 4, "total": 4, "revisados": 2, "fuera": 1}
    assert e["categorias"][0]["id"] == "conexiones" and e["incumplimientos"][0]["i"] == 0
    # desactivar en ESTE proyecto: va al .digproj, no al catálogo
    assert pu.activar("conex_codo", False) == ""
    assert win.normas_estado == {"conex_codo": False} and win.btn_normas.isHidden()
    import project_io
    assert project_io.build_model_dict(win)["normativas_activas"] == {"conex_codo": False}
    assert pu.activar("conex_codo", True) == "" and win.normas_estado == {}
    # cambiar un valor: se guarda global y deja de incumplir
    assert pu.cambiar("conex_codo", "angulos", json.dumps([11.25, 22.5, 37, 45, 90])) == ""
    assert win.btn_normas.isHidden()
    assert os.path.isfile(os.environ["PDFCAD_NORMATIVAS"])
    assert pu.cambiar("conex_codo", "angulos", "[]") != ""   # error: no se aplica
    assert pu.restablecer("conex_codo") == "" and not win.btn_normas.isHidden()


def test_ir_a_centra_el_lienzo(win):
    win.canvas.resetTransform(); win.canvas.scale(2, 2)
    win._normas_ir_a(0)
    c = win.canvas.mapToScene(win.canvas.viewport().rect().center())
    inc = win._normas_lista[0][0]
    assert abs(c.x() - inc.x) < 20 and abs(c.y() - inc.y) < 20
