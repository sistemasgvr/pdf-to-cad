"""fondo_pdf.py — La hoja del PDF como imagen de fondo de una vista, aunque sea enorme.

Reporte del usuario (2026-10-09): una hoja compuesta de 18 piezas daba «code=5: Overly
large image». El editor dibuja la hoja ENTERA como una sola imagen a zoom 3.5 (252 dpi)
y MuPDF no crea imágenes de más de 1 GiB (≈358 Mpx en RGB): 18 hojas del DU06 son
1006 Mpx (3 GB). «Capas de la hoja» (zoom 3.0) chocaba con lo mismo.

- `render_pix(page, zoom)`: si la imagen completa cabe, la de SIEMPRE (misma llamada,
  misma imagen: las hojas que ya se abrían no cambian en nada); si no, la misma hoja a
  menos resolución (≈`PRESUPUESTO_PX`) y `escala` = px de la imagen por px de la vista
  (< 1). Las coordenadas de la vista NO cambian (siguen siendo pt × zoom): la imagen se
  muestra agrandada 1/escala (`FondoItem`).
- `Nitidez`: al acercarse, vuelve a dibujar nítida SOLO la parte visible (hasta la
  resolución de siempre), como el compositor; con una lista de dibujo de MuPDF en caché
  (DU06 ×18: 0.7 s una vez, luego 20–100 ms por recorte).
- `gris`: la imagen en grises para el imán a la tinta, por bloques de filas (antes tres
  matrices float64 del tamaño de la hoja); el resultado es idéntico byte a byte.
- `leer_png`: Qt no abre por defecto imágenes de más de 256 MB (`QImageReader`): un
  proyecto con una hoja compuesta de ~2 hojas o más no se podía volver a abrir.
"""
from __future__ import annotations

import math
from typing import Callable, NamedTuple, Optional

import fitz
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

LIMITE_BYTES = 1 << 30            # MuPDF: pixmap ≤ 1 GiB (medido: ancho × alto × 3 ≤ 2³⁰)
PRESUPUESTO_PX = 100_000_000      # hoja reducida: ≈ 2 hojas de 36"×24" a zoom 3.5
NITIDO_MAX_PX = 24_000_000        # recorte nítido (como `pdf_view_quality`)


class Fondo(NamedTuple):
    pix: fitz.Pixmap
    escala: float                 # px de la imagen por px de la vista (1 = la de siempre)
    ancho: int                    # tamaño de la hoja en px de la vista (pt × zoom)
    alto: int


def tam_px(page: fitz.Page, zoom: float):
    """Ancho y alto en px de la hoja entera a `zoom` (el recorte que haría MuPDF)."""
    r = (page.rect * fitz.Matrix(zoom, zoom)).irect
    return r.width, r.height


def cabe(ancho: int, alto: int) -> bool:
    """¿MuPDF crea la imagen RGB de ese tamaño? (2 px de margen por el redondeo)."""
    return (ancho + 2) * (alto + 2) * 3 <= LIMITE_BYTES


def escala_reducida(ancho: int, alto: int) -> float:
    return min(1.0, math.sqrt(PRESUPUESTO_PX / max(1.0, float(ancho) * float(alto))))


def render_pix(page: fitz.Page, zoom: float) -> Fondo:
    """La hoja entera a `zoom` (o reducida si no cabe; ver el docstring del módulo)."""
    ancho, alto = tam_px(page, zoom)
    if cabe(ancho, alto):
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return Fondo(pix, 1.0, pix.width, pix.height)
        except RuntimeError as exc:           # el límite de MuPDF por si cambia de versión
            if "large" not in str(exc).lower() and "wide" not in str(exc).lower():
                raise
    escala = escala_reducida(ancho, alto)
    z = zoom * escala
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
    return Fondo(pix, escala, ancho, alto)


def qimage(pix: fitz.Pixmap, buf: Optional[bytes] = None) -> QtGui.QImage:
    buf = bytes(pix.samples) if buf is None else buf
    return QtGui.QImage(buf, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888).copy()


def gris(buf: bytes, ancho: int, alto: int, stride: int) -> np.ndarray:
    """Grises de una imagen RGB888: 0.299 R + 0.587 G + 0.114 B truncado, como
    siempre, pero por bloques de filas (sin matrices float64 de toda la hoja)."""
    arr = np.frombuffer(buf, np.uint8).reshape(alto, stride)[:, :ancho * 3].reshape(alto, ancho, 3)
    out = np.empty((alto, ancho), np.uint8)
    paso = max(1, 4_000_000 // max(1, ancho))
    for y in range(0, alto, paso):
        a = arr[y:y + paso]
        out[y:y + paso] = (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]).astype(np.uint8)
    return out


def snap_nitido(nitidez: "Nitidez", page: fitz.Page, zoom: float, x: float, y: float, r: int):
    """Imán a la tinta con la hoja enorme: la ventana de radio `r` alrededor de (x, y)
    (px de la vista) se dibuja a resolución completa y se busca ahí, igual que en la
    imagen de siempre. En la imagen reducida una línea fina queda gris claro y el
    imán no la veía."""
    from geometry import snap_point
    xi, yi = int(x), int(y)
    clip = fitz.Rect(page.rect.x0 + (xi - r - 1) / zoom, page.rect.y0 + (yi - r - 1) / zoom,
                     page.rect.x0 + (xi + r + 2) / zoom, page.rect.y0 + (yi + r + 2) / zoom)
    pix = nitidez._lista_de(page).get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, clip=clip)
    tile = gris(bytes(pix.samples), pix.width, pix.height, pix.stride)
    sx, sy = snap_point(tile, x - pix.x, y - pix.y, r)
    return sx + pix.x, sy + pix.y


def leer_png(datos: bytes) -> QtGui.QImage:
    """PNG → QImage sin el tope de 256 MB de `QImageReader` (la hoja de un proyecto
    con una hoja compuesta lo pasa fácil)."""
    if QtGui.QImageReader.allocationLimit():
        QtGui.QImageReader.setAllocationLimit(0)
    return QtGui.QImage.fromData(datos, "PNG")


def escala_de(item) -> float:
    """Escala del fondo que muestra `item` (1 si es un pixmap normal)."""
    return float(getattr(item, "escala", 1.0)) if item is not None else 1.0


def nuevo_item(pm: QtGui.QPixmap, escala: float) -> QtWidgets.QGraphicsPixmapItem:
    """Item para la imagen de la hoja: el de siempre si `escala` = 1."""
    if escala >= 1.0:
        return QtWidgets.QGraphicsPixmapItem(pm)
    return FondoItem(pm, escala)


def _vivo(item) -> bool:
    try:
        return item is not None and item.scene() is not None
    except RuntimeError:                       # el C++ ya se borró (scene().clear())
        return False


class FondoItem(QtWidgets.QGraphicsPixmapItem):
    """Imagen reducida de la hoja, agrandada 1/escala para ocupar la hoja entera en
    las coordenadas de la vista. Bajo el recorte nítido (`nitido`, hijo) no se pinta:
    con la opacidad del PDF < 100 % las dos imágenes se sumarían (tinta más oscura)."""

    def __init__(self, pm: QtGui.QPixmap, escala: float):
        super().__init__(pm)
        self.escala = float(escala)
        self.nitido: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self.setScale(1.0 / self.escala)
        self.setTransformationMode(QtCore.Qt.SmoothTransformation)

    def paint(self, painter, option, widget=None):
        n = self.nitido
        if not _vivo(n):
            super().paint(painter, option, widget)
            return
        painter.save()
        fuera = QtGui.QPainterPath()
        fuera.addRect(self.boundingRect())
        dentro = QtGui.QPainterPath()
        dentro.addRect(n.mapRectToParent(n.boundingRect()))
        painter.setClipPath(fuera.subtracted(dentro), QtCore.Qt.IntersectClip)
        super().paint(painter, option, widget)
        painter.restore()


class Nitidez(QtCore.QObject):
    """Recorte nítido de la parte visible de un `FondoItem` (hoja reducida) en una
    vista con señal `viewChanged`. `zoom()` = px de la vista por pt de la hoja;
    `pagina()` = la fitz.Page que muestra el fondo (None = no hay). Con un fondo
    normal (escala 1) no hace nada."""

    def __init__(self, view, zoom: Callable[[], float], pagina: Callable[[], Optional[fitz.Page]],
                 delay_ms: int = 150):
        super().__init__(view)
        self.view = view
        self._zoom = zoom
        self._pagina = pagina
        self.item: Optional[FondoItem] = None
        self._clave = None
        self._lista = None                     # ((documento, hoja), página, lista de dibujo de MuPDF)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.actualizar)
        view.viewChanged.connect(self.programar)

    def fijar(self, item) -> None:
        """Fondo nuevo en la vista (o el de siempre: entonces queda inactiva)."""
        self.soltar()
        self.item = item if isinstance(item, FondoItem) else None
        self._lista = None
        self.programar()

    def soltar(self) -> None:
        """Quita el recorte (llamar ANTES de vaciar la escena)."""
        self._timer.stop()
        self._quitar()
        self.item = None
        self._clave = None

    def invalidar(self) -> None:
        """La hoja cambió (capas): el recorte y la lista de dibujo ya no sirven."""
        self._lista = None
        self._quitar()
        self._clave = None
        self.programar()

    def programar(self) -> None:
        if self.item is not None:
            self._timer.start()

    def _quitar(self) -> None:
        it = self.item
        if it is None or not isinstance(it, FondoItem):
            return
        n = it.nitido
        it.nitido = None
        if _vivo(n):
            n.setParentItem(None)
            n.scene().removeItem(n)
        if _vivo(it):
            it.update()

    @staticmethod
    def _id(page):
        return (id(page.parent), page.number)

    def _lista_de(self, page):
        # `doc[i]` da un objeto nuevo en cada llamada: la clave es (documento, hoja).
        # Al cambiar de hoja o de PDF pasa por `fijar`, que la descarta.
        if self._lista is None or self._lista[0] != self._id(page):
            self._lista = (self._id(page), page, page.get_displaylist())
        return self._lista[2]

    def actualizar(self) -> None:
        it = self.item
        if not _vivo(it):
            self.item = None
            return
        try:
            page = self._pagina()
        except Exception:
            page = None
        zoom = float(self._zoom() or 0.0)
        if page is None or zoom <= 0:
            self._quitar(); return
        base = zoom * it.escala                               # px/pt de la imagen reducida
        pantalla = abs(self.view.transform().m11()) * self.view.devicePixelRatioF()
        quiero = min(zoom, pantalla * zoom * 1.15)            # nunca más que la de siempre
        if quiero < base * 1.4:
            self._quitar(); self._clave = None
            return
        hoja = QtCore.QRectF(0, 0, page.rect.width * zoom, page.rect.height * zoom)
        region = self.view.mapToScene(self.view.viewport().rect()).boundingRect().intersected(hoja)
        if region.isEmpty():
            self._quitar(); self._clave = None
            return
        pad = 0.25 * max(region.width(), region.height())
        region = region.adjusted(-pad, -pad, pad, pad).intersected(hoja)
        x0, y0 = region.left() / zoom, region.top() / zoom
        x1, y1 = region.right() / zoom, region.bottom() / zoom
        area = max(1.0, (x1 - x0) * (y1 - y0))
        escala = min(quiero, math.sqrt(NITIDO_MAX_PX / area))
        if escala < base * 1.4:
            self._quitar(); self._clave = None
            return
        clave = (self._id(page), round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1), round(escala, 3))
        if clave == self._clave and _vivo(it.nitido):
            return
        clip = fitz.Rect(page.rect.x0 + x0, page.rect.y0 + y0, page.rect.x0 + x1, page.rect.y0 + y1)
        pix = self._lista_de(page).get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False, clip=clip)
        pm = QtGui.QPixmap.fromImage(qimage(pix))
        if pm.isNull():
            return
        self._quitar()
        n = QtWidgets.QGraphicsPixmapItem(pm, it)
        n.setTransformationMode(QtCore.Qt.SmoothTransformation)
        n.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        # px del recorte → px de la imagen reducida (padre): MuPDF empieza el recorte
        # en (pix.x, pix.y) px de la hoja a `escala`; exacto, sin estirar.
        k = base / escala
        n.setPos(pix.x * k, pix.y * k)
        n.setTransform(QtGui.QTransform.fromScale(k, k))
        it.nitido = n
        it.update()
        self._clave = clave
