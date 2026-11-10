"""Hacia dónde va el fluido con un PUNTO DE LLEGADA (pedido del usuario 2026-11-10: «ya no todo a la izquierda o a la
derecha: puede llegar a un buzón del medio»), en el perfil y en el plano, con el ojo de ver/ocultar y las validaciones
según ese sentido."""
import math

import pytest

from nucleo import flujo as FL, flujo_perfil as FP, flujo_validar as FV, perfil_datos as PD
from nucleo import perfil_recorrido as PR, perfil_validar as PV

FT = 0.1


def _colector():
    # un colector de 3 vértices: baja de oeste a este (-9 → -10 → -11), buzón en (1200, 500)
    return dict(layer="ALCANTARILLADO", pts=[(200, 500), (1200, 500), (2200, 500)], diam=8.0,
                inv_start=-9.0, inv_end=-11.0)


def test_punto_de_llegada_en_una_punta_o_en_medio():
    p = _colector()
    assert FL.poner_hacia(p, 2200, 503) and p["flujo"] == FL.ADELANTE and FL.HACIA not in p   # su fin
    assert FL.poner_hacia(p, 199, 500) and p["flujo"] == FL.ATRAS                            # su inicio
    assert FL.poner_hacia(p, 1200, 497)                                                       # el buzón del medio
    assert "flujo" not in p and FL.punto(p) == pytest.approx((1200, 500)) and FL.tiene(p)
    assert FL.partes(p) == [(0, 0.0, 1.0, FL.ADELANTE), (1, 0.0, 1.0, FL.ATRAS)]
    assert FL.llegada(p) == pytest.approx((1200, 500))
    assert not FL.poner_hacia(p, 1200, 500)                                                   # ya estaba así
    FL.poner_hacia(p, 700, 500)                                                               # a mitad de un tramo
    assert FL.partes(p) == [(0, 0.0, 0.5, FL.ADELANTE), (0, 0.5, 1.0, FL.ATRAS), (1, 0.0, 1.0, FL.ATRAS)]
    assert FL.sentido_en(p, 0, 0.2) == FL.ADELANTE and FL.sentido_en(p, 0, 0.8) == FL.ATRAS
    # dos ramas que llegan al punto, y una flecha por parte apuntando hacia él
    ramas = FL.ramas(p)
    assert [r[-1] for r in ramas] == [pytest.approx((700, 500))] * 2
    cosenos = sorted(round(math.cos(math.radians(a))) for _x, _y, a in FL.flechas(p))
    assert cosenos == [-1, -1, 1]                              # una al este (antes del punto) y dos al oeste
    assert FL.poner(p, FL.AUTO) and not FL.tiene(p) and FL.HACIA not in p


def test_dar_vuelta_la_utilidad_no_cambia_el_punto_de_llegada():
    from nucleo import unir_utilidades as UU
    p = _colector()
    FL.poner_hacia(p, 1200, 500)
    q = UU.invertir(p)
    assert FL.punto(q) == FL.punto(p) and FL.partes(q) == [(0, 0.0, 1.0, FL.ADELANTE), (1, 0.0, 1.0, FL.ATRAS)]


def test_iman_buzon_punta_vertice_y_linea():
    pts = [(0, 0), (100, 0), (200, 0)]
    assert FL.iman(pts, 98, 3, 10, buzones=[(100, 0)])[2] == "buzon"
    assert FL.iman(pts, 98, 3, 10)[2] == "vertice"
    assert FL.iman(pts, 197, 2, 10)[2] == "punta"
    x, y, tipo = FL.iman(pts, 150, 20, 10)
    assert tipo == "linea" and (x, y) == pytest.approx((150, 0))
    assert FL.iman(pts, 150, 40, 10) is None                                    # lejos de la utilidad


def _perfil(pipes):
    rec = PR.desde(pipes, 0, 700, 500, FT)
    return PD.armar(pipes, [], [], rec, FT)


def test_perfil_con_el_punto_dentro_de_un_paso_valida_cada_parte():
    p = _colector()
    FL.poner_hacia(p, 700, 500)                                 # llega a la mitad del 1.er tramo
    perfil = _perfil([p])
    con = [ps for ps in perfil.pasos if ps.flujo_corte is not None]
    assert len(con) == 1 and con[0].flujo_fijo
    e_corte = con[0].e_en(con[0].flujo_corte)
    assert con[0].punto_en(e_corte) == pytest.approx((700, 500), abs=1e-6)
    # el tramo baja hacia el este: la parte que va hacia el oeste (hacia el punto) sube → contrapendiente
    al = [a for a in PV.validar(perfil, [], None, 3.0) if a.clase == "contrapendiente"]
    assert al and all(a.nivel == "ERROR" for a in al)
    assert FP.llegadas(perfil, [(ps.flujo, ps.flujo_corte) for ps in perfil.pasos]) == [pytest.approx(e_corte)]


def test_elegir_en_el_perfil_asigna_cada_utilidad():
    pipes = [dict(layer="ALCANTARILLADO", pts=[(200, 500), (1200, 500)], diam=8.0, inv_start=-9.0, inv_end=-10.0),
             dict(layer="ALCANTARILLADO", pts=[(1200, 500), (2200, 500)], diam=8.0, inv_start=-10.0, inv_end=-11.0)]
    perfil = _perfil(pipes)
    nodo = next(k for k, n in enumerate(perfil.nodos) if n.x == pytest.approx(1200))
    e = perfil.nodos[nodo].e
    asig = FP.asignar(perfil, e, (perfil.nodos[nodo].x, perfil.nodos[nodo].y))
    assert asig == {0: ("sentido", FL.ADELANTE), 1: ("sentido", FL.ATRAS)}      # los dos van hacia el buzón
    for j, (clase, valor) in asig.items():
        (FL.poner_hacia(pipes[j], *valor, tol_px=5) if clase == "punto" else FL.poner(pipes[j], valor))
    assert pipes[0]["flujo"] == FL.ADELANTE and pipes[1]["flujo"] == FL.ATRAS     # los dos llegan al buzón
    # la 2.ª baja hacia el este pero el fluido va al oeste: contrapendiente, en el perfil y en el plano
    perfil = _perfil(pipes)
    al = [a for a in PV.validar(perfil, [], None, 3.0) if a.clase == "contrapendiente"]
    assert len(al) == 1 and perfil.pasos[al[0].paso].pipe == 1
    av = FV.avisos(pipes, FT)
    assert [(a.pipe, a.clase, a.nivel) for a in av] == [(1, "flujo", "ERROR")]
    assert "T1" in av[0].mensaje
    # el perfil no repite el aviso del plano (la contrapendiente la revisa por paso)
    assert not [a for a in PV.validar(perfil, av, None, 3.0) if a.clase == "flujo"]
    # una punta en medio de un paso: el paso queda partido
    asig = FP.asignar(perfil, perfil.e_ini + 30.0)
    assert [c for c, _v in asig.values()].count("punto") == 1


def test_sin_sentido_indicado_no_hay_avisos_nuevos_en_el_plano():
    p = _colector()
    p["inv_end"] = -5.0                                        # sube hacia el este: en automático no se avisa
    assert FV.avisos([p], FT) == []


def test_caida_en_el_buzon_con_el_sentido_indicado():
    from nucleo import normas_catalogo as nc, normas_reglas as NR, normas_validar as NV
    cat = nc.normalizar({"tipos": [], "reglas": [NR.regla_vacia(utilidad="DRENAJE", elemento="BUZON",
                                                                  revisar="caida", max=0.6)]})
    # en el vértice 1: el tramo 1 llega a 7.0 y el tramo 2 sale a 9.0 (en el orden de los vértices)
    p = dict(layer="DRENAJE", tipo="", pts=[(0, 0), (2000, 0), (4000, 0)], name="", diam=24.0, pipe_size="24 in",
             inv_start=5.0, inv_end=10.0, vertex_inv_out={"1": 9.0}, vertex_inv_in={"1": 7.0})
    estr = [dict(x=0.0, y=0.0), dict(x=2000.0, y=0.0), dict(x=4000.0, y=0.0)]

    def caidas(q):
        return [a for a in NV.validar(cat, [q], [], FT, (), estr, ()) if a.mensaje.startswith("Caída")]
    assert not caidas(p)                                       # en el orden de los vértices: 7.0 − 9.0 = −2 ft (cumple)
    FL.poner(p, FL.ATRAS)                                      # el fluido va al oeste: entra 9.0, sale 7.0 = 2 ft
    av = caidas(p)
    assert av and "2 ft" in av[0].mensaje
    FL.poner_hacia(p, 2000, 0)                                 # llega por los dos lados: no hay «entra → sale»
    assert not caidas(p)


# ---------------------------------------------------------------- ventana

@pytest.fixture
def win(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n, i18n_core
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    previo = i18n_core._current_lang
    i18n_core._current_lang = "es"
    from ui.ventana import ventana_flujo as VF
    ajustes = {}
    monkeypatch.setattr(VF, "ajuste", lambda clave, defecto=True: ajustes.get(clave, defecto))
    monkeypatch.setattr(VF, "guardar_ajuste", lambda clave, valor: ajustes.__setitem__(clave, bool(valor)))
    from ui.ventana.app_window import Main
    w = Main()
    w._info = lambda *a, **k: None
    img = QtGui.QImage(3500, 1500, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    w.canvas.set_image(img)
    w.scale, w.zoom = 1.0, 10.0
    w.pipes = [_colector(), dict(layer="ELECTRICO", pts=[(200, 1200), (1200, 1200)], diam=4.0)]
    w._refresh_lists()
    w._redraw()
    yield w
    w._dirty = False
    w.close()
    i18n_core._current_lang = previo


def _flechas(win):
    from PySide6 import QtWidgets
    return [it for it in win._overlay if isinstance(it, QtWidgets.QGraphicsPathItem)
            and it.flags() & QtWidgets.QGraphicsItem.ItemIgnoresTransformations]


def test_elegir_en_el_plano_con_iman_animacion_y_ojo(win):
    from PySide6 import QtCore
    form = win.gprop.layout()
    win.pipe_list.setCurrentRow(1)
    assert not form.isRowVisible(win.box_flujo)                # eléctrico: no lleva flujo
    win.pipe_list.setCurrentRow(0)
    assert form.isRowVisible(win.box_flujo) and not win.btn_flujo_auto.isEnabled()
    assert "Automático" in win.lbl_flujo_estado.text()
    win.btn_flujo_elegir.click()
    assert win.mode == "flujo_punto" and win.btn_flujo_elegir.isChecked()
    win._pista_flujo(1203, 520)                                # vista previa: diana y flechas en verde
    assert win._pista_flujo_items
    win.on_click(1203, 1000, QtCore.Qt.LeftButton)             # lejos: no hace nada
    assert win.mode == "flujo_punto" and not FL.tiene(win.pipes[0])
    win.on_click(1203, 506, QtCore.Qt.LeftButton)              # el imán lo lleva al vértice del medio
    assert win.mode == "idle" and FL.punto(win.pipes[0]) == pytest.approx((1200, 500))
    assert not win._pista_flujo_items and win.btn_flujo_auto.isEnabled()
    assert "intermedio" in win.lbl_flujo_estado.text()
    anim = win._flujo_anim
    assert anim.activa()
    pos = anim.posiciones(500, win.canvas.transform().m11())
    assert pos and all(abs(y - 500) < 1e-6 for _x, y, _a in pos)
    assert any(abs(a) < 1e-6 for *_q, a in pos) and any(abs(abs(a) - 180) < 1e-6 for *_q, a in pos)
    anim.detener()
    assert not anim.activa()
    # el ojo: flechas (2 tramos × círculo y flecha) + la diana de llegada (anillo y centro)
    assert len(_flechas(win)) == 6
    win.btn_flujo_ver.click()
    assert not _flechas(win) and "Ver" in win.btn_flujo_ver.toolTip()
    win.btn_flujo_ver.click()
    assert len(_flechas(win)) == 6
    # la contrapendiente sale como aviso del plano (el 2.º tramo baja hacia el este y el fluido va al oeste)
    assert any(a.clase == "flujo" for a in win._normas_avisos)
    win.undo()
    assert not FL.tiene(win.pipes[0])
    # Esc cancela el modo sin cambiar nada
    win.pipe_list.setCurrentRow(0)
    win.flujo_elegir_en_plano()
    win._on_escape()
    assert win.mode == "idle" and not FL.tiene(win.pipes[0])


def test_elegir_en_el_perfil_con_vista_previa(win):
    from PySide6 import QtCore
    win.pipes = [dict(layer="ALCANTARILLADO", pts=[(200, 500), (1200, 500)], diam=8.0, inv_start=-9.0, inv_end=-10.0),
                 dict(layer="ALCANTARILLADO", pts=[(1200, 500), (2200, 500)], diam=8.0, inv_start=-10.0,
                      inv_end=-11.0)]
    win._refresh_lists()
    win._redraw()
    win.abrir_perfil()
    win.perfil_nuevo()
    win.on_click(300, 500, QtCore.Qt.LeftButton)
    win.on_click(2100, 500, QtCore.Qt.LeftButton)
    assert win.btn_perfil_flujo.isVisibleTo(win) and win.btn_perfil_ver_flujo.isVisibleTo(win)
    v = win.perfil_vista
    v.resize(1400, 500)
    v._calcular()
    win.btn_perfil_flujo.click()
    assert v.eligiendo_flujo() and win.lbl_perfil_guia.isVisibleTo(win) and "LLEGA" in win.lbl_perfil_guia.text()
    d = win._perfil_datos
    nodo = next(k for k, n in enumerate(d.nodos) if n.x == pytest.approx(1200))
    pos = QtCore.QPointF(v.X(d.nodos[nodo].e) + 4, v.Z(d.pasos[0].z1))
    pista = v._mover_eligiendo(pos)
    assert pista["nodo"] == nodo                                # el imán toma el buzón del medio
    previa = [(h, f) for _i, _c, _a, h, f in v._flechas_flujo()]
    assert [h for h, _f in previa] == [1, -1] and all(f for _h, f in previa)
    v._clic_eligiendo(pos, QtCore.Qt.LeftButton)
    assert not v.eligiendo_flujo() and not win.btn_perfil_flujo.isChecked()
    assert win.pipes[0]["flujo"] == FL.ADELANTE and win.pipes[1]["flujo"] == FL.ATRAS
    assert [p.flujo for p in win._perfil_datos.pasos] == [1, -1]
    assert any(a.clase == "contrapendiente" for a in v.alertas)
    # el ojo del perfil oculta flechas y dianas
    assert v._flechas_flujo()
    win.btn_perfil_ver_flujo.click()
    assert not v._flechas_flujo() and not v.ver_flujo
    win.btn_perfil_ver_flujo.click()
    assert v._flechas_flujo()
    # Esc y clic derecho cancelan
    win.perfil_flujo_elegir(True)
    win._on_escape()
    assert not v.eligiendo_flujo()
    win.perfil_flujo_elegir(True)
    v._clic_eligiendo(pos, QtCore.Qt.RightButton)
    assert not v.eligiendo_flujo() and win.pipes[1]["flujo"] == FL.ATRAS
    win.undo()
    assert all(not FL.tiene(p) for p in win.pipes)
    assert math.isfinite(win._perfil_datos.e_fin)
