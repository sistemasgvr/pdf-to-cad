"""Genera `presentacion_1_3_0.digproj`: lienzo en blanco para PRESENTAR la versión 1.3.0.

  Filas 1–4 (N01–N36)  cada caso del Excel de normativas (hojas TIPOS, PRESION-DIAMETROS,
                       PRESION-ACCESORIOS y ELECT-TELECOM): uno que cumple y otro que no.
  Filas 5–6 (X01–X13)  las otras novedades que se ven sin PDF: editar en bloque, copiar y
                       pegar propiedades, unir utilidades, la revisión antes de exportar
                       (puntas, cortas, repetidas, sueltas, tramos diminutos), choques,
                       bancoducto en dos utilidades, sólido y diámetro por defecto.

Cada celda dice qué fila del Excel prueba y qué aviso debe salir (o «sin aviso»). Los
textos se exportan al DXF. Las normativas son las de fábrica (`normas_catalogo.BASE`):
con otras importadas, los avisos pueden cambiar.

Uso:
    python tests/escenarios/generar_presentacion_130.py   # regenera el .digproj
    pytest tests/escenarios                                # valida lo esperado

Se construye con el código REAL de la app (Main sin ventana), como los demás escenarios.
"""
import copy
import os
import textwrap

import generar_escenarios as base            # también arma sys.path (app/ + raíz)
from generar_escenarios import Lienzo, pol

SALIDA = os.path.join(base._AQUI, "presentacion_1_3_0.digproj")

# ARCH D apaisada (36 × 24 in) a 1" = 60' → 2160 × 1440 pies (misma hoja que la 2.ª tanda).
HOJA = dict(name="ARCH D", w_pt=36 * 72.0, h_pt=24 * 72.0, ft_per_inch=60.0,
            scale_ft_per_pt=60.0 / 72.0, unit="in", landscape=True)
ANCHO_FT, ALTO_FT = 36 * 60.0, 24 * 60.0
TITULO_FT = 80.0                              # franja de arriba con el título
COLS, FILAS = 9, 6
CELDA_X, CELDA_Y = ANCHO_FT / COLS, (ALTO_FT - TITULO_FT) / FILAS     # 240 × 226.7 ft
L = 60.0                                      # largo típico de un tramo (ft)
ALTO_TEXTO = 6.0
ANCHO_ETIQUETA = 46

DP, AC, DOM = "DISTRIBUCION PRINCIPAL", "ALIMENTACION Y CONDUCCION", "INSTALACION DOMICILIARIA"

TITULO = (
    "PDF a CAD 1.3.0 · Normativas en tablas y novedades\n"
    "Filas 1-4 (N01-N36): un caso por fila del Excel de normativas, el que cumple y el que no. "
    "Filas 5-6 (X01-X13): otras novedades.\n"
    "Avisos: circulito ámbar «!» en el lugar, etiqueta del accesorio en ámbar y «N avisos de normativa» "
    "en la barra de estado (clic = lista; clic en un aviso = ir al lugar). «Sin tipo» no se dibuja: "
    "se ve en el panel y en la lista.\n"
    "Ver → Avisos: desmarca «Cruces y conflictos» para ver solo las normativas. "
    "Herramientas → Tabla de datos (Ctrl+Shift+T): todo esto en tablas, exportable a Excel.")


# ─────────────────────────── utilidades con tamaño de catálogo ───────────────────────────
# El diámetro que miran las normativas es el del TAMAÑO elegido (`model_ops.diametro`):
# sin `pipe_size` vale 12" (por defecto). Se busca una familia del catálogo de Civil 3D
# instalado que tenga ese tamaño, para que el panel lo muestre; sin catálogo queda solo
# el tamaño (las normativas lo leen igual).
_PREFERIDAS = {"pressure": ("C115", "C901", "C900"),
               "conduit": ("Pvc", "DIPipe", "HDPE"), "gravity": ("Pvc", "Concrete")}


def _familias(win, kind):
    from catalogo import civil_catalog as cc
    try:
        fams = cc.pressure_pipes(win.civil_year) if kind == "pressure" else cc.imperial_pipes(win.civil_year)
    except Exception:
        return []
    out = []
    for f in fams:
        try:
            tam = (cc.pressure_pipe_sizes(win.civil_year, f["id"]) if kind == "pressure"
                   else cc.pipe_sizes(win.civil_year, f["id"]))
        except Exception:
            tam = []
        out.append((f["id"], tam))
    pref = _PREFERIDAS.get(kind, ())
    return sorted(out, key=lambda f: next((k for k, p in enumerate(pref) if p.lower() in f[0].lower()), 99))


class Dibujo(Lienzo):
    def __init__(self, win):
        super().__init__(win)
        self._fams = {}

    def familia_con(self, capa, diam):
        from nucleo.model import network_kind
        kind = network_kind(capa)
        if kind not in self._fams:
            self._fams[kind] = _familias(self.w, kind)
        tam = f"{diam:g} in"
        return next((fid for fid, tams in self._fams[kind] if tam in tams), ""), tam

    def util(self, capa, pts, diam=None, tipo="", amp=None, inv=(-4.0, -4.0), **extra):
        """Utilidad con tipo, amperaje y TAMAÑO de catálogo (`diam` None = por defecto)."""
        if diam is not None:
            fid, tam = self.familia_con(capa, diam)
            extra.update(pipe_family=fid, pipe_size=tam)
        i = self.tubo(capa, pts, diam if diam is not None else 12.0, inv, **extra)
        p = self.w.pipes[i]
        if tipo:
            p["tipo"] = tipo
        if amp is not None:
            p["amperaje"] = float(amp)
        return i


# ─────────────────────────── formas ───────────────────────────

def recta(dz, capa, P, d, tipo="", largo=2 * L, **k):
    return dz.util(capa, [(P[0] - largo / 2, P[1]), (P[0] + largo / 2, P[1])], d, tipo, **k)


def codo(dz, capa, P, defl, d, tipo="", leg=L):
    """Entra por el oeste y se desvía `defl`° en P (deflexión sobre el eje)."""
    return dz.util(capa, [(P[0] - leg, P[1]), P, pol(P, defl, leg)], d, tipo)


def te(dz, capa, P, d_tronco, d_ramal, tipo_tronco, tipo_ramal=None, ang=-90):
    """Tronco oeste→este con vértice en P y ramal que nace en P (a 90°: Tee; a 45°: Wye)."""
    dz.util(capa, [(P[0] - L, P[1]), P, (P[0] + L, P[1])], d_tronco, tipo_tronco)
    dz.util(capa, [P, pol(P, ang, L)], d_ramal, tipo_ramal if tipo_ramal is not None else tipo_tronco)


def cruz(dz, capa, P, d, tipo):
    dz.util(capa, [(P[0] - L, P[1]), P, (P[0] + L, P[1])], d, tipo)
    dz.util(capa, [(P[0], P[1] - L), P, (P[0], P[1] + L)], d, tipo)


# ─────────────────────────── normativas (N) ───────────────────────────
# Cada caso: (código, título, fila del Excel, qué debe salir, función, avisos esperados).
# Avisos esperados = clases de `normas_validar.CLASES` (orden indistinto).

def n_codos_ok(dz, P):
    for k, defl in enumerate((11.25, 22.5, 45.0, 90.0)):
        q = (P[0] + (-55 if k % 2 == 0 else 55), P[1] + (15 if k < 2 else -55))
        codo(dz, "AGUA", q, defl, 8, DP, leg=40)


CASOS_N = [
    # TIPOS
    ("N01", "Agua sin tipo", "TIPOS", "AVISO «Sin tipo: elige su tipo…» (en el panel y la lista, no en el plano)",
     lambda dz, P: recta(dz, "AGUA", P, 8), ["tipo"]),
    ("N02", "Agua con un tipo que ya no está en la lista («RIEGO»)", "TIPOS",
     "AVISO «El tipo «RIEGO» ya no está en la lista»",
     lambda dz, P: recta(dz, "AGUA", P, 8, "RIEGO"), ["tipo"]),
    ("N03", "Eléctrico sin tipo", "TIPOS", "AVISO «Sin tipo» (eléctrico también tiene tipos)",
     lambda dz, P: recta(dz, "ELECTRICO", P, 4), ["tipo"]),
    # PRESION-DIAMETROS
    ("N04", "Distribución principal Ø8\"", "PRESION-DIAMETROS · DP 6; 8; 12; 16", "sin aviso",
     lambda dz, P: recta(dz, "AGUA", P, 8, DP), []),
    ("N05", "Distribución principal Ø4\" (cul-de-sac)", "PRESION-DIAMETROS · DP 4 · CALLES SIN SALIDA",
     "INFO (celeste): «solo se permite en CALLES SIN SALIDA…» (informativo)",
     lambda dz, P: recta(dz, "AGUA", P, 4, DP), ["nota"]),
    ("N06", "Distribución principal Ø10\"", "PRESION-DIAMETROS · DP 6; 8; 12; 16",
     "AVISO «Diámetro 10\" no permitido para DP»",
     lambda dz, P: recta(dz, "AGUA", P, 10, DP), ["diametro"]),
    ("N07", "Distribución principal Ø2\"", "PRESION-DIAMETROS · 2\" es de domiciliaria",
     "AVISO «Diámetro 2\": es de INSTALACION DOMICILIARIA…»",
     lambda dz, P: recta(dz, "AGUA", P, 2, DP), ["diametro"]),
    ("N08", "Alimentación y conducción Ø20\"", "PRESION-DIAMETROS · AC 16; 20; 24", "sin aviso",
     lambda dz, P: recta(dz, "AGUA", P, 20, AC), []),
    ("N09", "Alimentación y conducción Ø12\"", "PRESION-DIAMETROS · AC 16; 20; 24",
     "AVISO «Diámetro 12\": es de DISTRIBUCION PRINCIPAL…»",
     lambda dz, P: recta(dz, "AGUA", P, 12, AC), ["diametro"]),
    ("N10", "Instalación domiciliaria Ø1.5\"", "PRESION-DIAMETROS · DOM 1; 1,5; 2", "sin aviso",
     lambda dz, P: recta(dz, "AGUA", P, 1.5, DOM), []),
    ("N11", "Instalación domiciliaria Ø3\"", "PRESION-DIAMETROS · DOM 1; 1,5; 2",
     "AVISO «Diámetro 3\" no permitido para INSTALACION DOMICILIARIA»",
     lambda dz, P: recta(dz, "AGUA", P, 3, DOM), ["diametro"]),
    # PRESION-ACCESORIOS
    ("N12", "Wye en alimentación Ø20\" / ramal Ø16\"", "PRESION-ACCESORIOS · Y · prohibida en DP",
     "sin aviso (la Y solo está prohibida en DP)",
     lambda dz, P: te(dz, "AGUA", P, 20, 16, AC, ang=-45), []),
    ("N13", "Wye en distribución principal Ø8\" / Ø6\"", "PRESION-ACCESORIOS · Y · prohibida en DP",
     "AVISO «Wye no permitida en DISTRIBUCION PRINCIPAL»",
     lambda dz, P: te(dz, "AGUA", P, 8, 6, DP, ang=-45), ["accesorio"]),
    ("N14", "Tee DP Ø12\" con ramal Ø8\"", "PRESION-ACCESORIOS · T · ramal -1 (12 → 8)", "sin aviso",
     lambda dz, P: te(dz, "AGUA", P, 12, 8, DP), []),
    ("N15", "Tee DP Ø12\" con ramal Ø12\"", "PRESION-ACCESORIOS · T · ramal -1",
     "AVISO «Tee: el ramal debe ser 8\" (un tamaño menor que 12\")»",
     lambda dz, P: te(dz, "AGUA", P, 12, 12, DP), ["accesorio"]),
    ("N16", "Tee DP Ø6\" con ramal Ø4\"", "PRESION-ACCESORIOS · T · ramal -1 (6 no tiene menor)",
     "AVISO «Tee: no hay un tamaño menor que 6\"…» + INFO del ramal Ø4\" (cul-de-sac)",
     lambda dz, P: te(dz, "AGUA", P, 6, 4, DP), ["accesorio", "nota"]),
    ("N17", "Tee DP con principal Ø4\"", "PRESION-ACCESORIOS · T · principal 6; 8; 12; 16",
     "AVISO «Tee: la principal debe ser 6\", 8\", 12\", 16\"; es 4\"» + INFO (cul-de-sac) en las dos",
     lambda dz, P: te(dz, "AGUA", P, 4, 4, DP), ["accesorio", "nota", "nota"]),
    ("N18", "Tee en alimentación Ø20\" / Ø16\"", "PRESION-ACCESORIOS · T · solo en DP",
     "AVISO «Tee solo se permite en DISTRIBUCION PRINCIPAL»",
     lambda dz, P: te(dz, "AGUA", P, 20, 16, AC), ["accesorio"]),
    ("N19", "Cruz DP Ø8\"", "PRESION-ACCESORIOS · Cruz · principal 6; 8", "sin aviso",
     lambda dz, P: cruz(dz, "AGUA", P, 8, DP), []),
    ("N20", "Cruz DP Ø12\"", "PRESION-ACCESORIOS · Cruz · principal 6; 8",
     "AVISO «Cruz: la principal debe ser 6\", 8\"; es 12\"»",
     lambda dz, P: cruz(dz, "AGUA", P, 12, DP), ["accesorio"]),
    ("N21", "Codos DP de 11.25°, 22.5°, 45° y 90°", "PRESION-ACCESORIOS · Codo · ángulos",
     "sin aviso (etiquetas «Codo 11.25°»…)", n_codos_ok, []),
    ("N22", "Codo DP de 30°", "PRESION-ACCESORIOS · Codo · 11,25; 22,5; 45; 90",
     "AVISO «Codo de 30°: fuera de norma»", lambda dz, P: codo(dz, "AGUA", P, 30, 8, DP), ["accesorio"]),
    ("N23", "Codo de 30° en alimentación", "PRESION-ACCESORIOS · Codo · solo en DP",
     "sin aviso (fuera de DP vale cualquier ángulo)",
     lambda dz, P: codo(dz, "AGUA", P, 30, 20, AC), []),
    ("N24", "T domiciliaria: DP Ø8\" + ramal domiciliario Ø1\"", "PRESION-ACCESORIOS · T - Domiciliaria · 1; 1,5; 2",
     "sin aviso (se revisa SOLO con la fila T - Domiciliaria)",
     lambda dz, P: te(dz, "AGUA", P, 8, 1, DP, DOM), []),
    ("N25", "T domiciliaria con ramal Ø3\"", "PRESION-ACCESORIOS · T - Domiciliaria · 1; 1,5; 2",
     "AVISO «T domiciliaria: el ramal debe ser 1\", 1.5\", 2\"; es 3\"» + AVISO de diámetro del ramal",
     lambda dz, P: te(dz, "AGUA", P, 8, 3, DP, DOM), ["accesorio", "diametro"]),
    ("N26", "Codo de gas de 90°", "PRESION-ACCESORIOS · GAS · Codo · 45; 90", "sin aviso",
     lambda dz, P: codo(dz, "GAS", P, 90, 6), []),
    ("N27", "Codo de gas de 60°", "PRESION-ACCESORIOS · GAS · Codo · 45; 90",
     "AVISO «Codo de 60°: fuera de norma. Permitidos: 45°, 90°»",
     lambda dz, P: codo(dz, "GAS", P, 60, 6), ["accesorio"]),
    # ELECT-TELECOM
    ("N28", "Eléctrico DP Ø4\"", "ELECT-TELECOM · ELECTRICO DP · mínimo 3", "sin aviso",
     lambda dz, P: recta(dz, "ELECTRICO", P, 4, DP), []),
    ("N29", "Eléctrico DP Ø2\"", "ELECT-TELECOM · ELECTRICO DP · mínimo 3",
     "AVISO «Diámetro 2\": mínimo 3\"»", lambda dz, P: recta(dz, "ELECTRICO", P, 2, DP), ["electrico"]),
    ("N30", "Telecom Ø2\"", "ELECT-TELECOM · TELECOM · mínimo 4", "AVISO «Diámetro 2\": mínimo 4\"»",
     lambda dz, P: recta(dz, "TELECOM", P, 2), ["electrico"]),
    ("N31", "Eléctrico domiciliario SIN amperaje", "ELECT-TELECOM · DOM · por amperaje",
     "AVISO «Falta el amperaje: escríbelo…»",
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DOM), ["electrico"]),
    ("N32", "Eléctrico dom. 200 A, 80 ft, Ø3\"", "ELECT-TELECOM · DOM · 0-320 A · 0-100 ft · 3", "sin aviso",
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DOM, largo=80, amp=200), []),
    ("N33", "Eléctrico dom. 350 A, 150 ft, Ø3\"", "ELECT-TELECOM · DOM · 321-400 A · 101-200 ft · 4",
     "AVISO «Diámetro 3\": debe ser 4\" (… 321-400 A, 101-200 ft)»",
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DOM, largo=150, amp=350), ["electrico"]),
    ("N34", "Eléctrico dom. 350 A, 150 ft, Ø4\"", "ELECT-TELECOM · DOM · 321-400 A · 101-200 ft · 4", "sin aviso",
     lambda dz, P: recta(dz, "ELECTRICO", P, 4, DOM, largo=150, amp=350), []),
    ("N35", "Eléctrico dom. 350 A, 80 ft, Ø4\"", "ELECT-TELECOM · DOM · 321-400 A · 0-100 ft · 3",
     "AVISO «Diámetro 4\": debe ser 3\"»",
     lambda dz, P: recta(dz, "ELECTRICO", P, 4, DOM, largo=80, amp=350), ["electrico"]),
    ("N36", "Eléctrico dom. 500 A", "ELECT-TELECOM · ninguna fila llega a 500 A",
     "sin aviso: fuera de la tabla no se revisa",
     lambda dz, P: recta(dz, "ELECTRICO", P, 4, DOM, largo=80, amp=500), []),
]


# ─────────────────────────── otras novedades (X) ───────────────────────────
# (código, título, cómo mostrarlo, función, avisos de normativa, revisión antes de exportar)
# Revisión = [(tipo de `limpieza`, arreglado)].

def x_bloque(dz, P):
    for k in range(4):
        recta(dz, "ELECTRICO", (P[0], P[1] + 30 - 20 * k), 4, largo=120)


def x_copiar(dz, P):
    recta(dz, "AGUA", (P[0], P[1] + 30), 8, DP, largo=120, name="Fuente")
    for k in range(2):
        recta(dz, "AGUA", (P[0], P[1] - 10 - 25 * k), 12, largo=120)


def x_unir(dz, P):
    a, b, c, d = (P[0] - 90, P[1]), (P[0] - 30, P[1]), (P[0] + 30, P[1] + 12), (P[0] + 90, P[1] + 12)
    for u, v in ((a, b), (b, c), (c, d)):
        dz.util("DRENAJE", [u, v], 18, inv=(-6.0, -6.2))


def x_punta(dz, P):
    recta(dz, "TELECOM", P, 4, largo=120)
    dz.util("TELECOM", [(P[0], P[1] - 0.5), (P[0], P[1] - L)], 4)


def x_corta(dz, P):
    recta(dz, "TELECOM", P, 4, largo=120)
    dz.util("TELECOM", [(P[0] + 60, P[1]), (P[0] + 60.6, P[1])], 4)


def x_repetida(dz, P):
    recta(dz, "TELECOM", P, 4, largo=120)
    recta(dz, "TELECOM", P, 4, largo=120)


def x_suelta(dz, P):
    recta(dz, "TELECOM", (P[0], P[1] + 20), 4, largo=120)
    dz.util("TELECOM", [(P[0] - 1.5, P[1] - 30), (P[0] + 1.5, P[1] - 30)], 4)


def x_quiebres(dz, P):
    b = pol(P, 30, 0.3)
    dz.util("TELECOM", [(P[0] - L, P[1]), P, b, (b[0] + L, b[1])], 4)


def x_curva_t(dz, P):
    x0 = P[0] - 30
    dz.util("TELECOM", [(x0, P[1] - 50), (x0, P[1] + 50)], 4)
    esquina = (x0 + 30.0, P[1])
    dz.util("TELECOM", [(x0, P[1]), esquina, (esquina[0], P[1] + 50)], 4)
    ex, ey = dz.px(*esquina)
    dz.w.structures.append({"cod": "", "x": ex, "y": ey, "curve": True, "radius_ft": 29.9,
                            "net": "conduit", "world": False, "hidden": False, "rim": None,
                            "sump": None, "part": "", "part_size": "", "covered": True})


def x_choque(dz, P):
    recta(dz, "TELECOM", P, 4, largo=120, inv=(-6.0, -6.0))
    dz.util("DRENAJE", [(P[0], P[1] - 50), (P[0], P[1] + 50)], 18, inv=(-6.0, -6.0))


def x_bancoducto(dz, P):
    from nucleo.duct_bank import Conduit, DuctBank
    a = recta(dz, "TELECOM", (P[0], P[1] + 15), 4, largo=120)
    b = recta(dz, "TELECOM", (P[0], P[1] - 25), 4, largo=120)
    db = DuctBank(name="DB-PRESENTACION", width_in=24.0, height_in=16.0,
                  conduits=[Conduit(7.0, 8.0, 4.0, "T1"), Conduit(17.0, 8.0, 4.0, "T2")])
    db.assign([a, b])
    dz.w.duct_banks.append(db)


def x_solido(dz, P):
    fin = (P[0] + 40, P[1])
    dz.util("TELECOM", [(P[0] - 70, P[1]), fin], 4)
    largo, ancho = 10.0, 6.0
    esquinas = [(fin[0] - largo / 2, fin[1] - ancho / 2), (fin[0] + largo / 2, fin[1] - ancho / 2),
                (fin[0] + largo / 2, fin[1] + ancho / 2), (fin[0] - largo / 2, fin[1] + ancho / 2)]
    cx, cy = dz.px(*fin)
    dz.w.structures.append({"cod": "", "x": cx, "y": cy, "net": "conduit", "shape": "rect",
                            "outline": [dz.px(*q) for q in esquinas], "width_ft": ancho,
                            "length_ft": largo, "rot_deg": 0.0, "world": False, "hidden": False,
                            "rim": None, "sump": None, "part": "", "part_size": "", "covered": True})


def x_defecto(dz, P):
    recta(dz, "AGUA", P, None, DP, largo=120)


CASOS_X = [
    ("X01", "Editar en bloque (4 eléctricas sin tipo)",
     "Ctrl+clic en las 4 → Ctrl+E → Tipo = DISTRIBUCION PRINCIPAL: se van los 4 avisos «Sin tipo». "
     "Ctrl+Z lo deshace.", x_bloque, ["tipo"] * 4, []),
    ("X02", "Copiar y pegar propiedades",
     "Selecciona «Fuente» (DP Ø8\") → Ctrl+Shift+C; selecciona las otras dos → Ctrl+Shift+V.",
     x_copiar, ["tipo"] * 2, []),
    ("X03", "Unir utilidades (3 tramos de drenaje)",
     "Ctrl+clic en los 3 tramos → Ctrl+J: queda UNA utilidad (vista previa verde).", x_unir, [], []),
    ("X04", "Punta que casi toca otra línea (0.5 ft)",
     "Exportar DXF → «Antes de exportar»: «líneas que casi tocan a otra: se unirán».", x_punta, [],
     [("punta", True)]),
    ("X05", "Utilidad de 0.6 ft", "Antes de exportar: «utilidades muy cortas: se borrarán».", x_corta, [],
     [("corta", True)]),
    ("X06", "Utilidad repetida (dos iguales)", "Antes de exportar: «utilidades repetidas: se borrará una».",
     x_repetida, [], [("duplicada", True)]),
    ("X07", "Utilidad suelta de 3 ft", "Herramientas → Revisar y limpiar el dibujo: solo AVISO (no se toca).",
     x_suelta, [], [("suelta", False)]),
    ("X08", "Tramo de 0.3 ft entre dos quiebres",
     "En Civil 3D sería una tubería diminuta: el DXF sale SIEMPRE sin ella (se quita un vértice).",
     x_quiebres, [], [("tramo", True)]),
    ("X09", "Curva que llega a 0.1 ft de la T",
     "Tubería diminuta entre la T y la curva: la curva se estira hasta la T (r 29.9 → 30 ft).",
     x_curva_t, [], [("tramo", True)]),
    ("X10", "Telecom × drenaje a la misma cota", "Alerta roja «Tuberías que chocan» (en cualquier utilidad).",
     x_choque, [], []),
    ("X11", "Un bancoducto en DOS utilidades",
     "Selecciona una: el panel dice su bancoducto; en el DXF va un PDFCAD_DUCTBANK por utilidad.",
     x_bancoducto, [], []),
    ("X12", "Sólido al final de una línea de telecom",
     "Buzones → SÓLIDO-1: Largo/Ancho/Altura y Cota superior automática (el eje llega al centro).",
     x_solido, [], []),
    ("X13", "Agua DP sin tamaño elegido", "Panel: Diámetro 12\" (Por defecto); 12\" está en DP: sin aviso.",
     x_defecto, [], []),
]


# ─────────────────────────── armado ───────────────────────────

def centro(i):
    col, fila = i % COLS, i // COLS
    return (col * CELDA_X + CELDA_X / 2, ALTO_FT - TITULO_FT - (fila * CELDA_Y + CELDA_Y / 2) - 15)


def _etiqueta(dz, P, lineas):
    x0, y0 = P[0] - CELDA_X / 2 + 6, P[1] + 112          # justo encima del dibujo (llega a +60)
    dz.texto((x0, y0), "\n".join(lineas), ALTO_TEXTO)


def construir(win):
    """Dibuja todos los casos en `win`. Devuelve {código: dict(P, pipes, avisos, revision)}."""
    win.blank_canvas = True
    win.paper = dict(HOJA)
    win._load_blank_page(HOJA)
    dz = Dibujo(win)
    dz.texto((10, ALTO_FT - 8), TITULO, 9.0)
    datos = {}
    todos = [(c, t, f"Excel: {ex}", f"Debe salir: {esp}", fn, av, [])
             for c, t, ex, esp, fn, av in CASOS_N]
    todos += [(c, t, f"Cómo: {como}", None, fn, av, rev) for c, t, como, fn, av, rev in CASOS_X]
    for i, (cod, titulo, l2, l3, fn, avisos, revision) in enumerate(todos):
        P = centro(i if cod.startswith("N") else COLS * 4 + (i - len(CASOS_N)))
        antes = len(win.pipes)
        fn(dz, P)
        datos[cod] = dict(P=P, pipes=list(range(antes, len(win.pipes))), avisos=avisos, revision=revision)
        lineas = textwrap.wrap(f"{cod} · {titulo}", ANCHO_ETIQUETA)
        lineas += textwrap.wrap(l2, ANCHO_ETIQUETA, subsequent_indent="   ")
        if l3:
            lineas += textwrap.wrap(l3, ANCHO_ETIQUETA, subsequent_indent="   ")
        _etiqueta(dz, P, lineas)
    win._rebuild_structures()
    win._refresh_lists()
    win._redraw()
    return datos


def _caso_de(datos, pipe):
    return next((c for c, d in datos.items() if pipe in d["pipes"]), None)


def avisos_por_caso(win, datos):
    """{código: [clases de aviso]} con lo que dice la app ahora."""
    out = {c: [] for c in datos}
    for a in win._normas_avisos:
        c = _caso_de(datos, a.pipe)
        out.setdefault(c, []).append(a.clase)
    return out


def revision_por_caso(win, datos):
    """{código: [(tipo, arreglado)]} de la revisión antes de exportar (sobre COPIAS)."""
    from nucleo import limpieza
    ft = win.scale / win.zoom
    res = limpieza.limpiar(copy.deepcopy(win.pipes), copy.deepcopy(win.structures), ft)
    out = {c: [] for c in datos}
    for ch in res.cambios:
        out.setdefault(_caso_de(datos, ch.pipe), []).append((ch.tipo, ch.arreglado))
    return out


def comparar(win, datos):
    """[(código, qué, esperado, obtenido)] de lo que NO coincide."""
    malos = []
    av, rev = avisos_por_caso(win, datos), revision_por_caso(win, datos)
    for c in sorted(set(datos) | set(av) | set(rev), key=str):
        esp = datos.get(c, {})
        if sorted(av.get(c, [])) != sorted(esp.get("avisos", [])):
            malos.append((c, "avisos", sorted(esp.get("avisos", [])), sorted(av.get(c, []))))
        if sorted(rev.get(c, [])) != sorted(esp.get("revision", [])):
            malos.append((c, "revisión", sorted(esp.get("revision", [])), sorted(rev.get(c, []))))
    return malos


def generar(ruta=SALIDA):
    import tempfile
    os.environ.setdefault("PDFCAD_NORMAS_TABLAS", os.path.join(tempfile.mkdtemp(), "normas.json"))
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    win = Main()
    from nucleo import normas_catalogo
    win.normas_cat = normas_catalogo.nuevo()          # las normativas de fábrica
    datos = construir(win)
    win.project_path = ruta
    win._write_project(ruta)
    return win, datos


if __name__ == "__main__":
    win, datos = generar()
    print(f"Proyecto: {SALIDA}")
    print(f"{len(CASOS_N)} casos de normativas + {len(CASOS_X)} novedades · {len(win.pipes)} utilidades · "
          f"{len(win.structures)} estructuras · {sum(1 for a in win._normas_avisos if not a.info)} avisos")
    malos = comparar(win, datos)
    for c, que, esp, obt in malos:
        print(f"  XX {c} {que}: esperado {esp}, obtenido {obt}")
    print("Todo como se esperaba." if not malos else f"{len(malos)} diferencias.")
    win._dirty = False
