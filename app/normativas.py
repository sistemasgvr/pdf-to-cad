"""Normativas de diseño (PURO: sin Qt). Motor escalable de reglas.

Arquitectura (pensada para crecer: distancias entre buzones, separaciones entre
utilidades, recubrimientos… con valores de la ciudad de Los Ángeles):

  - TIPO de regla (`TIPOS`): qué se comprueba y con qué campos. Lleva su
    categoría, la lista de `Campo`s que la ventana dibuja SOLA (no hay UI por
    regla) y su función `verificar(regla, contexto) -> Resultado`.
  - REGLA (dict): una instancia de un tipo con valores concretos: id, tipo,
    título, descripción, fuente, utilidades a las que aplica, si es obligatoria
    o recomendada, si viene activada y sus parámetros. `REGLAS_BASE` trae las
    iniciales; el usuario edita valores y el catálogo se guarda GLOBAL
    (`ruta_global`, solo lo que difiere de la base).
  - ESTADO del proyecto: {id: activa} — cada proyecto decide qué reglas usa
    (va al .digproj como `normativas_activas`).
  - CONTEXTO: los datos del proyecto que miran los verificadores, calculados
    una sola vez y solo si alguna regla los pide (accesorios, …).

Para sumar una normativa nueva: un `TipoRegla` en `TIPOS` (campos + verificar)
y, si trae valores iniciales, su entrada en `REGLAS_BASE`. La ventana, el guardado
y los avisos en el lienzo no cambian. Tipos de campo que la ventana ya sabe
editar: `grados_lista`, `grados`, `pies`, `utilidades`.
"""
from __future__ import annotations

import copy
import json
import math
import os
from dataclasses import dataclass, field
from typing import Callable

from i18n_core import N_, t

import accesorios as acc

# ─────────────────────────────── catálogo ───────────────────────────────

CATEGORIAS = {                      # orden = orden en la ventana
    "conexiones": N_("Accesorios de conexión"),
    "separaciones": N_("Separaciones entre utilidades"),
    "recubrimiento": N_("Recubrimiento"),
    "requisitos": N_("Otros requisitos"),
    "estructuras": N_("Buzones y estructuras"),
}

# Utilidades de la app + objetos contra los que se mide una separación
# (llegan de las tablas de los ingenieros: vía férrea, bordillo, sumidero…).
CONTRAS = {
    "AGUA": N_("Agua"), "ALCANTARILLADO": N_("Alcantarillado"), "DRENAJE": N_("Drenaje"),
    "GAS": N_("Gas"), "ELECTRICO": N_("Eléctrico"), "TELECOM": N_("Telecomunicaciones"),
    "VIA_FERREA": N_("Vía férrea"), "BORDILLO": N_("Bordillo y cuneta"), "SUMIDERO": N_("Sumidero"),
    "BUZON": N_("Buzón"), "OTRA_TUBERIA": N_("Otra tubería"), "SUPERFICIE": N_("Superficie"),
}

UTILIDADES_PRESION = ("AGUA", "GAS")

NOMBRE_ACCESORIO = {"codo": N_("Codo"), "tee": N_("Tee"), "wye": N_("Wye"), "cruz": N_("Cruz")}


@dataclass
class Campo:
    clave: str                      # clave en regla["params"] (o "utilidades")
    tipo: str                       # grados_lista | grados | pies | utilidades
    etiqueta: str                   # N_(…): se traduce al mostrar
    ayuda: str = ""
    minimo: float = 0.0
    maximo: float = 360.0
    opciones: tuple = ()            # utilidades: las que tiene sentido elegir (vacío = todas)
    opcional: bool = False          # puede quedar vacío (p. ej. un máximo que no existe)


@dataclass
class Incumplimiento:
    regla: str
    x: float
    y: float
    valor: float
    esperado: float
    mensaje: str
    capa: str = ""
    pipes: list = field(default_factory=list)


@dataclass
class Resultado:
    regla: str
    activa: bool
    evaluados: int = 0
    incumplimientos: list = field(default_factory=list)
    pendiente: bool = False         # el tipo de regla aún no se revisa en el plano


@dataclass
class TipoRegla:
    id: str
    nombre: str
    categoria: str
    campos: list
    verificar: Callable


class Contexto:
    """Datos del proyecto para los verificadores, calculados al primer uso.
    `z_at(i_pipe, i_tramo, x, y)` = solera; `ft_per_px` = escala del lienzo."""

    def __init__(self, pipes, structures=None, z_at=None, ft_per_px=0.0):
        self.pipes = pipes or []
        self.structures = structures or []
        self.z_at = z_at
        self.ft_per_px = ft_per_px or 0.0
        self._acc = None

    @property
    def accesorios(self):
        if self._acc is None:
            self._acc = acc.accesorios(self.pipes, self.z_at, self.ft_per_px)
        return self._acc


def _mas_cercano(valor, permitidos):
    return min(permitidos, key=lambda a: abs(a - valor)) if permitidos else valor


def _verificar_angulos(regla, ctx):
    """Ángulos permitidos de un tipo de accesorio (codo/tee/wye/cruz)."""
    p = regla.get("params") or {}
    tipo = p.get("accesorio", "codo")
    permitidos = sorted(float(a) for a in p.get("angulos") or [])
    tol = float(p.get("tolerancia", 1.0))
    utils = set(regla.get("utilidades") or [])
    res = Resultado(regla["id"], True)
    for a in ctx.accesorios:
        if a["tipo"] != tipo or (utils and a["capa"] not in utils):
            continue
        res.evaluados += 1
        if any(abs(a["angulo"] - v) <= tol + 1e-9 for v in permitidos):
            continue
        cerca = _mas_cercano(a["angulo"], permitidos)
        msg = t("{acc} de {ang} en {capa}: fuera de norma. Permitidos: {lista} (±{tol}). "
                "El más cercano es {cerca}.").format(
            acc=t(NOMBRE_ACCESORIO.get(tipo, tipo)), ang=acc.texto_angulo(a["angulo"]),
            capa=a["capa"], lista=", ".join(acc.texto_angulo(v) for v in permitidos) or "—",
            tol=acc.texto_angulo(tol), cerca=acc.texto_angulo(cerca))
        res.incumplimientos.append(Incumplimiento(regla["id"], a["x"], a["y"], a["angulo"], cerca,
                                                  msg, a["capa"], list(a["pipes"])))
    return res


def _sin_revision(regla, _ctx):
    """Tipos que se guardan, se exportan y se editan, pero que todavía no se
    comprueban sobre el plano (separaciones, recubrimiento…)."""
    return Resultado(regla["id"], True, pendiente=True)


_CAMPOS_DISTANCIA = [
    Campo("minimo", "pies", N_("Mínimo"), "", 0.0, 1000.0, opcional=True),
    Campo("maximo", "pies", N_("Máximo"), "", 0.0, 1000.0, opcional=True),
]

TIPOS = {
    "separacion_horizontal": TipoRegla(
        id="separacion_horizontal", nombre=N_("Separación horizontal"), categoria="separaciones",
        campos=_CAMPOS_DISTANCIA, verificar=_sin_revision),
    "separacion_vertical": TipoRegla(
        id="separacion_vertical", nombre=N_("Separación vertical"), categoria="separaciones",
        campos=_CAMPOS_DISTANCIA, verificar=_sin_revision),
    "recubrimiento": TipoRegla(
        id="recubrimiento", nombre=N_("Recubrimiento"), categoria="recubrimiento",
        campos=_CAMPOS_DISTANCIA, verificar=_sin_revision),
    "requisito": TipoRegla(
        id="requisito", nombre=N_("Requisito (texto)"), categoria="requisitos",
        campos=[], verificar=_sin_revision),
    "angulos_accesorio": TipoRegla(
        id="angulos_accesorio", nombre=N_("Ángulos permitidos de un accesorio"), categoria="conexiones",
        campos=[
            Campo("angulos", "grados_lista", N_("Ángulos permitidos"),
                  N_("Escribe un ángulo en grados y pulsa Agregar. Quita uno con su botón ×."), 0.1, 180.0),
            Campo("tolerancia", "grados", N_("Tolerancia"),
                  N_("Cuánto puede apartarse el ángulo dibujado de uno permitido."), 0.0, 10.0),
            Campo("utilidades", "utilidades", N_("Se aplica a"), opciones=UTILIDADES_PRESION),
        ],
        verificar=_verificar_angulos),
}

FUENTE_AWWA = N_("AWWA C110 / C153 — valores iniciales")

REGLAS_BASE = [
    {"id": "conex_codo", "tipo": "angulos_accesorio",
     "titulo": N_("Codos: solo ángulos comerciales"),
     "descripcion": N_("Los codos se fabrican en ángulos fijos. Se mide el ángulo ENTRE las dos tuberías "
                       "(180° = sigue recta): los codos AWWA de 11.25°, 22.5°, 45° y 90° dan 168.75°, "
                       "157.5°, 135° y 90°."),
     "fuente": FUENTE_AWWA, "utilidades": list(UTILIDADES_PRESION), "obligatoria": True, "activa": True,
     "params": {"accesorio": "codo", "angulos": [90.0, 135.0, 157.5, 168.75], "tolerancia": 1.0}},
    {"id": "conex_tee", "tipo": "angulos_accesorio",
     "titulo": N_("Tee: ramal a 90°"),
     "descripcion": N_("La Tee une un ramal perpendicular a una tubería recta."),
     "fuente": FUENTE_AWWA, "utilidades": list(UTILIDADES_PRESION), "obligatoria": True, "activa": True,
     "params": {"accesorio": "tee", "angulos": [90.0], "tolerancia": 1.0}},
    {"id": "conex_wye", "tipo": "angulos_accesorio",
     "titulo": N_("Wye: ramal a 45°"),
     "descripcion": N_("La Wye une un ramal inclinado a una tubería."),
     "fuente": FUENTE_AWWA, "utilidades": list(UTILIDADES_PRESION), "obligatoria": True, "activa": True,
     "params": {"accesorio": "wye", "angulos": [45.0], "tolerancia": 1.0}},
    {"id": "conex_cruz", "tipo": "angulos_accesorio",
     "titulo": N_("Cruz: líneas a 90°"),
     "descripcion": N_("La cruz une dos tuberías que se cruzan en ángulo recto."),
     "fuente": FUENTE_AWWA, "utilidades": list(UTILIDADES_PRESION), "obligatoria": True, "activa": True,
     "params": {"accesorio": "cruz", "angulos": [90.0], "tolerancia": 1.0}},
]

EDITABLES = ("params", "utilidades", "obligatoria", "activa")


def es_base(rid):
    return any(r["id"] == rid for r in REGLAS_BASE)


def titulo_de(regla):
    """Título para mostrar: el propio (reglas de la app) o armado con sus datos
    (reglas importadas del Excel: «Eléctrico ↔ Agua · Separación horizontal»)."""
    if regla.get("titulo"):
        return t(regla["titulo"])
    p = regla.get("params") or {}
    utils = ", ".join(t(CONTRAS.get(u, u)) for u in regla.get("utilidades") or [])
    if p.get("condicion"):
        utils += f" ({p['condicion']})"
    contra = t(CONTRAS.get(p.get("contra", ""), p.get("contra", "")))
    if p.get("condicion_contra"):
        contra += f" ({p['condicion_contra']})"
    tipo = TIPOS.get(regla.get("tipo"))
    nombre = t(tipo.nombre) if tipo else regla.get("tipo", "")
    return f"{utils} ↔ {contra} · {nombre}" if contra.strip() else f"{utils} · {nombre}"


def _pies(v):
    return f"{v:g} ft"


def resumen_valor(regla):
    """El valor en pocas palabras, para la fila compacta de la ventana."""
    p = regla.get("params") or {}
    if regla.get("tipo") == "angulos_accesorio":
        return ", ".join(acc.texto_angulo(a) for a in p.get("angulos") or []) + \
            f" (±{acc.texto_angulo(float(p.get('tolerancia', 0)))})"
    mn, mx = p.get("minimo"), p.get("maximo")
    if mn is not None and mx is not None:
        return f"{mn:g}–{mx:g} ft"
    if mn is not None:
        return "≥ " + _pies(mn)
    if mx is not None:
        return "≤ " + _pies(mx)
    return p.get("texto_original", "")[:60]

# ─────────────────────────────── guardado ───────────────────────────────


def ruta_global():
    """Archivo del catálogo del usuario (común a todos los proyectos)."""
    r = os.environ.get("PDFCAD_NORMATIVAS")
    if r:
        return r
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "pdf-to-cad", "normativas.json")


def _base_por_id():
    return {r["id"]: r for r in REGLAS_BASE}


def cargar_anexos(ruta=None):
    """Referencias, notas y datos del documento que llegaron con el Excel
    ({"referencias": {id: texto}, "notas": [...], "documento": {...}})."""
    try:
        with open(ruta or ruta_global(), encoding="utf-8") as f:
            datos = json.load(f) or {}
    except (OSError, ValueError):
        datos = {}
    return {"referencias": dict(datos.get("referencias") or {}), "notas": list(datos.get("notas") or []),
            "documento": dict(datos.get("documento") or {})}


def fusionar(reglas, nuevas):
    """Agrega o actualiza las reglas importadas. Una regla de la app (mismo id)
    solo cambia sus valores; las demás se reemplazan enteras. Devuelve
    (cuántas nuevas, cuántas actualizadas)."""
    por_id = {r["id"]: i for i, r in enumerate(reglas)}
    n_new = n_upd = 0
    for nr in nuevas:
        i = por_id.get(nr["id"])
        if i is None:
            reglas.append(nr); por_id[nr["id"]] = len(reglas) - 1; n_new += 1
            continue
        actual = reglas[i]
        if es_base(nr["id"]):
            for k in EDITABLES:
                if k == "params":
                    actual["params"].update({pk: pv for pk, pv in (nr.get("params") or {}).items()
                                             if pk in actual["params"]})
                elif k in nr:
                    actual[k] = nr[k]
        else:
            reglas[i] = nr
        n_upd += 1
    return n_new, n_upd


def quitar(reglas, rid):
    """Quita una regla importada (las de la app no se quitan: se desactivan)."""
    if es_base(rid):
        return False
    n = len(reglas)
    reglas[:] = [r for r in reglas if r["id"] != rid]
    return len(reglas) < n


def cargar_catalogo(ruta=None):
    """REGLAS_BASE + lo que el usuario cambió (archivo global). Una regla del
    archivo sin base (creada por el usuario) se agrega si su tipo existe."""
    reglas = copy.deepcopy(REGLAS_BASE)
    ruta = ruta or ruta_global()
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return reglas
    cambios = (datos or {}).get("reglas") or {}
    # Versión 1: los ángulos de codo se guardaban como GIRO; desde la 2 son el
    # ángulo entre las dos tuberías (180° − giro).
    if int((datos or {}).get("version", 1)) < 2:
        for cam in cambios.values():
            p = cam.get("params") if isinstance(cam, dict) else None
            if isinstance(p, dict) and isinstance(p.get("angulos"), list) and cam is cambios.get("conex_codo"):
                p["angulos"] = sorted(round(180.0 - float(a), 4) for a in p["angulos"])
    por_id = {r["id"]: r for r in reglas}
    for rid, cam in cambios.items():
        r = por_id.get(rid)
        if r is None or not isinstance(cam, dict):
            continue
        for k in EDITABLES:
            if k == "params" and isinstance(cam.get(k), dict):
                r["params"].update(cam[k])
            elif k in cam:
                r[k] = cam[k]
    for r in (datos or {}).get("extra") or []:
        if isinstance(r, dict) and r.get("tipo") in TIPOS and r.get("id") not in por_id:
            reglas.append(r)
    return reglas


def guardar_catalogo(reglas, ruta=None, anexos=None):
    """Guarda SOLO lo que difiere de la base (así una mejora de los valores
    iniciales llega a quien no los tocó), las reglas importadas enteras y los
    anexos del Excel (si no se pasan, se conservan los que ya había)."""
    if anexos is None:
        anexos = cargar_anexos(ruta)
    base = _base_por_id()
    cambios, extra = {}, []
    for r in reglas:
        b = base.get(r["id"])
        if b is None:
            extra.append(r)
            continue
        dif = {}
        for k in EDITABLES:
            if k == "params":
                dp = {pk: pv for pk, pv in (r.get("params") or {}).items() if b["params"].get(pk) != pv}
                if dp:
                    dif["params"] = dp
            elif r.get(k) != b.get(k):
                dif[k] = r.get(k)
        if dif:
            cambios[r["id"]] = dif
    ruta = ruta or ruta_global()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "reglas": cambios, "extra": extra, **anexos}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)


def restablecer(reglas, rid):
    """Vuelve la regla `rid` a sus valores iniciales (si tiene base)."""
    b = _base_por_id().get(rid)
    if b is None:
        return False
    for i, r in enumerate(reglas):
        if r["id"] == rid:
            reglas[i] = copy.deepcopy(b)
            return True
    return False


def modificada(regla):
    """True si la regla difiere de sus valores iniciales."""
    b = _base_por_id().get(regla["id"])
    return b is not None and any(regla.get(k) != b.get(k) for k in ("params", "utilidades", "obligatoria"))


# ─────────────────────────────── edición ────────────────────────────────


def aplicar_cambio(regla, clave, valor):
    """Valida y aplica un cambio de la ventana. Devuelve None si es válido o el
    texto del error (ya traducido) si no."""
    tipo = TIPOS.get(regla.get("tipo"))
    if clave == "obligatoria":
        regla["obligatoria"] = bool(valor)
        return None
    campo = next((c for c in (tipo.campos if tipo else []) if c.clave == clave), None)
    if campo is None:
        return t("Campo desconocido: {c}").format(c=clave)
    try:
        if campo.tipo == "grados_lista":
            vals = sorted({round(float(v), 4) for v in valor})
            if not vals:
                return t("Debe quedar al menos un ángulo permitido.")
            if any(not (campo.minimo <= v <= campo.maximo) for v in vals):
                return t("Cada ángulo debe estar entre {a} y {b}.").format(
                    a=acc.texto_angulo(campo.minimo), b=acc.texto_angulo(campo.maximo))
            regla["params"][clave] = vals
        elif campo.tipo in ("grados", "pies") and campo.opcional and valor in (None, ""):
            regla["params"][clave] = None
        elif campo.tipo in ("grados", "pies"):
            v = float(valor)
            if not (campo.minimo <= v <= campo.maximo) or math.isnan(v):
                return t("El valor debe estar entre {a} y {b}.").format(a=campo.minimo, b=campo.maximo)
            regla["params"][clave] = v
            p = regla["params"]
            if p.get("minimo") is not None and p.get("maximo") is not None and p["maximo"] < p["minimo"]:
                return t("El máximo no puede ser menor que el mínimo.")
        elif campo.tipo == "utilidades":
            vals = [str(u) for u in valor]
            if not vals:
                return t("Elige al menos una utilidad.")
            regla["utilidades"] = vals
        else:
            return t("Campo desconocido: {c}").format(c=clave)
    except (TypeError, ValueError):
        return t("Valor no válido.")
    return None


# ─────────────────────────────── evaluación ─────────────────────────────


def activa_en(regla, estado_proyecto):
    """¿La regla está activa en este proyecto? (sin ajuste propio → la del catálogo)."""
    return bool((estado_proyecto or {}).get(regla["id"], regla.get("activa", True)))


def evaluar(reglas, estado_proyecto, ctx):
    """{id: Resultado}. Las reglas desactivadas no se comprueban."""
    salida = {}
    for r in reglas:
        tipo = TIPOS.get(r.get("tipo"))
        if tipo is None:
            continue
        if not activa_en(r, estado_proyecto):
            salida[r["id"]] = Resultado(r["id"], False)
            continue
        salida[r["id"]] = tipo.verificar(r, ctx)
    return salida


def incumplimientos(resultados, reglas):
    """Lista plana de (Incumplimiento, regla) de las reglas activas, las
    obligatorias primero."""
    por_id = {r["id"]: r for r in reglas}
    out = [(i, por_id[res.regla]) for res in resultados.values() if res.activa
           for i in res.incumplimientos if res.regla in por_id]
    out.sort(key=lambda ir: (not ir[1].get("obligatoria", True), ir[0].capa, ir[0].x, ir[0].y))
    return out


def estado_de_punto(x, y, lista, tol):
    """'obligatoria' / 'recomendada' / None: la peor regla incumplida en (x, y)."""
    peor = None
    for inc, regla in lista:
        if (inc.x - x) ** 2 + (inc.y - y) ** 2 <= tol * tol:
            if regla.get("obligatoria", True):
                return "obligatoria", inc, regla
            peor = peor or ("recomendada", inc, regla)
    return peor or (None, None, None)
