"""Revisión de las utilidades contra las normativas en tablas (PURO: sin Qt).

`validar(cat, pipes, accesorios, ft_per_px)` → [Aviso]. Solo AVISA (nunca cambia nada):

  • Tipo: la utilidad tiene tipos en el catálogo y no eligió ninguno → «elige su tipo».
  • Diámetros (PRESION-DIAMETROS): el diámetro tiene que estar en la lista de SU tipo;
    si está en la de otro tipo, se dice de cuál (un diámetro de domiciliaria en una
    principal). Si la fila trae una condición propia en «SOLO SE PERMITE EN» (cul-de-sacs),
    va como mensaje informativo.
  • Eléctrico y telecom (ELECT-TELECOM): filas de su tipo (o sin tipo = todas); las que
    piden amperaje necesitan el número (si falta, aviso) y la longitud se mide sola;
    la fila que encaja fija el diámetro (fijo, mínimo, máximo). Con bancoducto no se
    revisa (los bancoductos quedaron para después).
  • Accesorios de presión (PRESION-ACCESORIOS, sobre `accesorios.accesorios`): «solo se
    permite en» / «prohibido» según el tipo de la línea PRINCIPAL (en el CODO «solo se
    permite en» es dónde se exigen sus ángulos: en otro tipo vale cualquiera); diámetro principal de
    la lista; ramal «-1» = un tamaño menor en esa lista (la principal de 6" no tiene menor:
    aviso); ángulos del codo (±1°). Una T cuyo RAMAL es de instalación domiciliaria se
    revisa SOLO con la fila «T - Domiciliaria» (diámetro del ramal de su lista).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from nucleo import accesorios as acc
from nucleo import model_ops
from nucleo import normas_catalogo as nc
from traduccion.i18n_core import N_, t

TOL_ANGULO = 1.0
TOL_DIAM = 0.01
DOMICILIARIA = "INSTALACION DOMICILIARIA"

CLASES = {
    "tipo": N_("Tipo de utilidad"),
    "diametro": N_("Diámetro"),
    "electrico": N_("Diámetro según amperaje y largo"),
    "accesorio": N_("Accesorio"),
    "nota": N_("Condición de uso"),
}
NOMBRE_ACC = {"codo": N_("Codo"), "tee": N_("Tee"), "wye": N_("Wye"), "cruz": N_("Cruz"),
              "tee_dom": N_("T domiciliaria")}


@dataclass
class Aviso:
    x: float
    y: float
    clase: str                       # CLASES
    mensaje: str
    pipe: int = -1                   # utilidad (o la principal del accesorio)
    info: bool = False               # True = solo informativo (no es un incumplimiento)


def _largo_px(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _medio(pts):
    falta = _largo_px(pts) / 2.0
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L >= falta and L > 0:
            k = falta / L
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        falta -= L
    return tuple(pts[0])


def _en(valor, lista):
    return any(abs(valor - v) <= TOL_DIAM for v in lista)


def _txt_lista(nums):
    return ", ".join(nc.texto_pulgadas(n) for n in nums)


def _tipo(p):
    return nc.clave(p.get("tipo"))


def _dice_lo_mismo(nota, tipo):
    """«TUBERIA DE DISTRIBUCION PRINCIPAL» repite el tipo; «CALLES SIN SALIDA…» no.
    Singular y plural cuentan igual («INSTALACIONES DOMICILIARIAS»)."""
    def raiz(w):
        return w[:-2] if w.endswith("ES") and len(w) > 4 else w[:-1] if w.endswith("S") else w

    def raices(s):
        return {raiz(w) for w in nc.clave(s).split() if len(w) > 2}
    return bool(raices(tipo)) and raices(tipo) <= raices(nota)


# ─────────────────────────── por utilidad ───────────────────────────

def _revisar_tipo(cat, p, i, xy, out):
    tipos = nc.tipos_de(cat, p.get("layer"))
    if not tipos:
        return False
    if not _tipo(p):
        out.append(Aviso(*xy, "tipo", t("Sin tipo: elige su tipo para revisar sus normativas."), i))
        return False
    if _tipo(p) not in {nc.clave(x) for x in tipos}:
        out.append(Aviso(*xy, "tipo", t("El tipo «{tipo}» ya no está en la lista de tipos.").format(
            tipo=p.get("tipo")), i))
        return False
    return True


def _revisar_diametro(cat, p, i, xy, out):
    u = nc.clave(p.get("layer"))
    filas = [f for f in cat.get("diametros", []) if nc.clave(f["utilidad"]) == u and f["diametros"]]
    if not filas:
        return
    d, defecto = model_ops.diametro(p)
    tipo = _tipo(p)
    propias = [f for f in filas if nc.clave(f["tipo"]) == tipo]
    if not propias:
        return
    permitidos = sorted({v for f in propias for v in f["diametros"]})
    d_txt = nc.texto_pulgadas(d) + (" " + t("(por defecto)") if defecto else "")
    if not _en(d, permitidos):
        otros = [f for f in filas if nc.clave(f["tipo"]) != tipo and _en(d, f["diametros"])]
        if otros:
            msg = t("Diámetro {d}: es de «{otro}» y esta utilidad es «{tipo}». Para su tipo: {lista}.").format(
                d=d_txt, otro=otros[0]["tipo"], tipo=tipo, lista=_txt_lista(permitidos))
        else:
            msg = t("Diámetro {d} no permitido para «{tipo}». Permitidos: {lista}.").format(
                d=d_txt, tipo=tipo, lista=_txt_lista(permitidos))
        out.append(Aviso(*xy, "diametro", msg, i))
        return
    for f in propias:
        nota = (f.get("nota") or "").strip()
        if _en(d, f["diametros"]) and nota and not _dice_lo_mismo(nota, tipo):
            out.append(Aviso(*xy, "nota", t("Diámetro {d}: solo se permite en {nota}.").format(d=d_txt, nota=nota),
                             i, info=True))
            break


def _cumple_rango(v, r):
    return r is None or (v is not None and r[0] - 1e-9 <= v <= r[1] + 1e-9)


def _revisar_electrico(cat, p, i, xy, largo_ft, con_bancoducto, out):
    u = nc.clave(p.get("layer"))
    tipo = _tipo(p)
    filas = [f for f in cat.get("electricas", []) if nc.clave(f["utilidad"]) == u
             and (not f.get("tipo") or nc.clave(f["tipo"]) == tipo)]
    if con_bancoducto:
        filas = [f for f in filas if nc.clave(f.get("estructura")) not in ("", "SIMPLE")]
    if not filas:
        return
    if any(f.get("amperaje") for f in filas) and p.get("amperaje") in (None, ""):
        out.append(Aviso(*xy, "electrico", t("Falta el amperaje: escríbelo para revisar su diámetro."), i))
        return
    amp = nc.numero(p.get("amperaje"))
    d, defecto = model_ops.diametro(p)
    d_txt = nc.texto_pulgadas(d) + (" " + t("(por defecto)") if defecto else "")
    for f in filas:
        if not (_cumple_rango(amp, f.get("amperaje")) and _cumple_rango(largo_ft, f.get("longitud"))):
            continue
        fijo, dmin, dmax = f.get("diam_fijo") or [], f.get("diam_min"), f.get("diam_max")
        if fijo and not _en(d, fijo):
            req = t("debe ser {lista}").format(lista=_txt_lista(fijo))
        elif dmin is not None and d < dmin - TOL_DIAM:
            req = t("mínimo {d}").format(d=nc.texto_pulgadas(dmin))
        elif dmax is not None and d > dmax + TOL_DIAM:
            req = t("máximo {d}").format(d=nc.texto_pulgadas(dmax))
        else:
            continue
        cond = []
        if f.get("tipo"):
            cond.append(f["tipo"])
        if f.get("amperaje"):
            cond.append(t("{r} A").format(r=nc.texto_rango(f["amperaje"])))
        if f.get("longitud"):
            cond.append(t("{r} ft de largo").format(r=nc.texto_rango(f["longitud"])))
        msg = t("Diámetro {d}: {req}").format(d=d_txt, req=req)
        if cond:
            msg += " (" + ", ".join(cond) + ")"
        out.append(Aviso(*xy, "electrico", msg + ".", i))


# ─────────────────────────── accesorios ───────────────────────────

def _fila_acc(cat, utilidad, tipo_acc):
    for f in cat.get("accesorios", []):
        if nc.clave(f["utilidad"]) == utilidad and nc.ACCESORIOS.get(nc.clave(f["accesorio"])) == tipo_acc:
            return f
    return None


def _revisar_accesorio(cat, pipes, a, out):
    u = nc.clave(a.get("capa"))
    principales = a.get("tronco") or a.get("pipes") or []
    principal = next((j for j in principales if 0 <= j < len(pipes) and _tipo(pipes[j])),
                     principales[0] if principales else -1)
    tipo_p = _tipo(pipes[principal]) if 0 <= principal < len(pipes) else ""
    ramal = a.get("ramal")
    tipo_acc = a["tipo"]
    if tipo_acc == "tee" and ramal is not None and _tipo(pipes[ramal]) == DOMICILIARIA:
        fila = _fila_acc(cat, u, "tee_dom")
        if fila and fila.get("diam_principal"):
            d = model_ops.diametro(pipes[ramal])[0]
            if not _en(d, fila["diam_principal"]):
                out.append(Aviso(a["x"], a["y"], "accesorio", t(
                    "T domiciliaria: el ramal debe ser {lista}; es {d}.").format(
                        lista=_txt_lista(fila["diam_principal"]), d=nc.texto_pulgadas(d)), ramal))
        return
    fila = _fila_acc(cat, u, tipo_acc)
    if fila is None:
        return
    nombre = t(NOMBRE_ACC[tipo_acc])
    xy = (a["x"], a["y"])
    if fila.get("prohibido_en") and tipo_p == nc.clave(fila["prohibido_en"]):
        out.append(Aviso(*xy, "accesorio", t("{acc} no permitida en «{tipo}».").format(acc=nombre, tipo=tipo_p),
                         principal))
        return
    if fila.get("solo_en"):
        if not tipo_p:
            return                                   # sin tipo: ya avisa la utilidad
        if tipo_p != nc.clave(fila["solo_en"]):
            if tipo_acc == "codo":
                return                               # codo: en otros tipos vale cualquier ángulo
            out.append(Aviso(*xy, "accesorio", t("{acc} solo se permite en «{tipo}».").format(
                acc=nombre, tipo=fila["solo_en"]), principal))
            return
    lista = sorted(fila.get("diam_principal") or [])
    d = model_ops.diametro(pipes[principal])[0] if 0 <= principal < len(pipes) else None
    if lista and d is not None and not _en(d, lista):
        out.append(Aviso(*xy, "accesorio", t("{acc}: la principal debe ser {lista}; es {d}.").format(
            acc=nombre, lista=_txt_lista(lista), d=nc.texto_pulgadas(d)), principal))
        return
    if fila.get("ramal") is not None and ramal is not None and lista and d is not None:
        k = next((n for n, v in enumerate(lista) if abs(v - d) <= TOL_DIAM), None)
        destino = (k + int(fila["ramal"])) if k is not None else None
        dr = model_ops.diametro(pipes[ramal])[0]
        if destino is None or not 0 <= destino < len(lista):
            out.append(Aviso(*xy, "accesorio", t("{acc}: no hay un tamaño menor que {d} en {lista} para el ramal.")
                             .format(acc=nombre, d=nc.texto_pulgadas(d), lista=_txt_lista(lista)), ramal))
        elif abs(dr - lista[destino]) > TOL_DIAM:
            out.append(Aviso(*xy, "accesorio", t("{acc}: el ramal debe ser {r} (un tamaño menor que {d}); es {dr}.")
                             .format(acc=nombre, r=nc.texto_pulgadas(lista[destino]), d=nc.texto_pulgadas(d),
                                     dr=nc.texto_pulgadas(dr)), ramal))
    angulos = fila.get("angulos") or []
    if angulos and tipo_acc == "codo" and not any(abs(a["angulo"] - v) <= TOL_ANGULO for v in angulos):
        out.append(Aviso(*xy, "accesorio", t("Codo de {ang}: fuera de norma. Permitidos: {lista}.").format(
            ang=acc.texto_angulo(a["angulo"]), lista=", ".join(acc.texto_angulo(v) for v in angulos)), principal))


# ─────────────────────────── todo ───────────────────────────

def validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto=()):
    """Avisos de todas las utilidades y accesorios. `con_bancoducto` = índices de las
    utilidades que llevan bancoducto (sus filas «SIMPLE» no aplican)."""
    out = []
    if not cat:
        return out
    con_bancoducto = set(con_bancoducto)
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        if p.get("world") or len(pts) < 2:
            continue
        xy = _medio(pts)
        tiene_tipo = _revisar_tipo(cat, p, i, xy, out)
        if tiene_tipo:
            _revisar_diametro(cat, p, i, xy, out)
        if tiene_tipo or not nc.tipos_de(cat, p.get("layer")):
            _revisar_electrico(cat, p, i, xy, _largo_px(pts) * (ft_per_px or 0.0), i in con_bancoducto, out)
    for a in accesorios_ or []:
        _revisar_accesorio(cat, pipes, a, out)
    return out


def en_punto(avisos, x, y, tol):
    """Avisos (no informativos) a ≤ tol del punto."""
    return [a for a in avisos if not a.info and (a.x - x) ** 2 + (a.y - y) ** 2 <= tol * tol]
