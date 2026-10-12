"""Tabla con toda la información de cada elemento del proyecto (PURO: sin Qt).

Herramientas → «Tabla de datos…» (pedido del usuario 2026-10-09): utilidades, buzones y
cajas, curvas, bancoductos y avisos de normativa, cada uno con sus columnas, y
`exportar_excel` las escribe en un libro (una hoja por tabla, como tabla de Excel).

`armar(...)` recibe lo que solo la ventana sabe como funciones: `a_cad(x, y)` (px del
lienzo → coordenadas del DXF en pies, con la georreferencia si la hay),
`nombre_utilidad(capa)` y `nombre_familia(id)` (textos que se muestran).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from nucleo import model_ops
from nucleo.model import network_kind
from traduccion.i18n_core import N_, t


@dataclass
class Tabla:
    clave: str
    titulo: str                                   # N_(…)
    columnas: list                                # N_(…)
    filas: list = field(default_factory=list)
    lugares: list = field(default_factory=list)   # por fila: (x_px, y_px, objeto, índice) o None


RED = {"gravity": N_("Gravedad"), "conduit": N_("Conducto"), "pressure": N_("Presión")}


def _r(v, dec=2):
    try:
        return None if v is None or v == "" else round(float(v), dec)
    except (TypeError, ValueError):
        return v


def _xy(a_cad, pt):
    x, y = a_cad(pt[0], pt[1])
    return _r(x, 3), _r(y, 3)


def _largo_px(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _estado_aviso(a):
    if getattr(a, "aprobado", None):
        return t("Aprobado")
    return t("Información") if a.info else t("Pendiente")


def _registro(a):
    r = getattr(a, "aprobado", None) or {}
    return r.get("usuario", ""), r.get("fecha", ""), r.get("nota", "")


def armar(pipes, structures, duct_banks, avisos, a_cad, ft_per_px,
          nombre_utilidad=lambda c: c, nombre_familia=lambda f: f, conflictos=()):
    pipes = pipes or []
    structures = structures or []
    db_de = {}
    for db in duct_banks or []:
        for i in db.assigned():
            db_de[i] = db.name or t("(sin nombre)")
    avisos_de = {}
    for a in avisos or []:
        if not a.info and not getattr(a, "aprobado", None):
            avisos_de[a.pipe] = avisos_de.get(a.pipe, 0) + 1

    ut = Tabla("utilidades", N_("Utilidades"), [
        N_("N°"), N_("Nombre"), N_("Utilidad"), N_("Tipo"), N_("Estado"), N_("Familia"), N_("Tamaño"),
        N_("Diámetro (in)"), N_("Material"), N_("Largo (ft)"), N_("Vértices"), N_("Curvas"), N_("Rasante inicial (ft)"),
        N_("Rasante final (ft)"), N_("Amperaje (A)"), N_("Bancoducto"), N_("Inicio X"), N_("Inicio Y"),
        N_("Fin X"), N_("Fin Y"), N_("Avisos")])
    curva_de = {}
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        if p.get("world") or len(pts) < 2:
            continue
        cv = model_ops.curve_vertex_indices(p, structures, pipes) if len(pts) >= 3 else {}
        for k, s in cv.items():
            curva_de[id(s)] = (i, k)
        d, defecto = model_ops.diametro(p)
        ix, iy = _xy(a_cad, pts[0])
        fx, fy = _xy(a_cad, pts[-1])
        ut.filas.append([
            i + 1, (p.get("name") or "").strip() or model_ops.nombre_por_defecto(p, i),
            nombre_utilidad(p.get("layer") or ""), p.get("tipo") or "",
            t("Abandonada") if p.get("ab") else t("Activa"),
            nombre_familia(p.get("pipe_family") or "") if p.get("pipe_family") else t("Por defecto"),
            p.get("pipe_size") or t("Por defecto"), _r(d, 3), p.get("material") or "", _r(_largo_px(pts) * (ft_per_px or 0)), len(pts),
            len(cv), _r(p.get("inv_start"), 3), _r(p.get("inv_end"), 3), _r(p.get("amperaje"), 1),
            db_de.get(i, ""), ix, iy, fx, fy, avisos_de.get(i, 0)])
        ut.lugares.append((pts[len(pts) // 2][0], pts[len(pts) // 2][1], "pipe", i))

    bz = Tabla("buzones", N_("Buzones y cajas"), [
        N_("Código"), N_("Clase"), N_("Red"), N_("X"), N_("Y"), N_("Tapa (ft)"), N_("Fondo (ft)"),
        N_("Familia"), N_("Tamaño"), N_("Visible"), N_("Forma"), N_("Largo (ft)"), N_("Ancho (ft)"),
        N_("Alto (ft)")])
    cu = Tabla("curvas", N_("Curvas"), [
        N_("Código"), N_("Utilidad"), N_("Vértice"), N_("Radio (ft)"), N_("Origen"), N_("X"), N_("Y")])
    for n, s in enumerate(structures):
        if s.get("world") or s.get("x") is None:
            continue
        x, y = _xy(a_cad, (s["x"], s["y"]))
        if s.get("curve"):
            i, k = curva_de.get(id(s), (None, None))
            r = float(s.get("radius_ft") or 0.0)
            radio = _r(r) if r > 0.01 else (t("Automático ({r} ft)").format(
                r=_r(model_ops.radio_auto_ft(pipes[i]))) if i is not None else t("Automático"))
            cu.filas.append([s.get("cod", ""), (i + 1) if i is not None else "", k if k is not None else "",
                             radio, t("Quiebre del plano") if s.get("quiebre") else t("Curva"), x, y])
            cu.lugares.append((s["x"], s["y"], "curve", n))
            continue
        clase = t("Sólido") if s.get("solid") else (t("Caja") if s.get("net") == "conduit" else t("Buzón"))
        red = RED.get(s.get("net") or "gravity", "")
        bz.filas.append([
            s.get("cod", ""), clase, t(red) if red else "", x, y, _r(s.get("rim"), 3), _r(s.get("sump"), 3),
            s.get("part") or "", s.get("part_size") or "", t("No") if s.get("hidden") else t("Sí"),
            s.get("shape") or "", _r(s.get("length_ft")), _r(s.get("width_ft")),
            _r(s.get("solid_height_ft")) if s.get("solid") else None])
        bz.lugares.append((s["x"], s["y"], "struct", n))

    bd = Tabla("bancoductos", N_("Bancoductos"), [
        N_("Nombre"), N_("Ancho (in)"), N_("Alto (in)"), N_("Conductos"), N_("Utilidades")])
    for db in duct_banks or []:
        bd.filas.append([db.name or t("(sin nombre)"), _r(db.width_in), _r(db.height_in), len(db.conduits),
                         ", ".join(f"#{i + 1}" for i in db.assigned())])
        bd.lugares.append(None)

    av = Tabla("avisos", N_("Avisos de normativa"), [
        N_("N°"), N_("Utilidad"), N_("Tipo de aviso"), N_("Mensaje"), N_("Estado"), N_("Aprobado por"),
        N_("Fecha de aprobación"), N_("Nota"), N_("X"), N_("Y")])
    from nucleo.normas_validar import CLASES
    for n, a in enumerate(avisos or [], 1):
        x, y = _xy(a_cad, (a.x, a.y))
        av.filas.append([n, (a.pipe + 1) if a.pipe is not None and a.pipe >= 0 else "",
                         t(CLASES.get(a.clase, a.clase)) + (" · " + t("Información") if a.info else ""),
                         a.mensaje, _estado_aviso(a), *_registro(a), x, y])
        av.lugares.append((a.x, a.y, "pipe", a.pipe))

    co = Tabla("conflictos", N_("Conflictos"), [
        N_("ID"), N_("Tipo de conflicto"), N_("Utilidades"), N_("Cota A (ft)"), N_("Cota B (ft)"),
        N_("Diferencia (ft)"), N_("Detalle"), N_("X"), N_("Y")])
    for c in conflictos or []:
        x, y = _xy(a_cad, (c.x, c.y))
        za = c.cotas[0] if len(c.cotas) > 0 else None
        zb = c.cotas[1] if len(c.cotas) > 1 else None
        co.filas.append([c.id, t(c.titulo), ", ".join(f"#{i + 1}" for i in c.pipes), _r(za, 3), _r(zb, 3),
                         _r(c.diferencia, 3), " ".join(c.mensaje.split()), x, y])
        co.lugares.append((c.x, c.y, "pipe" if c.pipes else None, c.pipes[0] if c.pipes else -1))
    return [ut, bz, cu, bd, av, co]


def exportar_excel(tablas, ruta):
    """Un libro con una hoja por tabla (encabezados ya traducidos). Lo arma `tabla_excel`
    (columnas editables en verde, hoja «Léeme»): se puede editar y volver a cargar."""
    from nucleo import tabla_excel
    tabla_excel.exportar(tablas, ruta)
