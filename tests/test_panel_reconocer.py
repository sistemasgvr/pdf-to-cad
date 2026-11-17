"""Panel «Reconocer» del riel (`ui/comun/panel_reconocer.py` + `ui/ventana/ventana_reconocer.py`).

El panel solo muestra un `nucleo.reconocer_estado.Estado` y emite señales: el ▶ de una fila que no se puede
reconocer se ve apagado y el clic explica el motivo (nunca `setEnabled(False)`: un botón deshabilitado no dice
nada). Los colores de estado nunca son de utilidad (memoria «colores sin choque»)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.path.isdir(r"C:/Windows/Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:/Windows/Fonts")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from nucleo import reconocer_estado as RE  # noqa: E402
from traduccion.i18n_core import t  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import theme
    viejo = a.styleSheet()
    a.setStyleSheet(theme.build_stylesheet(theme.tokens()))
    yield a
    a.setStyleSheet(viejo)


def _capa(name, **kw):
    d = {"name": name, "short": name, "path_count": 5, "on": True, "source": "ocg"}
    d.update(kw)
    return d


def _estado():
    interp = {"layers": [_capa("C-ELEC-UNGD-E"), _capa("C-STRM-UGND-E"), _capa("C-STRM-UGND-N")],
              "simbolos": [{}, {}, {}], "rotulos_n": 0}
    e = RE.de_interpretacion(RE.nuevo(), interp, "h1")
    f = e.filas["ELECTRICO"]
    f.estado, f.hechos, f.verificar = "reconocida", 7, [{"a": 1}, {"b": 2}]
    return e


@pytest.fixture
def panel(app):
    from ui.comun.panel_reconocer import PanelReconocer
    p = PanelReconocer()
    p.resize(320, 700)
    p.show()
    p.mostrar(_estado())
    app.processEvents()
    yield p
    p.deleteLater()


def _espia(senal):
    vistos = []
    senal.connect(lambda *a: vistos.append(a))
    return vistos


def test_una_fila_por_parte_con_su_motivo(panel):
    assert list(panel.filas) == list(RE.PARTES)
    assert panel.filas["GAS"].detalle.text() == t(RE.M_SIN_CAPAS)
    assert panel.filas["ROTULOS"].detalle.text() == t(RE.M_SIN_ROTULOS)
    assert "2" in panel.filas["DRENAJE"].detalle.text()            # 2 capas de drenaje
    assert "7" in panel.filas["ELECTRICO"].detalle.text()          # reconocida: 7
    assert "3" in panel.filas["VALVULAS"].detalle.text()           # 3 símbolos
    assert panel.filas["AGUA"].nombre.text() == t("Agua")


def test_motivo_de_diametros_con_nombres_traducidos(panel):
    e = _estado()
    e.filas["ELECTRICO"].estado = "pendiente"
    panel.mostrar(e)
    texto = panel.motivo("DIAMETROS")
    assert t("Eléctrico") in texto and t("Drenaje") in texto
    assert "ELECTRICO" not in texto


def test_play_bloqueado_no_reproduce_y_explica(panel, app):
    rep, avisos = _espia(panel.reproducir), _espia(panel.aviso)
    b = panel.filas["GAS"].btn_play
    assert b.isEnabled()                                             # se ve apagado, pero responde
    assert b.property("bloqueado") is True
    b.click()
    app.processEvents()
    assert rep == []
    assert avisos and avisos[-1][0] == t(RE.M_SIN_CAPAS)
    panel.filas["DRENAJE"].btn_play.click()
    assert rep == [("DRENAJE",)]


def test_valvulas_sin_utilidad_reconocida_bloqueadas(panel):
    e = _estado()
    e.filas["ELECTRICO"].estado = "pendiente"
    panel.mostrar(e)
    assert panel.filas["VALVULAS"].btn_play.property("bloqueado") is True
    assert panel.motivo("VALVULAS") == t(RE.M_VALVULAS)


def test_ver_capas_y_menu(panel):
    ver, capas, ajustar = _espia(panel.ver), _espia(panel.capas), _espia(panel.ajustar)
    unir, ia = _espia(panel.unir_tramos), _espia(panel.rotulos_ia)
    panel.filas["ELECTRICO"].btn_ver.click()
    assert ver == [("ELECTRICO",)]
    acciones = {a.text(): a for a in panel.filas["ELECTRICO"].menu.actions() if a.text()}
    acciones[t("Capas y estilos…")].trigger()
    # «Ajustar capas…» ya no va aparte: es la misma vista «Capas y estilos…» (2026-11-17)
    assert t("Ajustar capas…") not in acciones
    assert capas == [("ELECTRICO",)] and ajustar == []
    a_unir = acciones[t("Unir tramos")]
    assert a_unir.isCheckable() and a_unir.isChecked()
    a_unir.trigger()
    assert unir == [("ELECTRICO", False)]
    rot = {a.text() for a in panel.filas["ROTULOS"].menu.actions() if a.text()}
    assert t("Leer rótulos ilegibles con la IA…") in rot
    acc = next(a for a in panel.filas["ROTULOS"].menu.actions() if a.text() == t("Leer rótulos ilegibles con la IA…"))
    acc.trigger()
    assert ia == [()]
    assert t("Unir tramos") not in rot


def test_ver_bloqueado_explica(panel):
    ver, avisos = _espia(panel.ver), _espia(panel.aviso)
    panel.filas["GAS"].btn_ver.click()
    assert ver == [] and avisos[-1][0] == t(RE.M_SIN_CAPAS)


def test_pie_ultimo_y_por_verificar(panel, app):
    panel.mostrar(_estado(), ultimo=("ELECTRICO", 7))
    app.processEvents()
    assert t("Eléctrico") in panel.lbl_ultimo.text() and "7" in panel.lbl_ultimo.text()
    assert "2" in panel.btn_verificar.text()
    pv = _espia(panel.por_verificar)
    panel.btn_verificar.click()
    assert pv == [()]


def test_todo_cancelar_e_interpretar(panel, app):
    todo, cancelar, interp = _espia(panel.todo), _espia(panel.cancelar), _espia(panel.interpretar)
    panel.btn_todo.click()
    assert todo == [()]
    assert not panel.btn_cancelar.isVisibleTo(panel)
    e = _estado()
    e.filas["DRENAJE"].estado = "reconociendo"
    panel.mostrar(e)
    assert panel.btn_cancelar.isVisibleTo(panel)
    panel.btn_cancelar.click()
    assert cancelar == [()]
    panel.mostrar(RE.nuevo())                                        # sin interpretar
    assert panel.btn_interpretar.isVisibleTo(panel)
    assert not panel.lista.isVisibleTo(panel)
    panel.btn_interpretar.click()
    assert interp == [()]


def test_interpretando_muestra_etapa_barra_y_porcentaje(panel, app):
    """Reporte 2026-11-17: mientras interpreta, el panel decía solo «Interpretando la hoja…» y nada más."""
    panel.mostrar(RE.nuevo(), interpretando=True)
    assert panel.caja_interp.isVisibleTo(panel)
    panel.avance_interpretacion("Leyendo las letras de las líneas", 0.42)
    assert panel.lbl_interp.text() == "Leyendo las letras de las líneas"
    assert panel.bar_interp.value() == 420
    assert panel.lbl_interp_pct.text() == t("{p} %").format(p=42)
    panel.mostrar(_estado())                                         # terminó: ya no se ve
    assert not panel.caja_interp.isVisibleTo(panel)


def test_interpretacion_punto_por_punto(panel):
    """Pedido 2026-11-17: mientras interpreta, el panel dice QUÉ ya se interpretó (cada utilidad, válvulas, rótulos,
    escala), no solo una barra."""
    panel.reiniciar_interpretacion()
    panel.mostrar(RE.nuevo(), interpretando=True)
    fl = panel.lista_interp
    assert all(f.estado == "espera" for f in fl.values())
    panel.etapa_interpretacion(0)
    assert fl["AGUA"].estado == "curso" and fl["VALVULAS"].estado == "espera"
    panel.parte_interpretada("AGUA", 5)
    panel.parte_interpretada("GAS", 0)
    assert fl["AGUA"].estado == "hecho" and fl["AGUA"].detalle.text() == t("{n} capas").format(n=5)
    assert fl["GAS"].estado == "nada"
    panel.etapa_interpretacion(2)
    assert fl["VALVULAS"].estado == "curso"
    panel.parte_interpretada("VALVULAS", 3)
    panel.parte_interpretada("ESCALA", 20 / 72.0)
    assert fl["VALVULAS"].detalle.text() == t("{n} símbolos").format(n=3)
    assert fl["ESCALA"].detalle.text() == t("Escala 1\"={v}'").format(v="20")
    panel.reiniciar_interpretacion()
    assert fl["AGUA"].estado == "espera"


def test_el_trabajo_avisa_cada_parte(tmp_path, monkeypatch):
    from hoja import interpretar_trabajo as IT
    import vector_pipeline
    monkeypatch.setattr(vector_pipeline, "detect_scale", lambda page: 0.5)
    import fitz
    ruta = str(tmp_path / "h.pdf")
    d = fitz.open(); pg = d.new_page(); pg.draw_line((10, 10), (200, 10)); d.save(ruta); d.close()
    vistos = []
    IT.interpretar(ruta, 0, progreso=lambda *a: vistos.append(a))
    partes = {a[1] for a in vistos if a[0] == "parte"}
    assert set(RE.UTILIDADES) <= partes and {"VALVULAS", "ROTULOS", "ESCALA"} <= partes
    assert [a[1] for a in vistos if a[0] == "etapa"] == [0, 1, 2, 3, 4]


def test_tarjeta_sobre_el_plano_no_sobre_los_paneles(app):
    """Reporte 2026-11-17: la tarjeta de avance quedaba abajo a la derecha de la VENTANA y el borde del panel
    Propiedades la cruzaba. Con lienzo, va dentro de lo que queda libre del lienzo."""
    from ui.comun import tarjeta_avance as TA
    win = QtWidgets.QMainWindow()
    win.resize(1400, 800)
    cont = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(cont); lay.setContentsMargins(0, 0, 0, 0)
    win.canvas = QtWidgets.QWidget()
    derecha = QtWidgets.QWidget(); derecha.setFixedWidth(300)
    lay.addWidget(win.canvas, 1); lay.addWidget(derecha)
    win.setCentralWidget(cont)
    win.show(); app.processEvents()
    capa = TA.CapaTarjetas(win)
    capa.begin("Interpretando la hoja…")
    app.processEvents()
    g = capa.tarjetas[0].geometry()
    lienzo = QtCore.QRect(win.canvas.mapTo(win, QtCore.QPoint(0, 0)), win.canvas.size())
    assert lienzo.contains(g)
    capa.end(guardar=False)
    win.close(); win.deleteLater()


def test_tarjeta_de_avance_va_de_0_a_100_con_su_cifra(app):
    """Sin «i de n» la tarjeta tampoco se queda quieta: reparte el 0–100 % y lo muestra; el panel recibe lo mismo."""
    from ui.comun import tarjeta_avance as TA
    host = QtWidgets.QWidget()
    host.resize(800, 600)
    vistos = []
    capa = TA.CapaTarjetas(host, al_avance=lambda tx, d, f: vistos.append(f))
    capa.begin("Interpretando la hoja…", "Capas")
    capa.step(detail="Leyendo capas", done=1, total=4)
    tarjeta = capa.tarjetas[0]
    assert tarjeta.pct.text().endswith("%")
    assert vistos and vistos == sorted(vistos)                       # nunca retrocede
    assert 0.0 <= capa.fraccion() < 1.0
    capa.end(guardar=False)
    assert capa.tarjetas == []
    host.deleteLater()


def test_hoja_escaneada(panel):
    panel.mostrar(RE.nuevo(), escaneo=True)
    assert panel.lbl_vacio.text() == t("Hoja escaneada: no hay nada que reconocer.")
    assert not panel.btn_interpretar.isVisibleTo(panel)
    assert not panel.lista.isVisibleTo(panel)


def test_colores_de_estado_sin_utilidad_en_los_dos_temas(app):
    from ui.comun import theme, ui_common
    from ui.comun.panel_reconocer import color_estado
    for tema in (theme.LIGHT, theme.DARK):
        neutros = {tema.text3, tema.text_muted, ui_common.QA_UNCOVERED, ui_common.QA_OFFPATTERN}
        for est in RE.ESTADOS:
            assert color_estado(est, tema) in neutros, est


def test_se_dibuja_en_claro_y_oscuro(app):
    from ui.comun import theme
    from ui.comun.panel_reconocer import PanelReconocer
    viejo = theme.tokens()
    try:
        for tema in (theme.LIGHT, theme.DARK):
            theme._current = tema
            theme.THEME_BUS.changed.emit(tema.name)
            p = PanelReconocer()
            p.resize(320, 700)
            p.mostrar(_estado())
            img = p.grab()
            assert not img.isNull() and img.width() == 320
            p.deleteLater()
    finally:
        theme._current = viejo
        theme.THEME_BUS.changed.emit(viejo.name)


# ─────────────────────────── en la ventana ───────────────────────────

@pytest.fixture
def win(app, monkeypatch):
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana.app_window import Main
    w = Main()
    w.resize(1400, 820)
    w.show()
    app.processEvents()
    yield w
    i18n_core._current_lang = previo
    w._dirty = False
    w.close()
    w.deleteLater()


def test_pagina_del_riel_y_senales(win, app, monkeypatch):
    from ui.ventana import ventana_shell
    i = next(k for k, r in enumerate(ventana_shell.RIEL) if r and r[1] == "Reconocer")
    assert ventana_shell.RIEL[i][2] == 4 and ventana_shell.PAGINAS[4] == "Reconocer"
    assert ventana_shell.RIEL[3][1] == "Revisión"                   # lo de antes no se corre
    win._ir_riel(i)
    app.processEvents()
    assert win.paneles_riel.currentIndex() == 4
    assert win.panel_reconocer.isVisibleTo(win.paneles_riel)
    assert isinstance(win.reconocer_estado, RE.Estado)
    llamados = []
    monkeypatch.setattr(type(win), "reconocer_parte", lambda self, p: llamados.append(p))
    win.reconocer_estado = _estado()
    win._refrescar_panel_reconocer()
    win.panel_reconocer.filas["DRENAJE"].btn_play.click()
    assert llamados == ["DRENAJE"]
    win.panel_reconocer.filas["GAS"].btn_play.click()
    assert llamados == ["DRENAJE"]
    assert win.lbl_info.text() == t(RE.M_SIN_CAPAS)


def test_unir_tramos_se_guarda_en_la_fila(win):
    win.reconocer_estado = _estado()
    win._refrescar_panel_reconocer()
    win.panel_reconocer.unir_tramos.emit("AGUA", False)
    assert win.reconocer_estado.filas["AGUA"].unir_tramos is False
