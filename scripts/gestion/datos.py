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
ESTADOS_BASE = dict(ESTADOS)
ORDEN_BASE = list(ORDEN_ESTADOS)
TIPOS_NOVEDAD = {"nuevo": "Novedades", "mejora": "Mejoras", "correccion": "Correcciones"}


@dataclass
class Grupo:
    id: str
    nombre: str
    padre: str = ""
    detalle: str = ""
    catalogo: str = ""          # área del catálogo cuyas piezas se cuentan en este grupo
    privado: bool = False       # el cliente no la ve (ni lo que tiene dentro): nunca se publica


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
    privado: bool = False       # el cliente no la ve: nunca se publica (pedido 2026-11-18)

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
    estados: list = field(default_factory=list)   # [[estado]]: estados propios o colores cambiados (dicts)

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


def aplicar_estados(lista):
    """[[estado]] de funciones.toml: id, nombre, cliente, fondo, texto. Cambia el color de uno de siempre o suma
    uno propio (antes de «Sin clasificar»). Se repone desde los de fábrica en cada lectura."""
    ESTADOS.clear()
    ESTADOS.update(ESTADOS_BASE)
    ORDEN_ESTADOS[:] = ORDEN_BASE
    for e in lista:
        eid = e.get("id", "")
        base = ESTADOS.get(eid, (eid, eid, "#c3d5df", "#24323b"))
        ESTADOS[eid] = (e.get("nombre") or base[0], e.get("cliente", base[1]), e.get("fondo") or base[2],
                        e.get("texto") or base[3])
        if eid not in ORDEN_ESTADOS:
            ORDEN_ESTADOS.insert(len(ORDEN_ESTADOS) - 1, eid)


def leer():
    d = _toml(ruta("funciones.toml"))
    p = d.get("proyecto", {})
    aplicar_estados(d.get("estado", []))
    return Proyecto(estados=list(d.get("estado", [])), nombre=p.get("nombre", "Proyecto"), version_actual=p.get("version_actual", ""),
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
    if not v.novedades:
        out.append("La versión aún no tiene cambios")
    for n in v.novedades:
        t = n.get("titulo") or "(sin título)"
        if not (n.get("titulo") or "").strip():
            out.append("Hay un cambio sin título")
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
            elif es_privada(pr, f):
                out.append(f"«{t}»: la función «{f.nombre}» es privada (el cliente no la ve)")
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
        if omitir_vacios and (v is False or v in ("", [], None)):
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
    partes += [_tabla("estado", e) for e in pr.estados]
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


# ───────────────────────── edición del administrador ─────────────────────────

def slug(texto, largo=40):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = "".join(c if c.isalnum() else "-" for c in t)
    return "-".join(p for p in t.split("-") if p)[:largo].strip("-") or "item"


def _id_libre(base, usados):
    i, out = 2, base
    while out in usados:
        out, i = f"{base}-{i}", i + 1
    return out


def agregar_grupo(pr: Proyecto, nombre, padre="", detalle=""):
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El grupo necesita un nombre")
    if padre and not pr.grupo(padre):
        raise ValueError(f"No existe el grupo «{padre}»")
    gid = _id_libre(f"{padre}.{slug(nombre)}" if padre else slug(nombre), {g.id for g in pr.grupos})
    g = Grupo(id=gid, nombre=nombre, padre=padre, detalle=detalle.strip())
    # justo después del último grupo de la misma rama, para que el orden del diagrama tenga sentido
    pos = max((i for i, x in enumerate(pr.grupos) if x.id == padre or x.padre == padre), default=len(pr.grupos) - 1)
    pr.grupos.insert(pos + 1, g)
    return g


def agregar_funcion(pr: Proyecto, grupo, nombre, estado="", desde="", nota="", hoy=None):
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("La función necesita un nombre")
    if not pr.grupo(grupo):
        raise ValueError(f"No existe el grupo «{grupo}»")
    fid = _id_libre(f"{grupo}.{slug(nombre)}", {f.id for f in pr.funciones})
    f = Funcion(id=fid, grupo=grupo, nombre=nombre, desde=desde or pr.version_actual, nota=nota.strip())
    aprobar(pr, f, estado, hoy)
    ult = max((i for i, x in enumerate(pr.funciones) if x.grupo == grupo), default=len(pr.funciones) - 1)
    pr.funciones.insert(ult + 1, f)
    return f


def editar_funcion(pr: Proyecto, f: Funcion, nombre=None, grupo=None, nota=None):
    """Cambia nombre, grupo o nota interna. El id no cambia (lo usan las versiones)."""
    if nombre is not None:
        if not nombre.strip():
            raise ValueError("El nombre no puede quedar vacío")
        f.nombre = nombre.strip()
    if grupo is not None and grupo != f.grupo:
        if not pr.grupo(grupo):
            raise ValueError(f"No existe el grupo «{grupo}»")
        f.grupo = grupo
    if nota is not None:
        f.nota = nota.strip()


def usos_de_funcion(pr: Proyecto, fid):
    return [v.numero for v in pr.versiones if any(fid in n.get("funciones", []) for n in v.novedades)]


def quitar_funcion(pr: Proyecto, f: Funcion):
    usos = usos_de_funcion(pr, f.id)
    if usos:
        raise ValueError(f"«{f.nombre}» está en las novedades de la versión {', '.join(usos)}: quítala de ahí primero")
    pr.funciones.remove(f)


def quitar_grupo(pr: Proyecto, gid):
    if pr.funciones_de(gid) or pr.hijos(gid):
        raise ValueError("Solo se puede quitar un grupo vacío (sin funciones ni subgrupos)")
    pr.grupos[:] = [g for g in pr.grupos if g.id != gid]


def poner_estado(pr: Proyecto, nombre, fondo, texto="#ffffff", cliente=None, eid=None):
    """Agrega un estado propio o cambia el color/nombre de uno existente (por `eid`)."""
    if eid is None:
        if not nombre.strip():
            raise ValueError("El estado necesita un nombre")
        eid = _id_libre(slug(nombre, 24).replace("-", "_"), set(ESTADOS))
    for c in (fondo, texto):
        if not (isinstance(c, str) and len(c) == 7 and c.startswith("#")):
            raise ValueError(f"Color inválido: {c}")
    d = {"id": eid, "nombre": nombre.strip() or ESTADOS.get(eid, ("",))[0],
         "cliente": (cliente if cliente is not None else nombre).strip(), "fondo": fondo, "texto": texto}
    pr.estados[:] = [e for e in pr.estados if e.get("id") != eid] + [d]
    aplicar_estados(pr.estados)
    return eid


def quitar_estado(pr: Proyecto, eid):
    if eid in ESTADOS_BASE:              # de fábrica: solo vuelve a su color original
        pr.estados[:] = [e for e in pr.estados if e.get("id") != eid]
    else:
        en_uso = [x.nombre for x in pr.funciones + pr.fichas if eid in (x.estado, x.propuesto)]
        if en_uso:
            raise ValueError(f"El estado se usa en {len(en_uso)} ítem(s), p. ej. «{en_uso[0]}»: cámbialos primero")
        pr.estados[:] = [e for e in pr.estados if e.get("id") != eid]
    aplicar_estados(pr.estados)


# ───────────────────────── privado (pedido 2026-11-18) ─────────────────────────

def grupo_privado(pr: Proyecto, gid):
    """La tarjeta/área o alguna de las que la contienen es privada."""
    vistos = set()
    while gid and gid not in vistos:
        vistos.add(gid)
        g = pr.grupo(gid)
        if g is None:
            return False
        if g.privado:
            return True
        gid = g.padre
    return False


def es_privada(pr: Proyecto, f: Funcion):
    return f.privado or grupo_privado(pr, f.grupo)


def publico(pr: Proyecto):
    """Copia del proyecto SIN lo privado: lo único que se arma para el cliente (sitio y reporte)."""
    import dataclasses
    grupos = [g for g in pr.grupos if not grupo_privado(pr, g.id)]
    ocultas = {g.catalogo for g in pr.grupos if g.catalogo and grupo_privado(pr, g.id)}
    return dataclasses.replace(pr, grupos=grupos,
                               funciones=[f for f in pr.funciones if not es_privada(pr, f)],
                               fichas=[fi for fi in pr.fichas if fi.area not in ocultas])
