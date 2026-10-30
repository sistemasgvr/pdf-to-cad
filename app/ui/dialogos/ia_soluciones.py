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
from ui.dialogos import ia_soluciones_vista as V

_ROL = QtCore.Qt.UserRole


class _Senales(QtCore.QObject):
    trozo = QtCore.Signal(object, str)
    listo = QtCore.Signal(object, object)


class SolucionesDialog(QtWidgets.QDialog):
    """Rediseño 2026-10-30 (maqueta del usuario): lista «CONFLICTOS DETECTADOS» a la izquierda; a la derecha el
    conflicto con sus datos en fichas, las propuestas como tarjetas con su opción (la recomendada arriba, con su
    motivo adentro) y abajo «Ver en el plano» y «Aplicar propuesta elegida» en azul (Ctrl+Enter)."""

    def __init__(self, win):
        super().__init__(win, QtCore.Qt.Window)
        self.win = win
        self.setWindowTitle(_tr("Resolver conflictos"))
        self.resize(980, 640)
        self._actual = None                               # (conflicto, propuestas, ficha)
        self._pedido = 0                                  # la respuesta de la IA de otro conflicto se descarta
        self._rec = None
        self._elegida = None                              # id de la propuesta elegida («P3»)
        self._a_mano = False                              # la eligió el usuario (no se cambia sola)
        self._origen_rec = ""
        self._tarjetas = []
        self._senales = _Senales(self)
        self._senales.trozo.connect(self._al_trozo)
        self._senales.listo.connect(self._al_listo)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        div = QtWidgets.QSplitter()
        div.setChildrenCollapsible(False)
        div.setHandleWidth(1)
        # ── izquierda: conflictos ──
        self.izq = QtWidgets.QFrame()
        self.izq.setObjectName("listaConflictosIA")
        il = QtWidgets.QVBoxLayout(self.izq)
        il.setContentsMargins(12, 12, 12, 10)
        il.setSpacing(8)
        cab = QtWidgets.QHBoxLayout()
        self.lbl_lista = QtWidgets.QLabel(_tr("CONFLICTOS DETECTADOS"))
        self.lbl_total = QtWidgets.QLabel()
        cab.addWidget(self.lbl_lista, 1)
        cab.addWidget(self.lbl_total)
        il.addLayout(cab)
        self.chk_auto = QtWidgets.QCheckBox(_tr("Solo los que tienen solución automática"))
        self.chk_auto.toggled.connect(lambda _on: self.refrescar())
        il.addWidget(self.chk_auto)
        self.lista = QtWidgets.QListWidget()
        self.lista.setObjectName("conflictosIA")
        self.lista.setIconSize(QtCore.QSize(16, 16))
        self.lista.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.lista.setAccessibleName(_tr("Resolver conflictos"))
        self.lista.currentItemChanged.connect(lambda it, _p: self._elegir(it))
        il.addWidget(self.lista, 1)
        self.lbl_pie = QtWidgets.QLabel()
        il.addWidget(self.lbl_pie)
        # ── derecha: el conflicto elegido ──
        der = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(der)
        dl.setContentsMargins(16, 14, 16, 12)
        dl.setSpacing(8)
        tit = QtWidgets.QHBoxLayout()
        tit.setSpacing(8)
        self.lbl_id = QtWidgets.QLabel()
        self.lbl_titulo = QtWidgets.QLabel()
        self.lbl_titulo.setWordWrap(True)
        self.lbl_critico = QtWidgets.QLabel(_tr("Choque en Civil 3D"))
        tit.addWidget(self.lbl_id, 0, QtCore.Qt.AlignTop)
        tit.addWidget(self.lbl_titulo, 1)
        tit.addWidget(self.lbl_critico, 0, QtCore.Qt.AlignTop)
        dl.addLayout(tit)
        self.fichas = QtWidgets.QHBoxLayout()            # Red · Cotas
        self.fichas.setSpacing(6)
        dl.addLayout(self.fichas)
        self.fichas2 = QtWidgets.QHBoxLayout()           # Separación actual (y la que piden las propuestas)
        self.fichas2.setSpacing(6)
        dl.addLayout(self.fichas2)
        self.lbl_msg = QtWidgets.QLabel()
        self.lbl_msg.setWordWrap(True)
        dl.addWidget(self.lbl_msg)
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        dl.addWidget(sep)
        cab_p = QtWidgets.QHBoxLayout()
        cab_p.setSpacing(8)
        self.lbl_props = QtWidgets.QLabel(_tr("Propuestas calculadas por la app"))
        self.lbl_n = QtWidgets.QLabel()
        self.lbl_orden = QtWidgets.QLabel(_tr("Probadas en una copia del proyecto"))
        cab_p.addWidget(self.lbl_props)
        cab_p.addWidget(self.lbl_n)
        cab_p.addStretch(1)
        cab_p.addWidget(self.lbl_orden)
        dl.addLayout(cab_p)
        self.caja_rec = QtWidgets.QFrame()               # el texto de la IA mientras escribe (o sin recomendada)
        self.caja_rec.setObjectName("recomendacion")
        rl = QtWidgets.QVBoxLayout(self.caja_rec)
        rl.setContentsMargins(12, 8, 12, 8)
        self.texto = QtWidgets.QLabel()
        self.texto.setWordWrap(True)
        self.texto.setTextFormat(QtCore.Qt.RichText)
        self.texto.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        rl.addWidget(self.texto)
        dl.addWidget(self.caja_rec)
        self.props = QtWidgets.QScrollArea()             # las tarjetas
        self.props.setWidgetResizable(True)
        self.props.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.props.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._cont = QtWidgets.QWidget()
        self._cl = QtWidgets.QVBoxLayout(self._cont)
        self._cl.setContentsMargins(0, 0, 4, 0)
        self._cl.setSpacing(8)
        self._cl.addStretch(1)
        self.props.setWidget(self._cont)
        dl.addWidget(self.props, 1)
        self.lbl_sin_props = QtWidgets.QLabel(_tr("No hay una solución automática para este tipo de conflicto: "
                                                  "hay que cambiar el dibujo."))
        self.lbl_sin_props.setWordWrap(True)
        self.lbl_sin_props.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_sin_props.setObjectName("sinPropuestas")
        self.lbl_sin_props.setMinimumHeight(90)
        self.lbl_sin_props.hide()
        dl.addWidget(self.lbl_sin_props, 1)
        self.lbl_estado = QtWidgets.QLabel()
        self.lbl_estado.setObjectName("hint")
        self.lbl_estado.setWordWrap(True)
        dl.addWidget(self.lbl_estado)
        botones = QtWidgets.QHBoxLayout()
        self.btn_ver = QtWidgets.QPushButton(_tr("Ver en el plano"))
        self.btn_ver.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_ver.setMinimumHeight(38)
        self.btn_ver.setAutoDefault(False)              # azul solo «Aplicar» (el botón importante)
        self.btn_aplicar = V.boton_aplicar(_tr("Aplicar propuesta elegida"))
        self.btn_aplicar.setAutoDefault(False)
        self.btn_aplicar.setToolTip(_tr("Aplicar propuesta elegida") + " (Ctrl+Enter)")
        self.btn_ver.clicked.connect(self._ver)
        self.btn_aplicar.clicked.connect(self._aplicar)
        for tecla in ("Ctrl+Return", "Ctrl+Enter"):
            QtGui.QShortcut(QtGui.QKeySequence(tecla), self, activated=self._aplicar)
        botones.addWidget(self.btn_ver)
        botones.addStretch(1)
        botones.addWidget(self.btn_aplicar)
        dl.addLayout(botones)
        div.addWidget(self.izq)
        div.addWidget(der)
        div.setStretchFactor(0, 0)
        div.setStretchFactor(1, 1)
        div.setSizes([250, 730])
        lay.addWidget(div, 1)
        from ui.comun import ia_estilo as E
        E.al_cambiar_tema(self, self._estilo)
        self.refrescar()

    def _estilo(self):
        from ui.comun import icons, theme
        tk = theme.tokens()
        self.izq.setStyleSheet(f"#listaConflictosIA {{ background: {tk.surface_alt}; border: none; }}")
        self.lbl_lista.setStyleSheet(f"color: {tk.text_muted}; font-size: 11px; font-weight: 700;"
                                     f" letter-spacing: 0.6px; background: transparent;")
        self.lbl_total.setStyleSheet(f"color: {tk.text_muted}; background: {tk.surface}; border: 1px solid "
                                     f"{tk.border_soft}; border-radius: 6px; padding: 1px 6px; font-size: 11px;")
        self.lbl_pie.setStyleSheet(f"color: {tk.text_muted}; font-size: 11px; background: transparent;")
        self.lista.setStyleSheet(
            f"QListWidget#conflictosIA {{ background: transparent; border: none; outline: 0; }}"
            f" QListWidget#conflictosIA::item {{ padding: 6px 8px; border-radius: 6px; color: {tk.text}; }}"
            f" QListWidget#conflictosIA::item:hover {{ background: {tk.hover}; }}"
            f" QListWidget#conflictosIA::item:selected {{ background: {tk.accent}; color: {tk.text_on_accent};"
            f" font-weight: 600; }}")
        self.lbl_id.setStyleSheet(f"background: {tk.soft}; color: {tk.soft_text}; border-radius: 6px;"
                                  f" padding: 2px 8px; font-weight: 700; font-family: Consolas, monospace;")
        self.lbl_titulo.setStyleSheet(f"font-weight: 600; font-size: 16px; color: {tk.text};")
        self.lbl_critico.setStyleSheet(f"background: {tk.danger_soft}; color: {tk.danger}; border: 1px solid "
                                       f"{tk.danger}; border-radius: 6px; padding: 2px 8px;")
        self.lbl_msg.setStyleSheet(f"color: {tk.text_muted};")
        self.lbl_props.setStyleSheet(f"color: {tk.text}; font-weight: 600;")
        self.lbl_n.setStyleSheet(f"background: {tk.soft}; color: {tk.soft_text}; border-radius: 8px;"
                                 f" padding: 1px 8px; font-size: 11px; font-weight: 600;")
        self.lbl_orden.setStyleSheet(f"color: {tk.text_muted}; font-style: italic; font-size: 11px;")
        self.lbl_sin_props.setStyleSheet(f"#sinPropuestas {{ color: {tk.text_muted}; background: {tk.input_bg};"
                                         f" border: 1px dashed {tk.border}; border-radius: 8px; padding: 16px; }}")
        self.caja_rec.setStyleSheet(f"#recomendacion {{ background: {tk.surface_alt}; border: 1px solid "
                                    f"{tk.border_soft}; border-left: 3px solid {tk.accent}; border-radius: 8px; }}")
        self.texto.setStyleSheet(f"color: {tk.text}; background: transparent;")
        self.btn_ver.setIcon(icons.icon("mdi:eye-outline", color=tk.text))
        V.estilo_boton_aplicar(self.btn_aplicar)
        self._ico_auto = icons.icon("mdi:auto-fix", color=tk.accent if not theme.is_dark() else tk.focus)
        vacio = QtGui.QPixmap(18, 18)                         # los iconos de siempre (pedido 2026-10-30)
        vacio.fill(QtCore.Qt.transparent)
        self._ico_vacio = QtGui.QIcon(vacio)
        self._ico_ok = icons.icon("mdi:check-circle-outline", color=tk.success)
        for k in range(self.lista.count()):                  # retintar sin volver a calcular nada
            it = self.lista.item(k)
            if not it.data(_ROL + 2):
                it.setIcon(self._ico_auto if it.data(_ROL + 1) else self._ico_vacio)
        if getattr(self, "_actual", None) is not None:
            self._datos_conflicto(self._actual[0], self._actual[1])
            self._llenar(self._actual[1], self._rec)

    # ── lista de conflictos ──
    def refrescar(self, elegir=None, mover=True):
        """`mover`=False: no lleva el lienzo al conflicto elegido (tras aplicar, el usuario se perdía)."""
        self._mover = mover
        self.win._resultados_al_dia()
        solo = self.chk_auto.isChecked()
        self.lista.blockSignals(True)
        self.lista.clear()
        vigentes = list(getattr(self.win, "_conflictos", None) or [])
        for c in vigentes:
            auto = c.clave in CON_PROPUESTA or c.clave == "redes"
            if solo and not auto:
                continue
            it = QtWidgets.QListWidgetItem(self._ico_auto if auto else self._ico_vacio, f"{c.id}  {_tr(c.titulo)}")
            it.setData(_ROL, c.id)
            it.setData(_ROL + 1, auto)
            self.lista.addItem(it)
        # Los resueltos siguen en la lista con su MISMO número (2026-10-29), al final y en gris.
        resueltos = self.win.conflictos_resueltos() if hasattr(self.win, "conflictos_resueltos") else []
        for cid, titulo in resueltos:
            it = QtWidgets.QListWidgetItem(self._ico_ok, _tr("{c} · {t} (resuelto)").format(c=cid, t=_tr(titulo)))
            it.setData(_ROL, cid)
            it.setData(_ROL + 1, False)
            it.setData(_ROL + 2, True)
            it.setForeground(self.palette().brush(QtGui.QPalette.Disabled, QtGui.QPalette.Text))
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        self.lbl_total.setText(_tr("{n} totales").format(n=len(vigentes)))
        self.lbl_pie.setText(_tr("{n} resueltos").format(n=len(resueltos)) if resueltos else "")
        n = self.lista.count()
        fila = next((k for k in range(n) if self.lista.item(k).data(_ROL) == elegir), 0 if n else -1)
        if fila >= 0:
            self.lista.setCurrentRow(fila)
        else:
            self._limpiar(_tr("No hay conflictos en el dibujo."))
        self._mover = True

    def elegir(self, cid):
        self.refrescar(elegir=cid)

    def _limpiar(self, msg=""):
        self._actual = None
        self._elegida = None
        self.lbl_id.hide()
        self.lbl_critico.hide()
        self.lbl_titulo.setText(msg)
        self.lbl_msg.clear()
        self._vaciar(self.fichas)
        self._vaciar(self.fichas2)
        self._rescatar_texto()
        self._poner_tarjetas([])
        self.props.show()
        self.lbl_sin_props.hide()
        self.texto.clear()
        self.caja_rec.hide()
        self.lbl_n.hide()
        self._botones()

    def _elegir(self, it):
        if it is None:
            return self._limpiar()
        if it.data(_ROL + 2):                                # resuelto: solo su número y que está resuelto
            self._limpiar(_tr("{c} · resuelto").format(c=it.data(_ROL)))
            self.lbl_msg.setText(_tr("Este conflicto ya no está en el dibujo. Conserva su número; Ctrl+Z lo deshace."))
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            c, props = self.win.soluciones_de(it.data(_ROL))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if c is None:
            return self._limpiar()
        ficha = informe_datos.ficha_conflicto(c, self.win.pipes)
        self._actual = (c, props, ficha)
        self._elegida = None
        self._a_mano = False
        self._datos_conflicto(c, props)
        if getattr(self, "_mover", True):
            self.win._ir_a_elemento(c.x, c.y, activar=False)
        self._llenar(props, None)
        self._recomendar(c, props, ficha)

    # ── cabecera del conflicto ──
    @staticmethod
    def _vaciar(fila):
        while fila.count():
            w = fila.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _datos_conflicto(self, c, props):
        from ui.comun import theme
        tk = theme.tokens()
        self.lbl_id.setText(c.id)
        self.lbl_id.show()
        self.lbl_titulo.setText(_tr(c.titulo))
        self.lbl_critico.setVisible(c.clave in ("cruce", "choque", "redes"))
        self.lbl_msg.setText(" ".join((c.mensaje or "").split()))
        self._vaciar(self.fichas)
        self._vaciar(self.fichas2)
        codigos = [self.win._etq(self.win.pipes[i]) for i in c.pipes or [] if 0 <= i < len(self.win.pipes)]
        if len(codigos) >= 2:
            self.fichas.addWidget(V.chip(_tr("Red: {a} vs {b}").format(a=codigos[0], b=codigos[1]),
                                         tk.surface_alt, tk.text, tk.border, mono=True))
        elif codigos:
            self.fichas.addWidget(V.chip(_tr("Utilidad: {a}").format(a=codigos[0]), tk.surface_alt, tk.text,
                                         tk.border, mono=True))
        cotas = [z for z in c.cotas or [] if z is not None]
        if cotas:
            self.fichas.addWidget(V.chip(_tr("Cotas: {v}").format(v=" / ".join(f"{z:.2f} ft" for z in cotas)),
                                         tk.surface_alt, tk.text, tk.border, mono=True))
        self.fichas.addStretch(1)
        if c.diferencia is not None:
            req = max((p.separacion_ft for p in props or []), default=0.0)
            txt = _tr("Separación actual: {v} ft").format(v=f"{c.diferencia:.2f}")
            if req:
                txt += "  " + _tr("(Req: ≥ {v} ft)").format(v=f"{req:.2f}")
            self.fichas2.addWidget(V.chip(txt, tk.warning_soft, tk.text, tk.warning))
        self.fichas2.addStretch(1)

    # ── propuestas ──
    def _rescatar_texto(self):
        if self.texto.parent() is not self.caja_rec:     # el texto de la IA no se borra con su tarjeta
            self.caja_rec.layout().addWidget(self.texto)

    def _poner_tarjetas(self, tarjetas):
        for t_ in self._tarjetas:
            self._cl.removeWidget(t_)
            t_.hide()
            t_.deleteLater()
        self._tarjetas = tarjetas
        for k, t_ in enumerate(tarjetas):
            self._cl.insertWidget(k, t_)
            t_.elegida.connect(self._marcar)

    def _llenar(self, props, rec):
        self._rec = rec
        if not self._a_mano or not any(p.id == self._elegida for p in props):   # la recomendada, salvo otra elegida
            self._elegida = rec if rec else next((p.id for p in props if p.valida),
                                                 props[0].id if props else None)
        self._rescatar_texto()
        rotulo = _tr("Recomendada por la IA") if self._origen_rec == "ia" else _tr("Recomendada")
        grupo = QtWidgets.QButtonGroup(self._cont)
        orden = sorted(props, key=lambda p: (p.id != rec, not p.valida))   # la recomendada arriba
        tarjetas = []
        for p in orden:
            motivo = self.texto if (p.id == rec and self.texto.text()) else None
            tarjetas.append(V.TarjetaPropuesta(p, p.id == rec, rotulo, grupo, motivo))
        self._poner_tarjetas(tarjetas)
        self.caja_rec.setVisible(bool(self.texto.text()) and self.texto.parent() is self.caja_rec)
        for t_ in tarjetas:
            t_.marcar(t_.p.id == self._elegida)
        vacio = not props
        self.props.setVisible(not vacio)
        self.lbl_sin_props.setVisible(vacio and self._actual is not None)
        self.lbl_n.setVisible(not vacio)
        self.lbl_n.setText(_tr("{n} opciones").format(n=len(props)) if len(props) != 1 else _tr("1 opción"))
        self._botones()

    def _marcar(self, pid):
        self._elegida = pid
        self._a_mano = True
        for t_ in self._tarjetas:
            t_.marcar(t_.p.id == pid)
        self._botones()

    def _botones(self):
        p = self._propuesta()
        self.btn_aplicar.setEnabled(bool(p and p.valida))
        V.estilo_boton_aplicar(self.btn_aplicar)
        self.btn_ver.setEnabled(self._actual is not None)

    def _propuesta(self):
        if self._actual is None or self._elegida is None:
            return None
        return next((p for p in self._actual[1] if p.id == self._elegida), None)

    # ── recomendación (IA o app) ──
    def _recomendar(self, c, props, ficha):
        self._pedido += 1
        pedido = self._pedido
        prov = P.crear(self.win._config_ia())
        if prov is None:
            rec, txt = soluciones_ia.plantilla(ficha, props)
            return self._mostrar(rec, txt, _tr("Sin IA: recomendación de la app."))
        mem = self.win._ia_memoria()
        self.texto.setText("<i>" + html.escape(_tr("La IA está pensando…")) + "</i>")
        self.caja_rec.show()
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
        self.texto.setText(html.escape(self._buffer).replace(chr(10), "<br>"))
        if self.texto.parent() is self.caja_rec:
            self.caja_rec.show()

    def _al_listo(self, pedido, r):
        if pedido != self._pedido or self._actual is None:
            return
        rec, txt, origen = r
        self._origen_rec = origen
        nota = {"memoria": _tr("Guardada: no se volvió a preguntar a la IA."), "ia": _tr("Redactada por la IA."),
                "plantilla": _tr("La IA escribió cifras que no están en los datos: recomendación de la app.")
                }.get(origen, origen)
        self._mostrar(rec, txt, nota)

    def _mostrar(self, rec, txt, nota):
        cuerpo = html.escape(txt).replace(chr(10), "<br>")
        if not rec:
            cuerpo = "<b>" + html.escape(_tr("Recomendación")) + "</b><br>" + cuerpo
        self.texto.setText(cuerpo + "<br><i style='font-size:small'>" + html.escape(nota) + "</i>")
        self._llenar(self._actual[1], rec)               # el motivo va DENTRO de la tarjeta recomendada

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
            self.refrescar(elegir=c.id, mover=False)        # el mismo conflicto, ahora «resuelto»; el lienzo no se mueve
