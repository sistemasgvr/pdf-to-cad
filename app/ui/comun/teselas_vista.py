"""teselas_vista.py — Una hoja del PDF dibujada en un item, nítida con teselas (`teselas.py`).

`Superficie` es lo que cada item que muestra una hoja (el fondo del editor, de «Capas de la
hoja» y de la vista previa —`fondo_pdf.FondoItem`—, cada pieza del compositor
—`composite_view.PieceItem`— y el «Área a tomar» —`TeselasItem`—) usa para:

  · `actualizar(vista)`: con el zoom de la vista elige el nivel (`teselas.nivel_para`: nunca se
    agranda una tesela en pantalla) y pide las que se ven, primero las del centro, y un anillo
    alrededor para el desplazamiento. No dibuja nada: lo hace el proceso de las teselas;
  · `pintar(...)`: dentro del `paint` del item, la imagen de la hoja de siempre y encima las
    teselas que ya llegaron; donde falta una, las que haya del nivel anterior o, si no, del
    siguiente (recortadas a su cuadro); donde no hay ninguna, la imagen de la hoja. Con la opacidad
    del PDF < 100 % (o «Fundir bordes») la imagen no se pinta debajo de una tesela: se
    sumarían y la tinta se vería más oscura.

Coordenadas del item = pt de la hoja × `k` + (`dx`, `dy`): el fondo del editor va a `zoom ×
escala` px/pt desde (0, 0) y una pieza a `ov` px/pt desde su origen (−ox, −oy). Las teselas
caen EXACTAS sobre la imagen de la hoja, como el recorte nítido de antes.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun import teselas as T
from ui.comun.teselas_servidor import servidor


def _vivo(item) -> bool:
    try:
        return item is not None and item.scene() is not None
    except RuntimeError:                       # el C++ ya se borró (scene().clear())
        return False


class Superficie:
    def __init__(self, item):
        self.item = item
        self.page = None
        self._hoja = None                      # (id del documento, nº de hoja)
        self.k, self.dx, self.dy = 1.0, 0.0, 0.0
        self.base = 1.0                        # px/pt de la imagen de la hoja que ya muestra el item
        self.limite = None                     # (x0, y0, x1, y1) pt: lo que se ve de la hoja (clip de la pieza)
        self.nivel: Optional[int] = None       # None = solo la imagen de la hoja
        self.tok = self.firma = None

    # ── configuración ────────────────────────────────────────────────
    def fijar(self, page, k: float, dx: float = 0.0, dy: float = 0.0,
              base: Optional[float] = None, limite=None, calentar: bool = False) -> None:
        """La hoja que muestra el item y cómo cae en él. Llamar las veces que haga falta: solo
        cambia algo si cambió la hoja. `calentar`: los procesos preparan ya la lista de dibujo
        de la hoja (una hoja compuesta de 36 mapas: ~8 s una vez), no al primer zoom."""
        hoja = (id(page.parent), page.number)
        self.k, self.dx, self.dy = float(k), float(dx), float(dy)
        self.base = float(base if base is not None else k)
        self.limite = limite
        if hoja != self._hoja:
            self._hoja = hoja
            self.page = page
            self.tok = self.firma = None
            self._poner_nivel(None)
            if calentar:
                servidor().calentar(page)
        else:
            self.page = page

    def soltar(self) -> None:
        """El item deja de mostrar la hoja (o se va de la escena)."""
        servidor().olvidar(self)
        self.page = None
        self._hoja = None
        self.tok = self.firma = None
        self.nivel = None

    def pausar(self) -> None:
        """Fuera de la vista: no pide nada y vuelve a la imagen de la hoja (lo que ya llegó sigue
        en la caché: al volver a verse aparece al instante)."""
        servidor().olvidar(self)
        self._poner_nivel(None)

    def invalidar(self) -> None:
        """La hoja cambió de capas: las teselas de antes ya no sirven (otra firma)."""
        self.tok = self.firma = None
        servidor().olvidar(self)
        self._actualizar_item()

    def viva(self) -> bool:
        return (self.page is not None and not getattr(self.page.parent, "is_closed", False)
                and _vivo(self.item))

    # ── pedidos ──────────────────────────────────────────────────────
    def actualizar(self, vista) -> None:
        """Pide las teselas para lo que muestra `vista` (QGraphicsView) de este item."""
        if self.page is None or not _vivo(self.item) or getattr(self.page.parent, "is_closed", False):
            return
        tr = self.item.deviceTransform(vista.viewportTransform())
        esc = math.sqrt(abs(tr.m11() * tr.m22() - tr.m12() * tr.m21()))
        inv, ok = tr.inverted()
        if not ok or esc <= 0:
            return
        r = QtCore.QRectF(vista.viewport().rect())
        vis = inv.mapRect(r)
        c = inv.map(r.center())
        self.pedir_region(self._a_pt(vis), esc * self.k * vista.devicePixelRatioF(),
                          ((c.x() - self.dx) / self.k, (c.y() - self.dy) / self.k))

    def pedir_region(self, rect_pt, ppp: float, centro_pt=None) -> None:
        """Pide las teselas de `rect_pt` (pt de la hoja) para verlas a `ppp` px de pantalla
        por pt (en orden: del centro hacia afuera; luego el anillo de alrededor)."""
        if self.page is None:
            return
        nivel = T.nivel_para(ppp)
        if not T.hace_falta(ppp, self.base):
            self._poner_nivel(None)
            servidor().pedir(self, self.page, [])
            return
        self.tok, self.firma = servidor().preparar(self.page)
        rect_pt = self._recortar(rect_pt)
        if rect_pt is None:
            servidor().pedir(self, self.page, [])
            return
        w, h = self.page.rect.width, self.page.rect.height
        pedidos = []
        for d, tx, ty, visible in T.teselas_en(rect_pt, nivel, w, h, centro_pt, margen=1):
            if self._fuera(nivel, tx, ty):
                continue
            pedidos.append((d * ppp + (0.0 if visible else 1e9), self._clave(nivel, tx, ty), visible))
        self._poner_nivel(nivel)
        servidor().pedir(self, self.page, pedidos)

    def recibida(self, clave) -> None:
        """Llegó una tesela: repintar solo su cuadro."""
        if not _vivo(self.item):
            return
        try:
            self.item.update(self._rect_local(clave[3], clave[4], clave[5]))
        except RuntimeError:
            pass

    # ── pintar ───────────────────────────────────────────────────────
    def pintar(self, painter, pintar_base, exclusivo: bool = False, recorte=None) -> None:
        """La imagen de la hoja (`pintar_base()`) y encima las teselas. `recorte`: QPainterPath
        (coords del item) al que se limitan las teselas (pieza poligonal)."""
        if self.nivel is None or self.page is None or self.tok is None:
            pintar_base()
            return
        dibujos, cubierto = self._plan(painter)
        if exclusivo and cubierto:
            painter.save()
            todo = QtGui.QPainterPath()
            todo.addRect(self.item.boundingRect())
            tapa = QtGui.QPainterPath()
            tapa.setFillRule(QtCore.Qt.WindingFill)
            for r in cubierto:
                tapa.addRect(r)
            painter.setClipPath(todo.subtracted(tapa), QtCore.Qt.IntersectClip)
            pintar_base()
            painter.restore()
        else:
            pintar_base()
        if not dibujos:
            return
        painter.save()
        # sin suavizado de bordes: dos teselas vecinas comparten el borde exacto (sin rayas)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        if recorte is not None:
            painter.setClipPath(recorte, QtCore.Qt.IntersectClip)
        for t, celda in dibujos:
            self._dibujar(painter, t, celda)
        painter.restore()

    def _plan(self, painter):
        """[(tesela, cuadro o None)] a dibujar y los cuadros que quedan cubiertos."""
        srv = servidor()
        dev = painter.device()
        inv, ok = painter.worldTransform().inverted()
        vis = inv.mapRect(QtCore.QRectF(0, 0, dev.width(), dev.height())) if ok and dev is not None \
            else self.item.boundingRect()
        rect_pt = self._recortar(self._a_pt(vis.intersected(self.item.boundingRect())))
        if rect_pt is None:
            return [], []
        nivel = self.nivel
        w, h = self.page.rect.width, self.page.rect.height
        r = T.rango(rect_pt, nivel, w, h)
        if r is None:
            return [], []
        dibujos, cubierto = [], []
        for ty in range(r[1], r[3] + 1):
            for tx in range(r[0], r[2] + 1):
                t = srv.tesela(self._clave(nivel, tx, ty))
                if t is not None:
                    dibujos.append((t, None)); cubierto.append(self._rect_t(t))
                    continue
                celda = self._rect_local(nivel, tx, ty)
                # mientras llega: las de un nivel anterior que la cubran entera (recortadas a su
                # cuadro), o las que haya del siguiente; si no, se ve la imagen de la hoja
                previas = self._previas(srv, nivel, tx, ty, w, h)
                if previas:
                    for t in previas:
                        parte = self._rect_t(t).intersected(celda)
                        dibujos.append((t, parte)); cubierto.append(parte)
                    continue
                for cx, cy in T.de_otro_nivel(nivel, tx, ty, nivel + 1, w, h):
                    t = srv.tesela(self._clave(nivel + 1, cx, cy))
                    if t is not None:
                        parte = self._rect_t(t).intersected(celda)
                        dibujos.append((t, parte)); cubierto.append(parte)
        return dibujos, cubierto

    def _previas(self, srv, nivel, tx, ty, w, h):
        """Teselas YA listas del nivel anterior más cercano que tenga alguna sobre el cuadro de
        (nivel, tx, ty) —si se ven mejor que la imagen de la hoja—; [] si no hay."""
        for n2 in range(nivel - 1, T.NIVEL_MIN - 1, -1):
            if not T.mejor_que_base(n2, self.base):
                return []
            ts = [srv.tesela(self._clave(n2, x, y)) for x, y in T.de_otro_nivel(nivel, tx, ty, n2, w, h)]
            ts = [t for t in ts if t is not None]
            if ts:
                return ts
        return []

    def _dibujar(self, painter, t, celda) -> None:
        dest = self._rect_t(t)
        if celda is None:
            painter.drawPixmap(dest, t.pm, QtCore.QRectF(0, 0, t.w, t.h))
            return
        tgt = dest.intersected(celda)
        if tgt.isEmpty():
            return
        fx, fy = t.w / dest.width(), t.h / dest.height()
        src = QtCore.QRectF((tgt.left() - dest.left()) * fx, (tgt.top() - dest.top()) * fy,
                            tgt.width() * fx, tgt.height() * fy)
        painter.drawPixmap(tgt, t.pm, src)

    # ── estado (pruebas y diagnóstico) ───────────────────────────────
    def escala(self) -> float:
        """px/pt de las teselas que se muestran (0 = solo la imagen de la hoja)."""
        return T.escala_nivel(self.nivel) if self.nivel is not None else 0.0

    def listas(self):
        """Teselas del nivel actual que ya están en la caché (las pedidas por esta superficie)."""
        if self.nivel is None or self.tok is None:
            return []
        srv = servidor()
        lst = srv._duenos.get(id(self), (None, None, []))[2]
        return [(c, srv._cache[c]) for _p, c, _v in lst if c in srv._cache and c[3] == self.nivel]

    # ── utilidades ───────────────────────────────────────────────────
    def _clave(self, nivel, tx, ty):
        return (self.tok, self.firma, self.page.number, int(nivel), int(tx), int(ty))

    def _a_pt(self, r: QtCore.QRectF):
        k = self.k
        return ((r.left() - self.dx) / k, (r.top() - self.dy) / k,
                (r.right() - self.dx) / k, (r.bottom() - self.dy) / k)

    def _recortar(self, rect_pt):
        x0, y0, x1, y1 = rect_pt
        if self.limite is not None:
            lx0, ly0, lx1, ly1 = self.limite
            x0, y0, x1, y1 = max(x0, lx0), max(y0, ly0), min(x1, lx1), min(y1, ly1)
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            return None
        return x0, y0, x1, y1

    def _fuera(self, nivel, tx, ty) -> bool:
        """¿La tesela cae entera fuera de lo que se ve de la hoja (`limite`)?"""
        if self.limite is None:
            return False
        r = T.rect_tesela(nivel, tx, ty, self.page.rect.width, self.page.rect.height)
        if r is None:
            return True
        lx0, ly0, lx1, ly1 = self.limite
        return r[2] <= lx0 or r[0] >= lx1 or r[3] <= ly0 or r[1] >= ly1

    def _rect_local(self, nivel, tx, ty) -> QtCore.QRectF:
        r = T.rect_tesela(nivel, tx, ty, self.page.rect.width, self.page.rect.height) or (0, 0, 0, 0)
        k = self.k
        return QtCore.QRectF(r[0] * k + self.dx, r[1] * k + self.dy, (r[2] - r[0]) * k, (r[3] - r[1]) * k)

    def _rect_t(self, t) -> QtCore.QRectF:
        """Cuadro de la tesela en coords del item, desde el origen EXACTO que dio MuPDF."""
        f = self.k / T.escala_nivel(t.nivel)
        return QtCore.QRectF(t.x * f + self.dx, t.y * f + self.dy, t.w * f, t.h * f)

    def _poner_nivel(self, nivel) -> None:
        if nivel != self.nivel:
            self.nivel = nivel
            self._actualizar_item()

    def _actualizar_item(self) -> None:
        if _vivo(self.item):
            try:
                self.item.update()
            except RuntimeError:
                pass


class TeselasItem(QtWidgets.QGraphicsItem):
    """Solo las teselas (sin imagen debajo): para una vista que ya tiene su propia imagen de la
    hoja en otro item («Área a tomar» del compositor, `pdf_view_quality.ViewportSharpener`)."""

    def __init__(self):
        super().__init__()
        self.superficie = Superficie(self)
        self._rect = QtCore.QRectF()
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)

    def set_rect(self, rect: QtCore.QRectF) -> None:
        if rect != self._rect:
            self.prepareGeometryChange()
            self._rect = QtCore.QRectF(rect)

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect

    def paint(self, painter, option, widget=None):
        self.superficie.pintar(painter, lambda: None)
