"""Propuestas de diseño trazables al catálogo; nunca son lecturas del PDF ni se aplican solas."""
from __future__ import annotations

import math

from nucleo import normas_catalogo as nc, normas_validar as nv


def opciones(cat, p, largo_ft=None, preferidos=()):
    """Mínimo explícito/listado que cumple todos los alcances aplicables por tipo.

    Sin tipo se ofrecen hipótesis separadas, que la interfaz debe mostrar. No se
    inventan tamaños desde límites máximos ni se usan condiciones desconocidas.
    """
    reglas = [r for r in (cat or {}).get("reglas", []) if r.get("activa", True)
              and r.get("utilidad") == nc.clave(p.get("layer"))
              and r.get("elemento") == "TUBERIA" and r.get("revisar") == "diametro"]
    tipo = nc.clave(p.get("tipo"))
    tipos = [tipo] if tipo else list(dict.fromkeys([""] + [r.get("tipo") or "" for r in reglas]))
    out = []
    for tp in tipos:
        rs = [r for r in reglas if not r.get("tipo") or r["tipo"] == tp]
        candidatos = sorted({float(d) for r in rs for d in list(r.get("valores") or []) + [r.get("min")] + list(preferidos)
                             if nc.numero(d) is not None and math.isfinite(float(d)) and float(d) > 0})
        for d in candidatos:
            copia = dict(p, tipo=tp, diam=d, diam_elegido=True, pipe_size="")
            dt = nv.datos(0, copia, True, 1.0)
            dt._largo = largo_ft
            aplican, desconocida = [], False
            for r in rs:
                # La ausencia de datos no equivale a cero ni permite ignorar una restricción.
                if r.get("si_largo") and largo_ft is None:
                    desconocida = True
                    continue
                if r.get("si_material") and not dt.material:
                    desconocida = True
                    continue
                a = nv.aplica(r, dt)
                if a is None:
                    desconocida = True
                elif a:
                    aplican.append(r)
            if desconocida or not aplican:
                continue
            grupos = nv.agrupar(aplican)
            if not all(nv.cumple_grupo(g, d) for g in grupos):
                continue
            soporte = [r for g in grupos for r in g if nv.cumple(r, d)]
            # Una excepción con nota (p. ej. cul-de-sac) no es un supuesto automático.
            if any(all(r.get("nota") for r in g if nv.cumple(r, d)) for g in grupos):
                continue
            out.append(dict(id=f"N{len(out) + 1}", diam_in=d, tipo=tp,
                            tipo_supuesto=bool(tp and not tipo),
                            fuente="; ".join(dict.fromkeys(r.get("fuente") or "Catálogo de normativas" for r in soporte)),
                            criterio="; ".join(dict.fromkeys(nv.con_condiciones(nv.requisito(r), r) for r in soporte))))
            # Las alternativas explícitas y los tamaños confirmados del entorno
            # permiten valorar continuidad, en lugar de imponer siempre el mínimo.
    return out
