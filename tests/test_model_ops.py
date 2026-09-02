"""Pruebas de humo de las operaciones de modelo puras (model_ops.py), sin Qt.

Cubren la auto-detección de buzones y el conteo de conexiones, ambas con lógica
geométrica sutil (tolerancia de coincidencia, reconciliación por coordenada,
extremos vs vértices intermedios).
"""
import model_ops


def _gravity_pipe(pts, layer="ALCANTARILLADO"):
    return {"layer": layer, "pts": pts, "world": False}


def test_detecta_buzones_en_vertices_de_gravedad():
    pipes = [_gravity_pipe([(0, 0), (100, 0), (200, 0)])]
    out = model_ops.rebuild_structures(pipes, [])
    xs = sorted(s["x"] for s in out)
    assert xs == [0, 100, 200]                    # un buzón por vértice
    assert all(s["net"] == "gravity" for s in out)
    assert all(s["cod"].startswith("BZ-") for s in out)
    assert len({s["cod"] for s in out}) == 3      # códigos únicos


def test_presion_no_genera_buzones():
    pipes = [_gravity_pipe([(0, 0), (50, 0)], layer="AGUA")]
    assert model_ops.rebuild_structures(pipes, []) == []


def test_reconcilia_ediciones_por_coordenada():
    pipes = [_gravity_pipe([(0, 0), (100, 0)])]
    # Estructura previa editada por el usuario en (0,0).
    prev = [{"cod": "BZ-MIO", "x": 0, "y": 0, "rim": 55.5, "sump": 40.0,
             "part": "AeccX", "part_size": "48 in", "covered": False,
             "hidden": True, "net": "gravity", "world": False}]
    out = model_ops.rebuild_structures(pipes, prev)
    bz0 = [s for s in out if s["x"] == 0][0]
    assert bz0["cod"] == "BZ-MIO"                  # se preserva el código editado
    assert bz0["rim"] == 55.5 and bz0["sump"] == 40.0
    assert bz0["part"] == "AeccX" and bz0["part_size"] == "48 in"
    assert bz0["covered"] is False and bz0["hidden"] is True


def test_buzones_world_se_conservan_aparte():
    pipes = [_gravity_pipe([(0, 0), (100, 0)])]
    world = [{"cod": "EXCEL-1", "x": 999, "y": 999, "world": True}]
    out = model_ops.rebuild_structures(pipes, world)
    assert any(s.get("world") and s["cod"] == "EXCEL-1" for s in out)
    assert any(not s.get("world") and s["x"] == 0 for s in out)


def test_bz_segment_count_extremos_vs_intermedios():
    pipes = [_gravity_pipe([(0, 0), (100, 0), (200, 0)])]
    # extremo (una sola punta de tramo) → 1
    assert model_ops.bz_segment_count(pipes, {"x": 0, "y": 0}) == 1
    assert model_ops.bz_segment_count(pipes, {"x": 200, "y": 0}) == 1
    # vértice intermedio (entra + sale) → 2
    assert model_ops.bz_segment_count(pipes, {"x": 100, "y": 0}) == 2
    # lejos de todo → 0
    assert model_ops.bz_segment_count(pipes, {"x": 500, "y": 500}) == 0
    # cruce de dos tuberías en el mismo punto → 2 (una punta de cada una)
    pipes2 = [_gravity_pipe([(0, 0), (50, 0)]), _gravity_pipe([(50, 0), (50, 50)])]
    assert model_ops.bz_segment_count(pipes2, {"x": 50, "y": 0}) == 2


def test_bz_segment_count_sin_coordenada():
    assert model_ops.bz_segment_count([], {"x": None, "y": None}) == 0


# ── Cotas por tramo: interpolación / migración / snapshot ──
def test_interp_vertex_z_lineal_sin_overrides():
    pts = [(0, 0), (10, 0), (20, 0), (30, 0)]     # equiespaciados
    z = model_ops.interp_vertex_z(pts, 100.0, 130.0, {})
    assert z == [100.0, 110.0, 120.0, 130.0]      # interpolación lineal por distancia


def test_interp_vertex_z_respeta_override_intermedio():
    pts = [(0, 0), (10, 0), (20, 0), (30, 0)]
    z = model_ops.interp_vertex_z(pts, 100.0, 130.0, {2: 200.0})
    assert z[0] == 100.0 and z[3] == 130.0
    assert z[2] == 200.0                          # ancla fijada
    assert z[1] == 150.0                          # interpola 100→200 a mitad
    assert z[3] == 130.0


def test_interp_vertex_z_casos_borde():
    assert model_ops.interp_vertex_z([], 5, 9, {}) == []
    assert model_ops.interp_vertex_z([(0, 0)], 5, 9, {}) == [5]
    # longitud cero (vértices coincidentes) → no divide por cero; ambos toman za
    assert model_ops.interp_vertex_z([(0, 0), (0, 0)], 5, 9, {}) == [5, 5]


def test_migrate_vertex_inv_formato_viejo_a_nuevo():
    p = {"vertex_inv": {1: 100.0, 2: 90.0}}
    model_ops.migrate_vertex_inv(p)
    assert "vertex_inv" not in p
    assert p["vertex_inv_out"] == {1: 100.0, 2: 90.0}
    assert p["vertex_inv_in"] == {1: 100.0, 2: 90.0}
    # idempotente: si ya está migrado, no pisa
    p2 = {"vertex_inv_out": {1: 1.0}, "vertex_inv_in": {1: 2.0}}
    model_ops.migrate_vertex_inv(p2)
    assert p2["vertex_inv_out"] == {1: 1.0} and p2["vertex_inv_in"] == {1: 2.0}


# ── pipe_at_vertex ──
def test_pipe_at_vertex_encuentra_por_cercania():
    p = _gravity_pipe([(0, 0), (100, 0)])
    pipes = [p]
    assert model_ops.pipe_at_vertex(pipes, 0, 0) is p           # exacto
    assert model_ops.pipe_at_vertex(pipes, 100, 5) is p         # dentro de tol (14)
    assert model_ops.pipe_at_vertex(pipes, 50, 50) is None      # lejos de todo vértice
    # ignora tuberías 'world' (importadas de Excel, sin pts editables)
    assert model_ops.pipe_at_vertex([{"world": True, "pts": [(0, 0)]}], 0, 0) is None


# ── leader_geo (4 orientaciones) ──
def _pxft(ft):   # conversión trivial pies→px para el test (determinista)
    return ft * 4.0


def test_leader_geo_simple_solo_flecha():
    ld = {"arrow": (0, 0), "tp": (50, 0), "text": "", "simple": True}
    g = model_ops.leader_geo(ld, _pxft)
    assert g["segs"] == [[(0, 0), (50, 0)]]                     # cabeza → final
    assert g["label_pos"] == (50, 0) and g["rot"] == 0


def test_leader_geo_horizontal_vertical_diagonal():
    base = {"arrow": (0, 0), "tp": (100, 0), "text": "AB"}
    gh = model_ops.leader_geo({**base, "orient": "h"}, _pxft)
    assert gh["rot"] == 0 and gh["side"] in ("right", "left")
    gv = model_ops.leader_geo({**base, "tp": (0, 100), "orient": "v"}, _pxft)
    assert gv["rot"] == -90 and gv["cad_rot"] == 90
    gd = model_ops.leader_geo({**base, "tp": (80, 60), "orient": "d"}, _pxft)
    assert len(gd["segs"][0]) == 3                              # flecha → 2º clic → landing
    # H depende de px_for_ft (usa size_ft o LEADER_TEXT_FT por defecto)
    assert gh["H"] > 0 and gh["cad_h"] > 0


def test_snapshot_congela_intermedios_y_evita_cascada():
    # 4 vértices, 3 tramos. Sin overrides al inicio.
    p = {"pts": [(0, 0), (10, 0), (20, 0), (30, 0)], "inv_start": 100.0, "inv_end": 130.0}
    model_ops.snapshot_seg_values(p)
    # Los intermedios (1 y 2) quedan congelados como overrides = su valor auto.
    assert p["vertex_inv_out"] == {1: 110.0, 2: 120.0}
    assert p["vertex_inv_in"] == {1: 110.0, 2: 120.0}
    # Ahora editar el vértice 2 NO recalcula el 1 (ya es override fijo).
    p["vertex_inv_out"][2] = 999.0
    model_ops.snapshot_seg_values(p)              # idempotente: no toca los ya fijados
    assert p["vertex_inv_out"][1] == 110.0        # el 1 se mantiene (no cascada)
    assert p["vertex_inv_out"][2] == 999.0
