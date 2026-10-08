"""Plantilla UNIVERSAL de normativas en Excel: exportar e importar (PURO: openpyxl).

Una FILA por regla en la hoja «Reglas» (columnas fijas con listas desplegables);
«Referencias», «Notas» y «Documento» guardan el resto de lo que venía en las
tablas de los ingenieros, y las columnas de TRAZABILIDAD (texto original,
encabezado, condición y hoja de origen) permiten volver a la fuente: nada se
pierde al pasar del Excel libre a la plantilla.

Los encabezados y las listas van en español fijo: es un formato de datos (el
importador lee por nombre de columna, en cualquier orden).

`importar(ruta)` acepta el formato SIMPLE (`normativas_simple`, el oficial desde
2026-10-06: es el que exporta la app), esta plantilla y también el Excel de «clearance tables»
original (lo convierte `normativas_clearance`).
"""
from __future__ import annotations

import datetime
import re
import unicodedata

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from nucleo import normativas as N
from nucleo import normativas_clearance as CL
from nucleo import normativas_simple as SIMPLE

TIPO_ETIQUETA = {
    "separacion_horizontal": "Separación horizontal",
    "separacion_vertical": "Separación vertical",
    "recubrimiento": "Recubrimiento",
    "requisito": "Requisito (texto)",
    "angulos_accesorio": "Ángulo de accesorio",
}
CONTRA_ETIQUETA = {k: v for k, v in N.CONTRAS.items()}          # textos en español (N_ = la clave)
ACCESORIO_ETIQUETA = {"codo": "Codo", "tee": "Tee", "wye": "Wye", "cruz": "Cruz"}
MEDIDO = sorted({n for _p, n in CL.MEDIDO_DE} | set(CL.MEDIDO_DEFECTO.values())
                | {"Desvío sobre el eje prolongado", "Ángulo del ramal contra el tronco"})
SI_NO = ("Sí", "No")
ESTADOS = ("OK", "Revisar")

# (clave, encabezado, ancho, ayuda)
COLUMNAS = [
    ("id", "ID", 12, "Código único de la regla. Si lo dejas vacío, la app pone uno."),
    ("activa", "Activa", 8, "Sí/No: si la regla viene encendida en los proyectos nuevos."),
    ("obligatoria", "Obligatoria", 12, "Sí = obligatoria (aviso rojo); No = recomendada (aviso ámbar)."),
    ("tipo", "Tipo", 22, "Qué se exige: separación horizontal o vertical, recubrimiento, ángulo de accesorio o un requisito de texto."),
    ("utilidad", "Utilidad", 22, "A qué utilidad se aplica. Varias: sepáralas con «;»."),
    ("condicion", "Condición de la utilidad", 30, "Solo si la regla depende de la presión, el diámetro o el material (texto libre)."),
    ("contra", "Contra (utilidad u objeto)", 24, "Contra qué se mide: otra utilidad, vía férrea, bordillo, buzón, superficie… En ángulos: Codo, Tee, Wye o Cruz."),
    ("condicion_contra", "Condición del contra", 28, "Igual que la condición, pero de lo que está del otro lado (texto libre)."),
    ("minimo", "Mínimo (ft)", 11, "En PIES (18 pulgadas = 1.5). Vacío si no hay mínimo."),
    ("maximo", "Máximo (ft)", 11, "En PIES. Vacío si no hay máximo. Para un valor exacto, pon el mismo en mínimo y máximo."),
    ("angulos", "Ángulos permitidos (°)", 22, "Solo en «Ángulo de accesorio»: lista separada por «;», p. ej. 11.25; 22.5; 45; 90."),
    ("tolerancia", "Tolerancia (°)", 12, "Solo en «Ángulo de accesorio»: cuánto puede apartarse (1 si se deja vacío)."),
    ("medido", "Medido desde", 32, "Desde dónde hasta dónde se mide (elige de la lista o escribe)."),
    ("refs", "Referencias", 18, "IDs de la hoja «Referencias», separados por «;» (de qué libro o norma sale)."),
    ("notas", "Notas", 14, "IDs de la hoja «Notas» que matizan la regla, separados por «;»."),
    ("descripcion", "Descripción / comentario", 40, "Texto libre para el ingeniero."),
    ("estado", "Estado", 10, "OK o Revisar (la conversión automática marca «Revisar» lo que no entendió del todo)."),
    ("texto_original", "Texto original", 50, "TRAZABILIDAD: el texto tal como estaba en la tabla de origen."),
    ("encabezado_original", "Encabezado original", 30, "TRAZABILIDAD: encabezado de la columna de origen."),
    ("condicion_original", "Condición original", 30, "TRAZABILIDAD: rótulo de la fila de origen (tipo de tubería, tamaño…)."),
    ("hoja", "Hoja de origen", 18, "TRAZABILIDAD: hoja del Excel de origen."),
]
TRAZABILIDAD = {"texto_original", "encabezado_original", "condicion_original", "hoja"}

_AZUL = PatternFill("solid", fgColor="1F4E79")
_GRIS = PatternFill("solid", fgColor="7F7F7F")
_AMBAR = PatternFill("solid", fgColor="FFF2CC")
_BLANCO = Font(color="FFFFFF", bold=True)
_BORDE = Border(bottom=Side(style="thin", color="BFBFBF"))


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


def _lista(s):
    return [x.strip() for x in re.split(r"[;,\n]", str(s or "")) if x.strip()]


def _num(v):
    if v in (None, ""):
        return None
    return float(str(v).replace(",", "."))


# ─────────────────────────────── exportar ───────────────────────────────


def _fila_de(regla):
    p = regla.get("params") or {}
    tipo = regla.get("tipo")
    utils = "; ".join(CONTRA_ETIQUETA.get(u, u) for u in regla.get("utilidades") or [])
    if tipo == "angulos_accesorio":
        contra = ACCESORIO_ETIQUETA.get(p.get("accesorio"), p.get("accesorio", ""))
        angulos = "; ".join(f"{a:g}" for a in p.get("angulos") or [])
        tol = p.get("tolerancia")
        medido = "Desvío sobre el eje prolongado" if p.get("accesorio") == "codo" else "Ángulo del ramal contra el tronco"
    else:
        contra = CONTRA_ETIQUETA.get(p.get("contra"), p.get("contra", ""))
        angulos, tol, medido = "", None, p.get("medido_desde", "")
    return {
        "id": regla["id"], "activa": "Sí" if regla.get("activa", True) else "No",
        "obligatoria": "Sí" if regla.get("obligatoria", True) else "No",
        "tipo": TIPO_ETIQUETA.get(tipo, tipo), "utilidad": utils,
        "condicion": p.get("condicion", ""), "contra": contra, "condicion_contra": p.get("condicion_contra", ""),
        "minimo": p.get("minimo"), "maximo": p.get("maximo"), "angulos": angulos, "tolerancia": tol,
        "medido": medido, "refs": "; ".join(p.get("referencias") or []), "notas": "; ".join(p.get("notas") or []),
        "descripcion": regla.get("descripcion") or p.get("descripcion", ""),
        "estado": p.get("estado", "OK"), "texto_original": p.get("texto_original", ""),
        "encabezado_original": p.get("encabezado_original", ""),
        "condicion_original": p.get("condicion_original", ""), "hoja": p.get("hoja", ""),
    }


def _cabecera(ws, titulos, anchos, relleno=_AZUL):
    for c, (t, w) in enumerate(zip(titulos, anchos), 1):
        cel = ws.cell(row=1, column=c, value=t)
        cel.font = _BLANCO; cel.fill = relleno
        cel.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32


def exportar(reglas, anexos, ruta, version_app=""):
    """Escribe la plantilla con TODAS las reglas actuales (cambiadas o no)."""
    wb = openpyxl.Workbook()
    _hoja_instrucciones(wb.active)
    ws = wb.create_sheet("Reglas")
    _cabecera(ws, [h for _k, h, _w, _a in COLUMNAS], [w for _k, _h, w, _a in COLUMNAS])
    for c, (k, _h, _w, ayuda) in enumerate(COLUMNAS, 1):
        if k in TRAZABILIDAD:
            ws.cell(row=1, column=c).fill = _GRIS
    for f, regla in enumerate(reglas, 2):
        datos = _fila_de(regla)
        for c, (k, _h, _w, _a) in enumerate(COLUMNAS, 1):
            cel = ws.cell(row=f, column=c, value=datos.get(k))
            cel.alignment = Alignment(wrap_text=k in ("texto_original", "descripcion"), vertical="top")
            cel.border = _BORDE
            if k == "estado" and datos.get(k) == "Revisar":
                cel.fill = _AMBAR
    ultima = max(len(reglas) + 1, 2) + 500                      # filas libres para agregar reglas
    ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(COLUMNAS))}{len(reglas) + 1}"
    _listas(wb, ws, ultima)

    wr = wb.create_sheet("Referencias")
    _cabecera(wr, ["ID", "Texto (libro, norma, correo…)", "Aparece en"], [10, 90, 50])
    for f, (rid, ref) in enumerate(sorted((anexos.get("referencias") or {}).items()), 2):
        ref = ref if isinstance(ref, dict) else {"texto": ref, "origen": ""}
        for c, v in enumerate((rid, ref.get("texto", ""), ref.get("origen", "")), 1):
            wr.cell(row=f, column=c, value=v).alignment = Alignment(wrap_text=True, vertical="top")

    wn = wb.create_sheet("Notas")
    _cabecera(wn, ["ID", "Hoja de origen", "Aplica a", "Texto"], [10, 18, 16, 110])
    for f, n in enumerate(anexos.get("notas") or [], 2):
        for c, v in enumerate((n.get("id"), n.get("hoja"), n.get("aplica"), n.get("texto")), 1):
            wn.cell(row=f, column=c, value=v).alignment = Alignment(wrap_text=True, vertical="top")

    wd = wb.create_sheet("Documento")
    _cabecera(wd, ["Dato", "Valor"], [26, 100])
    doc = anexos.get("documento") or {}
    filas = [("Archivo de origen", doc.get("archivo", "")),
             ("Exportado", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
             ("Versión de la app", version_app)]
    filas += [(f"Título · {x.get('hoja', '')}", x.get("texto", "")) for x in doc.get("titulos") or []]
    filas += [(f"Tabla · {x.get('hoja', '')}", x.get("texto", "")) for x in doc.get("tablas") or []]
    for f, (k, v) in enumerate(filas, 2):
        wd.cell(row=f, column=1, value=k); wd.cell(row=f, column=2, value=v)
    wb.move_sheet("Listas", offset=len(wb.sheetnames))
    wb.active = 1
    wb.save(ruta)


def _listas(wb, ws, ultima):
    wl = wb.create_sheet("Listas")
    listas = [("Tipo", list(TIPO_ETIQUETA.values())),
              ("Utilidad", [CONTRA_ETIQUETA[k] for k in ("AGUA", "ALCANTARILLADO", "DRENAJE", "GAS", "ELECTRICO", "TELECOM")]),
              ("Contra", list(CONTRA_ETIQUETA.values()) + list(ACCESORIO_ETIQUETA.values())),
              ("Medido desde", MEDIDO), ("Sí/No", list(SI_NO)), ("Estado", list(ESTADOS))]
    _cabecera(wl, [n for n, _ in listas], [24, 22, 26, 40, 8, 10])
    for c, (_n, vals) in enumerate(listas, 1):
        for f, v in enumerate(vals, 2):
            wl.cell(row=f, column=c, value=v)
    col = {k: openpyxl.utils.get_column_letter(i) for i, (k, *_r) in enumerate(COLUMNAS, 1)}

    def _dv(lista_col, n, claves, estricto):
        letra = openpyxl.utils.get_column_letter(lista_col)
        dv = DataValidation(type="list", formula1=f"=Listas!${letra}$2:${letra}${n + 1}",
                            allow_blank=True, showErrorMessage=True,
                            errorStyle="stop" if estricto else "warning",
                            error="Elige un valor de la lista." if estricto else
                            "No está en la lista: la app lo guardará como texto y lo marcará para revisar.")
        for k in claves:
            dv.add(f"{col[k]}2:{col[k]}{ultima}")
        ws.add_data_validation(dv)

    _dv(1, len(listas[0][1]), ["tipo"], True)
    _dv(2, len(listas[1][1]), ["utilidad"], False)          # admite «Agua; Gas»
    _dv(3, len(listas[2][1]), ["contra"], False)
    _dv(4, len(listas[3][1]), ["medido"], False)
    _dv(5, 2, ["activa", "obligatoria"], True)
    _dv(6, 2, ["estado"], True)
    num = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                         showErrorMessage=True, error="Escribe un número en pies (0 o más).")
    for k in ("minimo", "maximo", "tolerancia"):
        num.add(f"{col[k]}2:{col[k]}{ultima}")
    ws.add_data_validation(num)


def _hoja_instrucciones(ws):
    ws.title = "Instrucciones"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 110
    lineas = [
        ("NORMATIVAS DE DISEÑO — PLANTILLA", None),
        ("", None),
        ("Cómo se llena", "Una FILA por regla en la hoja «Reglas». Usa las listas desplegables; las distancias "
                          "van en PIES (18 pulgadas = 1.5). Para importarla: en la app, Normativas → Importar Excel."),
        ("Ejemplo", "Eléctrico a 5 ft de Agua en horizontal → Tipo: Separación horizontal · Utilidad: Eléctrico · "
                    "Contra: Agua · Mínimo (ft): 5 · Referencias: REF-01."),
        ("Varias utilidades", "Escríbelas separadas por «;» (Agua; Gas)."),
        ("Referencias y notas", "La fuente (libro, norma, correo) va en «Referencias» con un ID (REF-01…); las "
                                "aclaraciones van en «Notas» (NOTA-01…). En cada regla se citan por su ID."),
        ("Columnas grises", "TRAZABILIDAD: el texto tal como venía en la tabla de origen. No hace falta llenarlas "
                            "en reglas nuevas; sirven para revisar de dónde salió cada regla."),
        ("Estado «Revisar»", "La conversión automática marca así lo que no entendió del todo (condiciones, "
                             "excepciones): revisa el texto original y corrige la fila."),
        ("", None),
        ("Columnas de «Reglas»", None),
    ] + [(h, a) for _k, h, _w, a in COLUMNAS]
    for f, (a, b) in enumerate(lineas, 1):
        ws.cell(row=f, column=1, value=a).font = Font(bold=True, size=14 if f == 1 else 11)
        if b:
            ws.cell(row=f, column=2, value=b).alignment = Alignment(wrap_text=True, vertical="top")


# ─────────────────────────────── importar ───────────────────────────────


def _mapa(etiquetas):
    return {_norm(v): k for k, v in etiquetas.items()} | {_norm(k): k for k in etiquetas}


_TIPOS = _mapa(TIPO_ETIQUETA)
_CONTRAS = _mapa(CONTRA_ETIQUETA)
_ACCES = _mapa(ACCESORIO_ETIQUETA)


def _anexos_de(wb):
    anexos = {"referencias": {}, "notas": [], "documento": {}}
    if "Referencias" in wb.sheetnames:
        for fila in wb["Referencias"].iter_rows(min_row=2, values_only=True):
            if fila and fila[0]:
                anexos["referencias"][str(fila[0]).strip()] = {
                    "texto": str(fila[1] or ""), "origen": str(fila[2] or "") if len(fila) > 2 else ""}
    if "Notas" in wb.sheetnames:
        for fila in wb["Notas"].iter_rows(min_row=2, values_only=True):
            if fila and fila[0]:
                anexos["notas"].append({"id": str(fila[0]).strip(), "hoja": str(fila[1] or ""),
                                        "aplica": str(fila[2] or ""), "texto": str(fila[3] or "")})
    if "Documento" in wb.sheetnames:
        titulos, tablas, doc = [], [], {}
        for fila in wb["Documento"].iter_rows(min_row=2, values_only=True):
            if not fila or not fila[0]:
                continue
            k, v = str(fila[0]), "" if fila[1] is None else str(fila[1])
            if k.startswith("Título · "):
                titulos.append({"hoja": k[len("Título · "):], "texto": v})
            elif k.startswith("Tabla · "):
                tablas.append({"hoja": k[len("Tabla · "):], "texto": v})
            elif k == "Archivo de origen":
                doc["archivo"] = v
        doc["titulos"] = titulos
        doc["tablas"] = tablas
        anexos["documento"] = doc
    return anexos


def importar(ruta):
    """(reglas, anexos, errores, formato). `errores` = [(fila, texto)]; las filas
    con error no se importan. `formato` = "simple" | "plantilla" | "clearance"."""
    wb = openpyxl.load_workbook(ruta, data_only=True)
    if "Reglas" not in wb.sheetnames and SIMPLE.es_formato_simple(wb):
        reglas, anexos, errores = SIMPLE.importar(wb, archivo=ruta.replace("\\", "/").rsplit("/", 1)[-1])
        return reglas, anexos, errores, "simple"
    if "Reglas" not in wb.sheetnames and CL.es_formato_clearance(wb):
        reglas, anexos = CL.convertir(wb, archivo=ruta.replace("\\", "/").rsplit("/", 1)[-1])
        return reglas, anexos, [], "clearance"
    if "Reglas" not in wb.sheetnames:
        return [], {}, [(0, "El archivo no tiene la hoja «Reglas» ni tablas de «clearance»: no es una plantilla de normativas.")], ""
    ws = wb["Reglas"]
    cab = [_norm(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]
    pos = {}
    for k, h, _w, _a in COLUMNAS:
        if _norm(h) in cab:
            pos[k] = cab.index(_norm(h))
    if "tipo" not in pos or "utilidad" not in pos:
        return [], {}, [(1, "Faltan las columnas «Tipo» y «Utilidad» en la hoja «Reglas».")], ""
    anexos = _anexos_de(wb)
    reglas, errores, ids = [], [], set()
    for f, fila in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        v = {k: (fila[i] if i < len(fila) else None) for k, i in pos.items()}
        if all(x in (None, "") for x in v.values()):
            continue
        regla, err = _regla_de_fila(v, f, ids, anexos)
        if err:
            errores.append((f, err))
            continue
        ids.add(regla["id"])
        reglas.append(regla)
    return reglas, anexos, errores, "plantilla"


def _si(v, defecto=True):
    if v in (None, ""):
        return defecto
    return _norm(v) in ("SI", "S", "YES", "Y", "TRUE", "1", "X")


def _regla_de_fila(v, f, ids, anexos):
    tipo = _TIPOS.get(_norm(v.get("tipo")))
    if not tipo:
        return None, f"Tipo no válido: «{v.get('tipo') or ''}»."
    utils = []
    for u in _lista(v.get("utilidad")):
        cod = _CONTRAS.get(_norm(u))
        if cod not in ("AGUA", "ALCANTARILLADO", "DRENAJE", "GAS", "ELECTRICO", "TELECOM"):
            return None, f"Utilidad no válida: «{u}»."
        utils.append(cod)
    if not utils:
        return None, "Falta la utilidad."
    rid = str(v.get("id") or "").strip()
    if not rid:
        rid = f"{CL.ABREV.get(utils[0], 'X')}-{f:03d}"
    if rid in ids:
        return None, f"El ID «{rid}» está repetido."
    try:
        mn, mx = _num(v.get("minimo")), _num(v.get("maximo"))
        tol = _num(v.get("tolerancia"))
    except ValueError:
        return None, "Mínimo, máximo o tolerancia no es un número."
    if (mn is not None and mn < 0) or (mx is not None and mx < 0):
        return None, "Las distancias no pueden ser negativas."
    if mn is not None and mx is not None and mx < mn:
        return None, "El máximo es menor que el mínimo."
    refs, notas = _lista(v.get("refs")), _lista(v.get("notas"))
    estado = "Revisar" if _norm(v.get("estado")) == "REVISAR" else "OK"
    faltan = [r for r in refs if r not in anexos["referencias"]]
    if faltan:
        estado = "Revisar"
    base = {"id": rid, "tipo": tipo, "utilidades": utils, "activa": _si(v.get("activa")),
            "obligatoria": _si(v.get("obligatoria"))}
    if tipo == "angulos_accesorio":
        acc_ = _ACCES.get(_norm(v.get("contra")))
        if not acc_:
            return None, "En «Ángulo de accesorio», Contra debe ser Codo, Tee, Wye o Cruz."
        try:
            angulos = sorted({round(float(a.replace(",", ".")), 4) for a in _lista(str(v.get("angulos") or "").replace(";", "\n"))})
        except ValueError:
            return None, "Ángulos permitidos: escribe números separados por «;»."
        if not angulos or any(not (0 < a <= 180) for a in angulos):
            return None, "Ángulos permitidos: al menos uno, entre 0 y 180."
        base["params"] = {"accesorio": acc_, "angulos": angulos, "tolerancia": 1.0 if tol is None else tol,
                          "descripcion": str(v.get("descripcion") or "")}
        return base, None
    if tipo != "requisito" and mn is None and mx is None:
        return None, "Falta el mínimo o el máximo (en pies)."
    contra_txt = str(v.get("contra") or "").strip()
    contra = _CONTRAS.get(_norm(contra_txt), contra_txt)
    if contra_txt and contra == contra_txt:
        estado = "Revisar"                           # contra que la app no conoce: se guarda tal cual
    base["params"] = {
        "contra": contra, "condicion": str(v.get("condicion") or ""),
        "condicion_contra": str(v.get("condicion_contra") or ""), "minimo": mn, "maximo": mx,
        "medido_desde": str(v.get("medido") or ""), "referencias": refs, "notas": notas,
        "descripcion": str(v.get("descripcion") or ""), "estado": estado,
        "texto_original": str(v.get("texto_original") or ""),
        "encabezado_original": str(v.get("encabezado_original") or ""),
        "condicion_original": str(v.get("condicion_original") or ""), "hoja": str(v.get("hoja") or ""),
    }
    return base, None
