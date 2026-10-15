"""Excel de normativas en el formato del usuario (PURO: sin Qt; usa openpyxl).

`importar(ruta)` lee las hojas TIPOS, PRESION-DIAMETROS, PRESION-ACCESORIOS y
ELECT-TELECOM (los encabezados se buscan por NOMBRE, no por posición; hojas y columnas
que no estén se toman vacías) y `exportar(cat, ruta)` escribe el mismo libro: cada
hoja como tabla de Excel, con desplegables que se alimentan SOLOS de la hoja TIPOS
(UTILIDAD → las 6 utilidades; TIPO → solo los tipos de la utilidad de esa fila, aunque
se agreguen filas nuevas a TIPOS en cualquier orden). Para eso TIPOS lleva un bloque
auxiliar oculto (K:P) con una columna por utilidad: FILTER sobre la tabla de tipos
(Excel 365). Ver `normas_catalogo` para el significado de cada columna.

Rangos en DOS columnas MIN y MAX (2026-10-14); se sigue leyendo el formato viejo «0-320» en
«AMPERAJE (A)» / «LONGITUD RANGO (pies)». `importar(ruta, problemas=[])` anota cada celda que
no se entiende (hoja, fila, columna) y no la usa. Al exportar cada encabezado lleva un
comentario de Excel con lo que va ahí, las columnas de un solo número validan que sea un
número, y la primera hoja es INSTRUCCIONES (`normas_excel_ayuda`); esa hoja y cualquier
otra que no sea de las cuatro tablas («auxiliar») NUNCA se leen.
"""
from __future__ import annotations

from nucleo import normas_catalogo as nc
from nucleo import normas_excel_ayuda as ayuda

HOJA_TIPOS = "TIPOS"
HOJA_DIAM = "PRESION-DIAMETROS"
HOJA_ACC = "PRESION-ACCESORIOS"
HOJA_ELEC = "ELECT-TELECOM"

COL_TIPOS = ("UTILIDAD", "TIPO")
COL_DIAM = ("UTILIDAD", "TIPO", "DIAMETRO (in)", "DIAMETRO MIN (in)", "DIAMETRO MAX (in)", "SOLO SE PERMITE EN")
COL_ACC = ("UTILIDAD", "ACCESORIO", "SOLO SE PERMITE EN", "DIAMETRO PRINCIPAL (in)", "PROHIBIDO USO",
           "DIAMETRO RAMAL DISTRIBUCION", "ANGULOS PERMITIDOS")
COL_ELEC = ("UTILIDAD", "ESTRUCTURA", "TIPO", "AMPERAJE MIN (A)", "AMPERAJE MAX (A)", "LONGITUD MIN (pies)",
            "LONGITUD MAX (pies)", "DIAMETRO FIJO (in)", "DIAMETRO MIN (in)", "DIAMETRO MAX (in)",
            "RADIO CURVA MIN (pies)", "RADIO CURVA MAX (pies)", "RADIO CURVA FIJO (pies)")
# Columnas de UN número (validación numérica al exportar; aviso al importar si no lo es).
NUMERICAS = {"DIAMETRO MIN (in)", "DIAMETRO MAX (in)", "AMPERAJE MIN (A)", "AMPERAJE MAX (A)",
             "LONGITUD MIN (pies)", "LONGITUD MAX (pies)", "RADIO CURVA MIN (pies)", "RADIO CURVA MAX (pies)",
             "DIAMETRO RAMAL DISTRIBUCION"}
LISTAS = {"DIAMETRO (in)", "DIAMETRO PRINCIPAL (in)", "DIAMETRO FIJO (in)", "ANGULOS PERMITIDOS",
          "RADIO CURVA FIJO (pies)"}
# Otros nombres que se aceptan para una columna (el ingeniero le sumó «(in)», 2026-10-14).
ALIAS = {"DIAMETRO PRINCIPAL (in)": ("DIAMETRO PRINCIPAL",)}
# Columnas del formato viejo que se siguen leyendo (rango «0-320» en una celda).
VIEJAS = {HOJA_ELEC: ("AMPERAJE (A)", "LONGITUD RANGO (pies)")}
AUX = "KLMNOP"                      # columnas del bloque auxiliar de TIPOS (una por utilidad)
FILAS_DV = 500                      # filas con desplegable (las tablas crecen dentro)
ESTILO_TABLA = "TableStyleMedium10"


# ─────────────────────────── importar ───────────────────────────

def _hoja(wb, nombre):
    for ws in wb.worksheets:
        if nc.clave(ws.title) == nc.clave(nombre):
            return ws
    return None


def _filas(ws):
    """[{encabezado: valor}] de la primera tabla de la hoja (fila 1 = encabezados)."""
    if ws is None:
        return []
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return []
    cab = [nc.clave(c) for c in filas[0]]
    out = []
    for n, f in enumerate(filas[1:], 2):
        d = {cab[i]: v for i, v in enumerate(f) if i < len(cab) and cab[i]}
        if any(v not in (None, "") for v in d.values()):
            d["_fila"] = n
            out.append(d)
    return out


class _Lector:
    """Lee celdas y anota las que no se entienden («Hoja, fila N, COLUMNA: «>=400» no es un número»)."""

    def __init__(self, problemas):
        self.problemas = problemas if problemas is not None else []

    def _mal(self, hoja, d, col, v, que):
        self.problemas.append(f"{hoja}, fila {d.get('_fila', '?')}, {col}: «{v}» {que}")

    def numero(self, hoja, d, col):
        v = _val(d, col)
        n = nc.numero(v)
        if n is None and v not in (None, "") and str(v).strip():
            self._mal(hoja, d, col, v, "no es un número")
        return n

    def lista(self, hoja, d, col):
        v = _val(d, col)
        nums = nc.lista_numeros(v)
        partes = [x for x in str(v).split(";") if x.strip()] if v not in (None, "") else []
        if len(nums) != len(partes) and not isinstance(v, (int, float)):
            self._mal(hoja, d, col, v, "no es una lista como 6; 8; 12")
        return nums

    def rango(self, hoja, d, col_min, col_max, col_vieja):
        """[mín, máx] de las columnas MIN/MAX, o del formato viejo «0-320» en una celda."""
        r = nc.rango_min_max(self.numero(hoja, d, col_min), self.numero(hoja, d, col_max))
        if r is None and col_vieja:
            v = d.get(nc.clave(col_vieja))
            r = nc.rango(v)
            if r is None and v not in (None, "") and str(v).strip():
                self._mal(hoja, d, col_vieja, v, "no se entiende (usa MIN y MAX)")
        return r


def _val(d, col):
    """Valor de la columna `col` (o de uno de sus otros nombres, `ALIAS`)."""
    for nombre in (col,) + ALIAS.get(col, ()):
        if nc.clave(nombre) in d:
            return d[nc.clave(nombre)]
    return None


def _txt(d, col):
    v = _val(d, col)
    return "" if v is None else str(v).strip()


def _columnas_desconocidas(ws, columnas, lee):
    """Anota cada encabezado de la tabla que la app no conoce (sus datos no se usarían)."""
    if ws is None:
        return
    conocidas = {nc.clave(c) for c in columnas}
    conocidas |= {nc.clave(a) for c in columnas for a in ALIAS.get(c, ())}
    conocidas |= {nc.clave(c) for c in VIEJAS.get(ws.title.upper(), ())}
    if nc.clave(ws.title) == nc.clave(HOJA_TIPOS):
        conocidas |= {nc.clave(u) for u in nc.UTILIDADES}          # bloque auxiliar oculto (K:P)
    fila = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    for v in fila:
        if v not in (None, "") and nc.clave(v) not in conocidas and not str(v).strip().startswith("_"):
            lee.problemas.append(f"{ws.title}: columna «{v}» desconocida")


def importar(ruta, problemas=None):
    """(catálogo, hojas que faltan). Si se pasa la lista `problemas`, se le agrega cada celda
    que no se entendió (y que por eso no se usa)."""
    import openpyxl
    wb = openpyxl.load_workbook(ruta, data_only=True)
    lee = _Lector(problemas)
    avisos = []
    cat = {"tipos": [], "diametros": [], "accesorios": [], "electricas": []}
    hojas = {n: _hoja(wb, n) for n in (HOJA_TIPOS, HOJA_DIAM, HOJA_ACC, HOJA_ELEC)}
    for n, ws in hojas.items():
        if ws is None:
            avisos.append(n)
    for n, cols in ((HOJA_TIPOS, COL_TIPOS), (HOJA_DIAM, COL_DIAM), (HOJA_ACC, COL_ACC), (HOJA_ELEC, COL_ELEC)):
        _columnas_desconocidas(hojas[n], cols, lee)
    for d in _filas(hojas[HOJA_TIPOS]):
        u, t = nc.clave(_txt(d, "UTILIDAD")), nc.clave(_txt(d, "TIPO"))
        if u and t:
            cat["tipos"].append([u, t])
    H = HOJA_DIAM
    for d in _filas(hojas[H]):
        cat["diametros"].append({"utilidad": nc.clave(_txt(d, "UTILIDAD")), "tipo": nc.clave(_txt(d, "TIPO")),
                                 "diametros": lee.lista(H, d, "DIAMETRO (in)"),
                                 "diam_min": lee.numero(H, d, "DIAMETRO MIN (in)"),
                                 "diam_max": lee.numero(H, d, "DIAMETRO MAX (in)"),
                                 "nota": _txt(d, "SOLO SE PERMITE EN")})
    H = HOJA_ACC
    for d in _filas(hojas[H]):
        cat["accesorios"].append({
            "utilidad": nc.clave(_txt(d, "UTILIDAD")), "accesorio": _txt(d, "ACCESORIO"),
            "solo_en": nc.clave(_txt(d, "SOLO SE PERMITE EN")),
            "diam_principal": lee.lista(H, d, "DIAMETRO PRINCIPAL (in)"),
            "prohibido_en": nc.clave(_txt(d, "PROHIBIDO USO")),
            "ramal": lee.numero(H, d, "DIAMETRO RAMAL DISTRIBUCION"),
            "angulos": lee.lista(H, d, "ANGULOS PERMITIDOS")})
    H = HOJA_ELEC
    for d in _filas(hojas[H]):
        cat["electricas"].append({
            "utilidad": nc.clave(_txt(d, "UTILIDAD")), "estructura": nc.clave(_txt(d, "ESTRUCTURA")),
            "tipo": nc.clave(_txt(d, "TIPO")),
            "amperaje": lee.rango(H, d, "AMPERAJE MIN (A)", "AMPERAJE MAX (A)", "AMPERAJE (A)"),
            "longitud": lee.rango(H, d, "LONGITUD MIN (pies)", "LONGITUD MAX (pies)", "LONGITUD RANGO (pies)"),
            "diam_fijo": lee.lista(H, d, "DIAMETRO FIJO (in)"),
            "diam_min": lee.numero(H, d, "DIAMETRO MIN (in)"),
            "diam_max": lee.numero(H, d, "DIAMETRO MAX (in)"),
            "radio_min": lee.numero(H, d, "RADIO CURVA MIN (pies)"),
            "radio_max": lee.numero(H, d, "RADIO CURVA MAX (pies)"),
            "radio_fijo": lee.lista(H, d, "RADIO CURVA FIJO (pies)")})
    return nc.normalizar(cat), avisos


# ─────────────────────────── exportar ───────────────────────────

def _celda(v):
    return None if v in (None, "", []) else v


def _filas_export(cat):
    tipos = [list(t) for t in cat.get("tipos", [])]
    tipos.sort(key=lambda t: (nc.UTILIDADES.index(t[0]) if t[0] in nc.UTILIDADES else 99,))
    diam = [[f["utilidad"], f["tipo"] or None,
             (f["diametros"][0] if len(f["diametros"]) == 1 else nc.texto_lista(f["diametros"])) or None,
             f.get("diam_min"), f.get("diam_max"), f.get("nota") or None] for f in cat.get("diametros", [])]
    acc = [[f["utilidad"], f["accesorio"], _celda(f.get("solo_en")), _celda(nc.texto_lista(f.get("diam_principal"))),
            _celda(f.get("prohibido_en")), (int(f["ramal"]) if f.get("ramal") is not None else None),
            _celda(nc.texto_lista(f.get("angulos")))] for f in cat.get("accesorios", [])]
    elec = []
    for f in cat.get("electricas", []):
        fijo = f.get("diam_fijo") or []
        amp, lar = f.get("amperaje") or [None, None], f.get("longitud") or [None, None]
        elec.append([f["utilidad"], _celda(f.get("estructura")), _celda(f.get("tipo")),
                     amp[0], amp[1], lar[0], lar[1],
                     (fijo[0] if len(fijo) == 1 else _celda(nc.texto_lista(fijo))),
                     f.get("diam_min"), f.get("diam_max"), f.get("radio_min"), f.get("radio_max"),
                     _celda(nc.texto_lista(f.get("radio_fijo")))])
    return tipos, diam, acc, elec


def _tabla(ws, nombre, cabecera, filas, anchos):
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.worksheet.table import Table, TableStyleInfo
    ws.append(list(cabecera))
    for k, col in enumerate(cabecera):
        texto = ayuda.comentario(ws.title, col)
        if texto:
            com = Comment(texto, "pdf-to-cad")
            com.width, com.height = 320, 40 + 16 * (texto.count("\n") + len(texto) // 45)
            ws.cell(row=1, column=k + 1).comment = com
        letra = chr(65 + k)
        if col in NUMERICAS:
            dv = DataValidation(type="decimal", operator="between", formula1="-1000000", formula2="1000000",
                                allow_blank=True, showErrorMessage=True, errorTitle=col,
                                error="Escribe UN número (sin símbolos ni unidades). Para un rango usa las "
                                      "columnas MIN y MAX.")
            dv.add(f"{letra}2:{letra}{FILAS_DV}")
            ws.add_data_validation(dv)
    for f in filas:
        ws.append([int(v) if isinstance(v, float) and v.is_integer() else v for v in f])
    for i, w in enumerate(anchos):
        ws.column_dimensions[chr(65 + i)].width = w
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "A2"
    t = Table(displayName=nombre, ref=f"A1:{chr(64 + len(cabecera))}{max(2, len(filas) + 1)}")
    t.tableStyleInfo = TableStyleInfo(name=ESTILO_TABLA, showRowStripes=True)
    ws.add_table(t)


def _desplegable(ws, rango, formula, titulo):
    from openpyxl.worksheet.datavalidation import DataValidation
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=True,
                        errorTitle=titulo,
                        error="Elige un valor de la lista (los tipos se agregan en la hoja TIPOS).")
    dv.add(rango)
    ws.add_data_validation(dv)


def exportar(cat, ruta):
    import openpyxl
    from openpyxl.worksheet.formula import ArrayFormula
    cat = nc.normalizar(cat)
    tipos, diam, acc, elec = _filas_export(cat)
    wb = openpyxl.Workbook()
    wt = wb.active
    wt.title = HOJA_TIPOS
    _tabla(wt, "TablaTipos", COL_TIPOS, tipos, [18, 34])
    # Bloque auxiliar oculto: los tipos de cada utilidad (se recalcula solo).
    for col, u in zip(AUX, nc.UTILIDADES):
        wt[f"{col}1"] = u
        ref = f"{col}2:{col}201"
        wt[f"{col}2"] = ArrayFormula(ref, f'=_xlfn._xlws.SORT(_xlfn.UNIQUE(_xlfn._xlws.FILTER('
                                          f'TablaTipos[TIPO],TablaTipos[UTILIDAD]={col}$1,"")))')
        wt.column_dimensions[col].hidden = True
    wd = wb.create_sheet(HOJA_DIAM)
    _tabla(wd, "TablaPresionDiametros", COL_DIAM, diam, [16, 30, 18, 14, 14, 60])
    wa = wb.create_sheet(HOJA_ACC)
    _tabla(wa, "TablaPresionAccesorios", COL_ACC, acc, [14, 18, 30, 20, 30, 18, 22])
    we = wb.create_sheet(HOJA_ELEC)
    _tabla(we, "TablaElectricaTelecom", COL_ELEC, elec, [14, 14, 30, 12, 12, 12, 12, 14, 14, 14, 14, 14, 14])

    util = f"TIPOS!${AUX[0]}$1:${AUX[-1]}$1"
    m = f"MATCH($A2,TIPOS!${AUX[0]}$1:${AUX[-1]}$1,0)-1"
    tipo = (f'OFFSET(TIPOS!${AUX[0]}$2,0,{m},MAX(1,COUNTIF(OFFSET(TIPOS!${AUX[0]}$2,0,{m},200,1),"?*")),1)')
    n = FILAS_DV
    for ws in (wt, wd, wa, we):
        _desplegable(ws, f"A2:A{n}", util, "Utilidad")
    _desplegable(wd, f"B2:B{n}", tipo, "Tipo")
    _desplegable(wa, f"C2:C{n}", tipo, "Tipo")
    _desplegable(wa, f"E2:E{n}", tipo, "Tipo")
    _desplegable(we, f"C2:C{n}", tipo, "Tipo")
    ayuda.escribir_instrucciones(wb)
    wb.active = 0
    wb.save(ruta)
