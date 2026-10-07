"""Accesorios de conexión que Civil 3D pondrá en las redes a PRESIÓN (PURO: sin Qt).

Para cada punto donde el plugin coloca un accesorio sólido (codo, Tee, Wye,
cruz) devuelve su TIPO y su ÁNGULO, con las mismas reglas que el plugin:

  - Solo redes a presión (agua, gas): en gravedad/conduit hay buzones o curvas.
  - Se juntan los EXTREMOS DE TRAMO de una misma red (nombre de red o, sin él,
    la capa) a ≤ 0.5 ft (`ProcesarJunturasPresion`); cada utilidad promedia su
    cota ahí y solo se unen las que quedan a ≤ 0.10 ft (misma regla que
    `model_ops.junturas_excedidas`). Un extremo que muere a MITAD de un tramo
    de la misma red y cota parte ese tramo (`PartirTramosEnTes`): es una T.
  - 2 tramos → codo si giran más de 1° (si no, unión recta: sin accesorio),
    3 → Tee si hay tronco recto (≥160°) y el ramal va a 90° ±20°, si no Wye;
    4 → cruz; 5+ → nada (lo avisa la alerta roja de `junturas_excedidas`).
  - ANTES de juntar nada, dos codos de la misma utilidad con un tramo más corto
    que `largo_min_entre_codos_ft` se funden en UNO en el cruce de las rectas
    vecinas (`FusionarCodosSeguidos`, que corre antes de crear la red).

Ángulo de cada accesorio (el que se compara con las normativas):
  codo = DEFLEXIÓN sobre el EJE: se prolonga el eje del lado recto y se mide cuánto
  se aparta el eje del otro lado (0° = recta; un codo AWWA de 45° da 45°). Así lo
  mide el ingeniero civil y así se compran (2026-10-07; del 2026-10-01 al 06 fue el
  ángulo ENTRE tuberías, 135°). "giro" = el mismo valor (lo usa el plugin). Tee/Wye = ángulo AGUDO entre el ramal y
  el tronco; cruz = ángulo agudo entre sus dos líneas.
"""
from __future__ import annotations

import math

from model import network_kind

TOL_UNION_FT = 0.5          # radio de la juntura (como el plugin)
TOL_COTA_FT = 0.10          # misma cota
GIRO_CODO_MIN_DEG = 1.0     # menos es una unión recta
GIRO_FUSION_MIN_DEG = 5.0   # FusionarCodosSeguidos solo funde codos de ≥ 5°
TRONCO_MIN_DEG = 160.0      # dos salidas «colineales»
RAMAL_TEE_MIN_DEG = 70.0    # ramal a 90° ±20° → Tee

TIPOS = ("codo", "tee", "wye", "cruz")


def red_de(pipe):
    """Red de Civil 3D de la utilidad: nombre de red o, si no hay, la capa."""
    return (pipe.get("name") or "").strip() or (pipe.get("layer") or "")


def largo_min_entre_codos_ft(diam_in):
    """3 diámetros, mínimo 1 ft (`LargoMinEntreCodosFt` del plugin)."""
    try:
        d = float(diam_in or 0) / 12.0
    except (TypeError, ValueError):
        d = 0.0
    return max(1.0, 3.0 * d)


def _ang(dx, dy):
    return math.atan2(dy, dx)


def _entre(a, b):
    """Ángulo (0–180°) entre dos direcciones en radianes."""
    return math.degrees(abs((a - b + math.pi) % (2 * math.pi) - math.pi))


def _agudo(a, b):
    """Ángulo agudo (0–90°) entre las RECTAS de dos direcciones."""
    e = _entre(a, b)
    return min(e, 180.0 - e)


def clasificar(salidas):
    """(tipo, ángulo°) para las direcciones (radianes) que salen del nodo, o
    None si no hay accesorio (unión recta, 1 salida o 5+)."""
    n = len(salidas)
    if n == 2:
        giro = 180.0 - _entre(salidas[0], salidas[1])   # deflexión sobre el eje prolongado
        return ("codo", giro) if giro > GIRO_CODO_MIN_DEG else None
    if n == 3:
        pares = sorted(((i, j) for i in range(3) for j in range(i + 1, 3)),
                       key=lambda ij: -_entre(salidas[ij[0]], salidas[ij[1]]))
        i, j = pares[0]
        ramal = salidas[3 - i - j]
        ang = _agudo(ramal, salidas[i])
        if _entre(salidas[i], salidas[j]) >= TRONCO_MIN_DEG and ang >= RAMAL_TEE_MIN_DEG:
            return ("tee", ang)
        return ("wye", ang)
    if n == 4:
        # Las dos líneas: cada salida con la más opuesta.
        a = salidas[0]
        k = max(range(1, 4), key=lambda m: _entre(a, salidas[m]))
        otras = [m for m in range(1, 4) if m != k]
        return ("cruz", _agudo(a, salidas[otras[0]]))
    return None


def _proyeccion(p, a, b):
    """(t, distancia) de p sobre el segmento a→b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return 0.0, math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    tc = max(0.0, min(1.0, t))
    return t, math.hypot(a[0] + dx * tc - p[0], a[1] + dy * tc - p[1])


def _interseccion(a1, a2, b1, b2):
    rx, ry = a2[0] - a1[0], a2[1] - a1[1]
    sx, sy = b2[0] - b1[0], b2[1] - b1[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        return None
    qx, qy = b1[0] - a1[0], b1[1] - a1[1]
    t = (qx * sy - qy * sx) / den
    return (a1[0] + rx * t, a1[1] + ry * t)


def accesorios(pipes, z_at, ft_per_px):
    """Accesorios de las redes a presión. `z_at(i_pipe, i_tramo, x, y)` = solera
    del tramo en ese punto (None = 0). Devuelve una lista de dicts:
    {"x", "y", "tipo", "angulo", "capa", "red", "pipes": [índices], "n"}."""
    if not ft_per_px or ft_per_px <= 0:
        return []
    tol = TOL_UNION_FT / ft_per_px
    tol2 = tol * tol

    def _z(i, k, x, y):
        z = z_at(i, k, x, y) if z_at else None
        return 0.0 if z is None else float(z)

    presion = [i for i, p in enumerate(pipes)
               if network_kind(p.get("layer") or "") == "pressure" and len(p.get("pts") or []) >= 2]
    # Vértices como los verá el plugin (codos seguidos ya fundidos). Solo cambia
    # la geometría de los accesorios; `pipes` no se toca.
    fundidos = []
    pipes = list(pipes)
    for i in presion:
        pts, nuevos = fusionar_codos_seguidos(pipes[i]["pts"], pipes[i].get("diam"), ft_per_px)
        if nuevos:
            pipes[i] = dict(pipes[i], pts=pts)
            fundidos += nuevos

    # Extremos de tramo: (x, y, red, i_pipe, z, dirección hacia el otro extremo, i_tramo, i_vértice)
    ext = []
    for i in presion:
        p = pipes[i]; red = red_de(p); pts = p["pts"]
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= 1e-12:
                continue
            ext.append((a[0], a[1], red, i, _z(i, k, *a), _ang(b[0] - a[0], b[1] - a[1]), k, k))
            ext.append((b[0], b[1], red, i, _z(i, k, *b), _ang(a[0] - b[0], a[1] - b[1]), k, k + 1))

    # T: la punta de una utilidad sobre el INTERIOR de un tramo de otra de la
    # misma red y cota → ese tramo se parte ahí (aporta dos extremos).
    # Rejilla de tramos (sin ella, 300 utilidades tardaban segundos por redibujo).
    celda = max(tol * 40.0, 1.0)
    rejilla = {}
    for j in presion:
        pts_j = pipes[j]["pts"]
        for k in range(len(pts_j) - 1):
            (ax, ay), (bx, by) = pts_j[k], pts_j[k + 1]
            for cx in range(int(math.floor((min(ax, bx) - tol) / celda)), int(math.floor((max(ax, bx) + tol) / celda)) + 1):
                for cy in range(int(math.floor((min(ay, by) - tol) / celda)), int(math.floor((max(ay, by) + tol) / celda)) + 1):
                    rejilla.setdefault((cx, cy), []).append((j, k))
    for i in presion:
        pts_i = pipes[i]["pts"]
        for vi in (0, len(pts_i) - 1):
            q = pts_i[vi]
            zi = _z(i, 0 if vi == 0 else len(pts_i) - 2, *q)
            for j, k in rejilla.get((int(math.floor(q[0] / celda)), int(math.floor(q[1] / celda))), ()):
                if j == i or red_de(pipes[j]) != red_de(pipes[i]):
                    continue
                pts_j = pipes[j]["pts"]
                a, b = pts_j[k], pts_j[k + 1]
                t, d = _proyeccion(q, a, b)
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if d > tol or t * L <= tol or (1 - t) * L <= tol:
                    continue
                if abs(_z(j, k, *q) - zi) > TOL_COTA_FT:
                    continue                      # cruce a otra cota: no se une
                zj = _z(j, k, *q)
                ext.append((q[0], q[1], red_de(pipes[j]), j, zj, _ang(a[0] - q[0], a[1] - q[1]), k, None))
                ext.append((q[0], q[1], red_de(pipes[j]), j, zj, _ang(b[0] - q[0], b[1] - q[1]), k, None))

    # Agrupar extremos cercanos de la misma red (como junturas_excedidas).
    # Mismo orden que el recorrido completo, pero solo mira las celdas vecinas
    # (el centro del grupo nunca se aleja más de `tol` de su primer extremo).
    celdas = {}
    for n, e in enumerate(ext):
        celdas.setdefault((int(math.floor(e[0] / tol)), int(math.floor(e[1] / tol))), []).append(n)
    usado = [False] * len(ext)
    nodos = []
    for a in range(len(ext)):
        if usado[a]:
            continue
        usado[a] = True
        grupo = [a]; sx, sy = ext[a][0], ext[a][1]
        c0x, c0y = int(math.floor(ext[a][0] / tol)), int(math.floor(ext[a][1] / tol))
        vecinos = sorted(b for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)
                         for b in celdas.get((c0x + dx, c0y + dy), ()) if b > a)
        for b in vecinos:
            if usado[b] or ext[b][2] != ext[a][2]:
                continue
            cx, cy = sx / len(grupo), sy / len(grupo)
            if (ext[b][0] - cx) ** 2 + (ext[b][1] - cy) ** 2 > tol2:
                continue
            usado[b] = True; grupo.append(b)
            sx += ext[b][0]; sy += ext[b][1]
        if len(grupo) < 2:
            continue
        # Por cota: cada utilidad su media; se encadenan las que quedan a ≤ 0.10 ft.
        por_pipe = {}
        for e in grupo:
            por_pipe.setdefault(ext[e][3], []).append(e)
        sub = sorted(((sum(ext[e][4] for e in v) / len(v), v) for v in por_pipe.values()),
                     key=lambda s: s[0])
        cadenas = [[sub[0]]]
        for s in sub[1:]:
            if abs(s[0] - cadenas[-1][-1][0]) <= TOL_COTA_FT:
                cadenas[-1].append(s)
            else:
                cadenas.append([s])
        for c in cadenas:
            miembros = [e for _z0, v in c for e in v]
            if len(miembros) < 2:
                continue
            r = clasificar([ext[e][5] for e in miembros])
            if r is None:
                continue
            tipo, ang = r
            ids = sorted({ext[e][3] for e in miembros})
            x = sum(ext[e][0] for e in miembros) / len(miembros)
            y = sum(ext[e][1] for e in miembros) / len(miembros)
            nodo = {"x": x, "y": y, "tipo": tipo, "angulo": ang, "red": ext[miembros[0]][2],
                    "giro": ang if tipo == "codo" else None,
                    "capa": pipes[ids[0]].get("layer") or "", "pipes": ids, "n": len(miembros)}
            if tipo == "codo" and any((fx - x) ** 2 + (fy - y) ** 2 <= tol2 for fx, fy in fundidos):
                nodo["fundido"] = True
            nodos.append(nodo)
    return nodos


def _giro(a, b, c):
    u = (b[0] - a[0], b[1] - a[1]); w = (c[0] - b[0], c[1] - b[1])
    if math.hypot(*u) < 1e-9 or math.hypot(*w) < 1e-9:
        return 0.0
    return _entre(_ang(*u), _ang(*w))


def fusionar_codos_seguidos(pts, diam, ft_per_px):
    """Réplica de `FusionarCodosSeguidos` del plugin sobre UNA polilínea: un tramo
    interior más corto que el largo mínimo entre dos giros de ≥ 5° se quita y el
    vértice queda en el cruce de las rectas vecinas (o en el medio si son casi
    paralelas). Devuelve (pts, [puntos fundidos])."""
    v = [tuple(q) for q in pts]
    lmin_px = largo_min_entre_codos_ft(diam) / ft_per_px
    nuevos = []
    for _vuelta in range(100):
        k = -1
        for i in range(1, len(v) - 2):
            largo = math.hypot(v[i + 1][0] - v[i][0], v[i + 1][1] - v[i][1])
            if largo >= lmin_px - 1e-6 or largo < 1e-9:
                continue
            if _giro(v[i - 1], v[i], v[i + 1]) < GIRO_FUSION_MIN_DEG or                     _giro(v[i], v[i + 1], v[i + 2]) < GIRO_FUSION_MIN_DEG:
                continue
            k = i
            break
        if k < 0:
            break
        medio = ((v[k][0] + v[k + 1][0]) / 2, (v[k][1] + v[k + 1][1]) / 2)
        x = _interseccion(v[k - 1], v[k], v[k + 1], v[k + 2]) or medio
        if math.hypot(x[0] - medio[0], x[1] - medio[1]) > 3 * lmin_px:
            x = medio                                  # casi paralelas: no disparar el vértice
        v[k] = x
        del v[k + 1]
        nuevos.append(x)
    return v, nuevos


def texto_angulo(ang):
    """45 → «45°», 11.25 → «11.25°», 22.5 → «22.5°», 37.431 → «37.43°»."""
    for dec in (0, 2):
        if abs(ang - round(ang, dec)) < 0.01:
            s = f"{round(ang, dec):.{dec}f}"
            return (s.rstrip("0").rstrip(".") if "." in s else s) + "°"
    return f"{ang:.1f}°"
