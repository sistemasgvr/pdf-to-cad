"""agregar_busqueda.py — dónde cae cada hoja del PDF que se agrega, buscado en SEGUNDO PLANO.

Pedido del usuario 2026-11-18 («Agregar utilidad desde otro PDF» con una 3.ª utilidad tardaba
minutos antes de mostrar nada): el compositor se abre al instante con las hojas del PDF nuevo y,
mientras el usuario las mira y marca, esta búsqueda (`hoja_calcada.calcar_trabajo`, trabajador
«agregar») ubica cada hoja sobre la hoja del editor y lo va avisando (`cambio`): la galería dice
«Cae en la hoja del editor» / «Buscando…» / «No cae…». Al continuar, la ventana ubica solo lo
marcado que falte (`ventana_agregar._agregando_recolocar`).

Estado por hoja nueva (fuente, hoja): `piezas` (las piezas calcadas, ya en su lugar) y `m`
(similaridad hoja → hoja compuesta). Sin Qt en los datos; la tarea y la señal sí.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6 import QtCore

TRABAJADOR = "agregar"

BUSCANDO, ENCAJA, NO_CAE = "buscando", "encaja", "no"


class BusquedaAgregar(QtCore.QObject):
    cambio = QtCore.Signal()

    def __init__(self, editor_dict: dict, fuentes_editor: Sequence[bytes], nuevas: Sequence[dict],
                 escala: float, nombres_editor: Sequence[str] = (), parent=None):
        super().__init__(parent)
        self.editor_dict = editor_dict
        self.fuentes_editor = list(fuentes_editor)
        self.nuevas = [dict(e) for e in nuevas]
        self.escala = float(escala)
        self.nombres_editor = list(nombres_editor)
        self.piezas: Dict[Tuple[int, int], List[dict]] = {}
        self.m: Dict[Tuple[int, int], Tuple[float, float, float, float]] = {}
        self.avance: Tuple[str, int, int] = ("", 0, 0)
        self.terminada = False
        self.cancelada = False
        self.error = ""
        self._tarea = None

    # ── consulta ─────────────────────────────────────────────────────────
    def estado(self, fuente: int, hoja: int) -> str:
        if (int(fuente), int(hoja)) in self.piezas:
            return ENCAJA
        return NO_CAE if self.terminada and not self.cancelada else BUSCANDO

    def ubicadas(self) -> List[Tuple[int, int]]:
        return sorted(self.piezas)

    def corriendo(self) -> bool:
        return self._tarea is not None and not self.terminada

    # ── trabajo ──────────────────────────────────────────────────────────
    def iniciar(self):
        from ui.comun import proceso
        t = proceso.Tarea("hoja.hoja_calcada:calcar_trabajo",
                          (self.editor_dict, self.fuentes_editor, [e["data"] for e in self.nuevas],
                           [e["name"] for e in self.nuevas], self.escala, self.nombres_editor))
        t.avance.connect(self._avance)
        t.terminado.connect(self._terminado)
        self._tarea = t
        proceso.trabajador(TRABAJADOR).enviar(t)

    def cancelar(self):
        """Deja de buscar (lo ya ubicado se conserva)."""
        if self._tarea is not None and not self.terminada:
            self.cancelada = True
            self.terminada = True
            self._tarea.cancelar()
            self.cambio.emit()

    def esperar(self, ms: int = 600_000) -> bool:
        """Espera el final (pruebas y quien lo necesite) atendiendo eventos. → terminó."""
        if self._tarea is None or self.terminada:
            return self.terminada
        lazo = QtCore.QEventLoop()
        self._tarea.terminado.connect(lambda *_a: lazo.quit())
        QtCore.QTimer.singleShot(ms, lazo.quit)
        if not self.terminada:
            lazo.exec()
        return self.terminada

    def poner(self, fuente: int, hoja: int, pieza: dict, m: Sequence[float]):
        clave = (int(fuente), int(hoja))
        self.piezas.setdefault(clave, []).append(dict(pieza))
        self.m.setdefault(clave, tuple(float(v) for v in m))

    @QtCore.Slot(object)
    def _avance(self, a):
        if not a:
            return
        if a[0] == "ubicada":
            _t, f, h, pieza, m = a
            self.poner(f, h, pieza, m)
            self.cambio.emit()
        elif a[0] == "detalle":
            self.avance = (str(a[1]), int(a[2] or 0), int(a[3] or 0))
            self.cambio.emit()

    @QtCore.Slot(object, str)
    def _terminado(self, res, err):
        if self.cancelada:
            return
        self.terminada = True
        if err and err != "cancelado":
            self.error = _resumen(err)
        elif res:
            # lo que dice el resultado manda (avisos que se perdieran en la cola)
            if res.get("comp"):
                ub = {(int(u["fuente"]), int(u["hoja"])): u["m"] for u in res.get("ubicaciones") or ()}
                piezas: Dict[Tuple[int, int], List[dict]] = {}
                for p in res["comp"]["pieces"]:
                    piezas.setdefault((int(p["source"]), int(p["page"])), []).append(dict(p))
                if sum(len(v) for v in piezas.values()) >= sum(len(v) for v in self.piezas.values()):
                    self.piezas = piezas
                    self.m = {k: tuple(float(v) for v in ub[k]) for k in piezas if k in ub}
        self.cambio.emit()


def _resumen(err: str) -> str:
    if err == "memoria":
        from traduccion.i18n import t as _tr
        return _tr("La hoja necesita más memoria de la que hay libre en el equipo.")
    lineas = [x for x in str(err).strip().splitlines() if x.strip()]
    return lineas[-1] if lineas else str(err)
