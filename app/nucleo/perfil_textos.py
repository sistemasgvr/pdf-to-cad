"""Textos del PERFIL LONGITUDINAL. PURO. Espejo de `PerfilTextos.cs` del plugin (H.1–H.7 de
`API-CIVIL/proyecto1/docs/PERFIL_DISENO.md`): lo que la app muestra es lo que Civil 3D va a rotular.

Los textos son en inglés a propósito: son los del plano (como en Civil 3D), no de la interfaz. El grado va como
«°» (en Civil 3D es «%%d»).
"""
from __future__ import annotations

import math
import unicodedata

GRADO = "°"
TITULO_ESTACION = "STATION (FT)"
TITULO_ELEVACION = "ELEVATION (FT)"
TEXTO_RASANTE = "EX. GRADE"
MAX_LINEAS_ESTRUCTURA = 6
MAX_CAR_RED = 24
ANGULOS_ESTANDAR = (11.25, 22.5, 45.0, 90.0)


def _redondear(v, dec=0):
    """Redondeo «AwayFromZero» como .NET."""
    k = 10 ** dec
    return math.copysign(math.floor(abs(v) * k + 0.5 + 1e-9) / k, v)


def estacion(est, decimales=2):
    if est is None or not math.isfinite(est):
        return ""
    r = _redondear(abs(est), decimales)
    negativo = est < 0 and r > 0
    cientos = math.floor(r / 100.0 + 1e-9)
    resto = max(0.0, r - cientos * 100.0)
    txt = f"{resto:0{3 + decimales if decimales else 2}.{decimales}f}"
    if txt.startswith("100"):
        cientos += 1
        txt = f"{0.0:0{3 + decimales if decimales else 2}.{decimales}f}"
    return ("-" if negativo else "") + f"{cientos:d}+" + txt


def cota(z):
    r = _redondear(z, 2)
    if r == 0:
        r = 0.0
    return f"{r:.2f}'"


def diametro(pulg):
    r = 1 if pulg is None or not math.isfinite(pulg) else max(1, _redondear(pulg))
    return f"{int(r)}\""


def angulo(grados):
    g = abs(grados)
    for s in ANGULOS_ESTANDAR:
        if abs(g - s) <= 1.0:
            return f"{s:g}" + GRADO
    t = f"{_redondear(g, 1):.1f}"
    if t.endswith(".0"):
        t = t[:-2]
    return t + GRADO


def pendiente(ratio):
    return f"{_redondear(abs(ratio) * 100.0, 2):.2f}%"


def longitud(ft):
    r = 1 if ft is None or not math.isfinite(ft) else max(1, _redondear(ft))
    return str(int(r))


def _plano(s):
    d = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def abreviar_material(m):
    p = _plano(m or "").strip()
    low = p.lower()
    if not low or low == "material sin definir":
        return ""
    for clave, ab in (("ductil", "DI"), ("corrugado", "CSP"), ("hormigon", "RCP"), ("concreto", "RCP"),
                      ("pvc", "PVC"), ("abs", "ABS"), ("hdpe", "HDPE"), ("polietileno", "HDPE"), ("acero", "STL")):
        if clave in low:
            return ab
    u = p.upper()
    return u[:10].rstrip() if len(u) > 10 else u


def unir(*partes):
    return " ".join(p.strip() for p in partes if p and p.strip())


def red_corta(red):
    r = (red or "").strip().upper()
    return r[:MAX_CAR_RED].rstrip() if len(r) > MAX_CAR_RED else r


def _sta(e):
    return "PIPE STA " + estacion(e)


def _top(z):
    return "TOP ELEV " + cota(z)


# ---------------------------------------------------------------- callouts de nodo (H.3)

def lineas_extremo(e, d, mat, gravedad, z):
    return [_sta(e), unir("END OF", diametro(d), abreviar_material(mat), "PIPE"),
            ("INV ELEV " if gravedad else "TOP ELEV ") + cota(z)]


def lineas_tee(e, dm, dr, lado, top):
    if lado:
        return [_sta(e), diametro(dm) + " X " + diametro(dr) + " TEE", unir(diametro(dr), "BRANCH", lado), _top(top)]
    return [_sta(e), diametro(dm) + " X " + diametro(dr) + " TEE", _top(top)]


def lineas_wye(e, dm, dr, lado, ang, top):
    return [_sta(e), diametro(dm) + " X " + diametro(dr) + " WYE",
            unir(diametro(dr), "BRANCH", lado, "" if ang is None else angulo(ang)), _top(top)]


def lineas_cruz(e, dm, dr, top):
    return [_sta(e), diametro(dm) + " X " + diametro(dr) + " CROSS", diametro(dr) + " BRANCHES LT & RT", _top(top)]


def lineas_codo(e, d, ang, vertical, mat, top):
    return [_sta(e), unir(diametro(d), "X", angulo(ang), "VERT" if vertical else "HORIZ",
                          abreviar_material(mat), "BEND"), _top(top)]


def lineas_reduccion(e, d1, d2, top):
    return [_sta(e), diametro(d1) + " X " + diametro(d2) + " REDUCER", _top(top)]


def lineas_deflexion(e, defl, top):
    return [_sta(e), angulo(defl) + " DEFLECTION", _top(top)]


def lineas_quiebre_conduit(e, defl, vertical, top):
    return [_sta(e), unir(angulo(defl), "VERT" if vertical else "HORIZ", "BEND"), _top(top)]


def lineas_estructura(e, nombre, rim, entradas, inv_out):
    """`entradas` = [(inv, diam_in, lado, ramal)]."""
    cab = ["STA " + estacion(e)]
    if (nombre or "").strip():
        cab.append(nombre.strip())
    if rim is not None:
        cab.append("RIM ELEV " + cota(rim))
    validas = [x for x in entradas or () if x[0] is not None]
    ins = []
    for inv, d, lado, ramal in validas:
        ins.append("INV IN " + cota(inv) + (" (" + unir(diametro(d), lado) + ")" if ramal or lado else ""))
    pie = ["INV OUT " + cota(inv_out)] if inv_out is not None else []
    if len(cab) + len(ins) + len(pie) > MAX_LINEAS_ESTRUCTURA and len(validas) > 1:
        ins = ["INV IN " + cota(min(x[0] for x in validas)) + f" ({len(validas)} BRANCHES)"]
    return cab + ins + pie


# ---------------------------------------------------------------- tramos (H.4)

def lineas_tramo(tipo, abandonado, largo, d, mat, s):
    """`tipo` = gravity | pressure | conduit. Devuelve [L1, L2] o [L1, L2, L3]."""
    L, m = longitud(largo), abreviar_material(mat)
    if abandonado:
        return [L + " LF OF EXIST", unir(diametro(d), m, "PIPE (ABANDONED)")]
    out = ["INSTALL " + L + " LF OF", unir("NEW", diametro(d), m, "CONDUIT" if tipo == "conduit" else "PIPE")]
    if tipo == "gravity" and s is not None:
        out.append("@ " + pendiente(s))
    return out


# ---------------------------------------------------------------- cruces (H.5)

def lineas_cruce(d, mat, abandonado, red, gravedad, z):
    r = [unir(diametro(d), abreviar_material(mat), "PIPE") + (" (ABAND.)" if abandonado else "")]
    rc = red_corta(red)
    if rc:
        r.append(rc)
    r.append(("INV ELEV " if gravedad else "TOP ELEV ") + cota(z))
    return r


def linea_claro(claro):
    return cota(claro) + " CLR"


# ---------------------------------------------------------------- título (H.7)

def lineas_titulo(n, d_pred, tipo, red, s, v):
    nombre = "MAIN" if tipo == "pressure" else ("CONDUIT" if tipo == "conduit" else "PIPE")
    l1 = f"PROFILE {n} - {longitud(d_pred)} INCH {nombre}"
    rc = (red or "").strip().upper()
    if rc:
        l1 += " - " + rc
    return [l1, f"HORIZ 1\"={s:g}'  VERT 1\"={v:g}'"]
