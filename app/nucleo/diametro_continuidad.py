"""diametro_continuidad.py — el diámetro de una línea por CONTINUIDAD con la red (PURO; pedido del usuario 2026-11-03:
«si un trayecto de una utilidad tiene una medida y ese trayecto continúa, la IA debe evaluarlo y decir: tu línea tal
tiene tal medida en tal sitio y te sugiero que esta también la tenga, con conceptos de ingeniería»).

Reglas de ingeniería que se aplican (las mismas en el PDF con capas y en el mapa sin capas):
  · Una tubería que SIGUE de frente a otra (extremo con extremo, giro ≤ `GIRO_SIGUE_DEG`) sin un buzón, caja o
    accesorio de cambio entre ellas lleva normalmente el MISMO diámetro: un cambio de diámetro se hace en una
    estructura (gravedad) o con una reducción (presión). Se camina por las líneas sin diámetro que siguen de frente
    hasta `MAX_SALTOS` para hallar la primera confirmada de cada lado.
  · Un RAMAL (su punta llega al interior de otra línea) no es mayor que la principal (`max_in`).
  · Una línea que RECIBE un ramal confirmado no es menor que él (`min_in`).
  · Los dos lados con el mismo diámetro = propuesta fuerte; con diámetros distintos, las dos opciones (el cambio
    está en algún nodo entre ellas: lo decide quien revisa, o la IA con la imagen).

Solo se miran las líneas de la MISMA capa (utilidad) y el mismo estado (activa / abandonada). Nada se aplica: da
opciones con su explicación (`opciones`, ids C1, C2…) para la tarjeta de la IA.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from traduccion.i18n_core import t

Pt = Tuple[float, float]

GIRO_SIGUE_DEG = 35.0          # extremo con extremo y casi de frente = la misma tubería que sigue
MAX_SALTOS = 6                 # líneas sin diámetro que se atraviesan siguiendo de frente
TOL_FT = 0.5                   # contacto (pies); sin escala, `TOL_PX`
TOL_PX = 1.5


def _confirmado(p) -> Optional[float]:
    from nucleo import model_ops
    d, defecto = model_ops.diametro(p)
    return None if defecto else float(d)


def _dist_seg(q: Pt, a: Pt, b: Pt) -> Tuple[float, float]:
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    u = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - u * vx, q[1] - a[1] - u * vy), u


def _interior(q: Pt, pts: Sequence[Pt], tol: float) -> bool:
    """¿q toca la línea lejos de sus dos extremos?"""
    for a, b in zip(pts, pts[1:]):
        d, _u = _dist_seg(q, a, b)
        if d <= tol and math.dist(q, pts[0]) > tol and math.dist(q, pts[-1]) > tol:
            return True
    return False


def _salida(pts: Sequence[Pt], extremo: int) -> Pt:
    """Dirección (unitaria) con que la línea SALE de su extremo (0 = inicio, -1 = fin), hacia adentro."""
    a, b = (pts[0], pts[1]) if extremo == 0 else (pts[-1], pts[-2])
    L = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def _largo(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _nombre(pipes, j) -> str:
    from nucleo import model_ops
    p = pipes[j]
    return (p.get("name") or "").strip() or model_ops.nombre_por_defecto(p, j)


def _sigue(pipes, i: int, extremo: int, tol: float, mismas) -> Optional[Tuple[int, int]]:
    """(línea, su extremo de llegada) que sigue de frente al extremo `extremo` de la línea i, o None. Si hay dos
    candidatas casi igual de rectas (una «Y»), ninguna: no se sabe cuál es la continuación."""
    pts = pipes[i]["pts"]
    q = pts[0] if extremo == 0 else pts[-1]
    sale = _salida(pts, extremo)
    cands = []
    for j in mismas:
        if j == i:
            continue
        op = pipes[j]["pts"]
        for e2, r in ((0, op[0]), (-1, op[-1])):
            if math.dist(q, r) <= tol:
                s2 = _salida(op, e2)
                # siguen de frente: salen del nodo en sentidos opuestos
                giro = math.degrees(math.acos(max(-1.0, min(1.0, -(sale[0] * s2[0] + sale[1] * s2[1])))))
                if giro <= GIRO_SIGUE_DEG:
                    cands.append((giro, j, e2))
    if not cands:
        return None
    cands.sort()
    if len(cands) > 1 and cands[1][0] - cands[0][0] < 10.0:
        return None
    return cands[0][1], cands[0][2]


def _estructura_en(q: Pt, estructuras, tol: float) -> bool:
    """¿Hay un buzón/caja VISIBLE en ese nodo? (ahí sí puede cambiar el diámetro)"""
    for s in estructuras or ():
        if s.get("hidden") or s.get("curve") or s.get("world") or s.get("x") is None:
            continue
        if math.hypot(s["x"] - q[0], s["y"] - q[1]) <= max(tol, 6.0):
            return True
    return False


def analizar(i: int, pipes: Sequence[dict], ft_px: Optional[float] = None, estructuras=()) -> dict:
    """{"lados": [{extremo, diam_in, linea, nombre, saltos, distancia_ft, estructura}], "max_in", "min_in",
    "ramales": [...], "opciones": [{id, diam_in, fuerza, texto, lineas}]} de la línea i."""
    p = pipes[i]
    pts = p.get("pts") or []
    vacio = dict(lados=[], max_in=None, min_in=None, ramales=[], opciones=[])
    if len(pts) < 2:
        return vacio
    tol = TOL_FT / ft_px if ft_px else TOL_PX
    mismas = [j for j, o in enumerate(pipes) if len(o.get("pts") or []) >= 2 and not o.get("world")
              and o.get("layer") == p.get("layer") and bool(o.get("ab")) == bool(p.get("ab"))]
    lados = []
    for extremo in (0, -1):
        actual, e, recorrido, saltos = i, extremo, 0.0, 0
        hubo_estructura = False
        while saltos <= MAX_SALTOS:
            q0 = pipes[actual]["pts"][0 if e == 0 else -1]
            hubo_estructura |= _estructura_en(q0, estructuras, tol)
            sig = _sigue(pipes, actual, e, tol, mismas)
            if sig is None:
                break
            j, e2 = sig
            d = _confirmado(pipes[j])
            if d is not None:
                lados.append(dict(extremo="inicio" if extremo == 0 else "fin", diam_in=d, linea=j,
                                  nombre=_nombre(pipes, j), saltos=saltos,
                                  distancia_ft=round(recorrido * ft_px, 1) if ft_px else None,
                                  estructura=hubo_estructura))
                break
            recorrido += _largo(pipes[j]["pts"])
            actual, e = j, (-1 if e2 == 0 else 0)          # sale por la otra punta
            saltos += 1
            if actual == i:
                break
    # ramales: esta línea llega al interior de otra (es su ramal) / otra llega al interior de esta
    max_in = min_in = None
    ramales = []
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    caja = (min(xs) - tol, min(ys) - tol, max(xs) + tol, max(ys) + tol)
    for j in mismas:
        if j == i:
            continue
        op = pipes[j]["pts"]
        if (max(q[0] for q in op) < caja[0] or min(q[0] for q in op) > caja[2]
                or max(q[1] for q in op) < caja[1] or min(q[1] for q in op) > caja[3]):
            continue                                       # no se tocan: ni ramal ni principal
        d = _confirmado(pipes[j])
        if d is None:
            continue
        if any(_interior(q, op, tol) for q in (pts[0], pts[-1])):
            max_in = d if max_in is None else min(max_in, d)
            ramales.append(dict(rol="principal", linea=j, nombre=_nombre(pipes, j), diam_in=d))
        elif any(_interior(q, pts, tol) for q in (op[0], op[-1])):
            min_in = d if min_in is None else max(min_in, d)
            ramales.append(dict(rol="ramal", linea=j, nombre=_nombre(pipes, j), diam_in=d))
    return dict(lados=lados, max_in=max_in, min_in=min_in, ramales=ramales,
                opciones=_opciones(lados, max_in, min_in))


def _donde(l) -> str:
    if l["saltos"] == 0:
        return t("justo a continuación")
    if l.get("distancia_ft") is not None:
        return t("a {d} ft siguiendo el trazado").format(d=f'{l["distancia_ft"]:g}')
    return t("más adelante en el trazado")


def _opciones(lados, max_in, min_in) -> List[dict]:
    def ok(d):
        return (max_in is None or d <= max_in + 1e-6) and (min_in is None or d >= min_in - 1e-6)
    out: List[dict] = []
    diams = sorted({l["diam_in"] for l in lados})
    if len(lados) == 2 and len(diams) == 1 and ok(diams[0]):
        a, b = lados
        out.append(dict(diam_in=diams[0], fuerza="alta", lineas=[a["linea"], b["linea"]], texto=t(
            'Las líneas {a} ({da}) y {b} ({db}) siguen de frente a los dos lados de esta con {d}" confirmados: '
            'una tubería no cambia de diámetro en un tramo sin estructura, así que esta lleva {d}".').format(
            a=a["nombre"], da=_donde(a), b=b["nombre"], db=_donde(b), d=f"{diams[0]:g}")))
    else:
        for l in lados:
            if not ok(l["diam_in"]) or any(abs(o["diam_in"] - l["diam_in"]) < 1e-6 for o in out):
                continue
            fuerza = "alta" if len(lados) == 1 and l["saltos"] == 0 and not l["estructura"] else "media"
            texto = t('Esta línea sigue de frente a {n} ({donde}), que tiene {d}" confirmados: sin un buzón o una '
                      'reducción entre ellas, la tubería mantiene su diámetro.').format(
                n=l["nombre"], donde=_donde(l), d=f'{l["diam_in"]:g}')
            if len(diams) > 1:
                texto += " " + t("Del otro lado sigue con otro diámetro: el cambio está en algún nodo entre las dos.")
                fuerza = "media"
            out.append(dict(diam_in=l["diam_in"], fuerza=fuerza, lineas=[l["linea"]], texto=texto))
    if max_in is not None:
        for o in out:
            o["texto"] += " " + t('Es un ramal de una principal de {d}": no puede ser mayor.').format(d=f"{max_in:g}")
    for k, o in enumerate(out):
        o["id"] = f"C{k + 1}"
    return out
