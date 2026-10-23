"""Accesorios contra la tabla de reglas (PURO). Los detecta `accesorios.accesorios` (redes a presión): codo,
Tee, Wye y cruz, con su línea PRINCIPAL (tronco) y su RAMAL. Una T cuyo ramal es de instalación domiciliaria
es el elemento «T - DOMICILIARIA» (solo sus reglas). El TIPO de una regla es el de la principal.

En orden, como siempre: «Se permite» NO → no permitida (y nada más); «Solo en tipos» → solo en esos (sin tipo
en la principal no se juzga: ya avisa la utilidad); diámetro de la principal (si falla, no se mira el ramal);
ramal (diámetro, tamaños o pulgadas menos que la principal); ángulo (codo: deflexión; T/Y: el del ramal).
"""
from __future__ import annotations

from nucleo import accesorios as acc
from nucleo import normas_catalogo as nc
from nucleo import normas_reglas as NR
from nucleo import normas_validar as V
from traduccion.i18n_core import t

_ELEMENTO = {"wye": NR.Y, "tee": NR.T, "cruz": NR.CRUZ, "codo": NR.CODO}


def _txt(nums):
    return ", ".join(nc.texto_pulgadas(n) for n in nums)


def _diametros(grupo):
    """«6", 8", 12"» si el grupo es solo una lista de diámetros; si no, lo que pide («mínimo 4"»)."""
    if all(r.get("valores") and r.get("min") is None and r.get("max") is None for r in grupo):
        return _txt(sorted({v for r in grupo for v in r["valores"]}))
    return V.requisito_grupo(grupo)


def _grupos(por_util, u, elemento, tipo_p, memo):
    """{revisar: [grupos de reglas]} de ese accesorio con esa principal, una vez por combinación (los
    accesorios se cuentan por miles y se repiten)."""
    k = (u, elemento, tipo_p)
    if k not in memo:
        por = {}
        for r in por_util.get(u) or []:
            if r["elemento"] == elemento and (not r.get("tipo") or r["tipo"] == tipo_p):
                por.setdefault(r["revisar"], []).append(r)
        memo[k] = {c: V.agrupar(rs) for c, rs in por.items()}
    return memo[k]


def revisar(por_util, pipes, todos, a, out, memo=None):
    u = nc.clave(a.get("capa"))
    reglas = por_util.get(u) or []
    if not reglas or a.get("tipo") not in _ELEMENTO:
        return
    principales = a.get("tronco") or a.get("pipes") or []
    principal = next((j for j in principales if 0 <= j < len(pipes) and V._tipo(pipes[j])),
                     principales[0] if principales else -1)
    tipo_p = V._tipo(pipes[principal]) if 0 <= principal < len(pipes) else ""
    ramal = a.get("ramal")
    elemento = _ELEMENTO[a["tipo"]]
    if a["tipo"] == "tee" and ramal is not None and 0 <= ramal < len(pipes) \
            and V._tipo(pipes[ramal]) == V.DOMICILIARIA:
        elemento = NR.T_DOM
    grupos = _grupos(por_util, u, elemento, tipo_p, {} if memo is None else memo)
    if not grupos:
        return
    nombre = t(V.NOMBRE_ACC["tee_dom" if elemento == NR.T_DOM else a["tipo"]])
    xy = (a["x"], a["y"])

    def de(clave):
        return grupos.get(clave) or []

    for grupo in de("permitido"):
        if any(nc.clave(r["valores"][0]) == NR.NO for r in grupo if r.get("valores")):
            donde = grupo[0].get("tipo") or u
            out.append(V.aviso(*xy, "accesorio", t("{acc} no permitida en «{tipo}».").format(acc=nombre, tipo=donde),
                               principal, grupo))
            return
    for grupo in de("solo_en"):
        if not tipo_p:
            return                                       # sin tipo: ya avisa la utilidad
        tipos = [x for r in grupo for x in r.get("valores") or []]
        if tipo_p not in {nc.clave(x) for x in tipos}:
            out.append(V.aviso(*xy, "accesorio", t("{acc} solo se permite en {tipos}.").format(
                acc=nombre, tipos=(" " + t("o") + " ").join(f"«{x}»" for x in dict.fromkeys(tipos))), principal, grupo))
            return
    d = V.model_ops.diametro(pipes[principal])[0] if 0 <= principal < len(pipes) else None
    lista_p = sorted({v for g in de("diam_principal") for r in g for v in r.get("valores") or []})
    for grupo in de("diam_principal"):
        if d is not None and not V.cumple_grupo(grupo, d):
            out.append(V.aviso(*xy, "accesorio", t("{acc}: la principal debe ser {req}; es {d}.").format(
                acc=nombre, req=_diametros(grupo), d=nc.texto_pulgadas(d)),
                principal, grupo))
            return
    dr = V.model_ops.diametro(pipes[ramal])[0] if ramal is not None and 0 <= ramal < len(pipes) else None
    if dr is not None:
        for grupo in de("diam_ramal"):
            if not V.cumple_grupo(grupo, dr):
                etq = t("T domiciliaria") if elemento == NR.T_DOM else nombre
                out.append(V.aviso(*xy, "accesorio", t("{acc}: el ramal debe ser {req}; es {d}.").format(
                    acc=etq, req=_diametros(grupo),
                    d=nc.texto_pulgadas(dr)), ramal, grupo))
        if d is not None:
            for grupo in de("ramal_pasos"):
                _pasos(grupo, nombre, xy, d, dr, lista_p, ramal, out)
            for grupo in de("ramal_menos"):
                if not V.cumple_grupo(grupo, d - dr):
                    out.append(V.aviso(*xy, "accesorio", t(
                        "{acc}: el ramal ({dr}) va {v} menos que la principal ({d}): {req}.").format(
                        acc=nombre, dr=nc.texto_pulgadas(dr), d=nc.texto_pulgadas(d), v=nc.texto_pulgadas(d - dr),
                        req=V.requisito_grupo(grupo)), ramal, grupo))
    ang = a.get("angulo")
    for grupo in de("angulo"):
        if ang is not None and not V.cumple_grupo(grupo, ang):
            if a["tipo"] == "codo":
                msg = t("Codo de {ang}: fuera de norma. Permitidos: {lista}.")
            else:
                msg = t("{acc}: ramal a {ang}, fuera de norma. Permitidos: {lista}.")
            vals = [v for r in grupo for v in r.get("valores") or []]
            lista = ", ".join(acc.texto_angulo(v) for v in vals) if vals else V.requisito_grupo(grupo)
            out.append(V.aviso(*xy, "accesorio", msg.format(acc=nombre, ang=acc.texto_angulo(ang), lista=lista),
                               principal, grupo))


def _pasos(grupo, nombre, xy, d, dr, lista, ramal, out):
    """«-1» = un tamaño menor que la principal en la lista de «Diámetro de la principal»."""
    if not lista:
        return
    paso = int(grupo[0]["valores"][0]) if grupo[0].get("valores") else -1
    k = next((n for n, v in enumerate(lista) if abs(v - d) <= V.TOL["diametro"]), None)
    destino = (k + paso) if k is not None else None
    if destino is None or not 0 <= destino < len(lista):
        out.append(V.aviso(*xy, "accesorio", t("{acc}: no hay un tamaño menor que {d} en {lista} para el ramal.")
                           .format(acc=nombre, d=nc.texto_pulgadas(d), lista=_txt(lista)), ramal, grupo))
    elif abs(dr - lista[destino]) > V.TOL["diametro"]:
        out.append(V.aviso(*xy, "accesorio", t("{acc}: el ramal debe ser {r} (un tamaño menor que {d}); es {dr}.")
                           .format(acc=nombre, r=nc.texto_pulgadas(lista[destino]), d=nc.texto_pulgadas(d),
                                   dr=nc.texto_pulgadas(dr)), ramal, grupo))
