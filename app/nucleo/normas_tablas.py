"""Las normativas como TEXTO para editarlas en la aplicación (PURO: sin Qt).

Pedido del usuario 2026-10-20: «que todo sea editable desde la aplicación… la aplicación manda en todo», y
2026-10-21: una sola tabla de reglas (`normas_reglas`). La ventana muestra dos tablas —Tipos y Reglas, las
mismas hojas del Excel— y aquí está lo que no es interfaz:

  • `TABLAS` y `tipo_columna`: qué va en cada columna. `opciones(col, fila, tipos)` = la lista que ofrece la
    app para esa celda según el resto de la fila (TIPO = los de su utilidad; ELEMENTO = los que existen en
    esa utilidad; REVISAR = lo que se mide de ese elemento; VALORES = SI/NO, tipos o materiales según
    REVISAR…), o None = texto/número libre.
  • `filas(cat, clave)` / `catalogo(textos)`: ida y vuelta con `normas_reglas.leer_fila` —las MISMAS reglas que
    al importar el Excel— y la lista de problemas por celda (un TIPO que no está en la tabla Tipos también).
  • `renombrar_tipo`: cambiar el nombre de un tipo en Tipos lo cambia en las reglas.
  • `frase(fila)`: la regla leída como frase («En AGUA · DISTRIBUCION PRINCIPAL, Tubería: Diámetro…»).
"""
from __future__ import annotations

from dataclasses import dataclass

from nucleo import normas_catalogo as nc
from nucleo import normas_reglas as NR
from traduccion.i18n_core import N_, t

UTILIDAD, TIPO, ELEMENTO, REVISAR, NUMERO, VALORES, MATERIAL, CON_UTILIDAD, CON_TIPO, NIVEL, SINO, TEXTO = (
    "utilidad", "tipo", "elemento", "revisar", "numero", "valores", "material", "con_utilidad", "con_tipo",
    "nivel", "sino", "texto")


@dataclass(frozen=True)
class Tabla:
    clave: str                       # «tipos» / «reglas»
    hoja: str                        # la del Excel
    titulo: str                      # pestaña (español; la interfaz lo traduce)
    columnas: tuple


TABLAS = (
    Tabla("tipos", "TIPOS", N_("Tipos"), ("UTILIDAD", "TIPO")),
    Tabla("reglas", "REGLAS", N_("Reglas"), NR.COLUMNAS),
)
_POR_COL = {"ACTIVA": SINO, "UTILIDAD": UTILIDAD, "TIPO": TIPO, "ELEMENTO": ELEMENTO, "SI MATERIAL": MATERIAL,
            "REVISAR": REVISAR, "VALORES": VALORES, "CON UTILIDAD": CON_UTILIDAD, "CON TIPO": CON_TIPO,
            "NIVEL": NIVEL}


def tipo_columna(tabla, col):
    """Qué va en la columna `col`. En Tipos, la columna TIPO es texto libre: ahí se CREAN los tipos."""
    if tabla.clave == "tipos":
        return UTILIDAD if col == "UTILIDAD" else TEXTO
    if col in NR.NUMERICAS:
        return NUMERO
    return _POR_COL.get(col, TEXTO)


def tipos_de(textos_tipos, utilidad):
    """Tipos de la utilidad en las filas (de texto) de la tabla Tipos, sin repetir."""
    u, out = nc.clave(utilidad), []
    for fila in textos_tipos or []:
        if len(fila) >= 2 and nc.clave(fila[0]) == u and nc.clave(fila[1]) and nc.clave(fila[1]) not in out:
            out.append(nc.clave(fila[1]))
    return out


def _col(fila, col):
    k = NR.COLUMNAS.index(col)
    return (fila[k] if k < len(fila) else "") or ""


def opciones(col, fila, textos_tipos):
    """[(valor, ayuda)] que ofrece la app para la celda `col` de la regla `fila` (textos), o None = libre.
    Las de VALORES y SI MATERIAL admiten varias separadas con «;»."""
    u = nc.clave(_col(fila, "UTILIDAD"))
    if col == "ACTIVA":
        return [(NR.SI, ""), (NR.NO, "")]
    if col == "UTILIDAD":
        return [(x, "") for x in nc.UTILIDADES]
    if col == "TIPO":
        return [("", "")] + [(x, "") for x in tipos_de(textos_tipos, u)]
    if col == "ELEMENTO":
        return [(e, "") for e in NR.elementos_de(u)] if u in nc.UTILIDADES else [(e, "") for e in NR.ELEMENTOS]
    if col == "REVISAR":
        e = nc.clave(_col(fila, "ELEMENTO")) or NR.TUBERIA
        return [(r.texto, "") for r in NR.revisar_de(u, e)]
    if col == "SI MATERIAL":
        return [("", "")] + [(m, "") for m in NR.MATERIALES]
    if col == "VALORES":
        rv = NR.POR_TEXTO.get(nc.clave(_col(fila, "REVISAR")))
        if rv is None or rv.valores == NR.NUM:
            return None
        if rv.valores == NR.SINO:
            return [(NR.SI, ""), (NR.NO, "")]
        if rv.valores == NR.MATERIAL:
            return [(m, "") for m in NR.MATERIALES]
        return [(x, "") for x in tipos_de(textos_tipos, u)]
    if col == "CON UTILIDAD":
        return [("", "")] + [(x, "") for x in nc.UTILIDADES + (NR.CUALQUIERA,)]
    if col == "CON TIPO":
        return [("", "")] + [(x, "") for x in tipos_de(textos_tipos, _col(fila, "CON UTILIDAD"))]
    if col == "NIVEL":
        return [(n, "") for n in NR.NIVELES]
    return None


def filas(cat, clave):
    """Filas de texto de la tabla `clave`, en el orden de sus columnas."""
    if clave == "tipos":
        return [list(x) for x in cat.get("tipos", [])]
    return [NR.fila_de(r) for r in cat.get("reglas", [])]


def catalogo(textos):
    """(catálogo, problemas): `textos` = {clave de tabla: [[celda, …]]}. Cada problema es (clave de tabla, fila
    desde 0, columna, motivo); las filas vacías no cuentan."""
    problemas, tipos = [], []
    for n, fila in enumerate(textos.get("tipos") or []):
        u, tp = (fila + ["", ""])[:2]
        if not (str(u).strip() or str(tp).strip()):
            continue
        if nc.clave(u) not in nc.UTILIDADES:
            problemas.append(("tipos", n, "UTILIDAD", "«{v}» no es una utilidad de la aplicación".format(v=u)))
        elif not nc.clave(tp):
            problemas.append(("tipos", n, "TIPO", "está vacío"))
        elif [nc.clave(u), nc.clave(tp)] not in tipos:
            tipos.append([nc.clave(u), nc.clave(tp)])
    estrictos = {tuple(x) for x in tipos}
    reglas = []
    for n, fila in enumerate(textos.get("reglas") or []):
        if not any(str(v).strip() for k, v in enumerate(fila) if NR.COLUMNAS[k] not in ("ACTIVA", "NIVEL")):
            continue
        r, mal = NR.leer_fila(fila, estrictos)
        problemas += [("reglas", n, col, motivo) for col, motivo in mal]
        if r is not None:
            reglas.append(r)
    return nc.normalizar({"tipos": tipos, "reglas": reglas}), problemas


def renombrar_tipo(textos, utilidad, viejo, nuevo):
    """El tipo `viejo` de la utilidad pasa a llamarse `nuevo` en las reglas (TIPO, CON TIPO y los VALORES de
    «Solo en tipos»), en sitio. Devuelve cuántas celdas cambió."""
    u, v, n = nc.clave(utilidad), nc.clave(viejo), nc.clave(nuevo)
    if not (u and v and n) or v == n:
        return 0
    k_u, k_t = NR.COLUMNAS.index("UTILIDAD"), NR.COLUMNAS.index("TIPO")
    k_cu, k_ct = NR.COLUMNAS.index("CON UTILIDAD"), NR.COLUMNAS.index("CON TIPO")
    k_r, k_v = NR.COLUMNAS.index("REVISAR"), NR.COLUMNAS.index("VALORES")
    cambios = 0
    for fila in textos.get("reglas") or []:
        if nc.clave(fila[k_u]) == u and nc.clave(fila[k_t]) == v:
            fila[k_t] = n
            cambios += 1
        if nc.clave(fila[k_cu]) == u and nc.clave(fila[k_ct]) == v:
            fila[k_ct] = n
            cambios += 1
        rv = NR.POR_TEXTO.get(nc.clave(fila[k_r]))
        if nc.clave(fila[k_u]) == u and rv is not None and rv.valores == NR.TIPOS_:
            partes = [x.strip() for x in str(fila[k_v]).split(";") if x.strip()]
            if any(nc.clave(x) == v for x in partes):
                fila[k_v] = "; ".join(n if nc.clave(x) == v else x for x in partes)
                cambios += 1
    return cambios


def frase(fila):
    """La regla como frase, para el globo de la fila («En AGUA · DISTRIBUCION PRINCIPAL, Tubería: …»)."""
    from nucleo import normas_validar as V
    r, _mal = NR.leer_fila(fila)
    if r is None:
        return ""
    rv = NR.POR_CLAVE[r["revisar"]]
    donde = " · ".join(x for x in (r["utilidad"], r["tipo"]) if x)
    cond = V.condiciones(dict(r, tipo=""))
    txt = t("En {donde}, {elemento}").format(donde=donde, elemento=r["elemento"])
    if cond:
        txt += " (" + t("si") + " " + ", ".join(cond) + ")"
    if rv.clave == "referencia":
        txt += ": " + t("solo referencia (no se revisa).")
    else:
        txt += ": " + rv.texto + " " + V.requisito(r)
        if r.get("con_utilidad"):
            txt += " " + t("con {u}").format(u=" · ".join(x for x in (r["con_utilidad"], r["con_tipo"]) if x))
        txt += "."
    if not r.get("activa", True):
        txt += " " + t("(desactivada)")
    if r.get("nota"):
        txt += "\n" + r["nota"]
    if r.get("fuente"):
        txt += "\n" + t("Fuente: {f}").format(f=r["fuente"])
    return txt
