"""Lo reconocido entra ENCIMA sin repetir lo que ya está dibujado (`nucleo.reconocer_mas`).

Recomendación del usuario (2026-11-12). Desde el plan 2026-11-16 (Tarea 9) ya no hay «Reconocer más capas de esta
hoja…»: cada ▶ del panel «Reconocer» importa encima (`ventana_importar_parte`, sus pruebas en
`test_importar_parte`); aquí queda la regla pura.
"""
from nucleo import reconocer_mas


def test_quitar_repetidas_solo_lo_que_corre_entero_sobre_su_capa():
    hecho = [{"layer": "DRENAJE", "pts": [(0, 0), (100, 0), (100, 50)]}]
    igual = {"layer": "DRENAJE", "pts": [(0.5, 0.4), (100.3, 0), (100, 49.6)]}
    parte = {"layer": "DRENAJE", "pts": [(20, 0), (80, 0)]}
    sigue = {"layer": "DRENAJE", "pts": [(50, 0), (180, 0)]}          # se sale de lo dibujado
    otra_capa = {"layer": "AGUA", "pts": [(0, 0), (100, 0)]}
    abandonada = {"layer": "DRENAJE", "ab": True, "pts": [(0, 0), (100, 0)]}
    quedan, n = reconocer_mas.quitar_repetidas(hecho, [igual, parte, sigue, otra_capa, abandonada], 2.0)
    assert n == 2
    assert quedan == [sigue, otra_capa, abandonada]
