"""ventana_capas.py — «Capas» del editor: encender y apagar utilidades y planos, como en AutoCAD.

Pedido del usuario 2026-10-26: los planos de fondo de cada utilidad agregada (antes pestañas al pie
del lienzo, `ventana_planos`) y las utilidades dibujadas se manejan como capas. El botón «Capas ▾» de
la barra (`ui/comun/capas_popup`) lista:

- UTILIDADES (lo dibujado): una fila por capa de utilidad del proyecto (Agua, Alcantarillado…).
  Apagada (`Main.capas_apagadas`): sus líneas, sus buzones y curvas y sus marcas (cruces, accesorios,
  avisos, C-n de las que solo tienen utilidades apagadas cerca) no se pintan y en el lienzo no se
  eligen ni enganchan. En el Inventario sigue en la lista, atenuada; elegida desde ahí se ve.
- PLANOS DEL PDF (fondo): un plano por grupo de hojas (`ventana_planos._poner_planos`).

Solo cambia lo que se VE: el modelo, los cálculos, la Tabla de datos y el DXF no cambian. Apagar o
encender no rehace nada: la capa de líneas y las de marcas filtran al pintar (`fijar_ocultas`). Va
al .digproj (`capas_apagadas`) sin marcar el proyecto como cambiado (es la vista).
"""
from __future__ import annotations

from collections import Counter

from PySide6 import QtGui

from nucleo.model import TIPOS
from traduccion.i18n import t as _tr
from ui.comun import capas_popup as CP
from ui.comun.ui_common import layer_qcolor
import geometry as G

# Una marca (cruce, accesorio, aviso…) es de las utilidades que pasan a ≤ esto de su punto
MARCA_FT = 2.0


def _miles(n) -> str:
    return f"{int(n):,}".replace(",", " ")


class CapasMixin:
    def _construir_boton_capas(self, tb):
        """El botón «Capas ▾» en la barra de herramientas."""
        self.btn_capas = CP.BotonCapas(self._estado_capas, self._cambiar_capa, self._solo_capa,
                                       self._encender_capas)
        tb.addWidget(self.btn_capas)

    # ── lo que muestra el panel ───────────────────────────────────────────
    def _capas_utilidad(self):
        """{capa: nº de utilidades dibujadas} en el orden de `TIPOS` (y las demás después)."""
        n = Counter(p.get("layer") for p in self.pipes if p.get("pts") and p.get("layer"))
        for s in self.structures:                       # cajas sueltas de una utilidad sin líneas
            if s.get("standalone") and s.get("utility") and not s.get("world"):
                n.setdefault(s["utility"], 0)
        orden = [lay for _l, lay in TIPOS]
        return {c: n[c] for c in sorted(n, key=lambda c: (orden.index(c) if c in orden else len(orden), c))}

    def _estado_capas(self) -> CP.Estado:
        apagadas = getattr(self, "capas_apagadas", set())
        utilidades = [CP.Fila(CP.UTILIDAD, c, self._tipo(c), c not in apagadas, layer_qcolor(c), _miles(k),
                              _tr("{n} utilidades de {t} dibujadas").format(n=_miles(k), t=self._tipo(c)))
                      for c, k in self._capas_utilidad().items()]
        planos = []
        encendidos = set(self._planos_encendidos())
        comp = self.composite
        for g in self._grupos_planos():
            utils = self._utilidades_plano(g)
            hojas = sum(1 for p in comp.pieces if int(p.grupo) == int(g))
            planos.append(CP.Fila(CP.PLANO, int(g), self._nombre_plano(g), int(g) in encendidos,
                                  layer_qcolor(utils[0]) if len(utils) == 1 else None,
                                  _tr("{n} hoja(s)").format(n=hojas),
                                  _tr("Plano original del PDF: {pdf}").format(pdf=self._pdfs_plano(g))))
        return CP.Estado(utilidades, planos)

    def _sync_boton_capas(self):
        """Cuántas capas hay apagadas, en el botón (lo llama cada redibujo: barato)."""
        btn = getattr(self, "btn_capas", None)
        if btn is None:
            return
        presentes = set(self._capas_utilidad())
        n = len(set(getattr(self, "capas_apagadas", ())) & presentes)
        gs = self._grupos_planos()
        if gs:
            n += len(gs) - len(self._planos_encendidos())
        btn.resumen(n)

    # ── lo que pide el usuario ────────────────────────────────────────────
    def _cambiar_capa(self, tipo, clave, encendida):
        if tipo == CP.PLANO:
            vis = set(self._planos_encendidos())
            (vis.add if encendida else vis.discard)(int(clave))
            self._poner_planos(vis)
            return
        (self.capas_apagadas.discard if encendida else self.capas_apagadas.add)(clave)
        self._aplicar_capas()
        self._info((_tr("Capa encendida: {c}.") if encendida else _tr("Capa apagada: {c}.")).format(c=self._tipo(clave)))

    def _solo_capa(self, tipo, clave):
        """«Ver solo esta» (LAYISO de AutoCAD): las demás de su sección se apagan."""
        if tipo == CP.PLANO:
            self._poner_planos({int(clave)})
            return
        self.capas_apagadas = set(self._capas_utilidad()) - {clave}
        self._aplicar_capas()
        self._info(_tr("Solo a la vista: {c}.").format(c=self._tipo(clave)))

    def _encender_capas(self):
        self.capas_apagadas = set()
        gs = self._grupos_planos()
        if gs and len(self._planos_encendidos()) != len(gs):
            self._poner_planos(gs)                         # (redibuja)
        self._aplicar_capas()
        self._info(_tr("Todas las capas encendidas."))

    def _aplicar_capas(self):
        """Mismo modelo: el redibujo reusa líneas y marcas y solo cambia qué se pinta."""
        self._redraw()
        self._atenuar_lista_utilidades()

    # ── qué está apagado ──────────────────────────────────────────────────
    def _capa_apagada(self, i) -> bool:
        """La utilidad i está en una capa apagada (no se pinta ni se elige en el lienzo)."""
        ap = getattr(self, "capas_apagadas", None)
        return bool(ap) and self.pipes[i].get("layer") in ap

    def _capas_en(self, x, y):
        """Las capas de las utilidades que pasan a ≤ `MARCA_FT` del punto (dueñas de una marca)."""
        r = max(3.0, MARCA_FT / self.scale * self.zoom) if self.scale else 3.0
        out = set()
        for i in self._utilidades_cerca(x, y, r, todas=True):
            p = self.pipes[i]
            capa = p.get("layer")
            if capa in out or not p.get("pts"):
                continue
            if any(G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1]) <= r for a, b in zip(p["pts"], p["pts"][1:])):
                out.add(capa)
        return frozenset(out)

    def _ocultar_marcas_apagadas(self):
        """Al final de cada redibujo: las capas de marcas filtran lo de utilidades apagadas."""
        grupo = getattr(self, "_marcas", None)
        if grupo is not None:
            grupo.fijar_ocultas(getattr(self, "capas_apagadas", ()), self._capas_en)

    def _atenuar_lista_utilidades(self):
        """En el Inventario las utilidades apagadas siguen en la lista, en gris."""
        lst = getattr(self, "pipe_list", None)
        if lst is None:
            return
        ap = getattr(self, "capas_apagadas", set())
        tenue = QtGui.QBrush(QtGui.QColor(lst.palette().color(QtGui.QPalette.Disabled, QtGui.QPalette.Text)))
        normal = QtGui.QBrush()
        for row in range(min(lst.count(), len(self.pipes))):
            it = lst.item(row)
            apagada = bool(ap) and self.pipes[row].get("layer") in ap
            if apagada or it.foreground() != normal:
                it.setForeground(tenue if apagada else normal)
