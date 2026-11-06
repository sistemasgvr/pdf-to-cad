"""Las NORMATIVAS DE LA APP sobre los cambios que propone el plugin de Civil 3D (PURO).

El plugin no conoce las normativas: cada propuesta trae su `efecto` en datos (rasantes, tamaños, movimiento,
tapa/fondo) y aquí se aplica a una COPIA de `datos_red` y se revisa con el mismo validador de la app
(`civil3d_normativas.filas` → `normas_validar`), antes y después: qué avisos crea y cuáles quita. Y la pendiente
objetivo de `proponer_pendiente` también sale de las reglas de la app (`objetivos_pendiente`).
"""
from __future__ import annotations

import copy

from ia import civil3d_normativas as CN


def aplicar_efecto(datos, efecto):
    """Copia de `datos` con el `efecto` de una propuesta del plugin (cotas, tamaños, mover, estructuras)."""
    d = copy.deepcopy(datos)
    tcols = (d.get("tuberias") or {}).get("columnas") or []
    ecols = (d.get("estructuras") or {}).get("columnas") or []
    tub = {f[0]: f for f in (d.get("tuberias") or {}).get("filas") or []}
    est = {f[0]: f for f in (d.get("estructuras") or {}).get("filas") or []}

    def pon(fila, cols, campo, valor):
        if fila is not None and campo in cols and valor is not None:
            fila[cols.index(campo)] = valor

    def suma(fila, cols, campo, delta):
        if fila is not None and campo in cols and fila[cols.index(campo)] is not None and delta:
            fila[cols.index(campo)] += delta

    e = efecto or {}
    for c in e.get("cotas") or []:
        pon(tub.get(c.get("handle")), tcols, "cota_ini", c.get("ini"))
        pon(tub.get(c.get("handle")), tcols, "cota_fin", c.get("fin"))
    for c in e.get("tamanos") or []:
        pon(tub.get(c.get("handle")), tcols, "diam_in", c.get("diam_in"))
        pon(tub.get(c.get("handle")), tcols, "material", c.get("material"))
    for c in e.get("estructuras") or []:
        pon(est.get(c.get("handle")), ecols, "rim", c.get("rim"))
        pon(est.get(c.get("handle")), ecols, "sump", c.get("sump"))
    mv = e.get("mover")
    if mv:
        dx, dy, dz = mv.get("dx") or 0.0, mv.get("dy") or 0.0, mv.get("dz") or 0.0
        for h in mv.get("handles") or []:
            for campo, dd in (("x_ini", dx), ("x_fin", dx), ("y_ini", dy), ("y_fin", dy), ("cota_ini", dz), ("cota_fin", dz)):
                suma(tub.get(h), tcols, campo, dd)
        for h in mv.get("estructuras") or []:
            for campo, dd in (("x", dx), ("y", dy), ("rim", dz), ("sump", dz)):
                suma(est.get(h), ecols, campo, dd)
    return d


def _clave(f):
    return (f["clase"], f["utilidad"], f["tuberia"])


def revisar_efecto(datos, normas_cat, efecto):
    """{"nuevos": [...], "resueltos": [...]}: avisos de normativa de la APP (no informativos) que la propuesta
    crea o quita, comparados por clase, utilidad y tubería."""
    if not efecto or not (normas_cat or {}).get("reglas"):
        return {"nuevos": [], "resueltos": []}
    antes = [f for f in CN.filas(datos, normas_cat)[0] if f["nivel"] != "INFO"]
    despues = [f for f in CN.filas(aplicar_efecto(datos, efecto), normas_cat)[0] if f["nivel"] != "INFO"]
    # La app da UN aviso por utilidad y clase en el primer tramo que falla («T1 … (y 1 tramo más)»): un aviso es
    # nuevo si esa utilidad no tenía ninguno de esa clase; resuelto, si esa tubería deja de tenerlo.
    ua = {(f["clase"], f["utilidad"]) for f in antes}
    kd = {_clave(f) for f in despues}
    return {"nuevos": [f for f in despues if (f["clase"], f["utilidad"]) not in ua],
            "resueltos": [f for f in antes if _clave(f) not in kd]}


def con_normativa(propuesta, datos, normas_cat, maximo=6):
    """La propuesta (dict del plugin) con lo que dice la normativa de la app: avisos nuevos como advertencias y los
    que resuelve como consecuencia. No cambia nada si la propuesta no trae `efecto`."""
    r = revisar_efecto(datos, normas_cat, propuesta.get("efecto"))
    if not (r["nuevos"] or r["resueltos"]):
        return propuesta
    p = dict(propuesta)
    p["advertencias"] = list(p.get("advertencias") or []) + [
        "Normativa: " + (f"{f['tuberia']}: " if f["tuberia"] else "") + f["mensaje"] for f in r["nuevos"][:maximo]]
    if r["resueltos"]:
        p["consecuencias"] = list(p.get("consecuencias") or []) + [
            "Ya cumple la normativa: " + "; ".join(dict.fromkeys(
                (f"{f['tuberia']} ({f['clase'].lower()})" if f["tuberia"] else f["clase"]) for f in r["resueltos"]))[:400]]
    p["normativa_app"] = {"nuevos": len(r["nuevos"]), "resueltos": len(r["resueltos"])}
    return p


def objetivos_pendiente(datos, normas_cat):
    """{handle: {min, max, fuente}}: la pendiente (%) que piden las reglas de la APP a cada tubería de Civil 3D
    (`normas_validar.aplica`: utilidad, tipo y condiciones; mismo alcance = basta una regla, distintos = todos)."""
    from nucleo import normas_catalogo as nc
    from nucleo import normas_validar as NV

    pipes, _est, info = CN.armar(datos)
    por_util = NV.activas(normas_cat)
    out = {}
    for i, p in enumerate(pipes):
        capa = nc.clave(p.get("layer"))
        tipos = {nc.clave(x) for x in nc.tipos_de(normas_cat, capa)}
        dt = NV.datos(i, p, nc.clave(p.get("tipo")) in tipos, CN.FT_PX)
        reglas = [r for r in por_util.get(capa) or [] if r["revisar"] == "pendiente" and NV.aplica(r, dt)]
        mn = mx = None
        fuentes = []
        for g in NV.agrupar(reglas):
            gmin = [r["min"] for r in g if r.get("min") is not None]
            gmax = [r["max"] for r in g if r.get("max") is not None]
            if gmin and len(gmin) == len(g):
                mn = min(gmin) if mn is None else max(mn, min(gmin))
            if gmax and len(gmax) == len(g):
                mx = max(gmax) if mx is None else min(mx, max(gmax))
            fuentes += [r["fuente"] for r in g if r.get("fuente")]
        if mn is None and mx is None:
            continue
        for c in info["origen"][i]:
            out[c["handle"]] = {"min": mn, "max": mx, "fuente": "; ".join(dict.fromkeys(fuentes))}
    return out
