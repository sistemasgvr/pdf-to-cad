"""Paleta de colores de una red que viene como IMAGEN dentro de un PDF (PURO: numpy + cv2, sin Qt).

Recibe las imágenes RGB que da `imagen_solo.pintar` (solo imágenes, fondo blanco) y descubre
qué colores «gráficos» trae la hoja, sin ningún color fijo:

- imagen INDEXADA (paleta del PDF, Phoenix SD): los colores son exactos; se cuentan tal cual.
- imagen RGB: el antialias y la compresión mezclan los tonos; se agrupan con k-means en Lab y
  se redondean a múltiplos de 32 (`normalizar`).
- imagen FOTOGRÁFICA (ortofoto, logo con degradado): no da colores (lista vacía).

El antialias se decide por VECINDAD, no por tono: un color es la rampa de otro si va sobre la
recta «otro → blanco» y la mayoría de sus píxeles tocan a ese otro (p. ej. los grises de los
bordes del texto negro). Un tono suelto, aunque sea el 50 % exacto de otro (la trama de
Phoenix #80A6D4 frente a #004DA8), queda como color propio.

Todo se calcula sobre el HISTOGRAMA de colores distintos (no sobre los píxeles): una hoja de
35 millones de píxeles tiene unos miles de colores. Resultado determinista (semilla fija).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

PIXELES_MIN = 200            # un color con menos píxeles es ruido / antialias suelto
N_PRINCIPALES = 12           # grupos que, en una hoja gráfica, cubren casi todo lo que no es fondo
CUBRE_MIN = 0.85             # fracción mínima de lo no-fondo que deben cubrir esos grupos
MUESTRA_MAX = 200_000        # píxeles de muestra para el k-means
K_COLORES = 8                # centros del k-means (hojas RGB)
UNIR_DELTA_E = 10.0          # centros a menos de esto son el mismo color
DELTA_E = 12.0               # un píxel es de un color si queda a ≤ esto de su centro
FONDO_L = 92.0               # fondo = claro (L* > 92) …
FONDO_CROMA = 8.0            # … y casi sin color
FONDO_DOMINANTE = 0.60       # o el color que cubre más de esto de la imagen
RAMPA_RGB = 20.0             # un color a ≤ esto de una recta entre colores principales es antialias
ANTIALIAS_RGB = 30.0         # un color a ≤ esto de la recta padre→blanco puede ser su rampa
NUCLEO_MIN = 0.60            # los grupos principales deben cubrir al menos esto para que cuenten las rampas
TOCA_MIN = 0.60              # fracción de sus píxeles que debe tocar al color padre
FAMILIA_A = 0.85             # familia: mezcla con el blanco de como mucho esto …
FAMILIA_RESIDUO = 25.0       # … y a ≤ esto (RGB) del segmento color → blanco
FAMILIA_OTRO_MIN = 0.1       # otro color de la paleta con ≥ esto de los píxeles del color no es su familia
FAMILIA_MAS_OSCURO = 0.05    # … salvo donde toca un tono de la familia más oscuro que él
TOL_EXACTO = 2               # imagen indexada: igualdad ±2 por canal
PASO_NORMAL = 32
SEMILLA = 12345
_BLANCO = 0xFFFFFF


@dataclass(frozen=True)
class ColorImagen:
    rgb: tuple[int, int, int]
    pixeles: int
    exacto: bool
    absorbidos: tuple = ()      # colores de antialias que `paleta` sumó a éste (bordes, rejillas finas)


# ── histograma de colores ────────────────────────────────────────────────────────────────────

def _empaquetar(img: np.ndarray) -> np.ndarray:
    """Cada píxel como r<<16 | g<<8 | b (uint32). Se arman los 4 bytes (b, g, r, 0) y se leen como un entero de
    32 bits (little-endian): los mismos valores que con desplazamientos, ~4.6× más rápido (2026-11-20, monitor)."""
    h, w = img.shape[:2]
    out = np.zeros((h, w, 4), np.uint8)
    out[..., 0] = img[..., 2]
    out[..., 1] = img[..., 1]
    out[..., 2] = img[..., 0]
    return out.view("<u4")[..., 0]


def _desempaquetar(claves: np.ndarray) -> np.ndarray:
    k = claves.astype(np.uint32)
    return np.stack([(k >> 16) & 255, (k >> 8) & 255, k & 255], axis=1).astype(np.uint8)


def _histograma(imgs: Sequence[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """(colores (n,3) uint8, cuenta (n,) int64) de los colores distintos de todas las imágenes.

    El blanco puro (casi toda la hoja) se cuenta aparte y el resto se ordena: sin tablas de 2^24."""
    return _histograma_px(_empaquetar(img) for img in imgs)


def _histograma_px(pxs) -> tuple[np.ndarray, np.ndarray]:
    """`_histograma` de imágenes ya empaquetadas (`_empaquetar`)."""
    blancos = 0
    claves: list[np.ndarray] = []
    cuentas: list[np.ndarray] = []
    for px in pxs:
        k = px.ravel()
        hay = k != _BLANCO
        blancos += int(k.size - hay.sum())
        u, c = np.unique(k[hay], return_counts=True)
        claves.append(u)
        cuentas.append(c.astype(np.int64))
    if blancos:
        claves.append(np.array([_BLANCO], np.uint32))
        cuentas.append(np.array([blancos], np.int64))
    if not claves:
        return np.zeros((0, 3), np.uint8), np.zeros(0, np.int64)
    k = np.concatenate(claves)
    c = np.concatenate(cuentas)
    u, inv = np.unique(k, return_inverse=True)
    return _desempaquetar(u), np.bincount(inv, weights=c).astype(np.int64)


_MISMA: dict = {}


@contextlib.contextmanager
def misma_imagen(img: np.ndarray):
    """Mientras dura el bloque, `mascara` y `familia` de ESTE mismo objeto `img` (que nadie debe
    modificar dentro del bloque) reusan su empaquetado e histograma: con varios colores sobre la
    misma tesela eran ~4 pasadas enteras por color (una hoja de Phoenix SD, ~6 s por color). Mismo
    resultado; fuera del bloque, todo como siempre. No anidable (el de adentro reemplaza)."""
    _MISMA.clear()
    _MISMA.update(img=img, px=_empaquetar(img[..., :3]), hist=None)
    try:
        yield
    finally:
        _MISMA.clear()


def _buscar(tabla: np.ndarray, px: np.ndarray) -> np.ndarray:
    """`tabla[px]` (el mismo arreglo). Dentro de `misma_imagen`, si el blanco no está en la tabla, solo se buscan
    los píxeles que no son blanco: una tesela de un mapa con la red en imagen es casi toda blanca y la familia de
    cada tono se buscaba en sus 37 millones de píxeles (~0.2 s × 18 tonos × 4 teselas por hoja, 2026-11-19)."""
    if _MISMA.get("px") is not px or tabla[_BLANCO]:
        return tabla[px]
    if _MISMA.get("nb") is None:
        plano = px.reshape(-1)
        _MISMA["nb"] = np.flatnonzero(plano != _BLANCO)
        _MISMA["nb_px"] = plano[_MISMA["nb"]]
    out = np.zeros(px.shape, tabla.dtype)
    out.reshape(-1)[_MISMA["nb"]] = tabla[_MISMA["nb_px"]]
    return out


def _donde(tabla: np.ndarray, px: np.ndarray):
    """`np.nonzero(tabla[px])` (mismas filas y columnas, mismo orden), sin recorrer el blanco (ver `_buscar`)."""
    if _MISMA.get("px") is not px or tabla[_BLANCO] or _MISMA.get("nb") is None:
        return np.nonzero(_buscar(tabla, px))
    i = _MISMA["nb"][tabla[_MISMA["nb_px"]]]
    return np.divmod(i, px.shape[1])


def _igual_a(cols: np.ndarray, rgb) -> np.ndarray:
    """¿Cada color de `cols` es `rgb` (±`TOL_EXACTO`)? Dentro de `misma_imagen` se calcula una vez por color."""
    memo = _MISMA.setdefault("igual", {}) if _MISMA.get("img") is not None else None
    if memo is not None and tuple(rgb) in memo and memo[tuple(rgb)][0] is cols:
        return memo[tuple(rgb)][1]
    r = np.abs(cols.astype(np.int16) - np.array(rgb, np.int16)).max(axis=1) <= TOL_EXACTO
    if memo is not None:
        memo[tuple(rgb)] = (cols, r)
    return r


def _px_hist(img: np.ndarray):
    """(empaquetado, histograma) de `img` (memorizados dentro de `misma_imagen`)."""
    if _MISMA.get("img") is img:
        if _MISMA["hist"] is None:
            _MISMA["hist"] = _histograma_px([_MISMA["px"]])
        return _MISMA["px"], _MISMA["hist"]
    px = _empaquetar(img[..., :3])
    return px, _histograma_px([px])


def _lab(cols: np.ndarray) -> np.ndarray:
    """Lab (L 0–100) de colores (n,3) uint8, float32."""
    rgb = (cols.reshape(-1, 1, 3).astype(np.float32) / 255.0)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab).reshape(-1, 3)


def _es_fondo(cols: np.ndarray, cuenta: np.ndarray, lab: np.ndarray) -> np.ndarray:
    """Máscara de los colores que son fondo: claros y sin croma, o el dominante (>60 %)."""
    croma = np.hypot(lab[:, 1], lab[:, 2])
    fondo = (lab[:, 0] > FONDO_L) & (croma < FONDO_CROMA)
    total = int(cuenta.sum())
    if total:
        i = int(np.argmax(cuenta))
        if cuenta[i] > FONDO_DOMINANTE * total:
            fondo[i] = True
    return fondo


def _distancia_a_segmentos(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distancia mínima de cada punto p (n,3) a los segmentos a[i]→b[i] (m,3)."""
    mejor = np.full(len(p), np.inf)
    for i in range(len(a)):
        d = b[i] - a[i]
        n2 = float(d @ d)
        t = np.zeros(len(p)) if n2 == 0 else np.clip((p - a[i]) @ d / n2, 0.0, 1.0)
        mejor = np.minimum(mejor, np.linalg.norm(p - (a[i] + t[:, None] * d), axis=1))
    return mejor


def _foto(cols: np.ndarray, cuenta: np.ndarray) -> bool:
    """Los N_PRINCIPALES grupos de color (cuantizados a 8) NO explican lo que se pasa.

    Lo que sobra y queda sobre una recta entre dos colores principales (o el blanco) es antialias
    o rampa de un trazo y se cuenta como explicado; una foto deja una nube fuera de esas rectas."""
    total = int(cuenta.sum())
    if total == 0:
        return False
    q = cols.astype(np.int32) >> 3
    clave = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
    pesos = np.bincount(clave, weights=cuenta, minlength=32768)
    top = np.argsort(-pesos, kind="stable")[:N_PRINCIPALES]
    en_top = np.isin(clave, top)
    cubierto = float(cuenta[en_top].sum())
    resto = ~en_top
    if cubierto / total >= CUBRE_MIN or not resto.any():
        return cubierto / total < CUBRE_MIN
    if cubierto / total < NUCLEO_MIN:         # sin un núcleo de colores firmes, las «rampas» no salvan nada
        return True
    cen = np.array([np.average(cols[clave == g].astype(float), axis=0, weights=cuenta[clave == g])
                    for g in top if pesos[g] > 0] + [[255.0, 255.0, 255.0]])
    ia, ib = np.triu_indices(len(cen), 1)
    p = cols[resto].astype(float)
    rampa = np.zeros(len(p), bool)
    for ini in range(0, len(p), 50_000):
        trozo = p[ini:ini + 50_000]
        rampa[ini:ini + 50_000] = _distancia_a_segmentos(trozo, cen[ia], cen[ib]) <= RAMPA_RGB
    cubierto += float(cuenta[resto][rampa].sum())
    return cubierto / total < CUBRE_MIN


def es_fotografica(img: np.ndarray) -> bool:
    """¿La imagen es una foto / degradado? (los 12 grupos de color mayores no explican el resto)."""
    cols, cuenta = _histograma([img])
    lab = _lab(cols)
    fondo = _es_fondo(cols, cuenta, lab)
    return _foto(cols[~fondo], cuenta[~fondo])


# ── paleta ───────────────────────────────────────────────────────────────────────────────────

def normalizar(rgb, exacto: bool) -> tuple[int, int, int]:
    """Exacto: tal cual. Si no, múltiplos de 32 con tope 255 (nombre estable de la capa)."""
    if exacto:
        return (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return tuple(int(min(255, round(float(v) / PASO_NORMAL) * PASO_NORMAL)) for v in rgb)


def _muestra(cols: np.ndarray, cuenta: np.ndarray) -> np.ndarray:
    """Hasta MUESTRA_MAX píxeles repartidos como el histograma (determinista)."""
    total = int(cuenta.sum())
    if total <= MUESTRA_MAX:
        rep = cuenta
    else:
        rep = np.maximum(1, np.round(cuenta * (MUESTRA_MAX / total))).astype(np.int64)
    return np.repeat(cols, rep, axis=0)


def _centros_rgb(cols: np.ndarray, cuenta: np.ndarray, lab: np.ndarray) -> np.ndarray:
    """Centros (m,3) float32 en Lab: k-means sobre la muestra y unión de los que quedan a ΔE<10."""
    muestra = _lab(_muestra(cols, cuenta))
    k = min(K_COLORES, len(cols))
    cv2.setRNGSeed(SEMILLA)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, _, centros = cv2.kmeans(muestra, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    centros = centros.astype(np.float32)
    grupos: list[list[np.ndarray]] = []
    for c in centros:
        for g in grupos:
            if np.linalg.norm(np.mean(g, axis=0) - c) < UNIR_DELTA_E:
                g.append(c)
                break
        else:
            grupos.append([c])
    return np.array([np.mean(g, axis=0) for g in grupos], np.float32)


def _lab_a_rgb(lab: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(lab.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_Lab2RGB).reshape(-1, 3)
    return np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)


def _vecinos(imgs: Sequence[np.ndarray], tabla: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(etiqueta (N,), etiquetas de sus 8 vecinos (N,8)) de los píxeles con etiqueta >= 0."""
    labs: list[np.ndarray] = []
    nbs: list[np.ndarray] = []
    for img in imgs:
        etiquetas = tabla[_empaquetar(img)]
        ancho = etiquetas.shape[1] + 2
        plano = np.pad(etiquetas, 1, constant_values=-1).ravel()
        idx = np.flatnonzero(plano >= 0)
        offs = np.array([-ancho - 1, -ancho, -ancho + 1, -1, 1, ancho - 1, ancho, ancho + 1])
        labs.append(plano[idx])
        nbs.append(plano[idx[:, None] + offs[None, :]])
    if not labs:
        return np.zeros(0, np.int16), np.zeros((0, 8), np.int16)
    return np.concatenate(labs), np.concatenate(nbs)


def _en_recta_al_blanco(hijo: np.ndarray, padre: np.ndarray) -> bool:
    d = 255.0 - padre
    n2 = float(d @ d)
    if n2 == 0:
        return False
    t = float((hijo - padre) @ d) / n2
    return 0.0 < t < 1.0 and float(np.linalg.norm(padre + t * d - hijo)) <= ANTIALIAS_RGB


def _absorber_antialias(imgs: Sequence[np.ndarray], tabla: np.ndarray, rgb: np.ndarray,
                        recta: bool = True) -> np.ndarray:
    """Raíz de cada etiqueta: un color es ANTIALIAS de otro si va sobre la recta padre→blanco y
    ≥60 % de sus píxeles tocan (3×3) píxeles del padre (o de lo ya absorbido por él).
    `recta=False` (centros de k-means, que mezclan varios tonos claros) no exige la recta."""
    n = len(rgb)
    grupo = np.arange(n)
    lab, nb = _vecinos(imgs, tabla)
    if lab.size == 0:
        return grupo
    orden_px = np.argsort(lab, kind="stable")
    ini = np.searchsorted(lab[orden_px], np.arange(n + 1))
    g = np.append(np.arange(n), -1).astype(np.int64)          # g[-1] = -1: «sin vecino»
    raices: list[int] = []
    # del más lejano al blanco (padres) al más cercano (rampas)
    for c in np.argsort(-np.linalg.norm(255.0 - rgb, axis=1), kind="stable"):
        sel = orden_px[ini[c]:ini[c + 1]]
        mejor, frac_mejor = -1, TOCA_MIN
        if len(sel):
            nbg = g[nb[sel]]
            padres = [r for r in raices
                      if (_en_recta_al_blanco(rgb[c], rgb[r]) if recta
                          else np.linalg.norm(255.0 - rgb[r]) >= np.linalg.norm(255.0 - rgb[c]) + 10.0)]
            if padres and not recta:
                # centro mezclado de varios tonos claros: basta que toque a ALGÚN padre
                if float(np.isin(nbg, padres).any(axis=1).mean()) >= TOCA_MIN:
                    mejor = max(padres, key=lambda r: float((nbg == r).any(axis=1).mean()))
                    frac_mejor = 1.0
            else:
                for r in padres:
                    frac = float((nbg == r).any(axis=1).mean())
                    if frac >= frac_mejor:
                        mejor, frac_mejor = r, frac
        if mejor >= 0:
            grupo[c] = mejor
            g[c] = mejor
        else:
            raices.append(int(c))
    return grupo


def _mezcla(color, otro):
    """Fracción de blanco a si `otro` cae sobre el segmento color → blanco (desvío ≤
    `FAMILIA_RESIDUO`); None si no."""
    c = np.array(color, float)
    d = 255.0 - c
    n2 = float(d @ d)
    if n2 == 0:
        return None
    rel = np.array(otro, float) - c
    a = float(rel @ d) / n2
    return a if 0.0 <= a <= 1.0 and float(np.linalg.norm(rel - a * d)) <= FAMILIA_RESIDUO else None


def paleta(imgs: Sequence[np.ndarray], indexada: bool) -> list[ColorImagen]:
    """Colores gráficos de las imágenes, de más a menos píxeles. [] si son fotográficas o no hay."""
    if not imgs:
        return []
    cols, cuenta = _histograma(imgs)
    lab = _lab(cols)
    fondo = _es_fondo(cols, cuenta, lab)
    cols, cuenta, lab = cols[~fondo], cuenta[~fondo], lab[~fondo]
    if len(cols) == 0 or _foto(cols, cuenta):
        return []
    if indexada:
        sel = cuenta >= PIXELES_MIN
        cand_rgb, cand_pix = cols[sel], cuenta[sel]
        etiqueta = np.arange(len(cand_rgb))
        claves = _empaquetar(cand_rgb[None, :, :])[0] if len(cand_rgb) else np.zeros(0, np.uint32)
    else:
        centros = _centros_rgb(cols, cuenta, lab)
        d = np.linalg.norm(lab[:, None, :] - centros[None, :, :], axis=2)
        cerca = d.argmin(axis=1)
        ok = d[np.arange(len(lab)), cerca] <= DELTA_E
        cand_pix = np.bincount(cerca[ok], weights=cuenta[ok], minlength=len(centros)).astype(np.int64)
        cand_rgb = _lab_a_rgb(centros)
        # para la vecindad cada color va a su centro más cercano (el antialias intermedio no corta la cadena)
        etiqueta = cerca
        claves = _empaquetar(cols[None, :, :])[0]
    if len(cand_rgb) == 0:
        return []
    tabla = np.full(1 << 24, -1, np.int16)
    tabla[claves] = etiqueta
    grupo = _absorber_antialias(imgs, tabla, cand_rgb.astype(float), recta=indexada)
    suma = np.bincount(grupo, weights=cand_pix, minlength=len(cand_rgb)).astype(np.int64)
    salida: dict[tuple[int, int, int], int] = {}
    absorbidos: dict[tuple[int, int, int], list] = {}
    for i in np.argsort(-suma, kind="stable"):
        if grupo[i] != i or suma[i] < PIXELES_MIN:
            continue
        rgb = normalizar(cand_rgb[i], indexada)
        salida[rgb] = salida.get(rgb, 0) + int(suma[i])
        hijos = absorbidos.setdefault(rgb, [])
        for j in np.nonzero(grupo == i)[0]:
            hijo = tuple(int(v) for v in cand_rgb[j])
            if int(j) != int(i) and hijo != rgb and hijo not in hijos:
                hijos.append(hijo)
    ordenados = sorted(salida.items(), key=lambda kv: -kv[1])
    raices = np.array([rgb for rgb, _n in ordenados], np.int16)
    cuenta = dict(ordenados)

    def ajeno(hijo, propio):
        """Un absorbido no es de `propio` si es (±2) otro color de la paleta, o si es tan claro
        como otro color GRANDE que cae sobre su rampa (la trama #80A6D4 = 50 % del azul): de ahí
        para arriba los tonos pueden ser de cualquiera de los dos y solo cuentan como familia."""
        cerca = np.abs(raices - np.array(hijo, np.int16)).max(axis=1) <= TOL_EXACTO
        if cerca.any() and any(tuple(r) != propio for r in raices[cerca].tolist()):
            return True
        a_hijo = _mezcla(propio, hijo)
        return any(a_hijo is not None and r != propio and cuenta[r] >= FAMILIA_OTRO_MIN * cuenta[propio]
                   and (a_r := _mezcla(propio, r)) is not None and a_hijo >= a_r - FAMILIA_MAS_OSCURO
                   for r in cuenta)

    return [ColorImagen(rgb, n, indexada,
                        tuple(sorted(h for h in absorbidos[rgb] if not ajeno(h, rgb))))
            for rgb, n in ordenados]


def mascara(img: np.ndarray, color: ColorImagen, delta_e: float = DELTA_E) -> np.ndarray:
    """Píxeles de `img` que son de `color` o de sus colores `absorbidos` (antialias): exacto ±2 por
    canal; si no, ΔE76 en Lab ≤ delta_e."""
    todos = [color.rgb] + [tuple(c) for c in color.absorbidos]
    px, (cols, _) = _px_hist(img)                      # se decide por color distinto, no por píxel
    bueno = np.zeros(len(cols), bool)
    if color.exacto:
        ci = cols.astype(np.int16)
        for c in todos:
            bueno |= np.abs(ci - np.array(c, np.int16)).max(axis=1) <= TOL_EXACTO
    else:
        lab_cols = _lab(cols)
        for centro in _lab(np.array(todos, np.uint8)):
            bueno |= np.linalg.norm(lab_cols - centro, axis=1) <= delta_e
    tabla = np.zeros(1 << 24, bool)
    if bueno.any():
        tabla[_empaquetar(cols[bueno][None, :, :])[0]] = True
    return _buscar(tabla, px)


def familia(img: np.ndarray, color: ColorImagen, otros=()) -> np.ndarray:
    """FAMILIA de `color`: píxeles sobre el segmento RGB color → blanco (mezcla a ≤ `FAMILIA_A`,
    desvío ≤ `FAMILIA_RESIDUO`), es decir, su antialias aunque la paleta no lo haya absorbido.

    Quedan FUERA los píxeles (±2) de otro color GRANDE de la paleta (≥ `FAMILIA_OTRO_MIN` de los
    píxeles de `color`): la trama #80A6D4 es el 50 % exacto del azul y no es su borde. Los tonos
    chicos de la paleta (rampas que no se absorbieron) sí son familia. Excepción: un píxel de ese
    otro color que toca un píxel de familia MÁS OSCURO (más cerca de `color`) es borde del trazo
    (la rejilla fina del sumidero pasa por el 50 % exacto); la trama solo toca tonos más claros.
    La usa `imagen_trazos` para cerrar contornos finos (bandas, rejillas)."""
    px, (cols, _) = _px_hist(img)
    c = np.array(color.rgb, float)
    d = 255.0 - c
    n2 = float(d @ d)
    if n2 == 0 or len(cols) == 0:
        return np.zeros(img.shape[:2], bool)
    rel = cols.astype(float) - c
    a = rel @ d / n2
    resto = np.linalg.norm(rel - a[:, None] * d[None, :], axis=1)
    bueno = (a >= -0.05) & (a <= FAMILIA_A) & (resto <= FAMILIA_RESIDUO)
    ajeno = np.zeros(len(cols), bool)
    for o in otros:
        if tuple(o.rgb) != tuple(color.rgb) and o.pixeles >= FAMILIA_OTRO_MIN * color.pixeles:
            ajeno |= _igual_a(cols, o.rgb)
    claves = _empaquetar(cols[None, :, :])[0]
    tabla = np.zeros(1 << 24, bool)
    tabla[claves[bueno & ~ajeno]] = True
    salida = _buscar(tabla, px)
    candidatos = bueno & ajeno
    if candidatos.any():
        t_aj = np.zeros(1 << 24, bool)
        t_aj[claves[candidatos]] = True
        t_a = np.full(1 << 24, np.inf, np.float32)
        t_a[claves[bueno]] = a[bueno]
        ys, xs = _donde(t_aj, px)
        a_propio = t_a[px[ys, xs]]
        borde = np.zeros(len(ys), bool)
        for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
            yy, xx = ys + dy, xs + dx
            ok = (yy >= 0) & (xx >= 0) & (yy < px.shape[0]) & (xx < px.shape[1])
            v = px[np.where(ok, yy, 0), np.where(ok, xx, 0)]
            borde |= ok & tabla[v] & (t_a[v] < a_propio - FAMILIA_MAS_OSCURO)
        salida[ys[borde], xs[borde]] = True
    return salida


def indexada(page) -> bool:
    """¿Todas las imágenes útiles de la hoja son indexadas (`cs-name` «Indexed…»)?"""
    from hoja import imagen_solo
    imgs = imagen_solo.imagenes_utiles(page)
    return bool(imgs) and all(str(i.get("cs-name", "")).startswith("Indexed") for i in imgs)
