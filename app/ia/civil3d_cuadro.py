"""Cuadro de datos del dibujo de Civil 3D en Excel o Word (herramienta `exportar_cuadro` del chat «Civil 3D»).

Todo sale del plugin (`datos_red`, `metrados`, `buscar_conflictos` con las separaciones de la app) y de la revisión
con las normativas de la app (`civil3d_normativas`). Se guarda junto al DWG (si está guardado) o en Documentos, con
fecha y hora en el nombre: nunca se pisa un archivo. Puro salvo escribir el archivo (openpyxl / python-docx).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from traduccion.i18n_core import t

WORD_FILAS_MAX = 1500            # por tabla en Word (el Excel lleva todo)


def _ok(cliente, nombre, args=None):
    ok, salida = cliente.llamar(nombre, args or {})
    if not ok:
        raise ValueError(salida)
    return json.loads(salida)


def tablas(cliente, normas_cat=None, reglas=None):
    """{título: (columnas, filas)} con todo lo del cuadro."""
    datos = _ok(cliente, "datos_red")
    met = _ok(cliente, "metrados")
    out = {}

    def poner(titulo, t_):
        if t_ and t_.get("columnas"):
            out[titulo] = (list(t_["columnas"]), [list(f) for f in t_.get("filas") or []])

    poner(t("Tuberías"), datos.get("tuberias"))
    poner(t("Estructuras"), datos.get("estructuras"))
    poner(t("Accesorios"), datos.get("accesorios"))
    poner(t("Metrados de tubería"), met.get("tuberias"))
    poner(t("Metrados de accesorios"), met.get("accesorios"))
    poner(t("Metrados de estructuras"), met.get("estructuras"))
    try:
        conf = _ok(cliente, "buscar_conflictos", {"reglas": reglas or [], "limite": 200})
        poner(t("Conflictos"), conf.get("conflictos"))
    except ValueError:
        pass
    if (normas_cat or {}).get("reglas"):
        from ia import civil3d_normativas as CN
        filas, _, _ = CN.filas(datos, normas_cat)
        cols = ["nivel", "clase", "utilidad", "tuberia", "mensaje", "fuente"]
        out[t("Normativa")] = (cols, [[f[c] for c in cols] for f in filas])
    return out


def ruta_para(dibujo, extension, ahora=None):
    """Junto al DWG (si es una ruta que existe) o en Documentos; nombre con fecha y hora."""
    ahora = ahora or _dt.datetime.now()
    carpeta = os.path.dirname(dibujo or "")
    if not carpeta or not os.path.isdir(carpeta):
        carpeta = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(carpeta, exist_ok=True)
    base = os.path.splitext(os.path.basename(dibujo or ""))[0] or "Civil3D"
    return os.path.join(carpeta, f"{base}_cuadro_{ahora:%Y%m%d_%H%M%S}.{extension}")


def escribir_excel(tbls, ruta):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    for titulo, (cols, filas) in tbls.items():
        ws = wb.create_sheet(titulo[:31])
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
        for f in filas:
            ws.append([x if isinstance(x, (int, float, str)) or x is None else str(x) for x in f])
        ws.freeze_panes = "A2"
        for k, col in enumerate(ws.columns, 1):
            ancho = max((len(str(c.value)) for c in list(col)[:200] if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 8), 60)
    wb.save(ruta)


def escribir_word(tbls, ruta, titulo):
    from docx import Document
    doc = Document()
    doc.add_heading(titulo, level=1)
    doc.add_paragraph(t("Generado desde el dibujo de Civil 3D el {f}.").format(f=f"{_dt.datetime.now():%Y-%m-%d %H:%M}"))
    for nombre, (cols, filas) in tbls.items():
        doc.add_heading(nombre, level=2)
        if not filas:
            doc.add_paragraph(t("Sin datos."))
            continue
        tabla = doc.add_table(rows=1, cols=len(cols))
        tabla.style = "Light Grid Accent 1"
        for k, c in enumerate(cols):
            tabla.rows[0].cells[k].text = str(c)
        for f in filas[:WORD_FILAS_MAX]:
            celdas = tabla.add_row().cells
            for k, x in enumerate(f[:len(cols)]):
                celdas[k].text = "" if x is None else str(x)
        if len(filas) > WORD_FILAS_MAX:
            doc.add_paragraph(t("… y {n} filas más (están en el Excel).").format(n=len(filas) - WORD_FILAS_MAX))
    doc.save(ruta)


def ejecutar(cliente, normas_cat, reglas, args):
    """(ok, texto JSON) como una herramienta del plugin."""
    formato = ((args or {}).get("formato") or "excel").strip().lower()
    formato = "word" if formato.startswith(("w", "doc")) else "excel"
    try:
        estado = _ok(cliente, "estado")
        tbls = tablas(cliente, normas_cat, reglas)
    except ValueError as e:
        return False, str(e)
    ruta = ruta_para(estado.get("dibujo") or "", "docx" if formato == "word" else "xlsx")
    try:
        if formato == "word":
            escribir_word(tbls, ruta, t("Cuadro de datos · {d}").format(d=os.path.basename(estado.get("dibujo") or "Civil 3D")))
        else:
            escribir_excel(tbls, ruta)
    except OSError as e:
        return False, t("No se pudo guardar el archivo: {e}").format(e=e)
    return True, json.dumps({"archivo": ruta, "formato": formato,
                             "contenido": {k: len(v[1]) for k, v in tbls.items()}}, ensure_ascii=False)


def herramienta():
    return {"type": "function", "function": {
        "name": "exportar_cuadro",
        "description": "Guarda un cuadro de datos del dibujo en Excel o Word: tuberías, estructuras, accesorios, metrados, "
                       "conflictos y avisos de normativa. Devuelve la ruta del archivo.",
        "parameters": {"type": "object", "properties": {
            "formato": {"type": "string", "enum": ["excel", "word"]}}}}}
