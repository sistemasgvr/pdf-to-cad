"""Datos del PERFIL LONGITUDINAL de un recorrido (pedido del usuario 2026-10-31). PURO (sin Qt).

A partir de un `perfil_recorrido.Recorrido` arma lo que se dibuja, con las MISMAS reglas que `CREAR_PERFIL_RED`
(`API-CIVIL/proyecto1/docs/PERFIL_DISENO.md`):
- pasos (un tramo de utilidad o una parte) con estación, solera al inicio/fin, diámetro, alto interior, material
  y, en gravedad y presión, hacia dónde va el fluido (`nucleo/flujo`: el que indicó el usuario o el automático);
- fila de tramos (H.4): rachas con el mismo diámetro, material y estado (y en gravedad la misma pendiente);
- nodos (H.3): estructura de gravedad (STA · nombre · RIM · INV IN · INV OUT), accesorio (codo/tee/wye/cruz),
  reducción, deflexión de presión ≥1°, quiebre de conduit ≥2°, punta libre (END OF);
- válvulas (2026-11-05): las del proyecto sobre el recorrido, con su largo y su rótulo (H.3, como en el plugin);
- cruces (C.7): utilidades que cortan el recorrido a ≥15°, lejos de sus nodos, con el claro entre paredes;
- terreno: la tapa (RIM) de las estructuras del recorrido (la app no tiene superficie);
- escalas (F.3): `escala_auto` (horizontal), `elegir_v` (vertical) e `intervalos` de la rejilla.
Las cotas son SOLERAS (invert) como en la app; el eje = solera + medio alto interior, la corona = solera + alto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from nucleo import flujo as FL, model_ops, perfil_recorrido as PR, perfil_textos as T, perfil_trazo as TZ
from nucleo.model import network_kind

ANG_CRUCE_MIN_DEG = 15.0
UMBRAL_PRESION_DEG = 1.0
UMBRAL_CONDUIT_DEG = 2.0
S_ESTANDAR = (10, 20, 30, 40, 50, 60, 100, 200, 500, 1000)
V_ESTANDAR = (1, 2, 2.5, 4, 5, 10, 20, 25, 40, 50, 100)
COTA_MAYOR = (1, 2, 5, 10, 20, 50, 100)
COTA_MENOR = (0.5, 0.5, 1, 2, 5, 10, 20)
ANCHO_OBJ_IN = 24.0


@dataclass
class Paso:
    e0: float
    e1: float
    z0: float                  # solera al inicio (en el sentido de las estaciones)
    z1: float
    diam_in: float
    alto_ft: float
    material: str
    ab: bool
    pipe: int
    tramo: int
    lado0: str                 # lado del tramo de la utilidad en el inicio del paso («inicio»/«fin», o "" = parte)
    lado1: str
    p0: tuple
    p1: tuple
    invertida: bool = False    # el paso recorre su utilidad del fin al inicio
    flujo: int = 0             # 1 = el fluido va hacia B (estaciones mayores), -1 = hacia A, 0 = no aplica o sin indicar
    flujo_fijo: bool = False   # True = lo indicó el usuario (`pipe["flujo"]`/`["flujo_hacia"]`); False = automático
    flujo_corte: float = None  # parámetro sobre la cuerda p0→p1 donde LLEGA el fluido, si cae dentro del paso: la
                               # parte de antes va hacia B y la de después hacia A (`flujo` = 1); None = todo `flujo`
    t0: float = 0.0            # la parte [t0, t1] del tramo de la utilidad que recorre el paso (en su sentido)
    t1: float = 1.0
    traza: tuple = ()          # en planta, tal como se dibuja (con las curvas; `perfil_trazo`); () = la cuerda p0→p1
    s: tuple = ()              # parámetro de cada punto de `traza` sobre la cuerda p0→p1
    acum: tuple = ()           # largo exacto (px) desde el inicio del paso hasta cada punto de `traza`

    @property
    def pendiente(self):
        return (self.z1 - self.z0) / max(self.e1 - self.e0, 0.01)

    @property
    def puntos(self):
        """La traza en planta (la cuerda si el paso no tiene curvas)."""
        return self.traza or (self.p0, self.p1)

    def _acum(self):
        if self.traza and len(self.acum) == len(self.traza):
            return list(self.acum)
        pts = self.puntos
        out = [0.0]
        for p, q in zip(pts, pts[1:]):
            out.append(out[-1] + math.dist(p, q))
        return out

    def e_en(self, t):
        """Estación del punto de la cuerda p0→p1 en su parámetro t (sobre la curva, si la hay)."""
        if not self.traza:
            return self.e0 + (self.e1 - self.e0) * t
        acum, ss = self._acum(), self.s
        tot = acum[-1] or 1.0
        for k in range(len(ss) - 1):
            if ss[k] - 1e-12 <= t <= ss[k + 1] + 1e-12:
                f = 0.0 if ss[k + 1] - ss[k] <= 1e-12 else (t - ss[k]) / (ss[k + 1] - ss[k])
                return self.e0 + (self.e1 - self.e0) * (acum[k] + (acum[k + 1] - acum[k]) * f) / tot
        return self.e0 if t <= ss[0] else self.e1

    def t_en(self, e):
        """Lo inverso de `e_en`: el parámetro sobre la cuerda p0→p1 del punto de la estación e."""
        f = max(0.0, min(1.0, (e - self.e0) / max(self.e1 - self.e0, 1e-12)))
        if not self.traza:
            return f
        acum, ss = self._acum(), self.s
        meta = f * acum[-1]
        for k in range(len(ss) - 1):
            if meta <= acum[k + 1] + 1e-12 or k == len(ss) - 2:
                g = 0.0 if acum[k + 1] - acum[k] <= 1e-12 else (meta - acum[k]) / (acum[k + 1] - acum[k])
                return ss[k] + (ss[k + 1] - ss[k]) * max(0.0, min(1.0, g))
        return f

    def punto_cuerda(self, t):
        """Punto de la cuerda p0→p1 (sobre la polilínea de la utilidad) en su parámetro t."""
        return (self.p0[0] + (self.p1[0] - self.p0[0]) * t, self.p0[1] + (self.p1[1] - self.p0[1]) * t)

    def punto_en(self, e):
        """Punto en planta de la estación e (dentro del paso)."""
        f = (e - self.e0) / max(self.e1 - self.e0, 1e-9)
        if not self.traza:
            return (self.p0[0] + (self.p1[0] - self.p0[0]) * f, self.p0[1] + (self.p1[1] - self.p0[1]) * f)
        pts, acum = self.traza, self._acum()
        meta = max(0.0, min(1.0, f)) * acum[-1]
        for k in range(len(pts) - 1):
            if meta <= acum[k + 1] or k == len(pts) - 2:
                g = 0.0 if acum[k + 1] - acum[k] <= 1e-12 else (meta - acum[k]) / (acum[k + 1] - acum[k])
                return (pts[k][0] + (pts[k + 1][0] - pts[k][0]) * g, pts[k][1] + (pts[k + 1][1] - pts[k][1]) * g)
        return pts[-1]

    def proyectar(self, x, y):
        """(distancia, estación) del punto (x, y) proyectado sobre el paso tal como se dibuja; None si es nulo."""
        pts = self.puntos
        acum = self._acum()
        tot = acum[-1]
        if tot <= 1e-12:
            return None
        mejor = None
        for k in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 <= 1e-12:
                continue
            u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            d = math.hypot(ax + dx * u - x, ay + dy * u - y)
            if mejor is None or d < mejor[0]:
                mejor = (d, acum[k] + (acum[k + 1] - acum[k]) * u)
        if mejor is None:
            return None
        return mejor[0], self.e0 + (self.e1 - self.e0) * mejor[1] / tot


@dataclass
class Nodo:
    e: float
    x: float
    y: float
    tipo: str                  # estructura | codo | tee | wye | cruz | reduccion | deflexion | quiebre | extremo | union
    lineas: list
    arriba: bool               # franja del callout (superior / inferior)
    z_ancla: float             # cota donde apunta el leader
    rim: float | None = None
    cod: str = ""
    editable: list = field(default_factory=list)   # [(pipe, tramo, lado)] cotas que se mueven con este nodo


@dataclass
class Cruce:
    e: float
    z_solera: float
    diam_in: float
    alto_ft: float
    pipe: int
    encima: bool
    claro: float
    lineas: list


@dataclass
class Valvula:
    e: float
    z_solera: float
    alto_ft: float
    diam_in: float
    largo_ft: float
    paso: int
    lineas: list
    z_caja: float = None        # tope de la caja de la válvula (superficie); None = sin caja


@dataclass
class Celda:
    e0: float
    e1: float
    lineas: list


@dataclass
class Perfil:
    tipo: str
    red: str
    pasos: list
    nodos: list
    cruces: list
    celdas: list
    terreno: list              # [(estación, cota)]
    e_ini: float
    e_fin: float
    z_min: float
    z_max: float
    d_pred: float
    s: float
    v: float
    intervalos: tuple          # (cota mayor, cota menor, estación mayor, estación menor)
    titulo: list
    valvulas: list = field(default_factory=list)


# ---------------------------------------------------------------- escalas (F.3)

def escala_auto(largo):
    if not largo or largo <= 0:
        return S_ESTANDAR[0]
    for s in S_ESTANDAR:
        if largo / s <= ANCHO_OBJ_IN + 1e-9:
            return s
    return S_ESTANDAR[-1]


def elegir_v(s):
    ve = 2.5 if s <= 10 else (s / 5.0 if s <= 20 else min(10.0, s / 4.0))
    obj = s / ve
    for v in V_ESTANDAR:
        if v >= obj - 1e-9:
            return v
    return math.ceil(obj / 100.0 - 1e-9) * 100.0


def intervalos(s, v):
    k = len(COTA_MAYOR) - 1
    for i, c in enumerate(COTA_MAYOR):
        if c / v >= 2.0 - 1e-9:
            k = i
            break
    est_mayor = 100.0 if 100.0 / s >= 0.75 - 1e-9 else (500.0 if 500.0 / s >= 0.75 - 1e-9 else 1000.0)
    return COTA_MAYOR[k], COTA_MENOR[k], est_mayor, est_mayor / 10.0


# ---------------------------------------------------------------- armado

def armar(pipes, structures, accs, rec, ft, numero=1, v=None, valvulas=()):
    """`accs` = accesorios del plano (`Main._accs_todos`, o []); `v` = escala vertical forzada (None = auto);
    `valvulas` = las válvulas ubicadas del proyecto (dicts de `nucleo/valvulas.Lugar`)."""
    g = rec.grafo
    tol = PR.TOL_FT / ft if ft else 3.0
    pasos = _pasos(pipes, rec, ft, structures)
    nodos = _nodos(pipes, structures, accs or [], rec, pasos, ft, tol)
    cruces = _cruces(pipes, rec, pasos, ft, tol)
    celdas = _celdas(g.tipo, pasos)
    terreno = sorted((n.e, n.rim) for n in nodos if n.rim is not None)
    vals = _valvulas(pasos, valvulas, ft, pipes)
    largo = {}
    for p in pasos:
        k = round(p.diam_in, 3)
        largo[k] = largo.get(k, 0.0) + (p.e1 - p.e0)
    d_pred = max(largo, key=largo.get) if largo else 0.0
    zs = [p.z0 for p in pasos] + [p.z1 for p in pasos] + [p.z0 + p.alto_ft for p in pasos] \
        + [p.z1 + p.alto_ft for p in pasos] + [c.z_solera for c in cruces] \
        + [c.z_solera + c.alto_ft for c in cruces] + [z for _e, z in terreno]         + [v.z_caja for v in vals if v.z_caja is not None]
    e_ini, e_fin = rec.estaciones[0], rec.estaciones[-1]
    s = escala_auto(e_fin - e_ini)
    vv = v or elegir_v(s)
    return Perfil(g.tipo, g.red, pasos, nodos, cruces, celdas, terreno, e_ini, e_fin,
                  min(zs) if zs else 0.0, max(zs) if zs else 1.0, d_pred, s, vv, intervalos(s, vv),
                  T.lineas_titulo(numero, d_pred, g.tipo, g.red, s, vv), vals)


def _valvulas(pasos, valvulas, ft, pipes=()):
    """Válvulas del proyecto que caen sobre un paso del recorrido (su utilidad y su tramo, el centro sobre el
    paso), con la estación y la solera de ese punto. En orden de estación."""
    out = []
    for v in valvulas or ():
        for i, p in enumerate(pasos):
            if p.pipe != v.get("pipe") or p.tramo != v.get("tramo"):
                continue
            ax, ay = p.p0
            bx, by = p.p1
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 <= 0:
                continue
            t = ((v["x"] - ax) * dx + (v["y"] - ay) * dy) / L2
            if t < -1e-6 or t > 1 + 1e-6:
                continue
            if math.hypot(ax + dx * t - v["x"], ay + dy * t - v["y"]) * (ft or 1.0) > 0.1:
                continue
            e = p.e_en(t)
            z = p.z0 + (p.z1 - p.z0) * t
            d = float(v.get("diam_in") or p.diam_in)
            engranes = (v.get("bloque") or "").endswith("_GEAR")
            out.append(Valvula(e, z, p.alto_ft, d, float(v.get("largo_ft") or 0.0), i,
                               T.lineas_valvula(e, d, v.get("union") or "FLG", engranes, z + p.alto_ft)))
            from nucleo import valvulas as VV
            capa = pipes[p.pipe].get("layer") if 0 <= p.pipe < len(pipes) else None
            cj = VV.caja(z + p.alto_ft / 2.0, p.alto_ft * 12.0, capa, v["x"], v["y"])
            out[-1].z_caja = cj[1] if cj else None
            break
    return sorted(out, key=lambda x: x.e)


def _pasos(pipes, rec, ft, structures=()):
    g = rec.grafo
    out = []
    largos = []
    geos = {}                                         # utilidad → sus curvas (`perfil_trazo`)
    for paso in rec.pasos:
        ar = g.aristas[paso.arista]
        p = pipes[ar.pipe]
        za, zb = PR.z_solera(pipes, ar, 0.0), PR.z_solera(pipes, ar, 1.0)
        la = "inicio" if ar.t0 <= 1e-9 else ""
        lb = "fin" if ar.t1 >= 1 - 1e-9 else ""
        pa, pb = ar.pa, ar.pb
        if paso.invertida:
            za, zb, la, lb, pa, pb = zb, za, lb, la, pb, pa
        if ar.pipe not in geos:
            geos[ar.pipe] = TZ.curvas(pipes, structures, ar.pipe, ft)
        real = TZ.de_arista(p.get("pts") or [], geos[ar.pipe], ar, paso.invertida) if geos[ar.pipe] else None
        traza, ss, acum = real if real else ((), (), ())
        largos.append((acum[-1] if acum else ar.largo_px) * ft)   # por la curva (arco exacto), como el eje de C3D
        out.append(Paso(0.0, 0.0, za, zb, model_ops.diametro(p)[0], model_ops.alto_interior_ft(p),
                        p.get("material") or "", bool(p.get("ab")), ar.pipe, ar.tramo, la, lb, pa, pb,
                        bool(paso.invertida), traza=traza, s=ss, acum=acum, t0=ar.t0, t1=ar.t1))
    PR.estaciones(rec, ft, largos)
    for k, p in enumerate(out):
        p.e0, p.e1 = rec.estaciones[k], rec.estaciones[k + 1]
    if g.tipo in FL.REDES:
        _flujo(pipes, rec, out, g.tipo)
    return out


def _flujo(pipes, rec, pasos, tipo="gravity"):
    """Hacia dónde va el fluido en cada paso: el que indicó el usuario en la utilidad (a una punta o a un punto
    intermedio: `flujo_corte` si cae dentro del paso) o, si es automático, en gravedad hacia el extremo más bajo del
    recorrido (empate = hacia A, la regla de siempre: las estaciones automáticas empiezan en la solera más baja); a
    presión, sin indicar (0)."""
    if not pasos:
        return
    tendencia = FL.AUTO
    if tipo == "gravity":
        z_punta = getattr(rec.grafo, "_z_punta", None) or {}
        za, zb = z_punta.get(rec.nodos[0]), z_punta.get(rec.nodos[-1])
        if za is None or zb is None:
            za, zb = pasos[0].z0, pasos[-1].z1
        tendencia = FL.ADELANTE if zb < za - 1e-6 else FL.ATRAS
    for p in pasos:
        f, corte = FL.en_arista(pipes[p.pipe], p.tramo, p.t0, p.t1, p.invertida)
        p.flujo_fijo = FL.tiene(pipes[p.pipe])
        p.flujo = f or tendencia
        p.flujo_corte = corte


def _rumbo(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _lado(d_run, d_ramal):
    """LT / RT del ramal mirando en el sentido de las estaciones (el lienzo tiene la Y hacia abajo)."""
    cruz = math.cos(d_run) * math.sin(d_ramal) - math.sin(d_run) * math.cos(d_ramal)
    return "RT" if cruz > 0 else "LT"


def _estructura_en(structures, x, y, tol):
    mejor = None
    for s in structures:
        if s.get("hidden") or s.get("curve"):
            continue
        sx, sy = s.get("x"), s.get("y")
        if not isinstance(sx, (int, float)) or not isinstance(sy, (int, float)):
            continue
        d = math.hypot(sx - x, sy - y)
        if d <= tol and (mejor is None or d < mejor[0]):
            mejor = (d, s)
    return mejor[1] if mejor else None


def _accesorio_en(accs, x, y, tol):
    mejor = None
    for a in accs:
        d = math.hypot(a["x"] - x, a["y"] - y)
        if d <= tol and (mejor is None or d < mejor[0]):
            mejor = (d, a)
    return mejor[1] if mejor else None


def _nodos(pipes, structures, accs, rec, pasos, ft, tol):
    g = rec.grafo
    gravedad = g.tipo == "gravity"
    usadas = {p.arista for p in rec.pasos}
    out = []
    n = len(rec.nodos)
    for k, nid in enumerate(rec.nodos):
        x, y = g.nodos[nid]
        e = rec.estaciones[k]
        llega = pasos[k - 1] if k > 0 else None
        sale = pasos[k] if k < len(pasos) else None
        ref = llega or sale
        z_in = llega.z1 if llega else None
        z_out = sale.z0 if sale else None
        top = (z_in if z_in is not None else z_out) + ref.alto_ft
        editable = []
        if llega and llega.lado1:
            editable.append((llega.pipe, llega.tramo, llega.lado1))
        if sale and sale.lado0:
            editable.append((sale.pipe, sale.tramo, sale.lado0))
        ramales = [ea for ea in g.de_nodo.get(nid, ()) if ea not in usadas]
        est = _estructura_en(structures, x, y, model_ops._TOL) if gravedad else None
        if est is not None:
            entradas = [(z_in, ref.diam_in, "", False)] if z_in is not None else []
            d_run = _rumbo(llega.p0, llega.p1) if llega else _rumbo(sale.p0, sale.p1)
            for ea in ramales:
                ar = g.aristas[ea]
                t = 0.0 if ar.a == nid else 1.0
                d_r = PR._dir_salida(g, ea, nid)
                entradas.append((PR.z_solera(pipes, ar, t), model_ops.diametro(pipes[ar.pipe])[0],
                                 _lado(d_run, d_r), True))
            rim = est.get("rim")
            rim = float(rim) if isinstance(rim, (int, float)) else None
            out.append(Nodo(e, x, y, "estructura",
                            T.lineas_estructura(e, est.get("cod") or "", rim, entradas, z_out),
                            True, rim if rim is not None else top, rim, est.get("cod") or "", editable))
            continue
        acc = _accesorio_en(accs, x, y, tol)
        extremo = k in (0, n - 1)
        if acc is not None and acc.get("tipo") in ("tee", "wye", "cruz"):
            dm = ref.diam_in
            tronco = [j for j in acc.get("tronco") or () if isinstance(j, int) and 0 <= j < len(pipes)]
            if tronco:                                 # el principal es el del tronco (en el perfil de un ramal
                dm = max(model_ops.diametro(pipes[j])[0] for j in tronco)   # la T queda en su punta)
            ri = acc.get("ramal")
            dr = model_ops.diametro(pipes[ri])[0] if isinstance(ri, int) and 0 <= ri < len(pipes) else dm
            lado = ""
            if ramales:
                d_run = _rumbo(ref.p0, ref.p1)
                lado = _lado(d_run, PR._dir_salida(g, ramales[0], nid))
            if acc["tipo"] == "tee":
                lin = T.lineas_tee(e, dm, dr, lado, top)
            elif acc["tipo"] == "wye":
                lin = T.lineas_wye(e, dm, dr, lado, acc.get("angulo"), top)
            else:
                lin = T.lineas_cruz(e, dm, dr, top)
            out.append(Nodo(e, x, y, acc["tipo"], lin, True, top, editable=editable))
            continue
        if extremo and not (acc is not None and acc.get("tipo") == "codo"):
            z = (z_in if z_in is not None else z_out)
            out.append(Nodo(e, x, y, "extremo",
                            T.lineas_extremo(e, ref.diam_in, ref.material, gravedad,
                                             z if gravedad else top),
                            True, top, editable=editable))
            continue
        if llega and sale:
            dh = PR.deflexion(_rumbo(llega.p0, llega.p1), _rumbo(sale.p0, sale.p1))
            dv = math.degrees(abs(math.atan(sale.pendiente) - math.atan(llega.pendiente)))
        else:
            dh, dv = 0.0, 0.0
        vertical = dv > dh
        if acc is not None and acc.get("tipo") == "codo":
            ang = acc.get("angulo") if acc.get("angulo") is not None else max(dh, dv)
            out.append(Nodo(e, x, y, "codo", T.lineas_codo(e, ref.diam_in, ang, vertical, ref.material, top),
                            False, top, editable=editable))
            continue
        if llega and sale and round(llega.diam_in) != round(sale.diam_in):
            out.append(Nodo(e, x, y, "reduccion", T.lineas_reduccion(e, llega.diam_in, sale.diam_in, top),
                            False, top, editable=editable))
            continue
        defl = max(dh, dv)
        if g.tipo == "pressure" and defl >= UMBRAL_PRESION_DEG:
            out.append(Nodo(e, x, y, "deflexion", T.lineas_deflexion(e, defl, top), False, top, editable=editable))
        elif g.tipo == "conduit" and defl >= UMBRAL_CONDUIT_DEG:
            out.append(Nodo(e, x, y, "quiebre", T.lineas_quiebre_conduit(e, defl, vertical, top),
                            False, top, editable=editable))
        else:
            out.append(Nodo(e, x, y, "union", [], False, top, editable=editable))
    return out


def _celdas(tipo, pasos):
    out = []
    i = 0
    while i < len(pasos):
        a = pasos[i]
        j = i + 1
        while j < len(pasos):
            b = pasos[j]
            if (round(b.diam_in) != round(a.diam_in) or b.material != a.material or b.ab != a.ab
                    or (tipo == "gravity" and abs(b.pendiente - a.pendiente) >= 1e-4)):
                break
            j += 1
        e0, e1 = a.e0, pasos[j - 1].e1
        s = (pasos[j - 1].z1 - a.z0) / max(e1 - e0, 0.01)
        out.append(Celda(e0, e1, T.lineas_tramo(tipo, a.ab, e1 - e0, a.diam_in, a.material, s)))
        i = j
    return out


def _corte(a, b, c, d):
    """(t sobre a→b, u sobre c→d) del cruce de los dos segmentos, o None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    q = (c[0] - a[0], c[1] - a[1])
    t = (q[0] * s[1] - q[1] * s[0]) / den
    u = (q[0] * r[1] - q[1] * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return t, u
    return None


def _cruces(pipes, rec, pasos, ft, tol):
    g = rec.grafo
    del_recorrido = {p.pipe for p in pasos}
    nodos = [g.nodos[n] for n in rec.nodos]
    e_ini, e_fin = rec.estaciones[0], rec.estaciones[-1]
    out = []
    for j, p in enumerate(pipes):
        pts = p.get("pts") or []
        if j in del_recorrido or len(pts) < 2 or p.get("world"):
            continue
        if any(math.hypot(q[0] - nx, q[1] - ny) <= tol for q in (pts[0], pts[-1]) for nx, ny in nodos):
            continue
        hallado = None
        for k in range(len(pts) - 1):
            c, d = pts[k], pts[k + 1]
            for paso in pasos:
                tu = _corte(paso.p0, paso.p1, c, d)
                if tu is None:
                    continue
                ang = PR.deflexion(_rumbo(paso.p0, paso.p1), _rumbo(c, d))
                ang = min(ang, 180.0 - ang)
                e = paso.e_en(tu[0])
                if ang < ANG_CRUCE_MIN_DEG or not (e_ini + 0.5 <= e <= e_fin - 0.5):
                    continue
                hallado = (paso, tu, k, e)
                break
            if hallado:
                break
        if not hallado:
            continue
        paso, (t, u), k, e = hallado
        zz = model_ops.cotas_tramo(p, k) or (0.0, 0.0)
        z = float(zz[0]) + (float(zz[1]) - float(zz[0])) * u
        alto = model_ops.alto_interior_ft(p)
        d_in = model_ops.diametro(p)[0]
        z_run = paso.z0 + (paso.z1 - paso.z0) * t
        eje, eje_run = z + alto / 2, z_run + paso.alto_ft / 2
        encima = eje > eje_run
        claro = (z - (z_run + paso.alto_ft)) if encima else (z_run - (z + alto))
        grav = network_kind(p.get("layer") or "") == "gravity"
        lineas = T.lineas_cruce(d_in, p.get("material") or "", bool(p.get("ab")), model_ops.red_de(p), grav,
                                z if grav else z + alto)
        out.append(Cruce(e, z, d_in, alto, j, encima, claro, lineas))
    out.sort(key=lambda c: c.e)
    return out
