"""Comparar el dibujo de Civil 3D con el proyecto de la app (PURO): qué se cambió a mano en Civil 3D, para no perderlo
al volver a exportar. Herramientas de la APP en el chat «Civil 3D»: `comparar_con_app` y `traer_a_la_app`.

Pareo: cada tubería de Civil 3D lleva su utilidad de la app (Property Set «PDFCAD_Utilidad»: capa + número =
índice + 1 al exportar). Si la capa no coincide con la de la app, los números cambiaron desde esa exportación y no se
compara (se avisa). Por utilidad: diámetro (±`TOL_DIAM_IN`), material, rasantes de punta a punta (±`TOL_COTA_FT`;
el recorrido de Civil 3D puede ir al revés en presión) y largo en planta (±`TOL_LARGO`: si cambió, se movió el
trazo). Diferencias D1…; `traer_a_la_app` las convierte en una propuesta que la VENTANA aplica a la app (un paso de
Ctrl+Z), nunca el modelo.
"""
from __future__ import annotations

from ia.civil3d_normativas import _cadenas, _tabla
from traduccion.i18n_core import t

TOL_DIAM_IN = 0.6               # interior (gravedad) vs nominal (app)
TOL_COTA_FT = 0.01
TOL_LARGO = 0.03                # 3 %: las curvas de Civil 3D acortan un poco
LIMITE = 60


def _mismo_material(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def comparar(datos, pipes, ft_per_px):
    """[diferencia] con {id, pipe, utilidad, campo, app, civil, valor, texto, traer}."""
    from nucleo import model_ops

    por_util = {}
    for c in _tabla(datos.get("tuberias") or {}):
        if c.get("utilidad") and c.get("numero"):
            por_util.setdefault((c["utilidad"], str(c["numero"])), []).append(c)
    out, vistos = [], set()

    def dif(i, util, campo, app, civil, texto, valor=None, traer=True):
        out.append({"pipe": i, "utilidad": util, "campo": campo, "app": app, "civil": civil, "texto": texto,
                    "valor": valor, "traer": traer})

    for (capa, num), tubos in sorted(por_util.items()):
        util = f"{capa}-{num}"
        try:
            i = int(float(num)) - 1
        except ValueError:
            continue
        vistos.add(i)
        if not 0 <= i < len(pipes) or len(pipes[i].get("pts") or []) < 2:
            dif(i, util, "falta_app", "—", "está", t("{u} está en Civil 3D pero no en la app (o se borró).").format(u=util),
                traer=False)
            continue
        p = pipes[i]
        if (p.get("layer") or "").upper() != capa.upper():
            dif(i, util, "numeros", p.get("layer"), capa, t("La utilidad {n} de la app ahora es {a} y en Civil 3D es {c}: los números "
                                                          "cambiaron desde la exportación, no se compara.").format(n=num, a=p.get("layer"), c=capa),
                traer=False)
            continue
        d_app = model_ops.diametro(p)[0]
        d_c3d = max(float(c.get("diam_in") or 0.0) for c in tubos)
        if abs(d_app - d_c3d) > TOL_DIAM_IN:
            dif(i, util, "diam", f'{d_app:g}"', f'{d_c3d:g}"', t('{u}: diámetro {a}" en la app, {c}" en Civil 3D.').format(
                u=util, a=f"{d_app:g}", c=f"{d_c3d:g}"), round(d_c3d, 2))
        mats = {(c.get("material") or "").strip() for c in tubos} - {""}
        if len(mats) == 1:
            m = mats.pop()
            if not _mismo_material(m, p.get("material")) and m.lower() != "material sin definir":
                dif(i, util, "material", p.get("material") or "—", m,
                    t("{u}: material «{a}» en la app, «{c}» en Civil 3D.").format(u=util, a=p.get("material") or "—", c=m), m)
        largo_app = model_ops.largo_planta_ft(p, ft_per_px)
        largo_c3d = sum(float(c.get("largo_ft") or 0.0) for c in tubos)
        if largo_app > 0 and abs(largo_c3d - largo_app) > max(1.0, TOL_LARGO * largo_app):
            dif(i, util, "largo", f"{largo_app:.1f} ft", f"{largo_c3d:.1f} ft",
                t("{u}: el trazo cambió en Civil 3D (largo {a} → {c} ft). Moverlo en planta hay que hacerlo en la app.").format(
                    u=util, a=f"{largo_app:.1f}", c=f"{largo_c3d:.1f}"), traer=False)
        cads = _cadenas(tubos)
        if len(cads) == 1 and all(c.get("cota_ini") is not None and c.get("cota_fin") is not None for c in cads[0]):
            z0, z1 = float(cads[0][0]["cota_ini"]), float(cads[0][-1]["cota_fin"])
            a0, a1 = p.get("inv_start"), p.get("inv_end")
            if a0 is not None and a1 is not None:
                directo = abs(z0 - a0) + abs(z1 - a1)
                reves = abs(z1 - a0) + abs(z0 - a1)
                c0, c1 = (z0, z1) if directo <= reves else (z1, z0)
                for campo, app, civ, nombre in (("inv_start", a0, c0, t("inicio")), ("inv_end", a1, c1, t("fin"))):
                    if abs(app - civ) > TOL_COTA_FT:
                        dif(i, util, campo, f"{app:.2f}", f"{civ:.2f}", t("{u}: rasante de {l} {a} en la app, {c} en Civil 3D.").format(
                            u=util, l=nombre, a=f"{app:.2f}", c=f"{civ:.2f}"), round(civ, 3))
    for i, p in enumerate(pipes):
        if i not in vistos and len(p.get("pts") or []) >= 2 and not p.get("world"):
            out.append({"pipe": i, "utilidad": f"{p.get('layer')}-{i + 1}", "campo": "falta_civil", "app": "está", "civil": "—",
                        "texto": t("{u} está en la app pero no en Civil 3D (¿se borró allá o no se importó?).").format(
                            u=f"{p.get('layer')}-{i + 1}"), "valor": None, "traer": False})
    for k, d in enumerate(out, 1):
        d["id"] = f"D{k}"
    return out


def resumen(difs, limite=LIMITE):
    cols = ["id", "utilidad", "que", "app", "civil", "se_puede_traer"]
    filas = [[d["id"], d["utilidad"], d["texto"], d["app"], d["civil"], d["traer"]] for d in difs[:limite]]
    r = {"total": len(difs), "traibles": sum(1 for d in difs if d["traer"]), "diferencias": {"columnas": cols, "filas": filas}}
    if not difs:
        r["nota"] = t("El dibujo de Civil 3D coincide con el proyecto de la app (diámetros, materiales, rasantes y largos).")
    else:
        r["siguiente"] = t("Para no perder lo cambiado en Civil 3D: traer_a_la_app con los ids D# (o «todas»).")
    return r


def propuesta(difs, ids, pipes):
    """Propuesta para la tarjeta del chat (destino «app»): la aplica la ventana con `aplicar`."""
    quiere = {x.strip().upper() for x in ids or []}
    sel = [d for d in difs if d["traer"] and (not quiere or "TODAS" in quiere or d["id"].upper() in quiere)]
    if not sel:
        return None
    utils = sorted({d["utilidad"] for d in sel})
    return {"id": "APP-" + "-".join(d["id"] for d in sel)[:40], "destino": "app", "tipo": "traer_app",
            "elemento": ", ".join(utils[:4]) + (" " + t("y {n} más").format(n=len(utils) - 4) if len(utils) > 4 else ""),
            "antes": t("proyecto de la app"), "despues": t("como en Civil 3D"),
            "consecuencias": [d["texto"] for d in sel[:10]] + ([t("… y {n} más.").format(n=len(sel) - 10)] if len(sel) > 10 else []),
            "advertencias": [], "cambios": [{k: d[k] for k in ("pipe", "campo", "valor")} for d in sel]}


def aplicar(pipes, cambios):
    """Aplica los cambios a las utilidades de la app (en sitio). Devuelve los índices tocados."""
    from nucleo import edicion3d
    tocados = set()
    for c in cambios:
        i, campo, v = c["pipe"], c["campo"], c["valor"]
        if not 0 <= i < len(pipes) or v is None:
            continue
        p = pipes[i]
        n = len(p.get("pts") or [])
        if campo == "diam":
            p["diam"], p["diam_elegido"] = float(v), True
            p["pipe_size"] = ""            # el tamaño de catálogo era del diámetro anterior: el plugin elige por diámetro
        elif campo == "material":
            p["material"] = v
        elif campo == "inv_start" and n >= 2:
            edicion3d.aplicar_cota(p, 0, "inicio", float(v))
        elif campo == "inv_end" and n >= 2:
            edicion3d.aplicar_cota(p, n - 2, "fin", float(v))
        else:
            continue
        tocados.add(i)
    return sorted(tocados)


def herramientas():
    """Las definiciones que ve el modelo (formato `tools` de Ollama)."""
    return [
        {"type": "function", "function": {
            "name": "comparar_con_app",
            "description": "Compara el dibujo de Civil 3D con el proyecto abierto en la app (el que salió del PDF): "
                           "diámetros, materiales, COTAS (rasantes de inicio y fin), trazo y qué falta en uno u otro. "
                           "Ids D1…",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "traer_a_la_app",
            "description": "Prepara llevar a la app lo cambiado en Civil 3D (diferencias D# de comparar_con_app, o «todas»), "
                           "para no perderlo al exportar otra vez. Lo aplica el usuario con el botón.",
            "parameters": {"type": "object", "properties": {
                "diferencias": {"type": "array", "items": {"type": "string"}, "description": "ids D#, o [\"todas\"]"}}}}},
    ]
