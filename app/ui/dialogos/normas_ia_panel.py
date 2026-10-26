"""«¿Qué significa esta regla?» en Normativas → Reglas (pedido del usuario 2026-10-23): eliges una fila y
«Explicar con IA» muestra la regla en palabras sencillas. La respuesta queda guardada (`ia/explicar_norma`): al
volver a elegir esa regla aparece al instante, sin pedirla otra vez; si la regla cambia, se puede pedir de nuevo.
Sin IA configurada, muestra la regla leída como frase y qué mide."""
from __future__ import annotations

import html
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from ia import explicar_norma as EN
from ia import proveedor as P
from traduccion.i18n import t as _tr


class _Senales(QtCore.QObject):
    trozo = QtCore.Signal(int, str)
    listo = QtCore.Signal(int, object)


class PanelExplicacion(QtWidgets.QWidget):
    def __init__(self, win, editor, parent=None):
        super().__init__(parent)
        self.win, self.editor = win, editor
        self.vista = editor.vistas["reglas"]
        self._pedido = 0
        self._buffer = ""
        self._senales = _Senales(self)
        self._senales.trozo.connect(self._al_trozo)
        self._senales.listo.connect(self._al_listo)
        from ui.comun import ia_estilo as E
        externo = QtWidgets.QVBoxLayout(self)
        externo.setContentsMargins(0, 8, 0, 0)
        self.caja = QtWidgets.QFrame()                   # todo en una tarjeta con el icono de la IA
        self.caja.setObjectName("explicacionIA")
        externo.addWidget(self.caja)
        lay = QtWidgets.QVBoxLayout(self.caja)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(8)
        self.ico = QtWidgets.QLabel()
        self.ico.setStyleSheet("background: transparent;")
        self.lbl = QtWidgets.QLabel(_tr("¿Qué significa esta regla?"))
        self.btn = QtWidgets.QPushButton(_tr("Explicar con IA"))
        self.btn.setProperty("soft", True)
        self.btn.setAutoDefault(False)
        self.btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn.setToolTip(_tr("La IA explica la regla elegida en palabras sencillas. La respuesta se guarda: la "
                                "misma regla no se vuelve a pedir."))
        self.btn.clicked.connect(self.explicar)
        fila.addWidget(self.ico)
        fila.addWidget(self.lbl, 1)
        fila.addWidget(self.btn)
        lay.addLayout(fila)
        self.texto = QtWidgets.QTextBrowser()
        self.texto.setMaximumHeight(130)
        self.texto.setFrameShape(QtWidgets.QFrame.NoFrame)
        lay.addWidget(self.texto)
        E.al_cambiar_tema(self, self._estilo)
        self.vista.currentCellChanged.connect(lambda *_a: self.mostrar())
        self.mostrar()

    def _estilo(self):
        from ui.comun import ia_estilo as E, icons, theme
        tk = theme.tokens()
        self.caja.setStyleSheet(E.tarjeta("explicacionIA", tk))
        E.texto_en_tarjeta(self.texto)
        self.ico.setPixmap(E.pix("mdi:robot-outline", tk.accent if not theme.is_dark() else tk.focus, 20))
        self.lbl.setStyleSheet(f"font-weight: 600; color: {tk.text}; background: transparent;")
        self.btn.setIcon(icons.icon("mdi:lightbulb-outline", color=tk.soft_text))

    def _fila(self):
        r = self.vista.currentRow()
        return self.editor.fila_de("reglas", r) if r >= 0 else None

    def mostrar(self):
        """Lo guardado de la regla elegida (sin gastar nada) o cómo pedirlo."""
        self._pedido += 1
        fila = self._fila()
        self.btn.setEnabled(fila is not None and EN.datos(fila) is not None)
        if fila is None:
            self.texto.setHtml(self._gris(_tr("Elige una regla de la tabla.")))
            return
        if EN.datos(fila) is None:
            self.texto.setHtml(self._gris(_tr("La regla tiene celdas sin completar o que no se entienden.")))
            return
        guardada = EN.guardada(fila)
        if guardada:
            self.btn.setEnabled(False)
            self._poner(fila, guardada, _tr("Guardada: no se volvió a preguntar a la IA."))
        elif P.crear(self.win._config_ia()) is None:
            self._poner(fila, EN.plantilla(fila), _tr("Sin IA configurada: la regla leída por la app."))
        else:
            self.texto.setHtml(self._gris(_tr("Pulsa «Explicar con IA» para leerla en palabras sencillas.")))

    def explicar(self):
        fila = self._fila()
        prov = P.crear(self.win._config_ia())
        if fila is None:
            return
        if prov is None:
            self._poner(fila, EN.plantilla(fila), _tr("Sin IA configurada (IA → Configurar IA…): la regla leída por la app."))
            return
        self._pedido += 1
        pedido = self._pedido
        self._buffer = ""
        self.btn.setEnabled(False)
        self.texto.setHtml(self._gris(_tr("La IA está pensando…")))

        def correr():
            try:
                r = EN.explicar(prov, fila, al_texto=lambda s: self._senales.trozo.emit(pedido, s),
                                cancelado=lambda: pedido != self._pedido)
            except (P.ErrorIA, ValueError) as e:
                r = (None, str(e))
            self._senales.listo.emit(pedido, (fila, r))
        threading.Thread(target=correr, name="pdfcad-ia-norma", daemon=True).start()

    def _al_trozo(self, pedido, s):
        if pedido == self._pedido:
            self._buffer += s
            self.texto.setPlainText(self._buffer)

    def _al_listo(self, pedido, r):
        if pedido != self._pedido:
            return
        fila, (texto, origen) = r
        if texto is None:
            self.btn.setEnabled(True)
            self.texto.setHtml(html.escape(origen) + "<br><br>" + html.escape(EN.plantilla(fila)))
            return
        self._poner(fila, texto, _tr("Redactada por la IA y guardada.") if origen == "ia"
                    else _tr("Guardada: no se volvió a preguntar a la IA."))

    def _poner(self, fila, texto, nota):
        from ui.comun import theme
        from ui.dialogos.ia_chat_html import colores_aviso
        tk = theme.tokens()
        cuerpo = html.escape(texto).replace("\n", "<br>")
        cifras = EN.cifras_sin_respaldo(fila, texto)
        if cifras:                                       # misma tarjeta ámbar que el chat (contraste AA)
            fondo, letra = colores_aviso(theme.is_dark())
            cuerpo += (f"<table width='100%' cellspacing='0' cellpadding='6' style='margin-top:6px'><tr>"
                       f"<td bgcolor='{fondo}' style='color:{letra}'>" + html.escape(_tr(
                           "Revisa estas cifras: no están en la regla: {c}").format(
                           c=", ".join(f"{v:g}" for v in cifras))) + "</td></tr></table>")
        pie = f"<p style='margin-top:6px; font-size:small; color:{tk.text_muted}'><i>{html.escape(nota)}</i></p>"
        contenido = f"<div style='color:{tk.text}'>{cuerpo}</div>{pie}"
        self.texto.setHtml(contenido)

    @staticmethod
    def _gris(txt):
        from ui.comun import theme
        return f"<i style='color:{theme.tokens().text_muted}'>" + html.escape(txt) + "</i>"
