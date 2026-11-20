"""monitor_ventana.py — la ventana del monitor de rendimiento, en SU PROPIO proceso.

Lee la sesión del vigilante en vivo (`nucleo/vigilante_vivo.Sesion`, cada `LEER_MS`) y el latido de la ventana
(cada `LATIDO_MS`): como corre aparte, sigue al día aunque la app esté en «No responde». Arriba, el estado de la
app AHORA y las cifras de la sesión; debajo, pestañas (`monitor_pestanas`). Exporta el informe en Markdown
(`nucleo/vigilante_informe`) y compara con otra sesión (antes/después de un cambio).
"""
from __future__ import annotations

import os
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import vigilante_informe as VI
from nucleo import vigilante_vivo as VV
from traduccion.i18n import t as _tr
from ui.comun import theme
from ui.monitor import monitor_pestanas as MP
from ui.monitor.monitor_util import dur, mb

LEER_MS = 1000
LATIDO_MS = 250
CLAVE_AL_INICIAR = "monitor/al_iniciar"


def _ajustes():
    return QtCore.QSettings("pdf-to-cad", "app")


def abrir_al_iniciar() -> bool:
    return str(_ajustes().value(CLAVE_AL_INICIAR, "false")).lower() in ("true", "1")


class Punto(QtWidgets.QWidget):
    """Círculo de color del estado de la app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.color = QtGui.QColor("#888")

    def paintEvent(self, _e):                         # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QtCore.QRectF(1, 1, 12, 12))


class Cifra(QtWidgets.QFrame):
    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self.valor = QtWidgets.QLabel("—")
        self.valor.setProperty("rol", "h2")
        t = QtWidgets.QLabel(titulo)
        t.setProperty("rol", "t3")
        lay.addWidget(self.valor)
        lay.addWidget(t)


class Monitor(QtWidgets.QWidget):
    def __init__(self, carpeta: str | None = None):
        super().__init__()
        self.setWindowTitle(_tr("Monitor de rendimiento — Asistente C3D"))
        self.resize(1180, 760)
        self.ses = None
        self._cambios = -1
        self._res = None
        raiz = QtWidgets.QVBoxLayout(self)
        raiz.setContentsMargins(16, 14, 16, 14)
        raiz.setSpacing(10)
        raiz.addLayout(self._cabecera())
        raiz.addLayout(self._cifras())
        self.tabs = QtWidgets.QTabWidget()
        self.p_ahora = MP.PestanaAhora()
        self.p_congela = MP.PestanaCongelamientos()
        self.p_trabajos = MP.PestanaTrabajos()
        self.p_rec = MP.PestanaReconocimiento()
        self.p_pasos = MP.PestanaPasos()
        self.tabs.addTab(self.p_ahora, _tr("Ahora"))
        self.tabs.addTab(self.p_congela, _tr("Congelamientos"))
        self.tabs.addTab(self.p_trabajos, _tr("Trabajos"))
        self.tabs.addTab(self.p_rec, _tr("Reconocimiento"))
        self.tabs.addTab(self.p_pasos, _tr("Pasos y etapas"))
        raiz.addWidget(self.tabs, 1)
        self._llenar_sesiones(carpeta)
        self._t_leer = QtCore.QTimer(self, interval=LEER_MS, timeout=self._leer)
        self._t_latido = QtCore.QTimer(self, interval=LATIDO_MS, timeout=self._ver_ventana)
        self._t_leer.start()
        self._t_latido.start()
        self._leer()

    # ── armar ────────────────────────────────────────────────────────────────────────────────────────
    def _cabecera(self):
        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(10)
        self.punto = Punto()
        self.lbl_estado = QtWidgets.QLabel()
        self.lbl_estado.setProperty("rol", "h1")
        fila.addWidget(self.punto)
        fila.addWidget(self.lbl_estado)
        fila.addStretch(1)
        fila.addWidget(QtWidgets.QLabel(_tr("Sesión:")))
        self.cmb_sesion = QtWidgets.QComboBox()
        self.cmb_sesion.setMinimumWidth(230)
        self.cmb_sesion.currentIndexChanged.connect(self._cambiar_sesion)
        fila.addWidget(self.cmb_sesion)
        menu = QtWidgets.QMenu(self)
        menu.addAction(_tr("Exportar informe…"), self.exportar)
        menu.addAction(_tr("Comparar con otra sesión…"), self.comparar)
        menu.addAction(_tr("Abrir la carpeta de la sesión"), self.abrir_carpeta)
        menu.addSeparator()
        self.act_inicio = menu.addAction(_tr("Abrir el monitor junto con la app"))
        self.act_inicio.setCheckable(True)
        self.act_inicio.setChecked(abrir_al_iniciar())
        self.act_inicio.toggled.connect(lambda v: _ajustes().setValue(CLAVE_AL_INICIAR, bool(v)))
        btn = QtWidgets.QPushButton(_tr("Opciones"))
        btn.setProperty("options", True)
        btn.setMenu(menu)
        fila.addWidget(btn)
        return fila

    def _cifras(self):
        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(10)
        self.c_congela = Cifra(_tr("Pausas de la ventana"))
        self.c_peor = Cifra(_tr("Pausa más larga"))
        self.c_trabajos = Cifra(_tr("Trabajos terminados"))
        self.c_memoria = Cifra(_tr("Memoria de la app"))
        self.c_ram = Cifra(_tr("RAM libre del equipo"))
        self.c_tiempo = Cifra(_tr("Duración de la sesión"))
        for c in (self.c_congela, self.c_peor, self.c_trabajos, self.c_memoria, self.c_ram, self.c_tiempo):
            fila.addWidget(c, 1)
        return fila

    def _llenar_sesiones(self, carpeta):
        lista = list(reversed(VI.sesiones()))
        if carpeta and carpeta not in lista:
            lista.insert(0, carpeta)
        self.cmb_sesion.blockSignals(True)
        self.cmb_sesion.clear()
        for i, s in enumerate(lista):
            nombre = os.path.basename(s)
            etiqueta = _tr("{s} (la más reciente)").format(s=nombre) if i == 0 else nombre
            self.cmb_sesion.addItem(etiqueta, s)
        self.cmb_sesion.blockSignals(False)
        idx = lista.index(carpeta) if carpeta in lista else 0
        self.cmb_sesion.setCurrentIndex(idx)
        self._cambiar_sesion(idx)

    def _cambiar_sesion(self, _i):
        c = self.cmb_sesion.currentData()
        self.ses = VV.Sesion(c) if c else None
        self._cambios, self._res = -1, None
        self._leer()

    # ── al día ───────────────────────────────────────────────────────────────────────────────────────
    def _leer(self):
        ses = self.ses
        if ses is None:
            self.lbl_estado.setText(_tr("Todavía no hay sesiones registradas"))
            return
        ses.actualizar()
        if ses.cambios != self._cambios or self._res is None:
            self._cambios = ses.cambios
            self._res = VI.resumir(ses.sucesos)
            refrescar_todo = True
        else:
            refrescar_todo = False
        estado = self._ver_ventana()
        self.p_ahora.refrescar(ses, self._res, estado)
        if refrescar_todo:
            for p in (self.p_congela, self.p_trabajos, self.p_rec, self.p_pasos):
                p.refrescar(ses, self._res, estado)
        self._poner_cifras()

    def _poner_cifras(self):
        r, ses = self._res, self.ses
        self.c_congela.valor.setText(str(len(r["congelamientos"])))
        self.c_peor.valor.setText(dur(r["congelamientos"][0]["dur"]) if r["congelamientos"] else "—")
        self.c_trabajos.valor.setText(str(sum(a["veces"] for a in r["trabajos"])))
        self.c_memoria.valor.setText(mb(ses.serie[-1][1]) if ses.serie else "—")
        self.c_ram.valor.setText(mb(ses.ram_libre_mb))
        ini = min((p.inicio for p in ses.procesos.values() if p.inicio), default=None)
        viva = ses.ventana()[0] in (VV.RESPONDE, VV.OCUPADA, VV.NO_RESPONDE)
        fin = time.time() if viva else max([e.get("t", 0.0) for e in ses.sucesos[-1:]] + [s[0] for s in ses.serie[-1:]],
                                           default=None)
        self.c_tiempo.valor.setText(dur(fin - ini) if ini and fin else "—")

    def _ver_ventana(self) -> str:
        if self.ses is None:
            return ""
        tk = theme.tokens()
        estado, s = self.ses.ventana()
        textos = {
            VV.RESPONDE: (tk.success, _tr("La app responde")),
            VV.OCUPADA: (tk.warning, _tr("La app está ocupada · {d}").format(d=dur(s))),
            VV.NO_RESPONDE: (tk.danger, _tr("La app NO responde · {d}").format(d=dur(s))),
            VV.CERRADA: (tk.text_muted, _tr("La app se cerró")),
            VV.SIN_DATO: (tk.text_muted, _tr("Sin datos de la ventana")),
        }
        color, texto = textos[estado]
        self.punto.color = QtGui.QColor(color)
        self.punto.update()
        self.lbl_estado.setText(texto)
        return texto

    # ── acciones ─────────────────────────────────────────────────────────────────────────────────────
    def exportar(self):
        if self.ses is None:
            return
        ruta, _f = QtWidgets.QFileDialog.getSaveFileName(
            self, _tr("Guardar informe de rendimiento"),
            os.path.join(os.path.expanduser("~"), "Downloads", f"rendimiento-{os.path.basename(self.ses.carpeta)}.md"),
            _tr("Markdown (*.md)"))
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(VI.markdown(VI.resumir(VI.leer(self.ses.carpeta))))

    def comparar(self):
        if self.ses is None:
            return
        otras = [s for s in reversed(VI.sesiones()) if s != self.ses.carpeta]
        if not otras:
            QtWidgets.QMessageBox.information(self, _tr("Comparar"), _tr("No hay otra sesión para comparar."))
            return
        nombres = [os.path.basename(s) for s in otras]
        elegida, ok = QtWidgets.QInputDialog.getItem(self, _tr("Comparar"),
                                                     _tr("Sesión de ANTES (la elegida arriba es la de después):"),
                                                     nombres, 0, False)
        if not ok:
            return
        antes = otras[nombres.index(elegida)]
        texto = VI.comparar(VI.resumir(VI.leer(antes)), VI.resumir(VI.leer(self.ses.carpeta)))
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_tr("Antes y después"))
        dlg.resize(900, 640)
        lay = QtWidgets.QVBoxLayout(dlg)
        vista = QtWidgets.QTextBrowser()
        vista.setMarkdown(texto)
        lay.addWidget(vista)
        dlg.exec()

    def abrir_carpeta(self):
        if self.ses is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.ses.carpeta))


def main(carpeta: str | None = None) -> int:
    """El proceso del monitor (spawn desde la app, o `--monitor`)."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    from traduccion import i18n
    i18n.load_lang()
    theme.apply_theme(app, theme.load_preference("dark"))
    w = Monitor(carpeta)
    w.show()
    return app.exec()
