"""Receta de la válvula de compuerta (2026-11-05), PURA: las piezas de la válvula para CUALQUIER diámetro.

La MISMA receta la usan la Vista 3D de la app (`valvulas3d`, triángulos) y el plugin de Civil 3D
(`ValvulaReceta.cs`, Solid3d): las dos dibujan lo mismo. Es la forma de los bloques del catálogo del plugin de
válvulas del equipo (`Valvulas_AWWA_3D.dwg`), medida de sus 24 bloques (3"–54") y escrita como fórmulas del
diámetro N: así no queda limitada a esos tamaños. Las medidas de norma (brida, pernos, cara a cara, OD del tubo) son
las de `CatalogoValvulas.T` del plugin del equipo; un diámetro que no está en esa tabla se interpola (o se prolonga
desde los dos extremos) y queda marcado «estimado». `test_valvulas.test_espejo_de_la_receta_en_el_plugin` compara
estas constantes con las de `ValvulaReceta.cs`.

Unidades: PULGADAS. Origen = centro de la válvula sobre el eje de la tubería, X = eje, Z = vástago, Y = hacia el
volante. Capas: 0 = cuerpo (V-PRES-VALV-DIA), 1 = vástago y tuerca (V-PRES-VALV-INT).
Tipos: «FLG» (bridas), «RG» (junta mecánica, campanas; hasta `RG_MAX_IN`), «GEAR» (bridas + caja de engranes y
volante; desde `ENGRANES_MIN_IN`)."""
from __future__ import annotations

from dataclasses import dataclass, field

# N: (OD brida, espesor brida, círculo de pernos, nº pernos, agujero, cara a cara FLG, OD tubo) — ASME B16.1 cl.125 /
# AWWA C207 (54"), cara a cara AWWA C509/C515, OD AWWA C151. Igual a `CatalogoValvulas.T`.
TABLA = {
    3: (7.5, 0.75, 6.0, 4, 0.75, 8.0, 3.96),
    4: (9.0, 0.94, 7.5, 8, 0.75, 9.0, 4.80),
    6: (11.0, 1.0, 9.5, 8, 0.875, 10.0, 6.90),
    8: (13.5, 1.12, 11.75, 8, 0.875, 11.5, 9.05),
    10: (16.0, 1.19, 14.25, 12, 1.0, 13.0, 11.10),
    12: (19.0, 1.25, 17.0, 12, 1.0, 14.0, 13.20),
    14: (21.0, 1.38, 18.75, 12, 1.125, 15.0, 15.30),
    16: (23.5, 1.44, 21.25, 16, 1.125, 16.0, 17.40),
    18: (25.0, 1.56, 22.75, 16, 1.25, 17.0, 19.50),
    20: (27.5, 1.69, 25.0, 20, 1.25, 18.0, 21.60),
    24: (32.0, 1.88, 29.5, 20, 1.375, 20.0, 25.80),
    30: (38.75, 2.12, 36.0, 28, 1.375, 24.0, 32.00),
    36: (46.0, 2.38, 42.75, 32, 1.625, 28.0, 38.30),
    42: (53.0, 2.62, 49.5, 36, 1.625, 32.0, 44.50),
    48: (59.5, 2.75, 56.0, 44, 1.625, 36.0, 50.80),
    54: (66.25, 3.0, 62.75, 44, 2.0, 40.0, 57.10),
}
SERIE = tuple(sorted(TABLA))
N_MIN, N_MAX = 3.0, 72.0          # fuera de esto no hay válvula (menos de 3" = otro tipo: roscada, pendiente)
RG_MAX_IN = 16.0
ENGRANES_MIN_IN = 18.0

# Fórmulas (pulgadas) medidas en los 24 bloques del catálogo (coinciden con ≤0.01" en todos)
CUERPO_K, CUERPO_B = 0.54, 0.9            # radio del cuerpo = 0.54·N + 0.9
CAMPANA_SOBRE_TUBO = 1.35                 # RG: radio de la campana = OD tubo / 2 + 1.35
ARO_SOBRE_CAMPANA = 0.6                   # RG: aro de la junta = campana + 0.6
CAMPANA_LARGO, ARO_LARGO = 2.5, 1.0       # RG: largos de campana y aro (desde la cara)
RG_EXTRA, RG_K = 3.0, 0.17                # RG: largo = cara a cara + 3 + 0.17·N (`LargoValvula`)
CAJA_X_K, CAJA_X_MIN = 0.275, 2.3         # caja: medio ancho en X = máx(0.275·L, 2.3)
CAJA_Y_K, CAJA_Y_B = 0.52, 1.2            # caja: medio ancho en Y = 0.52·N + 1.2
TAPA_Z_K, TAPA_Z_B = 1.55, 2.1            # tapa: z inferior = 1.55·N + 2.1
TAPA_E_B, TAPA_E_K = 1.0, 0.03            # tapa: espesor = 1 + 0.03·N
TAPA_X_SOBRE, TAPA_Y_K, TAPA_Y_B = 0.6, 0.52, 1.9   # tapa: medio ancho X = caja + 0.6, Y = 0.52·N + 1.9
YUGO_TOPE_K, YUGO_TOPE_B = 1.98, 6.3      # sin engranes: cilindro sobre la tapa hasta 1.98·N + 6.3
YUGO_R_K, YUGO_R_B, YUGO_R_K2, YUGO_R_B2 = 0.205, 0.34, 0.1, 0.9   # su radio = máx(0.205·N+0.34, 0.1·N+0.9)
VASTAGO_R_K, VASTAGO_R_B = 0.1, 0.45      # vástago (capa INT): radio 0.1·N + 0.45
VASTAGO_Z0_B = 0.5                        # desde z = N + 0.5
VASTAGO_TOPE_B = 7.9                      # sin engranes: hasta 1.98·N + 7.9
TUERCA_LADO, TUERCA_ALTO, TUERCA_SOBRE = 2.0, 1.75, 0.275   # tuerca cuadrada de 2", su tope 0.275 sobre el vástago
EJE_GEAR_R_K, EJE_GEAR_R_B = 0.1, 0.55    # con engranes: cilindro de la tapa a la caja, radio 0.1·N + 0.55
ENGR_X_K, ENGR_X_B = 0.175, 3.0           # caja de engranes: medio lado 0.175·N + 3
ENGR_Z_K, ENGR_Z_B = 1.98, 5.3            # su z inferior = 1.98·N + 5.3
ENGR_H_K, ENGR_H_B = 0.3, 4.0             # su alto = 0.3·N + 4
VOL_Y_K, VOL_Y_B = 0.375, 7.0             # volante: plano en y = 0.375·N + 7 (hacia +Y)
VOL_R_K, VOL_R_B = 0.25, 8.0              # radio del aro (al eje del tubo del aro) = 0.25·N + 8
VOL_T_K, VOL_T_B = 0.015, 0.7             # radio del tubo del aro = 0.015·N + 0.7
VOL_CUBO_K, VOL_CUBO_B, VOL_CUBO_L = 0.05, 2.0, 3.0   # cubo: radio 0.05·N + 2, largo 3
VOL_EJE_K, VOL_EJE_B = 0.03, 1.0          # eje del volante: radio 0.03·N + 1 (de la caja al cubo)
VOL_RAYO_K, VOL_RAYO_B = 0.012, 0.565     # 4 rayos a 0/90/180/270°: radio 0.012·N + 0.565


def _interpolar(n):
    """Medidas de norma para N (pulgadas): la fila de la tabla o la recta entre las dos vecinas (fuera del
    rango, la de los dos extremos). Nº de pernos: múltiplo de 4."""
    if n in TABLA:
        return TABLA[n], False
    xs = SERIE
    if n < xs[0]:
        a, b = xs[0], xs[1]
    elif n > xs[-1]:
        a, b = xs[-2], xs[-1]
    else:
        a = max(x for x in xs if x < n)
        b = min(x for x in xs if x > n)
    t = (n - a) / (b - a)
    fila = [TABLA[a][k] + (TABLA[b][k] - TABLA[a][k]) * t for k in range(7)]
    fila[3] = max(4, int(round(fila[3] / 4.0)) * 4)
    return tuple(fila), True


def tipo_de(n, union="FLG"):
    """«GEAR» desde 18", «RG» si lo piden y cabe, si no «FLG»."""
    if n >= ENGRANES_MIN_IN:
        return "GEAR"
    return "RG" if union == "RG" and n <= RG_MAX_IN else "FLG"


def nombre(n, tipo):
    s = f"{n:g}"
    return f"VALV_{s}_FLG_GEAR" if tipo == "GEAR" else f"VALV_{s}_{tipo}"


@dataclass
class Receta:
    n: float
    tipo: str
    bloque: str
    largo: float                  # a lo largo del eje (pulgadas)
    od_extremo: float             # diámetro mayor de los extremos (brida o aro)
    estimada: bool
    piezas: list = field(default_factory=list)


def receta(n, union="FLG"):
    """Receta de la válvula de N pulgadas. Piezas (todas en pulgadas, capa 0/1):
    ("tubo", capa, x0, x1, r_ext, r_int)                    cilindro hueco a lo largo de X
    ("brida", capa, x0, x1, r_ext, r_int, r_pernos, n, r_ag)  disco hueco con agujeros (ángulos (i+½)·360/n desde +Y a +Z)
    ("caja", capa, (x0, y0, z0), (x1, y1, z1))
    ("cil", capa, eje "x"|"y"|"z", (cx, cy, cz) inicio, largo, r)
    ("toro", capa, (cx, cy, cz), R, r)                       aro en el plano XZ (eje Y)."""
    n = float(n)
    fila, estimada = _interpolar(n)
    od_b, esp, bc, pernos, agujero, cc, od_tubo = fila
    t = tipo_de(n, union)
    L = cc + RG_EXTRA + RG_K * n if t == "RG" else cc
    h = L / 2.0
    r_c = CUERPO_K * n + CUERPO_B
    r_i = n / 2.0
    p = []
    if t == "RG":
        r_camp = od_tubo / 2.0 + CAMPANA_SOBRE_TUBO
        r_aro = r_camp + ARO_SOBRE_CAMPANA
        x_c = h - ARO_LARGO - CAMPANA_LARGO
        p.append(("tubo", 0, -x_c, x_c, r_c, r_i))
        for s in (-1, 1):
            a, b = sorted((s * x_c, s * (h - ARO_LARGO)))
            p.append(("tubo", 0, a, b, r_camp, r_i))
            a, b = sorted((s * (h - ARO_LARGO), s * h))
            p.append(("tubo", 0, a, b, r_aro, r_i))
        od_ext = 2 * r_aro
    else:
        p.append(("tubo", 0, -(h - esp), h - esp, r_c, r_i))
        for s in (-1, 1):
            a, b = sorted((s * (h - esp), s * h))
            p.append(("brida", 0, a, b, od_b / 2.0, r_i, bc / 2.0, int(pernos), agujero / 2.0))
        od_ext = od_b
    bx = max(CAJA_X_K * L, CAJA_X_MIN)
    by = CAJA_Y_K * n + CAJA_Y_B
    z0 = TAPA_Z_K * n + TAPA_Z_B
    z1 = z0 + TAPA_E_B + TAPA_E_K * n
    p.append(("caja", 0, (-bx, -by, 0.0), (bx, by, z0)))
    cx, cy = bx + TAPA_X_SOBRE, TAPA_Y_K * n + TAPA_Y_B
    p.append(("caja", 0, (-cx, -cy, z0), (cx, cy, z1)))
    rv = VASTAGO_R_K * n + VASTAGO_R_B
    zv0 = n + VASTAGO_Z0_B
    if t == "GEAR":
        g0 = ENGR_Z_K * n + ENGR_Z_B
        g1 = g0 + ENGR_H_K * n + ENGR_H_B
        gx = ENGR_X_K * n + ENGR_X_B
        p.append(("cil", 0, "z", (0.0, 0.0, z1), g0 - z1, EJE_GEAR_R_K * n + EJE_GEAR_R_B))
        p.append(("caja", 0, (-gx, -gx, g0), (gx, gx, g1)))
        zg = (g0 + g1) / 2.0
        yv = VOL_Y_K * n + VOL_Y_B
        cubo_r = VOL_CUBO_K * n + VOL_CUBO_B
        y_cubo = yv - VOL_CUBO_L / 2.0
        p.append(("cil", 0, "y", (0.0, gx, zg), y_cubo - gx, VOL_EJE_K * n + VOL_EJE_B))
        p.append(("cil", 0, "y", (0.0, y_cubo, zg), VOL_CUBO_L, cubo_r))
        R = VOL_R_K * n + VOL_R_B
        p.append(("toro", 0, (0.0, yv, zg), R, VOL_T_K * n + VOL_T_B))
        rr = VOL_RAYO_K * n + VOL_RAYO_B
        p.append(("cil", 0, "x", (0.0, yv, zg), R, rr))
        p.append(("cil", 0, "x", (-R, yv, zg), R, rr))
        p.append(("cil", 0, "z", (0.0, yv, zg), R, rr))
        p.append(("cil", 0, "z", (0.0, yv, zg - R), R, rr))
        p.append(("cil", 1, "z", (0.0, 0.0, zv0), g0 - zv0, rv))
    else:
        zy = YUGO_TOPE_K * n + YUGO_TOPE_B
        ry = max(YUGO_R_K * n + YUGO_R_B, YUGO_R_K2 * n + YUGO_R_B2)
        p.append(("cil", 0, "z", (0.0, 0.0, z1), zy - z1, ry))
        zt = YUGO_TOPE_K * n + VASTAGO_TOPE_B
        p.append(("cil", 1, "z", (0.0, 0.0, zv0), zt - zv0, rv))
        a = TUERCA_LADO / 2.0
        p.append(("caja", 1, (-a, -a, zt + TUERCA_SOBRE - TUERCA_ALTO), (a, a, zt + TUERCA_SOBRE)))
    return Receta(n=n, tipo=t, bloque=nombre(n, t), largo=L, od_extremo=od_ext, estimada=estimada, piezas=p)
