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
- `Nitidez`: al acercarse, la parte visible se ve nítida, como el compositor. Desde
  2026-10-13 (pedido del usuario: «cargar la calidad original al hacer zoom») también en la
  hoja NORMAL y a la resolución de la pantalla, no solo hasta la de la imagen
  (`recorte_nitido`). Desde 2026-10-15 en TESELAS dibujadas en otro proceso (`teselas`): antes
  cada recorte trababa la ventana 0.3–1.3 s con 36 mapas. La imagen de la hoja y sus
  coordenadas no cambian.
- `gris`: la imagen en grises para el imán a la tinta, por bloques de filas (antes tres
  matrices float64 del tamaño de la hoja); el resultado es idéntico byte a byte.
- `leer_png`: Qt no abre por defecto imágenes de más de 256 MB (`QImageReader`): un
  proyecto con una hoja compuesta de ~2 hojas o más no se podía volver a abrir.
"""
from __future__ import annotations

import math
from typing import Callable, NamedTuple, Optional

import fitz
from nucleo import avance
from traduccion.i18n_core import t as _tr
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun.recorte_nitido import Hojas
from ui.comun.teselas_vista import Superficie

LIMITE_BYTES = 1 << 30            # MuPDF: pixmap ≤ 1 GiB (medido: ancho × alto × 3 ≤ 2³⁰)
PRESUPUESTO_PX = 100_000_000      # hoja reducida: ≈ 2 hojas de 36"×24" a zoom 3.5


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
    avance.avisar(_tr("Dibujando la hoja en pantalla ({w} × {h} px)…").format(w=_miles(ancho), h=_miles(alto)))
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
    """Item para la imagen de la hoja (`FondoItem`: con `escala` = 1 se pinta igual que un
    QGraphicsPixmapItem, pero admite el recorte nítido de `Nitidez`)."""
    return FondoItem(pm, min(1.0, float(escala)))


def _vivo(item) -> bool:
    try:
        return item is not None and item.scene() is not None
    except RuntimeError:                       # el C++ ya se borró (scene().clear())
        return False


class FondoItem(QtWidgets.QGraphicsPixmapItem):
    """Imagen de la hoja: reducida (`escala` < 1) se agranda 1/escala para ocupar la hoja
    entera en las coordenadas de la vista; con `escala` = 1 es la imagen de siempre, con los
    mismos ajustes de un QGraphicsPixmapItem. Al acercarse, encima van las teselas nítidas de
    `superficie` (`teselas_vista`); con la opacidad del PDF < 100 % la imagen no se pinta debajo
    de una tesela (las dos se sumarían: tinta más oscura)."""

    def __init__(self, pm: QtGui.QPixmap, escala: float):
        super().__init__(pm)
        self.escala = float(escala)
        self.superficie = Superficie(self)
        if self.escala < 1.0:
            self.setScale(1.0 / self.escala)
            self.setTransformationMode(QtCore.Qt.SmoothTransformation)

    def paint(self, painter, option, widget=None):
        base = lambda: QtWidgets.QGraphicsPixmapItem.paint(self, painter, option, widget)  # noqa: E731
        self.superficie.pintar(painter, base, exclusivo=painter.opacity() < 0.999)


class Nitidez(QtCore.QObject):
    """La parte visible de un `FondoItem` nítida al acercarse, en una vista con señal
    `viewChanged`: con la vista quieta `delay_ms`, pide las teselas que se ven a la resolución
    de la pantalla (`teselas_vista.Superficie`; se dibujan en otro proceso: la ventana no
    espera, reporte del usuario 2026-10-15 con 36 mapas). `zoom()` = px de la vista por pt de
    la hoja; `pagina()` = la fitz.Page que muestra el fondo (None = no hay). Sin acercarse más
    allá de la imagen (×1.4) no pide nada: la hoja se ve como siempre."""

    def __init__(self, view, zoom: Callable[[], float], pagina: Callable[[], Optional[fitz.Page]],
                 delay_ms: int = 80):
        super().__init__(view)
        self.view = view
        self._zoom = zoom
        self._pagina = pagina
        self.item: Optional[FondoItem] = None
        self._hojas = Hojas(max_hojas=1)       # lista de dibujo de la hoja, solo para el imán (`snap_nitido`)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.actualizar)
        view.viewChanged.connect(self.programar)

    def fijar(self, item) -> None:
        """Fondo nuevo en la vista (un item que no es `FondoItem` la deja inactiva)."""
        self.soltar()
        self.item = item if isinstance(item, FondoItem) else None
        self._hojas.soltar()
        self.programar()

    def soltar(self) -> None:
        """Deja de pedir teselas (llamar ANTES de vaciar la escena)."""
        self._timer.stop()
        it = self.item
        if isinstance(it, FondoItem):
            it.superficie.soltar()
            if _vivo(it):
                it.update()
        self.item = None

    def invalidar(self) -> None:
        """La hoja cambió (capas): las teselas y la lista de dibujo ya no sirven."""
        self._hojas.soltar()
        if isinstance(self.item, FondoItem):
            self.item.superficie.invalidar()
        self.programar()

    def programar(self) -> None:
        if self.item is not None:
            self._timer.start()

    @property
    def superficie(self):
        return self.item.superficie if isinstance(self.item, FondoItem) else None

    def _lista_de(self, page):
        """Lista de dibujo de MuPDF de la hoja para `snap_nitido`. `doc[i]` da un objeto nuevo
        en cada llamada: la clave es (documento, hoja); al cambiar de hoja o de PDF pasa por
        `fijar`, que la descarta."""
        return self._hojas.lista(page)

    def actualizar(self, refinar: bool = False) -> None:
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
            it.superficie.soltar(); it.update()
            return
        base = zoom * it.escala                               # px/pt de la imagen de la hoja
        it.superficie.fijar(page, k=base, base=base, calentar=True)
        it.superficie.actualizar(self.view)


def _miles(n) -> str:
    return f"{int(n):,}".replace(",", " ")
