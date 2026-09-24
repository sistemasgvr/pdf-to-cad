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


def test_hide_soft_vertex_structures():
    """Vértices bend/corner/curve de pipes reconocidas → CAJA oculta; bóvedas,
    extremos y vértices compartidos con una bóveda de otra pipe siguen visibles."""
    from model_ops import rebuild_structures, hide_soft_vertex_structures
    pipes = [
        {"layer": "ELECTRICO", "pts": [(0, 0), (100, 0), (200, 0), (300, 0)],
         "vertex_kinds": ["end", "bend", "vault", "corner"]},
        # otra pipe reconocida cuyo vértice (300,0) SÍ es bóveda → debe quedar visible
        {"layer": "ELECTRICO", "pts": [(300, 0), (300, 100)], "vertex_kinds": ["vault", "end"]},
        # pipe manual (sin vertex_kinds): todos reales
        {"layer": "ELECTRICO", "pts": [(500, 0), (600, 0)]},
    ]
    structs = rebuild_structures(pipes, [])
    n = hide_soft_vertex_structures(pipes, structs)
    assert n == 1
    by_xy = {(round(s["x"]), round(s["y"])): s for s in structs}
    assert by_xy[(100, 0)]["hidden"] is True          # bend sin bóveda
    assert by_xy[(200, 0)]["hidden"] is False         # vault
    assert by_xy[(300, 0)]["hidden"] is False         # corner aquí, vault en la otra pipe
    assert by_xy[(0, 0)]["hidden"] is False           # extremo
    assert by_xy[(500, 0)]["hidden"] is False         # manual
    # Idempotente y el flag sobrevive a un rebuild posterior
    assert hide_soft_vertex_structures(pipes, structs) == 0
    structs2 = rebuild_structures(pipes, structs)
    assert {(round(s["x"]), round(s["y"])): s["hidden"] for s in structs2}[(100, 0)] is True


def test_attach_vault_geometry_asocia_medidas_a_la_caja():
    from model_ops import attach_vault_geometry, rebuild_structures
    pipes = [{"layer": "ELECTRICO", "pts": [(0, 0), (100, 0), (200, 0)]}]
    structures = rebuild_structures(pipes, [])
    vg = [{"center": (101.0, 2.0), "corners": [(90, -10), (112, -10), (112, 10), (90, 10)], "shape": "rect",
           "width_ft": 6.3, "length_ft": 8.5, "angle_deg": 0.0, "orphan": False, "importable": True},
          # huérfana de una capa de estructuras PROPUESTAS / postes: no se importa
          {"center": (500.0, 500.0), "corners": None, "shape": "circle", "width_ft": 4.0, "length_ft": 4.0,
           "angle_deg": 0.0, "orphan": True, "importable": False},
          # huérfana de una capa de bóvedas reales (VALT): CAJA suelta con su contorno
          {"center": (700.0, 300.0), "corners": [(680, 280), (720, 280), (720, 320), (680, 320)], "shape": "rect",
           "width_ft": 9.9, "length_ft": 16.2, "angle_deg": 90.0, "orphan": True, "importable": True}]
    done, created = attach_vault_geometry(structures, vg)
    assert (done, created) == (2, 1)
    st = next(s for s in structures if abs(s["x"] - 100) < 1e-9)
    assert st["shape"] == "rect" and st["width_ft"] == 6.3 and st["length_ft"] == 8.5 and len(st["outline"]) == 4
    alone = next(s for s in structures if s.get("standalone"))
    assert (alone["x"], alone["y"]) == (700.0, 300.0) and alone["net"] == "conduit" and alone["cod"].startswith("CAJA-")
    assert alone["width_ft"] == 9.9 and len(alone["outline"]) == 4 and not alone["hidden"]
    n = len(structures)
    # rebuild conserva la geometría por coordenada y la caja suelta tal cual
    again = rebuild_structures(pipes, structures)
    st2 = next(s for s in again if abs(s["x"] - 100) < 1e-9)
    assert st2.get("width_ft") == 6.3 and st2.get("outline") == st["outline"]
    assert len(again) == n and sum(1 for s in again if s.get("standalone")) == 1
    assert len({s["cod"] for s in again}) == len(again)                    # códigos únicos
    # segunda pasada (re-import): no duplica la suelta
    done2, created2 = attach_vault_geometry(again, vg)
    assert created2 == 0 and sum(1 for s in again if s.get("standalone")) == 1


def test_attach_vault_geometry_drenaje_crea_buzon_de_gravedad():
    from model_ops import attach_vault_geometry
    structures = []
    vault = [{"center": (50.0, 80.0), "corners": [(40, 70), (60, 70), (60, 90), (40, 90)],
              "shape": "rect", "width_ft": 4.0, "length_ft": 5.0,
              "angle_deg": 0.0, "orphan": True, "importable": True}]
    done, created = attach_vault_geometry(
        structures, vault, net="gravity", utility="DRENAJE")
    assert (done, created) == (1, 1)
    assert structures[0]["net"] == "gravity"
    assert structures[0]["utility"] == "DRENAJE"
    assert structures[0]["cod"].startswith("BZ-")


def test_redes_coincidentes_conservan_estructuras_separadas_por_tipo():
    from model_ops import rebuild_structures, hide_soft_vertex_structures
    pipes = [
        {"layer": "ELECTRICO", "pts": [(0, 0), (100, 0)],
         "vertex_kinds": ["end", "corner"]},
        {"layer": "DRENAJE", "pts": [(100, 0), (100, 100)],
         "vertex_kinds": ["vault", "end"]},
    ]
    structures = rebuild_structures(pipes, [])
    at_crossing = [s for s in structures if abs(s["x"] - 100) < 1e-9 and abs(s["y"]) < 1e-9]
    assert {s["net"] for s in at_crossing} == {"conduit", "gravity"}
    hide_soft_vertex_structures(pipes, structures)
    by_net = {s["net"]: s for s in at_crossing}
    assert by_net["conduit"]["hidden"] is True
    assert by_net["gravity"]["hidden"] is False


def test_fillet_geo_arco_tangente_y_recorte():
    import math
    from model_ops import fillet_geo
    # esquina de 90°: T = r, centro a r·√2 de la esquina, arco de 90°
    g = fillet_geo((0.0, 100.0), (0.0, 0.0), (100.0, 0.0), 30.0)
    assert g and not g["clamped"] and abs(g["T"] - 30.0) < 1e-9
    assert math.dist(g["t1"], (0.0, 30.0)) < 1e-9 and math.dist(g["t2"], (30.0, 0.0)) < 1e-9
    assert abs(g["center"][0] - 30.0) < 1e-9 and abs(g["center"][1] - 30.0) < 1e-9
    assert all(abs(math.dist(q, g["center"]) - 30.0) < 1e-9 for q in g["arc"])
    assert math.dist(g["arc"][0], g["t1"]) < 1e-9 and math.dist(g["arc"][-1], g["t2"]) < 1e-9
    # el radio no entra en la pata corta (20 px): se recorta al 90 % y baja el radio
    g2 = fillet_geo((0.0, 20.0), (0.0, 0.0), (100.0, 0.0), 30.0)
    assert g2["clamped"] and abs(g2["T"] - 18.0) < 1e-9 and abs(g2["r"] - 18.0) < 1e-9
    # recta o sin radio: nada
    assert fillet_geo((-10.0, 0.0), (0.0, 0.0), (10.0, 0.0), 30.0) is None
    assert fillet_geo((0.0, 10.0), (0.0, 0.0), (10.0, 0.0), 0.0) is None
