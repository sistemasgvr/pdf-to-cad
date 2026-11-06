"""Copiloto del proyecto: la lógica pura (sin ventana)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from nucleo import bitacora  # noqa: E402


def test_bitacora_marca_deshechas_por_vigentes():
    lista = []
    a = bitacora.agregar(lista, "tanda", "A", usuario="u")
    v1 = bitacora.vigentes(lista)
    b = bitacora.agregar(lista, "tanda", "B", usuario="u")
    bitacora.marcar(lista, v1)
    assert b["deshecha"] and not a["deshecha"]
    bitacora.marcar(lista, [a["id"], b["id"]])
    assert not b["deshecha"]


def test_vigentes_no_incluye_las_deshechas():
    lista = []
    a = bitacora.agregar(lista, "tanda", "A", usuario="u")
    bitacora.marcar(lista, [])
    assert a["deshecha"] and bitacora.vigentes(lista) == []


def test_entrada_guarda_quien_cuando_y_detalle():
    lista = []
    e = bitacora.agregar(lista, "conflictos", "R", [{"codigo": "AGUA-1", "antes": "1", "despues": "2",
                                                       "por_que": "x", "evidencia": ""}], usuario="ana", paso=3)
    assert e["usuario"] == "ana" and e["paso"] == 3 and e["fecha"] and e["detalle"][0]["codigo"] == "AGUA-1"


# ── intención y estado ──
import pytest  # noqa: E402

from ia.copiloto_intencion import CONFLICTOS, ESTADO, REVISION, intencion  # noqa: E402
from nucleo import copiloto_estado  # noqa: E402
from nucleo.conflictos import Conflicto  # noqa: E402
from nucleo.normas_validar import Aviso  # noqa: E402


@pytest.mark.parametrize("q,esperado", [
    ("¿Cómo vamos?", ESTADO), ("cuántos avisos tengo", ESTADO), ("qué falta para exportar", ESTADO),
    ("dime cuántos avisos de normativa tengo y hay que empezar a solucionarlos", REVISION),
    ("revisemos los avisos", REVISION), ("Revisar avisos", REVISION), ("resuelve los avisos de reconocimiento", REVISION),
    ("soluciona los conflictos", CONFLICTOS), ("resuelve los conflictos", CONFLICTOS), ("Resolver conflictos", CONFLICTOS),
    ("resuelve C-12", None), ("mueve AGUA-5 3 ft al norte", None), ("¿qué es un codo?", None),
    ("¿Cuántos conflictos hay y dónde están?", None), ("¿cuántos avisos tiene AGUA-5?", None)])
def test_intencion(q, esperado):
    assert intencion(q) == esperado


def test_estado_orden_y_exclusiones():
    avisos = [Aviso(0, 0, "tipo", "m", 0), Aviso(0, 0, "grosor", "m", 1), Aviso(0, 0, "angulo", "m", 2),
              Aviso(0, 0, "diametro", "m", 3, info=True), Aviso(0, 0, "largo", "m", 4, aprobado={"x": 1})]
    e = copiloto_estado.armar([Conflicto("C-1", "cruce", 0, 0)], avisos)
    assert [g.clave for g in e.grupos] == ["conflictos", "grosor", "tipo", "largo"]
    assert e.grupos[-1].pendientes == 0 and e.grupos[-1].aprobados == 1 and not e.listo


def test_estado_vacio_esta_listo():
    assert copiloto_estado.armar([], []).listo


def test_solo_aprobados_esta_listo():
    assert copiloto_estado.armar([], [Aviso(0, 0, "largo", "m", 4, aprobado={"x": 1})]).listo


# ── clasificar avisos ──
from nucleo import copiloto_cola as CC  # noqa: E402
from nucleo import diametro_continuidad as DCO  # noqa: E402


def _p(pts, d=None, layer="DRENAJE", cerca=()):
    p = {"layer": layer, "pts": pts, "diam": d or 12.0, "diam_plano": {"estado": "sin_dato", "cerca": list(cerca)}}
    if d:
        p["diam_elegido"] = True
    return p


def _red():
    """Una línea sin dato entre dos de 12": la del medio (1) sigue de frente a las dos."""
    return [_p([(0, 0), (100, 0)], 12.0), _p([(100, 0), (200, 0)]), _p([(200, 0), (300, 0)], 12.0)]


def _clasificar(avisos, pipes, cat=None, bancoducto=(), tamano=lambda i, d: "x", saltados=(), elegible=None):
    return CC.clasificar(avisos, pipes, cat, 0.3, (), bancoducto, tamano, saltados=saltados, elegible=elegible)


def test_continuidad_con_indice_igual_sin_indice():
    pipes = _red() + [_p([(150, 0), (150, 80)]), _p([(150, 80), (150, 160)], 8.0), _p([(0, 0), (0, 50)], layer="AGUA")]
    idx = DCO.indice(pipes)
    for i in range(len(pipes)):
        assert DCO.analizar(i, pipes, 0.3, (), idx) == DCO.analizar(i, pipes, 0.3)


def test_continuidad_alta_es_seguro():
    c = _clasificar([Aviso(0, 0, "grosor", "m", 1)], _red())
    assert c.items[0].nivel == CC.SEGURO and c.items[0].valor == 12.0 and c.items[0].motivo


def test_con_bancoducto_nunca_es_seguro():
    assert _clasificar([Aviso(0, 0, "grosor", "m", 1)], _red(), bancoducto={1}).items[0].nivel == CC.DECISION


def test_familia_sin_ese_tamano_nunca_es_seguro():
    c = _clasificar([Aviso(0, 0, "grosor", "m", 1)], _red(), tamano=lambda i, d: None)
    assert c.items[0].nivel != CC.SEGURO


def test_normativa_nunca_es_seguro():
    c = _clasificar([Aviso(0, 0, "diametro", "m", 0)], [_p([(0, 0), (9, 0)])])
    assert c.items[0].nivel == CC.DECISION


def test_tipo_unico_es_seguro_y_varios_es_decision():
    uno = {"tipos": [["DRENAJE", "COLECTOR"]]}
    dos = {"tipos": [["DRENAJE", "COLECTOR"], ["DRENAJE", "LATERAL"]]}
    a = [Aviso(0, 0, "tipo", "m", 0)]
    c = _clasificar(a, [_p([(0, 0), (9, 0)])], uno)
    assert c.items[0].nivel == CC.SEGURO and c.items[0].valor == "COLECTOR"
    assert _clasificar(a, [_p([(0, 0), (9, 0)])], dos).items[0].nivel == CC.DECISION


def test_tipo_que_ya_no_existe_es_decision():
    p = dict(_p([(0, 0), (9, 0)]), tipo="VIEJO")
    assert _clasificar([Aviso(0, 0, "tipo", "m", 0)], [p], {"tipos": [["DRENAJE", "COLECTOR"]]}).items[0].nivel == CC.DECISION


def test_saltados_no_aparecen_y_angulo_tampoco():
    pipes = [_p([(0, 0), (9, 0)])]
    a = Aviso(0, 0, "largo", "m", 0)
    assert not _clasificar([a, Aviso(0, 0, "angulo", "m", 0)], pipes, saltados={CC.clave_de(a, pipes)}).items


def test_rotulos_elegibles_son_propuesta():
    pipes = [_p([(0, 0), (9, 0)], cerca=[{"id": "R1"}])]
    a = [Aviso(0, 0, "grosor", "m", 0)]
    assert _clasificar(a, pipes, elegible=lambda e, p: True).items[0].nivel == CC.PROPUESTA
    assert _clasificar(a, pipes, elegible=lambda e, p: False).items[0].nivel == CC.DECISION


def test_continuidad_que_no_es_segura_es_propuesta():
    pipes = [_p([(0, 0), (100, 0)], 12.0), _p([(100, 0), (200, 0)]), _p([(200, 0), (300, 0)], 18.0)]
    assert _clasificar([Aviso(0, 0, "grosor", "m", 1)], pipes).items[0].nivel == CC.PROPUESTA


def test_grupos_juntan_el_mismo_mensaje():
    pipes = [_p([(0, 0), (9, 0)]), _p([(0, 9), (9, 9)])]
    c = _clasificar([Aviso(0, 0, "largo", 'Mide 10.5 ft: máximo 8"', 0), Aviso(1, 1, "largo", 'Mide 22 ft: máximo 8"', 1)], pipes)
    assert len(c.grupos()) == 1 and len(next(iter(c.grupos().values()))) == 2


def test_aviso_informativo_o_aprobado_no_entra():
    pipes = [_p([(0, 0), (9, 0)])]
    assert not _clasificar([Aviso(0, 0, "largo", "m", 0, info=True),
                            Aviso(0, 0, "largo", "m", 0, aprobado={"x": 1})], pipes).items


def test_conflictos_ocultos_nunca_dice_listo():
    e = copiloto_estado.armar([], [], conflictos_ocultos=True)
    assert not e.listo and copiloto_estado.CONFLICTOS_OCULTOS in e.notas


def test_sin_escala_nunca_dice_listo():
    e = copiloto_estado.armar([], [], sin_escala=True)
    assert not e.listo and copiloto_estado.SIN_ESCALA in e.notas


# ── revisión final ──
@pytest.mark.parametrize("q", ["¿Qué conflicto conviene resolver primero y por qué?",
                               "¿por qué no puedo resolver los conflictos?", "¿qué falta en la zona 1?"])
def test_preguntas_no_son_del_copiloto(q):
    assert intencion(q) is None


def test_al_abrir_la_bitacora_no_apunta_a_pasos_de_deshacer():
    assert bitacora.al_abrir([{"id": "a", "paso": 3}]) == [{"id": "a", "paso": None}]


def test_linea_sin_cerca_es_decision():
    pipes = [_p([(0, 0), (100, 0)], 12.0), _p([(100, 0), (200, 0)]), _p([(200, 0), (300, 0)], 18.0)]
    del pipes[1]["diam_plano"]["cerca"]
    assert _clasificar([Aviso(0, 0, "grosor", "m", 1)], pipes).items[0].nivel == CC.DECISION
