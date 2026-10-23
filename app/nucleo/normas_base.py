"""Normativas de fábrica en la tabla única de reglas (PURO). 2026-10-21, pedido del usuario: sumar las normativas
que había + el Excel del ingeniero (manda donde cambia algo; lo viejo que cambió se quitó) + lo que se PUEDE
MEDIR de los dos Word («criterios para reubicación_agua, alcant_drena» y «Normativa Eléctrica y Telecom»).

Lo que la app no puede medir (caudales, velocidades, presiones, profundidades sin terreno, camas, sondeos) queda
como «Solo referencia»: escrito, con su fuente, sin avisos. Ver `normas_reglas` para el significado de cada
columna.
"""
from __future__ import annotations

from nucleo.normas_reglas import (BUZON, CODO, CRUZ, CUALQUIERA, CURVA, T, T_DOM, TUBERIA, Y, regla_vacia)

EXCEL = "Normativas (Excel del ingeniero)"
LADWP = "LADWP Design Standards 2023"
BOE_F200 = "LA Sewer Design Manual F200"
BOE_F300 = "LA Sewer Design Manual F300"
BOE_F400 = "LA Sewer Design Manual F400"
BOE_F500 = "LA Sewer Design Manual F500"
LA_ALC = "LA Sewer Design Manual (resumen)"
CAL = "California Waterworks Standards (agua/alcantarillado)"
MRDC = "Metro MRDC Sección 3 Civil"
GO128 = "CPUC GO 128"
SPEC104 = "LADWP Spec 104"
ESR = "LADWP Electric Service Requirements 2025"

DP, AC, ID, LT = "DISTRIBUCION PRINCIPAL", "ALIMENTACION Y CONDUCCION", "INSTALACION DOMICILIARIA", "LINEA TRONCAL"
COLECTOR, HC = "COLECTOR", "CONEXION DOMICILIARIA"
SD_COL, SD_LAT, SD_SUB, SD_SUM = "COLECTOR PRINCIPAL", "LATERAL", "SUBDRENAJE", "CONEXION DE SUMIDERO"

TIPOS = [
    ["AGUA", DP], ["AGUA", AC], ["AGUA", ID], ["AGUA", LT],
    ["ALCANTARILLADO", COLECTOR], ["ALCANTARILLADO", HC],
    ["DRENAJE", SD_COL], ["DRENAJE", SD_LAT], ["DRENAJE", SD_SUB], ["DRENAJE", SD_SUM],
    ["GAS", "SERVICIO RESIDENCIAL"], ["GAS", "SERVICIO COMERCIAL/MULTIFAMILIAR"], ["GAS", DP],
    ["ELECTRICO", DP], ["ELECTRICO", ID],
]


def R(utilidad, tipo, elemento, revisar, minimo=None, maximo=None, valores=(), fuente="", nota="", nivel="AVISO",
      si_diam=None, si_amp=None, si_largo=None, si_material=(), con="", con_tipo=""):
    return regla_vacia(utilidad=utilidad, tipo=tipo, elemento=elemento, revisar=revisar, min=minimo, max=maximo,
                       valores=list(valores), fuente=fuente, nota=nota, nivel=nivel, si_diam=si_diam,
                       si_amp=si_amp, si_largo=si_largo, si_material=list(si_material), con_utilidad=con,
                       con_tipo=con_tipo)


_ANG = [11.25, 22.5, 45, 90]

REGLAS = [
    # ── AGUA (Excel del ingeniero) ──
    R("AGUA", DP, TUBERIA, "diametro", valores=[6, 8, 12, 16], fuente=EXCEL),
    R("AGUA", DP, TUBERIA, "diametro", valores=[4], fuente=EXCEL,
      nota="CALLES SIN SALIDA (cul-de-sacs), donde no necesiten hidrantes mayores a 2 pulgadas"),
    R("AGUA", AC, TUBERIA, "diametro", valores=[16, 20, 24], fuente=EXCEL),
    R("AGUA", ID, TUBERIA, "diametro", valores=[1, 1.5, 2], fuente=EXCEL),
    R("AGUA", DP, Y, "permitido", valores=["NO"], fuente=EXCEL),
    R("AGUA", AC, Y, "permitido", valores=["NO"], fuente=EXCEL),
    R("AGUA", "", T, "solo_en", valores=[DP, AC], fuente=EXCEL),
    R("AGUA", DP, T, "diam_principal", valores=[6, 8, 12, 16], fuente=EXCEL),
    R("AGUA", DP, T, "ramal_pasos", valores=[-1], fuente=EXCEL),
    R("AGUA", AC, T, "diam_principal", valores=[16, 20, 24], fuente=EXCEL),
    R("AGUA", AC, T, "ramal_pasos", valores=[-1], fuente=EXCEL),
    R("AGUA", "", CRUZ, "solo_en", valores=[DP, AC], fuente=EXCEL),
    R("AGUA", DP, CRUZ, "diam_principal", valores=[6, 8, 12, 16], fuente=EXCEL),
    R("AGUA", AC, CRUZ, "diam_principal", valores=[16, 20, 24], fuente=EXCEL),
    R("AGUA", DP, CODO, "angulo", valores=_ANG, fuente=EXCEL),
    R("AGUA", AC, CODO, "angulo", valores=_ANG, fuente=EXCEL),
    R("AGUA", "", T_DOM, "diam_ramal", valores=[1, 1.5, 2], fuente=EXCEL),
    R("AGUA", "", T_DOM, "angulo", valores=[45, 90], fuente=EXCEL),
    # ── AGUA (Word) ──
    R("AGUA", LT, TUBERIA, "diametro", minimo=24, fuente=LADWP),
    R("AGUA", "", TUBERIA, "material", valores=["Fundición dúctil"], fuente=LADWP,
      nota="Hierro dúctil (DI) o acero soldado (WSP)."),
    R("AGUA", "", TUBERIA, "sep_h", minimo=10, con="ALCANTARILLADO", fuente=CAL,
      nota="Paralelo: 10 ft entre bordes. Prohibido en la misma zanja."),
    R("AGUA", "", TUBERIA, "encima", minimo=1, con="ALCANTARILLADO", fuente=CAL,
      nota="En el cruce el agua pasa al menos 1 ft por encima del alcantarillado."),
    R("AGUA", "", TUBERIA, "sep_h", minimo=10, con="DRENAJE", fuente=LA_ALC),
    R("AGUA", "", TUBERIA, "encima", minimo=1, con="DRENAJE", fuente=LA_ALC),
    R("AGUA", "", TUBERIA, "sep_h_ejes", minimo=4, con=CUALQUIERA, fuente=LADWP,
      nota="4 ft de centro a centro respecto a otras subestructuras (2 ft libres entre zanjas)."),
    R("AGUA", "", TUBERIA, "referencia", fuente=LADWP,
      nota="Cobertura mínima a la rasante: 2 ft (servicios hasta 2\"), 2,5 ft y 3 ft según el tamaño."),
    R("AGUA", "", TUBERIA, "referencia", fuente=LADWP,
      nota="Presión mínima 43 psi (doméstica en hora pico), 20 psi en el hidrante crítico; válvulas cada "
           "600–1200 ft en tuberías de 12\" o menores."),
    R("AGUA", "", TUBERIA, "referencia", fuente=CAL,
      nota="A 25 ft o más de una línea principal de agua de baja presión (5 psi o menos)."),
    # ── GAS (lo que había; el Excel no lo cambia) ──
    R("GAS", "SERVICIO RESIDENCIAL", TUBERIA, "diametro", valores=[0.5, 1, 1.5, 2]),
    R("GAS", "SERVICIO COMERCIAL/MULTIFAMILIAR", TUBERIA, "diametro", valores=[2, 4]),
    R("GAS", DP, TUBERIA, "diametro", minimo=6),
    R("GAS", "", CODO, "angulo", valores=[45, 90], fuente=EXCEL),
    # ── ALCANTARILLADO (Word) ──
    R("ALCANTARILLADO", COLECTOR, TUBERIA, "diametro", minimo=8, fuente=BOE_F200),
    R("ALCANTARILLADO", HC, TUBERIA, "diametro", minimo=6, fuente=BOE_F400),
    R("ALCANTARILLADO", HC, TUBERIA, "llega_menos", minimo=2, fuente=BOE_F400,
      nota="La conexión domiciliaria no puede superar el diámetro del colector menos 2 in."),
    R("ALCANTARILLADO", HC, TUBERIA, "pendiente", minimo=2, fuente=BOE_F500,
      nota="Excepcionalmente hasta 1 %."),
    R("ALCANTARILLADO", COLECTOR, TUBERIA, "pendiente", minimo=0.44, si_diam=[8, 8], fuente=BOE_F200,
      nota="Mínima excepcional en tramos extremos con pocas conexiones; hacia el buzón terminal 0,60 %. La de "
           "diseño la da la velocidad mínima de 3 fps."),
    R("ALCANTARILLADO", "", TUBERIA, "material_no", valores=["Acero corrugado"], fuente=BOE_F200,
      nota="Tampoco concreto no reforzado, asbesto-cemento ni fibra de vidrio."),
    R("ALCANTARILLADO", "", BUZON, "dist_buzones", maximo=400, si_diam=[8, 15], fuente=BOE_F400),
    R("ALCANTARILLADO", "", BUZON, "dist_buzones", maximo=500, si_diam=[18, 30], fuente=BOE_F400),
    R("ALCANTARILLADO", "", BUZON, "dist_buzones", maximo=900, si_diam=[33, None], fuente=BOE_F400),
    R("ALCANTARILLADO", "", BUZON, "caida", maximo=0.6, si_diam=[None, 15], fuente=BOE_F200,
      nota="Flujo directo; en entradas laterales hasta 1 ft."),
    R("ALCANTARILLADO", "", BUZON, "caida", minimo=0.1, nivel="INFO", fuente=BOE_F200,
      nota="Recomendado cuando sea posible (flujo directo)."),
    *[R("ALCANTARILLADO", "", CURVA, "radio", minimo=m, si_diam=[d, d], si_material=["PVC"], fuente=LA_ALC,
        nota="Plástico sin accesorios de deflexión; con radios menores, codos de 3° o 5°.")
      for d, m in ((6, 210), (8, 280), (10, 350), (12, 420), (15, 525))],
    R("ALCANTARILLADO", "", TUBERIA, "sep_h", minimo=1, con=CUALQUIERA, fuente=LA_ALC,
      nota="1 ft libre desde la zanja del alcantarillado (aquí, entre tuberías)."),
    R("ALCANTARILLADO", "", TUBERIA, "sep_v", minimo=1, con=CUALQUIERA, fuente=LA_ALC),
    R("ALCANTARILLADO", "", TUBERIA, "sep_h", minimo=6, con="GAS", nivel="INFO", fuente=BOE_F300,
      nota="Si el gas va a más de 60 psig: exponerlo (pothole) y mostrar la sección transversal."),
    R("ALCANTARILLADO", "", TUBERIA, "referencia", fuente=BOE_F200,
      nota="Velocidad mínima 3 fps con el PDWF; tirante del caudal pico seco ≤ D/2."),
    R("ALCANTARILLADO", "", TUBERIA, "referencia", fuente=LA_ALC,
      nota="Plástico: velocidad máxima 12 fps."),
    R("ALCANTARILLADO", HC, TUBERIA, "referencia", fuente=BOE_F500,
      nota="Profundidad mínima 4 ft bajo el borde de la acera en la línea de propiedad (3,5 ft en colinas)."),
    # ── DRENAJE (Word) ──
    R("DRENAJE", SD_SUB, TUBERIA, "pendiente", minimo=0.5, fuente=MRDC),
    R("DRENAJE", SD_LAT, TUBERIA, "pendiente", minimo=0.3, fuente=MRDC),
    R("DRENAJE", SD_COL, TUBERIA, "pendiente", minimo=0.25, fuente=MRDC),
    R("DRENAJE", SD_SUB, TUBERIA, "largo", maximo=300, fuente=MRDC),
    R("DRENAJE", "", BUZON, "dist_buzones", maximo=300, fuente=MRDC),
    R("DRENAJE", "", TUBERIA, "quiebre", maximo=10, fuente=MRDC,
      nota="Buzón en cambios de dirección mayores a 10°."),
    R("DRENAJE", SD_COL, TUBERIA, "diametro", minimo=24, fuente=MRDC),
    R("DRENAJE", SD_SUM, TUBERIA, "diametro", minimo=18, fuente=MRDC),
    R("DRENAJE", "", TUBERIA, "diametro", minimo=24, si_largo=[100, None], fuente=MRDC),
    R("DRENAJE", "", TUBERIA, "material", valores=["Hormigón armado"], fuente=MRDC,
      nota="RCP. HDPE y PVC solo con autorización de la agencia."),
    R("DRENAJE", "", TUBERIA, "material_no", valores=["Acero corrugado"], fuente=MRDC,
      nota="Prohibido el acero en el sistema permanente."),
    # ── ELÉCTRICO (Excel del ingeniero) ──
    R("ELECTRICO", DP, TUBERIA, "diametro", minimo=3, fuente=EXCEL),
    R("ELECTRICO", ID, TUBERIA, "diametro", valores=[3], si_amp=[0, 320], si_largo=[0, 100], fuente=EXCEL),
    R("ELECTRICO", ID, TUBERIA, "diametro", valores=[3], si_amp=[0, 320], si_largo=[101, 200], fuente=EXCEL),
    R("ELECTRICO", ID, TUBERIA, "diametro", valores=[3], si_amp=[321, 400], si_largo=[0, 100], fuente=EXCEL),
    R("ELECTRICO", ID, TUBERIA, "diametro", valores=[4], si_amp=[321, 400], si_largo=[101, 200], fuente=EXCEL),
    # ── ELÉCTRICO (Word) ──
    R("ELECTRICO", "", TUBERIA, "sep_v", minimo=0.5, con=CUALQUIERA, fuente=SPEC104,
      nota="Cruce con otro servicio existente: 6 in."),
    R("ELECTRICO", "", TUBERIA, "sep_h", minimo=1, con=CUALQUIERA, fuente=SPEC104,
      nota="Paralelo con otro servicio existente: 12 in."),
    R("ELECTRICO", "", TUBERIA, "sep_h", minimo=5, con="GAS", nivel="INFO", fuente=SPEC104,
      nota="5 ft si es una línea de gas de alta presión (HPGL)."),
    R("ELECTRICO", "", CURVA, "radio", minimo=3, si_diam=[None, 4], fuente=ESR,
      nota="Conduits de 4 in o menores."),
    R("ELECTRICO", "", CURVA, "radio", minimo=4, si_diam=[5, None], fuente=ESR,
      nota="Conduits mayores a 4 in: 4 a 5 ft."),
    R("ELECTRICO", "", TUBERIA, "referencia", fuente=GO128,
      nota="Profundidad: 24 in en vías públicas (hasta 35 kV), 18 in en aceras (≤750 V), 36 in sobre 35 kV; "
           "66 in bajo Metro Light Rail."),
    R("ELECTRICO", "", TUBERIA, "referencia", fuente=ESR,
      nota="Un conduit por cada 400 A de capacidad de servicio."),
    # ── TELECOM ──
    R("TELECOM", "", TUBERIA, "diametro", minimo=4, fuente=EXCEL),
    R("TELECOM", "", TUBERIA, "referencia", fuente=GO128,
      nota="Profundidad: 18 in en vía pública, 12 in en acera o propiedad privada. Fibra: mismo tamaño que el "
           "conduit primario, mínimo 4 in."),
]


def base():
    return {"version": 2, "tipos": [list(t) for t in TIPOS], "reglas": [dict(r) for r in REGLAS]}
