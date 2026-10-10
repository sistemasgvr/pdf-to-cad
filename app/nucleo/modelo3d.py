"""Modelo 3D de vista previa (PURO: sin Qt). Lo que Civil 3D va a construir, con
las MISMAS reglas que el plugin, para verlo sin exportar:

  • Utilidades: el EJE va a solera + medio alto interior (`OffsetEjeARasante`,
    `model_ops.alto_interior_ft`), cotas por tramo (`model_ops.cotas_tramo`), las
    curvas (CV) con su arco real (`limpieza_tramos.curvas` → `model_ops.fillet_geo`),
    sección circular o «W x H». Abandonadas: A TRAZOS (su estilo 3D en Civil 3D).
  • Bancoducto: reemplaza a su utilidad (HAS_DUCT_BANK); envolvente W×H con el FONDO
    en la cota de la utilidad (CrearDuctBanks) y sus conductos adentro.
  • Buzones/cajas (ImportarRed): fondo = solera más baja que llega (o el SUMP del
    usuario), tapa = RIM o fondo + recubrimiento (COVER_MIN, si no 5 ft), «Altura»
    explícita manda, mínimo 1 ft. Sólidos: contorno real, cota superior del usuario
    o automática (`solid_top_centrado`).
  • Accesorios de presión (`accesorios.accesorios`) con la forma de WyeSolido.cs
    (`accesorios3d`): brazos con campana (Tee/Wye/cruz) o cuerpo curvo (codo), en un tono
    claro de la utilidad; cada tubo se RECORTA hasta entrar en su campana, como en Civil 3D.
  • Conexiones verticales aprobadas, avisos de normativa y choques (marcas).

`construir(...)` → `Escena` con mallas (numpy) listas para la GPU, los volúmenes para
elegir con el ratón y los datos de cada objeto. Coordenadas en pies, centradas en el
dibujo y con el suelo en z = 0.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from nucleo import accesorios as acc
from nucleo import accesorios3d as A3
from nucleo import limpieza_tramos as LT
from nucleo import mallas3d as M
from nucleo import model_ops
from nucleo.model import network_kind

PROFUNDIDAD_FT = 5.0          # recubrimiento por defecto del plugin (defaultDepth)
BUZON_DIAM_FT = 4.0           # buzón sin tamaño: 48"
CAJA_LADO_FT = 4.0
RECUBRIMIENTO_SUELO_FT = 3.0  # suelo automático sin tapas: 3 ft sobre la tubería más alta
TRAZO_AB_FT, TRAZO_AB_D, HUECO_AB = 3.0, 4.0, 0.6   # abandonadas: trazo ≥3 ft o 4·D, hueco 60 %
CLARO_ACC = 0.55              # accesorios: color de la utilidad aclarado (se distinguen del tubo)
LADOS = 12                    # lados de la sección circular

ID_ESTRUCTURA = 100000
ID_ACCESORIO = 200000
ID_AVISO = 300000

COLOR_BANCODUCTO = (0.66, 0.66, 0.62, 0.45)
COLOR_AVISO = (1.0, 0.72, 0.1, 1.0)
COLOR_INFO = (0.35, 0.65, 1.0, 1.0)
COLOR_CHOQUE = (0.9, 0.12, 0.12, 1.0)


def objeto_de(ident):
    """(«pipe»|«struct»|«accesorio»|«aviso», índice) de un id de malla."""
    ident = int(round(ident))
    for base, tipo in ((ID_AVISO, "aviso"), (ID_ACCESORIO, "accesorio"), (ID_ESTRUCTURA, "struct")):
        if ident > base:
            return tipo, ident - base - 1
    return ("pipe", ident - 1) if ident > 0 else (None, -1)


@dataclass
class Escena:
    opacos: np.ndarray = field(default_factory=lambda: M.VACIA.copy())
    transparentes: np.ndarray = field(default_factory=lambda: M.VACIA.copy())
    suelo: np.ndarray = field(default_factory=lambda: M.VACIA.copy())
    picks: tuple = ()
    objetos: dict = field(default_factory=dict)      # id → {tipo, indice, caja, …}
    origen: tuple = (0.0, 0.0, 0.0)                 # (x, y, z del suelo) en pies del dibujo
    caja: tuple = ((0, 0, 0), (0, 0, 0))            # límites de lo dibujado (sin suelo)
    suelo_z: float = 0.0
    cuentas: dict = field(default_factory=dict)

    @property
    def vacia(self):
        return not len(self.opacos) and not len(self.transparentes)


# ─────────────────────────── geometría de cada utilidad ───────────────────────────

def diametro_ft(p):
    return model_ops.diametro(p)[0] / 12.0


def seccion(p):
    """(perfil, alto interior ft): «W x H» → rectángulo; si no, círculo del diámetro."""
    nums = re.findall(r"\d+(?:\.\d+)?", str(p.get("pipe_size") or ""))
    if len(nums) >= 2 and "x" in str(p.get("pipe_size")).lower():
        w, h = float(nums[0]) / 12.0, float(nums[1]) / 12.0
        return M.perfil_rect(w, h), h
    d = diametro_ft(p)
    return M.perfil_circulo(d / 2.0, LADOS), d


def recorrido(pipes, structures, i, ft):
    """[(x_px, y_px, solera)] de la utilidad i con el arco de cada curva."""
    p = pipes[i]
    pts = [tuple(q) for q in p.get("pts") or []]
    n = len(pts)
    if n < 2:
        return []
    zz = [model_ops.cotas_tramo(p, k) for k in range(n - 1)]
    try:
        _cv, geos = LT.curvas(pipes, structures, i, ft) if n >= 3 else ({}, {})
    except Exception:
        geos = {}

    def z_en(k, q):
        a, b = pts[k], pts[k + 1]
        L = math.dist(a, b)
        t = 0.0 if L < 1e-9 else max(0.0, min(1.0, math.dist(a, q) / L))
        return zz[k][0] + (zz[k][1] - zz[k][0]) * t

    out = [(pts[0][0], pts[0][1], zz[0][0])]
    for k in range(1, n - 1):
        g = geos.get(k)
        if g is None:
            out.append((pts[k][0], pts[k][1], zz[k - 1][1]))
            if abs(zz[k][0] - zz[k - 1][1]) > 1e-6:          # escalón de cota en el vértice
                out.append((pts[k][0], pts[k][1], zz[k][0]))
            continue
        za, zb = z_en(k - 1, g["t1"]), z_en(k, g["t2"])
        arco = [tuple(g["t1"])] + [tuple(q) for q in g["arc"]] + [tuple(g["t2"])]
        largos = np.cumsum([0.0] + [math.dist(a, b) for a, b in zip(arco, arco[1:])])
        total = largos[-1] or 1.0
        out += [(q[0], q[1], za + (zb - za) * s / total) for q, s in zip(arco, largos)]
    out.append((pts[-1][0], pts[-1][1], zz[-1][1]))
    limpio = [out[0]]
    for q in out[1:]:
        if math.dist(q, limpio[-1]) > 1e-6:
            limpio.append(q)
    return limpio


class _Armado:
    def __init__(self, ft, colores):
        self.ft = ft
        self.colores = colores or {}
        self.op, self.tr = [], []
        self.picks = M.Picks()
        self.objetos = {}

    def color(self, capa, alfa=1.0, factor=1.0):
        r, g, b = self.colores.get(capa, (0.6, 0.6, 0.6))
        return (r * factor, g * factor, b * factor, alfa)

    def claro(self, capa, k=CLARO_ACC):
        """Color de la utilidad mezclado con blanco (accesorios)."""
        r, g, b = self.colores.get(capa, (0.6, 0.6, 0.6))
        return (r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k, 1.0)

    def mundo(self, x, y, z):
        return (x * self.ft, -y * self.ft, z)

    def registrar(self, ident, tipo, indice, puntos, **datos):
        q = np.asarray(puntos, float).reshape(-1, 3)
        self.objetos[ident] = dict(tipo=tipo, indice=indice, caja=(q.min(axis=0), q.max(axis=0)), **datos)

    def tubo(self, camino, perfil, color, ident, radio_pick, transparente=False):
        """Tubería por el recorrido (los quiebres quedan en inglete: sin bolas en las uniones)."""
        destino = self.tr if transparente else self.op
        destino.append(M.barrido_camino(camino, perfil, color, ident, minimo=True))
        for a, b in zip(camino, camino[1:]):
            self.picks.capsula(a, b, radio_pick, ident)


def trazos_abandonada(alto):
    """(trazo, hueco) en pies de una utilidad abandonada: proporcionales al diámetro."""
    trazo = max(TRAZO_AB_FT, TRAZO_AB_D * alto)
    return trazo, trazo * HUECO_AB


def _utilidad(ar, pipes, structures, i, con_bancoducto, cortes=()):
    p = pipes[i]
    if p.get("world") or len(p.get("pts") or []) < 2 or i in con_bancoducto:
        return
    perfil, alto = seccion(p)
    camino = [ar.mundo(x, y, z + alto / 2.0) for x, y, z in recorrido(pipes, structures, i, ar.ft)]
    if len(camino) < 2:
        return
    ab = bool(p.get("ab"))
    for parte in A3.cortar(camino, cortes):          # el tubo muere dentro de la campana del accesorio
        # Abandonada = A TRAZOS, como su estilo 3D en Civil 3D (linetype discontinuo).
        for tramo in (M.trozos(parte, *trazos_abandonada(alto)) if ab else [parte]):
            if len(tramo) >= 2:
                ar.tubo([tuple(q) for q in tramo], perfil, ar.color(p.get("layer")), i + 1, max(alto / 2.0, 0.25))
    ar.registrar(i + 1, "pipe", i, camino, capa=p.get("layer"), diam_in=model_ops.diametro(p)[0], ab=ab,
                 z0=camino[0][2] - alto / 2.0, z1=camino[-1][2] - alto / 2.0,
                 tope=max(q[2] for q in camino) + alto / 2.0)


def _bancoducto(ar, pipes, structures, db):
    w, h = float(db.get("width_in") or 12) / 12.0, float(db.get("height_in") or 8) / 12.0
    for i in db.get("pipes") or []:
        if not (0 <= i < len(pipes)) or len(pipes[i].get("pts") or []) < 2:
            continue
        p = pipes[i]
        camino = [ar.mundo(x, y, z + h / 2.0) for x, y, z in recorrido(pipes, structures, i, ar.ft)]
        if len(camino) < 2:
            continue
        ar.tubo(camino, M.perfil_rect(w, h), COLOR_BANCODUCTO, i + 1, max(w, h) / 2.0,
                transparente=True)
        for c in db.get("conduits") or []:
            r = float(c.get("diam") or 4) / 24.0
            dx, dy = float(c["cx"]) / 12.0 - w / 2.0, h / 2.0 - float(c["cy"]) / 12.0
            pts, nor, _s = M.perfil_circulo(r, LADOS)
            ar.tubo(camino, (pts + [dx, dy], nor, True), ar.color(p.get("layer")), i + 1, r)
        ar.registrar(i + 1, "pipe", i, camino, capa=p.get("layer"), bancoducto=db.get("name") or "",
                     z0=camino[0][2] - h / 2.0, z1=camino[-1][2] - h / 2.0, tope=max(q[2] for q in camino) + h / 2.0)


def _soleras_en(pipes, x, y, tol_px):
    """[(solera, utilidad)] de las utilidades con un vértice en (x, y)."""
    out = []
    for i, p in enumerate(pipes):
        pts = p.get("pts") or []
        for k, (vx, vy) in enumerate(pts):
            if abs(vx - x) <= tol_px and abs(vy - y) <= tol_px and len(pts) >= 2:
                seg = k if k < len(pts) - 1 else k - 1
                out.append((model_ops.z_en_tramo(p, seg, vx, vy), i))
                break
    return [(z, i) for z, i in out if z is not None]


def _estructura(ar, pipes, j, s):
    if s.get("world") or s.get("curve") or s.get("hidden") or s.get("x") is None:
        return
    x, y = float(s["x"]), float(s["y"])
    soleras = _soleras_en(pipes, x, y, max(1.0, 0.5 / ar.ft))
    capa = pipes[soleras[0][1]].get("layer") if soleras else ("ELECTRICO" if s.get("net") == "conduit" else "DRENAJE")
    ident = ID_ESTRUCTURA + j + 1
    contorno = [ar.mundo(px, py, 0)[:2] for px, py in s.get("outline") or []]
    if s.get("solid"):
        h = float(s.get("solid_height_ft") or model_ops.SOLID_DEFAULT_H_FT)
        if s.get("solid_top_z") is not None:
            top = float(s["solid_top_z"])
        elif soleras:
            top = max(model_ops.solid_top_centrado(z, model_ops.alto_interior_ft(pipes[i]), h) for z, i in soleras)
        else:
            top = None
        z0, z1 = (None, None) if top is None else (top - h, top)
    else:
        cover = next((float(pipes[i].get("cover_min") or 0) for _z, i in soleras
                      if float(pipes[i].get("cover_min") or 0) > 0), PROFUNDIDAD_FT)
        if s.get("rim") is not None and s.get("sump") is not None:
            z0, z1 = float(s["sump"]), float(s["rim"])
        elif soleras:
            z0 = min(z for z, _i in soleras)
            z1 = z0 + cover
        else:
            z0, z1 = None, None
        if z0 is not None and float(s.get("height_ft") or 0) > 0.01:
            z1 = z0 + float(s["height_ft"])
        elif z0 is not None and z1 - z0 < 1.0:
            z1 = z0 + max(cover, 3.0)
    if z0 is None:
        return "suelto", (x, y, s, ident, capa)
    _cuerpo(ar, x, y, s, ident, capa, z0, z1, contorno)
    return None


def _cuerpo(ar, x, y, s, ident, capa, z0, z1, contorno):
    c = ar.mundo(x, y, 0)[:2]
    color = ar.color(capa, 1.0, 0.8)
    if len(contorno) >= 3:
        ar.op.append(M.prisma(contorno, z0, z1, color, ident))
        r = max(math.dist(c, q) for q in contorno)
    elif s.get("net") == "conduit":
        L = CAJA_LADO_FT / 2.0
        ar.op.append(M.prisma([(c[0] - L, c[1] - L), (c[0] + L, c[1] - L), (c[0] + L, c[1] + L), (c[0] - L, c[1] + L)],
                              z0, z1, color, ident))
        r = L * 1.42
    else:
        nums = re.findall(r"\d+(?:\.\d+)?", str(s.get("part_size") or ""))
        d = float(s.get("width_ft") or 0) or (float(nums[0]) / 12.0 if nums else BUZON_DIAM_FT)
        r = d / 2.0
        ar.op.append(M.cilindro_vertical(c, r, z0, z1, color, ident))
    ar.picks.capsula((c[0], c[1], z0), (c[0], c[1], z1), r, ident)
    ar.registrar(ident, "struct", ident - ID_ESTRUCTURA - 1, [(c[0], c[1], z0), (c[0], c[1], z1)],
                 cod=s.get("cod", ""), z0=z0, z1=z1, solido=bool(s.get("solid")))


def _direcciones(p, x, y, tol):
    """Rumbos (unitarios, px) desde (x, y) hacia los tramos de `p` que llegan ahí."""
    pts = p.get("pts") or []
    out = []
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        L = math.dist(a, b)
        if L < 1e-9:
            continue
        t = ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / (L * L)
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if math.dist(q, (x, y)) > tol or t < -tol / L or t > 1 + tol / L:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        if t * L > tol:
            out.append((-ux, -uy, k))
        if (1 - t) * L > tol:
            out.append((ux, uy, k))
    return out


def _accesorios(ar, pipes, z_at):
    """Accesorios con la forma de WyeSolido.cs. Devuelve (cantidad, {utilidad: cortes})."""
    nodos = acc.accesorios(pipes, z_at, ar.ft)
    cortes = {}
    tol = acc.TOL_UNION_FT / ar.ft
    for n, a in enumerate(nodos):
        ident = ID_ACCESORIO + n + 1
        brazos = []
        for i in a.get("pipes") or []:
            p = pipes[i]
            _perfil, alto = seccion(p)
            for ux, uy, k in _direcciones(p, a["x"], a["y"], tol):
                z = model_ops.z_en_tramo(p, k, a["x"], a["y"]) + alto / 2.0
                z1 = model_ops.z_en_tramo(p, k, a["x"] + ux / ar.ft, a["y"] + uy / ar.ft) + alto / 2.0
                u = np.array([ux, -uy, z1 - z])                     # 1 ft en planta y lo que sube/baja
                brazos.append(A3.Brazo(dir=u / np.linalg.norm(u), d=diametro_ft(p), pipe=i, eje_z=z,
                                       extra=dict(xy=ar.mundo(a["x"], a["y"], 0)[:2], u=(ux, -uy))))
        if len(brazos) < 2:
            continue
        mayor = max(brazos, key=lambda b: b.d)
        centro = np.array([*brazos[0].extra["xy"], mayor.eje_z])
        malla, c = A3.pieza(a["tipo"], centro, brazos, ar.claro(pipes[mayor.pipe].get("layer")), ident)
        ar.op.append(malla)
        for b in brazos:
            fin = c + b.dir * (b.largo + b.d * A3.LARGO_CAMPANA_D)
            ar.picks.capsula(tuple(c), tuple(fin), b.r_campana, ident)
            cortes.setdefault(b.pipe, []).append((b.extra["xy"], b.extra["u"], max(b.alcance, 0.0)))
        ar.registrar(ident, "accesorio", n, [c], acc_tipo=a["tipo"], angulo=a.get("angulo"), capa=a.get("capa"),
                     pipes=list(a.get("pipes") or []), eje_z=float(c[2]), x=a["x"], y=a["y"])
    return len(nodos), cortes


def _verticales(ar, pipes, cruces):
    for c in cruces or []:
        ia, ib = c.get("pipe_a"), c.get("pipe_b")
        if c.get("z_a") is None or c.get("z_b") is None or not all(0 <= k < len(pipes) for k in (ia, ib)):
            continue
        da, db_ = diametro_ft(pipes[ia]), diametro_ft(pipes[ib])
        r = min(da, db_) / 2.0
        q = ar.mundo(c["x"], c["y"], 0)
        ar.op.append(M.cilindro_vertical(q[:2], r, float(c["z_a"]) + da / 2.0, float(c["z_b"]) + db_ / 2.0,
                                         ar.color(pipes[ia].get("layer")), ia + 1, 14))


def _marca_en_utilidad(ar, pipes, i, x, y):
    """Punto 3D (eje + radio) de la utilidad i más cercano a (x, y), o None."""
    if not (0 <= i < len(pipes)):
        return None
    p = pipes[i]
    pts = p.get("pts") or []
    mejor = None
    for k in range(len(pts) - 1):
        z = model_ops.z_en_tramo(p, k, x, y)
        a, b = pts[k], pts[k + 1]
        L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / L2))
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        dd = math.dist(q, (x, y))
        if mejor is None or dd < mejor[0]:
            mejor = (dd, z)
    _p, alto = seccion(p)
    return None if mejor is None else ar.mundo(x, y, mejor[1] + alto)


def _marcas(ar, pipes, avisos, choques):
    base = 0
    for m, a in enumerate(avisos or []):
        if a.get("clase") == "tipo":                  # como en el plano: «sin tipo» no se marca
            continue
        q = _marca_en_utilidad(ar, pipes, a.get("pipe", -1), a["x"], a["y"])
        if q is None:
            continue
        ident = ID_AVISO + m + 1
        r = max(0.6, diametro_ft(pipes[a["pipe"]]) * 0.5)
        ar.op.append(M.esfera((q[0], q[1], q[2] + r), r, COLOR_INFO if a.get("info") else COLOR_AVISO, ident))
        ar.picks.capsula((q[0], q[1], q[2] + r), (q[0], q[1], q[2] + r), r, ident)
        ar.registrar(ident, "aviso", m, [q], mensaje=a.get("mensaje", ""), info=bool(a.get("info")))
        base = m + 1
    for k, e in enumerate(choques or []):
        cerca = min(range(len(pipes)), key=lambda i: min(math.dist(q, (e["x"], e["y"]))
                                                           for q in pipes[i].get("pts") or [(1e18, 1e18)]),
                    default=None)
        q = _marca_en_utilidad(ar, pipes, cerca, e["x"], e["y"]) if cerca is not None else None
        if q is None:
            continue
        ident = ID_AVISO + base + k + 1
        ar.op.append(M.esfera((q[0], q[1], q[2] + 0.8), 0.8, COLOR_CHOQUE, ident))
        ar.picks.capsula((q[0], q[1], q[2] + 0.8), (q[0], q[1], q[2] + 0.8), 0.8, ident)
        ar.registrar(ident, "aviso", -1, [q], mensaje=e.get("mensaje", ""), choque=True)


# ─────────────────────────── escena completa ───────────────────────────

def construir(pipes, structures, ft, colores=None, duct_banks=(), cruces=(), avisos=(), choques=(),
              ocultas=(), ver=None, suelo_z=None):
    """Escena 3D. `ft` = pies por px del lienzo; `colores` = {capa: (r, g, b)} 0–1;
    `duct_banks` = [{name, width_in, height_in, conduits, pipes}]; `avisos` =
    [{x, y, clase, mensaje, pipe, info}]; `choques` = [{x, y}]; `ocultas` = capas que
    no se dibujan; `ver` = {estructuras, accesorios, avisos} (todo por defecto);
    `suelo_z` = cota del suelo (None = automática)."""
    ver = dict(dict(estructuras=True, accesorios=True, avisos=True), **(ver or {}))
    if not ft or ft <= 0:
        return Escena()
    ocultas = set(ocultas or ())
    visibles = [i for i, p in enumerate(pipes) if p.get("layer") not in ocultas]
    vis_pipes = [p if i in visibles else dict(p, pts=[]) for i, p in enumerate(pipes)]
    ar = _Armado(ft, colores)
    con_db = set()
    for db in duct_banks or []:
        idx = [i for i in db.get("pipes") or [] if i in visibles]
        con_db |= set(db.get("pipes") or [])
        _bancoducto(ar, vis_pipes, structures, dict(db, pipes=idx))
    n_acc, cortes = (_accesorios(ar, vis_pipes, lambda i, k, x, y: model_ops.z_en_tramo(vis_pipes[i], k, x, y))
                     if ver["accesorios"] else (0, {}))
    for i in visibles:
        _utilidad(ar, vis_pipes, structures, i, con_db, cortes.get(i, ()))
    sueltos = []
    if ver["estructuras"]:
        for j, s in enumerate(structures or []):
            r = _estructura(ar, vis_pipes, j, s)
            if r:
                sueltos.append(r[1])
    _verticales(ar, vis_pipes, cruces)
    if ver["avisos"]:
        _marcas(ar, vis_pipes, [a for a in avisos or [] if a.get("pipe", -1) in visibles], choques)

    todo = [m for m in ar.op + ar.tr if len(m)]
    if not todo and not sueltos:
        return Escena(cuentas=dict(utilidades=0, estructuras=0, accesorios=0))
    pos = np.concatenate([m[:, :3] for m in todo]) if todo else np.zeros((1, 3))
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    rims = [o["z1"] for o in ar.objetos.values() if o["tipo"] == "struct" and not o.get("solido")]
    topes = [o["tope"] for o in ar.objetos.values() if o["tipo"] == "pipe"]
    if suelo_z is None:
        suelo_z = max(rims) if rims else (max(topes) + RECUBRIMIENTO_SUELO_FT if topes else 0.0)
    for x, y, s, ident, capa in sueltos:               # sólido suelto: apoyado en el suelo
        h = float(s.get("solid_height_ft") or model_ops.SOLID_DEFAULT_H_FT)
        _cuerpo(ar, x, y, s, ident, capa, suelo_z - h, suelo_z,
                [ar.mundo(px, py, 0)[:2] for px, py in s.get("outline") or []])
    origen = np.array([(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, suelo_z])

    def centrar(m):
        if len(m):
            m[:, :3] -= origen
            m[:, 11:14] -= origen
        return m
    opacos, transp = centrar(M.juntar(ar.op)), centrar(M.juntar(ar.tr))
    margen = max(hi[0] - lo[0], hi[1] - lo[1]) * 0.08 + 10.0
    suelo = M.plano(lo[0] - margen - origen[0], lo[1] - margen - origen[1],
                    hi[0] + margen - origen[0], hi[1] + margen - origen[1], 0.0, (0.55, 0.47, 0.36, 1.0))
    A, B, R, I = ar.picks.arreglos()
    for o in ar.objetos.values():
        o["caja"] = (o["caja"][0] - origen, o["caja"][1] - origen)
    return Escena(opacos=opacos, transparentes=transp, suelo=suelo, picks=(A - origen, B - origen, R, I),
                  objetos=ar.objetos, origen=tuple(origen), caja=(lo - origen, hi - origen), suelo_z=suelo_z,
                  cuentas=dict(utilidades=sum(1 for o in ar.objetos.values() if o["tipo"] == "pipe"),
                               estructuras=sum(1 for o in ar.objetos.values() if o["tipo"] == "struct"),
                               accesorios=n_acc))
