"""Textos de ayuda del Excel de normativas (PURO): el comentario de cada columna y la hoja
INSTRUCCIONES. Pedido del usuario 2026-10-14: el ingeniero editó el Excel a mano y escribió
rangos y operadores en una celda («0.5-2», «>4», «>=400») que la app no podía leer.

La hoja INSTRUCCIONES (y cualquier otra hoja que no sea de las cuatro tablas, como
«auxiliar») se escribe al exportar y NUNCA se lee al importar. Los textos van en español
fijo: el Excel es un formato de datos (sus encabezados también son fijos).
"""
from __future__ import annotations

HOJA_INSTRUCCIONES = "INSTRUCCIONES"

_VACIO = "Vacía = sin restricción."
_LISTA = "Varios valores separados con punto y coma: 6; 8; 12. Decimales con coma: 1,5."
_MIN = "Un solo número. Vacía = sin mínimo. El valor escrito también vale (es «desde»)."
_MAX = "Un solo número. Vacía = sin máximo. El valor escrito también vale (es «hasta»)."

COMENTARIOS = {
    # ── comunes ──
    "UTILIDAD": "Elige de la lista: AGUA, ALCANTARILLADO, DRENAJE, GAS, ELECTRICO o TELECOM.",
    "TIPO": "Elige de la lista. Los tipos se crean en la hoja TIPOS (una fila nueva por tipo).",
    # ── PRESION-DIAMETROS ──
    "DIAMETRO (in)": "Diámetros permitidos, uno por uno (en pulgadas).\n" + _LISTA
                     + "\nSi es un rango (de 0,5 a 2), deja esta vacía y usa MIN y MAX.",
    "DIAMETRO MIN (in)": "Rango de diámetros: el más chico permitido (pulgadas).\n" + _MIN
                         + "\nEjemplo «de 0,5 a 2»: MIN 0,5 y MAX 2. «Más de 4»: MIN 4, MAX vacía.",
    "DIAMETRO MAX (in)": "Rango de diámetros: el más grande permitido (pulgadas).\n" + _MAX,
    "SOLO SE PERMITE EN": "Texto libre: en qué caso vale esta fila (por ejemplo «calles sin salida»). "
                          "La app lo muestra como nota. " + _VACIO,
    # ── PRESION-ACCESORIOS ──
    "ACCESORIO": "Y, T, Cruz, Codo o T - Domiciliaria.",
    "SOLO SE PERMITE EN (accesorio)": "Tipo de la tubería PRINCIPAL donde se permite el accesorio "
                                      "(elige de la lista). En el Codo: el tipo donde se exigen sus "
                                      "ángulos. " + _VACIO,
    "DIAMETRO PRINCIPAL (in)": "Diámetros permitidos para la tubería principal (pulgadas).\n" + _LISTA
                          + "\n" + _VACIO,
    "PROHIBIDO USO": "Tipo de la tubería principal donde el accesorio NO se permite (elige de la lista). "
                     + _VACIO,
    "DIAMETRO RAMAL DISTRIBUCION": "Diámetro del ramal comparado con la principal, en pasos de la lista "
                                   "«DIAMETRO PRINCIPAL (in)»: -1 = un tamaño menor (12 → 8). " + _VACIO,
    "ANGULOS PERMITIDOS": "Solo para el Codo: ángulos permitidos en grados.\n" + _LISTA + "\n" + _VACIO,
    # ── ELECT-TELECOM ──
    "ESTRUCTURA": "SIMPLE = tubería normal. BANCODUCTO = aún no se revisa en la app.",
    "AMPERAJE MIN (A)": "Rango de amperaje donde vale esta fila: el mínimo.\n" + _MIN
                        + "\nEjemplo «de 0 a 320»: MIN 0, MAX 320. «400 o más»: MIN 400, MAX vacía.",
    "AMPERAJE MAX (A)": "Rango de amperaje donde vale esta fila: el máximo.\n" + _MAX,
    "LONGITUD MIN (pies)": "Rango de largo de la línea donde vale esta fila: el mínimo (pies).\n" + _MIN,
    "LONGITUD MAX (pies)": "Rango de largo de la línea donde vale esta fila: el máximo (pies).\n" + _MAX,
    "DIAMETRO FIJO (in)": "Diámetro obligatorio (pulgadas). Si hay varios válidos, sepáralos con «;». "
                          + _VACIO,
    "DIAMETRO MIN (in) (elec)": "Diámetro más chico permitido (pulgadas).\n" + _MIN,
    "DIAMETRO MAX (in) (elec)": "Diámetro más grande permitido (pulgadas).\n" + _MAX,
    "RADIO CURVA MIN (pies)": "Radio más chico permitido para las curvas de la línea (pies).\n" + _MIN,
    "RADIO CURVA MAX (pies)": "Radio más grande permitido para las curvas de la línea (pies).\n" + _MAX,
    "RADIO CURVA FIJO (pies)": "Radios permitidos, uno por uno (pies): la curva debe tener exactamente uno de "
                               "ellos.\n" + _LISTA + "\n" + _VACIO,
}

# Columnas con el mismo nombre en dos hojas y distinto sentido: (hoja, columna) → clave de COMENTARIOS.
POR_HOJA = {
    ("PRESION-ACCESORIOS", "SOLO SE PERMITE EN"): "SOLO SE PERMITE EN (accesorio)",
    ("ELECT-TELECOM", "DIAMETRO MIN (in)"): "DIAMETRO MIN (in) (elec)",
    ("ELECT-TELECOM", "DIAMETRO MAX (in)"): "DIAMETRO MAX (in) (elec)",
}


def comentario(hoja, columna):
    return COMENTARIOS.get(POR_HOJA.get((hoja, columna), columna), "")


# (texto, estilo): "t" título, "s" subtítulo, "" normal, "e" ejemplo.
INSTRUCCIONES = [
    ("Cómo llenar este Excel de normativas", "t"),
    ("Una fila = una regla. Pasa el mouse por el título de cada columna para ver qué va ahí.", ""),
    ("", ""),
    ("1. Celda vacía", "s"),
    ("Vacía = sin restricción (o no aplica). No escribas «-», «N/A» ni «todos».", ""),
    ("", ""),
    ("2. Un número", "s"),
    ("Solo el número, sin unidades ni símbolos: 4   (no 4\", no 4 in).", "e"),
    ("Decimales con coma o con punto: 1,5   o   1.5", "e"),
    ("", ""),
    ("3. Varios valores sueltos (lista)", "s"),
    ("Sepáralos con punto y coma: 6; 8; 12; 16", "e"),
    ("Sirve para DIAMETRO (in), DIAMETRO PRINCIPAL (in), DIAMETRO FIJO (in), ANGULOS PERMITIDOS y "
     "RADIO CURVA FIJO (pies).", ""),
    ("", ""),
    ("4. Rangos: usa las dos columnas MIN y MAX", "s"),
    ("Nunca escribas el rango en una sola celda (no «0.5-2», no «>4», no «>=400»).", ""),
    ("De 0,5 a 2   →   MIN = 0,5    MAX = 2", "e"),
    ("4 o más        →   MIN = 4      MAX = vacía", "e"),
    ("Hasta 100      →   MIN = vacía  MAX = 100", "e"),
    ("Los dos extremos cuentan: MIN 0 y MAX 320 incluye 0 y 320.", ""),
    ("«Más de 4» (sin el 4): pon como MIN el siguiente tamaño que sí vale, por ejemplo 6.", ""),
    ("", ""),
    ("5. Tipos", "s"),
    ("Los tipos (Distribución principal, Servicio residencial…) se crean en la hoja TIPOS: una fila "
     "con su UTILIDAD y su TIPO. Después aparecen en las listas de las otras hojas.", ""),
    ("", ""),
    ("6. Qué hojas lee la app", "s"),
    ("Solo TIPOS, PRESION-DIAMETROS, PRESION-ACCESORIOS y ELECT-TELECOM.", ""),
    ("Esta hoja y cualquier otra (por ejemplo «auxiliar», para ideas y notas) NO se importan: puedes "
     "escribir ahí lo que quieras.", ""),
    ("No cambies los títulos de las columnas: la app las busca por su nombre. Si una columna no se reconoce, "
     "al importar la app lo avisa.", ""),
    ("", ""),
    ("7. Al importar", "s"),
    ("En la app: Normativas → Normativas de diseño → «Importar Excel…». Si una celda no se entiende, "
     "la app te dice cuál (hoja, fila y columna) y no la usa.", ""),
]


def escribir_instrucciones(wb):
    """Agrega la hoja INSTRUCCIONES como PRIMERA hoja del libro."""
    from openpyxl.styles import Alignment, Font, PatternFill
    ws = wb.create_sheet(HOJA_INSTRUCCIONES, 0)
    ws.column_dimensions["A"].width = 110
    ws.sheet_view.showGridLines = False
    for texto, estilo in INSTRUCCIONES:
        ws.append([texto])
        c = ws.cell(row=ws.max_row, column=1)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if estilo == "t":
            c.font = Font(bold=True, size=15)
        elif estilo == "s":
            c.font = Font(bold=True, size=12, color="1F5C99")
        elif estilo == "e":
            c.font = Font(name="Consolas", size=11)
            c.fill = PatternFill("solid", fgColor="EEF4FB")
    return ws
