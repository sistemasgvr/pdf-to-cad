"""Excel de normativas en el formato del usuario (PURO: sin Qt; usa openpyxl).

`importar(ruta)` lee las hojas TIPOS, PRESION-DIAMETROS, PRESION-ACCESORIOS y
ELECT-TELECOM (los encabezados se buscan por NOMBRE, no por posición; hojas y columnas
que no estén se toman vacías) y `exportar(cat, ruta)` escribe el mismo libro: cada
hoja como tabla de Excel, con desplegables que se alimentan SOLOS de la hoja TIPOS
(UTILIDAD → las 6 utilidades; TIPO → solo los tipos de la utilidad de esa fila, aunque
se agreguen filas nuevas a TIPOS en cualquier orden). Para eso TIPOS lleva un bloque
auxiliar oculto (K:P) con una columna por utilidad: FILTER sobre la tabla de tipos
(Excel 365). Ver `normas_catalogo` para el significado de cada columna.
"""
from __future__ import annotations

from nucleo import normas_catalogo as nc

HOJA_TIPOS = "TIPOS"
HOJA_DIAM = "PRESION-DIAMETROS"
HOJA_ACC = "PRESION-ACCESORIOS"
HOJA_ELEC = "ELECT-TELECOM"

COL_TIPOS = ("UTILIDAD", "TIPO")
COL_DIAM = ("UTILIDAD", "TIPO", "DIAMETRO (in)", "SOLO SE PERMITE EN")
COL_ACC = ("UTILIDAD", "ACCESORIO", "SOLO SE PERMITE EN", "DIAMETRO PRINCIPAL", "PROHIBIDO USO",
           "DIAMETRO RAMAL DISTRIBUCION", "ANGULOS PERMITIDOS")
COL_ELEC = ("UTILIDAD", "ESTRUCTURA", "TIPO", "AMPERAJE (A)", "LONGITUD RANGO (pies)", "DIAMETRO FIJO (in)",
            "DIAMETRO MIN (in)", "DIAMETRO MAX (in)", "RADIO CURVA MIN (pies)")
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
    for f in filas[1:]:
        d = {cab[i]: v for i, v in enumerate(f) if i < len(cab) and cab[i]}
        if any(v not in (None, "") for v in d.values()):
            out.append(d)
    return out


def _txt(d, col):
    v = d.get(nc.clave(col))
    return "" if v is None else str(v).strip()


def importar(ruta):
    """(catálogo, avisos): avisos = textos de lo que no se pudo leer (hoja que falta…)."""
    import openpyxl
    wb = openpyxl.load_workbook(ruta, data_only=True)
    avisos = []
    cat = {"tipos": [], "diametros": [], "accesorios": [], "electricas": []}
    hojas = {n: _hoja(wb, n) for n in (HOJA_TIPOS, HOJA_DIAM, HOJA_ACC, HOJA_ELEC)}
    for n, ws in hojas.items():
        if ws is None:
            avisos.append(n)
    for d in _filas(hojas[HOJA_TIPOS]):
        u, t = nc.clave(_txt(d, "UTILIDAD")), nc.clave(_txt(d, "TIPO"))
        if u and t:
            cat["tipos"].append([u, t])
    for d in _filas(hojas[HOJA_DIAM]):
        cat["diametros"].append({"utilidad": nc.clave(_txt(d, "UTILIDAD")), "tipo": nc.clave(_txt(d, "TIPO")),
                                 "diametros": nc.lista_numeros(d.get(nc.clave("DIAMETRO (in)"))),
                                 "nota": _txt(d, "SOLO SE PERMITE EN")})
    for d in _filas(hojas[HOJA_ACC]):
        cat["accesorios"].append({
            "utilidad": nc.clave(_txt(d, "UTILIDAD")), "accesorio": _txt(d, "ACCESORIO"),
            "solo_en": nc.clave(_txt(d, "SOLO SE PERMITE EN")),
            "diam_principal": nc.lista_numeros(d.get(nc.clave("DIAMETRO PRINCIPAL"))),
            "prohibido_en": nc.clave(_txt(d, "PROHIBIDO USO")),
            "ramal": nc.numero(d.get(nc.clave("DIAMETRO RAMAL DISTRIBUCION"))),
            "angulos": nc.lista_numeros(d.get(nc.clave("ANGULOS PERMITIDOS")))})
    for d in _filas(hojas[HOJA_ELEC]):
        cat["electricas"].append({
            "utilidad": nc.clave(_txt(d, "UTILIDAD")), "estructura": nc.clave(_txt(d, "ESTRUCTURA")),
            "tipo": nc.clave(_txt(d, "TIPO")),
            "amperaje": nc.rango(d.get(nc.clave("AMPERAJE (A)"))),
            "longitud": nc.rango(d.get(nc.clave("LONGITUD RANGO (pies)"))),
            "diam_fijo": nc.lista_numeros(d.get(nc.clave("DIAMETRO FIJO (in)"))),
            "diam_min": nc.numero(d.get(nc.clave("DIAMETRO MIN (in)"))),
            "diam_max": nc.numero(d.get(nc.clave("DIAMETRO MAX (in)"))),
            "radio_min": nc.numero(d.get(nc.clave("RADIO CURVA MIN (pies)")))})
    return nc.normalizar(cat), avisos


# ─────────────────────────── exportar ───────────────────────────

def _celda(v):
    return None if v in (None, "", []) else v


def _filas_export(cat):
    tipos = [list(t) for t in cat.get("tipos", [])]
    tipos.sort(key=lambda t: (nc.UTILIDADES.index(t[0]) if t[0] in nc.UTILIDADES else 99,))
    diam = [[f["utilidad"], f["tipo"] or None,
             (f["diametros"][0] if len(f["diametros"]) == 1 else nc.texto_lista(f["diametros"])) or None,
             f.get("nota") or None] for f in cat.get("diametros", [])]
    acc = [[f["utilidad"], f["accesorio"], _celda(f.get("solo_en")), _celda(nc.texto_lista(f.get("diam_principal"))),
            _celda(f.get("prohibido_en")), (int(f["ramal"]) if f.get("ramal") is not None else None),
            _celda(nc.texto_lista(f.get("angulos")))] for f in cat.get("accesorios", [])]
    elec = []
    for f in cat.get("electricas", []):
        fijo = f.get("diam_fijo") or []
        elec.append([f["utilidad"], _celda(f.get("estructura")), _celda(f.get("tipo")),
                     _celda(nc.texto_rango(f.get("amperaje"))), _celda(nc.texto_rango(f.get("longitud"))),
                     (fijo[0] if len(fijo) == 1 else _celda(nc.texto_lista(fijo))),
                     f.get("diam_min"), f.get("diam_max"), f.get("radio_min")])
    return tipos, diam, acc, elec


def _tabla(ws, nombre, cabecera, filas, anchos):
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.table import Table, TableStyleInfo
    ws.append(list(cabecera))
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
    _tabla(wd, "TablaPresionDiametros", COL_DIAM, diam, [16, 30, 18, 60])
    wa = wb.create_sheet(HOJA_ACC)
    _tabla(wa, "TablaPresionAccesorios", COL_ACC, acc, [14, 18, 30, 20, 30, 18, 22])
    we = wb.create_sheet(HOJA_ELEC)
    _tabla(we, "TablaElectricaTelecom", COL_ELEC, elec, [14, 14, 30, 14, 16, 14, 14, 14, 16])

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
    wb.save(ruta)
