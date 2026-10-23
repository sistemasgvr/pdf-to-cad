"""Normativas en UNA tabla de reglas (PURO: sin Qt). Pedido del usuario 2026-10-21: «unificar todo en una
sola tabla más inteligente e integrada con lo que la app puede validar», que aguante separaciones entre
utilidades y tipos, y que solo deje escribir lo que la app contempla.

Una fila = una regla:

  ACTIVA | UTILIDAD | TIPO | ELEMENTO | SI DIAMETRO MIN/MAX (in) | SI AMPERAJE MIN/MAX (A) | SI LARGO MIN/MAX (ft)
  | SI MATERIAL | REVISAR | MIN | MAX | VALORES | CON UTILIDAD | CON TIPO | NIVEL | FUENTE | NOTA

  • UTILIDAD, TIPO: a qué tuberías aplica (TIPO vacío = todas las de la utilidad; en un accesorio, el tipo de
    su línea PRINCIPAL).
  • ELEMENTO: qué se mira — la tubería, sus curvas, sus buzones (redes por gravedad) o un accesorio (redes a
    presión: Y, T, Cruz, Codo, T - Domiciliaria = la T cuyo ramal es de instalación domiciliaria).
  • SI …: condiciones sobre la tubería (todas a la vez; vacías = siempre).
  • REVISAR: lo que se mide, de una lista CERRADA (`REVISAR`): solo lo que la app sabe medir. Su unidad va en
    el nombre. «Solo referencia» = queda escrita, no se mide (velocidades, profundidades…).
  • MIN / MAX / VALORES: el valor medido debe estar entre MIN y MAX, o ser uno de VALORES (lista con «;»).
    Varias reglas con el MISMO alcance (utilidad, tipo, elemento, condiciones, revisar, con) se suman: basta
    con cumplir UNA (6; 8; 12 y, aparte, 4 en cul-de-sacs). Alcances distintos: hay que cumplir todos.
  • CON UTILIDAD / CON TIPO: para separaciones — respecto a qué otra utilidad (CUALQUIERA = cualquier otra).
  • NIVEL: ERROR, AVISO o INFO (solo informa). FUENTE y NOTA: de dónde sale y aclaraciones.

En memoria una regla es un dict (`regla_vacia`). `leer_fila(textos, tipos)` → (regla o None, [(columna,
motivo)]): las MISMAS reglas para el Excel y para el editor de la ventana.
"""
from __future__ import annotations

from dataclasses import dataclass

from nucleo import model
from nucleo import normas_catalogo as nc

COLUMNAS = ("ACTIVA", "UTILIDAD", "TIPO", "ELEMENTO", "SI DIAMETRO MIN (in)", "SI DIAMETRO MAX (in)",
            "SI AMPERAJE MIN (A)", "SI AMPERAJE MAX (A)", "SI LARGO MIN (ft)", "SI LARGO MAX (ft)", "SI MATERIAL",
            "REVISAR", "MIN", "MAX", "VALORES", "CON UTILIDAD", "CON TIPO", "NIVEL", "FUENTE", "NOTA")
NUMERICAS = {"SI DIAMETRO MIN (in)", "SI DIAMETRO MAX (in)", "SI AMPERAJE MIN (A)", "SI AMPERAJE MAX (A)",
             "SI LARGO MIN (ft)", "SI LARGO MAX (ft)", "MIN", "MAX"}

TUBERIA, CURVA, BUZON = "TUBERIA", "CURVA", "BUZON"
Y, T, CRUZ, CODO, T_DOM = "Y", "T", "CRUZ", "CODO", "T - DOMICILIARIA"
ELEMENTOS = (TUBERIA, CURVA, BUZON, Y, T, CRUZ, CODO, T_DOM)
ACCESORIOS = (Y, T, CRUZ, CODO, T_DOM)
# Elemento → tipo de `accesorios.accesorios` («tee_dom» = la T con ramal domiciliario).
TIPO_ACC = {Y: "wye", T: "tee", CRUZ: "cruz", CODO: "codo", T_DOM: "tee_dom"}
# En qué redes existe cada elemento (los accesorios se detectan solo en las redes a presión).
REDES_ELEMENTO = {BUZON: ("gravity",), **{a: ("pressure",) for a in ACCESORIOS}}

CUALQUIERA = "CUALQUIERA"
SI, NO = "SI", "NO"
NIVELES = ("ERROR", "AVISO", "INFO")
MATERIALES = tuple(m for m in model.PIPE_MATERIALS if m != model.DEFAULT_PIPE_MATERIAL)

NUM, TIPOS_, MATERIAL, SINO = "num", "tipos", "material", "sino"


@dataclass(frozen=True)
class Revisar:
    clave: str
    texto: str                      # lo que se escribe en REVISAR (con su unidad)
    elementos: tuple
    usa: str                        # letras: n = MIN, x = MAX, v = VALORES
    valores: str = NUM              # qué va en VALORES
    con: bool = False               # pide CON UTILIDAD
    redes: tuple = ()               # vacío = todas
    utilidades: tuple = ()          # vacío = todas
    clase: str = ""                 # clase del aviso (`normas_validar.CLASES`)


_ACC_RAMAL = (Y, T, T_DOM)
REVISAR = (
    Revisar("diametro", "Diámetro (in)", (TUBERIA,), "nxv", clase="diametro"),
    Revisar("pendiente", "Pendiente (%)", (TUBERIA,), "nx", clase="pendiente"),
    Revisar("largo", "Largo (ft)", (TUBERIA,), "nx", clase="largo"),
    Revisar("amperaje", "Amperaje (A)", (TUBERIA,), "nxv", utilidades=("ELECTRICO",), clase="electrico"),
    Revisar("material", "Material permitido", (TUBERIA,), "v", MATERIAL, clase="material"),
    Revisar("material_no", "Material prohibido", (TUBERIA,), "v", MATERIAL, clase="material"),
    Revisar("quiebre", "Quiebre sin buzón (°)", (TUBERIA,), "x", redes=("gravity",), clase="buzon"),
    Revisar("llega_menos", "Diámetro menor que la tubería a la que llega (in)", (TUBERIA,), "nx", clase="diametro"),
    Revisar("sep_h", "Separación horizontal en paralelo, entre bordes (ft)", (TUBERIA,), "n", con=True,
            clase="separacion"),
    Revisar("sep_h_ejes", "Separación horizontal en paralelo, entre ejes (ft)", (TUBERIA,), "n", con=True,
            clase="separacion"),
    Revisar("sep_v", "Separación vertical en el cruce (ft)", (TUBERIA,), "n", con=True, clase="separacion"),
    Revisar("encima", "Por encima en el cruce (ft)", (TUBERIA,), "n", con=True, clase="separacion"),
    Revisar("debajo", "Por debajo en el cruce (ft)", (TUBERIA,), "n", con=True, clase="separacion"),
    Revisar("radio", "Radio (ft)", (CURVA,), "nxv", clase="radio"),
    Revisar("dist_buzones", "Distancia entre buzones (ft)", (BUZON,), "nx", clase="buzon"),
    Revisar("caida", "Caída en el buzón, flujo directo (ft)", (BUZON,), "nx", clase="buzon"),
    Revisar("permitido", "Se permite", ACCESORIOS, "v", SINO, clase="accesorio"),
    Revisar("solo_en", "Solo en tipos (de la principal)", ACCESORIOS, "v", TIPOS_, clase="accesorio"),
    Revisar("diam_principal", "Diámetro de la principal (in)", ACCESORIOS, "nxv", clase="accesorio"),
    Revisar("diam_ramal", "Diámetro del ramal (in)", _ACC_RAMAL, "nxv", clase="accesorio"),
    Revisar("ramal_pasos", "Ramal: tamaños menos que la principal (-1 = uno menor)", (Y, T), "v",
            clase="accesorio"),
    Revisar("ramal_menos", "Ramal: pulgadas menos que la principal (in)", _ACC_RAMAL, "nx", clase="accesorio"),
    Revisar("angulo", "Ángulo (°)", ACCESORIOS, "nxv", clase="accesorio"),
    Revisar("referencia", "Solo referencia (no se mide)", ELEMENTOS, "", clase="nota"),
)
POR_CLAVE = {r.clave: r for r in REVISAR}
POR_TEXTO = {nc.clave(r.texto): r for r in REVISAR}


def utilidades():
    return nc.UTILIDADES


def red_de(utilidad):
    return model.NETWORK_KIND.get(nc.clave(utilidad), "")


def elementos_de(utilidad):
    """Elementos que tienen sentido en esa utilidad (buzones solo en gravedad, accesorios solo a presión)."""
    red = red_de(utilidad)
    return tuple(e for e in ELEMENTOS if not REDES_ELEMENTO.get(e) or red in REDES_ELEMENTO[e])


def revisar_de(utilidad, elemento):
    """Lo que se puede revisar de ese elemento en esa utilidad (en el orden de `REVISAR`)."""
    red, u, e = red_de(utilidad), nc.clave(utilidad), nc.clave(elemento)
    return tuple(r for r in REVISAR if e in r.elementos and (not r.redes or red in r.redes)
                 and (not r.utilidades or u in r.utilidades))


def regla_vacia(**k):
    r = {"activa": True, "utilidad": "", "tipo": "", "elemento": TUBERIA, "si_diam": None, "si_amp": None,
         "si_largo": None, "si_material": [], "revisar": "", "min": None, "max": None, "valores": [],
         "con_utilidad": "", "con_tipo": "", "nivel": "AVISO", "fuente": "", "nota": ""}
    r.update(k)
    return r


def alcance(r):
    """Reglas con el mismo alcance se suman (basta con cumplir una)."""
    def t(v):
        return tuple(v) if isinstance(v, list) else v
    return (r["utilidad"], r["tipo"], r["elemento"], t(r["si_diam"]), t(r["si_amp"]), t(r["si_largo"]),
            tuple(sorted(r["si_material"])), r["revisar"], r["con_utilidad"], r["con_tipo"])


# ─────────────────────────── texto ↔ regla ───────────────────────────

def _n(v):
    return "" if v is None else nc.texto_numero(v)


def _extremos(r):
    return ["", ""] if not r else [_n(r[0]), _n(r[1])]


def texto_valores(regla):
    rv = POR_CLAVE.get(regla.get("revisar"))
    vals = regla.get("valores") or []
    if rv is not None and rv.valores != NUM:
        return "; ".join(str(v) for v in vals)
    return nc.texto_lista(vals)


def fila_de(regla):
    """La regla como fila de texto, en el orden de `COLUMNAS` (como en el Excel)."""
    rv = POR_CLAVE.get(regla.get("revisar"))
    return [SI if regla.get("activa", True) else NO, regla.get("utilidad") or "", regla.get("tipo") or "",
            regla.get("elemento") or "", *_extremos(regla.get("si_diam")), *_extremos(regla.get("si_amp")),
            *_extremos(regla.get("si_largo")), "; ".join(regla.get("si_material") or []),
            rv.texto if rv else (regla.get("revisar") or ""), _n(regla.get("min")), _n(regla.get("max")),
            texto_valores(regla), regla.get("con_utilidad") or "", regla.get("con_tipo") or "",
            regla.get("nivel") or "AVISO", regla.get("fuente") or "", regla.get("nota") or ""]


def _partes(v):
    return [x.strip() for x in str(v or "").split(";") if x.strip()]


def _de_lista(texto, opciones):
    """(elegidos con el nombre de la app, los que no están en `opciones`)."""
    por = {nc.clave(o): o for o in opciones}
    ok, mal = [], []
    for x in _partes(texto):
        (ok if nc.clave(x) in por else mal).append(por.get(nc.clave(x), x))
    return ok, mal


def leer_fila(fila, tipos=None):
    """(regla o None, [(columna, motivo)]). `fila` = textos en el orden de `COLUMNAS` (o dict columna →
    valor). `tipos` = {(utilidad, tipo)} de la tabla TIPOS: con ellos, un TIPO que no está ahí es un problema.
    Una fila con problemas no se usa (la aplicación manda)."""
    d = dict(fila) if isinstance(fila, dict) else dict(zip(COLUMNAS, fila))
    d = {nc.clave(k): ("" if v is None else (v.strip() if isinstance(v, str) else v)) for k, v in d.items()}

    def v(col):
        return d.get(nc.clave(col), "")

    mal = []
    r = regla_vacia()
    activa = nc.clave(v("ACTIVA"))
    if activa not in ("", SI, "NO", "SÍ"):
        mal.append(("ACTIVA", "escribe SI o NO"))
    r["activa"] = activa != "NO"
    u = nc.clave(v("UTILIDAD"))
    if u not in nc.UTILIDADES:
        mal.append(("UTILIDAD", "«{v}» no es una utilidad de la aplicación".format(v=v("UTILIDAD"))))
        return None, mal
    r["utilidad"] = u

    def tipo_ok(col, util, texto):
        t = nc.clave(texto)
        if t and tipos is not None and (util, t) not in tipos:
            mal.append((col, "«{t}» no es un tipo de {u} (pestaña/hoja TIPOS)".format(t=texto, u=util)))
        return t

    r["tipo"] = tipo_ok("TIPO", u, v("TIPO"))
    e = nc.clave(v("ELEMENTO")) or TUBERIA
    if e not in ELEMENTOS:
        mal.append(("ELEMENTO", "«{v}» no es un elemento que la app revisa".format(v=v("ELEMENTO"))))
        return None, mal
    if e not in elementos_de(u):
        mal.append(("ELEMENTO", "{e} no existe en {u} (los buzones son de redes por gravedad y los accesorios "
                                "de redes a presión)".format(e=e, u=u)))
    r["elemento"] = e
    for col_min, col_max, k in (("SI DIAMETRO MIN (in)", "SI DIAMETRO MAX (in)", "si_diam"),
                                ("SI AMPERAJE MIN (A)", "SI AMPERAJE MAX (A)", "si_amp"),
                                ("SI LARGO MIN (ft)", "SI LARGO MAX (ft)", "si_largo")):
        lo, hi = _numero(v(col_min), col_min, mal), _numero(v(col_max), col_max, mal)
        r[k] = nc.rango_min_max(lo, hi)
    if r["si_amp"] is not None and u != "ELECTRICO":
        mal.append(("SI AMPERAJE MIN (A)", "solo las utilidades eléctricas llevan amperaje"))
    r["si_material"], fuera = _de_lista(v("SI MATERIAL"), MATERIALES)
    if fuera:
        mal.append(("SI MATERIAL", "«{v}» no es un material de la app ({m})".format(
            v="; ".join(fuera), m=", ".join(MATERIALES))))
    rv = POR_TEXTO.get(nc.clave(v("REVISAR"))) or POR_CLAVE.get(str(v("REVISAR")))
    if rv is None:
        mal.append(("REVISAR", "elige de la lista lo que se revisa" if not v("REVISAR")
                    else "«{v}» no es algo que la app sabe medir".format(v=v("REVISAR"))))
        return None, mal
    if rv not in revisar_de(u, e):
        mal.append(("REVISAR", "«{r}» no se revisa en {e} de {u}".format(r=rv.texto, e=e, u=u)))
    r["revisar"] = rv.clave
    for col, letra in (("MIN", "n"), ("MAX", "x")):
        n = _numero(v(col), col, mal)
        if n is not None and letra not in rv.usa:
            mal.append((col, "«{r}» no usa {c}".format(r=rv.texto, c=col)))
        r["min" if col == "MIN" else "max"] = n
    if r["min"] is not None and r["max"] is not None and r["min"] > r["max"]:
        r["min"], r["max"] = r["max"], r["min"]
    r["valores"] = _valores(v("VALORES"), rv, u, r["tipo"], tipos, mal)
    if r["valores"] and "v" not in rv.usa:
        mal.append(("VALORES", "«{r}» no usa VALORES (usa MIN/MAX)".format(r=rv.texto)))
    if rv.clave != "referencia" and r["min"] is None and r["max"] is None and not r["valores"]:
        mal.append(("MIN" if "v" not in rv.usa else "VALORES", "falta el valor: escribe MIN, MAX o VALORES"))
    cu, ct = nc.clave(v("CON UTILIDAD")), v("CON TIPO")
    if rv.con:
        if cu != CUALQUIERA and cu not in nc.UTILIDADES:
            mal.append(("CON UTILIDAD", "elige la otra utilidad (o CUALQUIERA)"))
        r["con_utilidad"] = cu
        if nc.clave(ct):
            if cu == CUALQUIERA:
                mal.append(("CON TIPO", "con CUALQUIERA no va un tipo"))
            r["con_tipo"] = tipo_ok("CON TIPO", cu, ct)
    elif cu or nc.clave(ct):
        mal.append(("CON UTILIDAD", "solo las separaciones van CON otra utilidad"))
    nivel = nc.clave(v("NIVEL")) or "AVISO"
    if nivel not in NIVELES:
        mal.append(("NIVEL", "escribe ERROR, AVISO o INFO"))
    r["nivel"] = nivel if nivel in NIVELES else "AVISO"
    r["fuente"], r["nota"] = str(v("FUENTE") or ""), str(v("NOTA") or "")
    return (None if mal else r), mal


def _numero(texto, col, mal):
    if texto in (None, "") or (isinstance(texto, str) and not texto.strip()):
        return None
    n = nc.numero(texto)
    if n is None:
        mal.append((col, "«{v}» no es un número (sin unidades ni símbolos)".format(v=texto)))
    return n


def _valores(texto, rv, util, tipo, tipos, mal):
    if texto in (None, "") or (isinstance(texto, str) and not texto.strip()):
        return []
    if rv.valores == NUM:
        nums = nc.lista_numeros(texto)
        if isinstance(texto, (int, float)) and not isinstance(texto, bool):
            return nums
        if len(nums) != len(_partes(texto)):
            mal.append(("VALORES", "«{v}» no es una lista de números como 6; 8; 12".format(v=texto)))
        if rv.clave == "ramal_pasos" and (len(nums) != 1 or nums and not float(nums[0]).is_integer()):
            mal.append(("VALORES", "un solo número entero: -1 = un tamaño menor"))
        return nums
    if rv.valores == SINO:
        ok, fuera = _de_lista(texto, (SI, NO))
        if fuera or len(ok) != 1:
            mal.append(("VALORES", "escribe SI o NO"))
        return ok[:1]
    if rv.valores == MATERIAL:
        ok, fuera = _de_lista(texto, MATERIALES)
        if fuera:
            mal.append(("VALORES", "«{v}» no es un material de la app ({m})".format(
                v="; ".join(fuera), m=", ".join(MATERIALES))))
        return ok
    ok = [nc.clave(x) for x in _partes(texto)]           # tipos de la utilidad
    if tipos is not None:
        fuera = [x for x in ok if (util, x) not in tipos]
        if fuera:
            mal.append(("VALORES", "«{v}» no es un tipo de {u} (pestaña/hoja TIPOS)".format(
                v="; ".join(fuera), u=util)))
    return ok


def tipos_usados(regla):
    """[(utilidad, tipo)] que la regla nombra (se suman a TIPOS)."""
    out = []
    if regla.get("tipo"):
        out.append((regla["utilidad"], regla["tipo"]))
    if regla.get("con_tipo") and regla.get("con_utilidad") in nc.UTILIDADES:
        out.append((regla["con_utilidad"], regla["con_tipo"]))
    rv = POR_CLAVE.get(regla.get("revisar"))
    if rv is not None and rv.valores == TIPOS_:
        out += [(regla["utilidad"], t) for t in regla.get("valores") or []]
    return out
