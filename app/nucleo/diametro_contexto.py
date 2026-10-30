"""Contexto geométrico verificable para la revisión de diámetros, sin Qt ni PDF."""
from __future__ import annotations

import math

from nucleo import model_ops
from traduccion.i18n_core import t


def _proyectar(q, pts):
    mejor = (float("inf"), 0.0)
    for a, b in zip(pts, pts[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        den = vx * vx + vy * vy
        k = max(0., min(1., ((q[0]-a[0])*vx + (q[1]-a[1])*vy)/den)) if den else 0.
        d = math.hypot(q[0]-a[0]-k*vx, q[1]-a[1]-k*vy)
        if d < mejor[0]:
            mejor = d, k
    return mejor[0]


def reunir(p, pipes=(), ft_px=None, estructuras=()):
    pts = p.get("pts") or []
    if len(pts) < 2:
        return {"trayecto": {}, "contactos": [], "evidencias": []}
    dist = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    recta = math.dist(pts[0], pts[-1])
    giros = []
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        u, v = (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1])
        den = math.hypot(*u) * math.hypot(*v)
        if den:
            ang = math.degrees(math.acos(max(-1., min(1., (u[0]*v[0]+u[1]*v[1])/den))))
            if ang >= 10:
                giros.append(round(ang, 1))
    origen = pts[0]
    paso = ft_px or 1.
    # Muestra acotada, conservando ambos extremos; coordenadas relativas al inicio.
    indices = sorted({round(k*(len(pts)-1)/min(23, len(pts)-1)) for k in range(min(24,len(pts)))})
    trayecto = dict(largo_ft=round(dist*ft_px, 1) if ft_px else None,
                   separacion_extremos_ft=round(recta*ft_px, 1) if ft_px else None,
                   relacion_recorrido_recta=round(dist/recta, 2) if recta else None,
                   giros_mayores_10_grados=len(giros), angulos=giros[:12],
                   puntos_relativos=[[round((pts[k][0]-origen[0])*paso, 2),
                                      round((pts[k][1]-origen[1])*paso, 2)] for k in indices],
                   unidad="ft" if ft_px else "px")
    evidencias = []

    def evidencia(texto, **datos):
        evidencias.append(dict(id=f"E{len(evidencias)+1}", texto=texto, **datos))

    if ft_px:
        evidencia(t("El recorrido mide {l} ft y tiene {n} cambios de dirección de al menos 10°.").format(
            l=f"{dist*ft_px:g}", n=len(giros)), clase="trayecto")
    contactos = []
    tol = 0.5/ft_px if ft_px else 1.5
    for j, otra in enumerate(pipes):
        op = otra.get("pts") or []
        if otra is p or otra.get("world") or otra.get("layer") != p.get("layer") or len(op)<2:
            continue
        if bool(otra.get("ab")) != bool(p.get("ab")):
            continue
        # Contacto en extremos de cualquiera de las líneas, nunca un simple cruce interior.
        d = min(_proyectar(q, op) for q in (pts[0], pts[-1]))
        d = min(d, *(_proyectar(q, pts) for q in (op[0], op[-1])))
        if d > tol:
            continue
        diam, defecto = model_ops.diametro(otra)
        contacto = dict(linea=j, tipo=otra.get("tipo") or "", diam_in=None if defecto else diam,
                        distancia_ft=round(d*ft_px, 3) if ft_px else None,
                        continuidad="contacto geométrico; conexión hidráulica sin confirmar")
        contactos.append(contacto)
        if not defecto:
            evidencia(t('Una línea de la misma utilidad toca un extremo y tiene {d}" confirmado; '
                        'el contacto geométrico no confirma continuidad hidráulica.').format(d=f"{diam:g}"),
                      clase="vecina", diam_in=diam, linea=j)
        if len(contactos) >= 12:
            break
    cerca = 0
    for est in estructuras:
        if est.get("world") or est.get("x") is None or est.get("y") is None:
            continue
        if min(math.dist((est["x"],est["y"]), q) for q in (pts[0],pts[-1])) <= tol:
            cerca += 1
    if cerca:
        evidencia(t("Hay {n} estructuras junto a los extremos; su conexión debe comprobarse en el recorte.").format(n=cerca),
                  clase="estructuras")
    return dict(trayecto=trayecto, contactos=contactos, evidencias=evidencias)
