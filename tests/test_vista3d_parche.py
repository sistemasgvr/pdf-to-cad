"""Vista 3D por partes (pedido del usuario 2026-10-20: con 16 761 utilidades cada cambio rearmaba la escena
entera, ~100 s): `modelo3d_parche.parche` rehace solo la utilidad editada, sus vecinas, sus accesorios y sus
buzones, y tiene que dar EXACTAMENTE lo mismo que rearmar la escena entera con el mismo origen."""
import copy
import os
import random

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import modelo3d, modelo3d_parche as MP  # noqa: E402
from nucleo import instancias3d as I3  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESCENARIOS = [os.path.join(AQUI, "escenarios", "cruces", "escenarios_complejos.digproj"),
              os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj"),
              os.path.join(AQUI, "escenarios", "presentacion_1_3_1.digproj")]


def _datos(ruta):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.dialogos import vista3d_dialog
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ruta); w._redraw()
    dlg = vista3d_dialog.Vista3DDialog(w)
    datos = dlg._datos()
    dlg.close(); w._dirty = False; w.close()
    datos.update(avisos=[], conflictos=[])
    return datos


def _clave_acc(o):
    return ("acc", o.get("acc_tipo"), round(float(o.get("x") or 0), 6), round(float(o.get("y") or 0), 6),
            bool(o.get("vertical")), tuple(sorted(o.get("pipes") or ())))


def canon(esc):
    """{objeto (por su id; un accesorio por su lugar y utilidades): (filas de malla, instancias, picks)} sin
    los ids: lo que se DIBUJA de cada cosa, comparable entre dos armados."""
    clave = {}
    for ident, o in esc.objetos.items():
        clave[ident] = _clave_acc(o) if o["tipo"] == "accesorio" else ident
    out = {}

    def poner(ident, cosa, filas):
        k = clave.get(int(round(ident)), ("?", int(round(ident))))
        out.setdefault(k, {}).setdefault(cosa, []).extend(filas)
    for nombre, F, col in (("base", esc.base, MP.ID_COL), ("tr", esc.transparentes, MP.ID_COL)):
        for ident in np.unique(F[:, col]) if len(F) else ():
            G = np.delete(F[F[:, col] == ident], col, axis=1)
            poner(ident, nombre, [r.tobytes() for r in G.reshape(-1, 6 * G.shape[1])] if len(G) % 6 == 0 else
                  [r.tobytes() for r in G])
    for k, F in esc.instancias.items():
        for ident in np.unique(F[:, I3.ID]):
            G = np.delete(F[F[:, I3.ID] == ident], I3.ID, axis=1)
            poner(ident, str(k), [r.tobytes() for r in G])
    if len(esc.picks):
        A, B, R, I = esc.picks
        for a, b, r, i in zip(A, B, R, I):
            poner(i, "pick", [np.r_[a, b, r].tobytes()])
    for v in out.values():
        for k in v:
            v[k] = sorted(v[k])
    return out


def _editar(pipes, i, rng):
    p = pipes[i]
    n = len(p.get("pts") or [])
    p["inv_start"] = float(p.get("inv_start") or 0.0) + rng.choice([-0.7, 0.35, 1.2])
    if n >= 3 and rng.random() < 0.5:
        p.setdefault("vertex_inv_in", {})[1] = float(p.get("inv_end") or 0.0) - 0.8
        p["seg_edit_enabled"] = True
    if rng.random() < 0.5:
        p["diam"] = float(rng.choice([2, 4, 6, 8, 12, 16])); p["pipe_size"] = ""; p["diam_elegido"] = True


@pytest.mark.parametrize("ruta", ESCENARIOS, ids=lambda r: os.path.basename(r))
def test_parche_igual_que_rearmar_entera(ruta):
    datos = _datos(ruta)
    datos["ver"] = dict(datos["ver"], avisos=False)
    antes = modelo3d.construir(**datos)
    rng = random.Random(7)
    indices = [i for i, p in enumerate(datos["pipes"]) if len(p.get("pts") or []) >= 2]
    probadas = 0
    for i in rng.sample(indices, min(12, len(indices))):
        pipes = copy.deepcopy(datos["pipes"])
        _editar(pipes, i, rng)
        d2 = dict(datos, pipes=pipes)
        entera = modelo3d.construir(**dict(d2, suelo_z=antes.suelo_z, origen=antes.origen))
        parcial = MP.parche(antes, pipes, d2["structures"], d2["ft"], {i}, d2["colores"], d2["duct_banks"],
                            d2["cruces"], d2["ocultas"], d2["ver"])
        a, b = canon(entera), canon(parcial)
        assert a.keys() == b.keys(), (i, set(a) ^ set(b))
        for k in a:
            assert a[k] == b[k], (i, k)
        assert sorted(entera.rotulos) == sorted(parcial.rotulos)
        probadas += 1
    assert probadas


@pytest.mark.parametrize("ruta", ESCENARIOS[1:], ids=lambda r: os.path.basename(r))
def test_tabla_de_una_sola_fila_igual_que_la_entera(ruta):
    """La ficha de la Vista 3D arma solo la fila de lo elegido (`tabla_datos.armar(solo_…)`): misma fila."""
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ruta); w._redraw()
    entera = w._tablas_de_datos()
    for tabla, clave, objeto in ((0, "solo_pipes", "pipe"), (1, "solo_estructuras", "struct")):
        for fila, lugar in zip(entera[tabla].filas, entera[tabla].lugares):
            una = w._tablas_de_datos(**{clave: {lugar[3]}})[tabla]
            assert una.filas == [fila] and una.lugares == [lugar]
    w._dirty = False; w.close()
