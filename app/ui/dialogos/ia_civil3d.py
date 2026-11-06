"""Pestaña «Civil 3D» del Asistente (2026-11-03): chat con la IA local sobre el DWG abierto en Civil 3D (MCP).

Mismo aspecto que «Pregúntale al proyecto» incrustado (`ia_chat.PreguntaDialog.incrustado`): una línea de estado
arriba, la conversación sin marco, sugerencias como chips y la caja de escribir redondeada con «Enviar» circular.
Aquí el estado es DOBLE: la IA (Configurar IA…) y Civil 3D (conexión encendida con PDFCAD_IA, dibujo y redes).

La lógica es `ia/civil3d_agente` + `ia/civil3d_mcp` (puros); todo lo lento (arrancar el host, preguntar, aplicar)
va en un hilo y vuelve por señales. Las propuestas de cambio se muestran como tarjetas (`ia_civil3d_html`) y SOLO
el usuario las aplica con su botón.
"""
from __future__ import annotations

import html
import json
import threading
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ia import proveedor as P
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_
from ui.dialogos import ia_chat_html as HC
from ui.dialogos import ia_civil3d_html as H
from ui.dialogos.ia_chat import VistaChat

SUGERENCIAS = (N_("¿Qué redes hay y cuánto miden?"),
               N_("¿Hay tuberías en contrapendiente?"),
               N_("¿Cuáles son los buzones más profundos?"))
PINTAR_MS = 60
RELOJ_MS = 500


class _Senales(QtCore.QObject):
    estado = QtCore.Signal(object)            # dict de «estado» del plugin, o str con el error
    paso = QtCore.Signal(object, str)
    listo = QtCore.Signal(object, object)
    fallo = QtCore.Signal(object, object)    # turno, ia.reporte_error.Reporte
    aplicado = QtCore.Signal(object, bool, str)


class _Vista(VistaChat):
    """La vista del chat con los globos de ESTE chat (aplicar, descartar, ver en Civil 3D…)."""

    def event(self, ev):
        if ev.type() == QtCore.QEvent.ToolTip:
            a = self.anchorAt(self.viewport().mapFromGlobal(ev.globalPos()))
            esquema = a.split(":", 1)[0] if a else ""
            if esquema in H.TIPS:
                QtWidgets.QToolTip.showText(ev.globalPos(), _tr(H.TIPS[esquema]), self)
            else:
                QtWidgets.QToolTip.hideText()
            return True
        return QtWidgets.QTextBrowser.event(self, ev)


class ChatCivil3D(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.turnos = []
        self._activo = None                              # {"cancelado": bool}
        self._cliente = None                             # ia.civil3d_mcp.ClienteMCP (vivo mientras dure)
        self._agente = None
        self._civil = None                               # último «estado» del plugin (dict) o None
        self._cerrojo = threading.Lock()
        self._sen = _Senales(self)
        self._sen.estado.connect(self._al_estado)
        self._sen.paso.connect(self._al_paso)
        self._sen.listo.connect(self._al_listo)
        self._sen.fallo.connect(self._al_fallo)
        self._sen.aplicado.connect(self._al_aplicado)
        self._pintar_t = QtCore.QTimer(self, singleShot=True, interval=PINTAR_MS, timeout=self._pintar)
        self._reloj = QtCore.QTimer(self, interval=RELOJ_MS, timeout=self._pintar)

        from ui.comun import rediseno as R
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 4, 14, 12)
        lay.setSpacing(8)
        fila = QtWidgets.QHBoxLayout()                   # estado: punto de color + «Civil 3D: plano.dwg · 3 redes»
        fila.setSpacing(6)
        self.punto = QtWidgets.QLabel()
        self.punto.setFixedSize(10, 10)
        self.lbl_estado = R.texto("", "t3", traducir=False)
        self.lbl_estado.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.btn_reconectar = R.boton_icono("refresh", "Volver a buscar Civil 3D", self.reconectar)
        fila.addWidget(self.punto, 0, QtCore.Qt.AlignVCenter)
        fila.addWidget(self.lbl_estado, 1)
        fila.addWidget(self.btn_reconectar)
        lay.addLayout(fila)

        self.aviso = QtWidgets.QLabel()                  # lo que falta para preguntar (IA o Civil 3D)
        self.aviso.setWordWrap(True)
        self.aviso.setTextFormat(QtCore.Qt.RichText)
        self.aviso.linkActivated.connect(self._enlace_aviso)
        lay.addWidget(self.aviso)

        self.vista = _Vista()
        self.vista.setOpenLinks(False)
        self.vista.anchorClicked.connect(self._enlace)
        self.vista.setAccessibleName(_tr("Conversación con el dibujo de Civil 3D"))
        lay.addWidget(self.vista, 1)

        self.caja_sug = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self.caja_sug)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        self._botones_sug = []
        for s in SUGERENCIAS:
            b = QtWidgets.QPushButton(_tr(s))
            b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            b.clicked.connect(lambda _c=False, s=s: self.enviar(_tr(s)))
            sl.addWidget(b)
            self._botones_sug.append(b)
        lay.addWidget(self.caja_sug)

        self._caja = QtWidgets.QFrame()                  # caja de escribir (como el chat incrustado)
        self._caja.setObjectName("composer")
        cv = QtWidgets.QVBoxLayout(self._caja)
        cv.setContentsMargins(4, 4, 6, 6)
        cv.setSpacing(2)
        self.entrada = QtWidgets.QPlainTextEdit()
        self.entrada.setFixedHeight(64)
        self.entrada.setAccessibleName(_tr("Tu pregunta sobre el dibujo"))
        self.entrada.installEventFilter(self)
        cv.addWidget(self.entrada)
        abajo = QtWidgets.QHBoxLayout()
        abajo.setSpacing(6)
        abajo.addWidget(R.texto("Enter envía · Mayús+Enter nueva línea", "t3"), 1)
        self.btn_enviar = QtWidgets.QPushButton()
        self.btn_enviar.setProperty("kind", "primary")
        self.btn_enviar.setFixedSize(34, 34)
        self.btn_enviar.clicked.connect(lambda: self.enviar())
        abajo.addWidget(self.btn_enviar)
        cv.addLayout(abajo)
        lay.addWidget(self._caja)

        from ui.comun import ia_estilo as E
        self._ocupado(False)
        E.al_cambiar_tema(self, self._estilo)
        self.actualizar_estado()
        self._pintar()

    # ── aspecto ──
    def _estilo(self):
        from ui.comun import ia_estilo as E, icons, theme
        tk = theme.tokens()
        self.vista.setStyleSheet("QTextBrowser { background: transparent; border: none; padding: 0; }")
        self._caja.setStyleSheet(f"QFrame#composer {{ background: {tk.input_bg}; border: 1px solid {tk.border};"
                                 f" border-radius: 12px; }}")
        self.entrada.setStyleSheet("QPlainTextEdit { background: transparent; border: none; padding: 4px 6px; }")
        self.btn_enviar.setStyleSheet("QPushButton { border-radius: 17px; padding: 0; }")
        for b in self._botones_sug:
            b.setStyleSheet(E.chip_qss(tk))
            b.setIcon(icons.icon("mdi:chat-question-outline", color=tk.text_muted))
        self._ocupado(self._activo is not None)
        self.actualizar_estado()
        self._pintar()

    def _ocupado(self, si):
        from ui.comun import icons, theme
        tk = theme.tokens()
        self.btn_enviar.setToolTip(_tr("Detener la respuesta (Esc)") if si else _tr("Enviar la pregunta (Enter)"))
        self.btn_enviar.setAccessibleName(self.btn_enviar.toolTip())
        self.btn_enviar.setProperty("danger", bool(si))
        self.btn_enviar.setIcon(icons.icon("mdi:stop-circle-outline" if si else "mdi:send",
                                           color=tk.danger if si else tk.text_on_accent))
        self.btn_enviar.style().unpolish(self.btn_enviar)
        self.btn_enviar.style().polish(self.btn_enviar)
        (self._reloj.start if si else self._reloj.stop)()

    # ── estado de la IA y de Civil 3D ──
    def _config(self):
        c = P.Config.de(self.win._config_ia())
        return c if c.con_ia and c.proveedor == P.OLLAMA else None

    def actualizar_estado(self):
        from ui.comun import theme
        tk = theme.tokens()
        fondo, letra = HC.colores_aviso(theme.is_dark())
        conectado = isinstance(self._civil, dict)
        color = tk.success if conectado else tk.warning
        self.punto.setStyleSheet(f"QLabel {{ background: {color}; border-radius: 5px; }}")
        if conectado:
            e = self._civil
            redes = int(e.get("redes_gravedad") or 0) + int(e.get("redes_presion") or 0)
            texto = _tr("Civil 3D: {d} · {n} redes").format(d=e.get("dibujo") or "?", n=redes)
            if e.get("ocupado"):
                texto += " · " + _tr("ocupado con {c}").format(c=e.get("comando") or "")
        else:
            texto = _tr("Civil 3D sin conectar")
        c = self._config()
        texto += " · " + (_tr("IA: {m}").format(m=c.modelo) if c else _tr("IA sin configurar"))
        self.lbl_estado.setText(texto)
        self.punto.setAccessibleName(texto)
        falta = ""
        if c is None:
            falta = (html.escape(_tr("La IA local (Ollama) no está configurada.")) +
                     f" <a style='color:{letra}' href='config:'><b>" + html.escape(_tr("Configurar IA…")) + "</b></a>")
        elif not conectado:
            motivo = self._civil if isinstance(self._civil, str) and self._civil else _tr(
                "En Civil 3D: PANEL_REDES → «Encender conexión de la IA» (o el comando PDFCAD_IA).")
            falta = (html.escape(motivo) + f" <a style='color:{letra}' href='reconectar:'><b>" +
                     html.escape(_tr("Reintentar")) + "</b></a>")
        self.aviso.setVisible(bool(falta))
        self.aviso.setText(falta)
        self.aviso.setStyleSheet(f"QLabel {{ background:{fondo}; color:{letra}; padding:8px; border-radius:8px; }}")
        listo = c is not None and conectado
        self.entrada.setPlaceholderText(_tr("Pregunta sobre el dibujo… (Enter envía)") if listo
                                        else _tr("Conecta la IA y Civil 3D para preguntar."))

    def reconectar(self):
        """Vuelve a lanzar el host MCP y pide «estado» (en un hilo)."""
        def correr():
            try:
                self._cliente_vivo(nuevo=True)
                ok, txt = self._cliente.llamar("estado")
                self._sen.estado.emit(json.loads(txt) if ok else txt)
            except Exception as e:                       # noqa: BLE001 (se muestra en el aviso)
                self._sen.estado.emit(str(e))
        threading.Thread(target=correr, name="pdfcad-civil3d-estado", daemon=True).start()

    def showEvent(self, ev):                             # noqa: N802
        super().showEvent(ev)
        if self._civil is None and self._activo is None:
            self.reconectar()

    def _al_estado(self, e):
        self._civil = e if isinstance(e, dict) else (e or "")
        self.actualizar_estado()

    def _cliente_vivo(self, nuevo=False):
        from ia import civil3d_mcp as M
        with self._cerrojo:
            if nuevo and self._cliente is not None:
                self._cliente.cerrar()
                self._cliente = self._agente = None
            if self._cliente is None:
                self._cliente = M.ClienteMCP(perfil=M.PERFIL_BASICO, origen="qwen")
            return self._cliente

    def cerrar(self):
        if self._cliente is not None:
            self._cliente.cerrar()
            self._cliente = self._agente = None

    # ── teclado ──
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
            self._activo["cancelado"] = True
            return
        super().keyPressEvent(ev)

    # ── preguntar ──
    def enviar(self, texto=None):
        if self._activo is not None:
            self._activo["cancelado"] = True
            return
        q = (texto if texto is not None else self.entrada.toPlainText()).strip()
        if not q:
            return
        self.entrada.clear()
        turno = {"pregunta": q, "texto": "", "estado": "escribiendo", "error": "", "pasos": [], "propuestas": [],
                 "hora": time.strftime("%H:%M"), "t0": time.time(), "segundos": None, "modelo": ""}
        self.turnos.append(turno)
        cfg = self._config()
        if cfg is None:
            turno["estado"] = "error"
            turno["error"] = (html.escape(_tr("La IA local (Ollama) no está configurada.")) +
                              " <a href='config:'>" + html.escape(_tr("Configurar IA…")) + "</a>")
            return self._pintar(abajo=True)
        estado = {"cancelado": False}
        self._activo = estado
        self._ocupado(True)
        self._pintar(abajo=True)

        def correr():
            from ia import civil3d_agente as A
            try:
                cli = self._cliente_vivo()
                if self._agente is None:
                    self._agente = A.Agente(cli, A.pedir_ollama(cfg), reglas=self._reglas, normas_cat=self._normas_cat,
                                           proyecto=self._proyecto)
                res = self._agente.preguntar(q, cancelado=lambda: estado["cancelado"],
                                             al_paso=lambda n: self._sen.paso.emit(turno, n))
                self._sen.listo.emit(turno, res)
            except Exception as e:                       # noqa: BLE001 (ErrorIA, MCP o lo que sea: reporte en el chat)
                from ia import reporte_error as RE
                self._sen.fallo.emit(turno, RE.armar(e, "Chat Civil 3D", modelo=cfg.modelo, servidor=cfg.url,
                                                     pregunta=q, pasos=list(turno["pasos"])))

        threading.Thread(target=correr, name="pdfcad-civil3d-chat", daemon=True).start()

    def _proyecto(self):
        """(pipes, pies por px) del proyecto abierto en la app, para comparar con el dibujo; None sin proyecto."""
        w = self.win
        pipes = getattr(w, "pipes", None)
        if not pipes or not getattr(w, "scale", None) or not getattr(w, "zoom", None):
            return None
        ft = w.scale / w.zoom
        try:                                     # px de la hoja ↔ dibujo: la MISMA transformación que el DXF, invertida
            from geo import georef as georef_mod
            muestras = [(0.0, 0.0), (1000.0, 0.0), (0.0, 1000.0)]
            M, _, _ = georef_mod.fit([w._to_cad(x, y) for x, y in muestras], muestras, "affine")
            a_px = lambda x, y: (M[0][0] * x + M[0][1] * y + M[0][2], M[1][0] * x + M[1][1] * y + M[1][2])  # noqa: E731
            a_mundo = w._to_cad
        except Exception:                        # noqa: BLE001
            a_px = a_mundo = None
        gray, esc = getattr(w, "gray", None), getattr(getattr(w, "canvas", None), "fondo_escala", 1.0) or 1.0

        def tinta(x, y, r):
            """¿Hay tinta del PDF a ≤ r px de (x, y)? (la imagen en grises del imán, como `geometry.snap_point`)."""
            h, wd = gray.shape[:2]
            xi, yi, rr = int(x * esc), int(y * esc), max(1, int(round(r * esc)))
            ven = gray[max(0, yi - rr):min(h, yi + rr + 1), max(0, xi - rr):min(wd, xi + rr + 1)]
            return bool(ven.size) and bool((ven < 128).any())
        return {"pipes": pipes, "ft": ft, "a_px": a_px, "a_mundo": a_mundo,
                "tinta": tinta if gray is not None and a_px is not None else None}

    def _normas_cat(self):
        """Catálogo de normativas del proyecto abierto en la app (pendientes, diámetros, materiales, revisión)."""
        return getattr(self.win, "normas_cat", None)

    def _reglas(self):
        """Separaciones de las normativas del proyecto abierto en la app (para buscar y resolver conflictos)."""
        from ia.civil3d_reglas import reglas_separacion
        return reglas_separacion(getattr(self.win, "normas_cat", None))

    def _al_paso(self, turno, nombre):
        turno["pasos"].append(nombre)
        if not self._pintar_t.isActive():
            self._pintar_t.start()

    def _al_listo(self, turno, res):
        turno["texto"], turno["estado"] = res.texto, "listo"
        turno["propuestas"] = [dict(p, estado="pendiente") for p in res.propuestas]
        turno["segundos"] = time.time() - turno["t0"]
        turno["modelo"] = getattr(self._config(), "modelo", "")
        if res.sin_conexion:
            self._civil = res.texto
        self._terminar()
        if res.sin_conexion is False and not isinstance(self._civil, dict):
            self.reconectar()                            # respondió: Civil 3D está; refrescar la línea de estado

    def _al_fallo(self, turno, rep):
        turno["estado"], turno["reporte"] = "error", rep
        turno["error"] = html.escape(rep.texto() if hasattr(rep, "texto") else str(rep))
        self._terminar()

    def _terminar(self):
        self._activo = None
        self._ocupado(False)
        self.actualizar_estado()
        self._pintar()

    # ── aplicar / descartar (solo el usuario) ──
    def _propuesta(self, valor):
        try:
            i, k = (int(x) for x in valor.split("."))
            return self.turnos[i]["propuestas"][k]
        except (ValueError, IndexError, KeyError):
            return None

    def _decidir(self, valor, aplicar):
        p = self._propuesta(valor)
        if p is None or p.get("estado") != "pendiente" or self._agente is None:
            return
        if p.get("destino") == "app":            # «traer a la app»: lo aplica la app, no Civil 3D
            self._decidir_app(p, aplicar)
            return
        p["estado"] = "aplicando" if aplicar else "descartando"
        self._pintar()

        def correr():
            try:
                ok, txt = (self._agente.confirmar if aplicar else self._agente.cancelar)(p["id"])
            except Exception as e:                       # noqa: BLE001
                ok, txt = False, str(e)
            self._sen.aplicado.emit(p, aplicar and ok, txt if not ok else "")

        threading.Thread(target=correr, name="pdfcad-civil3d-aplicar", daemon=True).start()

    def _decidir_app(self, p, aplicar):
        """Lleva a la app lo cambiado en Civil 3D: un paso de Ctrl+Z (`civil3d_comparar.aplicar`)."""
        if not aplicar:
            p["estado"], p["resultado"] = "descartado", _tr("Descartada")
            self._pintar()
            return
        from ia import civil3d_comparar
        w = self.win
        w._push()
        tocados = civil3d_comparar.aplicar(w.pipes, p.get("cambios") or [])
        if not tocados:
            w._undo.pop()
            p["estado"], p["resultado"] = "error", _tr("No había nada que cambiar en la app.")
        else:
            w._redraw()
            p["estado"], p["resultado"] = "aplicado", _tr("Aplicado en la app · se deshace con Ctrl+Z")
        self._pintar()

    def _al_aplicado(self, p, aplicado, error):
        if error:
            p["estado"], p["resultado"] = "error", error
        elif aplicado:
            p["estado"], p["resultado"] = "aplicado", _tr("Aplicado en Civil 3D · se deshace con U")
        else:
            p["estado"], p["resultado"] = "descartado", _tr("Descartada")
        self._pintar()

    # ── enlaces ──
    def _enlace_aviso(self, url):
        (self.win.configurar_ia if url.startswith("config") else self.reconectar)()
        self.actualizar_estado()

    def _enlace(self, url):
        tipo, valor = url.scheme(), url.path()
        if tipo in ("aplicar", "descartar"):
            self._decidir(valor, tipo == "aplicar")
        elif tipo == "ira" and self._cliente is not None:
            threading.Thread(target=lambda: self._cliente.llamar("ir_a", {"handles": [valor]}),
                             daemon=True).start()
        elif tipo == "config":
            self.win.configurar_ia()
            self.actualizar_estado()
        elif tipo == "reconectar":
            self.reconectar()
        elif tipo == "copiarerror" and valor.isdigit() and int(valor) < len(self.turnos):
            rep = self.turnos[int(valor)].get("reporte")
            if rep is not None:
                QtWidgets.QApplication.clipboard().setText(rep.texto())
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), _tr("Copiada"), self.vista)
        elif tipo in ("copiar", "repetir") and valor.isdigit() and int(valor) < len(self.turnos):
            tu = self.turnos[int(valor)]
            if tipo == "repetir":
                self.enviar(tu["pregunta"])
            elif tu["texto"]:
                QtWidgets.QApplication.clipboard().setText(tu["texto"])
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), _tr("Copiada"), self.vista)

    # ── dibujar ──
    def _pintar(self, abajo=False):
        from ui.comun import theme
        barra = self.vista.verticalScrollBar()
        al_final = abajo or barra.value() >= barra.maximum() - 24
        pos = barra.value()
        self.vista.setHtml(H.conversacion(self.turnos, theme.tokens(), time.time()))
        barra.setValue(barra.maximum() if al_final else pos)
        self.caja_sug.setVisible(not self.turnos)
