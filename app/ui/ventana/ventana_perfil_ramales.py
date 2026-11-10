"""Ramales del perfil (mezcla de `PerfilMixin`): abrir el perfil del ramal de una T/Y/cruz y volver.

Movido tal cual de `ventana_perfil` (2026-11-08)."""
from __future__ import annotations

import math

from PySide6 import QtGui, QtWidgets

from nucleo import model_ops, perfil_recorrido as PR
from traduccion.i18n import t as _tr


class RamalesPerfilMixin:
    def _perfil_ramales(self, k):
        rec = self._perfil_rec
        if rec is None or not (0 <= k < len(rec.nodos)):
            return []
        return PR.ramales(rec, k)

    def _es_origen(self, k):
        """¿El nodo `k` es la T desde la que se abrió este ramal? (su rótulo = volver)."""
        pila = getattr(self, "_perfil_pila", None)
        rec = self._perfil_rec
        if not pila or rec is None or not (0 <= k < len(rec.nodos)):
            return False
        x, y = rec.grafo.nodos[rec.nodos[k]]
        ox, oy = pila[-1][3]
        return math.hypot(x - ox, y - oy) <= max(PR.TOL_FT / max(self._ft(), 1e-9), 1.0)

    def perfil_ramal(self, k, indice=None):
        """Abre el perfil del ramal que sale del nodo `k` (con varios, un menú para elegir; `indice` lo elige).
        El perfil de ahora queda en la pila de «Volver». En el perfil de un ramal, su T de origen vuelve."""
        if self._es_origen(k):
            return self.perfil_volver()
        es = self._perfil_ramales(k)
        if not es:
            return None
        if indice is None and len(es) > 1:
            g = self._perfil_rec.grafo
            m = QtWidgets.QMenu(self)
            for j, e in enumerate(es):
                ar = g.aristas[e]
                p = self.pipes[ar.pipe]
                m.addAction(_tr("Ramal {n}").format(n=p.get("name") or model_ops.nombre_por_defecto(p, ar.pipe)),
                            lambda j=j: self.perfil_ramal(k, j))
            m.exec(QtGui.QCursor.pos())
            return None
        e = es[indice or 0]
        rec = PR.ramal(self._perfil_rec.grafo, self._perfil_rec.nodos[k], e)
        PR.marcar_soleras(rec.grafo, self.pipes)
        rec = PR.rehacer(rec)
        origen = self._perfil_rec.grafo.nodos[self._perfil_rec.nodos[k]]
        self._perfil_pila.append((self._perfil_anclas, getattr(self, "_perfil_nombre", None),
                                  self._perfil_titulo_corto(), origen))
        self._perfil_poner(rec, encuadrar=True, a=None)
        return rec

    def perfil_volver(self):
        """Vuelve al perfil desde el que se abrió el ramal."""
        if not self._perfil_pila:
            return False
        anclas, nombre, _t, _o = self._perfil_pila.pop()
        rec = self._rec_de_anclas(*anclas) if anclas else None
        if rec is None:
            self._perfil_pila = []
            return False
        self._perfil_poner(rec, encuadrar=True, nombre=nombre, a=anclas[0])
        return True

    def _perfil_titulo_corto(self):
        d = getattr(self, "_perfil_datos", None)
        return (getattr(self, "_perfil_nombre", None) or (d.red if d else "")) or _tr("Perfil")
