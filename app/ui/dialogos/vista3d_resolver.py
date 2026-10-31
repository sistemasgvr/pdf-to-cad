"""Vista 3D → pestaña «Resolver» de un conflicto C-n (pedido del usuario 2026-10-30).

Reusa lo de «Resolver conflictos» del Asistente: las propuestas que la app calcula y PRUEBA en una copia
(`Main.soluciones_de`), las mismas tarjetas (`ia_soluciones_vista.TarjetaPropuesta`) y `Main.aplicar_propuesta`
(un paso de deshacer). Si la IA está configurada, ELLA marca la sugerida («Sugerida por la IA», con su porqué
dentro de la tarjeta); si no, la de la app. Elegir una propuesta la muestra YA en la 3D (`parche_local` con una
copia de la utilidad: el proyecto no cambia hasta «Aplicar»). ◀ ▶ (o N / Mayús+N) recorren los pendientes."""
from __future__ import annotations

import copy
import dataclasses
import html
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from ia import proveedor as P, soluciones_ia
from nucleo import informe_datos, soluciones
from traduccion.i18n import t as _tr
from ui.comun import rediseno as R
from ui.dialogos import ia_soluciones_vista as V


class _Senales(QtCore.QObject):
    listo = QtCore.Signal(object, object)


class PanelResolver(QtWidgets.QWidget):
    def __init__(self, vista):
        super().__init__()
        self.vista = vista                      # la ventana 3D
        self.win = vista.win
        self.cid = None
        self._props = []
        self._ficha = None
        self._c = None
        self._elegida = None
        self._a_mano = False
        self._rec = None
        self._origen = ""
        self._previa = None                      # índice de la utilidad que se ve con la propuesta (sin aplicar)
        self._pedido = 0
        self._tarjetas = []
        self._sen = _Senales(self)
        self._sen.listo.connect(self._al_listo)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        nav = QtWidgets.QHBoxLayout()
        self.btn_ant = R.boton_icono("chevron-left", "Conflicto anterior (Mayús+N)", lambda: self.mover(-1))
        self.btn_sig = R.boton_icono("chevron-right", "Siguiente conflicto (N)", lambda: self.mover(1))
        self.lbl_pos = QtWidgets.QLabel()
        self.lbl_pos.setProperty("rol", "t3")
        self.lbl_pos.setAlignment(QtCore.Qt.AlignCenter)
        nav.addWidget(self.btn_ant)
        nav.addWidget(self.lbl_pos, 1)
        nav.addWidget(self.btn_sig)
        v.addLayout(nav)
        self.lbl_msg = QtWidgets.QLabel()
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setProperty("rol", "t2")
        v.addWidget(self.lbl_msg)
        self.lbl_estado = QtWidgets.QLabel()            # calculando / sin solución / resuelto
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setTextFormat(QtCore.Qt.RichText)
        self.lbl_estado.linkActivated.connect(self._enlace)
        v.addWidget(self.lbl_estado)
        self._lista = QtWidgets.QVBoxLayout()
        self._lista.setSpacing(8)
        v.addLayout(self._lista)
        self.texto = QtWidgets.QLabel()                 # el porqué de la sugerida (va dentro de su tarjeta)
        self.texto.setWordWrap(True)
        self.texto.setTextFormat(QtCore.Qt.RichText)
        self.texto.hide()
        self.btn_aplicar = V.boton_aplicar(_tr("Aplicar"))
        self.btn_aplicar.setToolTip(_tr("Aplicar la propuesta elegida (Ctrl+Enter); Ctrl+Z la deshace"))
        self.btn_aplicar.clicked.connect(self.aplicar)
        v.addWidget(self.btn_aplicar)
        # «No hay codo/T/Y/cruz» (2026-10-30): el conflicto lo causa un accesorio que en realidad no va
        self.btn_sin_acc = QtWidgets.QPushButton()
        self.btn_sin_acc.setAutoDefault(False)
        self.btn_sin_acc.setToolTip(_tr("En ese punto no va accesorio: deja de marcarse y Civil 3D no lo dibuja"))
        self.btn_sin_acc.clicked.connect(self.sin_accesorio)
        self.btn_sin_acc.hide()
        self._acc = None
        v.addWidget(self.btn_sin_acc)
        v.addStretch(1)                                  # todo arriba (sin huecos entre las partes)
        for tecla in ("Ctrl+Return", "Ctrl+Enter"):
            sc = QtGui.QShortcut(QtGui.QKeySequence(tecla), self)
            sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self.aplicar)
        self._botones()

    # ── conflictos pendientes ──
    def _pendientes(self):
        return [c.id for c in getattr(self.win, "_conflictos", None) or []]

    def _nav(self):
        ids = self._pendientes()
        k = ids.index(self.cid) + 1 if self.cid in ids else 0
        self.lbl_pos.setText(_tr("{k} de {n}").format(k=k, n=len(ids)) if ids else _tr("Sin conflictos"))
        for b in (self.btn_ant, self.btn_sig):
            b.setEnabled(len(ids) > (1 if k else 0))

    def mover(self, paso):
        """Al conflicto anterior / siguiente (por número); desde uno resuelto, al más cercano en la lista."""
        ids = self._pendientes()
        if not ids:
            return
        if self.cid in ids:
            k = (ids.index(self.cid) + paso) % len(ids)
        else:
            k = 0 if paso > 0 else len(ids) - 1
        self.vista.ir_a_conflicto(ids[k])

    # ── cargar un conflicto ──
    def cargar(self, cid):
        self._quitar_previa()
        self.cid = cid
        self._pedido += 1
        self._c, self._props, self._ficha = None, [], None
        self._elegida, self._a_mano, self._rec, self._origen = None, False, None, ""
        self.texto.clear()
        self._poner_tarjetas([])
        self.lbl_msg.clear()
        self._acc = None
        self.btn_sin_acc.hide()
        self._nav()
        if not cid:
            self.lbl_estado.clear()
            return self._botones()
        self.lbl_estado.setText("<i>" + html.escape(_tr("Calculando soluciones…")) + "</i>")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            c, props = self.win.soluciones_de(cid)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if c is None:                                     # ya no está en el dibujo
            self.lbl_estado.setText(self._resuelto_html(cid))
            return self._botones()
        self._c, self._props = c, props
        self._ficha = informe_datos.ficha_conflicto(c, self.win.pipes)
        from ui.ventana.ventana_sin_accesorio import texto_no_hay
        self._acc = self.win.accesorio_de_conflicto(cid) if hasattr(self.win, "accesorio_de_conflicto") else None
        if self._acc is not None:
            self.btn_sin_acc.setText(texto_no_hay(self._acc.get("tipo")))
        self.btn_sin_acc.setVisible(self._acc is not None)
        self.lbl_msg.setText(" ".join((c.mensaje or "").split()))
        if not props:
            self.lbl_estado.setText(html.escape(_tr("Sin solución automática.")) + " <a href='editar'>"
                                    + html.escape(_tr("Ajusta las cotas en «Editar»")) + "</a>")
        else:
            self.lbl_estado.clear()
        self._llenar()
        self._recomendar()

    def _resuelto_html(self, cid):
        return ("<b>✔ " + html.escape(_tr("{c} resuelto").format(c=cid)) + "</b> · <a href='sig'>"
                + html.escape(_tr("Siguiente conflicto ▶")) + "</a>")

    def _enlace(self, href):
        if href == "sig":
            self.mover(1)
        elif href == "editar" and self._c is not None and self._c.pipes:
            self.vista.editar_utilidad(self._c.pipes[0])

    # ── propuestas ──
    def _poner_tarjetas(self, tarjetas):
        if self.texto.parent() is not None and self.texto.parent() is not self:
            self.texto.setParent(self)                    # el texto de la IA no se borra con su tarjeta
            self.texto.hide()
        for t_ in self._tarjetas:
            self._lista.removeWidget(t_)
            t_.hide()
            t_.deleteLater()
        self._tarjetas = tarjetas
        for t_ in tarjetas:
            self._lista.addWidget(t_)
            t_.elegida.connect(self._marcar)

    def _llenar(self):
        props, rec = self._props, self._rec
        if not self._a_mano or not any(p.id == self._elegida for p in props):
            self._elegida = rec if rec else next((p.id for p in props if p.valida), None)
        rotulo = _tr("Sugerida por la IA") if self._origen in ("ia", "memoria") else _tr("Recomendada")
        grupo = QtWidgets.QButtonGroup(self)
        tarjetas = []
        for p in sorted(props, key=lambda p: (p.id != rec, not p.valida)):    # la sugerida arriba
            motivo = self.texto if (p.id == rec and self.texto.text()) else None
            tarjetas.append(V.TarjetaPropuesta(p, p.id == rec, rotulo, grupo, motivo))
        self._poner_tarjetas(tarjetas)
        self._marcar(self._elegida, a_mano=False)

    def _marcar(self, pid, a_mano=True):
        self._elegida = pid
        if a_mano:
            self._a_mano = True
        for t_ in self._tarjetas:
            t_.marcar(t_.p.id == pid)
        self._mostrar_previa()
        self._botones()

    def _propuesta(self):
        return next((p for p in self._props if p.id == self._elegida), None)

    def _botones(self):
        p = self._propuesta()
        self.btn_aplicar.setEnabled(bool(p and p.valida))
        self.btn_aplicar.setVisible(bool(self._props))
        V.estilo_boton_aplicar(self.btn_aplicar)

    # ── vista previa en la 3D (copia: el proyecto no cambia) ──
    def _mostrar_previa(self):
        p = self._propuesta()
        if p is None or not (0 <= p.pipe < len(self.win.pipes)):
            return self._quitar_previa()
        if self._previa is not None and self._previa != p.pipe:
            self._quitar_previa()
        copia = [copy.deepcopy(self.win.pipes[p.pipe])]
        soluciones.aplicar(copia, dataclasses.replace(p, pipe=0))
        if self.vista.parche_local({p.pipe: copia[0]}):
            self._previa = p.pipe

    def _quitar_previa(self):
        if self._previa is not None:
            i, self._previa = self._previa, None
            if 0 <= i < len(self.win.pipes):
                self.vista.parche_local({i: None})            # la del proyecto

    def soltar(self):
        """Al cambiar de selección o de pestaña: la 3D vuelve a mostrar el proyecto."""
        self._pedido += 1
        self._quitar_previa()

    # ── sugerida (IA si está configurada; si no, la de la app) ──
    def _recomendar(self):
        if not self._props:
            return
        pedido = self._pedido
        prov = P.crear(self.win._config_ia())
        if prov is None:
            rec, txt = soluciones_ia.plantilla(self._ficha, self._props)
            return self._al_listo(pedido, (rec, txt, "plantilla-sin-ia"))
        self.texto.setText("<i>" + html.escape(_tr("La IA está eligiendo una alternativa…")) + "</i>")
        self.lbl_estado.setText(self.texto.text())
        mem = self.win._ia_memoria()
        ficha, props = self._ficha, self._props

        def correr():
            try:
                r = soluciones_ia.recomendar(prov, ficha, props, mem)
            except P.ErrorIA as e:
                rec, txt = soluciones_ia.plantilla(ficha, props)
                r = (rec, txt, _tr("La IA no respondió ({e}): recomendación de la app.").format(e=e))
            self._sen.listo.emit(pedido, r)
        threading.Thread(target=correr, name="pdfcad-ia-resolver-3d", daemon=True).start()

    def _al_listo(self, pedido, r):
        if pedido != self._pedido or not self._props:
            return
        rec, txt, origen = r
        self._rec, self._origen = rec, origen
        self.lbl_estado.clear()
        self.texto.setText(html.escape(txt or "").replace(chr(10), "<br>"))
        self._llenar()

    def sin_accesorio(self):
        """«No hay …»: en ese punto no va accesorio (un paso de deshacer)."""
        if self._acc is None or self._c is None:
            return
        self._quitar_previa()
        if self.win.marcar_sin_accesorio(self._acc, self._c):
            self._resuelto(_tr("Sin accesorio en ese punto (Ctrl+Z para deshacer)."))

    def _resuelto(self, mensaje):
        cid = self.cid
        self._props, self._c, self._acc = [], None, None
        self._poner_tarjetas([])
        self.btn_sin_acc.hide()
        self.lbl_msg.setText(mensaje)
        self.lbl_estado.setText(self._resuelto_html(cid))
        self._nav()
        self._botones()

    # ── aplicar ──
    def aplicar(self):
        p = self._propuesta()
        if p is None or not p.valida or self._c is None:
            return
        self._previa = None                                    # ahora es el proyecto (no se repone la copia)
        if self.win.aplicar_propuesta(p):
            soluciones_ia.aprender(self.win._ia_memoria(), self._ficha, p)
            self._resuelto(_tr("Aplicado: {p} (Ctrl+Z para deshacer).").format(p=p.texto))
