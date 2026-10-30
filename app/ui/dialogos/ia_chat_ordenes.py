"""Órdenes en el chat de la IA (pedido del usuario 2026-10-30), mezcla de `PreguntaDialog`.

    «mueve AGUA-5 3 ft al norte»
      → la IA lo traduce a UNA acción del catálogo (`ia/acciones.interpretar`, en un hilo)
      → la app la valida, la describe y prueba sus consecuencias (`Main.orden_preparar`)
      → el chat muestra «Entendí: … · Consecuencias: … · ¿Lo hago?» con «Sí, hazlo» / «No»
      → Sí: `Main.orden_ejecutar` (un paso de deshacer). No: «¿Qué cambio?» y el mensaje siguiente CORRIGE el
        pedido (la IA recibe lo que entendió antes y la corrección). Si falta un dato, la IA pregunta.

Una pregunta normal (o lo que la IA no reconoce como orden) sigue el camino de siempre (`consulta.preguntar`).
"""
from __future__ import annotations

import threading

from PySide6 import QtCore

from ia import acciones as AC
from ia import alcance as A
from ia import proveedor as P
from traduccion.i18n import t as _tr


class _SenalesOrden(QtCore.QObject):
    listo = QtCore.Signal(object, object)            # (turno, interpretación)
    fallo = QtCore.Signal(object, str)


class OrdenesMixin:
    def _iniciar_ordenes(self):
        self._orden_pendiente = None                  # {"pedido", "entendido"} tras un «No» o una repregunta
        self._sen_orden = _SenalesOrden(self)
        self._sen_orden.listo.connect(self._al_orden)
        self._sen_orden.fallo.connect(self._al_fallo)

    def _es_turno_de_orden(self, q):
        """¿Este mensaje va por el camino de las órdenes? (un pedido de hacer algo, o la corrección de uno)."""
        if A.revisar(q) in (A.INYECCION, A.CODIGO):
            return False                             # lo bloquea el camino de siempre, con su texto fijo
        return self._orden_pendiente is not None or AC.es_orden(q)

    def _empezar_orden(self, turno, prov, datos, estado):
        """Pide a la IA que traduzca el pedido (en un hilo). La respuesta llega a `_al_orden`."""
        q = turno["pregunta"]
        anterior = self._orden_pendiente
        materiales, tipos, _f = self.win._ia_opciones_orden()
        turno["texto"] = ""
        turno["orden_en_curso"] = True

        def correr():
            try:
                interp = AC.interpretar(prov, q, datos, materiales, tipos, anterior=anterior,
                                        cancelado=lambda: estado["cancelado"])
                self._sen_orden.listo.emit(turno, interp)
            except P.ErrorIA as e:
                self._sen_orden.fallo.emit(turno, str(e))
            except Exception as e:                    # noqa: BLE001 (se muestra en el chat)
                self._sen_orden.fallo.emit(turno, f"{type(e).__name__}: {e}")
        threading.Thread(target=correr, name="pdfcad-ia-orden", daemon=True).start()

    def _al_orden(self, turno, interp):
        turno.pop("orden_en_curso", None)
        pedido = (self._orden_pendiente or {}).get("pedido") or turno["pregunta"]
        if interp.get("accion") == "ninguna":         # era una pregunta: el camino de siempre
            self._orden_pendiente = None
            self._activo = None
            self._ocupado(False)
            return self._preguntar_normal(turno)
        if interp.get("accion") is None:              # falta un dato: la IA pregunta
            self._orden_pendiente = {"pedido": pedido, "entendido": ""}
            turno["texto"], turno["estado"] = interp.get("pregunta") or "", "listo"
            return self._terminar()
        o, que, cons = self.win.orden_preparar(interp, self.win._ia_datos())
        if o.error:
            self._orden_pendiente = {"pedido": pedido, "entendido": interp.get("entendido", "")}
            turno["texto"], turno["estado"] = o.error, "listo"
            return self._terminar()
        self._orden_pendiente = None
        turno["orden"] = {"obj": o, "que": que, "cons": cons, "estado": "confirmar", "pedido": pedido,
                          "entendido": interp.get("entendido", ""), "resultado": ""}
        turno["texto"], turno["estado"] = que, "listo"
        self._terminar()

    def _confirmar_orden(self, i, si):
        tu = self.turnos[i] if 0 <= i < len(self.turnos) else None
        od = (tu or {}).get("orden")
        if not od or od["estado"] != "confirmar":
            return
        if si:
            try:
                od["resultado"] = self.win.orden_ejecutar(od["obj"])
                od["estado"] = "hecho"
            except Exception as e:                    # noqa: BLE001 (se muestra en el chat)
                od["resultado"] = _tr("No se pudo hacer: {e}").format(e=e)
                od["estado"] = "error"
            self._orden_pendiente = None
        else:
            od["estado"] = "cancelado"
            od["resultado"] = _tr("No hice nada. ¿Qué entendí mal? Dime qué cambio (por ejemplo otra utilidad u "
                                  "otra cantidad) y te lo vuelvo a proponer.")
            self._orden_pendiente = {"pedido": od["pedido"], "entendido": od["que"]}
        self._pintar(abajo=True)
        self.entrada.setFocus()
