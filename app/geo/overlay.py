"""
overlay.py — Georreferenciación por SUPERPOSICIÓN ("rubber-sheeting").

Fondo: calles + parcelas reales (2229) y una marca en la intersección buscada.
Encima: la imagen del PDF semitransparente. Se acomoda con:
  · Manual: arrastrar (mover) + botones de escala/rotación (finos) — aproximar.
  · Calce por 2 puntos: clic en un punto del PLANO y luego su gemelo en la CALLE
    real, dos veces → la imagen se escala/rota/coloca sola.

TODA la ubicación se guarda como una SIMILITUD explícita (a, b, tx, ty):
    scene_x = a·px − b·py + tx
    scene_y = b·px + a·py + ty
donde a = escala·cosθ, b = escala·senθ. Así, mover / escalar / rotar / calzar
modifican los mismos 4 números y se combinan bien entre sí (los botones ± siguen
funcionando después del calce). Una similitud NUNCA refleja → jamás sale espejado.
La escena usa Y invertida (y_escena = −Norte) para que el Norte quede arriba.
"""
import math

from PySide6 import QtCore, QtGui, QtWidgets


class OverlayView(QtWidgets.QGraphicsView):
    alignHint = QtCore.Signal(str)
    alignDone = QtCore.Signal()

    def __init__(self, qimg, feet_per_pixel):
        super().__init__()
        self._sc = QtWidgets.QGraphicsScene(self); self.setScene(self._sc)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QtGui.QColor(20, 24, 33))
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self._bg = []
        self.img = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(qimg))
        self.img.setOpacity(0.6); self.img.setZValue(10)
        self._sc.addItem(self.img)                      # ← IMPRESCINDIBLE: mete la imagen en la escena
        self._w, self._h = self.img.pixmap().width(), self.img.pixmap().height()
        # similitud píxel→escena
        self._a, self._b = float(feet_per_pixel) or 1.0, 0.0
        self._tx, self._ty = 0.0, 0.0
        self._apply()
        self._align = None; self._await = None; self._cur_pixel = None
        self._drag = None            # arrastre con botón IZQUIERDO = mover el plano
        self._pan = None             # arrastre con botón CENTRAL (scroll) = panear la vista (estilo AutoCAD)
        # Origen local: la escena se dibuja restando (ox,oy) para que las
        # coordenadas sean pequeñas (~±2000). Si se dibujara en 2229 absoluto
        # (~6.4 millones), Qt pierde precisión y NO renderiza los pixmaps.
        self._ox = 0.0; self._oy = 0.0

    def set_origin(self, ox, oy):
        self._ox, self._oy = float(ox), float(oy)

    def _r2s(self, x, y):
        """Real (2229) → escena local (Y invertida, centrada en el origen)."""
        return (x - self._ox, self._oy - y)

    # ── modelo de transformación ──
    def _apply(self):
        self.img.setTransform(QtGui.QTransform(self._a, self._b, -self._b, self._a, self._tx, self._ty))

    def _map(self, px, py):
        return (self._a * px - self._b * py + self._tx, self._b * px + self._a * py + self._ty)

    def _center(self):
        return self._map(self._w / 2.0, self._h / 2.0)

    def _keep_center(self, csx, csy):
        """Ajusta tx,ty para que el centro de la imagen vuelva a (csx,csy)."""
        cx, cy = self._map(self._w / 2.0, self._h / 2.0)
        self._tx += csx - cx; self._ty += csy - cy; self._apply()

    # ── fondo real ──
    def _clear_bg(self):
        for it in self._bg:
            self._sc.removeItem(it)
        self._bg = []

    def set_reference(self, streets, parcels=None, marker=None):
        self._clear_bg()
        if parcels:
            pen = QtGui.QPen(QtGui.QColor("#4a5568")); pen.setCosmetic(True)
            for pts in parcels:
                self._bg.append(self._sc.addPath(self._path(pts, closed=True), pen))
        pen = QtGui.QPen(QtGui.QColor("#7fd0ff")); pen.setCosmetic(True); pen.setWidth(2)
        for pts in streets:
            self._bg.append(self._sc.addPath(self._path(pts), pen))
        if marker:
            sx, sy = self._r2s(*marker)
            pm = QtGui.QPen(QtGui.QColor("#ff5252")); pm.setCosmetic(True); pm.setWidth(2)
            self._bg.append(self._sc.addEllipse(sx - 30, sy - 30, 60, 60, pm))
        for it in self._bg:
            it.setZValue(0)

    def _path(self, pts, closed=False):
        s0 = self._r2s(pts[0][0], pts[0][1])
        path = QtGui.QPainterPath(); path.moveTo(s0[0], s0[1])
        for p in pts[1:]:
            s = self._r2s(p[0], p[1]); path.lineTo(s[0], s[1])
        if closed:
            path.closeSubpath()
        return path

    def set_initial_size(self, width_ft):
        """Arranca la imagen con un ancho aproximado en pies (para que se VEA;
        no es a escala — el calce por 2 puntos la ajusta)."""
        if self._w:
            self._a = float(width_ft) / self._w; self._b = 0.0; self._apply()

    def place_at(self, cx, cy):
        sx, sy = self._r2s(cx, cy)
        self._keep_center(sx, sy)
        r = self._sc.itemsBoundingRect()
        QtCore.QTimer.singleShot(0, lambda: self.fitInView(r, QtCore.Qt.KeepAspectRatio))

    # ── manual (aproximar / afinar) ──
    def scale_image(self, f):
        c = self._center()
        self._a *= f; self._b *= f
        self._keep_center(*c)

    def rotate_image(self, deg):
        c = self._center()
        sc = math.hypot(self._a, self._b); th = math.atan2(self._b, self._a) + math.radians(deg)
        self._a, self._b = sc * math.cos(th), sc * math.sin(th)
        self._keep_center(*c)

    def move(self, dx, dy):
        self._tx += dx; self._ty += dy; self._apply()

    def set_img_opacity(self, a):
        self.img.setOpacity(max(0.1, min(1.0, a)))

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

    # ── calce por N puntos (2 o más; mínimos cuadrados → promedia el error) ──
    def start_align(self):
        self._align = []; self._await = "plano"; self._cur_pixel = None
        self.alignHint.emit("Calce · clic en un punto reconocible del PLANO (imagen).")

    def is_aligning(self):
        return self._align is not None

    def cancel_align(self):
        self._align = None; self._await = None

    def finish_align(self):
        n = len(self._align) if self._align else 0
        self._align = None; self._await = None
        self.alignDone.emit()
        self.alignHint.emit(f"Calce terminado con {n} puntos. Afina con －/＋ si hace falta y pulsa «Usar superposición».")

    def _refit(self):
        """Similitud (escala+rotación+traslación) por MÍNIMOS CUADRADOS sobre
        todos los pares píxel↔escena recogidos. Más puntos → promedia el error
        de clic. Nunca refleja."""
        pts = self._align
        n = len(pts)
        lcx = sum(p[0] for p in pts) / n; lcy = sum(p[1] for p in pts) / n
        scx = sum(p[2] for p in pts) / n; scy = sum(p[3] for p in pts) / n
        num_re = num_im = den = 0.0
        for lx, ly, sx, sy in pts:
            px, py = lx - lcx, ly - lcy; qx, qy = sx - scx, sy - scy
            num_re += px * qx + py * qy
            num_im += px * qy - py * qx
            den += px * px + py * py
        if den < 1e-9:
            self.alignHint.emit("Los puntos del plano quedaron muy juntos; usa puntos más separados."); return
        self._a, self._b = num_re / den, num_im / den
        self._tx = scx - (self._a * lcx - self._b * lcy)
        self._ty = scy - (self._b * lcx + self._a * lcy)
        self._apply()

    def mousePressEvent(self, e):
        if self._align is not None and e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint())
            if self._await == "plano":
                lp = self.img.mapFromScene(sp)                 # → píxel local de la imagen
                self._cur_pixel = (lp.x(), lp.y()); self._await = "calle"
                self.alignHint.emit(f"Punto {len(self._align) + 1} · clic en el MISMO punto en la CALLE real.")
            else:
                self._align.append((self._cur_pixel[0], self._cur_pixel[1], sp.x(), sp.y()))
                self._await = "plano"
                if len(self._align) >= 2:
                    self._refit()
                    self.alignHint.emit(f"✓ {len(self._align)} puntos calzados. Agrega MÁS puntos (bien "
                                        "separados) para afinar, o pulsa «🎯» de nuevo para terminar.")
                else:
                    self.alignHint.emit("Punto 2 · clic en OTRO punto reconocible del PLANO (bien separado del 1º).")
            e.accept(); return
        # Botón CENTRAL (rueda) = panear la vista, como en AutoCAD (no mueve el plano).
        if e.button() == QtCore.Qt.MiddleButton:
            self._pan = e.position(); self.setCursor(QtCore.Qt.ClosedHandCursor)
            e.accept(); return
        if e.button() == QtCore.Qt.LeftButton:
            self._drag = e.position(); e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        # Paneo con botón central: desplaza las barras de scroll por el delta en píxeles.
        if self._pan is not None:
            p = e.position()
            dx = int(p.x() - self._pan.x()); dy = int(p.y() - self._pan.y())
            self._pan = p
            h = self.horizontalScrollBar(); v = self.verticalScrollBar()
            h.setValue(h.value() - dx); v.setValue(v.value() - dy)
            e.accept(); return
        if self._drag is not None:
            d0 = self.mapToScene(self._drag.toPoint()); d1 = self.mapToScene(e.position().toPoint())
            self.move(d1.x() - d0.x(), d1.y() - d0.y())
            self._drag = e.position(); e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan is not None and e.button() == QtCore.Qt.MiddleButton:
            self._pan = None; self.unsetCursor(); e.accept(); return
        if self._drag is not None:
            self._drag = None; e.accept(); return
        super().mouseReleaseEvent(e)

    # ── derivación de la georreferencia ──
    def georef_points(self):
        # escena local → real (2229): X = sx + ox ; Y = oy − sy
        return [((px, py), (sx + self._ox, self._oy - sy))
                for (px, py) in ((0.0, 0.0), (self._w, 0.0), (0.0, self._h))
                for (sx, sy) in [self._map(px, py)]]
