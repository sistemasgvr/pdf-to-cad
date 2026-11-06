"""Inventario → «Accesorios» (pedido del usuario 2026-11-05): la lista de codos, Tees, Wyes, cruces y válvulas
del plano, con un filtro por tipo, para elegirlos. Solo LEE lo que la app ya calculó: los accesorios del redibujo
(`_draw_accesorios` → `_accs_lista`, sin los marcados «no hay accesorio») y las válvulas (`_lugares_valvulas`).

Clic en una fila → el plano va a ese lugar y lo marca con el círculo que parpadea; debajo, sus datos. Clic derecho:
para un accesorio, «No hay …» (uno o varios, un paso de deshacer); para una válvula, su menú de siempre (unión,
material, quitar). La lista se arma solo con la sección a la vista (con miles de accesorios no estorba al redibujo).
"""
from __future__ import annotations

import re
import unicodedata

from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import accesorios as _A
from nucleo import sin_accesorio as _SA
from nucleo.model import TAB_ACC
from nucleo.normas_validar import NOMBRE_ACC
from ui.comun.responsive import GridAdaptable

# (clave del filtro, texto). La clave es el `tipo` del accesorio; «valvula» = las válvulas.
FILTROS_ACC = (("", N_("Todos")), ("codo", N_("Codos")), ("tee", N_("Tees")), ("wye", N_("Wyes")),
               ("cruz", N_("Cruces")), ("valvula", N_("Válvulas")))
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def orden_alfabetico(texto):
    """Clave de orden ALFABÉTICO (pedido del usuario 2026-11-06): sin mayúsculas ni tildes («Válvula» va con la V) y
    los números como números («Codo 11.25°» antes que «Codo 90°», «#2» antes que «#10»)."""
    plano = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").casefold()
    return [(0, float(x), "") if k % 2 else (1, 0.0, x) for k, x in enumerate(_NUM.split(plano)) if x]


class Fila:
    """Una fila de la lista: qué es (`clase` "acc" | "valv"), su tipo para el filtro y dónde está."""
    __slots__ = ("clase", "tipo", "x", "y", "texto", "globo", "capa", "pipes", "dato")

    def __init__(self, clase, tipo, x, y, texto, globo, capa, pipes, dato):
        self.clase, self.tipo, self.x, self.y = clase, tipo, x, y
        self.texto, self.globo, self.capa, self.pipes, self.dato = texto, globo, capa, pipes, dato

    def clave(self):
        return (self.clase, self.tipo, round(self.x, 3), round(self.y, 3), self.texto)

    def lugar(self):
        """Qué es y dónde (sin el texto): la selección sigue aunque cambie su unión o su material."""
        return (self.clase, self.tipo, round(self.x, 3), round(self.y, 3))


def _diam(p):
    try:
        d = float(p.get("diam") or 0)
    except (TypeError, ValueError):
        return ""
    return f'{d:g}"' if d > 0 else ""


class ListaAccesoriosMixin:
    # ── construcción ─────────────────────────────────────────────────────
    def _build_lista_accesorios(self):
        """La página «Accesorios» del Inventario (filtro + lista + datos de lo elegido)."""
        from ui.comun import rediseno as R
        w = R.transparente(QtWidgets.QWidget())
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        chips = GridAdaptable(max_cols=3, spacing=4)
        self.filtro_accesorios = QtWidgets.QButtonGroup(w)
        self._chips_acc = []
        for i, (clave, texto) in enumerate(FILTROS_ACC):
            b = QtWidgets.QPushButton(_tr(texto))
            b.setProperty("kind", "chip")
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.filtro_accesorios.addButton(b, i)
            chips.addWidget(b)
            self._chips_acc.append((b, clave, texto))
        self.filtro_accesorios.idClicked.connect(lambda _i: self._filtrar_inventario())
        v.addLayout(chips)
        self.acc_list = QtWidgets.QListWidget()
        self.acc_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.acc_list.currentRowChanged.connect(self._sel_accesorio)
        self.acc_list.itemSelectionChanged.connect(self._datos_accesorio)
        self.acc_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.acc_list.customContextMenuRequested.connect(self._menu_lista_accesorios)
        v.addWidget(self.acc_list, 1)
        self.lbl_acc_info = QtWidgets.QLabel()
        self.lbl_acc_info.setWordWrap(True)
        self.lbl_acc_info.setProperty("rol", "t3")
        v.addWidget(self.lbl_acc_info)
        self._acc_filas = []
        self._acc_claves = None
        self._acc_puntos = {}
        self._acc_tab_widget = w
        self._datos_accesorio()
        return w

    # ── datos ────────────────────────────────────────────────────────────
    def _filas_accesorios(self):
        filas = []
        pipes = self.pipes
        for a in getattr(self, "_accs_lista", None) or []:
            ids = [i for i in a.get("pipes") or () if 0 <= i < len(pipes)]
            tipo = a.get("tipo") or ""
            nombre = _tr(NOMBRE_ACC.get(tipo, tipo))
            ang = a.get("angulo")
            capa = a.get("capa") or (pipes[ids[0]].get("layer") if ids else "")
            diams = []
            for i in ids:
                d = _diam(pipes[i])
                if d and d not in diams:
                    diams.append(d)
            partes = [nombre + (" " + _A.texto_angulo(ang) if ang is not None else "")]
            if diams:
                partes.append(" × ".join(diams))
            partes.append(self._tipo(capa) if capa else "")
            partes.append(" ".join(f"#{i + 1}" for i in ids))
            texto = " · ".join(x for x in partes if x)
            globo = "\n".join([texto, _tr("Clic para verlo en el plano; clic derecho para más opciones.")])
            filas.append(Fila("acc", tipo, float(a["x"]), float(a["y"]), texto, globo, capa, ids, a))
        vs = getattr(self, "valvulas", None) or []
        if vs:
            from ui.ventana.ventana_valvulas import globo_valvula
            for k, (v, lug) in enumerate(zip(vs, self._lugares_valvulas())):
                if lug.ok:
                    capa = pipes[lug.pipe].get("layer") or ""
                    texto = " · ".join([_tr("Válvula") + f' {lug.diam_in:g}" {lug.union}', self._tipo(capa),
                                        f"#{lug.pipe + 1}"])
                    filas.append(Fila("valv", "valvula", lug.x, lug.y, texto, globo_valvula(lug), capa,
                                      [lug.pipe], k))
                else:
                    texto = _tr("Válvula fuera de lugar: {m}").format(m=lug.motivo)
                    filas.append(Fila("valv", "valvula", float(v["x"]), float(v["y"]), texto, texto, "", [], k))
        filas.sort(key=lambda f: (orden_alfabetico(f.texto), round(f.y), f.x))
        return filas

    def _llenar_lista_accesorios(self, forzar=False):
        """Rehace la lista si cambió lo que muestra. Solo con la sección «Accesorios» a la vista."""
        lista = getattr(self, "acc_list", None)
        if lista is None:
            return
        if not forzar and self._current_tab() != TAB_ACC:
            self._acc_claves = None                     # se arma al abrir la sección
            return
        filas = self._filas_accesorios()
        claves = [f.clave() for f in filas]
        if claves == self._acc_claves:
            return
        elegidas = {self._acc_filas[lista.row(it)].lugar() for it in lista.selectedItems()
                    if lista.row(it) < len(self._acc_filas)}
        actual = lista.currentRow()
        actual = self._acc_filas[actual].lugar() if 0 <= actual < len(self._acc_filas) else None
        lista.blockSignals(True)
        try:
            lista.clear()
            self._acc_filas = filas
            self._acc_claves = claves
            for f in filas:
                ic = _icon("mdi:valve", color=layer_qcolor(f.capa).name()) if f.clase == "valv" and f.capa \
                    else self._punto_acc(f.capa)
                it = fila_lista(lista, f.texto, ic)
                it.setToolTip(f.globo)
                if f.clase == "valv" and not f.capa:
                    it.setForeground(QtGui.QColor(_theme.tokens().danger))
            for fila, f in enumerate(filas):
                k = f.lugar()
                if k in elegidas:
                    lista.item(fila).setSelected(True)
                if k == actual:
                    lista.setCurrentRow(fila, QtCore.QItemSelectionModel.NoUpdate)
        finally:
            lista.blockSignals(False)
        cuenta = {}
        for f in filas:
            cuenta[f.tipo] = cuenta.get(f.tipo, 0) + 1
        for b, clave, texto in self._chips_acc:
            n = len(filas) if not clave else cuenta.get(clave, 0)
            b.setText(f"{_tr(texto)} ({n})")
        self._filtrar_inventario()
        self._datos_accesorio()

    def _punto_acc(self, capa):
        """Punto del color de la utilidad (como en la lista de Utilidades)."""
        color = layer_qcolor(capa) if capa else QtGui.QColor(_theme.tokens().text3)
        clave = color.name()
        ic = self._acc_puntos.get(clave)
        if ic is None:
            pm = QtGui.QPixmap(14, 14)
            pm.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pm)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QtCore.QRectF(2, 2, 10, 10))
            p.end()
            ic = self._acc_puntos[clave] = QtGui.QIcon(pm)
        return ic

    def _acc_pasa_filtro(self, fila):
        """¿La fila pasa el filtro de tipo elegido? (lo usa `_filtrar_inventario`)."""
        i = self.filtro_accesorios.checkedId()
        clave = FILTROS_ACC[i][0] if 0 <= i < len(FILTROS_ACC) else ""
        return not clave or (fila < len(self._acc_filas) and self._acc_filas[fila].tipo == clave)

    # ── selección ────────────────────────────────────────────────────────
    def _filas_elegidas(self):
        lista = self.acc_list
        filas = sorted(lista.row(it) for it in lista.selectedItems() if not it.isHidden())
        return [self._acc_filas[r] for r in filas if r < len(self._acc_filas)]

    def _sel_accesorio(self, fila):
        if getattr(self, "_acc_sin_mover", False):
            return                                      # elegido con un clic en el plano: ya se ve
        if 0 <= fila < len(self._acc_filas):
            f = self._acc_filas[fila]
            self._ir_a_elemento(f.x, f.y, activar=False)

    def _datos_accesorio(self):
        """Debajo de la lista: cuántos hay, o los datos del accesorio elegido."""
        lbl = getattr(self, "lbl_acc_info", None)
        if lbl is None:
            return
        if hasattr(self, "_sync_prop_accesorio"):
            self._sync_prop_accesorio()                 # propiedades en el panel derecho
        elegidas = self._filas_elegidas()
        if not self._acc_filas:
            lbl.setText(_tr("No hay accesorios: salen en las tuberías de agua y gas (codos, Tees, Wyes, cruces) "
                            "y con Dibujar → «Accesorios»."))
        elif not elegidas:
            lbl.setText(_tr("Clic en un accesorio para verlo en el plano. Ctrl+clic o Mayús+clic para elegir varios."))
        elif len(elegidas) > 1:
            lbl.setText(_tr("{n} accesorios elegidos. Clic derecho para más opciones.").format(n=len(elegidas)))
        else:
            f = elegidas[0]
            lineas = [f.texto]
            if f.clase == "acc":
                a = f.dato
                if a.get("ramal") is not None:
                    lineas.append(_tr("Ramal: #{r} · Principal: {t}").format(
                        r=a["ramal"] + 1, t=" ".join(f"#{i + 1}" for i in a.get("tronco") or ())))
                if a.get("red") and a.get("red") != f.capa:      # sin nombre de red, la red es la capa
                    lineas.append(_tr("Red: {r}").format(r=a["red"]))
            lbl.setText("\n".join(lineas))

    # ── clic derecho ─────────────────────────────────────────────────────
    def _menu_lista_accesorios(self, pos):
        lista = self.acc_list
        it = lista.itemAt(pos)
        if it is not None and not it.isSelected():
            lista.setCurrentRow(lista.row(it))
        elegidas = self._filas_elegidas()
        if not elegidas:
            return
        menu = QtWidgets.QMenu(self)
        f0 = elegidas[0]
        menu.addAction(_icon("mdi:crosshairs-gps"), _tr("Ver en el plano"),
                       lambda: self._ir_a_elemento(f0.x, f0.y, activar=False))
        if len(elegidas) == 1 and f0.pipes:
            for i in f0.pipes:
                menu.addAction(_tr("Ir a la utilidad #{n}").format(n=i + 1),
                               lambda i=i: self._ir_a_elemento(f0.x, f0.y, "pipe", i))
        accs = [f.dato for f in elegidas if f.clase == "acc"]
        valvs = [f for f in elegidas if f.clase == "valv"]
        menu.addSeparator()
        if len(accs) == 1 and not valvs:
            from ui.ventana.ventana_sin_accesorio import texto_no_hay
            menu.addAction(texto_no_hay(accs[0].get("tipo")), lambda: self.marcar_sin_accesorio(accs[0]))
        elif accs:
            menu.addAction(_tr("No hay accesorio en los {n} elegidos").format(n=len(accs)),
                           lambda: self.marcar_sin_accesorios(accs))
        if len(valvs) == 1 and not accs:
            self._menu_valvula(menu, valvs[0].x, valvs[0].y)
        elif valvs:
            menu.addAction(_tr("Quitar las {n} válvulas elegidas").format(n=len(valvs)),
                           lambda: self.quitar_valvulas([f.dato for f in valvs]))
        menu.exec(lista.viewport().mapToGlobal(pos))

    def marcar_sin_accesorios(self, accs):
        """«No hay accesorio» en varios puntos a la vez (un paso de deshacer)."""
        if not accs:
            return False
        self._push()
        self.sin_accesorio = list(getattr(self, "sin_accesorio", None) or []) + [_SA.marca(a, None) for a in accs]
        self._redraw()
        self._info(_tr("Ahí no se pondrá accesorio (ni en Civil 3D). Ctrl+Z para deshacer."))
        return True

    def quitar_valvulas(self, indices):
        """Quita varias válvulas (un paso de deshacer)."""
        vs = list(getattr(self, "valvulas", None) or [])
        quitar = {k for k in indices if 0 <= k < len(vs)}
        if not quitar:
            return False
        self._push()
        self.valvulas = [v for k, v in enumerate(vs) if k not in quitar]
        self._redraw()
        self._info(_tr("Válvula quitada (Ctrl+Z para deshacer)."))
        return True
