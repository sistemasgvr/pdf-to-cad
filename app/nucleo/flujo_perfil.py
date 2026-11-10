"""Elegir en el PERFIL hacia dónde va el fluido (pedido del usuario 2026-11-10: «un botón que me pida seleccionar un
punto en el perfil hacia donde va el fluido, con imán a buzones, vértices y tuberías»). PURO (sin Qt).

Con el punto de llegada en la estación `e` del recorrido, todo lo de antes va hacia B y todo lo de después hacia A:
- `objetivo(perfil, e)`: [(sentido, corte)] de cada paso, para la vista previa (mismo formato que
  `Paso.flujo` / `Paso.flujo_corte`);
- `asignar(perfil, e, punto=None)`: lo que se guarda en cada utilidad del recorrido: toda hacia una punta
  (`flujo` 1 / -1) o, si el punto cae dentro de ella, ese punto (`flujo_hacia`, `nucleo/flujo.poner_hacia`
  vuelve a una punta si cae en ella). Las utilidades fuera del recorrido no cambian;
- `llegadas(perfil, flujos)`: estaciones donde llega el fluido (los dos lados van hacia ahí, o una punta del
  recorrido a la que va), para marcarlas.
"""
from __future__ import annotations

EPS_E = 1e-6


def objetivo(perfil, e):
    out = []
    for ps in perfil.pasos:
        if e >= ps.e1 - EPS_E:
            out.append((1, None))
        elif e <= ps.e0 + EPS_E:
            out.append((-1, None))
        else:
            out.append((1, ps.t_en(e)))
    return out


def asignar(perfil, e, punto=None):
    """{utilidad: ("sentido", 1 | -1) | ("punto", (x, y))}. `punto` = el (x, y) exacto si el imán tomó un nodo del
    recorrido (un buzón o un vértice); si no, el punto de la cuerda en esa estación."""
    from nucleo import flujo as FL
    por = {}
    for i, ps in enumerate(perfil.pasos):
        por.setdefault(ps.pipe, []).append(i)
    out = {}
    for j, idx in por.items():
        pasos = [perfil.pasos[i] for i in idx]
        e_lo, e_hi = min(p.e0 for p in pasos), max(p.e1 for p in pasos)
        if e >= e_hi - EPS_E:
            out[j] = ("sentido", FL.de_paso(1, pasos[0].invertida))
        elif e <= e_lo + EPS_E:
            out[j] = ("sentido", FL.de_paso(-1, pasos[0].invertida))
        else:
            ps = next((p for p in pasos if p.e0 - EPS_E <= e <= p.e1 + EPS_E), pasos[0])
            out[j] = ("punto", tuple(punto) if punto is not None else ps.punto_cuerda(ps.t_en(e)))
    return out


def llegadas(perfil, flujos):
    """Estaciones donde llega el fluido según `flujos` ([(sentido, corte)] por paso): un corte dentro de un paso, un
    nodo con el paso de antes hacia B y el de después hacia A, o una punta del recorrido hacia la que va."""
    pasos = perfil.pasos
    out = []
    for i, (ps, (f, corte)) in enumerate(zip(pasos, flujos)):
        if corte is not None:
            out.append(ps.e_en(corte))
            continue
        if i == 0 and f == -1:
            out.append(ps.e0)
        if i + 1 < len(pasos):
            g, c2 = flujos[i + 1]
            if f == 1 and g == -1 and c2 is None:
                out.append(ps.e1)
        elif f == 1:
            out.append(ps.e1)
    return out
