"""Flujo desde el PERFIL LONGITUDINAL (mezcla de `Main`, base de `FlujoMixin`; pedido del usuario 2026-11-10: «en la
vista de perfil lo más práctico sería un botón que me pida seleccionar visualmente un punto en el perfil hacia donde
va el fluido, con snap a buzones, vértices y tuberías»).

- Cabecera del perfil: [⇥⇤ Flujo] (elegir el punto de llegada) y un ojo (ver/ocultar las flechas del perfil,
  QSettings `flujo/ver_perfil`); solo en gravedad y presión.
- Mientras se elige, la franja guía de arriba lo dice (`_perfil_ab_fichas`) y la vista muestra la diana, la etiqueta
  y las flechas en vivo (`ui/comun/perfil_vista_flujo`). Clic → `perfil_flujo_punto`: todo lo de antes del punto va
  hacia B y lo de después hacia A (`nucleo/flujo_perfil.asignar`): cada utilidad del recorrido toda hacia una punta
  o, si el punto cae dentro de ella, hacia ese punto. UN paso de deshacer. Esc o clic derecho = cancelar.
- Clic derecho en un tramo → «Sentido del flujo»: elegir, o volver a automático esa utilidad o todo el perfil.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from nucleo import flujo as FL, flujo_perfil as FP, perfil_recorrido as PR, perfil_textos as T
from traduccion.i18n import bind as _bind, t as _tr
from ui.comun import rediseno as R
from ui.comun.icons import icon

VER_PERFIL = "flujo/ver_perfil"


class PerfilFlujoMixin:
    def _perfil_flujo_cabecera(self, h):
        """Botón «Flujo» y ojo en la cabecera del perfil."""
        from ui.ventana.ventana_flujo import ajuste
        b = QtWidgets.QPushButton()
        b.setIcon(icon("mdi:arrow-collapse-horizontal"))
        _bind(b, "setText", "Flujo")
        _bind(b, "setToolTip", "Elegir hacia dónde va el fluido: clic en un buzón, un vértice o un punto de la tubería")
        b.setCheckable(True)
        b.setAutoDefault(False)
        b.clicked.connect(lambda on: self.perfil_flujo_elegir(on))
        b.hide()
        self.btn_perfil_flujo = b
        h.addWidget(b)
        self.btn_perfil_ver_flujo = R.boton_icono("eye-outline", "Ocultar el sentido del flujo en el perfil",
                                                  lambda: self.perfil_ver_flujo())
        self.btn_perfil_ver_flujo.hide()
        h.addWidget(self.btn_perfil_ver_flujo)
        self._perfil_ver_flujo_inicial = ajuste(VER_PERFIL)

    def _perfil_flujo_conectar(self, vista):
        vista.ver_flujo = getattr(self, "_perfil_ver_flujo_inicial", True)
        vista.flujoCambiado.connect(self.perfil_flujo)          # «automático» desde el clic derecho
        vista.flujoPunto.connect(self.perfil_flujo_punto)
        vista.flujoElegir.connect(self._perfil_flujo_modo)

    def _flujo_perfil_refrescar(self):
        """Tras rearmar el perfil: los botones solo en gravedad y presión."""
        b = getattr(self, "btn_perfil_flujo", None)
        if b is None:
            return
        d = getattr(self, "_perfil_datos", None)
        ver = d is not None and d.tipo in FL.REDES
        b.setVisible(ver)
        self.btn_perfil_ver_flujo.setVisible(ver)
        vista = self.perfil_vista
        if not ver and vista.eligiendo_flujo():
            vista.elegir_flujo(False)
        self._flujo_ojo(self.btn_perfil_ver_flujo, vista.ver_flujo, "perfil")

    def perfil_flujo_elegir(self, on=True):
        """Entra (o sale) del modo «elegir hacia dónde va el fluido» en el perfil."""
        vista = getattr(self, "perfil_vista", None)
        d = getattr(self, "_perfil_datos", None)
        if vista is None or d is None or d.tipo not in FL.REDES:
            if getattr(self, "btn_perfil_flujo", None) is not None:
                self.btn_perfil_flujo.setChecked(False)
            return False
        vista.elegir_flujo(bool(on))
        return vista.eligiendo_flujo()

    def _perfil_flujo_modo(self, on):
        """La vista entró o salió del modo: botón, franja guía y A/B (no se eligen a la vez)."""
        b = getattr(self, "btn_perfil_flujo", None)
        if b is not None:
            b.blockSignals(True)
            b.setChecked(bool(on))
            b.blockSignals(False)
        if on and getattr(self, "_perfil_paso", None):
            self._perfil_paso = None
            self._perfil_quitar_pista()
        self._perfil_ab_fichas()
        if on:
            self._info(_tr("Haz clic en el perfil donde llega el fluido (Esc cancela)."))

    def _perfil_flujo_esc(self):
        """Esc en la ventana mientras se elige en el perfil: cancelar. True si lo atendió."""
        vista = getattr(self, "perfil_vista", None)
        if vista is not None and vista.eligiendo_flujo():
            vista.elegir_flujo(False)
            return True
        return False

    def perfil_flujo_punto(self, e, nodo=-1):
        """El fluido llega a la estación `e` del perfil (en el nodo `nodo` si el imán lo tomó): lo de antes va hacia B
        y lo de después hacia A. UN paso de deshacer. True si cambió algo."""
        d = getattr(self, "_perfil_datos", None)
        if d is None or d.tipo not in FL.REDES:
            return False
        punto = (d.nodos[nodo].x, d.nodos[nodo].y) if 0 <= nodo < len(d.nodos) else None
        ft = self._ft()
        tol = PR.TOL_FT / ft if ft else 0.5
        cambios = {}
        for j, (clase, valor) in FP.asignar(d, e, punto).items():
            if not (0 <= j < len(self.pipes)) or not FL.aplica(self.pipes[j]):
                continue
            prueba = dict(self.pipes[j])
            if clase == "punto":
                FL.poner_hacia(prueba, valor[0], valor[1], tol)
            else:
                FL.poner(prueba, valor)
            if FL.estado(prueba) != FL.estado(self.pipes[j]):
                cambios[j] = (clase, valor)
        donde = T.estacion(e)
        if 0 <= nodo < len(d.nodos) and d.nodos[nodo].tipo == "estructura" and d.nodos[nodo].cod:
            donde = d.nodos[nodo].cod + " · " + donde
        if not cambios:
            self._info(_tr("El fluido ya llegaba a {x}.").format(x=donde))
            return False
        self._push()
        for j, (clase, valor) in cambios.items():
            if clase == "punto":
                FL.poner_hacia(self.pipes[j], valor[0], valor[1], tol)
            else:
                FL.poner(self.pipes[j], valor)
        self._dirty = True
        self._redraw()                                # el perfil se rehace solo (cambió el modelo)
        self._flujo_refrescar()
        self._info(_tr("Listo: el fluido llega a {x} ({n} utilidades cambiadas).").format(x=donde, n=len(cambios)))
        return True

    def perfil_flujo(self, i, hacia, todo=False):
        """Desde el perfil: el fluido va `hacia` B (1), A (-1) o automático (0) en la utilidad del paso `i` o, con
        `todo`, en todas las del recorrido (cada una según su sentido en el recorrido). UN paso de deshacer."""
        d = getattr(self, "_perfil_datos", None)
        if d is None or d.tipo not in FL.REDES:
            return False
        pasos = d.pasos if todo else ([d.pasos[i]] if 0 <= i < len(d.pasos) else [])
        valor = {}
        for ps in pasos:
            valor.setdefault(ps.pipe, FL.de_paso(hacia, ps.invertida))
        cambios = {j: v for j, v in valor.items() if 0 <= j < len(self.pipes)
                   and FL.estado(self.pipes[j]) != (v or FL.AUTO, None)}
        if not cambios:
            return False
        self._push()
        for j, v in cambios.items():
            FL.poner(self.pipes[j], v)
        self._dirty = True
        self._redraw()                                # el perfil se rehace solo (cambió el modelo)
        self._flujo_refrescar()
        return True

    def perfil_ver_flujo(self, on=None):
        """El ojo del perfil: ver u ocultar sus flechas y dianas de llegada."""
        from ui.ventana.ventana_flujo import guardar_ajuste
        vista = getattr(self, "perfil_vista", None)
        if vista is None:
            return None
        vista.ver_flujo = (not vista.ver_flujo) if on is None else bool(on)
        guardar_ajuste(VER_PERFIL, vista.ver_flujo)
        self._flujo_ojo(self.btn_perfil_ver_flujo, vista.ver_flujo, "perfil")
        vista.update()
        return vista.ver_flujo
