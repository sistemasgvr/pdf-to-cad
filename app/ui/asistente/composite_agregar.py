"""composite_agregar.py — «Componer hoja» al agregar una utilidad desde otro PDF (mezcla de `CompositeDialog`).

Pedido del usuario 2026-11-18: antes, «Agregar utilidad» ubicaba TODAS las hojas del PDF nuevo antes de
mostrar nada (minutos con una 3.ª utilidad). Ahora el compositor se abre al instante con las hojas del PDF
nuevo y la búsqueda (`ui.ventana.agregar_busqueda.BusquedaAgregar`) corre en segundo plano:

  · cada hoja de la galería dice si cae sobre la hoja del editor («✔ Cae en la hoja del editor»,
    «Buscando…», «No cae en la hoja del editor»);
  · una tarjeta arriba dice cómo va y, al terminar, ofrece «Marcar las N» (las piezas calcadas, ya en su
    lugar y con su área);
  · marcar una hoja que ya se ubicó pone sus piezas calcadas (no la hoja entera con su cajetín);
  · al continuar, la ventana ubica solo lo marcado que falte (`ventana_agregar`).

Requiere de la clase: `self.comp`, `self.view`, `self.lst_pages`, `self._cur_source`, `self._cur_page` y los
métodos `_refresh_scale_combo`, `_refresh_summary`, `_on_pieces_changed`, `_hoja_elegida`,
`_refresh_source_selection`, `_go_tab`.
"""
from __future__ import annotations

from typing import List

from PySide6 import QtCore, QtWidgets

from hoja import composite as C
from traduccion.i18n import t as _tr
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

TAB_SHEET = 2


class AgregarCompositorMixin:
    _agregar = None                          # BusquedaAgregar (None fuera de «Agregar utilidad»)

    # ── tarjeta ─────────────────────────────────────────────────────────
    def _agr_card(self) -> QtWidgets.QFrame:
        t = _theme.tokens()
        box = QtWidgets.QFrame()
        box.setObjectName("agrCard")
        box.setStyleSheet(
            f"QFrame#agrCard {{ background:{t.surface_alt}; border:1px solid {t.accent}; "
            f"border-left:4px solid {t.accent}; border-radius:4px; }}"
            f"QFrame#agrCard QLabel {{ background:transparent; border:none; }}")
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 8, 12); lay.setSpacing(8)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8)
        ic = QtWidgets.QLabel()
        ic.setPixmap(_icon("mdi:map-search-outline", color=t.accent).pixmap(QtCore.QSize(20, 20)))
        row.addWidget(ic, 0, QtCore.Qt.AlignTop)
        self.lbl_agr = QtWidgets.QLabel()
        self.lbl_agr.setWordWrap(True)
        self.lbl_agr.setTextFormat(QtCore.Qt.RichText)
        row.addWidget(self.lbl_agr, 1)
        lay.addLayout(row)
        self.bar_agr = QtWidgets.QProgressBar()
        self.bar_agr.setTextVisible(False)
        self.bar_agr.setFixedHeight(6)
        lay.addWidget(self.bar_agr)
        self.btn_agr_marcar = QtWidgets.QPushButton(_icon("mdi:check-all", color=t.text), "")
        self.btn_agr_marcar.setProperty("kind", "primary")
        self.btn_agr_marcar.setAutoDefault(False)
        self.btn_agr_marcar.setToolTip(_tr("Pone en la hoja compuesta las hojas que caen sobre la hoja del "
                                           "editor, cada una con su área y en su lugar"))
        self.btn_agr_marcar.clicked.connect(self._agr_marcar_todas)
        fila = QtWidgets.QHBoxLayout(); fila.setSpacing(8)
        fila.addWidget(self.btn_agr_marcar)
        fila.addStretch(1)
        lay.addLayout(fila)
        box.hide()
        self.agr_card = box
        return box

    def _agr_iniciar(self, busqueda):
        self._agregar = busqueda
        if busqueda is None:
            return
        # una línea más bajo cada miniatura (el estado de la hoja)
        extra = self._agr_extra = self.lst_pages.fontMetrics().lineSpacing() + 2
        g = self.lst_pages.gridSize()
        self.lst_pages.setGridSize(QtCore.QSize(g.width(), g.height() + extra))
        for i in range(self.lst_pages.count()):
            it = self.lst_pages.item(i)
            h = it.sizeHint()
            if h.isValid():
                it.setSizeHint(QtCore.QSize(h.width(), h.height() + extra))
        busqueda.cambio.connect(self._agr_cambio)
        self._agr_cambio()

    def _agr_desconectar(self):
        b = self._agregar
        if b is None:
            return
        try:
            b.cambio.disconnect(self._agr_cambio)
        except (RuntimeError, TypeError):
            pass

    # ── estado por hoja ─────────────────────────────────────────────────
    def _agr_linea(self, page: int):
        """(texto, globo, apagada) del estado de esa hoja del PDF a la vista, o None."""
        b = self._agregar
        if b is None:
            return None
        from ui.ventana.agregar_busqueda import ENCAJA, NO_CAE
        e = b.estado(self._cur_source, page)
        if e == ENCAJA:
            return (_tr("✔ Cae en la hoja del editor"),
                    _tr("Su mapa base coincide con el de la hoja del editor: al marcarla queda en su lugar."), False)
        if e == NO_CAE:
            return (_tr("No cae en la hoja del editor"),
                    _tr("Su mapa base no coincide con ninguna parte de la hoja del editor: es de otra zona."), True)
        return (_tr("Buscando…"), _tr("Se está buscando dónde cae sobre la hoja del editor."), False)

    def _agr_cambio(self):
        b = self._agregar
        if b is None or not hasattr(self, "agr_card"):
            return
        for i in range(self.lst_pages.count()):
            self._label_page_item(self.lst_pages.item(i), i)
        nombre = ", ".join(e["name"] for e in b.nuevas)
        k = len(b.ubicadas())
        total = sum(d.page_count for d in self.docs)
        faltan = self._agr_faltan()
        self.btn_agr_marcar.hide()
        if b.corriendo():
            texto, i, n = b.avance
            pct = int(round(100.0 * i / n)) if n else None
            self.lbl_agr.setText(
                _tr("<b>Buscando dónde cae cada hoja</b> de «{pdf}» sobre la hoja del editor…").format(pdf=nombre)
                + (" <b>%d %%</b>" % pct if pct is not None else "") + "<br>"
                + _tr("Ya encajan {k} hojas (✔ en la lista). Puedes ir mirando y marcando: al continuar se "
                      "ubican las que falten.").format(k=k))
            self.bar_agr.setRange(0, 0 if pct is None else 100)
            if pct is not None:
                self.bar_agr.setValue(pct)
            self.bar_agr.show()
        elif b.cancelada:
            self.agr_card.hide()
            return
        else:
            self.bar_agr.hide()
            if b.error:
                self.lbl_agr.setText(_tr("No se pudo terminar la búsqueda: {e}<br>Puedes marcar hojas igual: al "
                                         "continuar se ubican.").format(e=b.error))
            elif k:
                self.lbl_agr.setText(_tr("<b>{k} de {t} hojas</b> de «{pdf}» caen sobre la hoja del editor "
                                         "(✔ en la lista). Márcalas y continúa.").format(k=k, t=total, pdf=nombre))
                if faltan:
                    self.btn_agr_marcar.setText(_tr("Marcar las {n}").format(n=len(faltan)))
                    self.btn_agr_marcar.show()
            else:
                self.lbl_agr.setText(_tr("Ninguna hoja de «{pdf}» cae sobre la hoja del editor. Lo más común es que "
                                         "sea el PDF de otra zona: cancela y elige otro PDF.").format(pdf=nombre))
        self.agr_card.show()
        if hasattr(self, "btn_ok"):
            self._refresh_checks()                      # «Continuar» se activa cuando la búsqueda termina

    def _ocupado(self) -> bool:
        """La búsqueda de dónde cae cada hoja del PDF agregado sigue en marcha: la composición no está terminada y
        «Continuar» espera (2026-11-21: estaba activo con la composición a medias)."""
        b = getattr(self, "_agregar", None)
        return bool(b is not None and b.corriendo())

    def _agr_faltan(self) -> List[tuple]:
        b = self._agregar
        ya = {(p.source, p.page) for p in self.comp.pieces}
        return [k for k in b.ubicadas() if k not in ya] if b is not None else []

    # ── marcar ──────────────────────────────────────────────────────────
    def _agr_poner(self, hojas) -> int:
        """Pone en la hoja compuesta las piezas calcadas de esas hojas (ya en su lugar). → cuántas hojas."""
        b = self._agregar
        ya = {(p.source, p.page) for p in self.comp.pieces}
        puestas = 0
        for clave in hojas:
            if clave in ya or clave not in b.piezas:
                continue
            for d in b.piezas[clave]:
                self.comp.pieces.append(C.Piece.from_dict(d))
            puestas += 1
        if not puestas:
            return 0
        self._hoja_elegida()
        self._provisional = None
        self.comp.scale_ft_per_pt = b.escala
        self._editing = -1
        self._refresh_scale_combo()
        self.view.rebuild()
        self._refresh_summary()
        self._on_pieces_changed()
        self._refresh_source_selection()
        self._agr_cambio()
        return puestas

    def _agr_marcar_todas(self):
        if self._agr_poner(self._agr_faltan()):
            self._fitted.discard(TAB_SHEET)
            self._go_tab(TAB_SHEET)

    def _use_page(self, row: int):
        """Marcar la casilla de una hoja YA ubicada: sus piezas calcadas (su área, en su lugar)."""
        b = self._agregar
        if b is not None and (self._cur_source, row) in b.piezas:
            if row != self._cur_page:
                self.lst_pages.setCurrentRow(row)
            self._agr_poner([(self._cur_source, row)])
            return
        super()._use_page(row)

