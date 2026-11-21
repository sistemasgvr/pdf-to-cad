"""Válvulas con tubería a cada lado (2026-11-21): la punta libre junto a una válvula se prolonga hasta la principal."""
from nucleo import valvulas_conectar as VC


def _red():
    principal = {"layer": "AGUA", "pts": [(0.0, 0.0), (100.0, 0.0)], "vertex_kinds": ["end", "end"]}
    ramal = {"layer": "AGUA", "pts": [(50.0, 40.0), (50.0, 10.0)], "vertex_kinds": ["end", "end"]}   # termina en la válvula
    v = {"x": 50.0, "y": 8.0, "utilidad": "AGUA", "sim_w": 5.0, "sim_h": 5.0}
    return [principal, ramal], [v]


def test_la_punta_libre_llega_a_la_principal_por_su_recta():
    pipes, vs = _red()
    hechos = VC.conectar(pipes, vs)
    assert len(hechos) == 1
    x, y = pipes[1]["pts"][-1][:2]
    assert abs(x - 50.0) < 1e-9 and abs(y) < 1e-9 and pipes[1]["vertex_kinds"][-1] == "tee"
    assert pipes[0]["pts"] == [(0.0, 0.0), (100.0, 0.0)]            # la principal no se toca


def test_es_idempotente_y_no_toca_lo_ya_conectado_ni_lo_lejano_ni_otra_utilidad():
    pipes, vs = _red()
    VC.conectar(pipes, vs)
    assert VC.conectar(pipes, vs) == []                              # ya toca: no cambia nada
    pipes, vs = _red(); pipes[0]["pts"] = [(0.0, -500.0), (100.0, -500.0)]   # principal lejos
    assert VC.conectar(pipes, vs) == []
    pipes, vs = _red(); pipes[0]["layer"] = "GAS"                    # otra utilidad
    assert VC.conectar(pipes, vs) == []
    pipes, vs = _red(); pipes[0]["pts"] = [(40.0, 0.0), (60.0, 0.0)]
    pipes[1]["pts"] = [(50.0, 40.0), (50.0, 10.0)]; pipes[0]["pts"] = [(0.0, 9.9), (100.0, 10.2)]  # casi paralela no aplica aquí
    assert VC.conectar(pipes, vs) == []                              # ya toca (a ≤ 0.6 px)
