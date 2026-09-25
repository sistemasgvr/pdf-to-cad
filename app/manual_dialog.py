"""manual_dialog.py — visor del Manual de usuario.

Pensado para alguien a quien no se le da bien la tecnología: un capítulo por
página (nunca un muro de texto), índice siempre visible a la izquierda, botones
grandes «Anterior / Siguiente», letra ajustable (A− / A+) que se recuerda, y los
colores del tema activo (claro u oscuro).

El texto vive en ``docs/manual.<idioma>.html`` (``i18n.load_doc``). Cada capítulo
es un ``<section data-title="…">``. El HTML usa marcadores ``{{token}}`` que se
reemplazan por los colores del tema (``theme.tokens()``), y ``<img src="mark:…">``
para los símbolos del lienzo, que se DIBUJAN aquí con los mismos colores y formas
que usa ``app_window`` (así la leyenda es idéntica a lo que el usuario ve).
"""
from __future__ import annotations

import re

from PySide6 import QtCore, QtGui, QtWidgets

import i18n as _i18n
import theme as _theme
from i18n import t as _tr
from icons import icon as _icon

_SETTINGS_FONT = "manual/font_px"
_FONT_MIN, _FONT_MAX, _FONT_DEF = 13, 26, 17


# ── Símbolos del lienzo (mismos colores y formas que app_window) ─────────────
def _marca(nombre: str, lado: int = 26) -> QtGui.QImage:
    img = QtGui.QImage(lado, lado, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    c = lado / 2
    f = p.font(); f.setBold(True); f.setPixelSize(int(lado * 0.55)); p.setFont(f)

    def circulo(borde, relleno, texto, color_texto):
        p.setPen(QtGui.QPen(QtGui.QColor(*borde), 2))
        p.setBrush(QtGui.QColor(*relleno))
        p.drawEllipse(QtCore.QRectF(3, 3, lado - 6, lado - 6))
        p.setPen(QtGui.QColor(*color_texto))
        p.drawText(QtCore.QRectF(0, 0, lado, lado), QtCore.Qt.AlignCenter, texto)

    if nombre == "conflicto":
        circulo((180, 20, 20), (255, 235, 60), "!", (180, 20, 20))
    elif nombre == "sugerencia":
        circulo((30, 90, 220), (180, 220, 255), "↕", (30, 90, 220))
    elif nombre == "aprobado":
        circulo((30, 160, 60), (180, 240, 200), "✓", (30, 160, 60))
    elif nombre == "alerta":
        tri = QtGui.QPolygonF([QtCore.QPointF(c, 2), QtCore.QPointF(lado - 2, lado - 3),
                               QtCore.QPointF(2, lado - 3)])
        p.setPen(QtGui.QPen(QtGui.QColor(120, 0, 0), 1.5))
        p.setBrush(QtGui.QColor(215, 25, 25)); p.drawPolygon(tri)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.drawText(QtCore.QRectF(0, lado * 0.18, lado, lado * 0.8), QtCore.Qt.AlignCenter, "!")
    elif nombre.startswith("snap_"):
        p.setPen(QtGui.QPen(QtGui.QColor(20, 170, 60), 2.5)); p.setBrush(QtCore.Qt.NoBrush)
        r = QtCore.QRectF(5, 5, lado - 10, lado - 10)
        if nombre == "snap_extremo":
            p.drawEllipse(r)
        elif nombre == "snap_vertice":
            p.drawRect(r)
        else:
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(c, 4), QtCore.QPointF(lado - 4, lado - 5),
                                           QtCore.QPointF(4, lado - 5)]))
    p.end()
    return img


_MARCAS = ("conflicto", "sugerencia", "aprobado", "alerta",
           "snap_extremo", "snap_vertice", "snap_tramo")


def _colores() -> dict:
    t = _theme.tokens()
    oscuro = QtGui.QColor(t.surface).lightness() < 128
    return {
        "bg": t.surface, "text": t.text, "muted": t.text_muted, "accent": t.accent,
        "border": t.border, "card": t.surface_alt, "on_accent": t.text_on_accent,
        # Cajas de color suaves, con contraste suficiente en cada tema.
        "tip": "#1f3a2a" if oscuro else "#e6f6ea", "tip_border": "#3fae62",
        "warn": "#3d2f14" if oscuro else "#fff4d6", "warn_border": "#d6a21e",
        "info": "#18304d" if oscuro else "#e5f0ff", "info_border": "#3d7bd9",
        "danger": "#4a1c1c" if oscuro else "#fde8e8", "danger_border": "#d23c3c",
        "key": "#3a3f47" if oscuro else "#eceef2",
    }


def _capitulos(html: str) -> list[tuple[str, str]]:
    """[(título, html)] a partir de las <section data-title="…">."""
    return [(m.group(1), m.group(2)) for m in
            re.finditer(r'<section\s+data-title="([^"]+)"\s*>(.*?)</section>', html, re.S)]


class ManualDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_tr("Manual de usuario"))
        self.resize(1100, 800)
        self._settings = QtCore.QSettings("pdfcad", "app")
        try:
            self._font_px = int(self._settings.value(_SETTINGS_FONT, _FONT_DEF))
        except (TypeError, ValueError):
            self._font_px = _FONT_DEF

        doc = _i18n.load_doc("manual")
        self._estilo = re.search(r"<style>(.*?)</style>", doc, re.S)
        self._estilo = self._estilo.group(1) if self._estilo else ""
        self._caps = _capitulos(doc) or [(_tr("Manual de usuario"), doc)]

        t = _theme.tokens()
        lay = QtWidgets.QVBoxLayout(self)
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Índice: letra grande, un clic abre el capítulo.
        self.indice = QtWidgets.QListWidget()
        self.indice.setMinimumWidth(300)
        self.indice.setWordWrap(True)
        self.indice.setTextElideMode(QtCore.Qt.ElideNone)
        self.indice.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.indice.setStyleSheet(
            f"QListWidget{{background:{t.surface_alt};color:{t.text};border:1px solid {t.border};"
            f"font-size:15px;padding:6px;}}"
            f"QListWidget::item{{padding:9px 8px;border-radius:6px;}}"
            f"QListWidget::item:selected{{background:{t.accent};color:{t.text_on_accent};}}")
        for n, (titulo, _html) in enumerate(self._caps, 1):
            self.indice.addItem(f"{n}. {titulo}")
        self.indice.currentRowChanged.connect(self._mostrar)
        split.addWidget(self.indice)

        self.visor = QtWidgets.QTextBrowser()
        self.visor.setOpenExternalLinks(True)
        self.visor.setStyleSheet(f"QTextBrowser{{background:{t.surface};border:1px solid {t.border};"
                                 f"padding:14px 22px;}}")
        for nombre in _MARCAS:
            self.visor.document().addResource(QtGui.QTextDocument.ImageResource,
                                              QtCore.QUrl(f"mark:{nombre}"), _marca(nombre))
        split.addWidget(self.visor)
        split.setStretchFactor(1, 1)
        split.setSizes([310, 790])
        lay.addWidget(split, 1)

        # Barra inferior: botones grandes y claros.
        barra = QtWidgets.QHBoxLayout()
        estilo_btn = "QPushButton{font-size:15px;padding:9px 18px;}"
        self.btn_prev = QtWidgets.QPushButton(_icon("mdi:chevron-left"), " " + _tr("Anterior"))
        self.btn_next = QtWidgets.QPushButton(_tr("Siguiente") + " ")
        self.btn_next.setIcon(_icon("mdi:chevron-right"))
        self.btn_next.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.btn_menos = QtWidgets.QPushButton("A−")
        self.btn_mas = QtWidgets.QPushButton("A+")
        self.btn_menos.setToolTip(_tr("Letra más pequeña"))
        self.btn_mas.setToolTip(_tr("Letra más grande"))
        self.lbl_pos = QtWidgets.QLabel()
        self.lbl_pos.setStyleSheet(f"color:{t.text_muted};font-size:14px;")
        btn_cerrar = QtWidgets.QPushButton(_tr("Cerrar"))
        for b in (self.btn_prev, self.btn_next, self.btn_menos, self.btn_mas, btn_cerrar):
            b.setStyleSheet(estilo_btn); b.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_prev.clicked.connect(lambda: self._ir(-1))
        self.btn_next.clicked.connect(lambda: self._ir(+1))
        self.btn_menos.clicked.connect(lambda: self._letra(-1))
        self.btn_mas.clicked.connect(lambda: self._letra(+1))
        btn_cerrar.clicked.connect(self.accept)
        barra.addWidget(self.btn_prev); barra.addWidget(self.btn_next)
        barra.addSpacing(16); barra.addWidget(self.lbl_pos); barra.addStretch(1)
        barra.addWidget(QtWidgets.QLabel(_tr("Tamaño de letra:")))
        barra.addWidget(self.btn_menos); barra.addWidget(self.btn_mas)
        barra.addSpacing(16); barra.addWidget(btn_cerrar)
        lay.addLayout(barra)

        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageDown), self, lambda: self._ir(+1))
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_PageUp), self, lambda: self._ir(-1))
        QtGui.QShortcut(QtGui.QKeySequence.ZoomIn, self, lambda: self._letra(+1))
        QtGui.QShortcut(QtGui.QKeySequence.ZoomOut, self, lambda: self._letra(-1))

        self.indice.setCurrentRow(0)

    # ── navegación ──
    def _ir(self, paso):
        fila = self.indice.currentRow() + paso
        if 0 <= fila < len(self._caps):
            self.indice.setCurrentRow(fila)

    def _letra(self, paso):
        self._font_px = max(_FONT_MIN, min(_FONT_MAX, self._font_px + paso))
        self._settings.setValue(_SETTINGS_FONT, self._font_px)
        self._mostrar(self.indice.currentRow())

    def _mostrar(self, fila):
        if not (0 <= fila < len(self._caps)):
            return
        titulo, cuerpo = self._caps[fila]
        colores = _colores()
        css = self._estilo
        cuerpo_html = cuerpo
        for k, v in colores.items():
            css = css.replace("{{" + k + "}}", v)
            cuerpo_html = cuerpo_html.replace("{{" + k + "}}", v)
        fs = self._font_px
        css = (css.replace("{{fs}}", str(fs)).replace("{{fs_h1}}", str(int(fs * 1.6)))
               .replace("{{fs_h2}}", str(int(fs * 1.25))).replace("{{fs_small}}", str(max(12, fs - 2))))
        self.visor.document().setDefaultStyleSheet(css)
        self.visor.setHtml(f"<html><body><h1>{titulo}</h1>{cuerpo_html}</body></html>")
        self.visor.verticalScrollBar().setValue(0)
        n = len(self._caps)
        self.lbl_pos.setText(_tr("Capítulo {n} de {total}").format(n=fila + 1, total=n))
        self.btn_prev.setEnabled(fila > 0)
        self.btn_next.setEnabled(fila < n - 1)
        self.btn_menos.setEnabled(fs > _FONT_MIN)
        self.btn_mas.setEnabled(fs < _FONT_MAX)


def show_manual(win):
    dlg = ManualDialog(win)
    dlg.exec()
