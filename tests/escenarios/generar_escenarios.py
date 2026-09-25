"""Genera `escenarios_prueba.digproj`: un lienzo en blanco con casuísticas de
prueba para la app y el plugin de Civil 3D.

Cada caso vive en su propia celda de una grilla (separadas para que ningún caso
toque a otro) y lleva escrito en el lienzo qué debería pasar en la app y en
Civil 3D. Esos textos se exportan al DXF, así que también se leen en Civil 3D.

Uso:
    python tests/escenarios/generar_escenarios.py            # regenera el .digproj
    pytest tests/escenarios                                   # valida la parte de la app

Se construye con el código REAL de la app (Main sin ventana), así el .digproj es
exactamente lo que guardaría el usuario.
"""
import math
import os
import sys
import textwrap

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
for _p in (os.path.join(_RAIZ, "app"), _RAIZ):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SALIDA = os.path.join(_AQUI, "escenarios_prueba.digproj")

# Hoja ARCH D apaisada (36 × 24 in) a 1" = 40' → 1440 × 960 pies reales.
ESCALA_FT_IN = 40.0
ANCHO_FT, ALTO_FT = 36 * ESCALA_FT_IN, 24 * ESCALA_FT_IN
HOJA = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=ESCALA_FT_IN,
            scale_ft_per_pt=ESCALA_FT_IN / 72.0, unit="in", landscape=True)
COLS, FILAS = 8, 6
CELDA_X, CELDA_Y = ANCHO_FT / COLS, ALTO_FT / FILAS    # 180 × 160 ft
L = 38.0                                               # largo típico de un tramo (ft)
ANCHO_ETIQUETA = 40                                    # caracteres por línea de etiqueta


def pol(p, ang_deg, largo):
    a = math.radians(ang_deg)
    return (p[0] + largo * math.cos(a), p[1] + largo * math.sin(a))


class Lienzo:
    """Dibuja en PIES (coordenadas CAD) sobre la ventana de la app."""

    def __init__(self, win):
        self.w = win

    def px(self, x, y):
        w = self.w
        return (x / w.scale * w.zoom, (w.H - y / w.scale) * w.zoom)

    def tubo(self, capa, pts_ft, diam=12.0, inv=(-4.0, -4.0), **extra):
        from model import DEFAULT_PIPE_MATERIAL
        p = {"layer": capa, "pts": [self.px(*q) for q in pts_ft], "ab": False,
             "diam": float(diam), "diam_unit": "in", "material": DEFAULT_PIPE_MATERIAL,
             "inv_start": float(inv[0]), "inv_end": float(inv[1])}
        p.update(extra)
        self.w.pipes.append(p)
        return len(self.w.pipes) - 1

    def texto(self, pos_ft, texto, alto_ft=2.4):
        self.w.text_marks.append({"pos": self.px(*pos_ft), "text": texto, "size_ft": alto_ft,
                                  "font": "Arial", "bold": False, "rot": 0, "free": True})


# ─────────────────────────────────────────────────────────────────────────────
#  CASOS. Cada uno: código, título, qué esperar en la app y en Civil 3D, y una
#  función que lo dibuja con centro P. Devuelve lo que la validación necesita:
#    "app":     [(punto, estado)] marcador esperado en la app en ese punto
#               ("conflicto" | "sugerencia" | "aprobado" | None = ningún marcador)
#    "aprobar": [(punto, tubo_a, tubo_b)] conexión vertical a aprobar ahí
# ─────────────────────────────────────────────────────────────────────────────
def codo(lz, P, defl, diam=12.0, inv=(-4.0, -4.0), l2=L, **extra):
    """Utilidad que entra por el oeste y gira `defl` grados en P."""
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, pol(P, defl, l2)], diam, inv, **extra)


def tronco_y_ramal(lz, P, ang, d_tronco=12.0, d_ramal=12.0, capa="AGUA", inv=-4.0):
    """Tronco recto oeste→este con vértice en P + ramal que sale de P a `ang`°."""
    lz.tubo(capa, [(P[0] - L, P[1]), P, (P[0] + L, P[1])], d_tronco, (inv, inv))
    lz.tubo(capa, [P, pol(P, ang, L)], d_ramal, (inv, inv))


def e01(lz, P): codo(lz, P, 11)
def e02(lz, P): codo(lz, P, 45)
def e03(lz, P): codo(lz, P, 90, diam=18)
def e04(lz, P):
    codo(lz, (P[0], P[1] + 18), 130)
    codo(lz, (P[0], P[1] - 18), 140)
def e05(lz, P): codo(lz, P, 160)
def e06(lz, P): codo(lz, P, 176)
def e07(lz, P): codo(lz, P, 170, l2=2.0)
def e08(lz, P): codo(lz, P, 60, inv=(-2.0, -10.0))
def codo_reductor(lz, P, defl, d_entra, d_sale):
    """Dos utilidades de distinto diámetro que se unen en P girando `defl`°."""
    lz.tubo("AGUA", [(P[0] - L, P[1]), P], d_entra, (-4, -4))
    lz.tubo("AGUA", [P, pol(P, defl, L)], d_sale, (-4, -4))
    return {"app": [(P, "conflicto")]}
def e09(lz, P): return codo_reductor(lz, P, 45, 24, 12)
def e41(lz, P): return codo_reductor(lz, P, 90, 24, 12)
def e42(lz, P): return codo_reductor(lz, P, 90, 12, 24)
def e43(lz, P): return codo_reductor(lz, P, 160, 18, 12)
def e44(lz, P): tronco_y_ramal(lz, P, 30, 24, 12); return {"app": [(P, "conflicto")]}
def e10(lz, P):
    lz.tubo("AGUA", [pol(P, 210, L), P, pol(P, 330, L)], 12, (-4, -4))
    lz.tubo("AGUA", [P, pol(P, 90, L)], 12, (-4, -4))
    return {"app": [(P, "conflicto")]}
def e11(lz, P): tronco_y_ramal(lz, P, 45, 24, 12); return {"app": [(P, "conflicto")]}
def e12(lz, P): tronco_y_ramal(lz, P, 20); return {"app": [(P, "conflicto")]}
def e13(lz, P): tronco_y_ramal(lz, P, 90, 18, 18); return {"app": [(P, "conflicto")]}
def e14(lz, P): tronco_y_ramal(lz, P, 90, 24, 12); return {"app": [(P, "conflicto")]}
def e15(lz, P): tronco_y_ramal(lz, P, 72); return {"app": [(P, "conflicto")]}
def e16(lz, P): tronco_y_ramal(lz, P, 66); return {"app": [(P, "conflicto")]}
def e17(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [(P[0], P[1] - L), P, (P[0], P[1] + L)], 12, (-4, -4))
    return {"app": [(P, "conflicto")]}
def e18(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [(P[0], P[1] - L), P, (P[0], P[1] + L)], 12, (-4, -4))
    lz.tubo("AGUA", [P, pol(P, 45, L)], 12, (-4, -4))
    return {"app": [(P, "exceso")]}
def cruz_mas(lz, P, extras, capa="AGUA", inv_extra=-4.0):
    """Dos tubos que PASAN por P (2 tramos cada uno) + `extras` que terminan en P."""
    lz.tubo(capa, [(P[0] - L, P[1]), P, (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo(capa, [(P[0], P[1] - L), P, (P[0], P[1] + L)], 12, (-4, -4))
    for k in range(extras):
        lz.tubo(capa, [P, pol(P, 45 + 90 * k, L)], 12, (inv_extra, inv_extra))
def e45(lz, P): cruz_mas(lz, P, 2); return {"app": [(P, "exceso")]}
def e46(lz, P): cruz_mas(lz, P, 1, capa="DRENAJE"); return {"app": [(P, "sin_exceso")]}
def e47(lz, P): cruz_mas(lz, P, 1, inv_extra=-6.0); return {"app": [(P, "sin_exceso")]}
def extremo_a_extremo(lz, P, inv_b):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P], 12, (-4.0, -4.0))
    lz.tubo("AGUA", [P, pol(P, 60, L)], 12, (inv_b, inv_b))
def e19(lz, P): extremo_a_extremo(lz, P, -4.00); return {"app": [(P, "conflicto")]}
def e20(lz, P): extremo_a_extremo(lz, P, -4.08); return {"app": [(P, "conflicto")]}
def e21(lz, P): extremo_a_extremo(lz, P, -4.15); return {"app": [(P, "sugerencia")]}
def e22(lz, P):
    codo(lz, P, 60, inv=(-4.0, -5.0),
         vertex_inv_in={1: -4.0}, vertex_inv_out={1: -5.0}, seg_edit_enabled=True)
    return {"app": [(P, "escalon")]}
def e23(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], 12, (-4, -4))
    lz.tubo("AGUA", [(P[0], P[1] - L), P], 12, (-4, -4))
    return {"app": [(P, "conflicto")]}
def cruce(lz, P, capa_a, inv_a, capa_b, inv_b, d_a=12.0, d_b=12.0):
    a = lz.tubo(capa_a, [(P[0] - L, P[1]), (P[0] + L, P[1])], d_a, (inv_a, inv_a))
    b = lz.tubo(capa_b, [(P[0], P[1] - L), (P[0], P[1] + L)], d_b, (inv_b, inv_b))
    return a, b
def e24(lz, P): cruce(lz, P, "AGUA", -4, "DRENAJE", -8); return {"app": [(P, None)]}
def e25(lz, P): cruce(lz, P, "AGUA", -4, "DRENAJE", -4); return {"app": [(P, "redes")]}
def e26(lz, P): cruce(lz, P, "ELECTRICO", -3, "ELECTRICO", -5); return {"app": [(P, None)]}
def e27(lz, P): cruce(lz, P, "AGUA", -3, "AGUA", -6); return {"app": [(P, "sugerencia")]}
def e28(lz, P): cruce(lz, P, "GAS", -4, "AGUA", -4); return {"app": [(P, "redes")]}
def e48(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], 12, (-4, -4), name="Linea Sur")
    lz.tubo("AGUA", [(P[0], P[1] - L), (P[0], P[1] + L)], 12, (-4, -4))
    return {"app": [(P, "conflicto")]}
def e29(lz, P):
    a, b = cruce(lz, P, "AGUA", -2, "AGUA", -8)
    return {"app": [(P, "aprobado")], "aprobar": [(P, a, b)]}
def e30(lz, P):
    a = lz.tubo("AGUA", [(P[0] - L, P[1]), (P[0] + L, P[1])], 12, (-2, -2))
    b = lz.tubo("AGUA", [(P[0], P[1] - L), P], 12, (-8, -8))
    return {"app": [(P, "aprobado")], "aprobar": [(P, a, b)]}
def quiebre_y_extremo(lz, P, inv_quiebre, inv_extremo):
    a = lz.tubo("AGUA", [pol(P, 180, L), P, pol(P, 30, L)], 12, (inv_quiebre, inv_quiebre))
    b = lz.tubo("AGUA", [pol(P, 240, L), P], 12, (inv_extremo, inv_extremo))
    return {"app": [(P, "aprobado")], "aprobar": [(P, a, b)]}
def e31(lz, P): return quiebre_y_extremo(lz, P, -2.0, -8.0)
def e32(lz, P):
    a = lz.tubo("AGUA", [(P[0] - L, P[1]), P], 12, (-2, -2))
    b = lz.tubo("AGUA", [(P[0], P[1] - L), P], 12, (-8, -8))
    return {"app": [(P, "aprobado")], "aprobar": [(P, a, b)]}
def e33(lz, P):
    d = quiebre_y_extremo(lz, P, -2.0, -4.0)
    d["app"] = d["app"] + [(P, "inclinada")]
    return d
def e34(lz, P): return quiebre_y_extremo(lz, P, -8.0, -2.0)
def e35(lz, P):
    a, b = cruce(lz, P, "AGUA", -2, "AGUA", -8, d_a=24, d_b=12)
    return {"app": [(P, "aprobado")], "aprobar": [(P, a, b)]}
def e36(lz, P):
    lz.tubo("AGUA", [(P[0] - L, P[1]), P], 12, (-4, -4), name="Linea Norte")
    lz.tubo("AGUA", [P, pol(P, 40, L)], 12, (-4, -4), name="Linea Norte")
    return {"app": [(P, "conflicto")]}
def e37(lz, P): codo(lz, P, 45, ab=True)
def e38(lz, P): tronco_y_ramal(lz, P, 45, capa="GAS", inv=-3.0); return {"app": [(P, "conflicto")]}
def e39(lz, P):
    b = P; c = pol(b, 60, 0.6)
    lz.tubo("AGUA", [(P[0] - 30, P[1]), b, c, pol(c, 120, 30)], 12, (-4, -4))
    return {"app": [(pol(b, 60, 0.3), "codos")]}
def e40(lz, P):
    lz.tubo("DRENAJE", [(P[0] - L, P[1] - 10), (P[0], P[1] - 10), (P[0] + 20, P[1] + 25)],
            18, (-6.0, -7.0))


# (código, título, esperado en la app, esperado en Civil 3D, función)
CASOS = [
    ("E01", "Codo suave 11°", "sin marcadores", "ELBOW sólido 11°, curva normal (R=1·D)", e01),
    ("E02", "Codo 45°", "sin marcadores", "ELBOW sólido 45°", e02),
    ("E03", "Codo 90° Ø18\"", "sin marcadores", "ELBOW sólido 90° Ø18", e03),
    ("E04", "Límite de codo cerrado: 130° (arriba) y 140° (abajo)", "sin marcadores",
     "130° curva normal; 140° «Codo cerrado» radio mínimo viable", e04),
    ("E05", "Codo cerrado 160°", "sin marcadores", "«Codo cerrado», tubos recortados", e05),
    ("E06", "Codo casi en U 176°", "sin marcadores", "«Codo cerrado», recorte largo; curva gira antes del vértice", e06),
    ("E07", "Codo cerrado 170° con tramo de 2 ft", "sin marcadores",
     "aviso «Tubo … demasiado corto para recortar»", e07),
    ("E08", "Codo con pendiente (-2 → -10)", "sin marcadores", "ELBOW inclinado: sigue la pendiente (no rígido en Z)", e08),
    ("E09", "Codo reductor 45° Ø24→Ø12", "conflicto (misma cota)", "CODO REDUCTOR sólido (cuerpo que se estrecha)", e09),
    ("E10", "Y simétrica (3 tubos a 120°)", "conflicto (misma cota)", "WYE sólida", e10),
    ("E11", "Y reductora: tronco Ø24, ramal Ø12 a 45°", "conflicto (misma cota)",
     "WYE: ramal alargado, campana entera fuera del Ø24", e11),
    ("E12", "Y con ramal muy cerrado (20°)", "conflicto (misma cota)",
     "WYE sin hundido: tronco con cuerpo más grueso, brazos alargados", e12),
    ("E13", "Tee 90° Ø18", "conflicto (misma cota)", "TEE sólida", e13),
    ("E14", "Tee reductora Ø24 / Ø12", "conflicto (misma cota)", "TEE: ramal alargado, campana entera fuera del Ø24", e14),
    ("E15", "Umbral Tee/Y: ramal a 72°", "conflicto (misma cota)", "TEE sin choque: ramal y brazo vecino ~0.92 ft", e15),
    ("E16", "Umbral Tee/Y: ramal a 66°", "conflicto (misma cota)", "WYE (ramal <70°)", e16),
    ("E17", "Cruz: 4 tubos en un punto", "conflicto (misma cota)", "CRUZ sólida: 4 brazos iguales; 2 ejes, sin diagonal", e17),
    ("E18", "5 tubos en un punto", "▲ rojo: «Hay 5 tuberías…»", "aviso «máximo de 4»; 3 ejes, sin diagonal", e18),
    ("E19", "Extremo con extremo, misma cota", "conflicto (misma cota)", "se unen: ELBOW 60°", e19),
    ("E20", "Extremo con extremo, Δ 0.08 ft", "conflicto (≤0.10)", "se unen + «[COTAS] cotas unificadas»", e20),
    ("E21", "Extremo con extremo, Δ 0.15 ft", "sugerencia ↕ (>0.10)", "NO se unen: «[COTAS] … DISTINTA cota»", e21),
    ("E22", "Escalón en su propio vértice (-4.0 / -5.0)", "▲ rojo: «escalón… se unirán a -4.50»", "«[COTAS] cotas unificadas a -4.50»", e22),
    ("E23", "Extremo que muere a MITAD de otro tramo, misma cota", "conflicto (misma cota)",
     "TEE: se parte el tramo que pasa («[JUNTURA-T]»)", e23),
    ("E24", "Agua × drenaje a distinta cota", "sin marcador", "sin conexión", e24),
    ("E25", "Agua × drenaje a la misma cota", "▲ rojo: «redes distintas»", "sin conexión (redes distintas)", e25),
    ("E26", "Eléctrico × eléctrico a distinta cota", "sin marcador (conduits)", "sin conexión", e26),
    ("E27", "Agua × agua a distinta cota, SIN aprobar", "sugerencia ↕", "sin vertical", e27),
    ("E28", "Gas × agua a la misma cota", "▲ rojo: «redes distintas»", "sin conexión", e28),
    ("E29", "Cruce recto × recto APROBADO", "aprobado ✓", "TEE + TEE + vertical", e29),
    ("E30", "Extremo sobre tramo recto APROBADO", "aprobado ✓", "CODO abajo + TEE arriba + vertical", e30),
    ("E31", "Extremo sobre QUIEBRE APROBADO", "aprobado ✓", "WYE + aux 1.00 ft + codos; 2 ejes, sin diagonal", e31),
    ("E32", "Extremo con extremo APROBADO", "aprobado ✓", "CODO + CODO + vertical", e32),
    ("E33", "Quiebre + extremo APROBADO, Δz 2 ft", "aprobado ✓ + ▲ rojo: conexión con pendiente",
     "WYE con ramal inclinado (sin codos ni vertical) + la tubería que termina con pendiente", e33),
    ("E34", "Quiebre + extremo APROBADO, termina la de ARRIBA", "aprobado ✓", "WYE abajo, vertical SUBE; 2 ejes, sin diagonal", e34),
    ("E35", "Cruce APROBADO Ø24 × Ø12", "aprobado ✓", "vertical Ø12; TEE de arriba REDUCTORA (ramal Ø12)", e35),
    ("E36", "Dos tramos con nombre «Linea Norte»", "conflicto (misma cota)", "red «Linea Norte» (no RED-AGUA)", e36),
    ("E37", "Utilidad abandonada", "sin marcadores", "estilo 3D discontinuo", e37),
    ("E38", "Y en GAS", "conflicto (misma cota)", "WYE sólida en RED-GAS", e38),
    ("E39", "Dos codos de 60° separados 0.6 ft", "▲ rojo: tramo muy corto entre codos",
     "UN solo codo de 120° en la intersección (el tramo de 0.6 ft desaparece)", e39),
    ("E40", "Drenaje (gravedad) con quiebres — control", "sin marcadores", "buzones automáticos, sin cambios", e40),
    ("E41", "Codo reductor 90° Ø24→Ø12", "conflicto (misma cota)", "CODO REDUCTOR sólido 90°", e41),
    ("E42", "Codo reductor 90° Ø12→Ø24 (entra el delgado)", "conflicto (misma cota)", "CODO REDUCTOR que se ENSANCHA", e42),
    ("E43", "Codo reductor CERRADO 160° Ø18→Ø12", "conflicto (misma cota)", "«Codo cerrado» + reductor, tubos recortados", e43),
    ("E44", "Y reductora con ramal a 30° Ø24/Ø12", "conflicto (misma cota)", "WYE: ramal muy alargado (~3.2 ft)", e44),
    ("E45", "6 tramos en un punto", "▲ rojo: «Hay 6 tuberías…»", "aviso «máximo de 4», sin accesorio", e45),
    ("E46", "5 tramos de DRENAJE en un punto", "sin ▲ (gravedad: lo resuelve el buzón)", "buzón con 5 tubos", e46),
    ("E47", "5 tramos, uno 2 ft más abajo", "sin ▲ (el de abajo no se une)", "CRUZ + tubo aparte a su cota", e47),
    ("E48", "Agua «Linea Sur» × agua sin nombre, misma cota (cruce en X)", "conflicto (misma cota)",
     "sin conexión: un cruce en X de dos tubos que siguen de largo no se une (quedan chocando)", e48),
]


def centro(i):
    col, fila = i % COLS, i // COLS
    return (col * CELDA_X + CELDA_X / 2, ALTO_FT - (fila * CELDA_Y + CELDA_Y / 2) - 8)


def construir(win):
    """Dibuja todos los casos en `win`. Devuelve {código: (P, datos de validación)}."""
    win.blank_canvas = True
    win.paper = dict(HOJA)
    win._load_blank_page(HOJA)
    lz = Lienzo(win)
    datos = {}
    for i, (cod, titulo, app, c3d, fn) in enumerate(CASOS):
        P = centro(i)
        datos[cod] = (P, fn(lz, P) or {})
        x0, y0 = P[0] - CELDA_X / 2 + 4, P[1] + CELDA_Y / 2 + 2
        # Líneas cortas: una etiqueta larga invadía la celda de al lado.
        lineas = (textwrap.wrap(f"{cod} · {titulo}", ANCHO_ETIQUETA)
                  + textwrap.wrap(f"App: {app}", ANCHO_ETIQUETA, subsequent_indent="     ")
                  + textwrap.wrap(f"C3D: {c3d}", ANCHO_ETIQUETA, subsequent_indent="     "))
        lz.texto((x0, y0), "\n".join(lineas))
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


def buscar_hit(win, pt_ft, par=None, tol_px=4.0):
    x, y = Lienzo(win).px(*pt_ft)
    for h in win._conflict_hits:
        if (h[0] - x) ** 2 + (h[1] - y) ** 2 > tol_px ** 2:
            continue
        if par and {h[2], h[3]} != set(par):
            continue
        return h
    return None


# Alertas rojas de la app, por el estado con que las nombran los casos.
ALERTAS = {"exceso": "_exceso_hits", "escalon": "_escalon_hits", "redes": "_redes_hits",
           "codos": "_codos_hits", "inclinada": "_inclinada_hits"}


def buscar_alerta(win, pt_ft, lista, tol_px=4.0):
    """Triángulo rojo de la lista `lista` (atributo de Main) en ese punto, o None."""
    x, y = Lienzo(win).px(*pt_ft)
    return next((e for e in getattr(win, lista, []) or []
                 if (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= tol_px ** 2), None)


def validar(win, datos):
    """Marcadores de la app frente a lo esperado. Devuelve [(código, punto, esperado, obtenido)]."""
    filas = []
    for cod, (P, d) in datos.items():
        for (pt, esperado) in d.get("app", []):
            alerta = esperado.replace("sin_", "") if esperado else None
            if alerta in ALERTAS:
                hay = buscar_alerta(win, pt, ALERTAS[alerta]) is not None
                obtenido = alerta if hay else "sin_" + alerta
            else:
                h = buscar_hit(win, pt)
                obtenido = None if h is None else h[8]
            filas.append((cod, pt, esperado, obtenido))
    return filas


def marcadores_fuera_de_lugar(win, datos, tol_px=4.0):
    """Marcadores que NO están en un punto previsto: casos que se tocan sin querer."""
    lz = Lienzo(win)
    previstos = [lz.px(*pt) for (_P, d) in datos.values() for (pt, _e) in d.get("app", [])]
    todos = [(h[0], h[1]) for h in win._conflict_hits]
    todos += [(e["x"], e["y"]) for lista in ALERTAS.values() for e in getattr(win, lista, []) or []]
    return [h for h in todos
            if not any((h[0] - x) ** 2 + (h[1] - y) ** 2 <= tol_px ** 2 for (x, y) in previstos)]


def generar(ruta=SALIDA):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
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
    for cod, titulo, app, c3d, _fn in CASOS:
        print(f"{cod}  {titulo}\n       App: {app}\n       C3D: {c3d}")
    print("\nMarcadores de la app frente a lo esperado:")
    for cod, _pt, esp, obt in validar(win, datos):
        print(f"  {'OK ' if esp == obt else 'XX '} {cod}: esperado {esp!s:11} obtenido {obt!s}")
    sobran = marcadores_fuera_de_lugar(win, datos)
    print(f"\nMarcadores fuera de lugar (casos que se tocan sin querer): {len(sobran)}")
