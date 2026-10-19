"""Cálculo de cruces, conflictos, accesorios y avisos EN SEGUNDO PLANO (pedido del usuario 2026-10-19: con
16 761 utilidades editar, dibujar o borrar trababa la ventana ~8 s).

Con un modelo grande (≥ `UMBRAL` utilidades) y el modelo recién cambiado, el redibujo es PROVISIONAL: dibuja
al instante las utilidades, buzones, leaders… y deja a la vista las marcas de antes (sin acciones: sus
listas quedan vacías mientras tanto), y un PROCESO aparte hace los cálculos sobre una COPIA del modelo con `Calculo`,
que usa los MISMOS métodos de `ventana_calculo.CalculoPlanoMixin` y las MISMAS claves de `_memo` que la
ventana. Al terminar, si el modelo sigue siendo el mismo (misma firma), sus resultados entran al memo de la
ventana y se redibuja: es el mismo resultado que calcularlo en el redibujo. Si el modelo cambió mientras
tanto, se descarta y se calcula el actual. Quien necesita los resultados ya (Tabla de datos, normativas,
Vista 3D, aprobar avisos) llama `_resultados_al_dia()`, que espera al cálculo (o calcula aquí mismo).
"""
from __future__ import annotations

import os
import pickle

from PySide6 import QtCore

from nucleo import memo_modelo, model_ops
from traduccion.i18n import t as _tr
from ui.ventana.ventana_calculo import CalculoPlanoMixin
from ui.ventana.ventana_conflictos import ConflictosMixin
from ui.ventana.ventana_dibujo import DibujoMixin

UMBRAL = int(os.environ.get("PDFCAD_CALCULO_FONDO_MIN", "3000"))   # utilidades
PARTES = ("cruces", "accesorios")
MB_POR_PARTE = 700              # memoria que pide cada proceso para decidir si van dos a la vez
_PARTES = ("pipes", "structures", "cross_connections", "normas_cat", "normas_aprobados", "duct_banks",
           "scale", "zoom")


class Calculo(CalculoPlanoMixin):
    """Lo mínimo de la ventana para correr sus cálculos sobre una copia del modelo (sin escena ni widgets)."""
    _pipe_z_at = DibujoMixin._pipe_z_at
    _union_civil = ConflictosMixin._union_civil
    _union_civil_calc = ConflictosMixin._union_civil_calc
    _indice_union = ConflictosMixin._indice_union
    _etq = staticmethod(ConflictosMixin._etq)
    _tipo = staticmethod(ConflictosMixin._tipo)

    def __init__(self, modelo, conflictos=True):
        for k, v in modelo.items():
            setattr(self, k, v)
        self.conflictos = conflictos
        self.datos = {}
        self._en_redibujo = True
        self._indice_redibujo = None

    def _memo(self, clave, fn, copiar=True):           # = Memo.obtener de la ventana
        if clave not in self.datos:
            self.datos[clave] = fn()
        valor = self.datos[clave]
        return memo_modelo.copia(valor) if copiar else valor

    def correr(self, partes=PARTES):
        """`partes`: «cruces» (buzones, cruces, conflictos) y/o «accesorios» (accesorios, avisos, ángulos,
        etiquetas). No comparten claves ni dependen una de otra: pueden ir en procesos distintos."""
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        with model_ops.memo_cotas():
            if "cruces" in partes and self.structures:
                self._calcular_vertices_buzones()
            if "cruces" in partes and self.conflictos:
                self._calcular_cruces()
            if "accesorios" in partes and ft_px and self.pipes:
                accs, normas, _fuera = self._calcular_accesorios(ft_px)
                self._preparar_etiquetas(accs, normas, ft_px)
        return self.datos


def calcular(datos_modelo, conflictos, idioma, partes=PARTES, progreso=None):
    """Trabajo del PROCESO aparte (`ui/comun/proceso`, trabajador «plano»): un hilo compartía el GIL con la
    ventana y cada llamada a Qt del repintado esperaba su turno (pintar 16 761 utilidades pasaba de 0.1 a
    ~7 s mientras calculaba). Devuelve {clave de `_memo`: valor}."""
    from traduccion import i18n_core
    if idioma:
        i18n_core.activate(idioma)
    return Calculo(pickle.loads(datos_modelo), conflictos).correr(partes)


class CalculoFondoMixin:
    def _calculo_en_fondo(self):
        """¿Este redibujo es provisional (los cálculos van al proceso)? Lo decide al empezar el redibujo."""
        m = getattr(self, "_memo_redibujo", None)
        if (m is None or m.firma is None or len(self.pipes) < UMBRAL or getattr(self, "_forzar_sincronico", False)
                or not self.scale or not self.zoom):
            return False
        if ("accesorios", self.scale / self.zoom) in m.datos:
            return False                                # ya calculado (deshacer / el proceso ya terminó)
        return True

    def _lanzar_calculo(self):
        """Al final de un redibujo provisional: el cálculo del modelo de ahora (uno a la vez). Con núcleos y
        RAM para dos procesos (`proceso_hijo.paralelos`), cruces y accesorios van a la vez («plano» y
        «plano-2»): mismo código, mismo resultado, la mitad de espera."""
        from traduccion import i18n_core
        from ui.comun import proceso, proceso_hijo
        m = self._memo_redibujo
        calc = getattr(self, "_calculo", None)
        if calc is not None and calc["faltan"]:
            return                                      # al terminar, si el modelo cambió, se lanza otro
        modelo = {k: getattr(self, k, None) for k in _PARTES}
        conflictos = not (hasattr(self, "chk_show_conflicts") and not self.chk_show_conflicts.isChecked())
        datos = pickle.dumps(modelo, pickle.HIGHEST_PROTOCOL)
        grupos = ([(p,) for p in PARTES] if proceso_hijo.paralelos(len(PARTES), MB_POR_PARTE) >= len(PARTES)
                  else [PARTES])
        calc = self._calculo = {"firma": m.firma, "faltan": len(grupos), "res": {}, "error": "", "tareas": []}
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(_tr("Actualizando conflictos y avisos…"))
        for k, partes in enumerate(grupos):
            tarea = proceso.Tarea("ui.ventana.calculo_fondo:calcular",
                                  (datos, conflictos, i18n_core.get_lang(), partes))
            tarea.terminado.connect(lambda r, e, c=calc: self._parte_terminada(c, r, e))
            calc["tareas"].append(tarea)
            proceso.trabajador("plano" if k == 0 else f"plano-{k + 1}").enviar(tarea)

    def _parte_terminada(self, calc, resultado, error):
        if calc["faltan"] <= 0:
            return
        calc["faltan"] -= 1
        if error:
            calc["error"] = calc["error"] or str(error)
        elif resultado:
            calc["res"].update(resultado)
        if calc["faltan"] == 0:
            self._calculo_terminado(calc)

    def _calculo_terminado(self, calc):
        m = getattr(self, "_memo_redibujo", None)
        if hasattr(self, "statusBar"):
            self.statusBar().clearMessage()
        if calc["error"]:
            if calc["error"] != "cancelado":
                print("[calculo_fondo] el cálculo aparte falló; se calcula aquí:" + chr(10) + calc["error"])
            if getattr(self, "_provisional", False) and m is not None and m.firma == calc["firma"]:
                self._forzar_sincronico = True
                try:
                    self._redraw()
                finally:
                    self._forzar_sincronico = False
            return
        if m is not None and m.firma == calc["firma"]:
            for k, v in calc["res"].items():
                m.datos.setdefault(k, v)
        if getattr(self, "_provisional", False):
            self._redraw()                              # con el memo lleno (o, si cambió, otro cálculo)

    def _resultados_al_dia(self):
        """Para quien necesita conflictos/avisos/accesorios ya: espera al cálculo o los calcula aquí."""
        if not getattr(self, "_provisional", False) or getattr(self, "_en_redibujo", False):
            return
        calc = getattr(self, "_calculo", None)
        m = getattr(self, "_memo_redibujo", None)
        if calc is not None and calc["faltan"] and m is not None and calc["firma"] == m.firma:
            lazo = QtCore.QEventLoop()
            for t in calc["tareas"]:
                t.terminado.connect(lambda *_a: lazo.quit() if not calc["faltan"] else None)
            if calc["faltan"]:
                lazo.exec()
        if getattr(self, "_provisional", False):        # el cálculo era de otro modelo, o falló
            self._forzar_sincronico = True
            try:
                self._redraw()
            finally:
                self._forzar_sincronico = False
