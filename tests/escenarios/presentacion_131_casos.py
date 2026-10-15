"""Casos de la presentación 1.3.1 (los usa `generar_presentacion_131.py`).

N = una regla del Excel de normativas `normativas_1_3_1.xlsx` (el que corrigió el ingeniero:
rangos en columnas MIN/MAX y radio de curva), el caso que cumple y el que no.
X = otras novedades que se ven sin PDF.

Cada caso N: (código, título, hoja del Excel, regla en palabras simples, qué debe salir,
función que lo dibuja con centro P, avisos esperados = clases de `normas_validar.CLASES`).
"""
from generar_escenarios import pol

L = 60.0                                      # largo típico de un tramo (ft)
DP, AC, DOM = "DISTRIBUCION PRINCIPAL", "ALIMENTACION Y CONDUCCION", "INSTALACION DOMICILIARIA"
RES, COM = "SERVICIO RESIDENCIAL", "SERVICIO COMERCIAL/MULTIFAMILIAR"
DIM = "DIMENSIONAMIENTO RESIDENCIAL"
SIN = "sin aviso"


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


def curva(dz, capa, P, d, tipo, radio):
    """Línea que gira 90° en P con una CURVA de `radio` ft (None = radio automático)."""
    i = dz.util(capa, [(P[0] - L, P[1] - 20), (P[0], P[1] - 20), (P[0], P[1] + L - 20)], d, tipo)
    x, y = dz.px(P[0], P[1] - 20)
    dz.w.structures.append({"cod": "", "x": x, "y": y, "curve": True, "radius_ft": float(radio or 0.0),
                            "net": "conduit", "world": False, "hidden": False, "rim": None, "sump": None,
                            "part": "", "part_size": "", "covered": True})
    return i


def n_codos_ok(dz, P):
    for k, defl in enumerate((11.25, 22.5, 45.0, 90.0)):
        q = (P[0] + (-55 if k % 2 == 0 else 55), P[1] + (15 if k < 2 else -55))
        codo(dz, "AGUA", q, defl, 8, DP, leg=40)


# ─────────────────────────── normativas (N) ───────────────────────────

_T, _D, _A, _E = "TIPOS", "PRESION-DIAMETROS", "PRESION-ACCESORIOS", "ELECT-TELECOM"
def info_gas(nota):
    return f"solo INFO celeste con la nota de la fila («{nota}»)"

CASOS_N = [
    # ── TIPOS ──
    ("N01", "Agua sin tipo", _T, "toda utilidad con tipos en la hoja TIPOS debe tener uno elegido.",
     "AVISO «Sin tipo» (se ve en el panel y en la lista, no en el plano)",
     lambda dz, P: recta(dz, "AGUA", P, 8), ["tipo"]),
    ("N02", "Agua con tipo «RIEGO»", _T, "el tipo debe existir en la hoja TIPOS; «RIEGO» no está.",
     "AVISO «El tipo RIEGO ya no está en la lista»",
     lambda dz, P: recta(dz, "AGUA", P, 8, "RIEGO"), ["tipo"]),
    ("N03", "Gas sin tipo", _T, "el gas ahora tiene tipos (Residencial, Comercial, Distribución principal).",
     "AVISO «Sin tipo»", lambda dz, P: recta(dz, "GAS", P, 1), ["tipo"]),
    ("N04", "Telecom sin tipo", _T, "telecom tiene el tipo Distribución principal (sale de ELECT-TELECOM).",
     "AVISO «Sin tipo»", lambda dz, P: recta(dz, "TELECOM", P, 4), ["tipo"]),
    # ── PRESION-DIAMETROS · agua (listas) ──
    ("N05", "Agua DP Ø8\"", _D, "Distribución principal: 6, 8, 12 o 16 pulgadas. 8\" está en la lista.", SIN,
     lambda dz, P: recta(dz, "AGUA", P, 8, DP), []),
    ("N06", "Agua DP Ø4\" (cul-de-sac)", _D, "4\" se permite en DP solo en calles sin salida (otra fila).",
     "INFO celeste «solo se permite en CALLES SIN SALIDA…» (no es un error)",
     lambda dz, P: recta(dz, "AGUA", P, 4, DP), ["nota"]),
    ("N07", "Agua DP Ø10\"", _D, "10\" no está en ninguna lista de agua.",
     "AVISO «Diámetro 10\" no permitido para DP»", lambda dz, P: recta(dz, "AGUA", P, 10, DP), ["diametro"]),
    ("N08", "Agua DP Ø2\"", _D, "2\" es de Instalación domiciliaria, no de DP.",
     "AVISO «Diámetro 2\": es de INSTALACION DOMICILIARIA…»",
     lambda dz, P: recta(dz, "AGUA", P, 2, DP), ["diametro"]),
    ("N09", "Agua alimentación Ø20\"", _D, "Alimentación y conducción: 16, 20 o 24 pulgadas.", SIN,
     lambda dz, P: recta(dz, "AGUA", P, 20, AC), []),
    ("N10", "Agua alimentación Ø12\"", _D, "12\" es de Distribución principal, no de alimentación.",
     "AVISO «Diámetro 12\": es de DISTRIBUCION PRINCIPAL…»",
     lambda dz, P: recta(dz, "AGUA", P, 12, AC), ["diametro"]),
    ("N11", "Agua domiciliaria Ø1.5\"", _D, "Instalación domiciliaria: 1, 1,5 o 2 pulgadas.", SIN,
     lambda dz, P: recta(dz, "AGUA", P, 1.5, DOM), []),
    ("N12", "Agua domiciliaria Ø3\"", _D, "3\" no está en la lista de domiciliaria.",
     "AVISO «Diámetro 3\" no permitido para INSTALACION DOMICILIARIA»",
     lambda dz, P: recta(dz, "AGUA", P, 3, DOM), ["diametro"]),
    # ── PRESION-DIAMETROS · gas (Excel v4: listas en residencial y comercial, MIN 6 en DP) ──
    ("N13", "Gas residencial Ø1\"", _D, "Residencial: lista 0,5; 1; 1,5; 2. 1\" está en la lista.",
     info_gas("USO RESIDENCIAL"), lambda dz, P: recta(dz, "GAS", P, 1, RES), ["nota"]),
    ("N14", "Gas residencial Ø0.5\"", _D, "0,5\" también está en la lista de residencial.",
     info_gas("USO RESIDENCIAL"), lambda dz, P: recta(dz, "GAS", P, 0.5, RES), ["nota"]),
    ("N15", "Gas residencial Ø4\"", _D, "4\" no está en la lista de residencial; está en la de Comercial.",
     "AVISO «Diámetro 4\": es de SERVICIO COMERCIAL/MULTIFAMILIAR…»",
     lambda dz, P: recta(dz, "GAS", P, 4, RES), ["diametro"]),
    ("N16", "Gas comercial Ø4\"", _D, "Comercial: lista 2; 4. 4\" está en la lista.",
     info_gas("USO COMERCIAL O MULTIFAMILIAR"), lambda dz, P: recta(dz, "GAS", P, 4, COM), ["nota"]),
    ("N17", "Gas comercial Ø3\"", _D, "La lista de comercial es 2 y 4: 3\" no vale (no es un rango).",
     "AVISO «Diámetro 3\" no permitido para SERVICIO COMERCIAL…»",
     lambda dz, P: recta(dz, "GAS", P, 3, COM), ["diametro"]),
    ("N18", "Gas DP Ø8\"", _D, "DP: «mayores a 4\"» = MIN 6 y MAX vacía (sin límite). 8\" vale.",
     info_gas("TUBERIAS PRINCIPALES"), lambda dz, P: recta(dz, "GAS", P, 8, DP), ["nota"]),
    ("N19", "Gas DP Ø4\"", _D, "4\" no es «mayor a 4»: queda debajo del MIN 6 (es de Comercial).",
     "AVISO «Diámetro 4\": es de SERVICIO COMERCIAL/MULTIFAMILIAR…»",
     lambda dz, P: recta(dz, "GAS", P, 4, DP), ["diametro"]),
    # ── PRESION-ACCESORIOS ──
    ("N20", "Wye en agua alimentación", _A, "La Y está PROHIBIDA solo en DP; en alimentación vale.", SIN,
     lambda dz, P: te(dz, "AGUA", P, 20, 16, AC, ang=-45), []),
    ("N21", "Wye en agua DP Ø8\" / Ø6\"", _A, "La Y está prohibida en Distribución principal.",
     "AVISO «Wye no permitida en DISTRIBUCION PRINCIPAL»",
     lambda dz, P: te(dz, "AGUA", P, 8, 6, DP, ang=-45), ["accesorio"]),
    ("N22", "Tee DP Ø12\" + ramal Ø8\"", _A, "Tee en DP: el ramal es un tamaño menor en la lista (12 → 8).",
     SIN, lambda dz, P: te(dz, "AGUA", P, 12, 8, DP), []),
    ("N23", "Tee DP Ø12\" + ramal Ø12\"", _A, "El ramal debe ser un tamaño menor (-1): con 12\" debe ser 8\".",
     "AVISO «Tee: el ramal debe ser 8\"…»", lambda dz, P: te(dz, "AGUA", P, 12, 12, DP), ["accesorio"]),
    ("N24", "Tee DP Ø6\" + ramal Ø4\"", _A, "6\" es el más chico de la lista: no tiene un tamaño menor.",
     "AVISO «Tee: no hay un tamaño menor que 6\"» + INFO del ramal 4\" (cul-de-sac)",
     lambda dz, P: te(dz, "AGUA", P, 6, 4, DP), ["accesorio", "nota"]),
    ("N25", "Tee DP con principal Ø4\"", _A, "La principal de una Tee debe ser 6, 8, 12 o 16 pulgadas.",
     "AVISO «Tee: la principal debe ser 6\", 8\", 12\", 16\"» + INFO (cul-de-sac) en las dos",
     lambda dz, P: te(dz, "AGUA", P, 4, 4, DP), ["accesorio", "nota", "nota"]),
    ("N26", "Tee en agua alimentación", _A, "La Tee solo se permite en Distribución principal.",
     "AVISO «Tee solo se permite en DISTRIBUCION PRINCIPAL»",
     lambda dz, P: te(dz, "AGUA", P, 20, 16, AC), ["accesorio"]),
    ("N27", "Cruz DP Ø8\"", _A, "Cruz solo en DP y con principal de 6 u 8 pulgadas.", SIN,
     lambda dz, P: cruz(dz, "AGUA", P, 8, DP), []),
    ("N28", "Cruz DP Ø12\"", _A, "La principal de la Cruz debe ser 6\" u 8\".",
     "AVISO «Cruz: la principal debe ser 6\", 8\"; es 12\"»",
     lambda dz, P: cruz(dz, "AGUA", P, 12, DP), ["accesorio"]),
    ("N29", "Codos DP 11.25°, 22.5°, 45°, 90°", _A, "En DP el codo solo puede ser de 11,25, 22,5, 45 o 90°.",
     "sin aviso (etiquetas «Codo 11.25°»…)", n_codos_ok, []),
    ("N30", "Codo DP de 30°", _A, "30° no está en la lista de ángulos de DP.", "AVISO «Codo de 30°: fuera de norma»",
     lambda dz, P: codo(dz, "AGUA", P, 30, 8, DP), ["accesorio"]),
    ("N31", "Codo de 30° en alimentación", _A, "Los ángulos se exigen solo en DP: fuera de DP vale cualquiera.",
     SIN, lambda dz, P: codo(dz, "AGUA", P, 30, 20, AC), []),
    ("N32", "T domiciliaria: DP Ø8\" + ramal 1\"", _A,
     "Si el ramal es domiciliario se usa SOLO la fila «T - Domiciliaria»: ramal de 1, 1,5 o 2\".", SIN,
     lambda dz, P: te(dz, "AGUA", P, 8, 1, DP, DOM), []),
    ("N33", "T domiciliaria con ramal 3\"", _A, "El ramal domiciliario debe ser 1, 1,5 o 2 pulgadas.",
     "AVISO «T domiciliaria: el ramal debe ser 1\", 1.5\", 2\"» + AVISO de diámetro del ramal",
     lambda dz, P: te(dz, "AGUA", P, 8, 3, DP, DOM), ["accesorio", "diametro"]),
    ("N34", "Codo de gas de 90°", _A, "En gas el codo puede ser de 45° o 90° (en cualquier tipo).",
     "sin aviso del codo (solo la INFO de la tubería DP Ø8\")",
     lambda dz, P: codo(dz, "GAS", P, 90, 8, DP), ["nota"]),
    ("N35", "Codo de gas de 60°", _A, "60° no está en la lista del gas (45, 90).",
     "AVISO «Codo de 60°: fuera de norma. Permitidos: 45°, 90°» (+ INFO de la tubería)",
     lambda dz, P: codo(dz, "GAS", P, 60, 8, DP), ["accesorio", "nota"]),
    # ── ELECT-TELECOM · diámetro ──
    ("N36", "Eléctrico DP Ø4\"", _E, "Eléctrico DP: diámetro MIN 2\" (sin máximo). 4\" vale.", SIN,
     lambda dz, P: recta(dz, "ELECTRICO", P, 4, DP), []),
    ("N37", "Eléctrico DP Ø1\"", _E, "1\" es menos que el MIN de 2\".", "AVISO «Diámetro 1\": mínimo 2\"»",
     lambda dz, P: recta(dz, "ELECTRICO", P, 1, DP), ["electrico"]),
    ("N38", "Telecom DP Ø2\" (borde)", _E, "Telecom DP: MIN 2\". 2\" = el MIN, vale.", SIN,
     lambda dz, P: recta(dz, "TELECOM", P, 2, DP), []),
    ("N39", "Telecom DP Ø1\"", _E, "1\" es menos que el MIN de 2\".", "AVISO «Diámetro 1\": mínimo 2\"»",
     lambda dz, P: recta(dz, "TELECOM", P, 1, DP), ["electrico"]),
    # ── ELECT-TELECOM · amperaje y largo (rangos MIN / MAX, nuevo) ──
    ("N40", "Dimensionamiento resid. SIN amperaje", _E,
     "Sus filas dependen del amperaje: sin el dato no se puede saber cuál usar.",
     "AVISO «Falta el amperaje: escríbelo…»", lambda dz, P: recta(dz, "ELECTRICO", P, 3, DIM), ["electrico"]),
    ("N41", "Resid. 200 A, 80 ft, Ø3\"", _E, "Fila 0–320 A y 0–100 ft: diámetro MIN 3\". 3\" vale.", SIN,
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DIM, largo=80, amp=200), []),
    ("N42", "Resid. 200 A, 80 ft, Ø2\"", _E, "Misma fila (0–320 A, 0–100 ft): 2\" es menos que el MIN 3\".",
     "AVISO «Diámetro 2\": mínimo 3\" (… 0-320 A, 0-100 ft)»",
     lambda dz, P: recta(dz, "ELECTRICO", P, 2, DIM, largo=80, amp=200), ["electrico"]),
    ("N43", "Resid. 300 A, 150 ft, Ø3\"", _E, "Fila 0–320 A y 101–200 ft: MIN 3\". 3\" vale.", SIN,
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DIM, largo=150, amp=300), []),
    ("N44", "Resid. 400 A, 80 ft, Ø3\" (borde)", _E,
     "«400 A o más» = AMPERAJE MIN 400, MAX vacía. 400 A entra; fila 0–100 ft: MIN 3\".", SIN,
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DIM, largo=80, amp=400), []),
    ("N45", "Resid. 500 A, 150 ft, Ø3\"", _E, "500 A (≥ 400) y 101–200 ft: esa fila pide MIN 4\".",
     "AVISO «Diámetro 3\": mínimo 4\" (… ≥ 400 A, 101-200 ft)»",
     lambda dz, P: recta(dz, "ELECTRICO", P, 3, DIM, largo=150, amp=500), ["electrico"]),
    ("N46", "Resid. 500 A, 150 ft, Ø4\"", _E, "Misma fila (≥ 400 A, 101–200 ft): 4\" = el MIN, vale.", SIN,
     lambda dz, P: recta(dz, "ELECTRICO", P, 4, DIM, largo=150, amp=500), []),
    ("N47", "Resid. 350 A (hueco del Excel)", _E,
     "Ninguna fila cubre 321–399 A: la app no tiene con qué revisarla. Falta en el Excel.",
     "sin aviso (no se revisa)", lambda dz, P: recta(dz, "ELECTRICO", P, 2, DIM, largo=80, amp=350), []),
    ("N48", "Resid. 200 A, 250 ft", _E, "Ninguna fila llega a 250 ft (MAX 200): no se revisa.",
     "sin aviso (no se revisa)", lambda dz, P: recta(dz, "ELECTRICO", P, 2, DIM, largo=250, amp=200), []),
    # ── ELECT-TELECOM · radio de curva FIJO (Excel v4: «3;4») ──
    ("N49", "Eléctrico DP: curva de 3 ft", _E, "RADIO CURVA FIJO 3; 4: la curva es de 3 o de 4 ft. 3 ft vale.", SIN,
     lambda dz, P: curva(dz, "ELECTRICO", P, 4, DP, 3), []),
    ("N50", "Eléctrico DP: curva de 4 ft", _E, "4 ft también está en RADIO CURVA FIJO.", SIN,
     lambda dz, P: curva(dz, "ELECTRICO", P, 4, DP, 4), []),
    ("N51", "Eléctrico DP: curva de 3.5 ft", _E, "Es FIJO, no un rango: 3,5 ft no es ni 3 ni 4.",
     "AVISO en la curva «Curva de radio 3,5 ft: debe ser 3 ft, 4 ft»",
     lambda dz, P: curva(dz, "ELECTRICO", P, 4, DP, 3.5), ["radio"]),
    ("N52", "Eléctrico DP: curva de 10 ft", _E, "10 ft no está en RADIO CURVA FIJO (3; 4).",
     "AVISO en la curva «Curva de radio 10 ft: debe ser 3 ft, 4 ft»",
     lambda dz, P: curva(dz, "ELECTRICO", P, 4, DP, 10), ["radio"]),
    ("N53", "Eléctrico DP: curva automática Ø4\"", _E,
     "Sin radio escrito, la app usa 6 × diámetro = 2 ft: no es 3 ni 4.",
     "AVISO «Curva de radio 2 ft (automático): debe ser 3 ft, 4 ft»",
     lambda dz, P: curva(dz, "ELECTRICO", P, 4, DP, None), ["radio"]),
    ("N54", "Telecom DP: curva de 10 ft", _E, "La fila de telecom no tiene RADIO CURVA: cualquier radio vale.",
     SIN, lambda dz, P: curva(dz, "TELECOM", P, 4, DP, 10), []),
]
