"""Chat de Civil 3D (reporte 2026-11-10): «No, cámbialo a -10» no daba tarjeta nueva y «sí, aplícalo» hacía que la IA
dijera «Cambio aplicado» sin cambiar nada. La app decide qué hacer con la propuesta pendiente y vigila a la IA."""
import pytest

from ia import civil3d_agente as A
from ia import civil3d_respuesta as R


@pytest.mark.parametrize("texto, clase, cambio", [
    ("si aplicalo", "si", False), ("Sí, aplícalo por favor", "si", False), ("ok", "si", False),
    ("dale", "si", False), ("confirmo", "si", False), ("perfecto, aplícala", "si", False),
    ("No, cámbialo a -10 pies", None, True), ("no", "no", False), ("descártalo", "no", False),
    ("no gracias", "no", False), ("No, a -5", None, True), ("mejor -5", None, True),
    ("¿qué cota tiene la tubería?", None, False), ("Cámbiala a -20", None, True),
    ("sube la tubería 10 pies", None, True), ("sí, pero a -10", None, True),
])
def test_clasificar_y_pide_cambio(texto, clase, cambio):
    assert R.clasificar(texto) == clase
    assert R.pide_cambio(texto) == cambio


def test_dice_aplicado():
    assert R.dice_aplicado("Cambio aplicado: la cota inicial de ALCANTARILLADO-36 - (1) ahora es -10.00 pies.")
    assert R.dice_aplicado("Listo, ya lo apliqué.")
    assert not R.dice_aplicado("Propuse el cambio: aplícalo con el botón de la tarjeta.")


class _Cliente:
    instrucciones = ""

    def herramientas(self):
        return [{"name": "proponer_cambio", "description": "", "inputSchema": {"type": "object", "properties": {}}},
                {"name": "buscar_tuberias", "description": "", "inputSchema": {"type": "object", "properties": {}}}]

    def llamar(self, nombre, args):
        if nombre == "proponer_cambio":
            return True, '{"id": "c1", "antes": "-0.49", "despues": "-10.00"}'
        return True, "[]"


def _agente(respuestas):
    pedidos = []

    def pedir(msgs, tools):
        pedidos.append(msgs)
        return respuestas.pop(0)
    return A.Agente(_Cliente(), pedir), pedidos


def test_pedido_de_cambio_sin_propuesta_insiste_una_vez():
    llamada = {"tool_calls": [{"function": {"name": "proponer_cambio", "arguments": {"elemento": "X", "valor": -10}}}]}
    ag, pedidos = _agente([{"content": "La cota cambia de -0.49 a -10.00."}, llamada,
                           {"content": "Propuse cambiar la cota a -10.00."}])
    res = ag.preguntar("No, cámbialo a -10 pies")
    assert len(res.propuestas) == 1 and res.propuestas[0]["id"] == "c1"
    assert A.RECORDATORIO_CAMBIO in pedidos[1][-1]["content"]


def test_la_ia_no_puede_decir_que_aplico():
    ag, _ = _agente([{"content": "Cambio aplicado: ahora es -10."}, {"content": "Cambio aplicado: ahora es -10."}])
    res = ag.preguntar("si aplicalo")
    assert A.NADA_APLICADO in res.texto
