"""Bandas «en caja» con el contorno cortado y rejillas de sumidero (PURO: numpy + cv2, sin Qt).

La tubería de Phoenix SD viene como una BANDA: contorno de 1 px + bloques rellenos alternados con
cajitas blancas. La imagen de origen trae el contorno con cortes de blanco puro, así que muchas
cajitas no quedan encerradas y rellenar huecos (`imagen_huecos`) no las cierra. Aquí:

- `puentes`: dos BLOQUES seguidos (las partes gruesas del núcleo) se unen pintando solo el
  cuadrilátero entre sus caras enfrentadas, y solo con EVIDENCIA: van alineados (±`PUENTE_ANG`,
  desfase lateral ≤ `PUENTE_LADO`·ancho), con el mismo ancho (±`PUENTE_ANCHO`), el hueco a lo
  largo ≤ `PUENTE_MAX_PT` y, en las dos franjas laterales del hueco (donde corre el contorno), hay
  tinta de la FAMILIA en ≥ `PUENTE_EVIDENCIA` del largo de cada una. Una línea a trazos sin contorno
  no tiene esa tinta: sus guiones no se unen. Nada de cierres morfológicos: los bloques se hallan
  con una APERTURA (que solo quita) y lo que se pinta exige tinta a los dos lados.
- `rejillas`: una componente FINA (sin las partes gruesas) y compacta (≤ `SIMBOLO_MAX_PT`) con
  ≥ `REJILLA_LINEAS` líneas internas en cada una de dos direcciones es una rejilla = símbolo; sus
  píxeles salen de la extracción de líneas.

Determinista: todo en orden de etiquetas y de índices.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

PUENTE_MAX_PT = 6.0      # hueco entre bloques a lo largo (pt); medido en SD South: 17–22 px ≈ 4–5.3 pt
PUENTE_ANG = 10.0        # bloques alineados: ± grados
PUENTE_LADO = 0.25       # desfase lateral ≤ esto·ancho
PUENTE_ANCHO = 0.25      # mismo ancho ± esto
PUENTE_EVIDENCIA = 0.5   # tinta de familia en cada franja lateral: ≥ esto del largo del hueco
FRANJA_DENTRO = 2.0      # franja del contorno: de ancho/2 − esto …
FRANJA_FUERA = 1.5       # … a ancho/2 + esto (px)
BLOQUE_MIN_PX = 5        # apertura para hallar bloques (diámetro, px): el contorno de 1–2 px no queda
BLOQUE_AREA_MIN = 20     # bloque más chico que esto (px) no cuenta
SIMBOLO_MAX_PT = 16.0    # rejilla: lado ≤ esto (pt); medido en SD South: 5–13 pt (+ muñones pegados)
SIMBOLO_MIN_PT = 4.0     # … y ≥ esto (una letra no llega)
REJILLA_LINEAS = 2       # líneas internas mínimas en cada dirección …
REJILLA_LINEAS_MAS = 3   # … y en una de las dos al menos esto (una caja de banda abierta da 2 × 2)
REJILLA_COBERTURA = 0.5  # una fila es línea si su tinta cubre esto del ancho
REJILLA_FAMILIA_PX = 6   # familia que cuenta para una rejilla: a ≤ esto (px) de su núcleo fino
REJILLA_RALO = 0.15      # columna o fila del borde con menos tinta que esto = muñón, se recorta
REJILLA_CORTE_PT = 2.0   # columnas/filas ralas seguidas en ≥ esto (pt) separan una rejilla de lo que toca
REJILLA_GRUPO_PX = 6     # piezas finas a ≤ esto (px) van en la misma rejilla (paso de su malla)


# ── bloques y puentes ────────────────────────────────────────────────────────────────────────

def _bloques(nucleo: np.ndarray):
    """Partes gruesas del núcleo (apertura con un disco de `BLOQUE_MIN_PX`): por bloque, su
    rectángulo mínimo (centro, ejes posibles). Un eje es (u, extensión/2 a lo largo, ancho)."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BLOQUE_MIN_PX, BLOQUE_MIN_PX))
    grueso = cv2.morphologyEx(nucleo.astype(np.uint8), cv2.MORPH_OPEN, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats(grueso, connectivity=8)
    salida = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in st[i])
        if area < BLOQUE_AREA_MIN:
            continue
        sub = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        cont, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        pts = (np.vstack(cont).reshape(-1, 2) + (x, y)).astype(np.float32)
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(pts)
        rw, rh = rw + 1.0, rh + 1.0                      # de centros de píxel a bordes
        a = math.radians(ang)
        u = (math.cos(a), math.sin(a))
        v = (-u[1], u[0])
        ejes = []
        if rw >= rh:
            ejes.append((u, rw / 2, rh))
        if rh >= rw:
            ejes.append((v, rh / 2, rw))
        if max(rw, rh) < 1.2 * min(rw, rh):               # casi cuadrado: los dos ejes valen
            ejes = [(u, rw / 2, rh), (v, rh / 2, rw)]
        salida.append(((cx, cy), ejes))
    return salida


def _hay(tinta: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    xi, yi = np.floor(xs + 0.5).astype(int), np.floor(ys + 0.5).astype(int)
    ok = (xi >= 0) & (yi >= 0) & (xi < tinta.shape[1]) & (yi < tinta.shape[0])
    salida = np.zeros(xs.shape, bool)
    salida[ok] = tinta[yi[ok], xi[ok]]
    return salida


def _evidencia(tinta, p0, u, n, largo, ancho) -> bool:
    """¿Hay tinta en ≥ `PUENTE_EVIDENCIA` del largo del hueco en CADA franja lateral?"""
    if largo <= 0.5:
        return True
    t = np.arange(0.5, largo, 1.0)
    off = np.arange(ancho / 2 - FRANJA_DENTRO, ancho / 2 + FRANJA_FUERA + 1e-9, 0.5)
    for lado in (-1.0, 1.0):
        xs = p0[0] + t[:, None] * u[0] + lado * off[None, :] * n[0]
        ys = p0[1] + t[:, None] * u[1] + lado * off[None, :] * n[1]
        if float(_hay(tinta, xs, ys).any(axis=1).mean()) < PUENTE_EVIDENCIA:
            return False
    return True


def _candidato(A, B, u, ea, wa, hueco_max):
    """(hueco, desfase, cara de A, cara de B, n) si B sigue a A por su eje u (lado +u); si no None."""
    (ca, _ejes_a), (cb, ejes_b) = A, B
    rel = (cb[0] - ca[0], cb[1] - ca[1])
    a_lo = rel[0] * u[0] + rel[1] * u[1]
    lado = abs(rel[0] * u[1] - rel[1] * u[0])
    if a_lo <= 0 or lado > PUENTE_LADO * wa:
        return None
    for v, eb, wb in ejes_b:
        coseno = abs(u[0] * v[0] + u[1] * v[1])
        if coseno < math.cos(math.radians(PUENTE_ANG)) or abs(wb - wa) > PUENTE_ANCHO * wa:
            continue
        hueco = a_lo - ea - eb
        if hueco < 0 or hueco > hueco_max:
            continue
        return hueco, lado, eb, wb
    return None


def puentes(nucleo: np.ndarray, familia: np.ndarray, escala: float) -> np.ndarray:
    """Núcleo con los puentes pintados entre bloques seguidos de una banda (ver el módulo)."""
    bloques = _bloques(nucleo)
    if len(bloques) < 2:
        return nucleo
    tinta = np.asarray(nucleo, bool) | np.asarray(familia, bool)
    hueco_max = PUENTE_MAX_PT * escala
    centros = np.array([b[0] for b in bloques])
    radio = np.array([max(e[1] for e in b[1]) for b in bloques])
    mejor = {}                                       # (bloque, lado) → (hueco, desfase, otro, datos)
    for i, A in enumerate(bloques):
        d = np.hypot(centros[:, 0] - centros[i, 0], centros[:, 1] - centros[i, 1])
        cerca = np.nonzero(d <= radio[i] + radio + hueco_max)[0]
        for e, (u, ea, wa) in enumerate(A[1]):
            for s in (1.0, -1.0):
                us = (u[0] * s, u[1] * s)
                for j in cerca:
                    j = int(j)
                    if j == i:
                        continue
                    c = _candidato(A, bloques[j], us, ea, wa, hueco_max)
                    if c is None:
                        continue
                    hueco, lado, eb, wb = c
                    n = (-us[1], us[0])
                    p0 = (A[0][0] + us[0] * ea, A[0][1] + us[1] * ea)
                    if not _evidencia(tinta, p0, us, n, hueco, (wa + wb) / 2):
                        continue
                    clave = (i, e, s)                         # el mejor por cada lado
                    nuevo = (hueco, lado, j, (us, ea, wa, eb, wb))
                    if clave not in mejor or nuevo[:3] < mejor[clave][:3]:
                        mejor[clave] = nuevo
    elegido = {}
    for (i, _e, _s), (_hueco, _lado, j, datos) in mejor.items():
        elegido.setdefault(i, {})[j] = datos
    salida = np.asarray(nucleo, bool).copy()
    lienzo = np.zeros(salida.shape, np.uint8)
    for i in sorted(elegido):
        for j in sorted(elegido[i]):
            if i > j and j in elegido and i in elegido[j]:
                continue                               # el par ya se pintó desde j
            if j not in elegido or i not in elegido[j]:
                continue                               # sin acuerdo de los dos lados no hay puente
            us, ea, wa, eb, wb = elegido[i][j]
            n = (-us[1], us[0])
            ca, cb = bloques[i][0], bloques[j][0]
            fa = (ca[0] + us[0] * ea, ca[1] + us[1] * ea)
            fb = (cb[0] - us[0] * eb, cb[1] - us[1] * eb)
            ha, hb = (wa - 1) / 2, (wb - 1) / 2         # de centro a centro de los píxeles del borde:
            pts = [(fa[0] + n[0] * ha, fa[1] + n[1] * ha),   # el puente no sale del ancho del bloque
                   (fb[0] + n[0] * hb, fb[1] + n[1] * hb),
                   (fb[0] - n[0] * hb, fb[1] - n[1] * hb),
                   (fa[0] - n[0] * ha, fa[1] - n[1] * ha)]
            q = np.round(np.array(pts) * 16).astype(np.int32)      # 4 bits de subpíxel
            cv2.fillConvexPoly(lienzo, q, 1, cv2.LINE_8, 4)
    return salida | (lienzo > 0)


# ── rejillas ─────────────────────────────────────────────────────────────────────────────────

def _lineas_internas(sub: np.ndarray) -> int:
    """Líneas internas (filas seguidas con tinta ≥ `REJILLA_COBERTURA` del ancho), sin las que
    tocan el primer o el último par de filas (el marco)."""
    if sub.shape[0] < 5 or sub.shape[1] < 3:
        return 0
    filas = sub.mean(axis=1) >= REJILLA_COBERTURA
    cuenta, i, h = 0, 0, len(filas)
    while i < h:
        if filas[i]:
            j = i
            while j + 1 < h and filas[j + 1]:
                j += 1
            if i > 1 and j < h - 2:
                cuenta += 1
            i = j + 1
        else:
            i += 1
    return cuenta


def _recortar(sub: np.ndarray):
    """Sin los bordes ralos (muñones de la banda o de una trama pegados a la rejilla): se quitan,
    de afuera hacia adentro, las columnas y filas con tinta en menos de `REJILLA_RALO` de su largo.
    Devuelve (recorte, fila inicial, columna inicial)."""
    y0 = x0 = 0
    for _ in range(2):
        col = sub.mean(axis=0) >= REJILLA_RALO
        fil = sub.mean(axis=1) >= REJILLA_RALO
        if not col.any() or not fil.any():
            return sub[:0, :0], y0, x0
        c, f = np.nonzero(col)[0], np.nonzero(fil)[0]
        sub = sub[f[0]:f[-1] + 1, c[0]:c[-1] + 1]
        y0, x0 = y0 + int(f[0]), x0 + int(c[0])
    return sub, y0, x0


def _partir(sub: np.ndarray, oy: int, ox: int, hi: float, corte: float):
    """Corte X–Y: separa lo que va junto en un grupo (rejilla + el contorno fino de la banda que la
    toca + otra rejilla) por las columnas y filas RALAS (tinta < max(3, `REJILLA_RALO`·min(lado,
    `hi`))) seguidas en ≥ `corte` px (entre las líneas de una rejilla hay menos). Devuelve las hojas [(sub, fila, columna)] recortadas a su tinta."""
    ys, xs = np.nonzero(sub)
    if not len(xs):
        return []
    sub = sub[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    oy, ox = oy + int(ys.min()), ox + int(xs.min())
    for eje in (0, 1):
        cuenta = sub.sum(axis=eje)
        denso = cuenta >= max(3.0, REJILLA_RALO * min(sub.shape[eje], hi))
        tramos = []
        for k in np.nonzero(denso)[0].tolist():             # densos unidos sobre huecos < corte
            if tramos and k - tramos[-1][1] <= corte:
                tramos[-1][1] = k
            else:
                tramos.append([k, k])
        if len(tramos) > 1 or (tramos and (tramos[0][0] >= corte
                                           or tramos[-1][1] < len(denso) - corte)):
            salida = []
            for a, b in tramos:
                if eje == 0:
                    salida += _partir(sub[:, a:b + 1], oy, ox + a, hi, corte)
                else:
                    salida += _partir(sub[a:b + 1, :], oy + a, ox, hi, corte)
            return salida
    return [(sub, oy, ox)]


def _derecha(sub: np.ndarray, ang: float) -> np.ndarray:
    """La componente girada a su rectángulo mínimo (vecino más cercano), recortada a su tinta."""
    a = ang % 90.0
    if min(a, 90.0 - a) <= 1.0:
        return sub
    h, w = sub.shape
    lado = int(math.ceil(math.hypot(h, w))) + 2
    m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    m[:, 2] += ((lado - w) / 2, (lado - h) / 2)
    g = cv2.warpAffine(sub.astype(np.uint8), m, (lado, lado), flags=cv2.INTER_NEAREST) > 0
    ys, xs = np.nonzero(g)
    return g[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(xs) else g


def rejillas(nucleo: np.ndarray, familia: np.ndarray, escala: float, ruido: int):
    """Rejillas de sumidero: componentes FINAS (núcleo sin las partes gruesas y su borde, más la
    familia pegada a él) compactas, de lado entre `SIMBOLO_MIN_PT` y `SIMBOLO_MAX_PT`, con ≥ `REJILLA_LINEAS`
    líneas internas en cada dirección. Devuelve [(x0, y0, sub, caja)]: sub = la máscara de la
    rejilla desde (x0, y0), que sale de las líneas; caja = (xa, ya, xb, yb) de la rejilla sin los
    muñones pegados (el símbolo)."""
    nuc = np.asarray(nucleo, np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BLOQUE_MIN_PX, BLOQUE_MIN_PX))
    grueso = cv2.morphologyEx(nuc, cv2.MORPH_OPEN, k)
    grueso = cv2.dilate(grueso, np.ones((3, 3), np.uint8))       # con su borde de antialias
    nuc_fino = (nuc > 0) & (grueso == 0)
    # De la familia solo lo que queda a ≤ REJILLA_FAMILIA_PX de un trazo fino del núcleo (las
    # líneas claras de la rejilla); una trama de otro color que toca la rejilla queda en un muñón.
    lado = 2 * REJILLA_FAMILIA_PX + 1
    cerca = cv2.dilate(nuc_fino.astype(np.uint8), np.ones((lado, lado), np.uint8)) > 0
    fino = nuc_fino | (np.asarray(familia, bool) & cerca & (grueso == 0))
    # Las líneas de una rejilla vienen cortadas: se AGRUPAN las piezas a ≤ REJILLA_GRUPO_PX (solo para
    # decidir qué va junto; los píxeles de la rejilla son los de `fino`, no se pinta nada).
    junto = cv2.dilate(fino.astype(np.uint8), np.ones((REJILLA_GRUPO_PX + 1,) * 2, np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(junto, connectivity=8)
    lo, hi = SIMBOLO_MIN_PT * escala, SIMBOLO_MAX_PT * escala
    salida = []
    for i in range(1, n):
        x, y, w, h, _a = (int(v) for v in st[i])
        grupo = (lab[y:y + h, x:x + w] == i) & fino[y:y + h, x:x + w]
        if int(grupo.sum()) < ruido:
            continue
        for sub, oy, ox in _partir(grupo, 0, 0, hi, REJILLA_CORTE_PT * escala):
            if int(sub.sum()) < ruido or not (lo <= sub.shape[1] <= hi and lo <= sub.shape[0] <= hi):
                continue
            xs0, ys0 = x + ox, y + oy
            ys, xs = np.nonzero(sub)
            ang = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))[2]
            # En el giro del rectángulo mínimo o derecha (un muñón pegado tuerce el rectángulo)
            derecha = _recortar(sub)
            for d, fy, fx in (_recortar(_derecha(sub, ang)), derecha):
                a, b = _lineas_internas(d), _lineas_internas(d.T)
                if min(d.shape) >= lo and min(a, b) >= REJILLA_LINEAS and max(a, b) >= REJILLA_LINEAS_MAS:
                    d, fy, fx = derecha if min(derecha[0].shape) >= lo else (sub, 0, 0)
                    caja = (xs0 + fx, ys0 + fy, xs0 + fx + d.shape[1] - 1, ys0 + fy + d.shape[0] - 1)
                    salida.append((xs0, ys0, sub, caja))
                    break
    return salida
