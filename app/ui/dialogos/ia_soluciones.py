"""IA → «Resolver conflictos…» (pedido del usuario 2026-10-23, punto 3): por cada conflicto C-n, las soluciones que
la app calculó y PROBÓ en una copia del proyecto (`ventana_soluciones`), la recomendada por la IA con su porqué
(`ia/soluciones_ia`; sin IA, la de la app) y «Aplicar» en un solo paso de deshacer. No modal: se puede ir y
volver al plano. La explicación queda guardada en la memoria del proyecto (no se vuelve a pedir)."""
from __future__ import annotations

import html
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from ia import proveedor as P, soluciones_ia
from nucleo import informe_datos
from nucleo.soluciones import CON_PROPUESTA
from traduccion.i18n import t as _tr

_ROL = QtCore.Qt.UserRole


class _Senales(QtCore.QObject):
    trozo = QtCore.Signal(object, str)
    listo = QtCore.Signal(object, object)


class SolucionesDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win, QtCore.Qt.Window)
        self.win = win
        self.setWindowTitle(_tr("Resolver conflictos"))
        self.resize(980, 640)
        self._actual = None                               # (conflicto, propuestas, ficha)
        self._pedido = 0                                  # la respuesta de la IA de otro conflicto se descarta
        self._senales = _Senales(self)
        self._senales.trozo.connect(self._al_trozo)
        self._senales.listo.connect(self._al_listo)
        from ui.comun import ia_estilo as E
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(12)
        lay.addWidget(E.Encabezado("mdi:auto-fix", _tr("Resolver conflictos"), _tr(
            "Elige un conflicto: la app calcula las soluciones posibles y las prueba en una copia del proyecto (que "
            "el conflicto desaparezca sin crear otros problemas). La IA recomienda una y explica por qué. «Aplicar» "
            "se deshace con Ctrl+Z.")))
        div = QtWidgets.QSplitter()
        div.setChildrenCollapsible(False)
        izq = QtWidgets.QWidget()
        il = QtWidgets.QVBoxLayout(izq)
        il.setContentsMargins(0, 0, 6, 0)
        il.setSpacing(8)
        self.chk_auto = QtWidgets.QCheckBox(_tr("Solo los que tienen solución automática"))
        self.chk_auto.toggled.connect(lambda _on: self.refrescar())
        self.lista = QtWidgets.QListWidget()
        self.lista.setIconSize(QtCore.QSize(18, 18))
        self.lista.setAccessibleName(_tr("Resolver conflictos"))
        self.lista.currentItemChanged.connect(lambda it, _p: self._elegir(it))
        il.addWidget(self.chk_auto)
        il.addWidget(self.lista, 1)
        der = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(der)
        dl.setContentsMargins(6, 0, 0, 0)
        dl.setSpacing(8)
        self.lbl_titulo = QtWidgets.QLabel()
        self.lbl_titulo.setWordWrap(True)
        self.lbl_msg = QtWidgets.QLabel()
        self.lbl_msg.setWordWrap(True)
        self.props = QtWidgets.QTreeWidget()
        self.props.setHeaderLabels([_tr("Propuesta"), _tr("Resultado al probarla")])
        self.props.setRootIsDecorated(False)
        self.props.setWordWrap(True)
        self.props.setIconSize(QtCore.QSize(18, 18))
        self.props.header().setStretchLastSection(True)
        self.props.setColumnWidth(0, 420)
        # sin propuestas: un mensaje en vez de una tabla vacía
        self.lbl_sin_props = QtWidgets.QLabel(_tr("No hay una solución automática para este tipo de conflicto: "
                                                  "hay que cambiar el dibujo."))
        self.lbl_sin_props.setWordWrap(True)
        self.lbl_sin_props.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_sin_props.setObjectName("sinPropuestas")
        self.lbl_sin_props.setMinimumHeight(90)
        self.lbl_sin_props.hide()
        self.caja_rec = QtWidgets.QFrame()               # la recomendación, en una tarjeta con borde de acento
        self.caja_rec.setObjectName("recomendacion")
        rl = QtWidgets.QVBoxLayout(self.caja_rec)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(4)
        cab_rec = QtWidgets.QHBoxLayout()
        self.ico_rec = QtWidgets.QLabel()
        self.ico_rec.setStyleSheet("background: transparent;")
        cab_rec.addWidget(self.ico_rec)
        cab_rec.addWidget(E.etiqueta_seccion(_tr("Recomendación")), 1)
        rl.addLayout(cab_rec)
        self.texto = QtWidgets.QTextBrowser()
        self.texto.setMaximumHeight(150)
        self.texto.setFrameShape(QtWidgets.QFrame.NoFrame)
        rl.addWidget(self.texto)
        botones = QtWidgets.QHBoxLayout()
        self.btn_ver = QtWidgets.QPushButton(_tr("Ver en el plano"))
        self.btn_ver.setProperty("secondary", True)
        self.btn_aplicar = QtWidgets.QPushButton(_tr("Aplicar la propuesta elegida"))
        self.btn_ver.clicked.connect(self._ver)
        self.btn_aplicar.clicked.connect(self._aplicar)
        self.props.currentItemChanged.connect(lambda *_a: self._botones())
        botones.addWidget(self.btn_ver)
        botones.addStretch(1)
        botones.addWidget(self.btn_aplicar)
        for w in (self.lbl_titulo, self.lbl_msg):
            dl.addWidget(w)
        dl.addSpacing(4)
        dl.addWidget(E.etiqueta_seccion(_tr("Propuestas")))
        dl.addWidget(self.props, 1)
        dl.addWidget(self.lbl_sin_props, 1)
        dl.addWidget(self.caja_rec)
        dl.addLayout(botones)
        div.addWidget(izq)
        div.addWidget(der)
        div.setSizes([310, 670])
        lay.addWidget(div, 1)
        self.lbl_estado = QtWidgets.QLabel()
        self.lbl_estado.setObjectName("hint")
        self.lbl_estado.setWordWrap(True)
        lay.addWidget(self.lbl_estado)
        E.al_cambiar_tema(self, self._estilo)
        self.refrescar()

    def _estilo(self):
        from ui.comun import ia_estilo as E, icons, theme
        tk = theme.tokens()
        self.lbl_titulo.setStyleSheet(f"font-weight: 600; font-size: 16px; color: {tk.text};")
        self.lbl_msg.setStyleSheet(f"color: {tk.text_muted};")
        self.lbl_sin_props.setStyleSheet(f"#sinPropuestas {{ color: {tk.text_muted}; background: {tk.input_bg};"
                                         f" border: 1px dashed {tk.border}; border-radius: 8px; padding: 16px; }}")
        self.caja_rec.setStyleSheet(E.tarjeta("recomendacion", tk, borde_izq=tk.accent))
        E.texto_en_tarjeta(self.texto)
        self.ico_rec.setPixmap(E.pix("mdi:lightbulb-on", tk.accent if not theme.is_dark() else tk.focus, 18))
        self.btn_ver.setIcon(icons.icon("mdi:crosshairs-gps", color=tk.text))
        self.btn_aplicar.setIcon(icons.icon("mdi:check", color=tk.text_on_accent))
        self._ico_auto = icons.icon("mdi:auto-fix", color=tk.accent if not theme.is_dark() else tk.focus)
        vacio = QtGui.QPixmap(18, 18)
        vacio.fill(QtCore.Qt.transparent)
        self._ico_vacio = QtGui.QIcon(vacio)
        self._ico_ok = icons.icon("mdi:check-circle-outline", color=tk.success)
        self._ico_no = icons.icon("mdi:close", color=tk.danger)
        self._ico_rec = icons.icon("mdi:lightbulb-on", color=tk.accent if not theme.is_dark() else tk.focus)
        for k in range(self.lista.count()):                  # retintar sin volver a calcular nada
            it = self.lista.item(k)
            it.setIcon(self._ico_auto if it.data(_ROL + 1) else self._ico_vacio)
        if getattr(self, "_actual", None) is not None:
            self._llenar(self._actual[1], getattr(self, "_rec", None))

    # ── lista de conflictos ──
    def refrescar(self, elegir=None):
        self.win._resultados_al_dia()
        solo = self.chk_auto.isChecked()
        self.lista.blockSignals(True)
        self.lista.clear()
        for c in getattr(self.win, "_conflictos", None) or []:
            auto = c.clave in CON_PROPUESTA or c.clave == "redes"
            if solo and not auto:
                continue
            it = QtWidgets.QListWidgetItem(self._ico_auto if auto else self._ico_vacio, f"{c.id} · {_tr(c.titulo)}")
            it.setData(_ROL, c.id)
            it.setData(_ROL + 1, auto)
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        n = self.lista.count()
        fila = next((k for k in range(n) if self.lista.item(k).data(_ROL) == elegir), 0 if n else -1)
        if fila >= 0:
            self.lista.setCurrentRow(fila)
        else:
            self._limpiar(_tr("No hay conflictos en el dibujo."))

    def elegir(self, cid):
        self.refrescar(elegir=cid)

    def _limpiar(self, msg=""):
        self._actual = None
        self.lbl_titulo.setText(msg)
        self.lbl_msg.clear()
        self.props.clear()
        self.props.show()
        self.lbl_sin_props.hide()
        self.texto.clear()
        self._botones()

    def _elegir(self, it):
        if it is None:
            return self._limpiar()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            c, props = self.win.soluciones_de(it.data(_ROL))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if c is None:
            return self._limpiar()
        ficha = informe_datos.ficha_conflicto(c, self.win.pipes)
        self._actual = (c, props, ficha)
        self.lbl_titulo.setText(f"{c.id} · {_tr(c.titulo)}")
        self.lbl_msg.setText(" ".join((c.mensaje or "").split()))
        self.win._ir_a_elemento(c.x, c.y, activar=False)
        self._llenar(props, None)
        self._recomendar(c, props, ficha)

    def _llenar(self, props, rec):
        self.props.clear()
        from ui.comun import theme
        tk = theme.tokens()
        self._rec = rec
        for p in props:
            if p.valida:
                res = _tr("Resuelve el conflicto sin crear otros problemas")
                if p.otros_resueltos:
                    res += " " + _tr("(y resuelve {n} más)").format(n=p.otros_resueltos)
            elif not p.resuelve:
                res = _tr("No resuelve el conflicto")
            else:
                res = _tr("Crearía: {p}").format(p="; ".join(p.nuevos[:3]) + ("…" if len(p.nuevos) > 3 else ""))
            it = QtWidgets.QTreeWidgetItem([f"{p.id}. {p.texto}", res])
            it.setIcon(0, self._ico_rec if p.id == rec else self._ico_vacio)
            it.setIcon(1, self._ico_ok if p.valida else self._ico_no)
            if p.id == rec:                                  # la recomendada, en negrita
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
            if not p.valida:
                it.setForeground(1, QtGui.QBrush(QtGui.QColor(tk.text_muted)))
            it.setData(0, _ROL, p.id)
            it.setToolTip(0, p.texto)
            it.setToolTip(1, res)
            self.props.addTopLevelItem(it)
            if p.id == rec:
                self.props.setCurrentItem(it)
        if rec is None and self.props.topLevelItemCount():
            self.props.setCurrentItem(self.props.topLevelItem(0))
        vacio = not props
        self.props.setVisible(not vacio)
        self.lbl_sin_props.setVisible(vacio and self._actual is not None)
        self._botones()

    def _botones(self):
        p = self._propuesta()
        self.btn_aplicar.setEnabled(bool(p and p.valida))
        self.btn_ver.setEnabled(self._actual is not None)

    def _propuesta(self):
        it = self.props.currentItem()
        if it is None or self._actual is None:
            return None
        return next((p for p in self._actual[1] if p.id == it.data(0, _ROL)), None)

    # ── recomendación (IA o app) ──
    def _recomendar(self, c, props, ficha):
        self._pedido += 1
        pedido = self._pedido
        prov = P.crear(self.win._config_ia())
        if prov is None:
            rec, txt = soluciones_ia.plantilla(ficha, props)
            return self._mostrar(rec, txt, _tr("Sin IA: recomendación de la app."))
        mem = self.win._ia_memoria()
        self.texto.setHtml("<i>" + html.escape(_tr("La IA está pensando…")) + "</i>")
        self._buffer = ""

        def correr():
            try:
                r = soluciones_ia.recomendar(prov, ficha, props, mem,
                                             al_texto=lambda s: self._senales.trozo.emit(pedido, s))
            except P.ErrorIA as e:
                rec, txt = soluciones_ia.plantilla(ficha, props)
                r = (rec, txt, _tr("La IA no respondió ({e}): recomendación de la app.").format(e=e))
            self._senales.listo.emit(pedido, r)
        threading.Thread(target=correr, name="pdfcad-ia-soluciones", daemon=True).start()

    def _al_trozo(self, pedido, s):
        if pedido != self._pedido:
            return
        self._buffer += s
        self.texto.setPlainText(self._buffer)

    def _al_listo(self, pedido, r):
        if pedido != self._pedido or self._actual is None:
            return
        rec, txt, origen = r
        nota = {"memoria": _tr("Guardada: no se volvió a preguntar a la IA."), "ia": _tr("Redactada por la IA."),
                "plantilla": _tr("La IA escribió cifras que no están en los datos: recomendación de la app.")
                }.get(origen, origen)
        self._mostrar(rec, txt, nota)

    def _mostrar(self, rec, txt, nota):
        self._llenar(self._actual[1], rec)
        cuerpo = html.escape(txt)
        if rec:
            cuerpo = "<b>" + html.escape(_tr("Recomendada: {id}").format(id=rec)) + "</b><br>" + cuerpo
        self.texto.setHtml(cuerpo + "<br><br><i style='font-size:small'>" + html.escape(nota) + "</i>")

    # ── acciones ──
    def _ver(self):
        if self._actual:
            c = self._actual[0]
            self.win._ir_a_elemento(c.x, c.y)

    def _aplicar(self):
        p = self._propuesta()
        if p is None or not p.valida or self._actual is None:
            return
        c, _props, ficha = self._actual
        if self.win.aplicar_propuesta(p):
            soluciones_ia.aprender(self.win._ia_memoria(), ficha, p)
            self.lbl_estado.setText(_tr("Aplicado en {c}: {p} (Ctrl+Z para deshacer).").format(c=c.id, p=p.texto))
            self.refrescar()
