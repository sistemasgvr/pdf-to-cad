"""Revisión de las utilidades contra las normativas en tablas (PURO: sin Qt).

`validar(cat, pipes, accesorios, ft_per_px)` → [Aviso]. Solo AVISA (nunca cambia nada):

  • Tipo: la utilidad tiene tipos en el catálogo y no eligió ninguno → «elige su tipo».
  • Diámetros (PRESION-DIAMETROS): el diámetro tiene que estar en la lista de SU tipo o
    dentro de su rango MIN–MAX (2026-10-14: gas «de 0,5 a 2»);
    si está en la de otro tipo, se dice de cuál (un diámetro de domiciliaria en una
    principal). Si la fila trae una condición propia en «SOLO SE PERMITE EN» (cul-de-sacs),
    va como mensaje informativo.
  • Eléctrico y telecom (ELECT-TELECOM): filas de su tipo (o sin tipo = todas); las que
    piden amperaje necesitan el número (si falta, aviso) y la longitud se mide sola;
    la fila que encaja fija el diámetro (fijo, mínimo, máximo). Con bancoducto no se
    revisa (los bancoductos quedaron para después). Amperaje y longitud son rangos MIN–MAX
    (un extremo vacío = sin límite: «400 o más»). RADIO CURVA: cada curva de la línea (su
    radio, o el automático) tiene que ser uno de los FIJOS (Excel v4: «3; 4») y caer en
    MIN–MAX (aviso en la curva).
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
    "radio": N_("Radio de curva"),
    "angulo": N_("Ángulo fuera del paso de 0.25°"),
    "grosor": N_("Diámetro del plano"),          # nucleo/diametro_plano: no se encontró o es dudoso
}
NOMBRE_ACC = {"codo": N_("Codo"), "tee": N_("Tee"), "wye": N_("Wye"), "cruz": N_("Cruz"),
              "tee_dom": N_("T domiciliaria"), "reduccion": N_("Reducción")}


@dataclass
class Aviso:
    x: float
    y: float
    clase: str                       # CLASES
    mensaje: str
    pipe: int = -1                   # utilidad (o la principal del accesorio)
    info: bool = False               # True = solo informativo (no es un incumplimiento)
    aprobado: object = None          # registro de aprobación (normas_aprobacion) o None = pendiente


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


def _rango_diam(f):
    return nc.rango_min_max(f.get("diam_min"), f.get("diam_max"))


def _permite(f, d):
    """¿La fila de PRESION-DIAMETROS admite el diámetro d (por su lista o por su rango)?"""
    r = _rango_diam(f)
    return _en(d, f.get("diametros") or []) or (r is not None and nc.en_rango(d, r, TOL_DIAM))


def _tiene_diam(f):
    return bool(f.get("diametros")) or _rango_diam(f) is not None


def _txt_permitidos(filas):
    """«6", 8", 12"» + rangos «0,5"–2"», «≥ 4"»."""
    partes = [_txt_lista(sorted({v for f in filas for v in f.get("diametros") or []}))]
    for f in filas:
        r = _rango_diam(f)
        if r is None:
            continue
        if r[1] is None:
            partes.append("≥ " + nc.texto_pulgadas(r[0]))
        elif r[0] is None:
            partes.append("≤ " + nc.texto_pulgadas(r[1]))
        else:
            partes.append(f"{nc.texto_pulgadas(r[0])}–{nc.texto_pulgadas(r[1])}")
    return ", ".join(p for p in partes if p)


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

def _revisar_tipo(cat, p, i, xy, out, de_capa=None):
    """`de_capa` = (tipos, sus claves) de la capa, si ya se calcularon."""
    tipos, claves = de_capa if de_capa is not None else _tipos_de_capa(cat, p.get("layer"))
    if not tipos:
        return False
    if not _tipo(p):
        out.append(Aviso(*xy, "tipo", t("Sin tipo: elige su tipo para revisar sus normativas."), i))
        return False
    if _tipo(p) not in claves:
        out.append(Aviso(*xy, "tipo", t("El tipo «{tipo}» ya no está en la lista de tipos.").format(
            tipo=p.get("tipo")), i))
        return False
    return True


def _tipos_de_capa(cat, capa):
    tipos = nc.tipos_de(cat, capa)
    return tipos, {nc.clave(x) for x in tipos}


def _revisar_diametro(cat, p, i, xy, out):
    u = nc.clave(p.get("layer"))
    filas = [f for f in cat.get("diametros", []) if nc.clave(f["utilidad"]) == u and _tiene_diam(f)]
    if not filas:
        return
    d, defecto = model_ops.diametro(p)
    tipo = _tipo(p)
    propias = [f for f in filas if nc.clave(f["tipo"]) == tipo]
    if not propias:
        return
    permitidos = _txt_permitidos(propias)
    d_txt = nc.texto_pulgadas(d) + (" " + t("(por defecto)") if defecto else "")
    if not any(_permite(f, d) for f in propias):
        otros = [f for f in filas if nc.clave(f["tipo"]) != tipo and _permite(f, d)]
        if otros:
            msg = t("Diámetro {d}: es de «{otro}» y esta utilidad es «{tipo}». Para su tipo: {lista}.").format(
                d=d_txt, otro=otros[0]["tipo"], tipo=tipo, lista=permitidos)
        else:
            msg = t("Diámetro {d} no permitido para «{tipo}». Permitidos: {lista}.").format(
                d=d_txt, tipo=tipo, lista=permitidos)
        out.append(Aviso(*xy, "diametro", msg, i))
        return
    for f in propias:
        nota = (f.get("nota") or "").strip()
        if _permite(f, d) and nota and not _dice_lo_mismo(nota, tipo):
            out.append(Aviso(*xy, "nota", t("Diámetro {d}: solo se permite en {nota}.").format(d=d_txt, nota=nota),
                             i, info=True))
            break


def _cumple_rango(v, r):
    return nc.en_rango(v, r)


def _revisar_radios(p, i, f, curvas, cond, out):
    """Cada curva de la línea con su radio (o el automático) dentro de RADIO CURVA MIN/MAX."""
    r = nc.rango_min_max(f.get("radio_min"), f.get("radio_max"))
    fijos = f.get("radio_fijo") or []
    if r is None and not fijos:
        return
    for s in curvas:
        radio = float(s.get("radius_ft") or 0.0)
        auto = radio <= 0.01
        if auto:
            radio = model_ops.radio_auto_ft(p)
        if fijos and not any(abs(radio - v) <= 0.005 for v in fijos):
            req = t("debe ser {lista}").format(lista=", ".join(f"{nc.texto_numero(v)} ft" for v in fijos))
        elif r is not None and not nc.en_rango(radio, r, 0.005):
            req = (t("mínimo {r} ft").format(r=nc.texto_numero(r[0])) if r[0] is not None and radio < r[0]
                   else t("máximo {r} ft").format(r=nc.texto_numero(r[1])))
        else:
            continue
        txt = nc.texto_numero(round(radio, 2)) + (" " + t("(automático)") if auto else "")
        msg = t("Curva de radio {r} ft: {req}").format(r=txt, req=req)
        if cond:
            msg += " (" + ", ".join(cond) + ")"
        out.append(Aviso(s["x"], s["y"], "radio", msg + ".", i))


def _revisar_electrico(cat, p, i, xy, largo_ft, con_bancoducto, out, curvas=()):
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
        cond = []
        if f.get("tipo"):
            cond.append(f["tipo"])
        if f.get("amperaje"):
            cond.append(t("{r} A").format(r=nc.texto_rango(f["amperaje"])))
        if f.get("longitud"):
            cond.append(t("{r} ft de largo").format(r=nc.texto_rango(f["longitud"])))
        _revisar_radios(p, i, f, curvas, cond, out)
        if fijo and not _en(d, fijo):
            req = t("debe ser {lista}").format(lista=_txt_lista(fijo))
        elif dmin is not None and d < dmin - TOL_DIAM:
            req = t("mínimo {d}").format(d=nc.texto_pulgadas(dmin))
        elif dmax is not None and d > dmax + TOL_DIAM:
            req = t("máximo {d}").format(d=nc.texto_pulgadas(dmax))
        else:
            continue
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

def validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto=(), structures=()):
    """Ver `_validar` (las curvas de cada tubería, por celdas: `model_ops.indice_vertices`)."""
    with model_ops.indice_vertices():
        return _validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto, structures)


def _validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto=(), structures=()):
    """Avisos de todas las utilidades y accesorios. `con_bancoducto` = índices de las
    utilidades que llevan bancoducto (sus filas «SIMPLE» no aplican); `structures` = para
    revisar el radio de sus curvas (RADIO CURVA MIN/MAX)."""
    out = []
    if not cat:
        return out
    con_bancoducto = set(con_bancoducto)
    por_capa = {}                       # los tipos de cada capa una vez (el catálogo no cambia aquí)
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        if p.get("world") or len(pts) < 2:
            continue
        xy = _medio(pts)
        capa = p.get("layer")
        de_capa = por_capa.get(capa)
        if de_capa is None:
            de_capa = por_capa[capa] = _tipos_de_capa(cat, capa)
        tiene_tipo = _revisar_tipo(cat, p, i, xy, out, de_capa)
        if tiene_tipo:
            _revisar_diametro(cat, p, i, xy, out)
        if tiene_tipo or not de_capa[0]:
            curvas = (list(model_ops.curve_vertex_indices(p, structures, pipes).values())
                      if structures and len(pts) >= 3 else [])
            _revisar_electrico(cat, p, i, xy, _largo_px(pts) * (ft_per_px or 0.0), i in con_bancoducto, out,
                               curvas)
    for a in accesorios_ or []:
        _revisar_accesorio(cat, pipes, a, out)
    return out


def en_punto(avisos, x, y, tol):
    """Avisos (no informativos) a ≤ tol del punto."""
    return [a for a in avisos if not a.info and not a.aprobado and (a.x - x) ** 2 + (a.y - y) ** 2 <= tol * tol]
