"""encaje_imagen.py — ubicar una hoja de OTRO PDF sobre la hoja del editor por lo que SE VE.

Pedido del usuario 2026-11-17 («Agregar utilidad desde otro PDF»): hay PDF que dibujan el mismo lugar
de otra manera. El de drenaje de Phoenix (QS SD) trae el mapa base de lotes como IMAGEN (tiras de
4820×52 px) y solo calles y servidumbres como vectores: ningún método por trazos puede encajarlo. Aquí
se compara lo que se ve («tinta» = 1 − gris, suavizada y con media cero), en tres niveles:

  1. búsqueda (`PT_NIVELES[0]` pt por píxel): la hoja nueva, dibujada UNA vez y reducida a cada escala
     candidata, se correlaciona (FFT) con la hoja del editor ENTERA; los mejores lugares distintos
     pasan. Una hoja nueva que cae mitad y mitad sobre dos piezas se ubica igual que una entera;
  2. ajuste (2 pt/px, escala ±4 %) y 3. fino (1 pt/px, ±0.8 %, pico subpíxel), solo en la zona del
     editor alrededor de lo hallado.

Se acepta si el pico del nivel fino es claro (`Z_LIBRE`; `Z_CONOCIDA` cuando la escala ya la dio otra
hoja del mismo PDF, que además restringe la búsqueda) y el fino no se aparta del ajuste (`DERIVA_PT`);
si no, None: nunca se ubica una hoja «más o menos». (La «dominancia» del pico y una prueba nula con
la hoja corrida se probaron y no separan: los mapas de lotes se parecen a sí mismos corridos.)
Sin giro (mapas al norte; la hoja visible ya trae su /Rotate). PURO: fitz, numpy, OpenCV.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

PT_NIVELES = (6.0, 2.0, 1.0)  # pt de la hoja compuesta por píxel: búsqueda, ajuste, fino
PX_MAX = 2_000_000          # el lienzo de búsqueda no pasa de esto (sube el pt por píxel)
PASO_BUSQUEDA = 0.02        # pasos de la escala (log) en la búsqueda…
RANGO_AJUSTE = 1.04         # …±4 % en el ajuste, en pasos de
PASO_AJUSTE = 0.005
RANGO_FINO = 1.008          # …±0.8 % en el fino, en pasos de
PASO_FINO = 0.0015
ZOOM_HOJA_MAX = 2.0         # la hoja nueva se dibuja una vez a lo sumo a esta escala
CANDIDATOS = 3              # lugares de la búsqueda que pasan al ajuste
Z_LIBRE = 13.0              # pico del nivel fino (desvíos sobre la media de la correlación de la zona)
Z_CONOCIDA = 11.0           # …si la escala ya la dio otra hoja del mismo PDF (medido en Phoenix: las
                            # hojas bien ubicadas dan 12–20; las falsas, ≤ 11)
LEJOS_PX = 6
DERIVA_PT = 4.0             # el fino no se aparta más de esto del ajuste (si no, otra cosa)
MARGEN_PT = 60.0            # zona del lienzo alrededor de la hoja ubicada
CERCA_PT = 80.0             # `ubicar_cerca`: la hoja está a lo sumo a esto de lo previsto
RANGO_CERCA = 1.003         # …con la escala conocida ±0.3 % (las hojas de un PDF varían ≤0.13 %)
LISTAS_MAX = 12             # listas de dibujo de las hojas del editor que se guardan (0 = ninguna: se arma
                            # una por dibujo, como antes); las zonas de hojas seguidas tocan las mismas piezas


@dataclass
class Ubicado:
    """Similaridad hoja nueva (pt visibles) → hoja compuesta: X = s·x + tx, Y = s·y + ty."""
    s: float
    tx: float
    ty: float
    z: float
    dominio: float

    def tupla(self) -> Tuple[float, float, float, float]:
        return self.s, 0.0, self.tx, self.ty


def tinta(page, zoom: float, clip=None, lista=None) -> np.ndarray:
    """La hoja (o el recorte, en coordenadas de la hoja visible) como tinta 0..1. `lista` = la lista de
    dibujo de la hoja ya armada (`page.get_pixmap` arma una en cada llamada y la dibuja: mismos píxeles)."""
    import fitz
    if lista is None:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, colorspace=fitz.csGRAY, alpha=False)
    else:                       # (lo mismo que hace `Page.get_pixmap` con una lista nueva)
        pix = lista.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False, clip=clip)
    a = np.frombuffer(pix.samples, np.uint8)[: pix.h * pix.stride].reshape(pix.h, pix.stride)[:, : pix.w]
    return (255.0 - a.astype(np.float32)) / 255.0


TINTA_MIN = 0.08            # un píxel con al menos esto de tinta cuenta como línea (todas pesan igual:
                            # si no, el marco grueso de la hoja «encaja» con una tubería gruesa del editor)


def _prep(x: np.ndarray) -> np.ndarray:
    import cv2
    x = cv2.GaussianBlur((x >= TINTA_MIN).astype(np.float32), (0, 0), 1.0)
    return x - float(x.mean())


class Espectros:
    """La transformada de A por tamaño (H, W). A (la zona del editor) es la misma para todas las escalas de
    un nivel y el tamaño casi siempre también: se transforma una vez (la MISMA cuenta: mismos números)."""

    def __init__(self, A: np.ndarray):
        self.A = A
        self._por_tam = {}

    def de(self, H: int, W: int) -> np.ndarray:
        e = self._por_tam.get((H, W))
        if e is None:
            e = self._por_tam[(H, W)] = np.fft.rfft2(self.A, (H, W))
        return e


def _corr(A: np.ndarray, B: np.ndarray, esp: Optional[Espectros] = None) -> np.ndarray:
    import cv2
    H = cv2.getOptimalDFTSize(A.shape[0] + B.shape[0])
    W = cv2.getOptimalDFTSize(A.shape[1] + B.shape[1])
    FA = esp.de(H, W) if esp is not None else np.fft.rfft2(A, (H, W))
    return np.fft.irfft2(FA * np.conj(np.fft.rfft2(B, (H, W))), (H, W))


def _pico(c: np.ndarray, forma_b, dominio: bool = False):
    """(z, dx, dy subpíxel, dominio sobre el mejor lugar lejano) de la correlación `c` (B de
    `forma_b` deslizada sobre A: los desplazamientos válidos van de −alto/ancho de B a +A)."""
    H, W = c.shape
    i = int(np.argmax(c))
    py, px = divmod(i, W)
    m, sd = float(c.mean()), float(c.std()) or 1.0
    pico = float(c.flat[i])
    dom = 0.0
    if dominio:
        ys = [(py + k) % H for k in range(-LEJOS_PX, LEJOS_PX + 1)]
        xs = [(px + k) % W for k in range(-LEJOS_PX, LEJOS_PX + 1)]
        guarda = c[np.ix_(ys, xs)].copy()
        c[np.ix_(ys, xs)] = m
        dom = (pico - m) / max(1e-9, float(c.max()) - m)
        c[np.ix_(ys, xs)] = guarda

    def sub(v_m, v_0, v_p):
        q = v_m - 2 * v_0 + v_p
        return 0.0 if abs(q) < 1e-12 else 0.5 * (v_m - v_p) / q
    fy = sub(c[(py - 1) % H, px], pico, c[(py + 1) % H, px])
    fx = sub(c[py, (px - 1) % W], pico, c[py, (px + 1) % W])
    dy = py if py <= H - forma_b[0] else py - H
    dx = px if px <= W - forma_b[1] else px - W
    return (pico - m) / sd, dx + fx, dy + fy, dom


def escalas_alrededor(centro: float, factor: float, paso: float = PASO_BUSQUEDA) -> List[float]:
    k = int(math.ceil(math.log(factor) / paso))
    return [centro * math.exp(i * paso) for i in range(-k, k + 1)]


class Lienzo:
    """La hoja del editor dibujada: `piezas` = [(page, clip visible fitz.Rect, caja en la hoja
    compuesta (x0, y0, x1, y1))], cajas en pt (sin giro)."""

    def __init__(self, piezas):
        cajas = [c for _p, _r, c in piezas]
        self.piezas = list(piezas)
        self._listas = {}
        x0 = min(c[0] for c in cajas); y0 = min(c[1] for c in cajas)
        x1 = max(c[2] for c in cajas); y1 = max(c[3] for c in cajas)
        self.origen = (x0, y0)
        self.zona = (x0, y0, x1, y1)
        self.r = max(PT_NIVELES[0], math.sqrt((x1 - x0) * (y1 - y0) / PX_MAX))
        self.img = _prep(self.dibujar(self.r, self.zona))

    @classmethod
    def armado(cls, piezas, img: np.ndarray, r: float, origen, zona) -> "Lienzo":
        """Un lienzo ya dibujado (otro proceso del grupo: `encaje_imagen_lote`) sin volver a dibujarlo."""
        lz = cls.__new__(cls)
        lz.piezas, lz._listas = list(piezas), {}
        lz.img, lz.r, lz.origen, lz.zona = img, r, tuple(origen), tuple(zona)
        return lz

    def _lista(self, i: int):
        """La lista de dibujo de la hoja de la pieza `i` (se arma una vez; las más viejas se sueltan)."""
        dl = self._listas.pop(i, None)
        if dl is None:
            dl = self.piezas[i][0].get_displaylist(annots=True)
            while len(self._listas) >= LISTAS_MAX:
                self._listas.pop(next(iter(self._listas)))
        self._listas[i] = dl                        # (al final: la más reciente)
        return dl

    def dibujar(self, r: float, zona) -> np.ndarray:
        """La hoja del editor en `zona` (pt de la hoja compuesta) a `r` pt por píxel."""
        import fitz
        zx0, zy0, zx1, zy1 = zona
        H, W = int(math.ceil((zy1 - zy0) / r)) + 1, int(math.ceil((zx1 - zx0) / r)) + 1
        out = np.zeros((H, W), np.float32)
        for i, (page, clip, caja) in enumerate(self.piezas):
            ix0, iy0 = max(caja[0], zx0), max(caja[1], zy0)
            ix1, iy1 = min(caja[2], zx1), min(caja[3], zy1)
            if ix1 - ix0 < r or iy1 - iy0 < r:
                continue
            f = (caja[2] - caja[0]) / max(1e-9, clip.width)         # pt compuesta por pt de su hoja
            sub = fitz.Rect(clip.x0 + (ix0 - caja[0]) / f, clip.y0 + (iy0 - caja[1]) / f,
                            clip.x0 + (ix1 - caja[0]) / f, clip.y0 + (iy1 - caja[1]) / f)
            t = tinta(page, f / r, sub, self._lista(i) if LISTAS_MAX else None)
            cx, cy = int(round((ix0 - zx0) / r)), int(round((iy0 - zy0) / r))
            h, w = min(t.shape[0], H - cy), min(t.shape[1], W - cx)
            if h > 0 and w > 0:
                out[cy:cy + h, cx:cx + w] = np.maximum(out[cy:cy + h, cx:cx + w], t[:h, :w])
        return out

    def recorte(self, r: float, zona):
        """La zona (recortada a la hoja del editor) ya preparada → (imagen, zona) o None."""
        z = (max(zona[0], self.zona[0]), max(zona[1], self.zona[1]),
             min(zona[2], self.zona[2]), min(zona[3], self.zona[3]))
        if z[2] - z[0] < 10 * r or z[3] - z[1] < 10 * r:
            return None
        return _prep(self.dibujar(r, z)), z


class Hoja:
    """La hoja nueva dibujada UNA vez (a la mayor escala que se va a pedir) y reducida a pedido."""

    def __init__(self, page, zoom_max: float):
        self.page = page
        self.zoom = min(ZOOM_HOJA_MAX, zoom_max)
        self.base = tinta(page, self.zoom)

    def a(self, zoom: float):
        """→ (imagen preparada, zoom real: px por pt de la hoja)."""
        import cv2
        k = zoom / self.zoom
        h, w = max(2, int(round(self.base.shape[0] * k))), max(2, int(round(self.base.shape[1] * k)))
        img = cv2.resize(self.base, (w, h), interpolation=cv2.INTER_AREA)
        return _prep(img), w / self.base.shape[1] * self.zoom


def _nivel(lz: Lienzo, hoja: Hoja, r: float, escalas, zona):
    """El mejor (z, 0, s, tx, ty) de las escalas en una zona del lienzo."""
    rec = lz.recorte(r, zona)
    if rec is None:
        return None
    A, z0 = rec
    esp = Espectros(A)
    mejor = None
    for s in escalas:
        B, zr = hoja.a(s / r)
        z, dx, dy, _d = _pico(_corr(A, B, esp), B.shape)
        if mejor is None or z > mejor[0]:
            mejor = (z, 0.0, zr * r, z0[0] + dx * r, z0[1] + dy * r)
    return mejor


def _candidatos(lz: Lienzo, hoja: Hoja, escalas, cancelado=None, zona=None):
    """Búsqueda gruesa en el lienzo entero (o en `zona`, pt de la hoja compuesta: la celda de la hoja y
    sus vecinas): los mejores lugares distintos (z, dominio, s, tx, ty)."""
    out = []
    r = lz.r
    img, origen = lz.img, lz.origen
    if zona is not None:
        rec = lz.recorte(r, zona)
        if rec is None:
            return []
        img, z = rec
        origen = (z[0], z[1])
    esp = Espectros(img)
    for s in escalas:
        if cancelado is not None and cancelado():
            return []
        B, zr = hoja.a(s / r)
        if B.shape[0] > 4 * img.shape[0] + 600 and B.shape[1] > 4 * img.shape[1] + 600:
            continue
        z, dx, dy, dom = _pico(_corr(img, B, esp), B.shape, dominio=True)
        out.append((z, dom, zr * r, origen[0] + dx * r, origen[1] + dy * r))
    out.sort(key=lambda v: -v[0])
    elegidos = []
    for v in out:
        if any(abs(v[3] - e[3]) < 3 * r and abs(v[4] - e[4]) < 3 * r for e in elegidos):
            continue
        elegidos.append(v)
        if len(elegidos) >= CANDIDATOS:
            break
    return elegidos


def ubicar(lz: Lienzo, page, escalas: Sequence[float], cancelado=None, diag=None,
           z_min: float = Z_LIBRE, zona=None) -> Optional[Ubicado]:
    """La hoja nueva ubicada sobre el lienzo (búsqueda → ajuste → fino), o None. `zona` acota la
    búsqueda gruesa (pt de la hoja compuesta)."""
    if not escalas:
        return None
    hoja = Hoja(page, max(escalas) * RANGO_AJUSTE / PT_NIVELES[-1])
    W, H = page.rect.width, page.rect.height
    mejor = None
    for z0, dom0, s, tx, ty in _candidatos(lz, hoja, escalas, cancelado, zona):
        if cancelado is not None and cancelado():
            return None
        zona = (tx - MARGEN_PT, ty - MARGEN_PT, tx + s * W + MARGEN_PT, ty + s * H + MARGEN_PT)
        aj = _nivel(lz, hoja, PT_NIVELES[1], escalas_alrededor(s, RANGO_AJUSTE, PASO_AJUSTE), zona)
        fi = None if aj is None else _nivel(
            lz, hoja, PT_NIVELES[2], escalas_alrededor(aj[2], RANGO_FINO, PASO_FINO), zona)
        if diag is not None:
            diag.append(dict(busqueda=(z0, dom0, s, tx, ty), ajuste=aj, fino=fi))
        if fi is None or fi[0] < z_min:
            continue
        if math.hypot(fi[3] - aj[3], fi[4] - aj[4]) > DERIVA_PT:
            continue
        if mejor is None or fi[0] > mejor.z:
            mejor = Ubicado(fi[2], fi[3], fi[4], fi[0], dom0)
    return mejor


def ubicar_cerca(lz: Lienzo, page, previsto: Sequence[float], z_min: float = Z_CONOCIDA,
                 diag=None) -> Optional[Ubicado]:
    """La hoja nueva donde se PREVÉ (`previsto` = (s, 0, tx, ty), p. ej. por su celda y otra hoja ya
    ubicada del mismo PDF): solo se comprueba y afina en una ventana chica (sin búsqueda en el lienzo
    entero). → Ubicado, o None si ahí no está."""
    s0, _b, tx0, ty0 = (float(v) for v in previsto)
    W, H = page.rect.width, page.rect.height
    hoja = Hoja(page, s0 * RANGO_CERCA / PT_NIVELES[-1])
    zona = (tx0 - CERCA_PT, ty0 - CERCA_PT, tx0 + s0 * W + CERCA_PT, ty0 + s0 * H + CERCA_PT)
    aj = _nivel(lz, hoja, PT_NIVELES[1], [s0], zona)            # la escala ya se sabe: solo el lugar
    if aj is None or math.hypot(aj[3] - tx0, aj[4] - ty0) > CERCA_PT:
        return None
    fi = _nivel(lz, hoja, PT_NIVELES[2], escalas_alrededor(s0, RANGO_CERCA, PASO_FINO), zona)
    if diag is not None:
        diag.append(dict(previsto=tuple(previsto), ajuste=aj, fino=fi))
    if fi is None or fi[0] < z_min or math.hypot(fi[3] - aj[3], fi[4] - aj[4]) > DERIVA_PT:
        return None
    return Ubicado(fi[2], fi[3], fi[4], fi[0], 0.0)
