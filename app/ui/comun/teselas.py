"""teselas.py — La hoja del PDF nítida al acercarse, en TESELAS (cálculo puro, sin Qt).

Reporte del usuario (2026-10-15): con la hoja compuesta de 36 mapas (o el reconocimiento de
ella), cada vez que el zoom se detenía la ventana se trababa: el recorte nítido de lo visible
se dibujaba en el hilo de la interfaz (0.3–1.3 s cada uno; la primera vez ~7 s: lista de dibujo
+ cajas de 494 mil letras Type3) y PyMuPDF no suelta el GIL mientras dibuja, así que un hilo
no servía. Ahora se hace como los visores de mapas y de planos:

  · la hoja se parte en teselas de `TAM` × `TAM` px por NIVEL de zoom: nivel L = 2^(L/2)
    px/pt (`escala_nivel`; pasos de √2: la tesela queda entre 1 y 1.41 veces la resolución de
    la pantalla, nunca más chica; con pasos de 2 se dibujaba hasta 4× los píxeles a la vista).
    Las teselas de un nivel están en la rejilla de píxeles de la hoja a esa escala (la tesela
    (tx, ty) son los píxeles [tx·TAM, (tx+1)·TAM) de la hoja), así que caen EXACTAS una junto
    a otra y cada una tiene los mismos píxeles que el recorte de siempre
    (`recorte_nitido.Hojas.render`);
  · se dibujan en un PROCESO aparte (`teselas_hijo`) y se guardan en caché: al desplazarse o
    volver a un zoom ya visto no se dibuja otra vez; la ventana nunca espera;
  · se piden primero las del centro de la vista (`teselas_en`) y, mientras llegan, se ve la
    mejor que ya haya de otro nivel o la imagen de la hoja de siempre.
"""
from __future__ import annotations

import math
from typing import List, Tuple

TAM = 1024                  # px de lado de una tesela (≈ 3 MB en RGB; menos teselas = menos recorridos de la lista)
NIVEL_MIN = -8              # 1/16 px/pt
NIVEL_MAX = 12              # 64 px/pt (4608 dpi) = `recorte_nitido.MAX_ESCALA`
UMBRAL_BASE = 1.1           # teselas si la pantalla pide más que la imagen base en esto (antes 1.4: el
                            # primer paso de la rueda se veía algo borroso; ya no cuesta esperar)


def escala_nivel(nivel: int) -> float:
    n = int(nivel)
    return math.ldexp(1.0, n // 2) * (math.sqrt(2.0) if n % 2 else 1.0)


def nivel_para(ppp: float) -> int:
    """Nivel de la vista: el más chico cuya escala alcanza `ppp` (px de pantalla por pt), así
    la tesela nunca se agranda en pantalla (se ve nítida); a lo sumo se achica √2."""
    if not ppp or ppp <= 0 or not math.isfinite(ppp):
        return NIVEL_MIN
    n = max(NIVEL_MIN, min(NIVEL_MAX, int(math.ceil(2.0 * math.log2(ppp) - 1e-9))))
    while n > NIVEL_MIN and escala_nivel(n - 1) >= ppp * (1 - 1e-12):
        n -= 1                                   # redondeo de log2
    return n


def hace_falta(ppp: float, base: float) -> bool:
    """¿La pantalla (`ppp` px por pt) pide más de lo que da la imagen base (`base` px/pt)? Si
    no, la hoja se ve como siempre (a 1:1 o alejada, la imagen es la de MuPDF tal cual)."""
    return ppp >= base * UMBRAL_BASE


def mejor_que_base(nivel: int, base: float) -> bool:
    """¿Una tesela de `nivel` se ve mejor que la imagen base? (para cubrir mientras llega otra)"""
    return escala_nivel(nivel) > base * 1.05


def rect_tesela(nivel: int, tx: int, ty: int, ancho: float, alto: float):
    """(x0, y0, x1, y1) en pt de la hoja visible (origen arriba a la izquierda), recortado a
    la hoja de `ancho` × `alto` pt; None si cae fuera."""
    lado = TAM / escala_nivel(nivel)
    x0, y0 = tx * lado, ty * lado
    x1, y1 = min(ancho, x0 + lado), min(alto, y0 + lado)
    if tx < 0 or ty < 0 or x0 >= ancho or y0 >= alto:
        return None
    return x0, y0, x1, y1


def rango(rect_pt, nivel: int, ancho: float, alto: float, margen: int = 0):
    """(tx0, ty0, tx1, ty1) inclusivos de las teselas de `nivel` que tocan `rect_pt` (más
    `margen` teselas alrededor), dentro de la hoja; None si no toca la hoja."""
    x0, y0, x1, y1 = rect_pt
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(ancho, x1), min(alto, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    lado = TAM / escala_nivel(nivel)
    nx, ny = max(1, math.ceil(ancho / lado)), max(1, math.ceil(alto / lado))
    tx0, ty0 = int(x0 // lado) - margen, int(y0 // lado) - margen
    tx1 = int(math.ceil(x1 / lado)) - 1 + margen
    ty1 = int(math.ceil(y1 / lado)) - 1 + margen
    return max(0, tx0), max(0, ty0), min(nx - 1, tx1), min(ny - 1, ty1)


def teselas_en(rect_pt, nivel: int, ancho: float, alto: float, centro=None,
               margen: int = 0) -> List[Tuple[float, int, int, bool]]:
    """Teselas de `nivel` para ver `rect_pt` (pt de la hoja): [(distancia, tx, ty, visible)]
    ordenadas de la más cercana a `centro` (pt; por defecto el centro de `rect_pt`) a la más
    lejana; con `margen`, también el anillo de alrededor (visible=False: para adelantar el
    desplazamiento, después de todas las visibles)."""
    r = rango(rect_pt, nivel, ancho, alto, margen)
    if r is None:
        return []
    vis = rango(rect_pt, nivel, ancho, alto, 0)
    lado = TAM / escala_nivel(nivel)
    cx, cy = centro if centro is not None else ((rect_pt[0] + rect_pt[2]) / 2, (rect_pt[1] + rect_pt[3]) / 2)
    out = []
    for ty in range(r[1], r[3] + 1):
        for tx in range(r[0], r[2] + 1):
            dentro = vis is not None and vis[0] <= tx <= vis[2] and vis[1] <= ty <= vis[3]
            d = math.hypot((tx + 0.5) * lado - cx, (ty + 0.5) * lado - cy)
            out.append((d, tx, ty, dentro))
    out.sort(key=lambda e: (not e[3], e[0]))
    return out


def de_otro_nivel(nivel: int, tx: int, ty: int, otro: int, ancho: float, alto: float):
    """Teselas de `otro` nivel que tocan a (nivel, tx, ty): con ellas se cubre su cuadro
    mientras llega la suya (las rejillas de dos niveles no coinciden: se recortan al cuadro)."""
    r = rect_tesela(nivel, tx, ty, ancho, alto)
    if r is None or not NIVEL_MIN <= otro <= NIVEL_MAX:
        return []
    e = 1e-6 * max(1.0, r[2] - r[0])            # que un borde compartido no cuente como «toca»
    g = rango((r[0] + e, r[1] + e, r[2] - e, r[3] - e), otro, ancho, alto)
    if g is None:
        return []
    return [(x, y) for y in range(g[1], g[3] + 1) for x in range(g[0], g[2] + 1)]


def dibujar(hojas, page, nivel: int, tx: int, ty: int):
    """Pixmap de MuPDF de la tesela (None si cae fuera de la hoja). Los MISMOS píxeles que
    `page.get_pixmap(matrix=2^nivel, clip=…)` (`recorte_nitido.Hojas.render`: lista de dibujo
    en caché y, con letras Type3, sin las de fuera)."""
    r = rect_tesela(nivel, tx, ty, page.rect.width, page.rect.height)
    if r is None:
        return None
    return hojas.render(page, r, escala_nivel(nivel))
