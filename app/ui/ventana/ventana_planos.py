"""ventana_planos.py — PLANOS de fondo del editor, como las pestañas de presentación de AutoCAD.

Pedido del usuario 2026-10-24: con una utilidad agregada desde otro PDF (`ventana_agregar`), la hoja
del editor muestra los planos de todas las utilidades fundidos y los rótulos de uno caen sobre los
del otro. Debajo del lienzo, una pestaña por plano: «Todos» (fundidos, como hasta ahora) y una por
cada grupo de hojas (`Piece.grupo`: 0 = la hoja del editor, 1… = cada utilidad agregada; su nombre,
las utilidades que trajo: `Composite.utilidades_grupo`, o sus PDF). Ctrl+RePág / Ctrl+AvPág las
recorren, como en AutoCAD. Solo aparecen si la hoja tiene más de un grupo.

Cambiar de plano cambia SOLO la imagen de fondo (y con ella las teselas nítidas y el imán a la
tinta): lo dibujado, el deshacer, la vista, el reconocimiento y el DXF siguen sobre la hoja de
todos. El plano de un grupo es la hoja compuesta con solo sus piezas y el mismo `marco`
(`hoja_calcada.solo_grupo`: mismo tamaño y coordenadas), materializada y dibujada en el proceso
trabajador; su PDF queda abierto en un temporal mientras sirva (`_planos_docs`, por firma). La
imagen del plano anterior queda en memoria (una sola) para volver al instante. La pestaña elegida
va al .digproj (`vista_fondo`; page.png es la imagen a la vista) y al respaldo del asistente.
"""
from __future__ import annotations

import json
import os
import tempfile

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from hoja import hoja_calcada
from traduccion.i18n import t as _tr
from ui.comun import busy as _busy_mod
from ui.comun.ui_common import layer_qcolor, swatch_icon


class PlanosFondoMixin:
    # ── barra de pestañas ─────────────────────────────────────────────────
    def _construir_barra_planos(self):
        """Lienzo + barra de planos debajo (la ventana central)."""
        self._vista_fondo = None          # None = «Todos»; si no, el grupo cuyo plano se ve
        self._planos_docs = {}            # grupo → (firma, fitz.Document, ruta temporal)
        self._planos_img = {}             # grupo → (QPixmap, grises, escala): el plano anterior
        self._planos_tarea = None
        self._planos_firma_barra = None
        cont = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(cont)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.canvas, 1)
        bar = self.barra_planos = QtWidgets.QTabBar()
        bar.setShape(QtWidgets.QTabBar.RoundedSouth)
        bar.setDocumentMode(True)
        bar.setExpanding(False)
        bar.setDrawBase(False)
        bar.setFocusPolicy(QtCore.Qt.NoFocus)
        bar.setUsesScrollButtons(True)
        bar.currentChanged.connect(self._al_elegir_plano)
        fila = self._fila_planos = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(fila)
        h.setContentsMargins(6, 0, 6, 0)
        h.setSpacing(8)
        self.lbl_planos = QtWidgets.QLabel()
        h.addWidget(self.lbl_planos)
        h.addWidget(bar)
        h.addStretch(1)
        fila.hide()
        lay.addWidget(fila)
        self.setCentralWidget(cont)
        for tecla, paso in ((QtCore.Qt.Key_PageDown, 1), (QtCore.Qt.Key_PageUp, -1)):
            sc = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | tecla), cont)
            sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda paso=paso: self._plano_siguiente(paso))

    def _nombre_plano(self, g) -> str:
        from reconocimiento.recognition import utility_label
        comp = self.composite
        utils = list((comp.utilidades_grupo or {}).get(int(g)) or ()) if comp is not None else []
        if utils:
            return " + ".join(_tr(utility_label(u)) for u in utils)
        nombres = []
        for p in comp.pieces if comp is not None else ():
            if int(p.grupo) == int(g) and p.source < len(self.src_pdfs):
                n = os.path.splitext(self.src_pdfs[p.source].get("name") or "")[0]
                if n and n not in nombres:
                    nombres.append(n)
        if nombres:
            texto = " + ".join(nombres)
            return texto if len(texto) <= 40 else texto[:39] + "…"
        return _tr("Plano {n}").format(n=int(g) + 1)

    def _utilidades_plano(self, g):
        comp = self.composite
        return list((comp.utilidades_grupo or {}).get(int(g)) or ()) if comp is not None else []

    def _sync_barra_planos(self):
        """Pestañas según los grupos de la hoja (lo llama cada redibujo: solo cambia si cambió algo)."""
        bar = getattr(self, "barra_planos", None)
        if bar is None:
            return
        gs = hoja_calcada.grupos(self.composite) if self.canvas.pixmap_item is not None else []
        if self._vista_fondo is not None and self._vista_fondo not in gs:
            self._vista_fondo = None
        nombres = [self._nombre_plano(g) for g in gs]
        firma = (tuple(gs), tuple(nombres), self._vista_fondo, _tr("Todos"))
        if firma == self._planos_firma_barra:
            return
        self._planos_firma_barra = firma
        bar.blockSignals(True)
        try:
            while bar.count():
                bar.removeTab(0)
            if gs:
                self.lbl_planos.setText(_tr("Plano:"))
                i = bar.addTab(_tr("Todos"))
                bar.setTabData(i, None)
                bar.setTabToolTip(i, _tr("Los planos de todas las utilidades juntos, fundidos.") + "\n"
                                  + _tr("Ctrl+RePág / Ctrl+AvPág: plano anterior / siguiente."))
                actual = 0
                for g, nombre in zip(gs, nombres):
                    utils = self._utilidades_plano(g)
                    i = bar.addTab(nombre)
                    if len(utils) == 1:
                        bar.setTabIcon(i, swatch_icon(layer_qcolor(utils[0]), 12))
                    bar.setTabData(i, int(g))
                    bar.setTabToolTip(i, _tr("Solo el plano original de {p}, sin los demás. Lo dibujado no cambia.")
                                      .format(p=nombre))
                    if self._vista_fondo == g:
                        actual = i
                bar.setCurrentIndex(actual)
        finally:
            bar.blockSignals(False)
        self._fila_planos.setVisible(bool(gs))

    def _al_elegir_plano(self, i):
        if i < 0:
            return
        g = self.barra_planos.tabData(i)
        if not self._mostrar_plano(g):
            self._planos_firma_barra = None           # vuelve a marcar la pestaña del plano a la vista
            self._sync_barra_planos()

    def _plano_siguiente(self, paso):
        bar = self.barra_planos
        if not self._fila_planos.isHidden() and bar.count() > 1:
            bar.setCurrentIndex((bar.currentIndex() + paso) % bar.count())

    # ── cambiar de plano ──────────────────────────────────────────────────
    def _mostrar_plano(self, g) -> bool:
        """La imagen de fondo del plano `g` (None = «Todos»). False si no se pudo (queda la de antes)."""
        if g == self._vista_fondo or self.canvas.pixmap_item is None or not self.doc:
            return g == self._vista_fondo
        nombre = _tr("Todos") if g is None else self._nombre_plano(g)
        guardada = self._planos_img.get(g)
        if guardada is None:
            with _busy_mod.busy(self, _tr("Mostrando el plano: {p}…").format(p=nombre),
                                _tr("Dibujando la hoja en pantalla…")) as ov:
                doc = self.doc if g is None else self._doc_de_plano(g, ov)
                if doc is None:
                    QtWidgets.QMessageBox.warning(self, _tr("Plano"), _tr("No se pudo armar el plano de {p}.").format(p=nombre))
                    return False
                qimg, gris, escala, ancho, alto = self._fondo_de(doc[self.page_idx if g is None else 0])
            tam = self.canvas.tam_hoja()
            if tam is not None and (abs(ancho - tam[0]) > 1.0 or abs(alto - tam[1]) > 1.0):
                QtWidgets.QMessageBox.warning(self, _tr("Plano"), _tr("El plano de {p} no mide lo mismo que la hoja.").format(p=nombre))
                return False
            guardada = (QtGui.QPixmap.fromImage(qimg), gris, escala)
            del qimg
        antes = (self.canvas.pixmap_item.pixmap(), self.gray, self.canvas.fondo_escala)
        self._planos_img = {self._vista_fondo: antes}     # solo el anterior: volver es al instante
        self._vista_fondo = g
        pm, self.gray, escala = guardada
        self.canvas.cambiar_imagen(pm, escala)
        if self.canvas.nitidez is not None:
            self.canvas.nitidez.fijar(self.canvas.pixmap_item)   # teselas del plano a la vista
        self._redraw()                                    # minimapa y marcas de las hojas de ese plano
        self._info(_tr("Plano a la vista: {p}.").format(p=nombre))
        return True

    def _firma_plano(self, g) -> str:
        sub = hoja_calcada.solo_grupo(self.composite, g)
        fuentes = sorted({p.source for p in sub.pieces})
        return json.dumps([sub.to_dict(), [(i, (self.src_pdfs[i].get("name") or "") if i < len(self.src_pdfs) else "",
                                            sorted((self.hidden_ocgs_by_source or {}).get(str(i), [])))
                                           for i in fuentes]], sort_keys=True)

    def _args_plano(self, g):
        sub = hoja_calcada.solo_grupo(self.composite, g)
        return (sub.to_dict(), [e["data"] for e in self.src_pdfs],
                {k: list(v) for k, v in (self.hidden_ocgs_by_source or {}).items()},
                [e.get("name", "") for e in self.src_pdfs])

    def _abrir_plano(self, g, firma, data):
        fd, ruta = tempfile.mkstemp(prefix="pdfcad_plano", suffix=".pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        self._cerrar_plano(g)
        doc = fitz.open(ruta)
        self._planos_docs[g] = (firma, doc, ruta)
        return doc

    def _doc_de_plano(self, g, ov=None):
        """El PDF (una hoja) del plano del grupo `g`: armado en el proceso trabajador, o el ya abierto."""
        from ui.comun import proceso
        firma = self._firma_plano(g)
        e = self._planos_docs.get(g)
        if e is not None and e[0] == firma and not e[1].is_closed:
            return e[1]

        def etapa(a):
            if ov is not None and a and a[0] == "detalle" and ov.active:
                ov.step(detail=_busy_mod.detalle_de(a[1], a[2], a[3]), pump=False)
        res, err = proceso.ejecutar("hoja.composite_trabajo:materializar", *self._args_plano(g), al_avanzar=etapa)
        if err or not res:
            return None
        return self._abrir_plano(g, firma, res[0])

    def _preparar_plano(self, g):
        """Arma el PDF del plano `g` sin esperar (proyecto reabierto con ese plano a la vista): al
        llegar, las teselas nítidas y el imán usan su hoja."""
        from ui.comun import proceso
        if self._planos_tarea is not None:
            return
        firma = self._firma_plano(g)
        t = proceso.Tarea("hoja.composite_trabajo:materializar", self._args_plano(g))

        def fin(res, err, g=g, firma=firma):
            self._planos_tarea = None
            if err or not res or self._vista_fondo != g or self.composite is None or firma != self._firma_plano(g):
                return
            self._abrir_plano(g, firma, res[0])
            if self.canvas.nitidez is not None:
                self.canvas.nitidez.invalidar()
        t.terminado.connect(fin)
        self._planos_tarea = t
        proceso.trabajador("principal").enviar(t)

    def _doc_del_fondo(self):
        """(PDF, nº de hoja) de lo que muestra el fondo: la hoja de trabajo o el plano a la vista
        (si su PDF aún no está, se prepara y mientras tanto None)."""
        g = getattr(self, "_vista_fondo", None)
        if g is None:
            return self.doc, self.page_idx
        if self.composite is None or g not in hoja_calcada.grupos(self.composite):
            return None, 0
        e = self._planos_docs.get(g)
        if e is not None and not e[1].is_closed and e[0] == self._firma_plano(g):
            return e[1], 0
        self._preparar_plano(g)
        return None, 0

    # ── al cambiar la hoja ────────────────────────────────────────────────
    def _cerrar_plano(self, g):
        e = self._planos_docs.pop(g, None)
        if e is None:
            return
        try:
            e[1].close()
        except Exception:
            pass
        try:
            os.remove(e[2])
        except OSError:
            pass

    def _soltar_planos(self):
        """Hoja nueva en el editor (o se cierra): «Todos», sin imágenes guardadas ni PDF de planos."""
        self._vista_fondo = None
        self._planos_img = {}
        for g in list(getattr(self, "_planos_docs", {})):
            self._cerrar_plano(g)
