"""Ventana «Revisar y limpiar el dibujo» (Herramientas, y antes de exportar el DXF).

Muestra lo que encontró `nucleo.limpieza` (sobre una COPIA del dibujo): un grupo por
tipo de arreglo, con casilla para elegir qué se arregla, y un grupo «Para revisar»
con lo que no se arregla solo. Clic en un caso = ir a ese lugar del lienzo.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from nucleo import limpieza
from traduccion.i18n import N_, t as _tr

# Título de cada grupo arreglable (clave = Cambio.tipo).
_GRUPOS = {
    "tramo": N_("Tramos rectos diminutos (menos de {min} ft): en Civil 3D salen como tuberías diminutas"),
    "punta": N_("Puntas casi unidas (hasta {max} ft): se unen exacto a la otra utilidad"),
    "corta": N_("Utilidades más cortas que {corta} ft: se eliminan"),
    "duplicada": N_("Utilidades repetidas (la misma línea dos veces): se elimina la copia"),
}
_COMO = {
    "vertice": N_("se quita un vértice que sobra"),
    "curva": N_("la curva se estira hasta el vértice"),
    "esquina": N_("la curva arranca justo en el vértice"),
    "ancla": N_("la curva arranca justo en el vértice"),
}
_ROL = QtCore.Qt.UserRole


class LimpiezaDialog(QtWidgets.QDialog):
    """`res` = limpieza.Resultado de la vista previa; `etiqueta(i)` = «#5 Eléctrico»;
    `ir_a(x, y, i)` lleva el lienzo a ese lugar. Al cerrar: `accion` = "arreglar" |
    "seguir" (exportar sin cambios) | "cancelar" y `tipos()` = lo marcado."""

    def __init__(self, parent, res, etiqueta, ir_a, exportando=False):
        super().__init__(parent)
        self.ir_a = ir_a
        self.accion = "cancelar"
        self._exportando = exportando
        self.setWindowTitle(_tr("Revisar y limpiar el dibujo"))
        self.setMinimumSize(640, 460)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(10)
        txt = (_tr("Antes de exportar: esto saldría mal en Civil 3D o habría que corregirlo a mano.")
               if exportando else
               _tr("Lo que en Civil 3D saldría mal o habría que corregir a mano."))
        cab = QtWidgets.QLabel(txt)
        f = cab.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() * 1.1); cab.setFont(f)
        cab.setWordWrap(True)
        lay.addWidget(cab)
        ayuda = QtWidgets.QLabel(_tr("Desmarca lo que no quieras arreglar. Clic en un caso para verlo en el plano. "
                                     "Se puede deshacer con Ctrl+Z."))
        ayuda.setWordWrap(True); ayuda.setProperty("muted", True)
        lay.addWidget(ayuda)

        self.arbol = QtWidgets.QTreeWidget()
        self.arbol.setHeaderHidden(True)
        self.arbol.setUniformRowHeights(True)
        self.arbol.itemClicked.connect(self._clic)
        lay.addWidget(self.arbol, 1)
        self.grupos = {}
        fmt = {"min": f"{limpieza.TRAMO_MIN_FT:g}", "max": f"{limpieza.PUNTA_MAX_FT:g}",
               "corta": f"{limpieza.UTILIDAD_MIN_FT:g}"}
        for tipo in limpieza.ARREGLABLES:
            casos = res.de(tipo, True)
            if not casos:
                continue
            g = QtWidgets.QTreeWidgetItem([_tr(_GRUPOS[tipo]).format(**fmt) + f"  ({len(casos)})"])
            g.setFlags(g.flags() | QtCore.Qt.ItemIsUserCheckable)
            g.setCheckState(0, QtCore.Qt.Checked)
            self.arbol.addTopLevelItem(g)
            for c in casos:
                g.addChild(self._fila(c, etiqueta))
            self.grupos[tipo] = g
        avisos = res.avisos
        if avisos:
            g = QtWidgets.QTreeWidgetItem([_tr("Para revisar a mano (no se cambian)") + f"  ({len(avisos)})"])
            self.arbol.addTopLevelItem(g)
            for c in avisos:
                g.addChild(self._fila(c, etiqueta))
        for k in range(self.arbol.topLevelItemCount()):
            it = self.arbol.topLevelItem(k)
            it.setExpanded(it.childCount() <= 12)

        bb = QtWidgets.QDialogButtonBox()
        if exportando:
            self.btn_ok = bb.addButton(_tr("Arreglar y exportar"), QtWidgets.QDialogButtonBox.AcceptRole)
            b = bb.addButton(_tr("Exportar sin cambios"), QtWidgets.QDialogButtonBox.ActionRole)
            b.clicked.connect(lambda: self._cerrar("seguir"))
            b.setMinimumHeight(36); b.setProperty("secondary", True)
            c = bb.addButton(_tr("Cancelar"), QtWidgets.QDialogButtonBox.RejectRole)
        else:
            self.btn_ok = bb.addButton(_tr("Arreglar lo marcado"), QtWidgets.QDialogButtonBox.AcceptRole)
            c = bb.addButton(_tr("Cerrar"), QtWidgets.QDialogButtonBox.RejectRole)
        c.setMinimumHeight(36); c.setProperty("secondary", True)
        self.btn_ok.setDefault(True); self.btn_ok.setMinimumHeight(36)
        bb.accepted.connect(lambda: self._cerrar("arreglar"))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.arbol.itemChanged.connect(lambda *_: self._actualizar_boton())
        self._actualizar_boton()

    def _fila(self, c, etiqueta):
        quien = etiqueta(c.pipe)
        L = f"{c.largo_ft:.2f}"
        if c.tipo == "tramo":
            txt = (_tr("{u} · tramo de {l} ft: {como}").format(u=quien, l=L, como=_tr(_COMO.get(c.como, "")))
                   if c.arreglado else
                   _tr("{u} · tramo de {l} ft: no se arregla solo (junto a un buzón, una unión u otra curva)").format(
                       u=quien, l=L))
        elif c.tipo == "punta":
            txt = (_tr("{u} · punta a {l} ft de otra de su tipo: se une").format(u=quien, l=L) if c.arreglado else
                   _tr("{u} · punta a {l} ft de otra de su tipo: no se une sola (el tramo quedaría muy corto)").format(
                       u=quien, l=L))
        elif c.tipo == "corta":
            txt = _tr("{u} · mide {l} ft").format(u=quien, l=L)
        elif c.tipo == "duplicada":
            txt = _tr("{u} · repetida ({l} ft)").format(u=quien, l=L)
        else:
            txt = _tr("{u} · mide {l} ft y no toca ninguna otra de su tipo").format(u=quien, l=L)
        it = QtWidgets.QTreeWidgetItem([txt])
        it.setData(0, _ROL, (c.x, c.y, c.pipe))
        it.setToolTip(0, _tr("Clic para verlo en el plano."))
        return it

    def _clic(self, item, _col):
        dato = item.data(0, _ROL)
        if dato:
            self.ir_a(*dato)

    def tipos(self):
        return [t for t, g in self.grupos.items() if g.checkState(0) == QtCore.Qt.Checked]

    def _actualizar_boton(self):
        if not self._exportando:
            self.btn_ok.setEnabled(bool(self.tipos()))

    def _cerrar(self, accion):
        self.accion = accion
        if accion == "arreglar" and not self.tipos():
            self.accion = "seguir"
        self.accept()
