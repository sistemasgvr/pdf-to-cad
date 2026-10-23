"""La importación y la vista previa con hojas grandes: el MISMO resultado, sin trabar la ventana.

Reporte del usuario 2026-10-23: con las composiciones completas (36 mapas de agua + 36 de
alcantarillado de Phoenix) la ventana quedó «No responde» en «Preparando la vista previa…».
Los pasos de datos que comparten la vista previa (`recognition_quiebres.curvas_de_quiebres`) y la
importación (`Main._import_recognized_pipes`) comparaban todo con todo: insertar cada bóveda en su
línea (74 s), unir cada acometida a su tubería (117 s), asociar bóvedas (29 s), ocultar los buzones
de los quiebres y pasar los quiebres a curva (17 s). Ahora cada uno mira solo lo que puede estar
cerca (`nucleo.indice_plano`, `nucleo.vecindario`), con la MISMA cuenta y en el MISMO orden.

Aquí: una red sintética densa (gravedad y conductos, acometidas, bóvedas, codos, quiebres juntos)
pasa por la cadena con los índices de siempre y con los índices «apagados» (todo contra todo, el
recorrido de antes): tuberías, estructuras y curvas tienen que salir idénticas.
"""
import copy
import math
import random

import pytest

from nucleo import acometidas, indice_plano, model_ops, quiebres_curvas, vecindario
from reconocimiento import recognition as rec

ZOOM = 3.5
FPP = (100.0 / 72.0) / ZOOM          # pies por px (1" = 100')


def _red(semilla):
    """Tuberías como las deja el reconocimiento (px del lienzo): principales con quiebres, bóvedas
    en algunos vértices, acometidas que nacen en una principal, y bóvedas/codos sueltos."""
    rnd = random.Random(semilla)
    pipes, vault_pts, vaults_geo = [], [], []
    for k in range(70):
        capa = "ALCANTARILLADO" if k % 3 else "ELECTRICO"
        x, y = rnd.uniform(0, 1500), rnd.uniform(0, 1500)
        ang = rnd.uniform(0, 2 * math.pi)
        pts, kinds = [(x, y)], ["end"]
        for _ in range(rnd.randint(2, 7)):
            ang += math.radians(rnd.choice([0, 0, 1.0, 3.0, 12.0, -25.0, 45.0, -60.0, 90.0]))
            paso = rnd.uniform(8, 90)
            x, y = x + paso * math.cos(ang), y + paso * math.sin(ang)
            pts.append((x, y))
            kinds.append(rnd.choice(["bend", "bend", "corner", "curve", "vault", "junction"]))
        kinds[-1] = "end"
        p = {"layer": capa, "pts": pts, "vertex_kinds": kinds, "diam": rnd.choice([8.0, 12.0, 24.0]),
             "diam_unit": "in", "ab": False}
        if rnd.random() < 0.3 and len(pts) > 2:
            p["fillets"] = {rnd.randint(1, len(pts) - 2): rnd.uniform(5, 40)}
        pipes.append(p)
        for (vx, vy), kd in zip(pts, kinds):
            if kd == "vault" or rnd.random() < 0.08:
                vault_pts.append((vx + rnd.uniform(-2, 2), vy + rnd.uniform(-2, 2)))
                if rnd.random() < 0.5:
                    a = rnd.uniform(4, 16)
                    vaults_geo.append({"center": (vx, vy), "corners": [(vx - a, vy - a), (vx + a, vy - a),
                                                                      (vx + a, vy + a), (vx - a, vy + a)],
                                       "width_ft": 2 * a * FPP, "length_ft": 2 * a * FPP, "angle_deg": 0.0,
                                       "shape": "rect", "importable": True, "layer": "V-SSWR-MANH"})
                elif rnd.random() < 0.5:
                    vaults_geo.append({"center": (vx, vy), "circle": (vx, vy, 9.0), "shape": "circle",
                                       "width_ft": 18 * FPP, "length_ft": 18 * FPP, "importable": True})
    # acometidas: nacen («tee») sobre un tramo de una principal
    principales = [p for p in pipes if p["layer"] == "ALCANTARILLADO"]
    for _ in range(90):
        m = rnd.choice(principales)
        i = rnd.randrange(len(m["pts"]) - 1)
        (ax, ay), (bx, by) = m["pts"][i], m["pts"][i + 1]
        t = rnd.uniform(0.1, 0.9)
        q = (ax + (bx - ax) * t, ay + (by - ay) * t)
        L = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / L, (bx - ax) / L
        d = rnd.uniform(15, 50)
        pipes.append({"layer": "ALCANTARILLADO", "pts": [q, (q[0] + nx * d, q[1] + ny * d)],
                      "vertex_kinds": ["tee", "end"], "acometida": True, "diam": 6.0, "diam_unit": "in"})
    # bóvedas sueltas y algunas sin línea cerca
    for _ in range(25):
        vx, vy = rnd.uniform(0, 1500), rnd.uniform(0, 1500)
        vault_pts.append((vx, vy))
        vaults_geo.append({"center": (vx, vy), "corners": [(vx - 6, vy - 6), (vx + 6, vy - 6), (vx + 6, vy + 6),
                                                          (vx - 6, vy + 6)], "width_ft": 3.0, "length_ft": 3.0,
                           "shape": "rect", "importable": rnd.random() < 0.7})
    return pipes, vault_pts, vaults_geo


def _cadena(pipes, vault_pts, vaults_geo):
    """Los pasos de datos de la importación (los de `Main._importar_datos`, sobre listas sueltas)."""
    pipes = copy.deepcopy(pipes)
    inj = rec.inject_vault_vertices(pipes, list(vault_pts))
    n_ac = acometidas.unir_a_principal(pipes, range(len(pipes)), 0.8 * ZOOM)
    structures = model_ops.rebuild_structures(pipes, [])
    n_h = model_ops.hide_soft_vertex_structures(pipes, structures)
    geo = []
    for net, capa in (("gravity", "ALCANTARILLADO"), ("conduit", "ELECTRICO")):
        geo.append(model_ops.attach_vault_geometry(structures, copy.deepcopy(vaults_geo), net=net, utility=capa,
                                                   pipes=[p for p in pipes if p.get("layer") == capa]))
    n_cv = model_ops.attach_fillets(pipes, structures)
    nuevas, sin = quiebres_curvas.curvas_en_quiebres(pipes, structures, FPP)
    return dict(pipes=pipes, structures=structures, inj=inj, n_ac=n_ac, n_h=n_h, geo=geo, n_cv=n_cv,
                nuevas=[(s["x"], s["y"], s.get("cod")) for s in nuevas], sin=sin)


@pytest.fixture
def todo_contra_todo(monkeypatch):
    """Los índices «apagados»: cada consulta devuelve TODO, en orden (el recorrido de antes)."""
    def apagar():
        monkeypatch.setattr(indice_plano.IndiceUtilidades, "cerca", lambda self, x, y, r: list(range(len(self.firma))))
        monkeypatch.setattr(indice_plano.IndiceEstructuras, "en_caja",
                            lambda self, *a: (self._al_dia(), list(range(len(self.structures))))[1])
        monkeypatch.setattr(model_ops._VerticesDeBoveda, "de",
                            lambda self, vg, tol: model_ops._vertice_de_boveda(self.pipes, vg, tol))
        monkeypatch.setattr(acometidas, "_junto", lambda vertices, capa, q: any(
            math.dist(q, v) <= model_ops._TOL for cel in (vertices.get(capa) or {}).values() for v in cel))
        monkeypatch.setattr(vecindario.Vecindario, "de", lambda self, ip, margen: (self.pipes, ip, self.structures))
        monkeypatch.setattr(vecindario.Vecindario, "aplicar", lambda self, ip, antes, despues: None)
    return apagar


@pytest.mark.parametrize("semilla", [1, 2, 3, 4])
def test_misma_importacion_con_y_sin_indices(semilla, todo_contra_todo):
    pipes, vault_pts, vaults_geo = _red(semilla)
    rapido = _cadena(pipes, vault_pts, vaults_geo)
    todo_contra_todo()
    antes = _cadena(pipes, vault_pts, vaults_geo)
    assert rapido == antes
    # la red ejercita todo: buzones en las líneas, acometidas unidas, bóvedas, codos y curvas
    assert rapido["inj"][0] > 5 and rapido["n_ac"] > 5 and rapido["n_h"] > 5
    assert sum(g[0] for g in rapido["geo"]) > 10 and rapido["n_cv"] > 0 and len(rapido["nuevas"]) > 10


def test_misma_vista_previa_con_y_sin_indices(todo_contra_todo):
    from reconocimiento import recognition_quiebres as RQ
    pipes, vault_pts, _vaults_geo = _red(7)
    pls = [rec.RecognizedPolyline("C-SSWR-UNGD-E" if p["layer"] == "ALCANTARILLADO" else "C-ELEC-UNGD-E",
                                  p["layer"], list(p["pts"]), rec.utility_line_kind(p["layer"]),
                                  kinds=list(p["vertex_kinds"])) for p in pipes]
    res = []
    for capa in ("ALCANTARILLADO", "ELECTRICO"):
        mias = [pl for pl in pls if pl.utility_hint == capa]
        res.append(rec.RecognitionResult(capa, 0, 100.0 / 72.0, polylines=mias, polylines_joined=mias,
                                         polylines_raw=mias, vault_pts=list(vault_pts)))
    rapido = RQ.curvas_de_quiebres(copy.deepcopy(res), ZOOM)
    todo_contra_todo()
    antes = RQ.curvas_de_quiebres(copy.deepcopy(res), ZOOM)
    assert [sorted(v.items()) for v in rapido.values()] == [sorted(v.items()) for v in antes.values()]
    assert sum(len(v) for v in rapido.values()) > 5
