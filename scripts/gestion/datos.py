"""Datos de la gestión del proyecto (2026-11-11): funciones, versiones y catálogo de piezas, en TOML dentro de
`gestion/` del repo. Puro (sin Qt): lo usan el generador del sitio, la vista de administrador y el reporte.

Regla de revisión: cada persona (o su Claude) escribe solo `propuesto` (+ `propuesto_por`, `propuesto_nota`);
`estado` y `aprobado` los pone únicamente el administrador desde `python scripts/gestion admin`. Lo único que ve
el cliente es `estado`.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import tomllib
from dataclasses import dataclass, field

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GESTION = os.environ.get("PDFCAD_GESTION") or os.path.join(RAIZ, "gestion")


def ruta(*partes):
    return os.path.join(GESTION, *partes)


# id → (nombre interno, nombre para el cliente, color de fondo, color del texto)
ESTADOS = {
    "probado": ("Probado", "Disponible", "#2e9e4f", "#ffffff"),
    "falta_probar": ("Falta probar", "En pruebas", "#f2a7c3", "#5a1631"),
    "optimizar": ("Por optimizar", "En mejora", "#f39237", "#ffffff"),
    "en_desarrollo": ("En desarrollo", "En desarrollo", "#3b7dd8", "#ffffff"),
    "planificado": ("Planificado", "Planificado", "#e7ebee", "#3d4b55"),
    "con_bug": ("Con bug reportado", "En corrección", "#d64545", "#ffffff"),
    "": ("Sin clasificar", "", "#c3d5df", "#24323b"),
}
ORDEN_ESTADOS = ["probado", "falta_probar", "optimizar", "en_desarrollo", "con_bug", "planificado", ""]
TIPOS_NOVEDAD = {"nuevo": "Novedades", "mejora": "Mejoras", "correccion": "Correcciones"}


@dataclass
class Grupo:
    id: str
    nombre: str
    padre: str = ""
    detalle: str = ""
    catalogo: str = ""          # área del catálogo cuyas piezas se cuentan en este grupo


@dataclass
class Funcion:
    id: str
    grupo: str
    nombre: str
    estado: str = ""
    aprobado: str = ""
    propuesto: str = ""
    propuesto_por: str = ""
    propuesto_nota: str = ""
    desde: str = ""
    nota: str = ""              # interna: nunca sale en el sitio público

    @property
    def por_revisar(self):
        return bool(self.propuesto) and self.propuesto != self.estado


@dataclass
class Ficha:
    """Una pieza del catálogo (`gestion/catalogo/<area>/<tipo>/<id>/ficha.toml` + capturas)."""
    carpeta: str
    nombre: str
    tipo: str = ""
    area: str = ""
    responsable: str = ""
    descripcion: str = ""
    entradas: list = field(default_factory=list)
    tamanos: str = ""
    version: str = ""
    estado: str = ""
    aprobado: str = ""
    propuesto: str = ""
    propuesto_por: str = ""
    propuesto_nota: str = ""
    issues: list = field(default_factory=list)
    capturas: list = field(default_factory=list)

    @property
    def id(self):
        return os.path.relpath(self.carpeta, ruta("catalogo")).replace(os.sep, "/")

    @property
    def por_revisar(self):
        return bool(self.propuesto) and self.propuesto != self.estado


@dataclass
class Version:
    archivo: str
    numero: str
    fecha: str = ""
    titulo: str = ""
    resumen: str = ""
    publicada: bool = False
    novedades: list = field(default_factory=list)    # dicts: tipo, titulo, detalle, funciones, observacion
    pendientes: list = field(default_factory=list)   # dicts: titulo, detalle


@dataclass
class Proyecto:
    nombre: str
    version_actual: str
    admin: str
    sitio: str
    grupos: list
    funciones: list
    versiones: list
    fichas: list
    cloudflare: str = "pdfacad-funciones"     # nombre del proyecto de Cloudflare Pages

    def grupo(self, gid):
        return next((g for g in self.grupos if g.id == gid), None)

    def hijos(self, gid):
        return [g for g in self.grupos if g.padre == gid]

    def funciones_de(self, gid):
        return [f for f in self.funciones if f.grupo == gid]

    def fichas_de(self, area):
        return [f for f in self.fichas if f.area == area]

    def raices(self):
        return [g for g in self.grupos if not g.padre]


# ───────────────────────── leer ─────────────────────────

def _toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _campos(cls, d):
    nombres = cls.__dataclass_fields__
    return {k: v for k, v in d.items() if k in nombres}


def leer_ficha(carpeta):
    d = _toml(os.path.join(carpeta, "ficha.toml"))
    capturas = sorted(a for a in os.listdir(carpeta)
                      if a.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")))
    return Ficha(carpeta=carpeta, capturas=capturas, **_campos(Ficha, d))


def leer_fichas():
    base = ruta("catalogo")
    fichas = []
    for raiz, dirs, archivos in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith("_"))
        if "ficha.toml" in archivos and os.path.basename(raiz)[:1] != "_":
            fichas.append(leer_ficha(raiz))
    return fichas


def leer_versiones():
    base = ruta("versiones")
    out = []
    if os.path.isdir(base):
        for a in os.listdir(base):
            if a.endswith(".toml"):
                d = _toml(os.path.join(base, a))
                v = d.get("version", {})
                out.append(Version(archivo=os.path.join(base, a), novedades=d.get("novedad", []),
                                   pendientes=d.get("pendiente", []), **_campos(Version, v)))
    return sorted(out, key=lambda v: _clave_version(v.numero), reverse=True)


def _clave_version(n):
    return tuple(int(p) if p.isdigit() else 0 for p in str(n).split("."))


def leer():
    d = _toml(ruta("funciones.toml"))
    p = d.get("proyecto", {})
    return Proyecto(nombre=p.get("nombre", "Proyecto"), version_actual=p.get("version_actual", ""),
                    admin=p.get("admin", "Admin"), sitio=p.get("sitio", ""),
                    cloudflare=p.get("cloudflare", "pdfacad-funciones"),
                    grupos=[Grupo(**_campos(Grupo, g)) for g in d.get("grupo", [])],
                    funciones=[Funcion(**_campos(Funcion, f)) for f in d.get("funcion", [])],
                    versiones=leer_versiones(), fichas=leer_fichas())


def validar(pr: Proyecto):
    """Lista de problemas en palabras (vacía = todo bien)."""
    errores = []
    ids = {g.id for g in pr.grupos}
    vistos = set()
    for g in pr.grupos:
        if g.padre and g.padre not in ids:
            errores.append(f"Grupo «{g.id}»: su padre «{g.padre}» no existe")
    for f in pr.funciones:
        if f.id in vistos:
            errores.append(f"Función repetida: «{f.id}»")
        vistos.add(f.id)
        if f.grupo not in ids:
            errores.append(f"Función «{f.id}»: su grupo «{f.grupo}» no existe")
        for campo in ("estado", "propuesto"):
            if getattr(f, campo) not in ESTADOS:
                errores.append(f"Función «{f.id}»: {campo} «{getattr(f, campo)}» no es un estado válido")
    for fi in pr.fichas:
        for campo in ("estado", "propuesto"):
            if getattr(fi, campo) not in ESTADOS:
                errores.append(f"Ficha «{fi.id}»: {campo} «{getattr(fi, campo)}» no es un estado válido")
    for v in pr.versiones:
        if v.publicada:                      # una versión publicada debe cumplir todo
            errores += [f"Versión {v.numero}: {p}" for p in pendientes_version(pr, v)]
        else:
            for n in v.novedades:
                if n.get("tipo") not in TIPOS_NOVEDAD:
                    errores.append(f"Versión {v.numero}: novedad «{n.get('titulo')}» con tipo «{n.get('tipo')}»")
    return errores


def pendientes_version(pr: "Proyecto", v: "Version"):
    """Lo que impide publicar una versión. Regla (2026-11-11): todo cambio de una versión va asociado a una o más
    funciones del diagrama, y cada una debe existir y tener estado aprobado (si no, el cliente vería un cambio que
    no está en el diagrama)."""
    funciones = {f.id: f for f in pr.funciones}
    out = []
    for n in v.novedades:
        t = n.get("titulo") or "(sin título)"
        if n.get("tipo") not in TIPOS_NOVEDAD:
            out.append(f"«{t}»: tipo «{n.get('tipo')}» (usa nuevo, mejora o correccion)")
        if not n.get("funciones"):
            out.append(f"«{t}»: no está asociada a ninguna función del diagrama")
        for fid in n.get("funciones", []):
            f = funciones.get(fid)
            if f is None:
                out.append(f"«{t}»: la función «{fid}» no existe en el diagrama")
            elif not f.estado:
                out.append(f"«{t}»: la función «{f.nombre}» aún no tiene estado aprobado")
    return out


# ───────────────────────── escribir ─────────────────────────

def _valor(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_valor(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def _tabla(nombre, d, arreglo=True, omitir_vacios=True):
    lineas = [f"[[{nombre}]]" if arreglo else f"[{nombre}]"]
    for k, v in d.items():
        if omitir_vacios and v in ("", [], None):
            continue
        lineas.append(f"{k} = {_valor(v)}")
    return "\n".join(lineas)


CABECERA_FUNCIONES = """\
# Funciones del proyecto: fuente del diagrama (vista general y por versión) que ve el cliente.
# Editar: una entrada [[funcion]] por función, con un nombre CORTO (como en el diagrama).
# Cada persona (o su Claude) solo escribe `propuesto` (+ propuesto_por, propuesto_nota).
# `estado` y `aprobado` los pone SOLO el administrador con:  python scripts/gestion admin
# Estados: probado, falta_probar, optimizar, en_desarrollo, con_bug, planificado ("" = sin clasificar).
"""


def guardar_funciones(pr: Proyecto):
    partes = [CABECERA_FUNCIONES,
              _tabla("proyecto", dict(nombre=pr.nombre, version_actual=pr.version_actual, admin=pr.admin,
                                      sitio=pr.sitio, cloudflare=pr.cloudflare), arreglo=False)]
    for g in pr.grupos:
        partes.append(_tabla("grupo", g.__dict__))
    actual = None
    for f in pr.funciones:
        if f.grupo != actual:
            partes.append(f"# ── {f.grupo} ──")
            actual = f.grupo
        partes.append(_tabla("funcion", f.__dict__))
    _escribir(ruta("funciones.toml"), "\n\n".join(partes) + "\n")


def guardar_ficha(fi: Ficha):
    d = {k: v for k, v in fi.__dict__.items() if k not in ("carpeta", "capturas")}
    texto = ("# Ficha de una pieza del catálogo. Solo llenar `propuesto`; `estado` y `aprobado` los pone el "
             "administrador.\n" + "\n".join(_tabla("x", d, arreglo=False).splitlines()[1:]) + "\n")
    _escribir(os.path.join(fi.carpeta, "ficha.toml"), texto)


def guardar_version(v: Version):
    partes = ["# Entrega al cliente: lo que se escribe aquí sale tal cual en el sitio y en el reporte.\n"
              "# Títulos cortos y simples (no técnicos). `publicada = true` solo lo pone el administrador.",
              _tabla("version", dict(numero=v.numero, fecha=v.fecha, titulo=v.titulo, resumen=v.resumen,
                                     publicada=v.publicada), arreglo=False, omitir_vacios=False)]
    partes += [_tabla("novedad", n) for n in v.novedades]
    partes += [_tabla("pendiente", n) for n in v.pendientes]
    _escribir(v.archivo, "\n\n".join(partes) + "\n")


def _escribir(path, texto):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    os.replace(tmp, path)


def firma_aprobacion(pr: Proyecto, hoy=None):
    return f"{pr.admin} {(hoy or _dt.date.today()).isoformat()}"


def aprobar(pr: Proyecto, item, estado, hoy=None):
    """El administrador fija el estado oficial (y consume lo propuesto)."""
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")
    item.estado = estado
    item.aprobado = firma_aprobacion(pr, hoy) if estado else ""
    item.propuesto = item.propuesto_por = item.propuesto_nota = ""


def rechazar(item, motivo=""):
    if hasattr(item, "nota") and motivo:
        item.nota = (item.nota + " · " if item.nota else "") + f"Rechazado «{item.propuesto}»: {motivo}"
    item.propuesto = item.propuesto_por = item.propuesto_nota = ""


def conteo(items):
    c = {k: 0 for k in ORDEN_ESTADOS}
    for it in items:
        c[it.estado if it.estado in c else ""] += 1
    return c
