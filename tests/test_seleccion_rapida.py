"""Elegir con decenas de miles de utilidades (reporte del usuario 2026-11-18, proyecto de 29 mil): un clic en el
plano tardaba ~45 s (el arco de cada curva buscaba su tubería y sus vértices recorriendo todo) y elegir en la Vista
3D ~5 s (dos redibujos, la ficha armaba la tabla de avisos completa y la 3D reempaquetaba el modelo sin cambios).
Mismo resultado, menos trabajo."""
import os
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_vista3d import _esperar, win  # noqa: E402,F401


def test_tabla_parcial_lleva_las_mismas_filas_de_avisos_y_conflictos_de_esas_utilidades():
    from nucleo import tabla_datos
    pipes = [dict(layer="AGUA", pts=[(0, 10 * i), (100, 10 * i)], diam=8.0) for i in range(6)]
    avisos = [NS(x=5.0 * k, y=3.0, info=k == 4, aprobado=None, pipe=k % 6, clase="diametro", mensaje=f"m{k}")
              for k in range(12)]
    confl = [NS(x=1.0 * k, y=2.0, cotas=[1.0, 2.0], id=f"C-{k}", subtipo="cruce", titulo="Cruce", pipes=[k % 6, 5],
                diferencia=1.0, mensaje="x") for k in range(5)]
    codigos = {id(a): f"N-{k + 1}" for k, a in enumerate(avisos)}
    a_cad = lambda x, y: (x * 2.0, y * 2.0)                                   # noqa: E731
    entera = tabla_datos.armar(pipes, [], [], avisos, a_cad, 0.1, conflictos=confl, codigos_avisos=codigos)
    for i in range(6):
        una = tabla_datos.armar(pipes, [], [], avisos, a_cad, 0.1, conflictos=confl, codigos_avisos=codigos,
                                solo_pipes={i})
        assert una[0].filas == [f for f, lug in zip(entera[0].filas, entera[0].lugares) if lug[3] == i]
        assert una[4].filas == [f for f, a in zip(entera[4].filas, avisos) if a.pipe == i]
        assert una[5].filas == [f for f, c in zip(entera[5].filas, confl) if i in c.pipes]
        sin = tabla_datos.armar(pipes, [], [], avisos, a_cad, 0.1, conflictos=confl, solo_pipes={i},
                                filas_avisos=False)
        assert sin[0].filas == una[0].filas and not sin[4].filas and not sin[5].filas


def _red_con_curvas(w, n=90):
    """`n` utilidades con un codo cada una (estructura CV en su esquina): más de las que activan el índice."""
    w.pipes = [dict(layer="ELECTRICO", pts=[(100.0 + 40 * i, 100.0), (100.0 + 40 * i, 600.0),
                                            (400.0 + 40 * i, 900.0)], diam=4.0) for i in range(n)]
    w.structures = [dict(x=100.0 + 40 * i, y=600.0, curve=True, radius_ft=8.0, net="conduit", cod=f"CV-{i + 1}")
                    for i in range(n)]
    w.scale, w.zoom = 1.0, 10.0
    w._refresh_lists(); w._redraw()


def test_clic_en_el_arco_elige_lo_mismo_con_el_indice_que_recorriendo_todo(win, monkeypatch):
    from nucleo import model_ops
    _red_con_curvas(win)
    puntos = []
    for i in (0, 17, 44, 89):
        info = win._curve_arc_info(win.structures[i], win.pipes[i])
        assert info is not None
        arco = win._arc_polyline(info, n_per_90=12)
        puntos += [arco[len(arco) // 2], arco[len(arco) // 4], (win.pipes[i]["pts"][0][0] + 1, 300.0)]

    def elegidos():
        out = []
        for x, y in puntos:
            win.curve_list.setCurrentRow(-1); win.pipe_list.setCurrentRow(-1)
            win._pick(x, y)
            out.append((win.curve_list.currentRow(), win.sel_pipe))
        return out
    con_indice = elegidos()
    llamadas = []
    real = model_ops._curve_vertex_indices
    monkeypatch.setattr(model_ops, "_curve_vertex_indices", lambda *a, **k: llamadas.append(1) or real(*a, **k))
    win._pick(*puntos[0])
    assert len(llamadas) <= 2                      # memorizado por tubería en el índice (antes: una por cada curva)
    monkeypatch.setattr(model_ops, "_MIN_INDICE", 10 ** 9)                  # sin índice: el recorrido de antes
    assert elegidos() == con_indice
    assert any(c >= 0 for c, _p in con_indice)     # algún clic cayó en un arco


def test_elegir_en_3d_es_un_redibujo_y_no_reempaqueta_la_escena(win, monkeypatch):
    dlg = win.abrir_vista3d(); _esperar(dlg)
    redibujos, datos = [], []
    real_todo, real_datos = win._redraw_todo, dlg._datos
    monkeypatch.setattr(win, "_redraw_todo", lambda *a, **k: redibujos.append(1) or real_todo(*a, **k))
    monkeypatch.setattr(dlg, "_datos", lambda *a, **k: datos.append(1) or real_datos(*a, **k))
    dlg._elegido(2); dlg.actualizar()
    assert redibujos == [1] and win.sel_pipe == 1
    assert datos == []                              # nada de lo que usa la 3D cambió
    assert dlg.ficha.isVisible() or dlg._ficha_id == 2
    win.pipes[0]["inv_end"] = -9.0; win._redraw(); dlg.actualizar()
    assert datos                                    # un cambio de verdad sí se rearma
