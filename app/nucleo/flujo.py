"""Sentido del FLUJO en las utilidades por gravedad y a presión (pedidos del usuario 2026-11-09: «indicar hacia dónde
va el fluido, de una manera fácil, en las propiedades de la utilidad y en el perfil»; luego «también para las de
presión; eléctrico y telecom son las únicas que no deben tener»). PURO (sin Qt).

Hacia dónde va el fluido se elige con un PUNTO DE LLEGADA (pedido del usuario 2026-11-10: «ya no todo a la izquierda o
todo a la derecha: puede llegar a un buzón del medio»). Lo que se guarda en la utilidad:
- `pipe["flujo"]` = 1: va del INICIO al FIN (el orden de sus vértices, «Start to End» de Civil 3D) = llega a su fin;
- `pipe["flujo"]` = -1: va del FIN al INICIO = llega a su inicio;
- `pipe["flujo_hacia"]` = [x, y]: llega a un punto INTERMEDIO de la utilidad (un buzón, un vértice o un punto de la
  línea): las dos partes van hacia él. Se guarda el punto (px de la hoja), no el número de tramo: insertar o quitar
  vértices no lo corre, y al dar vuelta la utilidad sigue igual;
- `pipe["flujo_tramos"]` = [[mx, my, dx, dy], …]: PERSONALIZADO POR TRAMOS (pedido 2026-11-10: «cambiar de manera
  fácil y visual el sentido de cada tramo por separado»). Una entrada por tramo: su punto medio y la dirección del
  fluido (vector unitario; cero = ese tramo sigue automático). El tramo k toma la entrada más cercana a él y su
  sentido es el signo de esa dirección contra el tramo: insertar o quitar vértices, o dar vuelta la utilidad, no lo
  cambia;
- sin ninguna = AUTOMÁTICO. En gravedad: en el perfil, hacia el extremo más bajo del recorrido. A presión
  no hay pendiente que lo diga: queda SIN INDICAR.
Las tres formas se excluyen: indicar una quita las otras.
Se usa para validar (contrapendiente en el perfil y en el plano, caída en los buzones: `flujo_validar`) y para
dibujar las flechas: nada se mueve.
"""
from __future__ import annotations

import math

from nucleo.model import network_kind

ADELANTE, ATRAS, AUTO = 1, -1, 0
REDES = ("gravity", "pressure")          # las de conductos (eléctrico, telecom) no llevan sentido del flujo
HACIA = "flujo_hacia"
TRAMOS = "flujo_tramos"
EPS_T = 1e-9


def aplica(p):
    """True si la utilidad lleva sentido del flujo (gravedad o presión)."""
    return isinstance(p, dict) and network_kind(p.get("layer") or "") in REDES


def fijo(p):
    """El sentido de TODA la utilidad indicado por el usuario (1 / -1), o 0 = automático o a un punto intermedio."""
    v = p.get("flujo") if isinstance(p, dict) else None
    return v if v in (ADELANTE, ATRAS) else AUTO


def punto(p):
    """El punto intermedio al que llega el fluido (x, y), o None."""
    v = p.get(HACIA) if isinstance(p, dict) else None
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        return None
    try:
        return float(v[0]), float(v[1])
    except (TypeError, ValueError):
        return None


def _entradas(p):
    v = p.get(TRAMOS) if isinstance(p, dict) else None
    out = []
    for e in v or ():
        try:
            mx, my, dx, dy = (float(c) for c in e[:4])
        except (TypeError, ValueError):
            continue
        out.append((mx, my, dx, dy))
    return out


def por_tramos(p):
    """True si el sentido está personalizado por tramos."""
    return bool(_entradas(p))


def _dist_seg(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 1e-18 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
    return math.hypot(a[0] + dx * t - x, a[1] + dy * t - y)


def sentidos_tramos(p):
    """[1 / -1 / 0] de cada tramo en el modo por tramos (0 = ese tramo sigue automático)."""
    pts = (p.get("pts") or []) if isinstance(p, dict) else []
    ents = _entradas(p)
    out = []
    for k in range(len(pts) - 1):
        a, b = pts[k][:2], pts[k + 1][:2]
        if not ents:
            out.append(AUTO)
            continue
        mx, my, dx, dy = min(ents, key=lambda e: _dist_seg(e[0], e[1], a, b))
        d = dx * (b[0] - a[0]) + dy * (b[1] - a[1])
        out.append(ADELANTE if d > 1e-12 else ATRAS if d < -1e-12 else AUTO)
    return out


def tiene(p):
    """True si el usuario indicó hacia dónde va el fluido (a una punta, a un punto intermedio o por tramos)."""
    return bool(fijo(p)) or punto(p) is not None or any(sentidos_tramos(p))


def estado(p):
    return fijo(p), punto(p), tuple(sentidos_tramos(p)) if por_tramos(p) else ()


def poner(p, sentido):
    """Toda la utilidad hacia su fin (1) o su inicio (-1), o automático (0). True si cambió."""
    antes = estado(p)
    p.pop(HACIA, None)
    p.pop(TRAMOS, None)
    if sentido in (ADELANTE, ATRAS):
        p["flujo"] = int(sentido)
    else:
        p.pop("flujo", None)
    return estado(p) != antes


def proyectar(pts, x, y):
    """(tramo, t, (qx, qy), distancia, largo hasta q, largo total) del punto de la polilínea más cercano a (x, y)."""
    mejor, acum = None, 0.0
    tot = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    for k in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[k][:2], pts[k + 1][:2]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 1e-18 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        q = (ax + dx * t, ay + dy * t)
        d = math.hypot(q[0] - x, q[1] - y)
        if mejor is None or d < mejor[3] - 1e-12:
            mejor = (k, t, q, d, acum + math.sqrt(L2) * t, tot)
        acum += math.sqrt(L2)
    return mejor


def poner_hacia(p, x, y, tol_px=0.5):
    """El fluido llega al punto de la utilidad más cercano a (x, y). En una punta (a ≤ tol_px) = toda la utilidad
    hacia esa punta (`flujo` 1 / -1); si no, `flujo_hacia`. True si cambió."""
    pts = p.get("pts") or []
    if len(pts) < 2:
        return False
    r = proyectar(pts, x, y)
    if r is None:
        return False
    _k, _t, q, _d, s, tot = r
    if s <= tol_px:
        return poner(p, ATRAS)
    if tot - s <= tol_px:
        return poner(p, ADELANTE)
    antes = estado(p)
    p.pop("flujo", None)
    p.pop(TRAMOS, None)
    p[HACIA] = [q[0], q[1]]
    return estado(p) != antes


def por_tramo_actual(p):
    """[1 / -1 / 0] de cada tramo con el sentido de ahora (un tramo con el punto de llegada adentro toma el de su
    parte más larga)."""
    pts = p.get("pts") or []
    out = [AUTO] * max(0, len(pts) - 1)
    largo = [0.0] * len(out)
    for k, t0, t1, s in partes(p):
        if t1 - t0 > largo[k]:
            out[k], largo[k] = s, t1 - t0
    return out


def poner_tramo(p, k, sentido):
    """Personaliza por tramos: el tramo k va hacia el fin del tramo (1), hacia su inicio (-1) o automático (0); los
    demás tramos quedan como van ahora. True si cambió."""
    pts = p.get("pts") or []
    if not (0 <= k < len(pts) - 1):
        return False
    s = por_tramo_actual(p)
    s[k] = sentido if sentido in (ADELANTE, ATRAS) else AUTO
    antes = estado(p)
    p.pop("flujo", None)
    p.pop(HACIA, None)
    ents = []
    for j, sj in enumerate(s):
        (ax, ay), (bx, by) = pts[j][:2], pts[j + 1][:2]
        L = math.hypot(bx - ax, by - ay)
        if L <= 1e-12:
            continue
        # también los automáticos (dirección cero): cada tramo con su entrada, así ninguno toma la del vecino
        ents.append([(ax + bx) / 2, (ay + by) / 2, (bx - ax) / L * sj, (by - ay) / L * sj])
    if any(s):
        p[TRAMOS] = ents
    else:
        p.pop(TRAMOS, None)
    return estado(p) != antes


def vista_tramos(p, cotas=None):
    """[(sentido, indicado)] de cada tramo como se muestra al personalizar: el indicado o, si es automático, en
    gravedad hacia la solera más baja del tramo (`cotas(k)` = (z inicio, z fin) o None) y a presión 0 (sin indicar)."""
    gravedad = network_kind(p.get("layer") or "") == "gravity"
    out = []
    for k, s in enumerate(por_tramo_actual(p)):
        if s:
            out.append((s, True))
            continue
        c = cotas(k) if (cotas and gravedad) else None
        if c and c[0] is not None and c[1] is not None and abs(c[0] - c[1]) > 1e-9:
            out.append((ADELANTE if c[1] < c[0] else ATRAS, False))
        else:
            out.append((AUTO, False))
    return out


def alternar_tramo(p, k, cotas=None):
    """Un clic sobre el tramo k: si es automático, queda FIJO tal como se ve (a presión, hacia el fin del tramo); si
    ya está indicado, se invierte. True si cambió."""
    vista = vista_tramos(p, cotas)
    if not (0 <= k < len(vista)):
        return False
    s, indicado = vista[k]
    return poner_tramo(p, k, -s if indicado else (s or ADELANTE))


def corte(p):
    """(tramo, t) donde llega el fluido si va a un punto intermedio, o None."""
    pt = punto(p)
    pts = (p.get("pts") or []) if isinstance(p, dict) else []
    if pt is None or len(pts) < 2 or por_tramos(p):
        return None
    r = proyectar(pts, *pt)
    return (r[0], r[1]) if r else None


def partes(p):
    """[(tramo, t0, t1, sentido)] de toda la utilidad: 1 = va hacia su fin, -1 = hacia su inicio, 0 = automático. Un
    tramo con el punto de llegada adentro va en dos partes."""
    pts = p.get("pts") or []
    if por_tramos(p):
        return [(k, 0.0, 1.0, s) for k, s in enumerate(sentidos_tramos(p))]
    c = corte(p)
    f = fijo(p)
    out = []
    for k in range(len(pts) - 1):
        if c is None:
            out.append((k, 0.0, 1.0, f))
            continue
        kc, tc = c
        if k < kc:
            out.append((k, 0.0, 1.0, ADELANTE))
        elif k > kc:
            out.append((k, 0.0, 1.0, ATRAS))
        else:
            if tc > EPS_T:
                out.append((k, 0.0, tc, ADELANTE))
            if tc < 1.0 - EPS_T:
                out.append((k, tc, 1.0, ATRAS))
    return out


def sentido_en(p, k, t):
    """Sentido del fluido en el tramo k, en su parámetro t (1 / -1 / 0)."""
    for kk, t0, t1, s in partes(p):
        if kk == k and t0 - EPS_T <= t <= t1 + EPS_T:
            if t1 - t0 > EPS_T or t in (0.0, 1.0):
                return s
    return AUTO


def llegada(p):
    """(x, y) donde llega el fluido de la utilidad (su punta o el punto intermedio), o None si es automático."""
    pts = p.get("pts") or []
    if len(pts) < 2 or por_tramos(p):
        return None                                   # por tramos puede llegar a varios lados: sin una sola diana
    c = corte(p)
    if c is not None:
        k, t = c
        (ax, ay), (bx, by) = pts[k][:2], pts[k + 1][:2]
        return ax + (bx - ax) * t, ay + (by - ay) * t
    f = fijo(p)
    if f == ADELANTE:
        return tuple(pts[-1][:2])
    if f == ATRAS:
        return tuple(pts[0][:2])
    return None


def en_paso(p, invertida):
    """El sentido de TODA la utilidad visto desde un paso del perfil: 1 = hacia las estaciones mayores (B),
    -1 = hacia el inicio (A), 0 = automático. `invertida` = el paso recorre la utilidad del fin al inicio."""
    f = fijo(p)
    return -f if (f and invertida) else f


def en_arista(p, tramo, t0, t1, invertida):
    """(sentido, corte) de un paso del perfil que recorre la parte [t0, t1] del tramo `tramo` de la utilidad:
    sentido 1 = hacia B, -1 = hacia A, 0 = automático; `corte` = parámetro sobre el paso (0 = su inicio) donde
    llega el fluido si el punto de llegada cae dentro (entonces las dos partes van hacia él), o None."""
    if por_tramos(p):
        st = sentidos_tramos(p)
        s = st[tramo] if 0 <= tramo < len(st) else AUTO
        return (-s if invertida else s), None
    c = corte(p)
    if c is None:
        return en_paso(p, invertida), None
    kc, tc = c
    if tramo < kc or (tramo == kc and t1 <= tc + EPS_T):
        s = ADELANTE
    elif tramo > kc or (tramo == kc and t0 >= tc - EPS_T):
        s = ATRAS
    else:
        u = (tc - t0) / max(t1 - t0, 1e-12)
        return ADELANTE, (1.0 - u if invertida else u)
    return (-s if invertida else s), None


def de_paso(hacia, invertida):
    """Lo inverso de `en_paso`: el valor de `pipe["flujo"]` para que el fluido vaya `hacia` (1 = B, -1 = A, 0 =
    automático) en un paso que recorre la utilidad al derecho (`invertida` False) o al revés."""
    if hacia not in (ADELANTE, ATRAS):
        return AUTO
    return -hacia if invertida else hacia


def invertido(p):
    """El valor de `flujo` para la MISMA utilidad con sus vértices al revés (el fluido sigue igual). El punto
    intermedio (`flujo_hacia`) no cambia: es un punto."""
    f = fijo(p)
    return -f if f else AUTO


def rumbo_pantalla(pts):
    """Ángulo (grados, Y del lienzo hacia abajo) de la utilidad del inicio al fin. Si las puntas coinciden (lazo),
    el del primer tramo. None sin tramos."""
    if not pts or len(pts) < 2:
        return None
    a, b = pts[0], pts[-1]
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6:
        a, b = pts[0], pts[1]
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9:
        return None
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def flechas_plano(pts, sentido):
    """[(x, y, ángulo en grados)] de una flecha a la mitad de cada tramo, apuntando hacia donde va el fluido
    (`sentido` 1 / -1). [] si es automático."""
    if sentido not in (ADELANTE, ATRAS):
        return []
    out = []
    for a, b in zip(pts, pts[1:]):
        if sentido == ATRAS:
            a, b = b, a
        dx, dy = b[0] - a[0], b[1] - a[1]
        if math.hypot(dx, dy) < 1e-9:
            continue
        out.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.degrees(math.atan2(dy, dx))))
    return out


def flechas(p, dibujo=None, minimo_px=0.0):
    """[(x, y, ángulo en grados)] de una flecha a la mitad de cada tramo (o de cada parte, si el punto de llegada
    cae dentro), sobre la línea tal como se dibuja (`dibujo`, con sus curvas) y apuntando hacia donde va el fluido.
    Las partes de menos de `minimo_px` no llevan flecha. [] si es automático."""
    pts = p.get("pts") or []
    dib = dibujo if dibujo and len(dibujo) >= 2 else pts
    out = []
    for k, t0, t1, s in partes(p):
        if not s:
            continue
        (ax, ay), (bx, by) = pts[k][:2], pts[k + 1][:2]
        if math.hypot(bx - ax, by - ay) * (t1 - t0) < max(minimo_px, 1e-9):
            continue
        tm = (t0 + t1) / 2
        r = proyectar(dib, ax + (bx - ax) * tm, ay + (by - ay) * tm)
        if r is None:
            continue
        j, _u, q, _d, _s, _tot = r
        (cx, cy), (ex, ey) = dib[j][:2], dib[j + 1][:2]
        dx, dy = ex - cx, ey - cy
        if math.hypot(dx, dy) < 1e-9:
            dx, dy = bx - ax, by - ay
        if s == ATRAS:
            dx, dy = -dx, -dy
        out.append((q[0], q[1], math.degrees(math.atan2(dy, dx))))
    return out


def ramas(p, dibujo=None):
    """Polilíneas (px) orientadas HACIA donde va el fluido, sobre la línea tal como se dibuja: una (toda la
    utilidad hacia una punta) o dos que llegan al punto intermedio. [] si es automático."""
    pts = p.get("pts") or []
    dib = [tuple(q[:2]) for q in (dibujo if dibujo and len(dibujo) >= 2 else pts)]
    if len(dib) < 2:
        return []
    if por_tramos(p):
        return _ramas_tramos(pts, dib, sentidos_tramos(p))
    pt = punto(p)
    if pt is not None:
        c = proyectar(pts, *pt)
        if c is not None:
            k, t, *_ = c
            (ax, ay), (bx, by) = pts[k][:2], pts[k + 1][:2]
            r = proyectar(dib, ax + (bx - ax) * t, ay + (by - ay) * t)
            j, _u, q, *_ = r
            a = dib[:j + 1] + [q]
            b = list(reversed(dib[j + 1:])) + [q]
            return [x for x in (a, b) if _largo(x) > 1e-9]
    f = fijo(p)
    if f == ADELANTE:
        return [dib]
    if f == ATRAS:
        return [list(reversed(dib))]
    return []


def _tramo_en(dib, a, b):
    """La parte de la línea dibujada entre las proyecciones de a y b (de a hacia b)."""
    ra, rb = proyectar(dib, *a[:2]), proyectar(dib, *b[:2])
    if ra is None or rb is None:
        return [tuple(a[:2]), tuple(b[:2])]
    ja, qa, sa = ra[0], ra[2], ra[4]
    jb, qb, sb = rb[0], rb[2], rb[4]
    if sb < sa:
        return list(reversed(_tramo_en(dib, b, a)))
    return [qa] + list(dib[ja + 1:jb + 1]) + [qb]


def _ramas_tramos(pts, dib, sentidos):
    """Ramas del modo por tramos: tramos seguidos con el mismo sentido van juntos."""
    out, actual, s_act = [], [], 0
    for k, s in enumerate(sentidos):
        if not s:
            if actual:
                out.append(actual if s_act > 0 else list(reversed(actual)))
            actual, s_act = [], 0
            continue
        seg = _tramo_en(dib, pts[k], pts[k + 1])
        if s == s_act and actual:
            actual += seg[1:]
        else:
            if actual:
                out.append(actual if s_act > 0 else list(reversed(actual)))
            actual, s_act = list(seg), s
    if actual:
        out.append(actual if s_act > 0 else list(reversed(actual)))
    return [r for r in out if _largo(r) > 1e-9]


def flechas_vista(p, vista, dibujo=None):
    """[(tramo, x, y, ángulo, sentido, indicado)] de una flecha a la mitad de cada tramo según `vista`
    (`vista_tramos`): la que se muestra al personalizar por tramos (sentido 0 = a lo largo del tramo)."""
    pts = p.get("pts") or []
    dib = dibujo if dibujo and len(dibujo) >= 2 else pts
    out = []
    for k, (s, indicado) in enumerate(vista):
        (ax, ay), (bx, by) = pts[k][:2], pts[k + 1][:2]
        if math.hypot(bx - ax, by - ay) <= 1e-9:
            continue
        r = proyectar(dib, (ax + bx) / 2, (ay + by) / 2)
        j, q = r[0], r[2]
        (cx, cy), (ex, ey) = dib[j][:2], dib[j + 1][:2]
        dx, dy = ex - cx, ey - cy
        if math.hypot(dx, dy) < 1e-9:
            dx, dy = bx - ax, by - ay
        if s == ATRAS:
            dx, dy = -dx, -dy
        out.append((k, q[0], q[1], math.degrees(math.atan2(dy, dx)), s, indicado))
    return out


def _largo(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def iman(pts, x, y, r, buzones=()):
    """Dónde llegaría el fluido con el cursor en (x, y), sobre la utilidad de vértices `pts`: (x, y, tipo) con
    tipo «buzon» (uno de `buzones`, (x, y) de los buzones de la utilidad), «punta», «vertice» o «linea» (cualquier
    punto de la línea), a ≤ r px; la línea hasta 2.5 r. None si queda lejos."""
    if len(pts) < 2:
        return None
    for tipo, cand in (("buzon", buzones), ("punta", (pts[0], pts[-1])), ("vertice", pts[1:-1])):
        mejor = None
        for q in cand:
            d = math.hypot(q[0] - x, q[1] - y)
            if d <= r and (mejor is None or d < mejor[0]):
                mejor = (d, q)
        if mejor is not None:
            return float(mejor[1][0]), float(mejor[1][1]), tipo
    pr = proyectar(pts, x, y)
    if pr is not None and pr[3] <= 2.5 * r:
        return pr[2][0], pr[2][1], "linea"
    return None
