"""«Pregúntale al proyecto» (pedido del usuario 2026-10-23): una ventana de chat sobre el proyecto abierto.

La respuesta llega MIENTRAS se escribe (hilo aparte, la ventana nunca se traba) y cada código que nombra (C-12,
N-3, AGUA-5) es una ficha que lleva al lugar en el plano. Debajo de cada respuesta, como iconos con globo: «Útil»,
«No útil», «Corregir», «Copiar» y «Volver a preguntar»; y «Enseñarle algo…» deja una regla del proyecto. Todo eso
va a la memoria del proyecto (`ia/memoria`, texto plano junto al .digproj) y entra en las preguntas siguientes. La
lógica está en `ia/consulta.py`; el HTML de la conversación en `ia_chat_html.py`.
"""
from __future__ import annotations

import html
import os
import threading
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ia import consulta, proveedor as P
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_
from ui.dialogos import ia_chat_html as H

SUGERENCIAS = (N_("¿Cuántos conflictos hay y dónde están?"),
               N_("¿Qué conflicto conviene resolver primero y por qué?"),
               N_("¿Qué utilidades no cumplen la normativa?"),
               N_("Resume lo que hay en la zona 1."))
DE_CONFLICTOS = 2                                        # las primeras sugerencias hablan de conflictos
PINTAR_MS = 60
RELOJ_MS = 500                                           # «Pensando… N s»
TAMANOS = (9, 10, 11, 12, 14, 16, 18)                    # puntos de la letra del chat
TAMANO_DEF = 11


class _Senales(QtCore.QObject):
    trozo = QtCore.Signal(object, str)
    listo = QtCore.Signal(object, object)
    fallo = QtCore.Signal(object, str)


class VistaChat(QtWidgets.QTextBrowser):
    """El QTextBrowser del chat: iconos `ico:<nombre>` retintados con el tema y globo de ayuda en cada enlace."""

    def loadResource(self, tipo, url):                   # noqa: N802
        if tipo == QtGui.QTextDocument.ImageResource and url.scheme() == "ico":
            from ui.comun import icons, theme
            tk = theme.tokens()
            nombre = url.path()
            color = {"ia": tk.accent, "aviso": H.colores_aviso(theme.is_dark())[1]}.get(nombre, tk.text_muted)
            return icons.icon(H.ICONOS.get(nombre, "mdi:help"), color=color, size=40).pixmap(40, 40)
        return super().loadResource(tipo, url)

    def event(self, ev):
        if ev.type() == QtCore.QEvent.ToolTip:
            a = self.anchorAt(self.viewport().mapFromGlobal(ev.globalPos()))
            esquema = a.split(":", 1)[0] if a else ""
            if esquema in H.TIPS:
                QtWidgets.QToolTip.showText(ev.globalPos(), _tr(H.TIPS[esquema]), self)
            else:
                QtWidgets.QToolTip.hideText()
            return True
        return super().event(ev)


class PreguntaDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win, QtCore.Qt.Window)
        self.win = win
        self.setWindowTitle(_tr("Pregúntale al proyecto"))
        self.resize(620, 780)
        self.turnos = []
        self._activo = None                              # {"cancelado": bool} de la pregunta en curso
        self._senales = _Senales(self)
        self._senales.trozo.connect(self._al_trozo)
        self._senales.listo.connect(self._al_listo)
        self._senales.fallo.connect(self._al_fallo)
        self._pintar_t = QtCore.QTimer(self, singleShot=True, interval=PINTAR_MS, timeout=self._pintar)
        self._reloj = QtCore.QTimer(self, interval=RELOJ_MS, timeout=self._pintar)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        arriba = QtWidgets.QHBoxLayout()
        arriba.setSpacing(8)
        self.lbl_estado = QtWidgets.QLabel()
        self.lbl_estado.setObjectName("hint")
        self.btn_menos = self._boton_icono("mdi:format-font-size-decrease", _tr("Letra más chica (Ctrl+-)"),
                                           lambda: self.cambiar_tamano(-1))
        self.btn_mas = self._boton_icono("mdi:format-font-size-increase", _tr("Letra más grande (Ctrl++)"),
                                         lambda: self.cambiar_tamano(1))
        self.btn_cfg = QtWidgets.QPushButton(_tr("Configurar IA…"))
        self.btn_cfg.setProperty("soft", True)
        self.btn_cfg.clicked.connect(self.win.configurar_ia)
        arriba.addWidget(self.lbl_estado, 1)
        arriba.addWidget(self.btn_menos)
        arriba.addWidget(self.btn_mas)
        arriba.addWidget(self.btn_cfg)
        lay.addLayout(arriba)

        self.aviso = QtWidgets.QLabel()                  # «IA sin configurar», ANTES de escribir
        self.aviso.setWordWrap(True)
        self.aviso.setTextFormat(QtCore.Qt.RichText)
        self.aviso.linkActivated.connect(lambda _l: self.win.configurar_ia())
        lay.addWidget(self.aviso)

        self.vista = VistaChat()
        self.vista.setOpenLinks(False)
        self.vista.anchorClicked.connect(self._enlace)
        self.vista.setAccessibleName(_tr("Conversación"))
        lay.addWidget(self.vista, 1)

        self.caja_sug = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self.caja_sug)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)
        self._botones_sug = []
        for s in SUGERENCIAS:
            b = QtWidgets.QPushButton(_tr(s))
            b.setProperty("secondary", True)
            b.clicked.connect(lambda _c=False, s=s: self.enviar(_tr(s)))
            sl.addWidget(b)
            self._botones_sug.append(b)
        lay.addWidget(self.caja_sug)

        self.entrada = QtWidgets.QPlainTextEdit()
        self.entrada.setFixedHeight(76)
        self.entrada.setAccessibleName(_tr("Tu pregunta"))
        self.entrada.installEventFilter(self)
        lay.addWidget(self.entrada)

        abajo = QtWidgets.QHBoxLayout()
        abajo.setSpacing(8)
        self.lbl_memoria = QtWidgets.QLabel()
        self.lbl_memoria.setObjectName("hint")
        self.lbl_memoria.setWordWrap(True)
        self.lbl_memoria.linkActivated.connect(lambda _l: self.win.abrir_carpeta_ia())
        self.btn_ensenar = QtWidgets.QPushButton(_tr("Enseñarle algo…"))
        self.btn_ensenar.setProperty("soft", True)
        self.btn_ensenar.setToolTip(_tr("Una regla o un dato de este proyecto que la IA debe tener en cuenta."))
        self.btn_ensenar.clicked.connect(self._ensenar)
        self.btn_enviar = QtWidgets.QPushButton(_tr("Enviar"))
        self.btn_enviar.setDefault(True)
        self.btn_enviar.clicked.connect(lambda: self.enviar())
        abajo.addWidget(self.lbl_memoria, 1)
        abajo.addWidget(self.btn_ensenar)
        abajo.addWidget(self.btn_enviar)
        lay.addLayout(abajo)
        for tecla, d in ((QtGui.QKeySequence.ZoomIn, 1), ("Ctrl+=", 1), (QtGui.QKeySequence.ZoomOut, -1)):
            QtGui.QShortcut(QtGui.QKeySequence(tecla), self, activated=lambda d=d: self.cambiar_tamano(d))
        self._tamano = self._leer_tamano()
        self._aplicar_tamano()
        self._ocupado(False)
        self.actualizar_estado()
        self._pintar()
        from ui.comun import theme
        theme.THEME_BUS.changed.connect(lambda *_a: (self._ocupado(self._activo is not None),
                                                     self.actualizar_estado(), self._pintar()))

    def _boton_icono(self, nombre, tip, fn):
        from ui.comun import icons
        b = QtWidgets.QToolButton()
        b.setIcon(icons.icon(nombre))
        b.setToolTip(tip)
        b.setAccessibleName(tip)
        b.setAutoRaise(True)
        b.clicked.connect(fn)
        b._icono = nombre
        return b

    # ── tamaño de la letra ──
    def _leer_tamano(self):
        try:
            v = int(QtCore.QSettings("pdf-to-cad", "app").value("ia/chat_letra", TAMANO_DEF))
        except (TypeError, ValueError):
            v = TAMANO_DEF
        return min(TAMANOS, key=lambda x: abs(x - v))

    def cambiar_tamano(self, paso):
        i = max(0, min(len(TAMANOS) - 1, TAMANOS.index(self._tamano) + paso))
        if TAMANOS[i] != self._tamano:
            self._tamano = TAMANOS[i]
            QtCore.QSettings("pdf-to-cad", "app").setValue("ia/chat_letra", self._tamano)
            self._aplicar_tamano()

    def _aplicar_tamano(self):
        for w in (self.vista, self.entrada):
            f = w.font()
            f.setPointSize(self._tamano)
            w.setFont(f)
            w.document().setDefaultFont(f)
        self.btn_menos.setEnabled(self._tamano > TAMANOS[0])
        self.btn_mas.setEnabled(self._tamano < TAMANOS[-1])

    # ── estado ──
    def _configurada(self):
        c = P.Config.de(self.win._config_ia())
        return c if c.con_ia and c.proveedor in P.PROVEEDORES else None

    def actualizar_estado(self):
        from ui.comun import icons, theme
        tk = theme.tokens()
        for b in (self.btn_menos, self.btn_mas):
            b.setIcon(icons.icon(b._icono))
        c = self._configurada()
        if c:
            self.lbl_estado.setText(_tr("IA: {m} · {u}").format(m=c.modelo, u=c.url))
            self.entrada.setPlaceholderText(_tr("Escribe tu pregunta… (Enter envía; Mayús+Enter, otra línea)"))
            self.aviso.hide()
        else:
            self.lbl_estado.setText(_tr("IA sin configurar"))
            self.entrada.setPlaceholderText(_tr("Primero configura la IA para poder preguntar."))
            fondo, letra = H.colores_aviso(theme.is_dark())
            self.aviso.setStyleSheet(f"QLabel {{ background:{fondo}; color:{letra}; padding:8px; "
                                     f"border-radius:4px; }}")
            self.aviso.setText(html.escape(_tr("La IA no está configurada: elige el servidor y el modelo para "
                                               "poder preguntar.")) +
                               f" <a style='color:{letra}' href='config:'><b>" +
                               html.escape(_tr("Configurar IA…")) + "</b></a>")
            self.aviso.show()
        mem = self.win._ia_memoria()
        n = len(mem.registros("ensenanzas.jsonl"))
        if mem.carpeta:
            self.lbl_memoria.setText(_tr("Aprende en <a href='#'>{c}</a> · {n} enseñanzas").format(
                c=html.escape(os.path.basename(mem.carpeta)), n=n).replace(
                "<a href=", f"<a style='color:{tk.text_info}' href="))
        else:
            self.lbl_memoria.setText(_tr("Guarda el proyecto para que lo aprendido quede en una carpeta junto a "
                                         "él ({n} enseñanzas por ahora).").format(n=n))
        hay_conflictos = bool(getattr(self.win, "_conflictos", None))
        for k, b in enumerate(self._botones_sug):
            b.setVisible(hay_conflictos or k >= DE_CONFLICTOS)

    def proyecto_cambiado(self):
        if self._activo:
            self._activo["cancelado"] = True
        self.turnos = []
        self._activo = None
        self._ocupado(False)
        self.actualizar_estado()
        self._pintar()

    def enfocar(self):
        self.entrada.setFocus()

    def eventFilter(self, obj, ev):
        if obj is self.entrada and ev.type() == QtCore.QEvent.KeyPress and \
                ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and \
                not ev.modifiers() & QtCore.Qt.ShiftModifier:
            self.enviar()
            return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):                         # noqa: N802
        if ev.key() == QtCore.Qt.Key_Escape and self._activo is not None:
            self._activo["cancelado"] = True             # Esc = Detener (no cierra la ventana)
            return
        super().keyPressEvent(ev)

    def _ocupado(self, si):
        from ui.comun import icons, theme
        self.btn_enviar.setText(_tr("Detener") if si else _tr("Enviar"))
        self.btn_enviar.setToolTip(_tr("Detener la respuesta (Esc)") if si else _tr("Enviar la pregunta (Enter)"))
        self.btn_enviar.setProperty("danger", bool(si))
        self.btn_enviar.setIcon(icons.icon("mdi:stop-circle-outline" if si else "mdi:send",
                                           color=theme.tokens().text_on_accent))
        self.btn_enviar.style().unpolish(self.btn_enviar)
        self.btn_enviar.style().polish(self.btn_enviar)
        if si:
            self._reloj.start()
        else:
            self._reloj.stop()

    # ── preguntar ──
    def enviar(self, texto=None):
        if self._activo is not None:                     # «Detener»
            self._activo["cancelado"] = True
            return
        q = (texto if texto is not None else self.entrada.toPlainText()).strip()
        if not q:
            return
        self.entrada.clear()
        turno = {"pregunta": q, "texto": "", "estado": "escribiendo", "res": None, "error": "", "valor": 0,
                 "corregido": "", "hora": time.strftime("%H:%M"), "t0": time.time(), "siguientes": []}
        self.turnos.append(turno)
        prov = P.crear(self.win._config_ia())
        if prov is None:
            turno["estado"] = "error"
            turno["error"] = _tr("La IA no está configurada.") + " <a href='config:'>" + _tr("Configurar IA…") + "</a>"
            self._pintar()
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            datos = self.win._ia_datos()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        mem = self.win._ia_memoria()
        historial = [(x["pregunta"], x["texto"]) for x in self.turnos[:-1]
                     if "nota" not in x and x["estado"] == "listo"]
        estado = {"cancelado": False}
        self._activo = estado
        self._ocupado(True)
        self._pintar(abajo=True)

        def correr():
            try:
                res = consulta.preguntar(prov, q, datos, mem, historial,
                                         al_texto=lambda s: self._senales.trozo.emit(turno, s),
                                         cancelado=lambda: estado["cancelado"])
                self._senales.listo.emit(turno, res)
            except P.ErrorIA as e:
                self._senales.fallo.emit(turno, str(e))
            except Exception as e:                       # noqa: BLE001 (se muestra en el chat)
                self._senales.fallo.emit(turno, f"{type(e).__name__}: {e}")

        threading.Thread(target=correr, name="pdfcad-ia-chat", daemon=True).start()

    def _al_trozo(self, turno, s):
        turno["texto"] += s
        if not self._pintar_t.isActive():
            self._pintar_t.start()

    def _al_listo(self, turno, res):
        turno["res"], turno["texto"], turno["estado"] = res, res.texto, "listo"
        turno["siguientes"] = H.siguientes(res)
        self._terminar()

    def _al_fallo(self, turno, msg):
        turno["estado"], turno["error"] = "error", html.escape(msg)
        self._terminar()

    def _terminar(self):
        self._activo = None
        self._ocupado(False)
        self.actualizar_estado()
        self._pintar()

    # ── enlaces ──
    def _turno(self, valor):
        tu = self.turnos[int(valor)] if valor.isdigit() and int(valor) < len(self.turnos) else None
        return tu if tu is not None and "nota" not in tu else None

    def _enlace(self, url):
        tipo, valor = url.scheme(), url.path()
        if tipo == "ref":
            self.win._ia_ir_a(valor)
        elif tipo == "config":
            self.win.configurar_ia()
        elif tipo == "preg":
            ultimo = next((x for x in reversed(self.turnos) if "nota" not in x), None)
            if ultimo and valor.isdigit() and int(valor) < len(ultimo.get("siguientes", [])):
                self.enviar(ultimo["siguientes"][int(valor)])
        elif tipo == "repetir":
            turno = self._turno(valor)
            if turno is not None:
                self.enviar(turno["pregunta"])
        elif tipo == "copiar":
            turno = self._turno(valor)
            if turno is not None and turno["texto"]:
                QtWidgets.QApplication.clipboard().setText(turno["texto"])
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), _tr("Copiada"), self.vista)
        elif tipo in ("util", "noutil", "corr"):
            turno = self._turno(valor)
            if turno is None or turno["res"] is None:
                return
            mem = self.win._ia_memoria()
            if tipo == "corr":
                txt, ok = QtWidgets.QInputDialog.getMultiLineText(
                    self, _tr("Corregir la respuesta"), _tr("¿Cuál es la respuesta correcta? La IA la usará en "
                                                            "las próximas preguntas de este proyecto."))
                if not ok or not txt.strip():
                    return
                consulta.corregir(mem, turno["res"], txt.strip())
                turno["corregido"] = txt.strip()
            else:
                consulta.valorar(mem, turno["res"], tipo == "util")
                turno["valor"] = 1 if tipo == "util" else -1
            self.actualizar_estado()
            self._pintar()

    def _ensenar(self):
        txt, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, _tr("Enseñarle algo a la IA"), _tr("Una regla o un dato de este proyecto que la IA debe tener en "
                                                     "cuenta (por ejemplo: «los cruces con drenaje se resuelven "
                                                     "bajando el agua»)."))
        if ok and txt.strip():
            consulta.ensenar_nota(self.win._ia_memoria(), txt.strip())
            self.turnos.append({"nota": txt.strip()})
            self.actualizar_estado()
            self._pintar(abajo=True)

    # ── dibujar la conversación ──
    def _pintar(self, abajo=False):
        from ui.comun import theme
        datos = getattr(self.win, "_ia_cache_datos", None)
        existe = (lambda c: datos[1].ref(c) is not None) if datos else (lambda _c: False)
        barra = self.vista.verticalScrollBar()
        al_final = abajo or barra.value() >= barra.maximum() - 24   # si el usuario subió a leer, no lo bajamos
        pos = barra.value()
        self.vista.setHtml(H.conversacion(self.turnos, theme.tokens(), existe, time.time()))
        barra.setValue(barra.maximum() if al_final else pos)
        self.caja_sug.setVisible(not self.turnos)
