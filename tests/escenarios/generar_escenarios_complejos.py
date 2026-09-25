"""Genera `escenarios_complejos.digproj`: segunda tanda de escenarios, centrada
en los accesorios SÓLIDOS del plugin (codo, Tee, Wye) y en los casos que hoy no
están contemplados.

Complementa a `escenarios_prueba.digproj` (E01–E40) sin repetirlo:
  C01–C26  accesorios sólidos en situaciones difíciles
  F01–F10  casos NO contemplados (lo que pasa hoy y por qué no es lo correcto)

Cada celda lleva escrito qué debería pasar en la app y en Civil 3D; el texto se
exporta al DXF, así que también se lee dentro de Civil 3D. Las cifras de cada
celda (recortes, radios, alargamientos) se calculan con las mismas fórmulas y
constantes que `WyeSolido.cs` (ver «Espejo de WyeSolido.cs» abajo).

Uso:
    python tests/escenarios/generar_escenarios_complejos.py   # regenera el .digproj
    pytest tests/escenarios                                    # valida la parte de la app
"""
import math
import os
import textwrap

import generar_escenarios as base            # también arma sys.path (app/ + raíz)
from generar_escenarios import Lienzo, pol, buscar_hit

SALIDA = os.path.join(base._AQUI, "escenarios_complejos.digproj")

# ARCH D apaisada (36 × 24 in) a 1" = 60' → 2160 × 1440 pies reales: el doble de
# terreno que la primera tanda con la MISMA imagen de fondo (una hoja más grande
# a la misma escala pediría ~330 MB solo de lienzo blanco).
HOJA = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=60.0,
            scale_ft_per_pt=60.0 / 72.0, unit="in", landscape=True)
ANCHO_FT, ALTO_FT = 36 * 60.0, 24 * 60.0
COLS, FILAS = 8, 5
CELDA_X, CELDA_Y = ANCHO_FT / COLS, ALTO_FT / FILAS    # 270 × 288 ft
L = 50.0                     # largo típico de un tramo (ft)
ALTO_TEXTO = 4.0
ANCHO_ETIQUETA = 56          # caracteres por línea de etiqueta


# ─────────────────────────────────────────────────────────────────────────────
#  Espejo de WyeSolido.cs: mismas constantes y fórmulas que el plugin, para
#  escribir en cada celda lo que Civil 3D DEBERÍA hacer con números concretos.
#  test_escenarios_complejos compara estas constantes con las del .cs: si allí
#  cambian, el test falla y hay que regenerar el .digproj.
# ─────────────────────────────────────────────────────────────────────────────
WS = dict(LARGO_BRAZO_D=1.25, LARGO_BRAZO_TEE_D=0.75, LARGO_CAMPANA_D=0.45,
          HOLGURA_FT=0.02, PARED_FT=0.04, CALADO_EN_CAMPANA=0.75, SOLAPE_EXTRA_FT=0.12,
          RADIO_CURVA_D=1.0, COLLAR_CODO_D=0.12, TANGENCIA_MAX_D=0.85,
          RADIO_CURVA_MIN_D=1.0, GIRO_CERRADO_DEG=135.0, ANG_EJES_MIN_DEG=2.0,
          SEPARACION_MIN_FT=0.10, PENDIENTE_VERTICAL_DEG=60.0)


def _alcance(largo, d):
    """Brazo.AlcanceTuboFt: distancia del centro de la pieza a la punta del tubo."""
    return (largo + d * WS["LARGO_CAMPANA_D"] * WS["CALADO_EN_CAMPANA"]
            - WS["SOLAPE_EXTRA_FT"])


def _boca(largo, d):
    """Brazo.BocaFt: distancia del centro de la pieza al borde de la campana."""
    return largo + d * WS["LARGO_CAMPANA_D"]


def _curva_codo(d, ang):
    """CurvaCodo: (R, T, cerrado) para Ø `d` (ft) y `ang` grados entre ejes."""
    cerrado = (180.0 - ang) > WS["GIRO_CERRADO_DEG"]
    R = d * WS["RADIO_CURVA_D"]
    tan_phi = math.tan(math.radians(ang / 2.0))
    T = R / tan_phi
    if T > d * WS["TANGENCIA_MAX_D"]:
        rmin = ((d / 2 + WS["HOLGURA_FT"] + WS["PARED_FT"] + WS["SEPARACION_MIN_FT"] / 2)
                if cerrado else d * WS["RADIO_CURVA_MIN_D"])
        T = max(d * WS["TANGENCIA_MAX_D"], rmin / tan_phi)
        R = T * tan_phi
        if R < rmin - 1e-9:
            R = rmin
            T = R / tan_phi
    return R, T, cerrado


def codo(d_in, defl):
    """Qué sale en un quiebre de `defl`° entre dos tubos del mismo Ø (pulgadas).

    Replica DecidirTipoFitting (≤1° → Coupling, sin sólido) y ConstruirCodo
    (giro <2° o ejes <2° → dos brazos rectos de 1.25·D; si no, curva).
    """
    d = d_in / 12.0
    if defl <= 1.0:
        return dict(tipo="coupling")
    ang = 180.0 - defl
    if defl < 2.0 or ang < WS["ANG_EJES_MIN_DEG"]:
        largo = d * WS["LARGO_BRAZO_D"]
        return dict(tipo="manguito" if defl < 2.0 else "superpuesto",
                    largo=largo, alcance=_alcance(largo, d), boca=_boca(largo, d))
    R, T, cerrado = _curva_codo(d, ang)
    largo = T + d * WS["COLLAR_CODO_D"]
    return dict(tipo="cerrado" if cerrado else "codo", R=R, T=T, largo=largo,
                alcance=_alcance(largo, d), boca=_boca(largo, d))


def brazos(tipo, rumbos_deg, diams_in):
    """Brazos de una TEE/WYE tras Aplanar (+ SepararBrazos si es WYE).

    El orden debe ser el de los miembros de la juntura en el plugin: tramo que
    llega, tramo que sale y ramal (así se crean los tubos en el import).
    """
    f = WS["LARGO_BRAZO_TEE_D"] if tipo == "TEE" else WS["LARGO_BRAZO_D"]
    bs = []
    for r, d_in in zip(rumbos_deg, diams_in):
        d = d_in / 12.0
        a = math.radians(r)
        bs.append(dict(u=(math.cos(a), math.sin(a)), d=d, largo=d * f))
    if tipo == "WYE":
        _separar(bs)
    for b in bs:
        b["alcance"] = _alcance(b["largo"], b["d"])
        b["boca"] = _boca(b["largo"], b["d"])
    return bs


def _separar(bs):
    """SepararBrazos: alarga los pares cuyas campanas chocan (ley del coseno)."""
    for i in range(len(bs)):
        for k in range(i + 1, len(bs)):
            a, b = bs[i], bs[k]
            cos = max(-1.0, min(1.0, a["u"][0] * b["u"][0] + a["u"][1] * b["u"][1]))
            rA = a["d"] / 2 + WS["HOLGURA_FT"] + WS["PARED_FT"]
            rB = b["d"] / 2 + WS["HOLGURA_FT"] + WS["PARED_FT"]
            minimo = rA + rB + WS["SEPARACION_MIN_FT"]
            cA = a["largo"] + a["d"] * WS["LARGO_CAMPANA_D"] / 2
            cB = b["largo"] + b["d"] * WS["LARGO_CAMPANA_D"] / 2
            dist = math.sqrt(max(0.0, cA * cA + cB * cB - 2 * cA * cB * cos))
            if dist >= minimo:
                continue
            c_nec = minimo / math.sqrt(max(1e-9, 2.0 - 2.0 * cos))
            lA, lB = a["d"] * WS["LARGO_CAMPANA_D"], b["d"] * WS["LARGO_CAMPANA_D"]
            esqA = math.hypot(rA, lA / 2)
            esqB = math.hypot(rB, lB / 2)
            c_nec *= (esqA + esqB + WS["SEPARACION_MIN_FT"]) / minimo
            a["largo"] = max(a["largo"], c_nec - lA / 2)
            b["largo"] = max(b["largo"], c_nec - lB / 2)


def _eje(solera, d_in):
    """Cota del EJE de un tubo de presión (el plugin convierte solera → eje)."""
    return solera + d_in / 24.0


def _ang3(u, v):
    dot = sum(a * b for a, b in zip(u, v))
    nu = math.sqrt(sum(a * a for a in u)); nv = math.sqrt(sum(b * b for b in v))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (nu * nv)))))


def _ft(x):
    return f"{x:g}"


# ─────────────────────────────────────────────────────────────────────────────
#  Utilidades de dibujo
# ─────────────────────────────────────────────────────────────────────────────
def _tronco_y_ramal(lz, P, ang, d_tronco=12.0, d_ramal=12.0, inv=-4.0, largo_ramal=L, **extra):
    """Tronco recto oeste→este con vértice en P + ramal que nace en P a `ang`°."""
    t = lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], d_tronco, (inv, inv))
    r = lz.tubo("AGUA", [P, pol(P, ang, largo_ramal)], d_ramal, (inv, inv), **extra)
    return t, r


def _cruce(lz, P, inv_a, inv_b, d_a=12.0, d_b=12.0, rumbo_b=90.0):
    """Dos AGUA que se cruzan en P (a: oeste→este, b: a `rumbo_b`°)."""
    a = lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], d_a, (inv_a, inv_a))
    b = lz.tubo("AGUA", [pol(P, rumbo_b + 180, L), pol(P, rumbo_b, L)], d_b, (inv_b, inv_b))
    return a, b


# ─────────────────────────────────────────────────────────────────────────────
#  CASOS. Cada función dibuja con centro P y devuelve:
#    titulo, app (texto), c3d (texto), nc (texto de «no contemplado» o None) y
#    lo que valida la parte de la app:
#      marcas:  [(punto, estado[, (tubo_a, tubo_b)])] marcador esperado ahí
#               ("conflicto" | "sugerencia" | "aprobado" | None = ninguno)
#      aprobar: [(punto, tubo_a, tubo_b)] conexión vertical a aprobar
#      cuenta:  [(punto, n)] cuántos marcadores deben apilarse en ese punto
# ─────────────────────────────────────────────────────────────────────────────

# ── Codos ────────────────────────────────────────────────────────────────────
def c01(lz, P):
    tramos = [8.0, 5.0, 3.0, 2.7, 2.3]
    q = (P[0] - 40, P[1] - 15)
    pts = [(q[0] - 50, q[1]), q]
    rumbo = 90.0
    for t in tramos:
        q = pol(q, rumbo, t)
        pts.append(q)
        rumbo = 0.0 if rumbo == 90.0 else 90.0
    pts.append(pol(q, rumbo, 40))
    lz.tubo("AGUA", pts, 12, (-4, -4))
    c = codo(12, 90)
    minimo = 2 * c["alcance"] + 0.05
    ok = [t for t in tramos if t > minimo]
    cortos = [t for t in tramos if t <= minimo]
    solapan = [t for t in tramos if t < 2 * c["boca"]]
    return dict(
        titulo="Serpentín Ø12: 6 codos de 90° con tramos de 8/5/3/2.7/2.3 ft",
        app="sin marcadores",
        c3d=(f"6 ELBOW 90° (cada uno recorta {c['alcance']:.2f} ft). Tramos de "
             f"{'/'.join(_ft(t) for t in ok)} ft OK; en {'/'.join(_ft(t) for t in cortos)} ft "
             f"el 2.º codo avisa «Tubo … demasiado corto» (hacen falta >{minimo:.2f} ft)."),
        nc=(f"Codos vecinos se SOLAPAN sin aviso en tramos < {2 * c['boca']:.2f} ft "
            f"({'/'.join(_ft(t) for t in solapan)} ft)."),
        marcas=[])


def _codo_en_v(lz, P, rumbo_salida):
    """Utilidad oeste→P→`rumbo_salida` con punto bajo en P (-4 → -8 → -4)."""
    fin = pol(P, rumbo_salida, L)
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, fin], 12, (-4, -4),
            vertex_inv_in={1: -8.0}, vertex_inv_out={1: -8.0}, seg_edit_enabled=True)
    dA = (-L, 0.0, 4.0)
    dB = (fin[0] - P[0], fin[1] - P[1], 4.0)
    defl = 180.0 - _ang3(dA, dB)
    n = (dA[1] * dB[2] - dA[2] * dB[1], dA[2] * dB[0] - dA[0] * dB[2],
         dA[0] * dB[1] - dA[1] * dB[0])
    incl = _ang3(n, (0.0, 0.0, 1.0))
    return defl, min(incl, 180.0 - incl)


def c02(lz, P):
    defl, incl = _codo_en_v(lz, P, 60)
    return dict(
        titulo="Codo 3D: giro de 60° en planta + punto bajo (-4 → -8 → -4)",
        app="sin marcadores",
        c3d=(f"ELBOW de {defl:.1f}° (medido en 3D) en un plano inclinado {incl:.0f}° "
             "respecto a la horizontal; la curva debe empalmar con los DOS tubos inclinados."),
        nc=None, marcas=[])


def c03(lz, P):
    defl, _incl = _codo_en_v(lz, P, 0)
    return dict(
        titulo="Codo vertical: recto en planta, punto bajo (-4 → -8 → -4)",
        app="sin marcadores",
        c3d=f"ELBOW de {defl:.1f}° en un plano VERTICAL (sifón), no rígido en Z.",
        nc=None, marcas=[])


def c04(lz, P):
    for Q, defl in (((P[0], P[1] + 45), 0.5), ((P[0], P[1] - 45), 1.5)):
        lz.tubo("AGUA", [(Q[0] - L, Q[1]), Q, pol(Q, defl, L)], 12, (-4, -4))
    m = codo(12, 1.5)
    return dict(
        titulo="Casi recto: quiebre de 0.5° (arriba) y de 1.5° (abajo)",
        app="sin marcadores",
        c3d=("Arriba (≤1°): Coupling de catálogo o unión directa, sin sólido. Abajo (1–2°): "
             f"no se curva → «manguito» RECTO de {2 * m['boca']:.2f} ft (2 brazos de 1.25·D) "
             f"y tubos recortados {m['alcance']:.2f} ft."),
        nc="Entre 1° y 2° de deflexión sale un manguito de 3.4·D que no existe en obra.",
        marcas=[])


def c05(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, pol(P, 179, 40)], 12, (-4, -4))
    m = codo(12, 179)
    return dict(
        titulo="Retorno de 179°: la línea vuelve casi sobre sí misma",
        app="sin marcadores",
        c3d=("Aviso «Los dos tubos van casi superpuestos (1.0° entre ejes)»: se arma un "
             f"manguito recto y cada tubo se recorta {m['alcance']:.2f} ft; los dos tramos "
             "quedan a <1 ft uno del otro (se pisan)."),
        nc="Un retorno así es casi seguro un error de trazado y hoy se genera pieza igual.",
        marcas=[])


def c06(lz, P):
    lz.tubo("AGUA", [(P[0] - 4, P[1]), P, (P[0], P[1] + 4)], 48, (-6, -6))
    c = codo(48, 90)
    return dict(
        titulo="Codo 90° Ø48 con tramos de solo 4 ft",
        app="sin marcadores",
        c3d=(f"ELBOW 90° Ø48 (R={c['R']:.2f} ft) necesita recortar {c['alcance']:.2f} ft por "
             "lado → «Tubo de 4.00 ft demasiado corto» ×2; la pieza "
             f"({c['boca']:.2f} ft por brazo) queda más larga que los tubos."),
        nc=None, marcas=[])


def c07(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, pol(P, 45, L)], 12, (-4.0, -10.0),
            vertex_inv_in={1: -4.0}, vertex_inv_out={1: -10.0}, seg_edit_enabled=True)
    return dict(
        titulo="Escalón de 6 ft en el propio vértice de un codo (-4 / -10)",
        app="sin marcadores",
        c3d=("«[COTAS] cotas unificadas a -7.00 ft» (promedio de -4 y -10) + ELBOW 45°: "
             "el escalón desaparece y los dos tramos quedan inclinados."),
        nc="Un salto de cota en el vértice (caída) debería ser una vertical con 2 codos, no un promedio.",
        marcas=[])


# ── Wye ──────────────────────────────────────────────────────────────────────
def c08(lz, P):
    _tronco_y_ramal(lz, P, 8.0)
    bs = brazos("WYE", [180, 0, 8], [12, 12, 12])
    return dict(
        titulo="Y rasante: ramal a solo 8° del tronco",
        app="conflicto (misma cota)",
        c3d=(f"WYE: las campanas del tramo este y del ramal chocan → ambos brazos se alargan "
             f"de 1.25 a {bs[1]['largo']:.2f} ft (aviso «Campanas … separadas») y sus tubos "
             f"se recortan {bs[1]['alcance']:.2f} ft."),
        nc=(f"Brazos de {bs[1]['boca']:.1f} ft que se comen {bs[1]['alcance']:.1f} ft de "
            "tubería: falta un ángulo mínimo de Y o un aviso."),
        marcas=[(P, "conflicto")])


def c09(lz, P):
    diams = (18, 12, 8)
    lz.tubo("AGUA", [(P[0] - L, P[1]), P], diams[0], (-4, -4))
    lz.tubo("AGUA", [P, (P[0] + L, P[1])], diams[1], (-4, -4))
    lz.tubo("AGUA", [P, pol(P, 45, L)], diams[2], (-4, -4))
    ejes = [_eje(-4.0, d) for d in diams]
    zc = sum(ejes) / 3.0
    desv = "/".join(f"{z - zc:+.2f}" for z in ejes)
    return dict(
        titulo="Y reductora de 3 diámetros: Ø18 entra, Ø12 sale, ramal Ø8 a 45° (misma solera)",
        app="conflicto (misma cota)",
        c3d=(f"WYE sólida Ø18/12/8 asentada en el eje MEDIO (z={zc:.2f}): los ejes de los "
             f"tubos quedan a {desv} ft de la pieza, con solo 0.02 ft de holgura de campana."),
        nc="Con solera común cada brazo debería ir a la altura de SU tubo (pieza excéntrica).",
        marcas=[(P, "conflicto")])


def c10(lz, P):
    lz.tubo("AGUA", [pol(P, 195, L), P, pol(P, 345, L)], 12, (-4, -4))
    lz.tubo("AGUA", [P, pol(P, 90, L)], 12, (-4, -4))
    return dict(
        titulo="Y con tronco quebrado 30° y ramal a 90°",
        app="conflicto (misma cota)",
        c3d=("WYE, no TEE: el tronco se quiebra 30° (más que la tolerancia de 20° del Tee); "
             "salidas a 150°/105°/105°, sin choque de campanas; XDATA ramal 90°."),
        nc="Es una forma que no existe en catálogo: en obra sería Tee + codo de 30°.",
        marcas=[(P, "conflicto")])


def c11(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [P, pol(P, 45, L)], 12, (-3, -3))
    return dict(
        titulo="Y cuyo ramal llega 1 ft más alto que el tronco",
        app="sugerencia (cotas distintas)",
        c3d=("«[COTAS] … se tocan en planta pero a DISTINTA cota — NO se unen»: el tronco "
             "sigue recto (Coupling o unión directa) y el ramal queda suelto, sin pieza."),
        nc=None, marcas=[(P, "sugerencia")])


def c12(lz, P):
    sep = 3.0
    P1, P2 = (P[0] - sep / 2, P[1]), (P[0] + sep / 2, P[1])
    lz.tubo("AGUA", [(P1[0] - L, P[1]), P1, P2, (P2[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [P1, pol(P1, 45, L)], 12, (-4, -4))
    lz.tubo("AGUA", [P2, pol(P2, 315, L)], 12, (-4, -4))
    y1 = brazos("WYE", [180, 0, 45], [12, 12, 12])
    y2 = brazos("WYE", [180, 0, 315], [12, 12, 12])
    a1, a2 = y1[1]["alcance"], y2[0]["alcance"]
    resto = sep - a1
    solape = y1[1]["boca"] + y2[0]["boca"] - sep
    return dict(
        titulo="Dos Y seguidas separadas 3 ft (ramales a 45° y -45°)",
        app="conflicto en las dos Y",
        c3d=(f"2 WYE (campanas a 45° alargadas a {y1[1]['largo']:.2f} ft). En el tramo de 3 ft "
             f"la 1.ª recorta {a1:.2f} ft y la 2.ª avisa «Tubo de {resto:.2f} ft demasiado "
             f"corto para recortar {a2:.2f} ft»."),
        nc=f"Las dos piezas se solapan {solape:.2f} ft sin aviso.",
        marcas=[(P1, "conflicto"), (P2, "conflicto")])


def c13(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-2.0, -12.0))
    lz.tubo("AGUA", [P, pol(P, 45, L)], 12, (-7.0, -7.0))
    bs = brazos("WYE", [180, 0, 45], [12, 12, 12])
    pend = 10.0 / (2 * L)
    return dict(
        titulo="Y sobre un tronco con 10 % de pendiente (-2 → -7 → -12)",
        app="conflicto (misma cota)",
        c3d=("WYE rígida: los brazos del tronco salen HORIZONTALES aunque el tronco baja al "
             f"10 % → en las bocas el tubo queda {bs[0]['boca'] * pend:.2f}–"
             f"{bs[1]['boca'] * pend:.2f} ft fuera del eje de la pieza (holgura 0.02 ft)."),
        nc="La pieza rígida debería inclinarse ENTERA con el tronco, no aplanar sus brazos.",
        marcas=[(P, "conflicto")])


# ── Tee ──────────────────────────────────────────────────────────────────────
def c14(lz, P):
    arriba, abajo = (P[0], P[1] + 50), (P[0], P[1] - 50)
    for Q, quiebre in ((arriba, 19.0), (abajo, 21.0)):
        lz.tubo("AGUA", [pol(Q, 180, L), Q, pol(Q, quiebre, L)], 12, (-4, -4))
        lz.tubo("AGUA", [Q, pol(Q, 270, 40)], 12, (-4, -4))
    return dict(
        titulo="Umbral Tee/Y por colinealidad: tronco quebrado 19° (arriba) y 21° (abajo)",
        app="conflicto en las dos",
        c3d=("Arriba (salidas del tronco a 161°) → TEE. Abajo (159°) → WYE. El corte está en "
             "160°; la TEE de arriba sale con el tronco quebrado 19°."),
        nc=None, marcas=[(arriba, "conflicto"), (abajo, "conflicto")])


def c15(lz, P):
    _tronco_y_ramal(lz, P, 90, 36, 4)
    ejes = [_eje(-4.0, 36), _eje(-4.0, 36), _eje(-4.0, 4)]
    zc = sum(ejes) / 3.0
    bs = brazos("TEE", [180, 0, 90], [36, 36, 4])
    return dict(
        titulo="Tee reductora extrema: tronco Ø36, ramal Ø4 (misma solera)",
        app="conflicto (misma cota)",
        c3d=(f"TEE en z={zc:.2f} (eje medio): tronco {ejes[0] - zc:+.2f} ft y ramal "
             f"{ejes[2] - zc:+.2f} ft respecto a la pieza. El brazo del ramal mide "
             f"{bs[2]['largo']:.2f} ft desde el CENTRO: su campana queda enterrada en el "
             f"tronco (radio 1.50 ft) y el tubo Ø4 muere a {bs[2]['alcance']:.2f} ft del "
             "centro, dentro del sólido."),
        nc="Los brazos se miden desde el centro, no desde la pared del tronco, y la pieza no es excéntrica.",
        marcas=[(P, "conflicto")])


def c16(lz, P):
    _tronco_y_ramal(lz, P, 90, largo_ramal=1.0)
    bs = brazos("TEE", [180, 0, 90], [12, 12, 12])
    return dict(
        titulo="Tee con un ramal de solo 1.0 ft",
        app="conflicto (misma cota)",
        c3d=(f"TEE: el ramal no se puede recortar {bs[2]['alcance']:.2f} ft → «Tubo de 1.00 ft "
             "demasiado corto»; el tubo queda metido hasta el centro de la pieza."),
        nc=None, marcas=[(P, "conflicto")])


def c17(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4),
            vertex_inv_in={1: -7.0}, vertex_inv_out={1: -7.0}, seg_edit_enabled=True)
    lz.tubo("AGUA", [P, pol(P, 270, L)], 12, (-7, -7))
    bs = brazos("TEE", [180, 0, 270], [12, 12, 12])
    pend = 3.0 / L
    return dict(
        titulo="Tee en un punto bajo del tronco (-4 → -7 → -4) + ramal horizontal",
        app="conflicto (misma cota)",
        c3d=("TEE rígida: brazos del tronco horizontales con los tubos al 6 % → "
             f"{bs[0]['boca'] * pend:.2f} ft de desalineación en cada boca del tronco."),
        nc="Mismo caso que C13: la pieza debería seguir la pendiente del tronco.",
        marcas=[(P, "conflicto")])


def c18(lz, P):
    arriba, abajo = (P[0], P[1] + 40), (P[0], P[1] - 40)
    angs = []
    for Q, pend in ((arriba, 1.75), (abajo, 1.70)):
        lz.tubo("AGUA", [(Q[0] - L, Q[1]), Q, (Q[0] + L, Q[1])], 12, (-4, -4))
        lz.tubo("AGUA", [Q, pol(Q, 270, 12)], 12, (-4, -4 - 12 * pend))
        angs.append(math.degrees(math.atan(pend)))
    boca = brazos("TEE", [180, 0, 270], [12, 12, 12])[2]["boca"]
    return dict(
        titulo=f"Umbral de ramal vertical ({_ft(WS['PENDIENTE_VERTICAL_DEG'])}°): ramal a "
               f"{angs[0]:.1f}° (arriba) y {angs[1]:.1f}° (abajo)",
        app="conflicto en las dos",
        c3d=(f"Arriba: el brazo del ramal sigue la inclinación del tubo. Abajo: brazo "
             f"HORIZONTAL y el tubo cae ~{boca * 1.70:.1f} ft por debajo de su boca."),
        nc="El umbral es un salto brusco: justo por debajo, un ramal empinado se despega de la pieza.",
        marcas=[(arriba, "conflicto"), (abajo, "conflicto")])


def c19(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [pol(P, 250, L), P, pol(P, 70, L)], 12, (-4, -4))
    return dict(
        titulo="Cruz oblicua: 4 tubos a 0°/70°/180°/250°",
        app="conflicto (misma cota)",
        c3d=("4 tubos → Cross: NO tiene versión sólida y cae al catálogo (cruz de 90°) sobre "
             "ejes a 70°/110° — VERIFICAR qué pieza sale y si conecta los 4 tubos."),
        nc="Cross sólida no implementada: las cruces oblicuas no tienen pieza.",
        marcas=[(P, "conflicto")])


def c20(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4), name="Linea Este")
    lz.tubo("AGUA", [P, pol(P, 90, L)], 12, (-4, -4), name="Ramal Sur")
    return dict(
        titulo="Tee entre utilidades con distinto nombre de red («Linea Este» / «Ramal Sur»)",
        app="conflicto (misma cota)",
        c3d=("Se crean 2 redes («Linea Este» y «Ramal Sur») y no hay TEE: el tronco sigue "
             "recto y el ramal queda suelto."),
        nc="Utilidades que se tocan a la misma cota no se unen si su red se llama distinto, y no se avisa.",
        marcas=[(P, "conflicto")])


# ── Conexiones verticales (cruces aprobados) ────────────────────────────────
def c21(lz, P):
    arr = lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0], P[1] + L)], 12, (-2, -2))
    aba = lz.tubo("AGUA", [pol(P, 225, L), pol(P, 45, L)], 12, (-8, -8))
    c = codo(12, 90)
    t = brazos("TEE", [180, 0, 90], [12, 12, 12])[0]["alcance"]
    return dict(
        titulo="Cruce APROBADO sobre un quiebre de 90° de la superior (las dos pasan)",
        app="aprobado",
        c3d=("ELBOW 90° de la red + TEE + TEE + vertical. La TEE superior se alinea con el "
             "tramo que llega: queda ENCIMA del codo, con un brazo hacia donde no hay tubo, "
             f"y sus tubos se re-alargan de {c['alcance']:.2f} a {t:.2f} ft del vértice."),
        nc="Quiebre + utilidad que pasa no tiene tratamiento; solo está resuelto quiebre + extremo.",
        marcas=[(P, "aprobado", (arr, aba))], aprobar=[(P, arr, aba)])


def c22(lz, P):
    arr = lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0], P[1] + L)], 12, (-2, -2))
    aba = lz.tubo("AGUA", [pol(P, 225, L), P, pol(P, 315, L)], 12, (-8, -8))
    return dict(
        titulo="Cruce APROBADO donde LAS DOS tienen un quiebre de 90° en el punto",
        app="aprobado (4 marcadores apilados)",
        c3d=("2 ELBOW 90° (uno por utilidad) + 2 TEE rectas + vertical: 4 sólidos en el "
             "mismo punto y cada TEE con un brazo hacia donde no hay tubo."),
        nc="Igual que C21, por partida doble.",
        marcas=[(P, "aprobado", (arr, aba))], aprobar=[(P, arr, aba)], cuenta=[(P, 4)])


def c23(lz, P):
    a = lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], 12, (-2, -2))
    b = lz.tubo("AGUA", [(P[0], P[1] - L), (P[0], P[1] + L)], 12, (-5, -5))
    c = lz.tubo("AGUA", [pol(P, 225, L), pol(P, 45, L)], 12, (-8, -8))
    return dict(
        titulo="Tres utilidades apiladas en el mismo punto (-2 / -5 / -8), aprobadas a-b y b-c",
        app="3 marcadores en el mismo punto: a-b y b-c aprobados, a-c sugerencia",
        c3d=("Dos verticales. La del medio (-5) recibe 2 TEE superpuestas, una con ramal "
             "hacia arriba y otra hacia abajo, en vez de una sola pieza de 4 salidas."),
        nc="Sin pieza para 3 niveles; y en la app el click solo alcanza el primer marcador del punto.",
        marcas=[(P, "aprobado", (a, b)), (P, "aprobado", (b, c)), (P, "sugerencia", (a, c))],
        aprobar=[(P, a, b), (P, b, c)], cuenta=[(P, 3)])


def c24(lz, P):
    sep = 2.0
    P2 = (P[0] + sep, P[1])
    a = lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], 12, (-2, -2))
    b1 = lz.tubo("AGUA", [(P[0], P[1] - L), (P[0], P[1] + L)], 12, (-8, -8))
    b2 = lz.tubo("AGUA", [(P2[0], P[1] - L), (P2[0], P[1] + L)], 12, (-8, -8))
    t = brazos("TEE", [180, 0, 90], [12, 12, 12])[0]
    return dict(
        titulo="Dos cruces APROBADOS sobre la misma tubería a 2 ft uno del otro",
        app="aprobado en los dos",
        c3d=(f"El cruce #2 no parte la tubería (su extremo quedó a {sep - t['alcance']:.2f} ft "
             f"< 1.5 ft) y su recorte ALARGA el tramo oeste hasta {sep - t['alcance']:.2f} ft "
             "al este del cruce #1: la tubería atraviesa la TEE #1 (predicción del código)."),
        nc=(f"El recorte no comprueba si alarga el tubo; además las 2 TEE se solapan "
            f"{2 * t['boca'] - sep:.2f} ft."),
        marcas=[(P, "aprobado", (a, b1)), (P2, "aprobado", (a, b2))],
        aprobar=[(P, a, b1), (P2, a, b2)])


def c25(lz, P):
    a, b = _cruce(lz, P, -2.5, -4.0, d_a=14, d_b=14)
    d = 14 / 12.0
    alc = brazos("TEE", [90], [14])[0]["alcance"]
    z_lo, z_hi = -4.0 + d / 2, -2.5 + d / 2
    return dict(
        titulo="Cruce APROBADO con solo 1.5 ft entre soleras (Ø14)",
        app="aprobado",
        c3d=(f"Los brazos verticales de las 2 TEE ({alc:.2f} ft c/u) no caben en "
             f"{z_hi - z_lo:.2f} ft entre ejes → «Puertos branch cruzados» y la vertical va "
             "de eje a eje atravesando las dos piezas."),
        nc="Debería rechazarse al aprobar en la app (o usar otra pieza) en vez de dibujar un choque.",
        marcas=[(P, "aprobado", (a, b))], aprobar=[(P, a, b)])


def c26(lz, P):
    a, b = _cruce(lz, P, -2.0, -8.0, d_a=6, d_b=24)
    alc = brazos("TEE", [90], [24])[0]["alcance"]
    return dict(
        titulo="Cruce APROBADO entre Ø6 (arriba) y Ø24 (abajo)",
        app="aprobado",
        c3d=("Vertical Ø6 (la menor). La TEE inferior toma Ø24 para TODOS sus brazos, también "
             f"el vertical: la vertical Ø6 entra en una campana de Ø24 y arranca {alc:.2f} ft "
             "por encima del eje."),
        nc="En los cruces el sólido usa un solo diámetro (el primero de la descripción de la Tee).",
        marcas=[(P, "aprobado", (a, b))], aprobar=[(P, a, b)])


# ── No contemplados ─────────────────────────────────────────────────────────
def f01(lz, P):
    arriba, abajo = (P[0], P[1] + 50), (P[0], P[1] - 50)
    for Q, hueco in ((arriba, 0.6), (abajo, 0.4)):
        lz.tubo("AGUA", [(Q[0] - L, Q[1]), Q], 12, (-4, -4))
        q2 = pol(Q, 60, hueco)
        lz.tubo("AGUA", [q2, pol(q2, 60, L)], 12, (-4, -4))
    return dict(
        titulo="Casi-juntura: extremos a 0.6 ft (arriba) y a 0.4 ft (abajo)",
        app="sin marcadores en ninguno (no llegan a tocarse)",
        c3d=("Arriba (0.6 ft): no se unen, 2 extremos sueltos y sin aviso. Abajo (0.4 ft): el "
             "plugin SÍ los une (tolerancia 0.5 ft) con un ELBOW 60°."),
        nc="App y plugin no usan el mismo criterio de «se tocan», y nadie avisa de extremos a punto de tocarse.",
        marcas=[(arriba, None), (abajo, None)])


def f02(lz, P):
    lz.tubo("AGUA", [(P[0] - 60, P[1]), (P[0] + 30, P[1]), (P[0] + 30, P[1] + 30),
                     (P[0], P[1] + 30), (P[0], P[1] - 40)], 12, (-4, -4))
    return dict(
        titulo="Una utilidad que se cruza a sí misma a la misma cota",
        app="sin marcadores (una utilidad no se compara consigo misma)",
        c3d=("3 ELBOW 90° y, donde la línea se cruza, dos tubos de la misma red se atraviesan "
             "a la misma cota: choque físico sin pieza ni aviso."),
        nc="Auto-cruces no detectados ni en la app ni en el plugin.",
        marcas=[(P, None)])


def f03(lz, P):
    lz.tubo("AGUA", [(P[0] - 60, P[1]), (P[0] + 15, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [(P[0] - 15, P[1]), (P[0] + 60, P[1])], 12, (-4, -4))
    return dict(
        titulo="Dos utilidades superpuestas en 30 ft (colineales, misma cota)",
        app="sin marcadores (los tramos paralelos no se comparan)",
        c3d="30 ft de tubería doble superpuesta; ningún extremo coincide, así que no hay pieza ni aviso.",
        nc="Solapes colineales no detectados.",
        marcas=[(P, None)])


def f04(lz, P):
    for _ in range(2):
        lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], 12, (-4, -4))
    m = codo(12, 180)
    return dict(
        titulo="Utilidad duplicada exacta (dos veces la misma línea)",
        app="sin marcadores",
        c3d=("En cada extremo se juntan los 2 tubos: «casi superpuestos (0.0° entre ejes)» ×2, "
             f"dos manguitos rectos y los dos tubos recortados {m['alcance']:.2f} ft."),
        nc="Utilidades duplicadas (típico al copiar/pegar) no se detectan.",
        marcas=[(P, None)])


def f05(lz, P):
    _tronco_y_ramal(lz, P, 45, ab=True)
    return dict(
        titulo="Y que une una tubería activa con una ABANDONADA",
        app="conflicto (misma cota)",
        c3d="WYE sólida que une la activa con la abandonada (el ramal sale con estilo 3D discontinuo).",
        nc="¿Una abandonada debe unirse a la red activa con pieza? Hoy se une sin distinguir.",
        marcas=[(P, "conflicto")])


def f06(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [(P[0], P[1] - L), P, (P[0], P[1] + L)], 12, (-8, -8))
    return dict(
        titulo="Cruce a distinta cota con un vértice de cada utilidad en el punto",
        app="4 marcadores «sugerencia» apilados (el contador suma 4)",
        c3d=("«[COTAS] … DISTINTA cota — NO se unen»; cada una sigue recta "
             "(Coupling o unión directa ×2)."),
        nc="Un solo cruce físico cuenta 4 veces en la app (uno por cada par de tramos).",
        marcas=[(P, "sugerencia")], cuenta=[(P, 4)])


def f07(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, P, pol(P, 60, L)], 12, (-4, -4))
    return dict(
        titulo="Codo con el vértice repetido (tramo de 0 ft)",
        app="sin marcadores",
        c3d="El tramo de 0 ft se omite y sale un ELBOW 60° normal.",
        nc=None, marcas=[])


def f08(lz, P):
    R, n, paso = 80.0, 30, 3.0
    a0 = (P[0] - 60, P[1] - 60)
    centro = (a0[0], a0[1] + R)
    arco = [(centro[0] + R * math.sin(math.radians(k * paso)),
             centro[1] - R * math.cos(math.radians(k * paso))) for k in range(n + 1)]
    pts = [(a0[0] - 50, a0[1])] + arco + [pol(arco[-1], n * paso, 30)]
    lz.tubo("AGUA", pts, 12, (-4, -4))
    m3, m15 = codo(12, paso), codo(12, paso / 2)
    cuerda = 2 * R * math.sin(math.radians(paso / 2))
    return dict(
        titulo=f"Curva suave de 90° dibujada con {n} tramos ({_ft(paso)}° por vértice)",
        app="sin marcadores",
        c3d=(f"{n - 1} ELBOW de {_ft(paso)}° (recortan {m3['alcance']:.2f} ft) + 2 «manguitos» "
             f"rectos de {2 * m15['boca']:.2f} ft en los puntos de tangencia (deflexión "
             f"{_ft(paso / 2)}°). Cuerdas de {cuerda:.2f} ft."),
        nc=("Decenas de piezas: en fundición push-on la junta admite ~3–5° de deflexión "
            "(AWWA C600) sin accesorio. Falta ese criterio."),
        marcas=[])


def f09(lz, P):
    lz.tubo("ELECTRICO", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 4, (-3, -3))
    lz.tubo("ELECTRICO", [P, (P[0], P[1] - 30), (P[0] + 30, P[1] - 30)], 4, (-3, -3))
    return dict(
        titulo="Eléctrico: derivación en T + quiebre de 90°",
        app="conflicto (misma cota)",
        c3d="Red conduit con estructuras nulas: NO se generan sólidos, ni TEE en la derivación ni codo en el quiebre.",
        nc="Las curvas (sweeps) y derivaciones de conduit eléctrico/telecom no se modelan.",
        marcas=[(P, "conflicto")])


NO_DIBUJABLES = [
    "Bajante/subida vertical como tubería propia (hoy solo nace de un cruce aprobado).",
    "Cambio de diámetro dentro de una misma polilínea → Reducer de catálogo, sin sólido.",
    "Ángulos no estándar: el sólido admite cualquiera, el catálogo real no (11¼/22½/45/90).",
    "Choque entre sólidos vecinos: no se comprueba en ningún caso.",
    "Bloques de anclaje (empuje) en codos y tees de presión.",
    "Válvulas, tapones e hidrantes en extremos libres.",
    "Reimportar en el mismo dibujo: los sólidos de la corrida anterior no se borran.",
    "Tubos más cortos que las piezas: la app no avisa al dibujar.",
    "Rendimiento con cientos de piezas (una unión booleana por brazo).",
]


def f10(lz, P):
    return dict(
        titulo="No dibujables en el lienzo (solo lista)",
        app="—", c3d="—", nc=None, marcas=[], lista=NO_DIBUJABLES)


CASOS = [(f"C{i:02d}", fn) for i, fn in enumerate(
    [c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13,
     c14, c15, c16, c17, c18, c19, c20, c21, c22, c23, c24, c25, c26], start=1)]
CASOS += [(f"F{i:02d}", fn) for i, fn in enumerate(
    [f01, f02, f03, f04, f05, f06, f07, f08, f09, f10], start=1)]


# ─────────────────────────────────────────────────────────────────────────────
#  Construcción y validación
# ─────────────────────────────────────────────────────────────────────────────
def _celda(i):
    col, fila = i % COLS, i // COLS
    cx = col * CELDA_X + CELDA_X / 2
    cy = ALTO_FT - (fila * CELDA_Y + CELDA_Y / 2)
    return cx, cy


def _etiqueta(cod, d):
    w = ANCHO_ETIQUETA
    lineas = textwrap.wrap(f"{cod} · {d['titulo']}", w)
    if d.get("lista"):
        lineas += [s for item in d["lista"]
                   for s in textwrap.wrap(f"- {item}", w, subsequent_indent="  ")]
        return lineas
    lineas += textwrap.wrap(f"App: {d['app']}", w, subsequent_indent="     ")
    lineas += textwrap.wrap(f"C3D: {d['c3d']}", w, subsequent_indent="     ")
    if d.get("nc"):
        lineas += textwrap.wrap(f"NO CONTEMPLADO: {d['nc']}", w, subsequent_indent="     ")
    return lineas


def construir(win):
    """Dibuja todos los casos en `win`. Devuelve {código: (P, datos del caso)}."""
    win.blank_canvas = True
    win.paper = dict(HOJA)
    win._load_blank_page(HOJA)
    lz = Lienzo(win)
    datos = {}
    for i, (cod, fn) in enumerate(CASOS):
        cx, cy = _celda(i)
        P = (cx, cy - 35)                    # deja arriba sitio para la etiqueta
        d = fn(lz, P)
        datos[cod] = (P, d)
        lz.texto((cx - CELDA_X / 2 + 6, cy + CELDA_Y / 2 - 4),
                 "\n".join(_etiqueta(cod, d)), ALTO_TEXTO)
    win._redraw()

    # Aprobar las conexiones verticales igual que el diálogo de la app.
    for cod, (P, d) in datos.items():
        for (pt, a, b) in d.get("aprobar", []):
            hit = buscar_hit(win, pt, (a, b))
            if hit is None:
                raise RuntimeError(f"{cod}: no hay marcador que aprobar en {pt}")
            cx, cy, ia, ib, _ka, _kb, za, zb, _estado = hit
            win.cross_connections.append({
                "x": float(cx), "y": float(cy), "pipe_a": int(ia), "pipe_b": int(ib),
                "z_a": None if za is None else float(za),
                "z_b": None if zb is None else float(zb), "valve": True})
    win._redraw()
    return datos


def validar(win, datos):
    """Marcadores de la app frente a lo esperado: [(código, punto, esperado, obtenido)]."""
    filas = []
    for cod, (_P, d) in datos.items():
        for m in d.get("marcas", []):
            pt, esperado = m[0], m[1]
            par = m[2] if len(m) > 2 else None
            h = buscar_hit(win, pt, par)
            filas.append((cod, pt, esperado, None if h is None else h[8]))
    return filas


def contar(win, pt_ft, tol_px=4.0):
    x, y = Lienzo(win).px(*pt_ft)
    return sum(1 for h in win._conflict_hits
               if (h[0] - x) ** 2 + (h[1] - y) ** 2 <= tol_px ** 2)


def cuentas(win, datos):
    """[(código, punto, esperados, obtenidos)] para los puntos con marcadores apilados."""
    return [(cod, pt, n, contar(win, pt))
            for cod, (_P, d) in datos.items() for (pt, n) in d.get("cuenta", [])]


def marcadores_fuera_de_lugar(win, datos, tol_px=4.0):
    """Marcadores que NO están en un punto previsto: casos que se tocan sin querer."""
    lz = Lienzo(win)
    previstos = [lz.px(*m[0]) for (_P, d) in datos.values() for m in d.get("marcas", [])]
    return [h for h in win._conflict_hits
            if not any((h[0] - x) ** 2 + (h[1] - y) ** 2 <= tol_px ** 2 for (x, y) in previstos)]


def generar(ruta=SALIDA):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from app_window import Main
    win = Main()
    datos = construir(win)
    win.project_path = ruta
    win._write_project(ruta)
    return win, datos


if __name__ == "__main__":
    win, datos = generar()
    print(f"Proyecto: {SALIDA}")
    print(f"{len(CASOS)} casos · {len(win.pipes)} utilidades · "
          f"{len(win.cross_connections)} conexiones verticales aprobadas\n")
    for cod, (_P, d) in datos.items():
        print("\n".join(_etiqueta(cod, d)) + "\n")
    print("Marcadores de la app frente a lo esperado:")
    for cod, _pt, esp, obt in validar(win, datos):
        print(f"  {'OK ' if esp == obt else 'XX '} {cod}: esperado {esp!s:11} obtenido {obt!s}")
    for cod, _pt, esp, obt in cuentas(win, datos):
        print(f"  {'OK ' if esp == obt else 'XX '} {cod}: {esp} marcadores apilados, hay {obt}")
    sobran = marcadores_fuera_de_lugar(win, datos)
    print(f"\nMarcadores fuera de lugar (casos que se tocan sin querer): {len(sobran)}")
