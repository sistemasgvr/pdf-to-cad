"""Ventana «Revisar y limpiar el dibujo» (Herramientas, y antes de exportar el DXF).

Muestra lo que encontró `nucleo.limpieza` (sobre una COPIA del dibujo). Arriba, un
RESUMEN en palabras simples («3 líneas que casi tocan a otra: se unirán»); debajo,
«Ver detalles» con un grupo por tipo de arreglo (casilla para elegir qué se arregla),
un grupo «Para revisar» con lo que no se arregla solo y clic en un caso = ir a ese
lugar. Al exportar (pedido del usuario 2026-10-09: «más fácil de entender, más
resumido») el detalle arranca plegado.
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
# Resumen de cada grupo, en palabras simples (clave = Cambio.tipo).
_RESUMEN = {
    "punta": N_("{n} línea(s) que casi tocan a otra: se unirán"),
    "corta": N_("{n} línea(s) muy cortas (menos de {corta} ft): se borrarán"),
    "duplicada": N_("{n} línea(s) repetidas: se borrará la copia"),
    "tramo": N_("{n} tramo(s) rectos diminutos: se corrigen"),
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
        self.setWindowTitle(_tr("Antes de exportar") if exportando else _tr("Revisar y limpiar el dibujo"))
        self.setMinimumWidth(520)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(10)
        txt = (_tr("Encontramos algunas cosas que conviene arreglar antes de exportar:")
               if exportando else _tr("Esto saldría mal en Civil 3D o habría que corregirlo a mano:"))
        cab = QtWidgets.QLabel(txt)
        f = cab.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() * 1.1); cab.setFont(f)
        cab.setWordWrap(True)
        lay.addWidget(cab)
        fmt0 = {"corta": f"{limpieza.UTILIDAD_MIN_FT:g}"}
        lineas = [_tr(_RESUMEN[tp]).format(n=len(res.de(tp, True)), **fmt0)
                  for tp in limpieza.ARREGLABLES if res.de(tp, True)]
        if not exportando and res.avisos:
            lineas.append(_tr("{n} caso(s) para revisar a mano").format(n=len(res.avisos)))
        resumen = QtWidgets.QLabel("<br>".join("•&nbsp;" + ln for ln in lineas))
        resumen.setTextFormat(QtCore.Qt.RichText)
        resumen.setWordWrap(True)
        resumen.setStyleSheet("font-size: 11pt;")
        lay.addWidget(resumen)
        ayuda = QtWidgets.QLabel(_tr("Se puede deshacer con Ctrl+Z."))
        ayuda.setWordWrap(True); ayuda.setProperty("muted", True)
        lay.addWidget(ayuda)
        self.btn_detalles = QtWidgets.QToolButton()
        self.btn_detalles.setCheckable(True)
        self.btn_detalles.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_detalles.setArrowType(QtCore.Qt.RightArrow)
        self.btn_detalles.setText(_tr("Ver detalles (elegir qué arreglar, ir a cada caso)"))
        self.btn_detalles.setStyleSheet("QToolButton{border:0; padding:2px;}")
        lay.addWidget(self.btn_detalles, 0, QtCore.Qt.AlignLeft)

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
            b = bb.addButton(_tr("Exportar sin arreglar"), QtWidgets.QDialogButtonBox.ActionRole)
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
        self.btn_detalles.toggled.connect(self._ver_detalles)
        self.btn_detalles.setChecked(not exportando)
        self._ver_detalles(not exportando)
        self._actualizar_boton()

    def _ver_detalles(self, ver):
        self.arbol.setVisible(ver)
        self.btn_detalles.setArrowType(QtCore.Qt.DownArrow if ver else QtCore.Qt.RightArrow)
        if ver:
            self.resize(max(self.width(), 680), max(self.height(), 480))
        else:
            self.adjustSize()

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
