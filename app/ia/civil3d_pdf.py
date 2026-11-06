"""Comparar el dibujo de Civil 3D contra el PDF original (PURO): la herramienta `comparar_con_pdf` del chat «Civil 3D».

El PDF está en la app (la hoja de trabajo y su imagen en grises para el imán a la tinta) y la app sabe llevar un punto
del dibujo a la hoja (la MISMA transformación que el DXF exportado, invertida: `a_px`). Para cada tubería y buzón de
Civil 3D se mira si hay TINTA del PDF debajo (a ≤ `TOL_FT`): una tubería con poca tinta debajo se movió o no está en el
plano («sobra»). Y cada utilidad de la app (que salió del PDF) que no tiene tubería de Civil 3D encima «falta».
Ojo: cualquier tinta cuenta (también calles o cotas): es una revisión rápida, no una prueba.

`proyecto` = {"pipes", "ft", "a_px"(x, y) → px de la hoja, "a_mundo"(px, py) → (x, y), "tinta"(px, py, r_px) → bool}.
"""
from __future__ import annotations

import math

from ia.civil3d_normativas import _tabla
from traduccion.i18n_core import t

TOL_FT = 1.0
PASO_FT = 2.0
COBERTURA_MIN = 0.6
LIMITE = 40


def _muestras(ax, ay, bx, by, paso):
    L = math.hypot(bx - ax, by - ay)
    n = max(3, int(L / paso) + 1)
    return [(ax + (bx - ax) * k / (n - 1), ay + (by - ay) * k / (n - 1)) for k in range(n)]


def _cerca_de_tuberia(x, y, tubos, tol):
    for c in tubos:
        ax, ay, bx, by = c["x_ini"], c["y_ini"], c["x_fin"], c["y_fin"]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        if math.hypot(ax + u * dx - x, ay + u * dy - y) <= tol:
            return True
    return False


def comparar(datos, proyecto, tol_ft=TOL_FT):
    """[punto] con {id, tipo (sobra|buzon|falta), elemento, cobertura, x, y, texto}."""
    ft, a_px, tinta = proyecto["ft"], proyecto["a_px"], proyecto["tinta"]
    r_px = max(1.0, tol_ft / ft)
    out = []
    tubos = [c for c in _tabla(datos.get("tuberias") or {}) if None not in (c.get("x_ini"), c.get("y_ini"), c.get("x_fin"), c.get("y_fin"))]
    for c in tubos:
        pts = _muestras(c["x_ini"], c["y_ini"], c["x_fin"], c["y_fin"], PASO_FT)
        hay = [tinta(*a_px(x, y), r_px) for x, y in pts]
        cob = sum(hay) / len(hay)
        if cob >= COBERTURA_MIN:
            continue
        sin = [p for p, h in zip(pts, hay) if not h]
        mx, my = sin[len(sin) // 2]
        out.append({"tipo": "sobra", "elemento": c["nombre"], "cobertura": round(cob * 100), "x": round(mx, 2), "y": round(my, 2),
                    "texto": t("{n}: solo {p} % de su recorrido va sobre el PDF (se movió o no está en el plano).").format(
                        n=c["nombre"], p=round(cob * 100))})
    for e in _tabla(datos.get("estructuras") or {}):
        if e.get("nula") or e.get("x") is None:
            continue
        if not tinta(*a_px(e["x"], e["y"]), r_px * 2):
            out.append({"tipo": "buzon", "elemento": e["nombre"], "cobertura": 0, "x": round(e["x"], 2), "y": round(e["y"], 2),
                        "texto": t("{n}: no hay nada dibujado en el PDF donde está.").format(n=e["nombre"])})
    # lo del PDF (las utilidades de la app) que no está en Civil 3D
    a_mundo = proyecto.get("a_mundo")
    for i, p in enumerate(proyecto.get("pipes") or []):
        pts = p.get("pts") or []
        if a_mundo is None or len(pts) < 2 or p.get("world"):
            continue
        muestras = []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            muestras += _muestras(ax, ay, bx, by, PASO_FT / ft)
        mundo = [a_mundo(x, y) for x, y in muestras]
        dentro = [_cerca_de_tuberia(x, y, tubos, tol_ft * 2) for x, y in mundo]
        cob = sum(dentro) / len(dentro)
        if cob < COBERTURA_MIN:
            fuera = [m for m, d in zip(mundo, dentro) if not d]
            mx, my = fuera[len(fuera) // 2]
            nombre = f"{p.get('layer')}-{i + 1}"
            out.append({"tipo": "falta", "elemento": nombre, "cobertura": round(cob * 100), "x": round(mx, 2), "y": round(my, 2),
                        "texto": t("{n} está en el PDF (la app) pero solo {p} % tiene tubería en Civil 3D.").format(
                            n=nombre, p=round(cob * 100))})
    out.sort(key=lambda d: (-d["y"], d["x"]))
    for k, d in enumerate(out, 1):
        d["id"] = f"P{k}"
    return out


def resumen(puntos, limite=LIMITE):
    cols = ["id", "tipo", "elemento", "cobertura_pct", "x", "y", "que"]
    r = {"total": len(puntos), "por_tipo": {k: sum(1 for p in puntos if p["tipo"] == k) for k in ("sobra", "buzon", "falta")},
         "puntos": {"columnas": cols, "filas": [[p["id"], p["tipo"], p["elemento"], p["cobertura"], p["x"], p["y"], p["texto"]]
                                                 for p in puntos[:limite]]},
         "nota": t("Revisión rápida: cualquier tinta del PDF cuenta (calles, cotas). Para ver un punto: ir_a con su elemento.")
         + " " + t("Solo planta: las cotas (rasantes) se comparan con comparar_con_app.")}
    if not puntos:
        r["nota"] = t("Todo lo de Civil 3D va sobre el PDF y todo lo del PDF (la app) está en Civil 3D.")
    return r


def herramienta():
    return {"type": "function", "function": {
        "name": "comparar_con_pdf",
        "description": "Pone el dibujo de Civil 3D sobre el PDF original (el de la app) y marca lo que sobra (tuberías o buzones "
                       "sin nada del PDF debajo) y lo que falta (lo del PDF sin tubería en Civil 3D). Solo la PLANTA: el PDF no trae "
                       "elevaciones; las cotas (rasantes) se comparan con comparar_con_app. Ids P1…",
        "parameters": {"type": "object", "properties": {
            "tolerancia_ft": {"type": "number", "description": "distancia máxima a la tinta (defecto 1 ft)"}}}}}
