"""Miniaturas al pasar el mouse (hover) sobre listas.

- `duct_bank_pixmap(db)`: dibujo de la SECCIÓN de un bancoducto (envolvente,
  margen, conductos) — lo usa la lista «Bancoductos» del inventario.
- `pipe_pixmap(scene, pts)`: recorte del plano alrededor de una utilidad con
  la utilidad resaltada — lo usa el diseñador para «Asignar a:».
- `HoverPreview`: se instala en una QListWidget/QListView y muestra, en lugar
  del tooltip de texto, un globo con la miniatura + un texto corto. Si el
  proveedor devuelve None para una fila, queda el tooltip normal.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import theme as _theme


# ── Sección del bancoducto ────────────────────────────────────────────────
def _envelope_path(x, y, w, h, tl, tr, br, bl) -> QtGui.QPainterPath:
    """Rectángulo con radio propio por esquina (0 = escuadra viva)."""
    lim = min(w, h) / 2.0
    tl, tr, br, bl = (max(0.0, min(r, lim)) for r in (tl, tr, br, bl))
    p = QtGui.QPainterPath()
    p.moveTo(x + tl, y)
    p.lineTo(x + w - tr, y)
    if tr: p.arcTo(QtCore.QRectF(x + w - 2 * tr, y, 2 * tr, 2 * tr), 90, -90)
    p.lineTo(x + w, y + h - br)
    if br: p.arcTo(QtCore.QRectF(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br), 0, -90)
    p.lineTo(x + bl, y + h)
    if bl: p.arcTo(QtCore.QRectF(x, y + h - 2 * bl, 2 * bl, 2 * bl), -90, -90)
    p.lineTo(x, y + tl)
    if tl: p.arcTo(QtCore.QRectF(x, y, 2 * tl, 2 * tl), 180, -90)
    p.closeSubpath()
    return p


def duct_bank_pixmap(db, w: int = 260, h: int = 190) -> QtGui.QPixmap:
    """Miniatura de la sección transversal del bancoducto `db` (pulgadas →
    píxeles a escala uniforme, centrada). Conductos con su etiqueta si cabe."""
    t = _theme.tokens()
    dpr = 2.0
    pm = QtGui.QPixmap(int(w * dpr), int(h * dpr)); pm.setDevicePixelRatio(dpr)
    pm.fill(QtGui.QColor(t.grid_bg))
    qp = QtGui.QPainter(pm); qp.setRenderHint(QtGui.QPainter.Antialiasing)
    bw, bh = max(float(db.width_in), 0.1), max(float(db.height_in), 0.1)
    pad = 14.0
    k = min((w - 2 * pad) / bw, (h - 2 * pad - 14) / bh)
    ox = (w - bw * k) / 2.0
    oy = (h - 14 - bh * k) / 2.0
    env = _envelope_path(ox, oy, bw * k, bh * k, db.corner_tl * k, db.corner_tr * k,
                         db.corner_br * k, db.corner_bl * k)
    qp.setPen(QtGui.QPen(QtGui.QColor(t.envelope_border), 1.6))
    qp.setBrush(QtGui.QColor(t.envelope_fill))
    qp.drawPath(env)
    if db.has_margin():
        ix, iy, iw, ih = db.inner_rect()
        if iw > 0 and ih > 0:
            pen = QtGui.QPen(QtGui.QColor(t.text_muted), 1.0, QtCore.Qt.DashLine)
            qp.setPen(pen); qp.setBrush(QtCore.Qt.NoBrush)
            qp.drawRect(QtCore.QRectF(ox + ix * k, oy + iy * k, iw * k, ih * k))
    font = qp.font(); font.setPixelSize(9); qp.setFont(font)
    for c in db.conduits:
        r = max(float(c.diam) * k / 2.0, 1.5)
        rc = QtCore.QRectF(ox + c.cx * k - r, oy + c.cy * k - r, 2 * r, 2 * r)
        qp.setPen(QtGui.QPen(QtGui.QColor(t.conduit_border), 1.2))
        qp.setBrush(QtGui.QColor(t.conduit_fill))
        qp.drawEllipse(rc)
        if c.label and r >= 8:
            qp.setPen(QtGui.QColor(t.conduit_text))
            qp.drawText(rc, QtCore.Qt.AlignCenter, str(c.label)[:4])
    # Cota inferior: ancho × alto de la envolvente
    qp.setPen(QtGui.QColor(t.text))
    font.setPixelSize(11); qp.setFont(font)
    qp.drawText(QtCore.QRectF(0, h - 18, w, 16), QtCore.Qt.AlignCenter,
                f"{db.width_in:g}\" × {db.height_in:g}\"")
    qp.end()
    return pm


# ── Utilidad sobre el plano ───────────────────────────────────────────────
def pipe_pixmap(scene: QtWidgets.QGraphicsScene, pts, color="#f59e0b",
                w: int = 300, h: int = 200) -> Optional[QtGui.QPixmap]:
    """Recorte del plano (la escena del lienzo, con todo lo dibujado) alrededor
    de la polilínea `pts`, con la utilidad resaltada encima. None si no hay
    escena o la utilidad no tiene vértices en el lienzo (tramos importados)."""
    if scene is None or not pts or len(pts) < 1:
        return None
    xs = [float(x) for x, _ in pts]; ys = [float(y) for _, y in pts]
    src = QtCore.QRectF(QtCore.QPointF(min(xs), min(ys)), QtCore.QPointF(max(xs), max(ys)))
    m = max(src.width(), src.height()) * 0.12 + 30.0
    src = src.adjusted(-m, -m, m, m)
    # Misma proporción que la miniatura (si no, render() deforma el plano).
    ar = w / float(h)
    if src.width() / src.height() < ar:
        d = src.height() * ar - src.width(); src.adjust(-d / 2, 0, d / 2, 0)
    else:
        d = src.width() / ar - src.height(); src.adjust(0, -d / 2, 0, d / 2)
    dpr = 2.0
    pm = QtGui.QPixmap(int(w * dpr), int(h * dpr)); pm.setDevicePixelRatio(dpr)
    pm.fill(QtGui.QColor("white"))
    qp = QtGui.QPainter(pm); qp.setRenderHint(QtGui.QPainter.Antialiasing)
    target = QtCore.QRectF(0, 0, w, h)
    try:
        scene.render(qp, target, src, QtCore.Qt.IgnoreAspectRatio)
    except Exception:
        pass
    # Velo claro sobre el plano: la utilidad resaltada se distingue aunque
    # tenga el mismo color que sus vecinas.
    qp.fillRect(target, QtGui.QColor(255, 255, 255, 120))
    k = w / src.width()
    poly = QtGui.QPolygonF([QtCore.QPointF((x - src.left()) * k, (y - src.top()) * k)
                            for x, y in zip(xs, ys)])
    halo = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 7.0)
    halo.setCapStyle(QtCore.Qt.RoundCap); halo.setJoinStyle(QtCore.Qt.RoundJoin)
    qp.setPen(halo); qp.drawPolyline(poly)
    pen = QtGui.QPen(QtGui.QColor(color), 3.5)
    pen.setCapStyle(QtCore.Qt.RoundCap); pen.setJoinStyle(QtCore.Qt.RoundJoin)
    qp.setPen(pen); qp.drawPolyline(poly)
    # Inicio de la utilidad: punto verde (para distinguir el sentido)
    qp.setPen(QtCore.Qt.NoPen); qp.setBrush(QtGui.QColor("#16a34a"))
    qp.drawEllipse(poly[0], 4.5, 4.5)
    qp.end()
    return pm


# ── Globo de miniatura ────────────────────────────────────────────────────
class _PreviewPopup(QtWidgets.QFrame):
    def __init__(self, parent=None):
        # Hijo de la lista (se destruye con ella) pero ventana propia (ToolTip).
        super().__init__(parent, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6); lay.setSpacing(4)
        self.img = QtWidgets.QLabel(); self.img.setAlignment(QtCore.Qt.AlignCenter)
        self.txt = QtWidgets.QLabel(); self.txt.setWordWrap(True)
        self.txt.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(self.img); lay.addWidget(self.txt)

    def show_at(self, pix: Optional[QtGui.QPixmap], caption: str, gpos: QtCore.QPoint):
        t = _theme.tokens()
        self.setStyleSheet(f"_PreviewPopup, QFrame {{ background:{t.surface}; "
                           f"border:1px solid {t.border}; border-radius:6px; }}"
                           f"QLabel {{ border:none; color:{t.text}; background:transparent; }}")
        self.img.setVisible(pix is not None and not pix.isNull())
        if pix is not None:
            self.img.setPixmap(pix)
            self.txt.setFixedWidth(int(pix.width() / max(pix.devicePixelRatio(), 1.0)))
        self.txt.setText(caption or "")
        self.txt.setVisible(bool(caption))
        self.adjustSize()
        scr = QtGui.QGuiApplication.screenAt(gpos) or QtGui.QGuiApplication.primaryScreen()
        area = scr.availableGeometry() if scr else QtCore.QRect(0, 0, 1920, 1080)
        x, y = gpos.x() + 18, gpos.y() + 18
        if x + self.width() > area.right(): x = gpos.x() - self.width() - 12
        if y + self.height() > area.bottom(): y = area.bottom() - self.height() - 4
        self.move(max(area.left(), x), max(area.top(), y))
        self.show(); self.raise_()


class HoverPreview(QtCore.QObject):
    """Miniatura al pasar el mouse sobre las filas de `view`.

    `provider(index) -> (QPixmap | None, caption) | None`. Las miniaturas se
    guardan en caché por fila hasta `clear_cache()` (llamarlo al rellenar la
    lista)."""

    def __init__(self, view: QtWidgets.QAbstractItemView,
                 provider: Callable[[QtCore.QModelIndex], Optional[Tuple]]):
        super().__init__(view)
        self._view = view
        self._provider = provider
        self._popup: Optional[_PreviewPopup] = None
        self._row = -1
        self._cache = {}
        view.viewport().installEventFilter(self)
        view.viewport().setMouseTracking(True)

    def clear_cache(self):
        self._cache.clear()
        self.hide()

    def hide(self):
        self._row = -1
        if self._popup is not None:
            try:
                self._popup.hide()
            except RuntimeError:          # ya destruido junto con la lista
                self._popup = None

    def eventFilter(self, obj, ev):
        et = ev.type()
        if et == QtCore.QEvent.ToolTip:
            idx = self._view.indexAt(ev.pos())
            if not idx.isValid():
                self.hide(); return False
            key = (idx.row(), idx.column())
            if key not in self._cache:
                try:
                    self._cache[key] = self._provider(idx)
                except Exception:
                    self._cache[key] = None
            res = self._cache[key]
            if res is None:
                self.hide(); return False          # tooltip de texto normal
            if self._popup is None:
                self._popup = _PreviewPopup(self._view)
            pix, caption = res
            self._popup.show_at(pix, caption, ev.globalPos())
            self._row = idx.row()
            return True
        if et == QtCore.QEvent.MouseMove:
            if self._row >= 0:
                pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
                if self._view.indexAt(pos).row() != self._row:
                    self.hide()
        elif et in (QtCore.QEvent.Leave, QtCore.QEvent.MouseButtonPress,
                    QtCore.QEvent.Wheel, QtCore.QEvent.Hide):
            self.hide()
        return False
