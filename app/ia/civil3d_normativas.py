"""«Revisar normativas» sobre el dibujo de Civil 3D (PURO): la herramienta `revisar_normativas` del chat «Civil 3D».

La revisa la APP, con su mismo validador (`normas_validar`: diámetro, pendiente, largo, material, tipo, quiebres,
buzones, separaciones y accesorios), sobre una copia del modelo armada con lo que da el plugin (`datos_red`). Así
los avisos son los mismos que la app daría con esas utilidades; la IA solo los cuenta y explica.

Armado: las tuberías de Civil 3D de una misma utilidad de la app (Property Set «PDFCAD_Utilidad»: capa + número)
se encadenan punta con punta en una polilínea (como la utilidad de la app: un tramo por tubería, con sus rasantes)
y se parten donde cambia el diámetro, el material o hay una bifurcación. Las coordenadas van en px de
`FT_PX` pies (la escala típica del editor): las tolerancias de la app están en px. Las tuberías que no vienen de la
app (sin utilidad) no tienen normativa: se cuentan aparte.
"""
from __future__ import annotations

import json
import math

from traduccion.i18n_core import t

FT_PX = 0.08                     # pies por px de la copia (≈ 1"=20' a zoom 3.5: tolerancias de 14 px ≈ 1 ft)
UNION_FT = 0.1                   # dos puntas a ≤ esto son el mismo vértice
LIMITE = 40                      # avisos que ve el modelo (los más graves primero)
_SEVERIDAD = {"ERROR": 0, "AVISO": 1, "INFO": 2}


def _tabla(d):
    cols = d.get("columnas") or []
    return [dict(zip(cols, f)) for f in d.get("filas") or []]


def _clave_xy(x, y):
    return (round(x / UNION_FT), round(y / UNION_FT))


def _cadenas(tubos):
    """Recorridos punta con punta de una utilidad (cada tubo en uno solo). Se cortan en bifurcaciones y donde
    cambian diámetro o material."""
    grado = {}
    for c in tubos:
        for k in (_clave_xy(c["x_ini"], c["y_ini"]), _clave_xy(c["x_fin"], c["y_fin"])):
            grado[k] = grado.get(k, 0) + 1
    por_ini = {}
    for c in tubos:
        por_ini.setdefault(_clave_xy(c["x_ini"], c["y_ini"]), []).append(c)
    usados, out = set(), []

    def mismo(a, b):
        return (abs((a.get("diam_in") or 0) - (b.get("diam_in") or 0)) < 1e-6
                and (a.get("material") or "") == (b.get("material") or ""))

    # empiezan donde nadie llega (o en una bifurcación); luego lo que quede (lazos)
    llegan = {_clave_xy(c["x_fin"], c["y_fin"]) for c in tubos}
    orden = sorted(tubos, key=lambda c: (_clave_xy(c["x_ini"], c["y_ini"]) in llegan
                                         and grado[_clave_xy(c["x_ini"], c["y_ini"])] == 2))
    for c in orden:
        if c["handle"] in usados:
            continue
        cad = [c]
        usados.add(c["handle"])
        while True:
            k = _clave_xy(cad[-1]["x_fin"], cad[-1]["y_fin"])
            sig = [x for x in por_ini.get(k, []) if x["handle"] not in usados]
            if grado.get(k, 0) != 2 or len(sig) != 1 or not mismo(cad[-1], sig[0]):
                break
            cad.append(sig[0])
            usados.add(sig[0]["handle"])
        out.append(cad)
    return out


def armar(datos):
    """(pipes de la app, structures, origen) con `origen[i]` = las tuberías de Civil 3D de la utilidad i y
    `sin_utilidad` = cuántas tuberías no vienen de la app."""
    tubos = _tabla(datos.get("tuberias") or {})
    grupos, sueltas = {}, 0
    for c in tubos:
        if not c.get("utilidad") or not c.get("numero"):
            sueltas += 1
            continue
        if None in (c.get("x_ini"), c.get("y_ini"), c.get("x_fin"), c.get("y_fin")):
            continue
        grupos.setdefault((c["utilidad"], str(c["numero"])), []).append(c)
    pipes, origen = [], []
    for (capa, _num), lista in sorted(grupos.items()):
        for cad in _cadenas(lista):
            pts = [(cad[0]["x_ini"] / FT_PX, cad[0]["y_ini"] / FT_PX)] + [(c["x_fin"] / FT_PX, c["y_fin"] / FT_PX) for c in cad]
            p = {"layer": capa, "tipo": cad[0].get("tipo") or "", "material": cad[0].get("material") or "",
                 "diam": float(cad[0].get("diam_in") or 0.0), "diam_elegido": True, "pts": pts}
            if all(c.get("cota_ini") is not None and c.get("cota_fin") is not None for c in cad):
                p["inv_start"], p["inv_end"] = float(cad[0]["cota_ini"]), float(cad[-1]["cota_fin"])
                p["vertex_inv_out"] = {k: float(c["cota_ini"]) for k, c in enumerate(cad) if k > 0}
                p["vertex_inv_in"] = {k + 1: float(c["cota_fin"]) for k, c in enumerate(cad[:-1])}
            pipes.append(p)
            origen.append(cad)
    estructuras = []
    for e in _tabla(datos.get("estructuras") or {}):
        if e.get("x") is None or e.get("y") is None:
            continue
        s = {"x": e["x"] / FT_PX, "y": e["y"] / FT_PX, "hidden": bool(e.get("nula")), "part_size": e.get("tamano") or ""}
        if e.get("rim") is not None:
            s["rim"] = e["rim"]
        if e.get("sump") is not None:
            s["sump"] = e["sump"]
        estructuras.append(s)
    return pipes, estructuras, {"origen": origen, "sin_utilidad": sueltas, "tuberias": len(tubos)}


def _tuberia_en(cad, x, y):
    """La tubería de Civil 3D de la cadena más cercana al punto (px de la copia)."""
    def dist(c):
        ax, ay, bx, by = c["x_ini"] / FT_PX, c["y_ini"] / FT_PX, c["x_fin"] / FT_PX, c["y_fin"] / FT_PX
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        return math.hypot(ax + u * dx - x, ay + u * dy - y)
    return min(cad, key=dist) if cad else None


def filas(datos, normas_cat):
    """(avisos de normativa de la APP como filas, nº «sin tipo», info del armado). Los más graves primero."""
    from nucleo import accesorios as acc_mod
    from nucleo import model_ops, normas_validar

    pipes, estructuras, info = armar(datos)

    def z_at(i, k, x, y):
        return model_ops.z_en_tramo(pipes[i], k, x, y)

    accs = acc_mod.accesorios(pipes, z_at, FT_PX)
    out, sin_tipo = [], 0
    for a in normas_validar.validar(normas_cat, pipes, accs, FT_PX, (), estructuras, ()):
        if a.clase == "tipo":                  # «sin tipo»: como en el plano, se cuenta aparte (serían cientos)
            sin_tipo += 1
            continue
        cad = info["origen"][a.pipe] if 0 <= a.pipe < len(info["origen"]) else []
        tub = _tuberia_en(cad, a.x, a.y)
        out.append({"nivel": "INFO" if a.info else a.nivel, "clase": t(normas_validar.CLASES.get(a.clase, a.clase)),
                    "capa": cad[0]["utilidad"] if cad else "",
                    "utilidad": f"{cad[0]['utilidad']}-{cad[0]['numero']}" if cad else "",
                    "tuberia": tub["nombre"] if tub else "", "red": (tub or {}).get("red") or "",
                    "mensaje": a.mensaje, "fuente": a.fuente, "x": round(a.x * FT_PX, 2), "y": round(a.y * FT_PX, 2)})
    out.sort(key=lambda f: _SEVERIDAD.get(f["nivel"], 1))
    return out, sin_tipo, info


def revisar(datos, normas_cat, utilidad=None, red=None, limite=LIMITE):
    """Avisos de normativa del dibujo, como dict listo para el modelo."""
    if not (normas_cat or {}).get("reglas"):
        return {"error": t("La app no tiene normativas cargadas.")}
    todas, sin_tipo, info = filas(datos, normas_cat)
    pedida = (utilidad or "").strip().upper()
    sel = [f for f in todas if (not pedida or pedida in (f["utilidad"].upper(), f["capa"].upper()))
              and (not red or f["red"].upper() == red.strip().upper())]
    for k, f in enumerate(sel, 1):
        f["id"] = f"N{k}"
    por_clase = {}
    for f in sel:
        if f["nivel"] != "INFO":
            por_clase[f["clase"]] = por_clase.get(f["clase"], 0) + 1
    cols = ["id", "nivel", "clase", "utilidad", "tuberia", "mensaje", "fuente"]
    out = {"total": len(sel), "por_clase": por_clase,
           "avisos": {"columnas": cols, "filas": [[f[c] for c in cols] for f in sel[:limite]]},
           "revisadas": t("{u} utilidades de la app ({n} tuberías de Civil 3D)").format(
               u=len({(c[0]["utilidad"], c[0]["numero"]) for c in info["origen"]}), n=info["tuberias"] - info["sin_utilidad"])}
    if len(sel) > limite:
        out["nota"] = t("Hay {n} avisos más: filtrar por utilidad o red.").format(n=len(sel) - limite)
    if sin_tipo:
        out["sin_tipo"] = t("{n} utilidades sin tipo (o con un tipo que ya no existe): sus reglas por tipo no se "
                            "revisan.").format(n=sin_tipo)
    if info["sin_utilidad"]:
        out["sin_utilidad"] = t("{n} tuberías no vienen de la app (sin utilidad): no tienen normativa.").format(
            n=info["sin_utilidad"])
    out["siguiente"] = t("Para pendientes: proponer_pendiente. Para diámetro o material: proponer_tamano. "
                         "Para choques y separaciones: buscar_conflictos.")
    return out


def herramienta():
    """La definición que ve el modelo (formato `tools` de Ollama)."""
    return {"type": "function", "function": {
        "name": "revisar_normativas",
        "description": ("Revisa el dibujo contra las normativas de la app (diámetros, pendientes, largos, materiales, "
                        "tipos, buzones, accesorios y separaciones). Devuelve los avisos N1… con la tubería y el motivo."),
        "parameters": {"type": "object", "properties": {
            "utilidad": {"type": "string", "description": "solo esa utilidad, p. ej. AGUA-20 o AGUA (opcional)"},
            "red": {"type": "string", "description": "solo esa red (opcional)"}}}}}

