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

from nucleo import avance, memo_modelo, model_ops
from ui.ventana.calculo_avance import AvanceCalculo
from ui.ventana.ventana_calculo import CalculoPlanoMixin
from ui.ventana.ventana_conflictos import ConflictosMixin
from ui.ventana.ventana_dibujo import DibujoMixin

UMBRAL = int(os.environ.get("PDFCAD_CALCULO_FONDO_MIN", "3000"))   # utilidades
PARTES = ("cruces", "accesorios")
MB_POR_PARTE = 700              # memoria que pide cada proceso para decidir si van dos a la vez
_PARTES = ("pipes", "structures", "cross_connections", "normas_cat", "normas_aprobados", "duct_banks",
           "scale", "zoom")
# Cuánto pesa cada cálculo de su parte (s con AGUA 2): el proceso avisa cuánto lleva (barra de la barra de
# estado, `calculo_avance`). «union» va dentro de «clasificar_cruces» (ya contado ahí).
PESOS = {"cruces": {"vertices_buzones": 0.05, "cruces_presion": 0.64, "juntas": 0.41, "clasificar_cruces": 2.87,
                    "escalones": 0.05, "codos": 0.02, "retorno": 0.04, "choques": 0.54},
         "accesorios": {"accesorios": 2.54, "normas": 0.22, "angulos": 0.63, "etiquetas_accesorios": 0.40}}


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
        self._hecho = {}
        self._en_redibujo = True
        self._indice_redibujo = None

    def _memo(self, clave, fn, copiar=True):           # = Memo.obtener de la ventana
        if clave not in self.datos:
            self.datos[clave] = fn()
            nombre = clave[0] if isinstance(clave, tuple) and clave else clave
            for parte, pesos in PESOS.items():         # avance (solo avisa: el resultado es el mismo)
                if nombre in pesos:
                    hecho = self._hecho.get(parte, 0.0) + pesos[nombre]
                    self._hecho[parte] = hecho
                    avance.avisar(parte, int(hecho * 1000), int(sum(pesos.values()) * 1000))
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


def calentar(progreso=None):
    """Trabajo vacío: el proceso importa este módulo (y con él los cálculos) antes de que llegue el primer
    cálculo de verdad. Devuelve None."""
    return None


class CalculoFondoMixin:
    def _calentar_calculo(self, n_utilidades):
        """Al abrir un proyecto grande, los procesos del cálculo arrancan e importan sus módulos MIENTRAS la
        ventana lee la hoja y dibuja (2026-10-19, 16 761 utilidades: los avisos llegaban ~3 s más tarde por
        el arranque). No calcula nada: los mismos procesos y el mismo resultado, solo antes."""
        from ui.comun import proceso, proceso_hijo
        if n_utilidades < UMBRAL or not proceso.activo():
            return
        n = len(PARTES) if proceso_hijo.paralelos(len(PARTES), MB_POR_PARTE) >= len(PARTES) else 1
        for k in range(n):
            proceso.trabajador("plano" if k == 0 else f"plano-{k + 1}").enviar(
                proceso.Tarea("ui.ventana.calculo_fondo:calentar"))

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
        viejo = getattr(self, "_avance_calculo", None)
        if viejo is not None:
            viejo.cerrar()
        # barra de carga en la barra de estado (2026-10-20, `calculo_avance`; antes solo un texto)
        av = calc["avance"] = self._avance_calculo = AvanceCalculo(self, len(self.pipes), grupos)
        for k, partes in enumerate(grupos):
            tarea = proceso.Tarea("ui.ventana.calculo_fondo:calcular",
                                  (datos, conflictos, i18n_core.get_lang(), partes))
            tarea.avance.connect(lambda msg, a=av: a.aviso(msg[1], msg) if isinstance(msg, tuple) and len(msg) > 1
                                 else None)
            tarea.terminado.connect(lambda *_a, a=av, ps=partes: [a.lista(p) for p in ps])
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
        av = calc.get("avance")
        try:
            self._calculo_terminado_con(calc, m, av)
        finally:
            if av is not None:
                av.cerrar()
            elif hasattr(self, "statusBar"):
                self.statusBar().clearMessage()

    def _calculo_terminado_con(self, calc, m, av):
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
            if av is not None:
                av.dibujando()                          # el redibujo final traba la ventana: avisar antes
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
