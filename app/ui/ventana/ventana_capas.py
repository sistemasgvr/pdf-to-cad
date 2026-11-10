"""ventana_capas.py — «Capas» del editor: encender y apagar utilidades y planos, como en AutoCAD.

Pedido del usuario 2026-10-26: los planos de fondo de cada utilidad agregada (antes pestañas al pie
del lienzo, `ventana_planos`) y las utilidades dibujadas se manejan como capas. El botón «Capas ▾» de
la barra (`ui/comun/capas_popup`) lista:

- UTILIDADES (lo dibujado): una fila por capa de utilidad del proyecto (Agua, Alcantarillado…), con sus
  subgrupos Líneas, Estructuras y Válvulas (pedido 2026-11-07): `capas_apagadas` guarda «AGUA» = toda la utilidad
  y «AGUA/valvulas» = solo ese subgrupo (`sub_clave`).
  Apagada (`Main.capas_apagadas`): sus líneas, sus buzones y curvas y sus marcas (cruces, accesorios,
  avisos, C-n cuyas utilidades dueñas están todas apagadas; las que no saben de quién son, por las
  utilidades cercanas) no se pintan y en el lienzo no se eligen ni enganchan. En el Inventario sigue en la lista, atenuada; elegida desde ahí se ve.
- PLANOS DEL PDF (fondo): un plano por grupo de hojas (`ventana_planos._poner_planos`).

Solo cambia lo que se VE: el modelo, los cálculos, la Tabla de datos y el DXF no cambian. Apagar o
encender no rehace nada: la capa de líneas y las de marcas filtran al pintar (`fijar_ocultas`). Va
al .digproj (`capas_apagadas`) sin marcar el proyecto como cambiado (es la vista).
"""
from __future__ import annotations

from collections import Counter

from PySide6 import QtGui

from nucleo import valvulas as V
from nucleo.model import TIPOS
from traduccion.i18n import N_, t as _tr
from ui.comun import capas_popup as CP
from ui.comun.ui_common import layer_qcolor
import geometry as G

# Una marca sin dueñas conocidas (`capa_marcas.duenas`) es de las utilidades que pasan a ≤ esto de su punto
MARCA_FT = 2.0


LINEAS, ESTRUCTURAS, VALVULAS = "lineas", "estructuras", "valvulas"
NOMBRES_SUB = {LINEAS: N_("Líneas"), ESTRUCTURAS: N_("Estructuras"), VALVULAS: N_("Válvulas")}


def sub_clave(utilidad, sub) -> str:
    return f"{utilidad}/{sub}"


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
        for k in range(len(getattr(self, "valvulas", None) or ())):
            u = self._utilidad_valvula(k)
            if u:
                n.setdefault(u, 0)                      # subgrupo de su utilidad
            else:
                n[V.CAPA] += 1                          # sin utilidad: su propia fila
        orden = [lay for _l, lay in TIPOS]
        return {c: n[c] for c in sorted(n, key=lambda c: (orden.index(c) if c in orden else len(orden), c))}

    def _nombre_capa(self, clave):
        if "/" in str(clave):
            u, sub = clave.split("/", 1)
            return f"{self._tipo(u)} · {_tr(NOMBRES_SUB[sub])}"
        return _tr("Válvulas") if clave == V.CAPA else self._tipo(clave)

    def _utilidad_valvula(self, k):
        """La utilidad de la válvula k: la que leyó el plano o la de su tubería."""
        vs = self.valvulas
        lugares = getattr(self, "_valv_lugares", None) or ()
        lug = lugares[k] if k < len(lugares) else None
        if vs[k].get("utilidad"):
            return vs[k]["utilidad"]
        return (self.pipes[lug.pipe].get("layer") or "") if lug is not None and lug.ok and lug.pipe < len(self.pipes) else ""

    def _subcapas(self):
        """{utilidad: {subgrupo: cuántos hay}} solo con lo que tiene dibujado."""
        out = {}
        for p in self.pipes:
            if p.get("pts") and p.get("layer"):
                d = out.setdefault(p["layer"], {})
                d[LINEAS] = d.get(LINEAS, 0) + 1
        for i, _curva, s, _items in getattr(self, "_estructuras_vista", ()):
            duenas = self._duenas_memo.get(i)
            if duenas is None:
                duenas = self._duenas_memo[i] = self._duenas_estructura(s)
            for u in duenas or ():
                d = out.setdefault(u, {})
                d[ESTRUCTURAS] = d.get(ESTRUCTURAS, 0) + 1
        for k in range(len(getattr(self, "valvulas", None) or ())):
            u = self._utilidad_valvula(k)
            if u:
                d = out.setdefault(u, {})
                d[VALVULAS] = d.get(VALVULAS, 0) + 1
        return out

    def _lineas_apagadas(self):
        """Las utilidades con sus líneas (y sus marcas) apagadas."""
        ap = getattr(self, "capas_apagadas", None) or ()
        return {c.split("/")[0] for c in ap if "/" not in c or c.endswith("/" + LINEAS)}

    def _estructuras_apagadas(self):
        ap = getattr(self, "capas_apagadas", None) or ()
        return frozenset(c.split("/")[0] for c in ap if "/" not in c or c.endswith("/" + ESTRUCTURAS))

    def _valvula_apagada(self, k) -> bool:
        ap = getattr(self, "capas_apagadas", None) or ()
        if not ap:
            return False
        u = self._utilidad_valvula(k)
        return (u in ap or sub_clave(u, VALVULAS) in ap) if u else V.CAPA in ap

    def _estado_capas(self) -> CP.Estado:
        apagadas = getattr(self, "capas_apagadas", set())
        subcapas = self._subcapas()
        utilidades = []
        for c, k in self._capas_utilidad().items():
            subs = subcapas.get(c, {})
            apagados = [s for s in subs if sub_clave(c, s) in apagadas]
            utilidades.append(CP.Fila(CP.UTILIDAD, c, self._nombre_capa(c), c not in apagadas,
                                      None if c == V.CAPA else layer_qcolor(c), _miles(k),
                                      _tr("{n} válvulas reconocidas").format(n=_miles(k)) if c == V.CAPA else
                                      _tr("{n} utilidades de {t} dibujadas").format(n=_miles(k), t=self._tipo(c)),
                                      parcial=c not in apagadas and bool(apagados)))
            if len(subs) > 1:                           # de un solo tipo, el grupo ya lo dice todo
                utilidades += [CP.Fila(CP.UTILIDAD, sub_clave(c, s), _tr(NOMBRES_SUB[s]),
                                       c not in apagadas and s not in apagados, None, _miles(subs[s]),
                                       self._nombre_capa(sub_clave(c, s)), padre=c)
                               for s in (LINEAS, ESTRUCTURAS, VALVULAS) if s in subs]
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
        n = sum(1 for c in getattr(self, "capas_apagadas", ()) if c.split("/")[0] in presentes)
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
        if "/" in str(clave):
            self._cambiar_subcapa(clave, encendida)
        else:
            self.capas_apagadas = {c for c in self.capas_apagadas if c.split("/")[0] != clave}
            if not encendida:
                self.capas_apagadas.add(clave)
        self._aplicar_capas()
        self._info((_tr("Capa encendida: {c}.") if encendida else _tr("Capa apagada: {c}.")).format(c=self._nombre_capa(clave)))

    def _cambiar_subcapa(self, clave, encendida):
        """Un subgrupo. Si todos quedan apagados vale por la utilidad entera; encender uno con la utilidad apagada
        deja apagados los otros."""
        u = clave.split("/")[0]
        todas = {sub_clave(u, s) for s in self._subcapas().get(u, {})}
        if u in self.capas_apagadas:
            self.capas_apagadas.discard(u)
            self.capas_apagadas |= todas
        (self.capas_apagadas.discard if encendida else self.capas_apagadas.add)(clave)
        if todas <= self.capas_apagadas:
            self.capas_apagadas -= todas
            self.capas_apagadas.add(u)

    def _solo_capa(self, tipo, clave):
        """«Ver solo esta» (LAYISO de AutoCAD): las demás de su sección se apagan."""
        if tipo == CP.PLANO:
            self._poner_planos({int(clave)})
            return
        u = str(clave).split("/")[0]
        self.capas_apagadas = set(self._capas_utilidad()) - {u}
        if "/" in str(clave):
            self.capas_apagadas |= {sub_clave(u, s) for s in self._subcapas().get(u, {})} - {clave}
        self._aplicar_capas()
        self._info(_tr("Solo a la vista: {c}.").format(c=self._nombre_capa(clave)))

    def _encender_capas(self):
        self.capas_apagadas = set()
        gs = self._grupos_planos()
        if gs and len(self._planos_encendidos()) != len(gs):
            self._poner_planos(gs)
        self._aplicar_capas()
        self._info(_tr("Todas las capas encendidas."))

    def _aplicar_capas(self):
        """Encender o apagar no rehace la geometría: solo cambia qué se pinta de lo que ya está en la escena."""
        previa = getattr(self, "_capa_lineas", None)
        try:
            lista = (previa is not None and previa[1].scene() is self.canvas.scene()
                     and hasattr(self, "_estructuras_vista")
                     and not getattr(self, "_provisional", False))
        except RuntimeError:
            lista = False
        if lista:
            elegidas = previa[2]
            apagadas = self._lineas_apagadas()
            previa[1].fijar_ocultas({i for i, p in enumerate(self.pipes)
                                   if p.get("layer") in apagadas} - elegidas if apagadas else ())
            self._visibilidad_estructuras()
            self._sync_capa_valvulas()
            if previa[3]:
                self._actualizar_rotulos_tramos(elegidas, previa[3])
            self._ocultar_marcas_apagadas()
            self._sync_boton_capas()
        else:
            # Escena inicial o provisional: aún hace falta su primer dibujo completo.
            self._redraw()
        self._atenuar_lista_utilidades()

    # ── qué está apagado ──────────────────────────────────────────────────
    def _capa_apagada(self, i) -> bool:
        """La utilidad i está en una capa apagada (no se pinta ni se elige en el lienzo)."""
        return self.pipes[i].get("layer") in self._lineas_apagadas()

    def _capa_de_utilidad(self, i):
        """La capa de la utilidad i (dueña de una marca), o None si no se sabe."""
        return (self.pipes[i].get("layer") or None) if i is not None and 0 <= i < len(self.pipes) else None

    def _capas_de_utilidades(self, indices):
        """Las capas dueñas de una marca de esas utilidades, o None si alguna no se sabe (`capa_marcas.duenas`)."""
        capas = [self._capa_de_utilidad(i) for i in indices]
        return frozenset(capas) if capas and all(capas) else None

    def _capas_en(self, x, y, cerca=None):
        """Las capas de las utilidades que pasan a ≤ `MARCA_FT` del punto (dueñas de una marca).
        `cerca(x, y, r)` = candidatas (por defecto `_utilidades_cerca`, que revalida la geometría de
        TODAS las utilidades en cada llamada: con decenas de miles de marcas, ver `_capas_de_marcas`)."""
        r = max(3.0, MARCA_FT / self.scale * self.zoom) if self.scale else 3.0
        if cerca is None:
            cerca = lambda x, y, r: self._utilidades_cerca(x, y, r, todas=True)
        out = set()
        for i in cerca(x, y, r):
            p = self.pipes[i]
            capa = p.get("layer")
            if capa in out or not p.get("pts"):
                continue
            if any(G.pt_seg_dist(x, y, a[0], a[1], b[0], b[1]) <= r for a, b in zip(p["pts"], p["pts"][1:])):
                out.add(capa)
        return frozenset(out)

    def _capas_de_marcas(self):
        """`capas_en(x, y)` para TODAS las marcas de un apagado (reporte 2026-10-26: apagar una capa
        congelaba la ventana; AGUA 2 = 53 851 marcas × 14 ms ≈ 13 min). El índice de utilidades se
        valida UNA vez (no en cada marca) y un mismo punto (cruce + accesorio) se mide una vez. Mismas
        candidatas y misma cuenta exacta que `_capas_en`: mismo resultado."""
        from nucleo.indice_plano import IndiceUtilidades, _firma
        cache = getattr(self, "_cache_raton", None)
        if cache is None:
            cache = self._cache_raton = {}
        ix = cache.get("indice")
        if ix is None or not ix.vigente(self.pipes):
            firma = _firma(self.pipes)
            ix = IndiceUtilidades(self.pipes, firma)
            cache["indice"], cache["firma"] = ix, firma
        hechos = {}

        def capas_en(x, y):
            k = (x, y)
            v = hechos.get(k)
            if v is None:
                v = hechos[k] = self._capas_en(x, y, ix.cerca)
            return v
        return capas_en

    def _ocultar_marcas_apagadas(self):
        """Al final de cada redibujo: las capas de marcas filtran lo de utilidades apagadas."""
        grupo = getattr(self, "_marcas", None)
        if grupo is None:
            return
        apagadas = self._lineas_apagadas()
        perezosa = []                                       # el índice solo si alguna capa lo necesita

        def capas_en(x, y):
            if not perezosa:
                perezosa.append(self._capas_de_marcas())
            return perezosa[0](x, y)
        grupo.fijar_ocultas(apagadas, capas_en)

    def _atenuar_lista_utilidades(self):
        """En el Inventario las utilidades apagadas siguen en la lista, en gris."""
        lst = getattr(self, "pipe_list", None)
        if lst is None:
            return
        ap = self._lineas_apagadas()
        tenue = QtGui.QBrush(QtGui.QColor(lst.palette().color(QtGui.QPalette.Disabled, QtGui.QPalette.Text)))
        normal = QtGui.QBrush()
        for row in range(min(lst.count(), len(self.pipes))):
            it = lst.item(row)
            apagada = bool(ap) and self.pipes[row].get("layer") in ap
            deseada = tenue if apagada else normal
            if it.foreground() != deseada:
                it.setForeground(deseada)
