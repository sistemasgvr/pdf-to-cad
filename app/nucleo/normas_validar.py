"""Revisión de las utilidades contra la tabla de reglas (PURO: sin Qt). Solo AVISA: nunca cambia nada.

`validar(cat, pipes, accesorios, ft_per_px, con_bancoducto, structures, conexiones)` → [Aviso]:

  • Tipo: la utilidad tiene tipos en el catálogo y no eligió ninguno (o el suyo ya no existe) → aviso. Las
    reglas sin TIPO se revisan igual; las de un tipo, solo si la utilidad es de ese tipo.
  • Cada regla ACTIVA (`normas_reglas`) cuyo alcance encaja (utilidad, tipo y las condiciones SI…; una condición
    de material no aplica a una tubería con «Material sin definir»): se mide lo de REVISAR y se compara con
    MIN/MAX/VALORES. Reglas con el MISMO alcance se suman (basta cumplir una: 6; 8; 12 y aparte 4 en
    cul-de-sacs). En un diámetro, la NOTA dice dónde se usa: si solo la cumplen reglas con NOTA, sale como
    información con esa nota (como «SOLO SE PERMITE EN» del Excel viejo).
    Aquí: tubería (diámetro, pendiente por tramo, largo, amperaje, material, quiebres sin buzón), curvas (radio)
    y buzones (distancia entre buzones, caída). Accesorios en `normas_validar_acc`; separaciones con otras
    utilidades y «diámetro menor que la tubería a la que llega» en `normas_validar_red`.
  • Sin cotas (rasantes vacías) no se revisan pendientes, caídas ni cruces: no hay qué medir.
  • Eléctrico/telecom con bancoducto: no se revisan diámetro, amperaje ni radio (aún no se revisan).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from nucleo import model_ops
from nucleo import normas_catalogo as nc
from nucleo import normas_reglas as NR
from traduccion.i18n_core import N_, t

TOL = {"diametro": 0.01, "diam_principal": 0.01, "diam_ramal": 0.01, "radio": 0.005, "angulo": 1.0,
       "llega_menos": 0.01, "ramal_menos": 0.01}
TOL_GEN = 1e-6
DOMICILIARIA = "INSTALACION DOMICILIARIA"

CLASES = {
    "tipo": N_("Tipo de utilidad"),
    "diametro": N_("Diámetro"),
    "electrico": N_("Diámetro según amperaje y largo"),
    "accesorio": N_("Accesorio"),
    "nota": N_("Condición de uso"),
    "radio": N_("Radio de curva"),
    "angulo": N_("Ángulo fuera del paso de 0.25°"),
    "pendiente": N_("Pendiente"),
    "largo": N_("Largo"),
    "material": N_("Material"),
    "buzon": N_("Buzones"),
    "separacion": N_("Separación con otra utilidad"),
    "grosor": N_("Diámetro del plano"),          # nucleo/diametro_plano: no se encontró o es dudoso
}
NOMBRE_ACC = {"codo": N_("Codo"), "tee": N_("Tee"), "wye": N_("Wye"), "cruz": N_("Cruz"),
              "tee_dom": N_("T domiciliaria"), "reduccion": N_("Reducción")}
_SEVERIDAD = {"INFO": 0, "AVISO": 1, "ERROR": 2}


@dataclass
class Aviso:
    x: float
    y: float
    clase: str                       # CLASES
    mensaje: str
    pipe: int = -1                   # utilidad (o la principal del accesorio)
    info: bool = False               # True = solo informativo (no es un incumplimiento)
    aprobado: object = None          # registro de aprobación (normas_aprobacion) o None = pendiente
    nivel: str = "AVISO"             # ERROR / AVISO / INFO (de la regla)
    fuente: str = ""


# ─────────────────────────── medir y comparar ───────────────────────────

def cumple(regla, v):
    """¿El valor medido `v` cumple la regla (VALORES y MIN–MAX a la vez)?"""
    if v is None:
        return True
    tol = TOL.get(regla["revisar"], TOL_GEN)
    if isinstance(v, str):
        vals = {nc.clave(x) for x in regla.get("valores") or []}
        return nc.clave(v) not in vals if regla["revisar"] == "material_no" else nc.clave(v) in vals
    vals = regla.get("valores") or []
    if vals and not any(abs(v - x) <= tol for x in vals):
        return False
    return nc.en_rango(v, nc.rango_min_max(regla.get("min"), regla.get("max")), tol)


def cumple_grupo(reglas, v):
    return any(cumple(r, v) for r in reglas)


def unidad(revisar, n):
    if revisar in ("diametro", "diam_principal", "diam_ramal", "llega_menos", "ramal_menos"):
        return nc.texto_pulgadas(n)
    u = {"pendiente": " %", "amperaje": " A", "angulo": "°", "quiebre": "°"}.get(revisar, " ft")
    return nc.texto_numero(round(n, 3)) + u


def requisito(regla):
    """«debe ser 6", 8"» / «mínimo 0,44 %» / «entre 0 y 320 A» / «uno de: …»."""
    rv, partes = regla["revisar"], []
    vals = regla.get("valores") or []
    if vals:
        if rv == "material_no":
            partes.append(t("no puede ser {lista}").format(lista=", ".join(map(str, vals))))
        elif isinstance(vals[0], str):
            partes.append(t("debe ser {lista}").format(lista=", ".join(vals)))
        else:
            partes.append(t("debe ser {lista}").format(lista=", ".join(unidad(rv, x) for x in vals)))
    lo, hi = regla.get("min"), regla.get("max")
    if lo is not None and hi is not None:
        partes.append(t("entre {a} y {b}").format(a=unidad(rv, lo), b=unidad(rv, hi)))
    elif lo is not None:
        partes.append(t("mínimo {v}").format(v=unidad(rv, lo)))
    elif hi is not None:
        partes.append(t("máximo {v}").format(v=unidad(rv, hi)))
    return " ".join(partes)


def requisito_grupo(reglas):
    return (" " + t("o") + " ").join(dict.fromkeys(requisito(r) for r in reglas))


def condiciones(regla):
    """«INSTALACION DOMICILIARIA, 321-400 A, 101-200 ft de largo, PVC» (lo que acota la regla)."""
    out = [regla["tipo"]] if regla.get("tipo") else []
    if regla.get("si_diam"):
        out.append(t("{r} in de diámetro").format(r=nc.texto_rango(regla["si_diam"])))
    if regla.get("si_amp"):
        out.append(t("{r} A").format(r=nc.texto_rango(regla["si_amp"])))
    if regla.get("si_largo"):
        out.append(t("{r} ft de largo").format(r=nc.texto_rango(regla["si_largo"])))
    out += regla.get("si_material") or []
    return out


def con_condiciones(msg, regla, sin_tipo=False):
    cond = condiciones(regla)
    if sin_tipo and regla.get("tipo"):
        cond = cond[1:]
    return msg + (" (" + ", ".join(cond) + ")" if cond else "") + "."


def nivel_de(reglas):
    return max((r.get("nivel") or "AVISO" for r in reglas), key=lambda n: _SEVERIDAD.get(n, 1))


def aviso(x, y, clase, mensaje, pipe, reglas, info=False):
    nivel = nivel_de(reglas) if reglas else "AVISO"
    fuente = "; ".join(dict.fromkeys(r.get("fuente") for r in reglas if r.get("fuente"))) if reglas else ""
    return Aviso(x, y, clase, mensaje, pipe, info=info or nivel == "INFO", nivel=nivel, fuente=fuente)


def agrupar(reglas):
    grupos = {}
    for r in reglas:
        grupos.setdefault(NR.alcance(r), []).append(r)
    return list(grupos.values())


def activas(cat):
    """{utilidad: [reglas activas que se miden]}."""
    out = {}
    for r in (cat or {}).get("reglas") or []:
        if r.get("activa", True) and r.get("revisar") in NR.POR_CLAVE and r["revisar"] != "referencia":
            out.setdefault(r["utilidad"], []).append(r)
    return out


# ─────────────────────────── la tubería ───────────────────────────

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


def _tipo(p):
    return nc.clave(p.get("tipo"))


def tiene_cotas(p):
    return p.get("inv_start") is not None or p.get("inv_end") is not None


def material(p):
    m = (p.get("material") or "").strip()
    return "" if not m or nc.mismo(m, "Material sin definir") else m


class Datos:
    """Lo de una utilidad que miran las condiciones de las reglas (el largo, solo si alguien lo pide)."""
    __slots__ = ("i", "p", "tipo", "tipo_ok", "diam", "defecto", "amp", "material", "_ft", "_largo")

    def __init__(self, i, p, tipo, tipo_ok, diam, defecto, amp, material, ft_per_px):
        self.i, self.p, self.tipo, self.tipo_ok = i, p, tipo, tipo_ok
        self.diam, self.defecto, self.amp, self.material = diam, defecto, amp, material
        self._ft, self._largo = ft_per_px or 0.0, None

    @property
    def largo_ft(self):
        if self._largo is None:
            self._largo = _largo_px(self.p.get("pts") or []) * self._ft
        return self._largo


def datos(i, p, tipo_ok, ft_per_px):
    d, defecto = model_ops.diametro(p)
    return Datos(i, p, _tipo(p), tipo_ok, d, defecto, nc.numero(p.get("amperaje")), material(p), ft_per_px)


def aplica(r, dt, elementos=(NR.TUBERIA,)):
    """¿La regla aplica a esa utilidad (tipo y condiciones)? None = faltaría el amperaje."""
    if r["elemento"] not in elementos:
        return False
    if r.get("tipo") and (not dt.tipo_ok or r["tipo"] != dt.tipo):
        return False
    if r.get("si_amp"):                 # antes que lo demás: sin amperaje se pide (como siempre)
        if dt.amp is None:
            return None
        if not nc.en_rango(dt.amp, r["si_amp"]):
            return False
    if r.get("si_diam") and not nc.en_rango(dt.diam, r["si_diam"], 0.01):
        return False
    if r.get("si_largo") and not nc.en_rango(dt.largo_ft, r["si_largo"], 1e-6):
        return False
    if r.get("si_material") and not (dt.material and any(nc.mismo(dt.material, m) for m in r["si_material"])):
        return False
    return True


def _revisar_tipo(p, i, xy, de_capa, out):
    tipos, claves = de_capa
    if not tipos:
        return True
    if not _tipo(p):
        out.append(Aviso(*xy, "tipo", t("Sin tipo: elige su tipo para revisar sus normativas."), i))
        return False
    if _tipo(p) not in claves:
        out.append(Aviso(*xy, "tipo", t("El tipo «{tipo}» ya no está en la lista de tipos.").format(
            tipo=p.get("tipo")), i))
        return False
    return True


def _diametro(grupo, dt, xy, todas, out):
    """Diámetro con los mensajes de siempre (de otro tipo / no permitido / nota de uso)."""
    d_txt = nc.texto_pulgadas(dt.diam) + (" " + t("(por defecto)") if dt.defecto else "")
    r0 = grupo[0]
    clase = "electrico" if r0["utilidad"] in ("ELECTRICO", "TELECOM") else "diametro"
    if cumple_grupo(grupo, dt.diam):
        con_nota = [r for r in grupo if cumple(r, dt.diam)]
        if all(r.get("nota") for r in con_nota):      # la NOTA de un diámetro es dónde se usa (cul-de-sacs)
            out.append(aviso(*xy, "nota", t("Diámetro {d}: solo se permite en {nota}.").format(
                d=d_txt, nota=con_nota[0]["nota"]), dt.i, con_nota, info=True))
        return
    req = requisito_grupo(grupo)
    simple = r0.get("tipo") and not (r0.get("si_diam") or r0.get("si_amp") or r0.get("si_largo")
                                     or r0.get("si_material"))
    if simple and clase == "diametro":
        otros = [r for r in todas if r["revisar"] == "diametro" and r.get("tipo") and r["tipo"] != r0["tipo"]
                 and not (r.get("si_diam") or r.get("si_amp") or r.get("si_largo") or r.get("si_material"))
                 and cumple(r, dt.diam)]
        if otros:
            msg = t("Diámetro {d}: es de «{otro}» y esta utilidad es «{tipo}». Para su tipo: {req}.").format(
                d=d_txt, otro=otros[0]["tipo"], tipo=r0["tipo"], req=req)
        else:
            msg = t("Diámetro {d} no permitido para «{tipo}»: {req}.").format(d=d_txt, tipo=r0["tipo"], req=req)
        out.append(aviso(*xy, clase, msg, dt.i, grupo))
        return
    out.append(aviso(*xy, clase, con_condiciones(t("Diámetro {d}: {req}").format(d=d_txt, req=req), r0),
                     dt.i, grupo))


def _por_tramo(grupo, dt, valores, etiqueta, out):
    """Un aviso por utilidad: el peor tramo que no cumple (y cuántos más)."""
    pts = dt.p["pts"]
    malos = [(k, v) for k, v in enumerate(valores) if v is not None and not cumple_grupo(grupo, v)]
    if not malos:
        return
    k, v = malos[0]
    xy = ((pts[k][0] + pts[k + 1][0]) / 2.0, (pts[k][1] + pts[k + 1][1]) / 2.0)
    msg = t("{etq} T{n} {v}: {req}").format(etq=etiqueta, n=k + 1, v=unidad(grupo[0]["revisar"], v),
                                            req=requisito_grupo(grupo))
    if len(malos) == 2:
        msg += " " + t("(y 1 tramo más)")
    elif len(malos) > 2:
        msg += " " + t("(y {n} tramos más)").format(n=len(malos) - 1)
    out.append(aviso(*xy, NR.POR_CLAVE[grupo[0]["revisar"]].clase, con_condiciones(msg, grupo[0]), dt.i, grupo))


def _simple(grupo, dt, xy, valor, etiqueta, out):
    if valor is None or valor == "" or cumple_grupo(grupo, valor):
        return
    txt = valor if isinstance(valor, str) else unidad(grupo[0]["revisar"], valor)
    msg = t("{etq} {v}: {req}").format(etq=etiqueta, v=txt, req=requisito_grupo(grupo))
    out.append(aviso(*xy, NR.POR_CLAVE[grupo[0]["revisar"]].clase, con_condiciones(msg, grupo[0]), dt.i, grupo))


def _buzones_en(p, structures, ind):
    """Índices de los vértices de `p` con un buzón VISIBLE (no oculto, no curva)."""
    out = set()
    if ind is None:
        return out
    for k, (x, y) in enumerate(p.get("pts") or []):
        for j in ind[1].en_radio(x, y, model_ops._TOL):
            s = ind[0][j]
            if not (s.get("hidden") or s.get("curve") or s.get("world")):
                out.add(k)
                break
    return out


def _deflexion(a, b, c):
    u = (b[0] - a[0], b[1] - a[1]); w = (c[0] - b[0], c[1] - b[1])
    if math.hypot(*u) < 1e-9 or math.hypot(*w) < 1e-9:
        return 0.0
    ang = math.degrees(abs((math.atan2(w[1], w[0]) - math.atan2(u[1], u[0]) + math.pi) % (2 * math.pi) - math.pi))
    return ang


def _revisar_tuberia(reglas, todas, dt, xy, ft_px, sin_bd, curvas, buzones, out):
    pts = dt.p["pts"]
    for grupo in agrupar(reglas):
        rv = grupo[0]["revisar"]
        if sin_bd and rv in ("diametro", "amperaje", "radio"):
            continue
        if rv == "diametro":
            _diametro(grupo, dt, xy, todas, out)
        elif rv == "pendiente":
            if tiene_cotas(dt.p):
                vals = [None if s is None else abs(s) for s in model_ops.pendientes_tramos(dt.p, ft_px)]
                _por_tramo(grupo, dt, vals, t("Pendiente"), out)
        elif rv == "largo":
            _simple(grupo, dt, xy, dt.largo_ft, t("Largo"), out)
        elif rv == "amperaje":
            _simple(grupo, dt, xy, dt.amp, t("Amperaje"), out)
        elif rv in ("material", "material_no"):
            _simple(grupo, dt, xy, dt.material or None, t("Material"), out)
        elif rv == "quiebre":
            for k in range(1, len(pts) - 1):
                if k in buzones or k in curvas:
                    continue
                g = _deflexion(pts[k - 1], pts[k], pts[k + 1])
                if g > 0.01 and not cumple_grupo(grupo, g):
                    msg = t("Quiebre de {g} sin buzón: {req}").format(g=unidad("quiebre", g), req=requisito_grupo(grupo))
                    out.append(aviso(pts[k][0], pts[k][1], "buzon", con_condiciones(msg, grupo[0]), dt.i, grupo))
        elif rv == "radio":
            for s in curvas.values():
                radio = float(s.get("radius_ft") or 0.0)
                auto = radio <= 0.01
                if auto:
                    radio = model_ops.radio_auto_ft(dt.p)
                if cumple_grupo(grupo, radio):
                    continue
                txt = nc.texto_numero(round(radio, 2)) + (" " + t("(automático)") if auto else "")
                msg = t("Curva de radio {r} ft: {req}").format(r=txt, req=requisito_grupo(grupo))
                out.append(aviso(s["x"], s["y"], "radio", con_condiciones(msg, grupo[0]), dt.i, grupo))
        elif rv == "dist_buzones":
            _dist_buzones(grupo, dt, ft_px, buzones, out)
        elif rv == "caida":
            if tiene_cotas(dt.p):
                for k in range(1, len(pts) - 1):
                    if k not in buzones:
                        continue
                    a, b = model_ops.cotas_tramo(dt.p, k - 1), model_ops.cotas_tramo(dt.p, k)
                    if a is None or b is None:
                        continue
                    caida = a[1] - b[0]
                    if not cumple_grupo(grupo, caida):
                        msg = t("Caída en el buzón {v}: {req}").format(v=unidad("caida", caida),
                                                                       req=requisito_grupo(grupo))
                        out.append(aviso(pts[k][0], pts[k][1], "buzon", con_condiciones(msg, grupo[0]), dt.i,
                                         grupo))


def _dist_buzones(grupo, dt, ft_px, buzones, out):
    pts = dt.p["pts"]
    cortes = sorted({0, len(pts) - 1} | buzones)
    for a, b in zip(cortes, cortes[1:]):
        L = _largo_px(pts[a:b + 1]) * ft_px
        if cumple_grupo(grupo, L):
            continue
        x, y = _medio(pts[a:b + 1])
        msg = t("Distancia entre buzones {v}: {req}").format(v=unidad("dist_buzones", L), req=requisito_grupo(grupo))
        out.append(aviso(x, y, "buzon", con_condiciones(msg, grupo[0]), dt.i, grupo))


# ─────────────────────────── todo ───────────────────────────

def validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto=(), structures=(), conexiones=()):
    """Ver `_validar` (las curvas de cada tubería, por celdas: `model_ops.indice_vertices`)."""
    with model_ops.indice_vertices():
        return _validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto, structures, conexiones)


def _validar(cat, pipes, accesorios_, ft_per_px, con_bancoducto=(), structures=(), conexiones=()):
    """Avisos de todas las utilidades y accesorios. `con_bancoducto` = índices de las utilidades que llevan
    bancoducto; `structures` = curvas y buzones; `conexiones` = conexiones verticales aprobadas (esos cruces no
    se revisan)."""
    from nucleo import normas_validar_acc, normas_validar_red
    from nucleo.indice_plano import IndicePuntos
    out = []
    if not cat:
        return out
    por_util = activas(cat)
    con_bancoducto = set(con_bancoducto)
    estructuras = [s for s in structures or () if s.get("x") is not None and s.get("y") is not None]
    ind = (estructuras, IndicePuntos([(s["x"], s["y"]) for s in estructuras], model_ops._TOL * 4)) \
        if estructuras else None
    por_capa, por_tipo, todos = {}, {}, []
    elementos = (NR.TUBERIA, NR.CURVA, NR.BUZON)
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        if p.get("world") or len(pts) < 2:
            todos.append(None)
            continue
        xy = _medio(pts)
        capa = nc.clave(p.get("layer"))
        de_capa = por_capa.get(capa)
        if de_capa is None:
            tipos = nc.tipos_de(cat, capa)
            de_capa = por_capa[capa] = (tipos, {nc.clave(x) for x in tipos})
        tipo_ok = _revisar_tipo(p, i, xy, de_capa, out)
        dt = datos(i, p, tipo_ok, ft_per_px)
        todos.append(dt)
        # las reglas de su utilidad y su tipo, una vez por (utilidad, tipo): con miles de utilidades
        clave_t = (capa, dt.tipo if tipo_ok else None)
        reglas_t = por_tipo.get(clave_t)
        if reglas_t is None:
            reglas_t = por_tipo[clave_t] = [
                r for r in por_util.get(capa) or [] if not NR.POR_CLAVE[r["revisar"]].con
                and r["revisar"] != "llega_menos" and r["elemento"] in elementos
                and (not r.get("tipo") or (tipo_ok and r["tipo"] == dt.tipo))]
        if not reglas_t:
            continue
        propias, falta_amp = [], False
        for r in reglas_t:
            a = aplica(r, dt, elementos)
            if a is None:
                falta_amp = True
            elif a:
                propias.append(r)
        if falta_amp and i not in con_bancoducto:
            out.append(Aviso(*xy, "electrico", t("Falta el amperaje: escríbelo para revisar su diámetro."), i))
        if not propias:
            continue
        curvas = (model_ops.curve_vertex_indices(p, structures, pipes)
                  if structures and len(pts) >= 3 and any(r["elemento"] == NR.CURVA or r["revisar"] == "quiebre"
                                                         for r in propias) else {})
        buzones = (_buzones_en(p, estructuras, ind)
                   if any(r["elemento"] == NR.BUZON or r["revisar"] == "quiebre" for r in propias) else set())
        sin_bd = i in con_bancoducto and NR.red_de(capa) == "conduit"      # el bancoducto reemplaza su sección
        _revisar_tuberia(propias, por_util.get(capa) or [], dt, xy, ft_per_px or 0.0, sin_bd, curvas, buzones, out)
    normas_validar_red.revisar(por_util, pipes, todos, ft_per_px or 0.0, conexiones, out)
    memo_acc = {}
    for a in accesorios_ or []:
        normas_validar_acc.revisar(por_util, pipes, todos, a, out, memo_acc)
    return out


def en_punto(avisos, x, y, tol):
    """Avisos (no informativos) a ≤ tol del punto."""
    return [a for a in avisos if not a.info and not a.aprobado and (a.x - x) ** 2 + (a.y - y) ** 2 <= tol * tol]
