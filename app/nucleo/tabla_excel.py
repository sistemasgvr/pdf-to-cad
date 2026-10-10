"""Excel de la Tabla de datos, de IDA Y VUELTA (PURO: sin Qt).

`exportar` escribe una hoja por tabla (utilidades, buzones, curvas, bancoductos, avisos,
conflictos) más «Cotas por vértice» y una hoja «Léeme». Las columnas EDITABLES van en
verde; las grises son de consulta. `importar` lee el libro (encabezados en español o en
inglés), `cambios` compara con el proyecto (con la tolerancia del redondeo del Excel:
un valor que no se tocó no cuenta como cambio) y `aplicar` los pone en el modelo. La
ventana muestra los cambios antes de aplicarlos y se pueden deshacer.

Editables: utilidades (nombre, tipo, amperaje, rasante inicial y final), buzones y cajas
(tapa, fondo), curvas (radio; «Automático» = el radio por defecto) y cotas por vértice
(llegada y salida; vacío = automática, interpolada). Los conflictos se recalculan solos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from nucleo import model_ops
from nucleo.tabla_datos import Tabla, _r
from traduccion.i18n_core import N_, TRANSLATIONS, t

EDITABLES = {
    "utilidades": {N_("Nombre"): ("name", "texto", 0), N_("Tipo"): ("tipo", "texto", 0),
                   N_("Amperaje (A)"): ("amperaje", "num", 0.06),
                   N_("Rasante inicial (ft)"): ("inv_start", "num", 0.0006),
                   N_("Rasante final (ft)"): ("inv_end", "num", 0.0006)},
    "buzones": {N_("Tapa (ft)"): ("rim", "num", 0.0006), N_("Fondo (ft)"): ("sump", "num", 0.0006)},
    "curvas": {N_("Radio (ft)"): ("radius_ft", "radio", 0.006)},
    "vertices": {N_("Cota de llegada (ft)"): ("in", "num", 0.0006),
                 N_("Cota de salida (ft)"): ("out", "num", 0.0006)},
}
TITULO_VERTICES = N_("Cotas por vértice")
VERDE, VERDE_CLARO, GRIS = "C6EFCE", "EBF7EE", "D9D9D9"


@dataclass
class Cambio:
    objeto: str            # "pipe" | "struct" | "vertice"
    indice: int            # utilidad o estructura
    campo: str             # clave del modelo
    antes: object
    despues: object
    etiqueta: str          # «Utilidad #3 · Rasante inicial (ft)»
    vertice: int = -1


# ─────────────────────────── exportar ───────────────────────────

def tabla_vertices(pipes, a_cad):
    """Cotas por vértice INTERIOR de cada utilidad (las puntas son la rasante inicial/final)."""
    tb = Tabla("vertices", TITULO_VERTICES, [
        N_("Utilidad N°"), N_("Nombre"), N_("Vértice"), N_("Cota de llegada (ft)"), N_("Cota de salida (ft)"),
        N_("Automática (ft)"), N_("X"), N_("Y")])
    for i, p in enumerate(pipes or []):
        pts = p.get("pts") or []
        if p.get("world") or len(pts) < 3:
            continue
        z0 = float(p.get("inv_start") or 0.0); z1 = float(p.get("inv_end") or z0)
        auto = model_ops.interp_vertex_z(pts, z0, z1, {})
        v_in = {int(k): v for k, v in (p.get("vertex_inv_in") or {}).items()}
        v_out = {int(k): v for k, v in (p.get("vertex_inv_out") or {}).items()}
        nombre = (p.get("name") or "").strip() or model_ops.nombre_por_defecto(p, i)
        for v in range(1, len(pts) - 1):
            x, y = a_cad(*pts[v])
            tb.filas.append([i + 1, nombre, v, _r(v_in.get(v), 3), _r(v_out.get(v), 3), _r(auto[v], 3),
                             _r(x, 3), _r(y, 3)])
            tb.lugares.append((pts[v][0], pts[v][1], "pipe", i))
    return tb


def exportar(tablas, ruta):
    """Un libro con una hoja por tabla; las columnas editables en verde."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ley = wb.active
    ley.title = t("Léeme")[:31]
    for fila in (
            [t("Cómo editar este Excel y volver a cargarlo")],
            [t("1. Cambia solo las columnas VERDES (cotas, tapas y fondos, radios, nombre, tipo, amperaje).")],
            [t("2. Las columnas grises son de consulta: no se importan.")],
            [t("3. En la app: Herramientas → Tabla de datos → «Importar Excel…». Verás los cambios antes de "
               "aplicarlos y se pueden deshacer con Ctrl+Z.")],
            [t("4. En «Cotas por vértice», una celda vacía = cota automática (interpolada).")],
            [t("5. Los conflictos (hoja «Conflictos», C-1, C-2…) se recalculan al importar.")]):
        ley.append(fila)
    ley["A1"].font = Font(bold=True, size=13)
    ley.column_dimensions["A"].width = 110
    for tb in tablas:
        ws = wb.create_sheet(t(tb.titulo)[:31])
        editables = EDITABLES.get(tb.clave, {})
        ws.append([t(c) for c in tb.columnas])
        for f in tb.filas:
            ws.append(list(f))
        for k, c in enumerate(tb.columnas, 1):
            cab = ws.cell(row=1, column=k)
            cab.font = Font(bold=True)
            cab.alignment = Alignment(wrap_text=True, vertical="center")
            editable = c in editables
            cab.fill = PatternFill("solid", fgColor=VERDE if editable else GRIS)
            if editable:
                for r in range(2, len(tb.filas) + 2):
                    ws.cell(row=r, column=k).fill = PatternFill("solid", fgColor=VERDE_CLARO)
            largo = max([len(str(t(c)))] + [len(str(f[k - 1])) for f in tb.filas if f[k - 1] is not None])
            ws.column_dimensions[openpyxl.utils.get_column_letter(k)].width = min(60, max(9, largo + 2))
        ws.freeze_panes = "A2"
        if tb.filas:
            ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(tb.columnas))}{len(tb.filas) + 1}"
    wb.save(ruta)


# ─────────────────────────── importar ───────────────────────────

def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _en_dos_idiomas(clave):
    en = TRANSLATIONS.get("en", {}).get(clave, clave)
    return {_norm(clave), _norm(en)}


def importar(ruta):
    """{clave de tabla: [ {columna (clave en español): valor} ]} de las hojas reconocidas."""
    import openpyxl
    from nucleo import tabla_datos
    wb = openpyxl.load_workbook(ruta, data_only=True, read_only=True)
    titulos = {"utilidades": N_("Utilidades"), "buzones": N_("Buzones y cajas"), "curvas": N_("Curvas"),
               "vertices": TITULO_VERTICES}
    columnas = {tb.clave: tb.columnas for tb in tabla_datos.armar([], [], [], [], lambda x, y: (x, y), 1.0)}
    columnas["vertices"] = tabla_vertices([], lambda x, y: (x, y)).columnas
    hojas = {_norm(n): n for n in wb.sheetnames}
    leido = {}
    for clave, titulo in titulos.items():
        nombre = next((hojas[n] for n in _en_dos_idiomas(titulo) if n in hojas), None)
        if nombre is None:
            continue
        filas = list(wb[nombre].iter_rows(values_only=True))
        if not filas:
            continue
        mapa = {}
        for k, cab in enumerate(filas[0]):
            for col in columnas[clave]:
                if _norm(cab) in _en_dos_idiomas(col):
                    mapa[k] = col
        leido[clave] = [{mapa[k]: v for k, v in enumerate(f) if k in mapa} for f in filas[1:]
                        if any(v not in (None, "") for v in f)]
    wb.close()
    return leido


def _num(v):
    """Número de una celda (acepta «-4,25»), None si vacía; ValueError si no es número."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).strip().replace(",", "."))


def _distinto(a, b, tol):
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(float(a) - float(b)) > tol


def cambios(pipes, structures, leido):
    """([Cambio], [errores]) entre el Excel leído y el proyecto."""
    out, errores = [], []

    def valor(tipo, v, etiqueta):
        try:
            return _num(v) if tipo in ("num",) else v
        except ValueError:
            errores.append(t("{donde}: «{v}» no es un número.").format(donde=etiqueta, v=v))
            raise

    for fila in leido.get("utilidades", []):
        try:
            i = int(fila.get(N_("N°"))) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(pipes)):
            errores.append(t("Utilidad #{n}: no existe en el proyecto.").format(n=i + 1))
            continue
        p = pipes[i]
        for col, (campo, tipo, tol) in EDITABLES["utilidades"].items():
            if col not in fila:
                continue
            etq = t("Utilidad #{n} · {campo}").format(n=i + 1, campo=t(col))
            try:
                nuevo = valor(tipo, fila[col], etq)
            except ValueError:
                continue
            viejo = p.get(campo)
            if tipo == "texto":
                nuevo = "" if nuevo is None else str(nuevo).strip()
                viejo = "" if viejo is None else str(viejo)
                if campo == "name" and nuevo == model_ops.nombre_por_defecto(p, i) and not viejo:
                    continue                             # el nombre por defecto no es un nombre propio
                if nuevo != viejo:
                    out.append(Cambio("pipe", i, campo, viejo, nuevo, etq))
            elif _distinto(viejo, nuevo, tol):
                out.append(Cambio("pipe", i, campo, viejo, nuevo, etq))

    por_cod = {s.get("cod"): n for n, s in enumerate(structures or []) if s.get("cod")}
    for clave in ("buzones", "curvas"):
        for fila in leido.get(clave, []):
            cod = fila.get(N_("Código"))
            if cod in (None, ""):
                continue
            n = por_cod.get(str(cod))
            if n is None:
                errores.append(t("«{cod}»: no existe en el proyecto.").format(cod=cod))
                continue
            s = structures[n]
            for col, (campo, tipo, tol) in EDITABLES[clave].items():
                if col not in fila:
                    continue
                etq = f"{cod} · {t(col)}"
                v = fila[col]
                if tipo == "radio":
                    try:
                        nuevo = _num(v)
                    except ValueError:
                        nuevo = 0.0                      # «Automático (…)»: el radio por defecto
                    nuevo = 0.0 if nuevo is None else nuevo
                    viejo = float(s.get("radius_ft") or 0.0)
                else:
                    try:
                        nuevo = valor(tipo, v, etq)
                    except ValueError:
                        continue
                    viejo = s.get(campo)
                if _distinto(viejo, nuevo, tol):
                    out.append(Cambio("struct", n, campo, viejo, nuevo, etq))

    for fila in leido.get("vertices", []):
        try:
            i = int(fila.get(N_("Utilidad N°"))) - 1
            v = int(fila.get(N_("Vértice")))
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(pipes)) or not (0 < v < len(pipes[i].get("pts") or []) - 1):
            errores.append(t("Utilidad #{n}, vértice {v}: no existe.").format(n=i + 1, v=v))
            continue
        p = pipes[i]
        for col, (lado, tipo, tol) in EDITABLES["vertices"].items():
            if col not in fila:
                continue
            etq = t("Utilidad #{n} · vértice {v} · {campo}").format(n=i + 1, v=v, campo=t(col))
            try:
                nuevo = valor(tipo, fila[col], etq)
            except ValueError:
                continue
            dic = {int(k): x for k, x in (p.get("vertex_inv_" + lado) or {}).items()}
            if _distinto(dic.get(v), nuevo, tol):
                out.append(Cambio("vertice", i, "vertex_inv_" + lado, dic.get(v), nuevo, etq, v))
    return out, errores


def aplicar(pipes, structures, lista):
    """Pone los cambios en el modelo (en sitio)."""
    for c in lista:
        if c.objeto == "pipe":
            pipes[c.indice][c.campo] = c.despues
        elif c.objeto == "struct":
            structures[c.indice][c.campo] = c.despues
        elif c.objeto == "vertice":
            p = pipes[c.indice]
            dic = {int(k): x for k, x in (p.get(c.campo) or {}).items()}
            if c.despues is None:
                dic.pop(c.vertice, None)
            else:
                dic[c.vertice] = float(c.despues)
            p[c.campo] = dic


def texto(c):
    """«Utilidad #3 · Rasante inicial (ft): -4 → -5» (para la confirmación)."""
    def f(v):
        if v is None or v == "":
            return t("(vacío)")
        return f"{v:g}" if isinstance(v, float) else str(v)
    return f"{c.etiqueta}: {f(c.antes)} → {f(c.despues)}"
