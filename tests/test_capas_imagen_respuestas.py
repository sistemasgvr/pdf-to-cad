"""Lo SEGURO de las capas de imagen se aplica solo y las respuestas del usuario mandan (plan 2026-11-18 «Ejes de la
red en imagen», Tarea 7).

- `roles_iniciales` aplica cada `CapaCerteza` segura (líneas de su utilidad + sus símbolos como estructuras, como lo
  que asigna una leyenda: `CLAVE_LEYENDA`, solo en esa hoja); una dudosa no se asigna.
- La respuesta del usuario (`Main.responder_capa_imagen`) manda sobre lo automático, se guarda por sha1 del PDF de
  origen (vale en otra hoja del mismo PDF), va al .digproj y «Cancelar» la repone.
"""
import os
import sys
import time
import zlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

fitz = pytest.importorskip("fitz")
cv2 = pytest.importorskip("cv2")
import numpy as np  # noqa: E402

from hoja import estilos_sugeridos as ES, imagen_ejes as IE, leyenda_mapa  # noqa: E402
from hoja.certeza_capas import CapaCerteza  # noqa: E402
from reconocimiento import recognition as rec  # noqa: E402
from ui.asistente import roles_iniciales as RI  # noqa: E402
from traduccion.i18n_core import t  # noqa: E402

AZUL = (0, 77, 168)
CAPA_AZUL = IE.nombre("line", AZUL)
CAPA_SUMIDERO = IE.nombre("sym", AZUL, "cuadro 4x4 pt")
ROJO = (200, 30, 30)
CAPA_ROJA = IE.nombre("line", ROJO)
NEGRO = 'PDF_STYLE:[[0,0,0],0.5,"[] 0",null,1]'


def _layers(*nombres):
    return [{"name": n, "source": "style", "path_count": 10} for n in nombres]


LAYERS = _layers(CAPA_AZUL, CAPA_SUMIDERO, CAPA_ROJA, NEGRO)


def _sug(*capas, **kw):
    return ES.Sugerencia(capas=list(capas), **kw)


SEGURO = CapaCerteza(CAPA_AZUL, "DRENAJE", True, ["nombre", "rotulos"], [], [CAPA_SUMIDERO])
DUDOSO = CapaCerteza(CAPA_AZUL, "DRENAJE", False, ["nombre"], ["varios_colores"], [CAPA_SUMIDERO])
SIN_EVIDENCIA = CapaCerteza(CAPA_AZUL, None, False, [], ["sin_evidencia"], [CAPA_SUMIDERO])


def _todas(roles, rol):
    return {n for r in roles.values() for n in r.get(rol, ())}


# ── puro ─────────────────────────────────────────────────────────────────────────────────────

def test_seguro_se_asigna_solo():
    roles = RI.roles_iniciales(LAYERS, None, _sug(SEGURO))
    assert CAPA_AZUL in roles["DRENAJE"][rec.ROLE_LINEAS]
    assert CAPA_SUMIDERO in roles["DRENAJE"][rec.ROLE_BUZONES]
    # como lo que asigna una leyenda: solo en esta hoja
    assert set(roles["DRENAJE"][leyenda_mapa.CLAVE_LEYENDA]) == {CAPA_AZUL, CAPA_SUMIDERO}
    assert leyenda_mapa.roles_de_otra_hoja(roles) == {}


def test_dudoso_no_se_asigna():
    roles = RI.roles_iniciales(LAYERS, None, _sug(DUDOSO))
    assert CAPA_AZUL not in _todas(roles, rec.ROLE_LINEAS)
    assert CAPA_SUMIDERO not in _todas(roles, rec.ROLE_BUZONES)


def test_sin_capas_de_imagen_igual_que_antes():
    """Hoja sin red en imagen (`capas == []`): el mismo resultado de siempre."""
    sug = _sug(utilidad="GAS", lineas=[NEGRO], motivo=ES.OK)
    roles = RI.roles_iniciales(_layers(NEGRO), None, sug)
    assert roles["GAS"][rec.ROLE_LINEAS] == [NEGRO] and roles["GAS"][leyenda_mapa.CLAVE_LEYENDA] == [NEGRO]
    assert RI.roles_iniciales(_layers(NEGRO), None, _sug(motivo=ES.SIN_ROTULOS)) == {}


def test_con_capas_de_imagen_no_se_aplican_las_lineas_viejas():
    """Hoja SD: lo que el texto deduce para los estilos vectoriales no se asigna; manda la certeza de la imagen."""
    sug = _sug(SEGURO, utilidad="DRENAJE", lineas=[NEGRO], motivo=ES.OK)
    roles = RI.roles_iniciales(LAYERS, None, sug)
    assert NEGRO not in _todas(roles, rec.ROLE_LINEAS)
    assert CAPA_AZUL in roles["DRENAJE"][rec.ROLE_LINEAS]


def test_respuesta_manda_sobre_lo_seguro():
    roles = RI.roles_iniciales(LAYERS, None, _sug(SEGURO), respuestas={CAPA_AZUL: "ALCANTARILLADO"})
    assert CAPA_AZUL in roles["ALCANTARILLADO"][rec.ROLE_LINEAS]
    assert CAPA_SUMIDERO in roles["ALCANTARILLADO"][rec.ROLE_BUZONES]
    assert CAPA_AZUL not in (roles.get("DRENAJE") or {}).get(rec.ROLE_LINEAS, ())
    # asignación a mano: pasa a otras hojas (no va en lo que «asignó la leyenda»)
    assert CAPA_AZUL not in roles["ALCANTARILLADO"].get(leyenda_mapa.CLAVE_LEYENDA, ())
    otra = leyenda_mapa.roles_de_otra_hoja(roles)
    assert CAPA_AZUL in otra["ALCANTARILLADO"][rec.ROLE_LINEAS]


def test_respuesta_en_una_dudosa_la_asigna():
    roles = RI.roles_iniciales(LAYERS, None, _sug(DUDOSO), respuestas={CAPA_AZUL: "DRENAJE"})
    assert CAPA_AZUL in roles["DRENAJE"][rec.ROLE_LINEAS]


def test_respuesta_no_es_red_quita_tambien_lo_ya_asignado():
    from ui.ventana.ventana_capas_imagen import NO_RED
    assert NO_RED == RI.NO_RED == "NO_RED"
    antes = RI.roles_iniciales(LAYERS, None, _sug(SEGURO))       # roles de ESTA hoja (con lo seguro)
    roles = RI.roles_iniciales(LAYERS, None, _sug(SEGURO), base_roles=antes, respuestas={CAPA_AZUL: NO_RED})
    assert CAPA_AZUL not in _todas(roles, rec.ROLE_LINEAS)
    assert CAPA_SUMIDERO not in _todas(roles, rec.ROLE_BUZONES)


def test_misma_hoja_lo_quitado_a_mano_no_vuelve():
    """Volver a la misma hoja con roles elegidos en ella: lo seguro no se vuelve a poner."""
    antes = RI.roles_iniciales(LAYERS, None, _sug(SEGURO))
    antes["DRENAJE"][rec.ROLE_LINEAS].remove(CAPA_AZUL)
    roles = RI.roles_iniciales(LAYERS, None, _sug(SEGURO), base_roles=antes)
    assert CAPA_AZUL not in _todas(roles, rec.ROLE_LINEAS)


def test_nombres_de_fuentes_hacen_segura_una_sin_evidencia():
    """Hoja compuesta: el PDF de trabajo es un temporal; el nombre de los PDF de origen decide."""
    assert CAPA_AZUL not in _todas(RI.roles_iniciales(LAYERS, None, _sug(SIN_EVIDENCIA)), rec.ROLE_LINEAS)
    roles = RI.roles_iniciales(LAYERS, None, _sug(SIN_EVIDENCIA),
                               nombres_fuentes=lambda: ["QS SD_Indian School_South.pdf"])
    assert CAPA_AZUL in roles["DRENAJE"][rec.ROLE_LINEAS]
    neutro = RI.roles_iniciales(LAYERS, None, _sug(SIN_EVIDENCIA), nombres_fuentes=lambda: ["plano.pdf"])
    assert CAPA_AZUL not in _todas(neutro, rec.ROLE_LINEAS)


def test_respuesta_de_otro_pdf_no_asigna_una_dudosa():
    """Revisión T7 (I-1): la respuesta dada en una hoja del PDF A viaja como asignación a mano; en una hoja de OTRO
    PDF (sin respuesta para su sha1) donde la misma capa es DUDOSA no se asigna."""
    hoja_a = RI.roles_iniciales(LAYERS, None, _sug(DUDOSO), respuestas={CAPA_AZUL: "DRENAJE"})
    assert CAPA_AZUL in hoja_a["DRENAJE"][rec.ROLE_LINEAS]
    base_b = leyenda_mapa.roles_de_otra_hoja(hoja_a)
    assert CAPA_AZUL in base_b["DRENAJE"][rec.ROLE_LINEAS]            # llega como «a mano»
    hoja_b = RI.roles_iniciales(LAYERS, None, _sug(DUDOSO), base_roles=base_b, respuestas={})
    assert CAPA_AZUL not in _todas(hoja_b, rec.ROLE_LINEAS)
    assert CAPA_SUMIDERO not in _todas(hoja_b, rec.ROLE_BUZONES)
    # mismo PDF (su respuesta llega por sha1): sí
    hoja_a2 = RI.roles_iniciales(LAYERS, None, _sug(DUDOSO), base_roles=base_b, respuestas={CAPA_AZUL: "DRENAJE"})
    assert CAPA_AZUL in hoja_a2["DRENAJE"][rec.ROLE_LINEAS]
    # los demás roles a mano (no de imagen) siguen viajando
    base_c = {"GAS": {rec.ROLE_LINEAS: [NEGRO], leyenda_mapa.SUMAR_LEYENDA: True}}
    hoja_c = RI.roles_iniciales(LAYERS, None, _sug(DUDOSO), base_roles=base_c)
    assert hoja_c["GAS"][rec.ROLE_LINEAS] == [NEGRO]


# ── ventana real ─────────────────────────────────────────────────────────────────────────────

ESC = 2.0
_n_img = [0]


def _indexada(doc, page, rect, idx, paleta):
    alto, ancho = idx.shape
    _n_img[0] += 1
    marca = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, _n_img[0], 1), False)
    xref = page.insert_image(rect, stream=marca.tobytes("png"), keep_proportion=False)
    tabla = bytes(v for c in paleta for v in c).hex()
    datos = zlib.compress(np.ascontiguousarray(idx, np.uint8).tobytes())
    cab = ("<</Type/XObject/Subtype/Image/Width %d/Height %d/BitsPerComponent 8"
           "/ColorSpace[/Indexed/DeviceRGB %d <%s>]/Filter/FlateDecode" % (ancho, alto, len(paleta) - 1, tabla))
    doc.update_object(xref, cab + ">>")
    doc.update_stream(xref, datos, compress=False)
    doc.update_object(xref, cab + "/Length %d>>" % len(datos))


def _pdf_sd(ruta, hojas=2, lado=300, tiras=3, dos_colores=False):
    """PDF «vectorial» (líneas negras + texto, como los mapas de Phoenix) con la red azul en imagen indexada
    (`dos_colores`: y una vertical roja)."""
    doc = fitz.open()
    W = H = int(lado * ESC)
    for k in range(hojas):
        page = doc.new_page(width=lado, height=lado)
        idx = np.zeros((H, W), np.uint8)
        y = 296 - 40 * k
        cv2.rectangle(idx, (60, y), (540, y + 7), 1, -1)
        paleta = [(255, 255, 255), AZUL]
        if dos_colores:
            cv2.rectangle(idx, (446, 60), (453, 540), 2, -1)
            paleta.append(ROJO)
        paso = H // tiras
        for j in range(tiras):
            y0, y1 = j * paso, (H if j == tiras - 1 else (j + 1) * paso)
            _indexada(doc, page, fitz.Rect(0, y0 / ESC, lado, y1 / ESC), idx[y0:y1], paleta)
        for i in range(90):                                     # ≥80 trazos + texto = PDF vectorial
            page.draw_line((5, 3 + 3 * i), (25, 3 + 3 * i), color=(0, 0, 0), width=0.3)
        page.insert_text((40, 290), "CITY OF PHOENIX QUARTER SECTION MAP", fontsize=6)
    doc.save(str(ruta))
    return ruta


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ventana(monkeypatch, ruta):
    import test_flujo_abrir_interpretar as TF
    monkeypatch.setenv("PDFCAD_PROCESO", "0")
    _app()
    from PySide6 import QtWidgets
    from ui.comun import theme
    theme.save_preference = lambda *_a, **_k: None
    from ui.ventana import app_window
    for nombre in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, nombre, lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Discard)
    TF._prohibir_asistente_viejo(monkeypatch)
    TF._componer(monkeypatch, hoja=0)
    w = app_window.Main()
    w._open_pdf_path(str(ruta))
    TF.esperar_interpretacion(w)
    return w


def _cerrar(w):
    import test_flujo_abrir_interpretar as TF
    TF._esperar_hilos()
    from reconocimiento import lectura_retenida as LR
    LR.soltar()
    w._dirty = False
    w.close()
    _app().processEvents()


@pytest.fixture
def win_sd(monkeypatch, tmp_path):
    w = _ventana(monkeypatch, _pdf_sd(tmp_path / "QS SD_Prueba.pdf"))
    yield w
    _cerrar(w)


@pytest.fixture
def win_dudosa(monkeypatch, tmp_path):
    """Dos colores de línea y un nombre de PDF neutro: nada se asigna solo y se pregunta."""
    w = _ventana(monkeypatch, _pdf_sd(tmp_path / "plano.pdf", dos_colores=True))
    yield w
    _cerrar(w)


def test_ventana_sd_lo_seguro_queda_asignado(win_sd):
    w = win_sd
    capas = w._interpretacion["sugeridos"].capas
    assert [c.capa for c in capas] == [CAPA_AZUL] and capas[0].seguro
    assert CAPA_AZUL in w._layer_roles_by_utility["DRENAJE"][rec.ROLE_LINEAS]


def test_respuesta_manda_y_vale_en_otra_hoja(win_sd):
    import test_flujo_abrir_interpretar as TF
    w = win_sd
    pasos = len(w._undo)
    w.responder_capa_imagen(CAPA_AZUL, "ALCANTARILLADO")
    assert len(w._undo) == pasos + 1
    roles = w._layer_roles_by_utility
    assert CAPA_AZUL in roles["ALCANTARILLADO"][rec.ROLE_LINEAS]
    assert CAPA_AZUL not in (roles.get("DRENAJE") or {}).get(rec.ROLE_LINEAS, ())
    assert w._respuestas_de_hoja() == {CAPA_AZUL: "ALCANTARILLADO"}
    w._change_page(1)                                         # otra hoja del mismo PDF
    TF.esperar_interpretacion(w)
    assert w.page_idx == 1
    roles = w._layer_roles_by_utility
    assert CAPA_AZUL in roles["ALCANTARILLADO"][rec.ROLE_LINEAS]
    assert CAPA_AZUL not in (roles.get("DRENAJE") or {}).get(rec.ROLE_LINEAS, ())
    w.responder_capa_imagen(CAPA_AZUL, None)                  # «No es una red»
    assert w._respuestas_de_hoja() == {CAPA_AZUL: "NO_RED"}
    assert CAPA_AZUL not in _todas(w._layer_roles_by_utility, rec.ROLE_LINEAS)


def test_respuestas_van_al_digproj_y_cancelar_las_repone(win_sd, tmp_path):
    from ui.ventana import app_window, respaldo_editor
    w = win_sd
    assert "capas_imagen_respuestas" in respaldo_editor.CLAVES
    antes = respaldo_editor.tomar(w)
    w.responder_capa_imagen(CAPA_AZUL, "ALCANTARILLADO")
    guardadas = dict(w.capas_imagen_respuestas)
    assert len(guardadas) == 1 and list(guardadas.values()) == [{CAPA_AZUL: "ALCANTARILLADO"}]
    ruta = tmp_path / "sd.digproj"
    w._write_project(str(ruta))
    w2 = app_window.Main()
    try:
        w2._open_project_path(str(ruta))
        assert w2.capas_imagen_respuestas == guardadas
    finally:
        w2._dirty = False
        w2.close()
    respaldo_editor.reponer(w, antes)                         # «Cancelar» del asistente
    assert w.capas_imagen_respuestas == {}


def test_proyecto_viejo_sin_la_clave():
    from project_io import parse_model
    datos = parse_model({"tf": dict(scale=1, zoom=1, rot=0, W=1, H=1, derot=[1, 0, 0, 1, 0, 0])})
    assert datos["capas_imagen_respuestas"] == {}


def test_capas_trabajo_calcula_la_certeza_tambien_con_leyenda(monkeypatch, tmp_path):
    """Hoja con red en imagen Y leyenda con filas: la certeza de sus capas se calcula igual (con la leyenda)."""
    from types import SimpleNamespace
    from hoja import capas_trabajo, pdf_styles
    ruta = _pdf_sd(tmp_path / "QS SD_Leyenda.pdf", hojas=1)
    ley = SimpleNamespace(filas=[object()])
    vistas = []
    monkeypatch.setattr(leyenda_mapa, "aplica", lambda page: True)
    monkeypatch.setattr(leyenda_mapa, "leer", lambda doc, page: ley)
    real = ES.sugerir

    def sugerir(page, **kw):
        vistas.append(kw.get("leyenda"))
        return real(page, **{**kw, "leyenda": None})
    monkeypatch.setattr(ES, "sugerir", sugerir)
    with fitz.open(str(ruta)) as doc, pdf_styles.lectura_unica(doc):
        out = capas_trabajo.leer_doc(doc, 0)
    assert out["leyenda"] is ley and vistas == [ley]
    assert [c.capa for c in out["sugeridos"].capas] == [CAPA_AZUL]


def test_deshacer_quita_la_respuesta_y_sus_roles(win_sd):
    """Revisión T7 (I-2): Ctrl+Z quita la respuesta y la capa vuelve a lo automático; Ctrl+Mayús+Z la repone."""
    w = win_sd
    w.responder_capa_imagen(CAPA_AZUL, "ALCANTARILLADO")
    assert CAPA_AZUL in w._layer_roles_by_utility["ALCANTARILLADO"][rec.ROLE_LINEAS]
    w.undo()
    assert w.capas_imagen_respuestas == {} and w._respuestas_de_hoja() == {}
    roles = w._layer_roles_by_utility
    assert CAPA_AZUL not in (roles.get("ALCANTARILLADO") or {}).get(rec.ROLE_LINEAS, ())
    assert CAPA_AZUL in roles["DRENAJE"][rec.ROLE_LINEAS]              # lo seguro de la hoja, otra vez
    w.redo()
    assert w._respuestas_de_hoja() == {CAPA_AZUL: "ALCANTARILLADO"}
    roles = w._layer_roles_by_utility
    assert CAPA_AZUL in roles["ALCANTARILLADO"][rec.ROLE_LINEAS]
    assert CAPA_AZUL not in (roles.get("DRENAJE") or {}).get(rec.ROLE_LINEAS, ())


def test_utilidad_desconocida_no_se_guarda(win_sd):
    with pytest.raises(ValueError):
        win_sd.responder_capa_imagen(CAPA_AZUL, "AGUA POTABLE")
    assert win_sd.capas_imagen_respuestas == {}


# ── la pregunta (Tarea 8) ────────────────────────────────────────────────────────────────────

def _tarjetas(w):
    from ui.comun.tarjeta_capa_imagen import TarjetaCapaImagen
    return w.panel_reconocer.findChildren(TarjetaCapaImagen)


def test_tarjeta_aparece_y_responder_la_quita(win_dudosa):
    w = win_dudosa
    tarjetas = _tarjetas(w)
    assert sorted(x.capa for x in tarjetas) == sorted([CAPA_AZUL, CAPA_ROJA])
    assert w.reconocer_estado.filas["DRENAJE"].estado == "bloqueada"
    azul = next(x for x in tarjetas if x.capa == CAPA_AZUL)
    azul.elegida.emit(azul.capa, "DRENAJE")
    assert [x.capa for x in _tarjetas(w)] == [CAPA_ROJA]
    assert w.reconocer_estado.filas["DRENAJE"].estado == "pendiente"
    assert CAPA_AZUL in w._layer_roles_by_utility["DRENAJE"][rec.ROLE_LINEAS]
    assert t("tu respuesta") in w.panel_reconocer.filas["DRENAJE"].detalle.text()


def test_no_es_red_no_reconoce(win_dudosa):
    w = win_dudosa
    antes = {u: f.estado for u, f in w.reconocer_estado.filas.items()}
    roja = next(x for x in _tarjetas(w) if x.capa == CAPA_ROJA)
    roja.elegida.emit(roja.capa, None)
    assert [x.capa for x in _tarjetas(w)] == [CAPA_AZUL]
    assert w._respuestas_de_hoja() == {CAPA_ROJA: "NO_RED"}
    assert {u: f.estado for u, f in w.reconocer_estado.filas.items()} == antes
    assert CAPA_ROJA not in _todas(w._layer_roles_by_utility or {}, rec.ROLE_LINEAS)


def test_ubicar_abre_capas_y_estilos_en_esa_capa(win_dudosa, monkeypatch):
    w = win_dudosa
    vistos = []
    monkeypatch.setattr(w, "abrir_capas_estilos", lambda parte=None, capa=None: vistos.append((parte, capa)))
    roja = next(x for x in _tarjetas(w) if x.capa == CAPA_ROJA)
    roja.ubicar.emit(roja.capa)
    assert vistos == [(None, CAPA_ROJA)]


def test_seguro_no_muestra_tarjeta(win_sd):
    assert not _tarjetas(win_sd)
    detalle = win_sd.panel_reconocer.filas["DRENAJE"].detalle.text()
    assert t("Asignada por: {pistas}").format(pistas=t("nombre del PDF")) in detalle


def test_capas_y_estilos_marca_la_dudosa_con_su_porque(win_dudosa):
    """«Capas y estilos…»: la capa dudosa lleva «?» y el porqué en el globo; el resumen habla de la imagen."""
    from ui.asistente import layer_dialog_editor as LE
    from ui.comun.tarjeta_capa_imagen import porque
    w = win_dudosa
    doc, hoja, _propio = w._doc_de_lectura()
    dlg = LE.dialogo_editor(w, doc, hoja, interp=w._interpretacion_vigente(),
                            roles_by_utility=w._roles_de_la_hoja(w.page_idx),
                            legend_sources=w._legend_sources())
    try:
        its = dlg._items_by_name.get(CAPA_AZUL) or []
        assert its and not its[0].icon(0).isNull()
        c = next(c for c in w._interpretacion["sugeridos"].capas if c.capa == CAPA_AZUL)
        assert porque(c) in its[0].toolTip(0)
        texto, _det = dlg._map_legend_summary()
        assert "imagen" in texto or "image" in texto
        # el diálogo y el panel deciden las dudosas con los MISMOS nombres de origen (`_con_nombres`)
        assert set(dlg._capas_dudosas()) == {x.capa for x in _tarjetas(w)}
    finally:
        dlg.deleteLater()


def _dialogo(w):
    from ui.asistente import layer_dialog_editor as LE
    doc, hoja, _propio = w._doc_de_lectura()
    return LE.dialogo_editor(w, doc, hoja, interp=w._interpretacion_vigente(),
                             roles_by_utility=w._roles_de_la_hoja(w.page_idx), legend_sources=w._legend_sources())


def test_asignar_en_capas_y_estilos_responde_para_todo_el_pdf(win_dudosa):
    """Spec §7.6: asignar la capa dudosa en «Capas y estilos…» también responde (sha1 del PDF + capa): en otra hoja
    del mismo PDF queda asignada y sin tarjeta. La que no se tocó sigue dudosa. Un solo paso de deshacer."""
    import test_flujo_abrir_interpretar as TF
    from PySide6 import QtWidgets
    w = win_dudosa
    dlg = _dialogo(w)
    it = dlg._items_by_name[CAPA_AZUL][0]
    dlg.tree.setCurrentItem(it)
    dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("DRENAJE"))
    assert dlg._assignments[CAPA_AZUL][0] == "DRENAJE"
    pasos = len(w._undo)
    w._capas_estilos_cerrada(dlg, QtWidgets.QDialog.Accepted)
    assert len(w._undo) == pasos + 1
    assert w._respuestas_de_hoja() == {CAPA_AZUL: "DRENAJE"}            # la roja no se tocó: sigue sin respuesta
    assert [x.capa for x in _tarjetas(w)] == [CAPA_ROJA]
    w._change_page(1)                                                   # otra hoja del mismo PDF
    TF.esperar_interpretacion(w)
    assert w.page_idx == 1
    assert CAPA_AZUL in w._layer_roles_by_utility["DRENAJE"][rec.ROLE_LINEAS]
    assert [x.capa for x in _tarjetas(w)] == [CAPA_ROJA]


def test_nombres_de_fuentes_sin_src_pdfs_es_el_pdf_abierto(win_dudosa, monkeypatch):
    """Como `_legend_sources` (lo que recibe el diálogo): sin PDF de origen, el nombre del PDF abierto."""
    import os as _os
    w = win_dudosa
    monkeypatch.setattr(w, "src_pdfs", [])
    assert w._nombres_de_fuentes() == [_os.path.basename(w.pdf_path)] == [s["name"] for s in w._legend_sources()]
