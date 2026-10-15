"""Acometidas reconocidas en redes por gravedad (`nucleo.acometidas`, pedido 2026-10-14)."""
import os
import sys

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]

from nucleo import acometidas, model_ops  # noqa: E402


def _red(layer):
    principal = {"layer": layer, "pts": [(0.0, 0.0), (100.0, 0.0)], "vertex_kinds": ["vault", "vault"]}
    acometida = {"layer": layer, "pts": [(40.0, 0.0), (40.0, 30.0)], "vertex_kinds": ["tee", "end"],
                 "acometida": True}
    return [principal, acometida]


def test_en_gravedad_la_acometida_es_un_nodo_nulo_de_su_tuberia():
    pipes = _red("ALCANTARILLADO")
    assert acometidas.unir_a_principal(pipes, range(2), 0.8) == 1
    assert pipes[0]["pts"] == [(0.0, 0.0), (40.0, 0.0), (100.0, 0.0)]
    assert pipes[0]["vertex_kinds"] == ["vault", acometidas.VERTICE, "vault"]
    structs = model_ops.rebuild_structures(pipes, [])
    model_ops.hide_soft_vertex_structures(pipes, structs)
    visibles = sorted((s["x"], s["y"]) for s in structs if not s.get("hidden"))
    nulas = sorted((s["x"], s["y"]) for s in structs if s.get("hidden"))
    assert visibles == [(0.0, 0.0), (100.0, 0.0)]          # los buzones de la principal
    assert nulas == [(40.0, 0.0), (40.0, 30.0)]            # la T y la punta del predio


def test_a_presion_no_se_toca_nada():
    pipes = _red("AGUA")
    assert acometidas.unir_a_principal(pipes, range(2), 0.8) == 0
    assert len(pipes[0]["pts"]) == 2


def test_solo_las_tuberias_de_la_importacion():
    pipes = _red("ALCANTARILLADO")
    assert acometidas.unir_a_principal(pipes, [1], 0.8) == 0      # la principal ya estaba
    assert len(pipes[0]["pts"]) == 2
