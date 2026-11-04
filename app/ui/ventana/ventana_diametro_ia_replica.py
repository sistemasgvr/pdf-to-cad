"""La tarjeta «Diámetro según la IA» como CHAT (pedidos del usuario 2026-11-03).

1.ª vuelta: «Responder a la IA» — si la IA no encuentra el diámetro con certeza o propone uno que el usuario cree que
no es, el usuario le escribe y la IA vuelve a decidir con ese dato (`ia.diametro_ia_replica`). 2.ª vuelta («que se
trate como un chat más, no como un va y ven de preguntas»): la IA habla en primera persona y de tú; cada turno es una
burbuja (la IA a la izquierda, tú a la derecha), el mensaje actual de la IA es la última burbuja (`lbl_diam_ia`), el
tuyo aparece al instante mientras la IA piensa, hay respuestas rápidas («¿Por qué?», «Revisa las líneas vecinas») y
el campo de escribir con su botón de enviar. Mismo flujo en el PDF con capas y en el mapa sin capas.

La conversación es por línea (clave de su ficha); la propuesta nueva queda como siempre, para «Aprobar» (con deshacer).
Al aprobar tras conversar, la aclaración queda como enseñanza para casos parecidos (`usar_diametro_ia`).

Mezcla de `DiametroIAMixin`: usa `_diam_ia_*` de esa clase.
"""
import html
import json
import threading
import time

import shiboken6

from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R
from ui.comun.texto_ajustado import TextoAjustado

RAPIDAS = ("¿Por qué?", "Revisa las líneas vecinas")     # «no es ese» = «Otro diámetro…» o escribirlo


class ReplicaDiametroMixin:
    # ── burbujas ──
    def _diam_ia_burbuja(self, etiqueta, ia: bool):
        """Una burbuja del chat con `etiqueta` dentro: la de la IA a la izquierda, la tuya a la derecha."""
        caja = R.transparente(QtWidgets.QWidget())
        fila = QtWidgets.QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        marco = QtWidgets.QFrame()
        marco.setObjectName("burbujaIA" if ia else "burbujaTu")
        ml = QtWidgets.QVBoxLayout(marco)
        ml.setContentsMargins(10, 8, 10, 8)
        ml.addWidget(etiqueta)
        self._diam_ia_estilo_burbuja(marco, etiqueta, ia)
        if ia:
            fila.addWidget(marco, 6)
            fila.addStretch(1)
        else:
            fila.addStretch(1)
            fila.addWidget(marco, 5)
        return caja

    def _diam_ia_estilo_burbuja(self, marco, etiqueta, ia):
        t = _theme.tokens()
        # la de la IA, con borde: sobre la tarjeta suave `surface_alt` no se distinguía
        fondo, texto, borde = (t.surface, t.text, t.border) if ia else (t.soft, t.soft_text, t.soft)
        esquinas = ("border-top-left-radius:4px;" if ia else "border-top-right-radius:4px;")
        marco.setStyleSheet(f"QFrame#{marco.objectName()} {{ background:{fondo}; border:1px solid {borde}; "
                            f"border-radius:12px; {esquinas} }}"
                            f"QFrame#{marco.objectName()} QLabel {{ background:transparent; color:{texto}; }}")

    def _diam_ia_texto_burbuja(self, texto_html):
        lbl = TextoAjustado()
        lbl.setWordWrap(True)
        lbl.setTextFormat(QtCore.Qt.RichText)
        lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse)
        lbl.linkActivated.connect(self._diam_ia_ir)
        lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        lbl.setText(texto_html)
        return lbl

    # ── entrada ──
    def _diam_ia_replica_construir(self, lay):
        """Respuestas rápidas + campo de escribir con «Enviar», al pie de la tarjeta."""
        self._diam_ia_conv = {}
        self._diam_ia_replica_pendiente = None
        self._diam_ia_fila_resp = R.transparente(QtWidgets.QWidget())
        col = QtWidgets.QVBoxLayout(self._diam_ia_fila_resp)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(6)
        # respuestas rápidas: fichas chicas, en una fila si caben (`GridAdaptable`: en un panel angosto, dos filas;
        # una fila fija imponía su ancho al inspector)
        self._diam_ia_rapidas = R.transparente(QtWidgets.QWidget())
        rap = GridAdaptable(self._diam_ia_rapidas, max_cols=len(RAPIDAS), spacing=4)
        self._diam_ia_btn_rapidas = []
        for texto in RAPIDAS:
            b = QtWidgets.QPushButton()
            _bind(b, "setText", texto)
            b.setProperty("kind", "chip")
            b.clicked.connect(lambda _c=False, texto=texto: self.responder_diametro_ia(mensaje=_tr(texto)))
            rap.addWidget(b)
            self._diam_ia_btn_rapidas.append(b)
        col.addWidget(self._diam_ia_rapidas)
        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(6)
        self.ed_diam_ia_resp = QtWidgets.QLineEdit()
        self.ed_diam_ia_resp.setMinimumHeight(34)
        self.ed_diam_ia_resp.setPlaceholderText(_tr("Escríbeme o pregúntame…"))
        self.ed_diam_ia_resp.setToolTip(_tr(
            "Dime qué rótulo es el suyo, su función (principal, lateral, acometida), dónde está el dato o el "
            "diámetro, pídeme que mire una zona («revisa el membrete», «mira arriba») o pregúntame por qué propuse "
            "algo. Nada se aplica sin «Aprobar»."))
        self.ed_diam_ia_resp.returnPressed.connect(self.responder_diametro_ia)
        fila.addWidget(self.ed_diam_ia_resp, 1)
        self.btn_diam_ia_enviar = QtWidgets.QPushButton()
        self.btn_diam_ia_enviar.setIcon(_icon("mdi:send", color=_theme.tokens().text_on_accent))
        self.btn_diam_ia_enviar.setProperty("kind", "primary")
        self.btn_diam_ia_enviar.setMinimumHeight(34)
        self.btn_diam_ia_enviar.setToolTip(_tr("Enviar"))
        self.btn_diam_ia_enviar.setAccessibleName(_tr("Enviar"))
        self.btn_diam_ia_enviar.clicked.connect(lambda _c=False: self.responder_diametro_ia())
        fila.addWidget(self.btn_diam_ia_enviar)
        col.addLayout(fila)
        self._diam_ia_fila_resp.hide()
        lay.addWidget(self._diam_ia_fila_resp)
        _theme.THEME_BUS.changed.connect(lambda _n: self._diam_ia_restilo())

    def _diam_ia_restilo(self):
        """Otro tema: las burbujas con los colores nuevos."""
        tarjeta = getattr(self, "tarjeta_diam_ia", None)
        if tarjeta is None or not shiboken6.isValid(tarjeta):
            return
        for marco in tarjeta.findChildren(QtWidgets.QFrame):
            if marco.objectName() in ("burbujaIA", "burbujaTu"):
                self._diam_ia_estilo_burbuja(marco, None, marco.objectName() == "burbujaIA")
        self.btn_diam_ia_enviar.setIcon(_icon("mdi:send", color=_theme.tokens().text_on_accent))

    def _diam_ia_clave_si_hay(self, i):
        """La clave de la ficha de i SOLO si ya está armada (armarla cuesta: el panel no espera por el chat)."""
        if i is None or not (0 <= i < len(self.pipes)):
            return None
        f = self._diam_ia_fichas.get(self._diam_ia_clave_ficha(i))
        return None if f is None else self._diam_ia_clave(f)

    def _diam_ia_conv_de(self, i):
        if not hasattr(self, "_diam_ia_conv"):
            return []
        clave = self._diam_ia_clave_si_hay(i)
        return self._diam_ia_conv.get(clave, []) if clave else []

    def _diam_ia_pintar_hilo(self, i):
        """Los turnos anteriores (la IA y tú) como burbujas, encima del mensaje actual de la IA."""
        hilo = getattr(self, "_diam_ia_hilo", None)
        if hilo is None:
            return
        lay = hilo.layout()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None:
                w.hide()                               # sin bucle de eventos, deleteLater solo no basta
                w.deleteLater()
        turnos = list(self._diam_ia_conv_de(i)) if i is not None else []
        pend = getattr(self, "_diam_ia_replica_pendiente", None)
        if pend is not None and pend[0] == self._diam_ia_clave_si_hay(i):
            turnos.append({"ia": pend[2], "usuario": pend[1]})      # tu mensaje ya, mientras la IA piensa
        for h in turnos[-6:]:
            if h.get("ia"):
                lay.addWidget(self._diam_ia_burbuja(self._diam_ia_texto_burbuja(h["ia"]), ia=True))
            lay.addWidget(self._diam_ia_burbuja(self._diam_ia_texto_burbuja(html.escape(h.get("usuario", ""))),
                                                ia=False))
        hilo.setVisible(bool(turnos))

    def _diam_ia_replica_mostrar(self, i, con_resultado):
        """Hilo de la conversación siempre; la entrada solo con un resultado a la vista (no mientras piensa)."""
        if not hasattr(self, "_diam_ia_fila_resp"):
            return
        self._diam_ia_pintar_hilo(i)
        self._diam_ia_fila_resp.setVisible(bool(con_resultado))

    # ── enviar ──
    def responder_diametro_ia(self, i=None, mensaje=None):
        """Envía tu mensaje: la IA vuelve a revisar esta línea con ese dato, o te contesta (en un hilo)."""
        i = self._diam_ia_actual() if i is None else i
        prov = self._diam_ia_proveedor()
        mensaje = (self.ed_diam_ia_resp.text() if mensaje is None else mensaje).strip()
        if i is None or prov is None or not mensaje or getattr(self, "_diam_ia_pedido", None) is not None:
            return
        from ia import diametro_ia_replica as DR
        f = self._diam_ia_ficha(i)
        clave = self._diam_ia_clave(f)
        anterior = self._diam_ia_sug(i)
        historial = list(self._diam_ia_conv.get(clave, []))
        ev = self._diam_ia_evidencias.get(clave) or {}
        imagen = ev.get("imagen") if ev else self._diam_ia_imagen(i, f)
        capturas = ev.get("capturas") or ()
        mem = self._ia_memoria()
        self.ed_diam_ia_resp.clear()
        self._diam_ia_tok += 1
        tok = self._diam_ia_tok
        self._diam_ia_pedido = (tok, i, clave)
        # (clave, tu mensaje, lo que la IA te había dicho: queda como burbuja de arriba)
        self._diam_ia_replica_pendiente = (clave, mensaje, self.lbl_diam_ia.text())
        self._diam_ia_etapa = _tr("Revisando con tu respuesta")
        self._diam_ia_t0 = time.monotonic()
        self._diam_ia_reloj.start()
        self._diam_ia_refrescar()

        def correr():
            try:
                r = DR.replicar(prov, f, anterior, historial, mensaje, imagen=imagen, capturas=capturas, memoria=mem,
                                cancelado=lambda: self._diam_ia_tok != tok,
                                al_estado=lambda etapa: self._diam_ia_senales.etapa.emit(tok, etapa),
                                explorador=self._diam_ia_explorador(i, f, tok, prov))
            except Exception as e:                    # noqa: BLE001 (ErrorIA, red)
                r = str(e)
            self._diam_ia_senales.listo.emit(tok, r)
        threading.Thread(target=correr, name="pdfcad-ia-diametro-replica", daemon=True).start()

    def _diam_ia_replica_lista(self, clave, r):
        """Llegó la respuesta: se anota el turno y la nueva propuesta queda (también en la caché de la IA)."""
        pend = getattr(self, "_diam_ia_replica_pendiente", None)
        self._diam_ia_replica_pendiente = None
        if pend is None or pend[0] != clave:
            return
        from ia import diametro_ia as DI, diametro_ia_replica as DR
        respuesta = DR.respuesta_txt(r) if not isinstance(r, str) else r
        self._diam_ia_conv.setdefault(clave, []).append({"ia": pend[2], "usuario": pend[1], "respuesta": respuesta})
        prov = self._diam_ia_proveedor()
        if isinstance(r, str):
            return
        f = json.loads(clave)
        if prov is not None and r.origen != "descartada":
            self._ia_memoria().guardar_redaccion(DI.clave_de(f, prov.config.modelo),
                                                 json.dumps(r.a_dict(), ensure_ascii=False), prov.config.modelo)
