"""«¿Cómo hago…?» arriba del Manual de usuario (pedido del usuario 2026-10-23): se escribe qué se quiere hacer y la
IA responde con los pasos, sacados SOLO del manual (`ia/ayuda_manual`).

Rápido: los capítulos que hablan de eso aparecen AL INSTANTE (búsqueda local, ~1 ms) y llevan al capítulo con un
clic; la respuesta de la IA llega en vivo, con poco texto que leer (solo los trozos del manual que vienen al caso)
y poco que escribir; la misma pregunta otra vez sale guardada, sin esperar. Al abrir el manual se le pide al
servidor que deje el modelo cargado (`Proveedor.calentar`). Sin IA configurada, los capítulos son la respuesta.
"""
from __future__ import annotations

import html
import re
import threading

from PySide6 import QtCore, QtWidgets

from ia import ayuda_manual as AM
from ia import proveedor as P
from traduccion.i18n import t as _tr
from ui.comun import theme

_NEGRITA = re.compile(r"\*\*(.+?)\*\*")


class _Senales(QtCore.QObject):
    trozo = QtCore.Signal(int, str)
    listo = QtCore.Signal(int, object)


def _formato(texto):
    return _NEGRITA.sub(r"<b>\1</b>", html.escape(texto)).replace("\n", "<br>")


class PanelAyudaIA(QtWidgets.QWidget):
    """`config()` = la configuración de la IA (dict, `Main._config_ia`) o None; `abrir_capitulo(n)` = ir al
    capítulo n (0…) del manual."""

    def __init__(self, doc, config, abrir_capitulo, parent=None):
        super().__init__(parent)
        self.ix = AM.indice(doc)
        self.config = config
        self.abrir_capitulo = abrir_capitulo
        self._pedido = 0
        self._buffer = ""
        self._caps = []
        self._pregunta = ""
        self._senales = _Senales(self)
        self._senales.trozo.connect(self._al_trozo)
        self._senales.listo.connect(self._al_listo)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        fila = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(_tr("¿Cómo hago…?"))
        lbl.setStyleSheet("font-size:15px; font-weight:600;")
        self.campo = QtWidgets.QLineEdit()
        self.campo.setPlaceholderText(_tr("Escribe qué quieres hacer, por ejemplo: ¿cómo exporto a Civil 3D?"))
        self.campo.setClearButtonEnabled(True)
        self.campo.setStyleSheet("font-size:15px; padding:6px;")
        self.campo.returnPressed.connect(self.preguntar)
        self.btn = QtWidgets.QPushButton(_tr("Preguntar a la IA"))
        self.btn.setAutoDefault(False)
        self.btn.setStyleSheet("QPushButton{font-size:15px;padding:7px 16px;}")
        self.btn.clicked.connect(self._boton)
        fila.addWidget(lbl)
        fila.addWidget(self.campo, 1)
        fila.addWidget(self.btn)
        lay.addLayout(fila)
        self.respuesta = QtWidgets.QTextBrowser()
        self.respuesta.setOpenLinks(False)
        self.respuesta.anchorClicked.connect(self._enlace)
        self.respuesta.setMaximumHeight(280)
        self.respuesta.setStyleSheet("QTextBrowser{font-size:15px; padding:8px;}")
        self.respuesta.hide()
        lay.addWidget(self.respuesta)
        prov = self._proveedor()
        if prov is not None:                        # que el modelo ya esté cargado al preguntar
            threading.Thread(target=prov.calentar, name="pdfcad-ia-calentar", daemon=True).start()

    def _proveedor(self):
        cfg = self.config() if self.config else None
        return P.crear(cfg) if cfg else None

    @property
    def ocupado(self):
        return self.btn.text() == _tr("Detener")

    def _boton(self):
        if self.ocupado:
            self.detener()
        else:
            self.preguntar()

    def detener(self):
        self._pedido += 1
        self._ocupado(False)
        if self._buffer:
            self._mostrar(self._buffer, _tr("Detenida."))

    def _ocupado(self, si):
        self.btn.setText(_tr("Detener") if si else _tr("Preguntar a la IA"))

    def preguntar(self, pregunta=None):
        pregunta = (pregunta if pregunta is not None else self.campo.text()).strip()
        if not pregunta:
            return
        self._pedido += 1
        pedido = self._pedido
        self._pregunta = pregunta
        self._buffer = ""
        self._caps = self.ix.capitulos(pregunta)
        self.respuesta.show()
        guardada = AM.guardada(self.ix, pregunta)
        if guardada:
            self._ocupado(False)
            self._mostrar(guardada, _tr("Respuesta guardada: no se volvió a preguntar a la IA."))
            return
        prov = self._proveedor()
        if prov is None:
            self._ocupado(False)
            self._mostrar("", _tr("Sin IA configurada (IA → Configurar IA…): estos capítulos hablan de eso."))
            return
        self._ocupado(True)
        self._mostrar("", _tr("La IA está pensando…"))

        def correr():
            try:
                r = AM.responder(prov, self.ix, pregunta, al_texto=lambda s: self._senales.trozo.emit(pedido, s),
                                 cancelado=lambda: pedido != self._pedido)
            except P.ErrorIA as e:
                r = (None, str(e), None)
            self._senales.listo.emit(pedido, r)
        threading.Thread(target=correr, name="pdfcad-ia-ayuda", daemon=True).start()

    def _al_trozo(self, pedido, s):
        if pedido == self._pedido:
            self._buffer += s
            self._mostrar(self._buffer, _tr("escribiendo…"))

    def _al_listo(self, pedido, r):
        if pedido != self._pedido:
            return
        self._ocupado(False)
        texto, origen, _caps = r
        if texto is None:
            self._mostrar("", _tr("La IA no respondió ({e}): estos capítulos hablan de eso.").format(e=origen))
            return
        nota = {"ia": _tr("Según el manual de usuario."),
                "memoria": _tr("Respuesta guardada: no se volvió a preguntar a la IA.")}.get(origen, "")
        self._mostrar(texto, nota)

    def _mostrar(self, texto, nota):
        tk = theme.tokens()
        partes = []
        if texto:
            partes.append(f"<div>{_formato(texto)}</div>")
        if nota:
            partes.append(f"<p style='color:{tk.text_muted}; font-size:small'><i>{html.escape(nota)}</i></p>")
        if self._caps:
            enlaces = " · ".join(f"<a href='cap:{n}' style='color:{tk.text_info}'>{html.escape(cap)}</a>"
                                 for n, cap in self._caps)
            partes.append(f"<p>{html.escape(_tr('En el manual:'))} {enlaces}</p>")
        elif not texto:
            partes.append("<p>" + html.escape(_tr("El manual no habla de eso. Prueba con otras palabras o mira el "
                                                 "índice.")) + "</p>")
        barra = self.respuesta.verticalScrollBar()
        abajo = barra.value() >= barra.maximum() - 4
        self.respuesta.setHtml("".join(partes))
        if abajo:
            barra.setValue(barra.maximum())

    def _enlace(self, url):
        if url.scheme() == "cap":
            try:
                self.abrir_capitulo(int(url.path()))
            except ValueError:
                pass
