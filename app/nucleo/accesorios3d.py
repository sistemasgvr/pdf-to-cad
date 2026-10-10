"""Accesorios de presión en 3D como los construye el plugin (`WyeSolido.cs`) (PURO).

Espejo de WyeSolido.cs (mismas constantes y reglas; `tests/test_vista3d.py` compara
las constantes con el .cs):

  • Tee / Wye / cruz: un BRAZO por tubo que llega = cuerpo del diámetro del tubo
    (Wye 1.25·D, Tee y cruz 0.75·D; el tronco de la Wye 0.03 ft más grueso) +
    CAMPANA en la punta (Ø + holgura + pared, 0.45·D de largo, montada 0.10·D sobre
    el cuerpo). Rígidas en Z (`aplanar`): centro a la altura del eje del tubo más
    grueso, brazos horizontales. Si una campana quedaría dentro de otro brazo o
    chocaría con otra campana, se alarga el brazo (`sacar_campanas`, `separar`).
  • Codo: cuerpo CURVO (recta → arco tangente de radio 1·D, con tope de tangencia
    0.85·D y radio mínimo viable en codos cerrados → recta, `curva_codo`) + una
    campana en cada extremo. No se aplana: sigue la pendiente de los tubos.
  • Cada tubo muere DENTRO de su campana (`alcance`): lo que se recorta en 3D.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from nucleo import mallas3d as M

# Espejo de WyeSolido.cs (nombres iguales).
LARGO_BRAZO_D = 1.25
LARGO_BRAZO_TEE_D = 0.75
LARGO_CAMPANA_D = 0.45
HOLGURA_FT = 0.02
PARED_FT = 0.04
MONTAJE_CAMPANA_D = 0.10
CALADO_EN_CAMPANA = 0.75
SOLAPE_EXTRA_FT = 0.12
RADIO_CURVA_D = 1.0
COLLAR_CODO_D = 0.12
TANGENCIA_MAX_D = 0.85
RADIO_CURVA_MIN_D = 1.0
GIRO_CERRADO_DEG = 135.0
ANG_EJES_MIN_DEG = 2.0
SEPARACION_MIN_FT = 0.10
PENDIENTE_VERTICAL_DEG = 60.0
ENGROSE_TRONCO_Y_FT = 0.03

LADOS = 16
TIPO_PLUGIN = {"codo": "CODO", "tee": "TEE", "wye": "WYE", "cruz": "CROSS"}


@dataclass
class Brazo:
    dir: np.ndarray                 # desde el centro hacia el tubo (unitario, pies)
    d: float                        # diámetro (ft)
    pipe: int = -1
    eje_z: float | None = None      # cota del eje de su tubo en la juntura
    largo: float = 0.0
    engrose: float = 0.0
    off_z: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def r_campana(self):
        return self.d / 2.0 + HOLGURA_FT + PARED_FT

    @property
    def alcance(self):
        """Distancia del centro a donde MUERE el tubo (dentro de la campana)."""
        return self.largo + self.d * LARGO_CAMPANA_D * CALADO_EN_CAMPANA - SOLAPE_EXTRA_FT


def _ang(u, v):
    return math.acos(max(-1.0, min(1.0, float(np.dot(u, v)))))


def es_vertical(u):
    h, v = math.hypot(u[0], u[1]), abs(u[2])
    if v < 1e-9:
        return False
    return h < 1e-9 or math.degrees(math.atan2(v, h)) >= PENDIENTE_VERTICAL_DEG


def radio_minimo_viable(d):
    return d / 2.0 + HOLGURA_FT + PARED_FT + SEPARACION_MIN_FT / 2.0


def curva_codo(d, ang):
    """(R, T, cerrado) del codo de diámetro d con `ang` (rad) ENTRE EJES, o None."""
    giro = math.pi - ang
    cerrado = giro > math.radians(GIRO_CERRADO_DEG)
    R = d * RADIO_CURVA_D
    tan_phi = math.tan(ang / 2.0)
    if abs(tan_phi) < 1e-9:
        return None
    T = R / tan_phi
    t_max = d * TANGENCIA_MAX_D
    if T > t_max:
        r_min = radio_minimo_viable(d) if cerrado else d * RADIO_CURVA_MIN_D
        T = max(t_max, r_min / tan_phi)
        R = T * tan_phi
        if R < r_min - 1e-9:
            R = r_min
            T = R / tan_phi
    return R, T, cerrado


def aplanar(centro, brazos, tipo):
    """Largo base de cada brazo y, en Tee/Wye/cruz, eje Z rígido (`Aplanar`)."""
    factor = LARGO_BRAZO_TEE_D if tipo in ("TEE", "CROSS") else LARGO_BRAZO_D
    rigido = tipo in ("TEE", "WYE", "CROSS")
    for b in brazos:
        if rigido and not es_vertical(b.dir):
            h = np.array([b.dir[0], b.dir[1], 0.0])
            b.dir = h / np.linalg.norm(h) if np.linalg.norm(h) > 1e-9 else b.dir / np.linalg.norm(b.dir)
        else:
            b.dir = b.dir / np.linalg.norm(b.dir)
        if b.largo <= 1e-9:
            b.largo = b.d * factor
    if not rigido:
        return np.asarray(centro, float)
    con_eje = [b for b in brazos if b.eje_z is not None and not es_vertical(b.dir)]
    if not con_eje:
        return np.asarray(centro, float)
    d_max = max(b.d for b in con_eje)
    gruesos = [b.eje_z for b in con_eje if b.d >= d_max - 1e-6]
    z_ref = sum(gruesos) / len(gruesos)
    for b in con_eje:
        limite = max(0.0, (d_max - b.d) / 2.0)
        b.off_z = max(-limite, min(limite, b.eje_z - z_ref))
    return np.array([centro[0], centro[1], z_ref])


def marcar_tronco_y(brazos):
    if len(brazos) < 2 or any(b.engrose > 0 for b in brazos):
        return
    par = max(((a, b) for i, a in enumerate(brazos) for b in brazos[i + 1:]), key=lambda p: _ang(p[0].dir, p[1].dir))
    par[0].engrose = par[1].engrose = ENGROSE_TRONCO_Y_FT


def sacar_campanas(brazos):
    """Ninguna campana dentro del cuerpo de otro brazo (`SacarCampanasDelCuerpo`)."""
    margen = SEPARACION_MIN_FT / 2.0
    for i in brazos:
        monta = i.d * MONTAJE_CAMPANA_D
        requerido = 0.0
        for j in brazos:
            if j is i:
                continue
            th = _ang(i.dir, j.dir)
            if th > math.pi / 2.0 + 1e-9 or math.sin(th) < math.sin(math.radians(5.0)):
                continue
            r_vecino = max(j.d / 2.0 + j.engrose, j.r_campana)
            s0 = (r_vecino + margen + i.r_campana * math.cos(th)) / math.sin(th)
            requerido = max(requerido, s0 + monta)
        if requerido > i.largo + 1e-6:
            i.largo = requerido


def separar(brazos):
    """Campanas que no se tocan entre sí (`SepararBrazos`)."""
    for n, a in enumerate(brazos):
        for b in brazos[n + 1:]:
            cos = math.cos(_ang(a.dir, b.dir))
            minimo = a.r_campana + b.r_campana + SEPARACION_MIN_FT
            ca = a.largo + a.d * LARGO_CAMPANA_D / 2.0
            cb = b.largo + b.d * LARGO_CAMPANA_D / 2.0
            if math.sqrt(max(0.0, ca * ca + cb * cb - 2 * ca * cb * cos)) >= minimo:
                continue
            c = minimo / math.sqrt(max(1e-9, 2.0 - 2.0 * cos))
            la, lb = a.d * LARGO_CAMPANA_D, b.d * LARGO_CAMPANA_D
            esq_a = math.sqrt(a.r_campana ** 2 + (la / 2) ** 2)
            esq_b = math.sqrt(b.r_campana ** 2 + (lb / 2) ** 2)
            c *= (esq_a + esq_b + SEPARACION_MIN_FT) / minimo
            a.largo = max(a.largo, c - la / 2.0)
            b.largo = max(b.largo, c - lb / 2.0)


# ─────────────────────────── mallas ───────────────────────────

def _campana(punta, u, b, color, ident):
    monta = b.d * MONTAJE_CAMPANA_D
    ini = punta - u * monta
    return M.barrido(ini, punta + u * b.d * LARGO_CAMPANA_D, M.perfil_circulo(b.r_campana, LADOS), color, ident)


def malla_brazo(centro, b, color, ident):
    """Cuerpo (Ø del tubo, + engrose en el tronco de una Wye) + campana en la punta."""
    c = np.asarray(centro, float) + np.array([0.0, 0.0, b.off_z])
    fin = c + b.dir * b.largo
    cuerpo = M.barrido(c, fin, M.perfil_circulo(b.d / 2.0 + b.engrose, LADOS), color, ident)
    return M.juntar([cuerpo, _campana(fin, b.dir, b, color, ident)])


def malla_codo(centro, a, b, color, ident, arco=12):
    """Codo curvo: recta → arco tangente → recta + dos campanas. None si es casi recto
    o los ejes van superpuestos (el plugin arma entonces brazos rectos)."""
    dA, dB = a.dir / np.linalg.norm(a.dir), b.dir / np.linalg.norm(b.dir)
    ang = _ang(dA, dB)
    if math.pi - ang < math.radians(2.0) or ang < math.radians(ANG_EJES_MIN_DEG):
        return None
    d = max(a.d, b.d)
    rt = curva_codo(d, ang)
    if rt is None:
        return None
    R, T, _cerrado = rt
    a.largo, b.largo = T + a.d * COLLAR_CODO_D, T + b.d * COLLAR_CODO_D
    c = np.asarray(centro, float)
    pA, pB, tA, tB = c + dA * a.largo, c + dB * b.largo, c + dA * T, c + dB * T
    bis = dA + dB
    bis /= np.linalg.norm(bis)
    C = c + bis * (R / math.sin(ang / 2.0))
    va, vb = tA - C, tB - C
    om = _ang(va / np.linalg.norm(va), vb / np.linalg.norm(vb))
    arc = [tA]
    if om > 1e-6:
        for k in range(1, arco):
            t = k / arco
            arc.append(C + (math.sin((1 - t) * om) * va + math.sin(t * om) * vb) / math.sin(om))
    arc.append(tB)
    camino = [pA] + arc + [pB]
    cuerpo = M.barrido_camino(camino, M.perfil_circulo(d / 2.0, LADOS), color, ident)
    return M.juntar([cuerpo, _campana(pA, dA, a, color, ident), _campana(pB, dB, b, color, ident)])


def pieza(tipo_app, centro, brazos, color, ident):
    """(malla, brazos ya con su largo final) del accesorio, como el plugin."""
    tipo = TIPO_PLUGIN.get(tipo_app, "")
    c = aplanar(centro, brazos, tipo)
    if tipo == "WYE":
        marcar_tronco_y(brazos)
    if tipo in ("WYE", "TEE", "CROSS"):
        sacar_campanas(brazos)
        separar(brazos)
    malla = malla_codo(c, brazos[0], brazos[1], color, ident) if len(brazos) == 2 else None
    if malla is None:
        malla = M.juntar([malla_brazo(c, b, color, ident) for b in brazos])
    return malla, c


# ─────────────────────────── recorte de los tubos ───────────────────────────

def cortar(camino, cortes):
    """Partes del recorrido 3D `camino` que quedan fuera de los accesorios.
    `cortes` = [(punto xy del centro, dirección xy del brazo, alcance ft)]: se quita
    desde el centro hasta `alcance` hacia ese lado (medido en planta)."""
    P = np.asarray(camino, float)
    if not cortes or len(P) < 2:
        return [P]
    seg = np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    quitar = []
    for (cx, cy), (ux, uy), alc in cortes:
        mejor = None
        for k in range(len(P) - 1):
            a, b = P[k, :2], P[k + 1, :2]
            L = seg[k]
            t = 0.0 if L < 1e-9 else max(0.0, min(1.0, float(np.dot((cx, cy) - a, b - a)) / (L * L)))
            q = a + (b - a) * t
            dist = math.hypot(q[0] - cx, q[1] - cy)
            if mejor is None or dist < mejor[0]:
                mejor = (dist, s[k] + L * t, (b - a) / L if L > 1e-9 else np.zeros(2))
        _d, s0, tan = mejor
        if float(np.dot(tan, (ux, uy))) >= 0:
            quitar.append((s0, s0 + alc))
        else:
            quitar.append((s0 - alc, s0))
    quitar.sort()
    partes, ini = [], 0.0
    for a, b in quitar + [(s[-1] + 1.0, s[-1] + 1.0)]:
        fin = min(a, s[-1])
        if fin - ini > 1e-3:
            partes.append(M.subcamino(P, s, ini, fin))
        ini = max(ini, b)
    return partes

