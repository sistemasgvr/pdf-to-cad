"""Separaciones de las normativas de la app para el MCP de Civil 3D (PURO).

`buscar_conflictos` y `proponer_solucion` del plugin no inventan separaciones: la app les pasa las de su catálogo
de normativas (`normas_catalogo`, reglas activas «Separación vertical», «Por encima de» y «Por debajo de» con MIN),
como `[{a, b, sep_v_ft, encima|debajo, fuente}]` (b = «*» = con cualquiera). Las condiciones de una regla (diámetro,
material…) no se miran, igual que en «Resolver conflictos» (`nucleo/soluciones.separaciones`).
"""
from __future__ import annotations

from nucleo import normas_reglas as NR

CUALQUIERA = "*"
VERTICAL = ("sep_v", "encima", "debajo")      # como `normas_validar_red.VERTICAL`


def reglas_separacion(normas_cat) -> list:
    out, vistos = [], set()
    for r in (normas_cat or {}).get("reglas") or []:
        rv = r.get("revisar")
        if not r.get("activa", True) or rv not in VERTICAL or r.get("min") is None:
            continue
        a = (r.get("utilidad") or "").strip()
        if not a:
            continue
        con = (r.get("con_utilidad") or NR.CUALQUIERA).strip()
        try:
            sep = float(r["min"])
        except (TypeError, ValueError):
            continue
        d = {"a": a, "b": CUALQUIERA if con == NR.CUALQUIERA else con, "sep_v_ft": sep}
        if rv == "encima":
            d["encima"] = a
        elif rv == "debajo":
            d["debajo"] = a
        if r.get("fuente"):
            d["fuente"] = str(r["fuente"])[:120]
        clave = tuple(sorted(d.items()))
        if clave not in vistos:
            vistos.add(clave)
            out.append(d)
    return out

