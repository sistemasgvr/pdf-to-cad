"""Hoja SIN capas ni leyenda (reporte 2026-11-14, «Southwest Gas Combined 811 Records»): la utilidad y los
estilos de la red se deducen del plano y quedan asignados en «Capas de la hoja»; en la hoja compuesta el
mismo estilo con otro grosor por pieza se reconoce como uno (`pdf_styles.gemelos`)."""
import os

import fitz
import pytest

from hoja import composite as C, estilos_sugeridos as ES, pdf_styles
from reconocimiento import recognition as rec

TEAL, NARANJA, VERDE, GRIS = (0, 0.522, 0.522), (1.0, 0.412, 0.129), (0.0, 0.706, 0.0), (0.51, 0.51, 0.51)


def _hoja(doc, titulo=True, rotulos=True, dx=0.0):
    pg = doc.new_page(width=900, height=700)
    # red principal horizontal, acometidas verticales que nacen sobre ella, lotes (verde) junto a ellas
    pg.draw_line((50 + dx, 300), (850 + dx, 300), color=TEAL, width=0.48)
    for k in range(8):
        x = 100 + 90 * k + dx
        pg.draw_line((x, 300), (x, 420), color=NARANJA, width=0.24)
        pg.draw_line((x + 6, 310), (x + 6, 520), color=VERDE, width=0.0)
        if rotulos:
            pg.insert_text((x - 2, 410), '3/4" STL \'56', fontsize=6, rotate=90, color=NARANJA)
    if rotulos:
        pg.insert_text((400 + dx, 296), '2" STL \'56', fontsize=6, color=GRIS)
    if titulo:
        pg.insert_text((60, 640), "GAS DISTRIBUTION SYSTEM", fontsize=9)
        pg.insert_text((60, 660), "Southwest Gas Corporation", fontsize=7)
        pg.insert_text((60, 675), "consent of Southwest Gas", fontsize=7)
    return pg


def _estilo(color, width):
    return next(n for n in _nombres() if pdf_styles.style_label(n).startswith(
        "#" + "".join(f"{round(v * 255):02X}" for v in color) + f" {width:.2f}"))


_DOC = {}


def _nombres():
    return {d.get("layer") for d in pdf_styles.drawings(_DOC["pg"])}


def test_utilidad_y_estilos_de_la_red_por_texto_y_rotulos():
    doc = fitz.open()
    pg = _hoja(doc)
    _DOC["pg"] = pg
    s = ES.sugerir(pg)
    assert s.motivo == ES.OK and s.utilidad == "GAS"
    assert s.rotulada == _estilo(NARANJA, 0.24)                 # rótulos naranjas junto a las naranjas
    assert s.principal == _estilo(TEAL, 0.48)                   # las acometidas nacen sobre ella
    assert set(s.lineas) == {s.principal, s.rotulada}           # los lotes verdes no


def test_sin_titulo_sin_rotulos_y_ambiguo_no_asigna():
    doc = fitz.open()
    s = ES.sugerir(_hoja(doc, titulo=False))
    assert s.motivo == ES.SIN_UTILIDAD and s.utilidad is None and s.lineas     # sabe qué estilos, no qué red
    s = ES.sugerir(_hoja(doc, rotulos=False))
    assert s.motivo == ES.SIN_ROTULOS and not s.lineas
    # un mapa de gas que nombra «electric» un par de veces sigue siendo de gas; empatados, nadie
    assert ES.utilidad_de_texto(["GAS GAS GAS GAS GAS GAS ELECTRIC ELECTRIC"])[0] == "GAS"
    assert ES.utilidad_de_texto(["GAS GAS GAS WATER WATER"])[0] is None
    assert ES.utilidad_de_texto(["GASSED UP 5-21-2024"])[0] is None


def test_gemelos_solo_cambian_de_grosor():
    P = pdf_styles.PREFIX
    a = P + '["s",[0.0,0.522,0.522],0.48,"[] 0",null,1.0,null]'
    b = P + '["s",[0.0,0.522,0.522],0.46,"[] 0",null,1.0,null]'
    c = P + '["s",[0.0,0.522,0.522],0.40,"[] 0",null,1.0,null]'        # otro grosor de verdad
    d = P + '["s",[1.0,0.412,0.129],0.48,"[] 0",null,1.0,null]'        # otro color
    e = P + '["s",[0.0,0.522,0.522],0.48,"[3 2] 0",null,1.0,null]'     # a guiones
    assert pdf_styles.gemelos([a], [a, b, c, d, e]) == {a: a, b: a}


def _compuesta(tmp_path):
    """Dos hojas lado a lado; la segunda a escala 0.96: sus estilos salen con otro grosor."""
    src = fitz.open()
    _hoja(src)
    _hoja(src)
    src = fitz.open(stream=src.tobytes(), filetype="pdf")
    comp = C.Composite()
    comp.scale_ft_per_pt = 1.0
    comp.pieces = [C.Piece(0, 0, [0, 0, 1, 1], x=0, y=0, src_scale=1.0),
                   C.Piece(0, 1, [0, 0, 1, 1], x=900, y=0, src_scale=0.96)]
    out = C.build_document(comp, [src])
    ruta = str(tmp_path / "comp.pdf")
    out.save(ruta)
    return ruta


def test_compuesta_reconoce_el_estilo_con_el_grosor_de_cada_pieza(tmp_path):
    ruta = _compuesta(tmp_path)
    doc = fitz.open(ruta)
    pg = doc[0]
    nombres = {d.get("layer") for d in pdf_styles.drawings(pg)}
    teal = sorted(n for n in nombres if n and pdf_styles.style_label(n).startswith("#008585"))
    assert len(teal) == 2                                      # 0.48 y 0.46: la misma red, dos grosores
    roles = {rec.ROLE_LINEAS: [teal[-1]], rec.ROLE_BUZONES: []}          # se eligió solo uno
    r = rec.recognize_page(ruta, 0, "GAS", zoom=1.0, doc=doc, layer_roles=roles, scale_ft_per_pt=1.0)
    xs = [x for p in r.polylines for x, _y in p.pts_pdf]
    assert min(xs) < 100 and max(xs) > 1600                    # las dos piezas, no solo la del grosor elegido
    assert any("solo cambian de grosor" in w for w in r.warnings)


def test_capas_de_la_hoja_ya_viene_con_gas_asignado():
    from PySide6 import QtWidgets
    from ui.asistente.layer_dialog import SheetLayersDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open()
    _hoja(doc)
    _hoja(doc, rotulos=False)
    doc = fitz.open(stream=doc.tobytes(), filetype="pdf")
    dlg = SheetLayersDialog(None, doc, 0)
    try:
        roles = dlg.roles_by_utility()["GAS"]
        assert len(roles[rec.ROLE_LINEAS]) == 2
        assert dlg._recog_checks["GAS"].isEnabled() and dlg._recog_checks["GAS"].isChecked()
        assert dlg.recognition_utilities() == ("GAS",) and dlg.btn_ok.isEnabled()
        assert "GAS" in dlg.lbl_map_legend.text().upper() and dlg.lbl_map_legend.isVisibleTo(dlg)
        # otra hoja sin rótulos: lo deducido en la anterior no pasa; el aviso dice por qué
        dlg._load_sheet(1)
        assert not dlg._recog_checks["GAS"].isEnabled()
        assert "rótulos" in dlg.lbl_map_legend.text() and dlg.lbl_map_legend.isVisibleTo(dlg)
    finally:
        dlg._timer.stop()
        dlg._stop_legend()
        dlg.deleteLater()
        app.processEvents()


SW = os.path.join(os.path.expanduser("~"), "Downloads", "Southwest Gas Combined 811 Records.pdf")


@pytest.mark.skipif(not os.path.exists(SW), reason="sin el PDF de Southwest Gas")
def test_southwest_cada_hoja_es_gas_con_su_red_y_sus_acometidas():
    doc = fitz.open(SW)
    for i in (0, 20, 36, 53):
        s = ES.sugerir(doc[i])
        assert s.motivo == ES.OK and s.utilidad == "GAS"
        assert [pdf_styles.style_label(n)[:7] for n in s.lineas] == ["#008585", "#FF6921"]
