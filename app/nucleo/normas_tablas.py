"""Las tablas de normativas como TEXTO para editarlas en la aplicación (PURO: sin Qt).

Pedido del usuario 2026-10-20: «que todo sea editable desde la aplicación… la aplicación manda en
todo». La ventana de normativas muestra las cuatro tablas del Excel (`normas_excel`) y deja editarlas,
agregar y quitar filas; aquí está lo que no es interfaz:

  • `TABLAS`: cada tabla con su hoja del Excel, sus columnas y QUÉ va en cada una (`tipo_columna`):
    utilidad (de la app, `model.TIPOS`), tipo (de esa utilidad, de la tabla TIPOS), accesorio (los que la
    app reconoce), estructura, número, lista de números o texto libre. La interfaz ofrece un desplegable
    donde la app decide los valores.
  • `filas(cat, clave)`: el catálogo en texto, como se ve en el Excel («6; 8; 12», «1,5»).
  • `catalogo(textos)`: de vuelta al catálogo con `normas_excel.armar` —las MISMAS reglas que al importar
    el Excel— y la lista de problemas por celda; un TIPO que no está en la tabla TIPOS es un problema.
  • `renombrar_tipo`: cambiar el nombre de un tipo en TIPOS lo cambia en las demás tablas.
"""
from __future__ import annotations

from dataclasses import dataclass

from nucleo import normas_catalogo as nc
from nucleo import normas_excel as NE
from traduccion.i18n_core import N_

UTILIDAD, TIPO, ACCESORIO, ESTRUCTURA, NUMERO, LISTA, TEXTO = (
    "utilidad", "tipo", "accesorio", "estructura", "numero", "lista", "texto")


@dataclass(frozen=True)
class Tabla:
    clave: str                       # la del catálogo («tipos», «diametros», …)
    hoja: str                        # la del Excel
    titulo: str                      # pestaña (español; la interfaz lo traduce)
    columnas: tuple


TABLAS = (
    Tabla("tipos", NE.HOJA_TIPOS, N_("Tipos"), NE.COL_TIPOS),
    Tabla("diametros", NE.HOJA_DIAM, N_("Diámetros (presión)"), NE.COL_DIAM),
    Tabla("accesorios", NE.HOJA_ACC, N_("Accesorios (presión)"), NE.COL_ACC),
    Tabla("electricas", NE.HOJA_ELEC, N_("Eléctrico y telecom"), NE.COL_ELEC),
)
_TIPO_COLS = {(NE.HOJA_TIPOS, "TIPO"), (NE.HOJA_DIAM, "TIPO"), (NE.HOJA_ACC, "SOLO SE PERMITE EN"),
              (NE.HOJA_ACC, "PROHIBIDO USO"), (NE.HOJA_ELEC, "TIPO")}


def tipo_columna(tabla, col):
    """Qué va en la columna `col` de la tabla (ver arriba). En TIPOS, la columna TIPO es texto libre: ahí
    se CREAN los tipos (en las demás se eligen)."""
    if col == "UTILIDAD":
        return UTILIDAD
    if col == "ACCESORIO":
        return ACCESORIO
    if col == "ESTRUCTURA":
        return ESTRUCTURA
    if (tabla.hoja, col) in _TIPO_COLS:
        return TEXTO if tabla.hoja == NE.HOJA_TIPOS else TIPO
    if col in NE.NUMERICAS:
        return NUMERO
    if col in NE.LISTAS:
        return LISTA
    return TEXTO


def _n(v):
    return "" if v is None else nc.texto_numero(v)


def _extremos(r):
    return ["", ""] if not r else [_n(r[0]), _n(r[1])]


def filas(cat, clave):
    """Filas de texto de la tabla `clave`, en el orden de sus columnas."""
    if clave == "tipos":
        return [list(x) for x in cat.get("tipos", [])]
    if clave == "diametros":
        return [[f["utilidad"], f["tipo"], nc.texto_lista(f["diametros"]), _n(f.get("diam_min")),
                 _n(f.get("diam_max")), f.get("nota") or ""] for f in cat.get("diametros", [])]
    if clave == "accesorios":
        return [[f["utilidad"], f["accesorio"], f.get("solo_en") or "", nc.texto_lista(f.get("diam_principal")),
                 f.get("prohibido_en") or "", "" if f.get("ramal") is None else f"{int(f['ramal'])}",
                 nc.texto_lista(f.get("angulos"))] for f in cat.get("accesorios", [])]
    return [[f["utilidad"], f.get("estructura") or "", f.get("tipo") or "", *_extremos(f.get("amperaje")),
             *_extremos(f.get("longitud")), nc.texto_lista(f.get("diam_fijo")), _n(f.get("diam_min")),
             _n(f.get("diam_max")), _n(f.get("radio_min")), _n(f.get("radio_max")),
             nc.texto_lista(f.get("radio_fijo"))] for f in cat.get("electricas", [])]


def catalogo(textos):
    """(catálogo, problemas): `textos` = {clave de tabla: [[celda, …] en el orden de sus columnas]}.
    Cada problema es (clave de tabla, fila desde 0, columna, mensaje); las filas vacías no cuentan."""
    hojas, problemas = {}, []
    por_hoja = {t.hoja: t for t in TABLAS}
    for t in TABLAS:
        dicts = []
        for n, fila in enumerate(textos.get(t.clave) or []):
            d = {nc.clave(c): (v.strip() if isinstance(v, str) else v) for c, v in zip(t.columnas, fila)}
            if any(v not in (None, "") for v in d.values()):
                d["_fila"] = n
                dicts.append(d)
        hojas[t.hoja] = dicts
    crudos = []
    cat = NE.armar(hojas, crudos, tipos_estrictos=True)
    for texto in crudos:                       # «HOJA, fila N, COLUMNA: «v» motivo»
        hoja, _, resto = texto.partition(", fila ")
        num, _, resto = resto.partition(", ")
        col, _, motivo = resto.partition(": ")
        t = por_hoja.get(hoja)
        try:
            fila = int(num)
        except ValueError:
            fila = -1
        problemas.append((t.clave if t else hoja, fila, col, motivo or texto))
    return cat, problemas


def tipos_de(textos_tipos, utilidad):
    """Tipos de la utilidad en las filas (de texto) de la tabla TIPOS, sin repetir."""
    u, out = nc.clave(utilidad), []
    for fila in textos_tipos or []:
        if len(fila) >= 2 and nc.clave(fila[0]) == u and nc.clave(fila[1]) and nc.clave(fila[1]) not in out:
            out.append(nc.clave(fila[1]))
    return out


def renombrar_tipo(textos, utilidad, viejo, nuevo):
    """El tipo `viejo` de la utilidad pasa a llamarse `nuevo` en las demás tablas (en sitio). Devuelve
    cuántas celdas cambió."""
    u, v, n = nc.clave(utilidad), nc.clave(viejo), nc.clave(nuevo)
    if not (u and v and n) or v == n:
        return 0
    cambios = 0
    for t in TABLAS[1:]:
        cols = [k for k, c in enumerate(t.columnas) if tipo_columna(t, c) == TIPO]
        for fila in textos.get(t.clave) or []:
            if nc.clave(fila[0]) != u:
                continue
            for k in cols:
                if nc.clave(fila[k]) == v:
                    fila[k] = n
                    cambios += 1
    return cambios
