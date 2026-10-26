"""ventana_planos.py — PLANOS de fondo del editor, como CAPAS de AutoCAD (se encienden y apagan).

Pedido del usuario 2026-10-24: con una utilidad agregada desde otro PDF (`ventana_agregar`), la hoja
del editor muestra los planos de todas las utilidades fundidos y los rótulos de uno caen sobre los
del otro. Cada grupo de hojas (`Piece.grupo`: 0 = la hoja del editor, 1… = cada utilidad agregada; su
nombre, las utilidades que trajo: `Composite.utilidades_grupo`, o sus PDF) es un plano.

2026-10-26 (pedido del usuario: «que se manejen como en AutoCAD, para activar y desactivar capas»):
ya no son pestañas al pie del lienzo sino filas del desplegable «Capas» de la barra (`ventana_capas`),
y se ve CUALQUIER combinación: todos encendidos = la hoja de todos (la de trabajo, como siempre);
algunos = la hoja compuesta con solo sus piezas y el mismo `marco` (`hoja_calcada.solo_grupos`: mismo
tamaño y coordenadas), materializada y dibujada en el proceso trabajador; ninguno = papel vacío (la
imagen se oculta y el imán a la tinta no engancha).

Cambiar los planos cambia SOLO la imagen de fondo (y con ella las teselas nítidas y el imán a la
tinta): lo dibujado, el deshacer, la vista, el reconocimiento y el DXF siguen sobre la hoja de todos.
`_vista_fondo` = la imagen cargada (None = todos; si no, frozenset de grupos) y `_fondo_apagado` =
ninguno a la vista. Su PDF queda abierto en un temporal mientras sirva (`_planos_docs`, por firma); la
imagen anterior queda en memoria (una sola) para volver al instante. Van al .digproj (`vista_fondo`,
`fondo_apagado`; page.png es la imagen cargada) y al respaldo del asistente.
"""
from __future__ import annotations

import json
import os
import tempfile

import fitz
from PySide6 import QtGui, QtWidgets

from hoja import hoja_calcada
from traduccion.i18n import t as _tr
from ui.comun import busy as _busy_mod


def clave_planos(visibles, gs):
    """Clave de la imagen para los grupos `visibles` de la hoja con grupos `gs`: None = todos (la
    hoja de trabajo), frozenset = solo esos. Vacío → frozenset() (ninguno)."""
    vis = frozenset(int(g) for g in visibles) & frozenset(gs)
    return None if gs and vis == frozenset(gs) else vis


class PlanosFondoMixin:
    def _construir_planos(self):
        """Estado de los planos de fondo (el lienzo es la ventana central)."""
        self._vista_fondo = None          # None = todos; si no, frozenset de los grupos cuya imagen se ve
        self._fondo_apagado = False       # ningún plano encendido: papel vacío
        self._planos_docs = {}            # clave → (firma, fitz.Document, ruta temporal)
        self._planos_img = {}             # clave → (QPixmap, grises, escala): la imagen anterior
        self._planos_tarea = None
        self.capas_apagadas = set()       # utilidades apagadas en «Capas» (ventana_capas)
        self.setCentralWidget(self.canvas)

    def _nombre_plano(self, g) -> str:
        from reconocimiento.recognition import utility_label
        comp = self.composite
        utils = self._utilidades_plano(g)
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

    def _pdfs_plano(self, g) -> str:
        """Los PDF de origen del plano `g` (para el globo de su fila en «Capas»)."""
        comp = self.composite
        nombres = []
        for p in comp.pieces if comp is not None else ():
            if int(p.grupo) == int(g) and p.source < len(self.src_pdfs):
                n = self.src_pdfs[p.source].get("name") or ""
                if n and n not in nombres:
                    nombres.append(n)
        return ", ".join(nombres)

    def _utilidades_plano(self, g):
        comp = self.composite
        return list((comp.utilidades_grupo or {}).get(int(g)) or ()) if comp is not None else []

    def _grupos_planos(self):
        """Los planos de la hoja (grupos), o [] si la hoja no tiene utilidades agregadas."""
        return hoja_calcada.grupos(self.composite) if self.canvas.pixmap_item is not None else []

    def _planos_encendidos(self):
        """Los grupos cuyo plano se ve ahora."""
        gs = self._grupos_planos()
        if not gs or self._fondo_apagado:
            return []
        if self._vista_fondo is None:
            return list(gs)
        return sorted(set(self._vista_fondo) & set(gs))

    # ── encender / apagar ─────────────────────────────────────────────────
    def _poner_planos(self, visibles) -> bool:
        """Deja a la vista los planos `visibles` (grupos). False si no se pudo (queda lo de antes)."""
        gs = self._grupos_planos()
        if not gs or not self.doc:
            return False
        clave = clave_planos(visibles, gs)
        if clave is not None and not clave:
            if not self._fondo_apagado:
                self._apagar_fondo(True)
                self._redraw()
            self._info(_tr("Planos de fondo apagados: solo lo dibujado."))
            return True
        cambia = clave != self._vista_fondo
        if cambia and not self._mostrar_plano(clave):
            return False
        if self._fondo_apagado:
            self._apagar_fondo(False)
        self._redraw()                                    # minimapa y marcas de las hojas de ese plano
        self._info(_tr("Planos a la vista: {p}.").format(p=self._nombre_vista(clave)))
        return True

    def _nombre_vista(self, clave) -> str:
        if clave is None:
            return _tr("Todos")
        return " · ".join(self._nombre_plano(g) for g in sorted(clave))

    def _apagar_fondo(self, apagado: bool):
        self._fondo_apagado = bool(apagado)
        self.canvas.ocultar_fondo(self._fondo_apagado)
        if self.canvas.nitidez is not None:
            self.canvas.nitidez.invalidar()                # sin plano no hay teselas que pedir

    def _mostrar_plano(self, clave) -> bool:
        """Carga la imagen de fondo de `clave` (None = todos, frozenset = esos grupos). False si no se
        pudo (queda la de antes)."""
        if isinstance(clave, int):
            clave = frozenset((clave,))
        if clave == self._vista_fondo or self.canvas.pixmap_item is None or not self.doc:
            return clave == self._vista_fondo
        nombre = self._nombre_vista(clave)
        guardada = self._planos_img.get(clave)
        if guardada is None:
            with _busy_mod.busy(self, _tr("Mostrando el plano: {p}…").format(p=nombre),
                                _tr("Dibujando la hoja en pantalla…")) as ov:
                doc = self.doc if clave is None else self._doc_de_plano(clave, ov)
                if doc is None:
                    QtWidgets.QMessageBox.warning(self, _tr("Plano"), _tr("No se pudo armar el plano de {p}.").format(p=nombre))
                    return False
                qimg, gris, escala, ancho, alto = self._fondo_de(doc[self.page_idx if clave is None else 0])
            tam = self.canvas.tam_hoja()
            if tam is not None and (abs(ancho - tam[0]) > 1.0 or abs(alto - tam[1]) > 1.0):
                QtWidgets.QMessageBox.warning(self, _tr("Plano"), _tr("El plano de {p} no mide lo mismo que la hoja.").format(p=nombre))
                return False
            guardada = (QtGui.QPixmap.fromImage(qimg), gris, escala)
            del qimg
        antes = (self.canvas.pixmap_item.pixmap(), self.gray, self.canvas.fondo_escala)
        self._planos_img = {self._vista_fondo: antes}     # solo el anterior: volver es al instante
        self._vista_fondo = clave
        pm, self.gray, escala = guardada
        self.canvas.cambiar_imagen(pm, escala)
        if self.canvas.nitidez is not None:
            self.canvas.nitidez.fijar(self.canvas.pixmap_item)   # teselas del plano a la vista
        return True

    def _firma_plano(self, clave) -> str:
        sub = hoja_calcada.solo_grupos(self.composite, clave)
        fuentes = sorted({p.source for p in sub.pieces})
        return json.dumps([sub.to_dict(), [(i, (self.src_pdfs[i].get("name") or "") if i < len(self.src_pdfs) else "",
                                            sorted((self.hidden_ocgs_by_source or {}).get(str(i), [])))
                                           for i in fuentes]], sort_keys=True)

    def _args_plano(self, clave):
        sub = hoja_calcada.solo_grupos(self.composite, clave)
        return (sub.to_dict(), [e["data"] for e in self.src_pdfs],
                {k: list(v) for k, v in (self.hidden_ocgs_by_source or {}).items()},
                [e.get("name", "") for e in self.src_pdfs])

    def _abrir_plano(self, clave, firma, data):
        fd, ruta = tempfile.mkstemp(prefix="pdfcad_plano", suffix=".pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        self._cerrar_plano(clave)
        doc = fitz.open(ruta)
        self._planos_docs[clave] = (firma, doc, ruta)
        return doc

    def _doc_de_plano(self, clave, ov=None):
        """El PDF (una hoja) del plano `clave`: armado en el proceso trabajador, o el ya abierto."""
        from ui.comun import proceso
        firma = self._firma_plano(clave)
        e = self._planos_docs.get(clave)
        if e is not None and e[0] == firma and not e[1].is_closed:
            return e[1]

        def etapa(a):
            if ov is not None and a and a[0] == "detalle" and ov.active:
                ov.step(detail=_busy_mod.detalle_de(a[1], a[2], a[3]), pump=False)
        res, err = proceso.ejecutar("hoja.composite_trabajo:materializar", *self._args_plano(clave), al_avanzar=etapa)
        if err or not res:
            return None
        return self._abrir_plano(clave, firma, res[0])

    def _preparar_plano(self, clave):
        """Arma el PDF del plano `clave` sin esperar (proyecto reabierto con ese plano a la vista): al
        llegar, las teselas nítidas y el imán usan su hoja."""
        from ui.comun import proceso
        if self._planos_tarea is not None:
            return
        firma = self._firma_plano(clave)
        t = proceso.Tarea("hoja.composite_trabajo:materializar", self._args_plano(clave))

        def fin(res, err, clave=clave, firma=firma):
            self._planos_tarea = None
            if err or not res or self._vista_fondo != clave or self.composite is None or firma != self._firma_plano(clave):
                return
            self._abrir_plano(clave, firma, res[0])
            if self.canvas.nitidez is not None:
                self.canvas.nitidez.invalidar()
        t.terminado.connect(fin)
        self._planos_tarea = t
        proceso.trabajador("principal").enviar(t)

    def _doc_del_fondo(self):
        """(PDF, nº de hoja) de lo que muestra el fondo: la hoja de trabajo o los planos a la vista
        (si su PDF aún no está, se prepara y mientras tanto None). Sin planos a la vista, None."""
        if getattr(self, "_fondo_apagado", False):
            return None, 0
        clave = getattr(self, "_vista_fondo", None)
        if clave is None:
            return self.doc, self.page_idx
        if self.composite is None or not clave <= set(hoja_calcada.grupos(self.composite)):
            return None, 0
        e = self._planos_docs.get(clave)
        if e is not None and not e[1].is_closed and e[0] == self._firma_plano(clave):
            return e[1], 0
        self._preparar_plano(clave)
        return None, 0

    # ── al cambiar la hoja ────────────────────────────────────────────────
    def _cerrar_plano(self, clave):
        e = self._planos_docs.pop(clave, None)
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
        """Hoja nueva en el editor (o se cierra): todos los planos a la vista, sin imágenes guardadas ni
        PDF de planos."""
        self._vista_fondo = None
        self._planos_img = {}
        if getattr(self, "_fondo_apagado", False):
            self._apagar_fondo(False)
        for g in list(getattr(self, "_planos_docs", {})):
            self._cerrar_plano(g)
