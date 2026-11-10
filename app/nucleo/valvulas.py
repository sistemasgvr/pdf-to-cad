"""Válvulas de compuerta en redes a PRESIÓN (agua y gas), pedido del usuario 2026-11-04. PURO (sin Qt).

El usuario pone la válvula con un clic sobre una tubería (como el buzón) y la app decide todo lo demás:
diámetro (el de la tubería), pieza del catálogo, largo y dónde cabe. Solo en un TRAMO RECTO: entre dos vértices
de la tubería (o entre la tangencia de una curva y el vértice siguiente), nunca encima de un codo, Tee, Wye,
cruz ni curva. Lo que la app indica, el plugin lo cumple: el DXF lleva el punto EXACTO del centro, la dirección
del tramo y la pieza (`PDFCAD_VALVULA`).

Pieza = `valvula_receta` (2026-11-05: la forma del catálogo del plugin de válvulas del equipo como fórmulas del
diámetro, para CUALQUIER diámetro de `N_MIN` a `N_MAX`; fuera de la tabla de normas queda «estimada»): válvula de
compuerta AWWA C509/C515; RG (junta mecánica) hasta 16"; desde 18" con bridas y operador de engranes. Medidas
representativas (no certificadas por un fabricante), como dice ese plugin.

UN SOLO MODELO (unión con dev_santos_v2, 2026-11-06): una válvula la pone el usuario (Dibujar → Accesorios →
Válvula) o la lee el reconocimiento del PDF (`reconocimiento/recognition_valvulas`). Cada una es un dict:

    x, y        centro (px de la vista), sobre su tubería
    union       "FLG" | "RG"                      (pieza; las reconocidas empiezan en FLG)
    material    "" = el de la tubería | "DI-A" | "CI" | "PVC"
    utilidad    capa de la app («AGUA», «GAS»…) o "" si el plano no lo dice
    tipo        "" = compuerta; si no, el del plano («Purga», «Retención», «Mariposa»…; `TEXTOS`)
    estado      "abierta" | "cerrada" | ""
    origen      capa | leyenda | forma | manual
    certeza     segura | por_confirmar
    capa_pdf    capa o símbolo de donde salió
    x_pdf, y_pdf  (solo reconocidas) dónde estaba el símbolo antes de pegarla a su tubería (`pegar`)

Sin índices de utilidades: borrar o unir utilidades no las desordena; en cada redibujo y al exportar se vuelve a
ubicar sobre su tubería (`ubicar(..., libre=False)`) y, si ya no está en un tramo recto donde quepa —o una reconocida
cae junto a un codo, una Tee o una curva—, queda «por revisar» en rojo con el motivo y no va al DXF hasta que el
usuario la corra o la confirme (`exportable`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from nucleo import limpieza_tramos, model_ops
from nucleo import valvula_receta as VR
from nucleo.accesorios import GIRO_CODO_MIN_DEG, TOL_UNION_FT, red_de
from nucleo.model import network_kind
from traduccion.i18n_core import t as _tr

SERIE = VR.SERIE                       # diámetros de la tabla de normas (los demás, «estimados»)
RG_MAX_IN = VR.RG_MAX_IN               # la junta mecánica (RG) llega hasta 16"
ENGRANES_MIN_IN = VR.ENGRANES_MIN_IN   # ≥ 18": bridas + operador de engranes
UNIONES = ("FLG", "RG")
MATERIALES = ("DI-A", "CI", "PVC")

ALCANCE_ACC_D = 1.70           # brazo 1.25·D + campana 0.45·D de un codo/Tee/Wye/cruz (`accesorios3d`)
TUBO_MIN_FT = limpieza_tramos.TRAMO_MIN_FT   # tubo libre entre la válvula y lo que haya a cada lado (1 ft)
SOBRE_TOL_FT = 0.05            # una válvula guardada sigue «en su lugar» si se corre menos que esto
EPS = 1e-9
# Caja de la válvula (valve box, 2026-11-06): el tubo de 5-1/4" que sube de la válvula a la superficie para meter la
# llave (Tyler 6850 / AWWA). Va de la corona de la tubería hasta el SUELO (`nucleo/terreno`: hoy la cota 0, pedido
# del usuario 2026-11-06), lo mismo en el perfil, la Vista 3D y Civil 3D (el DXF lleva CAJA_TOPE_Z de cada una).
CAJA_DIAM_IN = 5.25


def caja(z_eje, diam_in, capa=None, x=None, y=None):
    """(cota de la base, cota del tope) de la caja de una válvula en (x, y) del plano: de la corona (eje + D/2) al
    suelo (`terreno.cota_en`), o None si la corona ya está en el suelo o encima (no hay caja que dibujar)."""
    from nucleo import terreno
    base = float(z_eje) + float(diam_in or 0.0) / 24.0
    tope = terreno.cota_en(x, y)
    return (base, tope) if base < tope - 1e-6 else None


def diametro_valido(d_in):
    """El diámetro (pulgadas, redondeado a 0.01") si hay válvula para él, o None."""
    d = round(float(d_in or 0), 2)
    return d if VR.N_MIN - 1e-9 <= d <= VR.N_MAX + 1e-9 else None


def pieza(n, union="FLG"):
    """(bloque, unión efectiva, largo in, OD del extremo in, avisos) de la válvula de n pulgadas. Todas se dibujan
    como la de COMPUERTA (`valvula_receta`; pedido del usuario 2026-11-08: una sola válvula genérica); el tipo que
    traiga del plano queda solo como dato."""
    rec = VR.receta(n, union)
    avisos = []
    u = "RG" if rec.tipo == "RG" else "FLG"
    if union == "RG" and u != "RG":
        avisos.append(_tr("La junta mecánica (RG) llega hasta 16\": va con bridas (FLG)."))
    if rec.estimada:
        avisos.append(_tr("{d}\" no está en la tabla de normas: medidas estimadas (interpoladas).").format(d=f"{n:g}"))
    return rec.bloque, u, rec.largo, rec.od_extremo, avisos


def material_de(elegido, material_tuberia):
    """El material de la válvula: el elegido o, sin elegir, el que sugiere la tubería (DI-A si no dice)."""
    if elegido in MATERIALES:
        return elegido
    m = (material_tuberia or "").upper()
    if "PVC" in m or "C900" in m or "C905" in m:
        return "PVC"
    if "CAST" in m or m.startswith("CI") or " CI" in m or "FUNDIDO" in m:
        return "CI"
    return "DI-A"


@dataclass
class Lugar:
    """Dónde queda (o por qué no) una válvula."""
    ok: bool = False
    motivo: str = ""
    pipe: int = -1
    tramo: int = -1
    x: float = 0.0
    y: float = 0.0
    ux: float = 1.0                # dirección del tramo (px del lienzo, unitaria)
    uy: float = 0.0
    diam_in: float = 0.0
    bloque: str = ""
    union: str = "FLG"
    material: str = ""
    largo_ft: float = 0.0
    brida_ft: float = 0.0
    movida: bool = False           # se corrió para caber
    estimada: bool = False         # diámetro fuera de la tabla de normas
    avisos: list = field(default_factory=list)


def es_presion(p):
    return network_kind(p.get("layer") or "") == "pressure"


def _dist_seg(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
    return math.hypot(x - (a[0] + u * dx), y - (a[1] + u * dy))


def _cruce(a, b, c, d):
    """Parámetros (t, u) del cruce de a–b con c–d dentro de los dos tramos, o None."""
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < EPS:
        return None
    q = (c[0] - a[0], c[1] - a[1])
    t = (q[0] * s[1] - q[1] * s[0]) / den
    u = (q[0] * r[1] - q[1] * r[0]) / den
    return (t, u) if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS else None


def _giro(pts, k):
    """Deflexión (°) en el vértice interior k."""
    a, c, b = pts[k - 1], pts[k], pts[k + 1]
    u = (c[0] - a[0], c[1] - a[1]); w = (b[0] - c[0], b[1] - c[1])
    nu, nw = math.hypot(*u), math.hypot(*w)
    if nu < EPS or nw < EPS:
        return 0.0
    cs = max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))
    return math.degrees(math.acos(cs))


def _otras_tocan(pipes, i, q, tol, cerca):
    """¿Otra utilidad (cualquier capa) pasa o termina en q? (ahí va un accesorio o una unión)."""
    for j in cerca(q[0], q[1], tol):
        if j == i:
            continue
        pts = pipes[j].get("pts") or ()
        for a, b in zip(pts, pts[1:]):
            if _dist_seg(q[0], q[1], a, b) <= tol:
                return True
    return False


def _tramo_libre(pipes, structures, i, k, ft, otras_valvulas, cerca, diam_in):
    """(a, b, lo, hi, prohibidos) del tramo recto k de la utilidad i: a/b = sus puntas, [lo, hi] = dónde puede
    ir el CENTRO de una válvula medido desde a (ft, sin el largo de la válvula), prohibidos = [(s, medio)] de lo
    que hay en medio (otras utilidades que llegan o cruzan, otras válvulas)."""
    p = pipes[i]
    pts = p["pts"]
    cv, geos = limpieza_tramos.curvas(pipes, structures, i, ft)
    _k, a, b = limpieza_tramos.rectos(pts, geos)[k]
    L = math.hypot(b[0] - a[0], b[1] - a[1]) * ft
    alcance = ALCANCE_ACC_D * diam_in / 12.0
    tol = TOL_UNION_FT / ft
    n = len(pts)

    def margen(v, en_curva):
        if en_curva:                                   # tangencia de una curva: solo tubo libre
            return TUBO_MIN_FT
        hay_acc = (0 < v < n - 1 and _giro(pts, v) > GIRO_CODO_MIN_DEG) or _otras_tocan(pipes, i, pts[v], tol, cerca)
        return (alcance if hay_acc else 0.0) + TUBO_MIN_FT

    lo = margen(k, k in geos)
    hi = L - margen(k + 1, (k + 1) in geos)
    prohibidos = []
    if L > EPS:
        ux, uy = (b[0] - a[0]) / (L / ft), (b[1] - a[1]) / (L / ft)
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        red = red_de(p)
        for j in cerca(cx, cy, L / ft / 2 + tol):
            if j == i:
                continue
            q = pipes[j]
            qp = q.get("pts") or ()
            for v in qp:                               # otra utilidad que llega a este tramo: Tee/Wye
                if _dist_seg(v[0], v[1], a, b) <= tol:
                    s = ((v[0] - a[0]) * ux + (v[1] - a[1]) * uy) * ft
                    prohibidos.append((s, alcance + TUBO_MIN_FT))
            if es_presion(q) and red_de(q) == red:     # cruce en X de la misma red: cruz
                for c, d in zip(qp, qp[1:]):
                    tu = _cruce(a, b, c, d)
                    if tu is not None:
                        prohibidos.append((tu[0] * L, alcance + TUBO_MIN_FT))
        for o in otras_valvulas:                       # otra válvula en el mismo tramo
            if _dist_seg(o["x"], o["y"], a, b) <= tol:
                s = ((o["x"] - a[0]) * ux + (o["y"] - a[1]) * uy) * ft
                prohibidos.append((s, o["largo_ft"] / 2 + TUBO_MIN_FT))
    return a, b, L, lo, hi, prohibidos


def _intervalos(lo, hi, prohibidos, medio):
    """Tramos [i, f] (ft desde la punta a) donde puede ir el centro de una válvula de medio largo `medio`."""
    libres = [(lo + medio, hi - medio)]
    for s, m in prohibidos:
        r0, r1 = s - m - medio, s + m + medio
        nuevos = []
        for i0, i1 in libres:
            if r1 <= i0 or r0 >= i1:
                nuevos.append((i0, i1))
                continue
            if r0 > i0:
                nuevos.append((i0, r0))
            if r1 < i1:
                nuevos.append((r1, i1))
        libres = nuevos
    return [(i0, i1) for i0, i1 in libres if i1 >= i0 - EPS]


def _todas(pipes):
    return lambda _x, _y, _r: range(len(pipes))


def ubicar(pipes, structures, x, y, ft, radio_px, union="FLG", material="", otras=(), libre=True, cerca=None):
    """Dónde queda una válvula con el clic (o el centro guardado) en (x, y). `ft` = pies por px del lienzo,
    `radio_px` = cuánto se busca la tubería, `otras` = las demás válvulas YA ubicadas ({"x", "y", "largo_ft"}),
    `libre` = puede correrse a lo largo del tramo para caber (al poner); sin `libre` (una guardada) solo vale
    donde está. `cerca(x, y, r)` = índices de utilidades con un tramo a ≤ r (por defecto todas)."""
    cerca = cerca or _todas(pipes)
    if not ft or ft <= 0:
        return Lugar(motivo=_tr("Falta la escala de la hoja."))
    mejor = None                                       # (dist, i, k) de presión
    otra = None                                        # la más cercana que no es de presión (para el motivo)
    for i in cerca(x, y, radio_px):
        p = pipes[i]
        pts = p.get("pts") or ()
        if len(pts) < 2:
            continue
        for k in range(len(pts) - 1):
            d = _dist_seg(x, y, pts[k], pts[k + 1])
            if d > radio_px:
                continue
            if es_presion(p):
                if mejor is None or d < mejor[0]:
                    mejor = (d, i, k)
            elif otra is None or d < otra[0]:
                otra = (d, i)
    if mejor is None:
        if otra is not None:
            return Lugar(motivo=_tr("{u} no es de agua ni de gas: las válvulas van en redes a presión.").format(
                u=model_ops.nombre_por_defecto(pipes[otra[1]], otra[1])))
        return Lugar(motivo=_tr("Acércate a una tubería de agua o gas: la válvula se pone sobre ella."))
    _d, i, k = mejor
    p = pipes[i]
    nombre = model_ops.nombre_por_defecto(p, i)
    d_in = model_ops.diametro(p)[0]
    n = diametro_valido(d_in)
    if n is None:
        return Lugar(pipe=i, tramo=k, motivo=_tr(
            "{u} es de {d}\": hay válvulas de {a}\" a {b}\".").format(
            u=nombre, d=f"{d_in:g}", a=f"{VR.N_MIN:g}", b=f"{VR.N_MAX:g}"))
    bloque, u_ef, largo_in, od_in, avisos = pieza(n, union)
    largo_ft = largo_in / 12.0
    lug = Lugar(pipe=i, tramo=k, diam_in=float(n), bloque=bloque, union=u_ef,
                material=material_de(material, p.get("material")), largo_ft=largo_ft, brida_ft=od_in / 12.0,
                avisos=avisos, estimada=n not in VR.TABLA)
    pts = p["pts"]
    try:
        a, b, L, lo, hi, prohibidos = _tramo_libre(pipes, structures, i, k, ft, otras, cerca, n)
    except (IndexError, KeyError):
        lug.motivo = _tr("No se pudo leer el tramo de {u}.").format(u=nombre)
        return lug
    if L <= EPS or ((b[0] - a[0]) * (pts[k + 1][0] - pts[k][0]) + (b[1] - a[1]) * (pts[k + 1][1] - pts[k][1])) <= 0:
        lug.motivo = _tr("Ahí {u} va en curva: la válvula va solo en un tramo recto.").format(u=nombre)
        return lug
    ux, uy = (b[0] - a[0]) / (L / ft), (b[1] - a[1]) / (L / ft)
    lug.ux, lug.uy = ux, uy
    s0 = ((x - a[0]) * ux + (y - a[1]) * uy) * ft      # el clic, en ft desde la punta a del tramo recto
    libres = _intervalos(lo, hi, prohibidos, largo_ft / 2)
    if not libres:
        necesita = largo_ft + (L - (hi - lo))
        lug.motivo = _tr("El tramo recto de {u} mide {L} ft: la válvula de {d}\" necesita {n} ft "
                         "(su largo y el espacio para el codo, la T o la curva de cada lado).").format(
            u=nombre, L=f"{L:.1f}", d=f"{n:g}", n=f"{necesita:.1f}")
        return lug
    if not libre:
        sobre = _dist_seg(x, y, a, b) * ft <= SOBRE_TOL_FT
        dentro = any(i0 - SOBRE_TOL_FT <= s0 <= i1 + SOBRE_TOL_FT for i0, i1 in libres)
        if not sobre or not dentro:
            lug.motivo = _tr("La válvula ya no cabe aquí: {u} cambió (codo, curva, T o el tramo). "
                             "Quítala y vuelve a ponerla.").format(u=nombre)
            return lug
        s = s0                                         # donde está (pie sobre el tramo)
    else:
        s = min((min(max(s0, i0), i1) for i0, i1 in libres), key=lambda v: abs(v - s0))
        lug.movida = abs(s - s0) > SOBRE_TOL_FT
    lug.x, lug.y = a[0] + ux * s / ft, a[1] + uy * s / ft
    lug.ok = True
    return lug


def ubicar_todas(pipes, structures, valvulas, ft, cerca=None):
    """[Lugar] de cada válvula guardada, en orden (cada una con las anteriores ya ubicadas como obstáculo)."""
    tol = TOL_UNION_FT / ft if ft else 3.0
    out, ya = [], []
    for v in valvulas or ():
        lug = ubicar(pipes, structures, float(v["x"]), float(v["y"]), ft, tol, v.get("union") or "FLG",
                     v.get("material") or "", ya, libre=False, cerca=cerca)
        out.append(lug)
        if lug.ok:
            ya.append({"x": lug.x, "y": lug.y, "largo_ft": lug.largo_ft})
    return out


def en(valvulas, lugares, x, y, tol):
    """Índice de la válvula a ≤ tol de (x, y) (o -1)."""
    mejor = (-1, tol)
    for idx, v in enumerate(valvulas or ()):
        lug = lugares[idx] if lugares and idx < len(lugares) else None
        px, py = (lug.x, lug.y) if lug is not None and lug.ok else (float(v["x"]), float(v["y"]))
        d = math.hypot(px - x, py - y)
        if d <= mejor[1]:
            mejor = (idx, d)
    return mejor[0]


def de_lugar(lug, union="FLG", material="", utilidad="", tipo=""):
    """La válvula que pone el usuario en un `Lugar` válido (origen «manual», segura)."""
    v = nueva(lug.x, lug.y, utilidad=utilidad, tipo=tipo, origen=MANUAL, certeza=SEGURA)
    v["union"] = union if union in UNIONES else "FLG"
    v["material"] = material if material in MATERIALES else ""
    return v


def exportable(v, lug):
    """¿Va al DXF (y al plugin)? Solo si cabe en su tramo recto y no está «por confirmar»."""
    return bool(lug is not None and lug.ok and (v.get("certeza") or SEGURA) != POR_CONFIRMAR)


def pegar(v, pipes, tol_px, cerca=None):
    """Una válvula RECONOCIDA sobre el eje de su tubería (el pie más cercano a ≤ `tol_px`, de su utilidad si la
    sabe): el símbolo del plano puede quedar unos puntos al lado (topografía vs. diseño). Guarda dónde estaba
    (`x_pdf`, `y_pdf`). Sin tubería, queda donde está (y se verá «por revisar»)."""
    indices = range(len(pipes)) if cerca is None else cerca(v["x"], v["y"], tol_px)
    mejor = None
    for i in indices:
        p = pipes[i]
        if v.get("utilidad") and p.get("layer") != v["utilidad"]:
            continue
        pts = p.get("pts") or ()
        for a, b in zip(pts, pts[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((v["x"] - a[0]) * dx + (v["y"] - a[1]) * dy) / L2))
            q = (a[0] + u * dx, a[1] + u * dy)
            d = math.hypot(q[0] - v["x"], q[1] - v["y"])
            if d <= tol_px and (mejor is None or d < mejor[0]):
                mejor = (d, q)
    out = dict(v)
    if mejor is not None:
        out.setdefault("x_pdf", float(v["x"]))
        out.setdefault("y_pdf", float(v["y"]))
        out["x"], out["y"] = float(mejor[1][0]), float(mejor[1][1])
    return out


# ── reconocidas del PDF (dev_santos_v2, 2026-11-05) ─────────────────────────────────────────────────────
CAPA = "VALVULAS"                  # clave en «Capas ▾» (`Main.capas_apagadas`)
SEGURA, POR_CONFIRMAR = "segura", "por_confirmar"
CAPA_PDF, LEYENDA, FORMA, MANUAL = "capa", "leyenda", "forma", "manual"
MISMA_PX = 2.0                     # dos válvulas de la misma utilidad a menos de esto (px) = la misma
EN_LINEA_PT = 1.5                  # sobre una línea cualquiera: a ≤ esto (pt de la hoja)
UNIR_PT = 5.0                      # con su utilidad conocida, su tubería puede estar hasta aquí (topografía vs. diseño)


def tol_pt(v: dict) -> float:
    """Sin utilidad, solo vale una línea encima: más lejos podría ser la de otra red."""
    return UNIR_PT if v.get("utilidad") else EN_LINEA_PT


def nueva(x, y, utilidad="", tipo="", estado="", origen=CAPA_PDF, certeza=SEGURA, capa_pdf="") -> dict:
    """Una válvula con todos sus datos (las del plano: `recognition_valvulas`; las del usuario: `de_lugar`)."""
    return dict(x=float(x), y=float(y), union="FLG", material="", utilidad=utilidad or "", tipo=tipo or "",
                estado=estado or "", origen=origen, certeza=certeza, capa_pdf=capa_pdf or "")


def juntar(existentes: Sequence[dict], nuevas: Sequence[dict]) -> List[dict]:
    """Las de antes + las nuevas que no estaban. Reimportar la misma hoja no las repite."""
    out = list(existentes)
    for v in nuevas:
        if not any(a.get("utilidad") == v.get("utilidad")
                   and math.hypot(a["x"] - v["x"], a["y"] - v["y"]) <= MISMA_PX for a in out):
            out.append(v)
    return out


def _pie(x, y, a, b) -> Tuple[float, float]:
    """(distancia al tramo a–b, rumbo del tramo en grados 0–180, con la y hacia arriba)."""
    ax, ay = a[0], a[1]
    dx, dy = b[0] - ax, b[1] - ay
    largo2 = dx * dx + dy * dy
    t = 0.0 if not largo2 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / largo2))
    return math.hypot(x - ax - t * dx, y - ay - t * dy), math.degrees(math.atan2(-dy, dx)) % 180.0


def mas_cercana(x, y, candidatas, tol, utilidad="") -> Optional[Tuple[int, float, float]]:
    """(índice, distancia, rumbo) de la línea más cercana a ≤ tol. `candidatas` = [(índice, capa, puntos)]; con
    `utilidad`, solo las de esa capa."""
    mejor = None
    for i, capa, pts in candidatas:
        if utilidad and capa != utilidad:
            continue
        for a, b in zip(pts, pts[1:]):
            d, rumbo = _pie(x, y, a, b)
            if d <= tol and (mejor is None or d < mejor[1]):
                mejor = (i, d, rumbo)
    return mejor


def relacion(v: dict, pipes: Sequence[dict], tol_px: float, cerca=None) -> Optional[Tuple[int, float, float]]:
    """La tubería de la válvula: (índice, distancia px, rumbo). `cerca(x, y, r)` = índices a revisar (índice de la
    ventana); sin él, todas."""
    indices = range(len(pipes)) if cerca is None else cerca(v["x"], v["y"], tol_px)
    return mas_cercana(v["x"], v["y"], [(i, pipes[i].get("layer"), pipes[i].get("pts") or ()) for i in indices],
                       tol_px, v.get("utilidad") or "")


N_ = lambda s: s          # noqa: E731  (marca para la traducción; los valores son datos)
TEXTOS = (N_("Válvula"), N_("De línea"), N_("Purga"), N_("Retención"), N_("Retención doble"),
          N_("Reguladora de presión"), N_("Mariposa"), N_("Aire"), N_("Compuerta"), N_("Riego"), N_("abierta"),
          N_("cerrada"))


def nombre(v: dict) -> str:
    """Tipo legible en español (el dato; la interfaz lo traduce con `t()`)."""
    return v.get("tipo") or "Válvula"
