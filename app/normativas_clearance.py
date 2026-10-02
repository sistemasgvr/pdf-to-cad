"""Convierte el Excel de «clearance tables» de los ingenieros (formato libre:
una hoja por utilidad con tablas HORIZONTAL/VERTICAL, valores como «5' MIN.¹»,
superíndices = referencias, notas sueltas) a reglas del motor de normativas.
PURO (solo openpyxl).

Regla de oro: NO SE PIERDE NADA. Cada celda con texto termina en un sitio:
  - un valor de tabla → una regla (con su texto original, encabezado,
    condición de la fila, hoja y referencias);
  - «REFERENCES» → referencias (las de igual texto se unen en un solo id);
  - notas, asteriscos, «SEE SHEET…», títulos de proyecto → notas / documento;
  - cualquier otra celda → nota «Sin clasificar».
`celdas_no_usadas` sirve de auditoría.

Lo que el conversor no entiende del todo queda con estado «Revisar» para que
el ingeniero lo mire en la plantilla.
"""
from __future__ import annotations

import re

SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_RE_SUP = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
# 5'  ·  18"  ·  13.58'  ·  36"-42"
_RE_VAL = re.compile(r"""^\s*(\*?)\s*(\d+(?:\.\d+)?)\s*(['"])(?:\s*-\s*(\d+(?:\.\d+)?)\s*(['"]))?""")

UTILIDAD_DE_TITULO = {
    "ELECTRICAL": "ELECTRICO", "GAS": "GAS", "SEWER": "ALCANTARILLADO", "STORMDRAIN": "DRENAJE",
    "TELECOMMUNICATIONS": "TELECOM", "WATER": "AGUA",
}
ABREV = {"ELECTRICO": "E", "GAS": "G", "ALCANTARILLADO": "S", "DRENAJE": "SD", "TELECOM": "T", "AGUA": "W"}

# Encabezado de columna → (contra, condición del contra). Sin superíndices, en mayúsculas.
CONTRA_DE = [
    (r"^CITY OF LA STORMDRAIN$", "DRENAJE", "Ciudad de LA"),
    (r"^LA COUNTY STORMDRAIN$", "DRENAJE", "Condado de LA"),
    (r"^STORMDRAIN$", "DRENAJE", ""),
    (r"^WATER$", "AGUA", ""),
    (r"^SEWER$", "ALCANTARILLADO", ""),
    (r"^(TELECOMMUNICATIONS|COMMUNICATIONS)$", "TELECOM", ""),
    (r"^ELECTRICAL$", "ELECTRICO", ""),
    (r"^GAS$", "GAS", ""),
    (r"^HIGH PRESSURE GAS LINE$|^GAS \(HIGH PRESSURE\)$", "GAS", "Alta presión"),
    (r"^MEDIUM PRESSURE GAS LINE$|^GAS \(MED PRESSURE\)$", "GAS", "Media presión"),
    (r"^STEEL GAS MAIN/SERVICE LINE > 12\" Ø$", "GAS", "Acero > 12\" Ø (principal o servicio)"),
    (r"^ARC WELDABLE GAS MAIN/SERVICE LINE < 12\" & > 4\" Ø$", "GAS", "Soldable por arco 4\"–12\" Ø (principal o servicio)"),
    (r"^NON-ARC WELDABLE GAS MAIN/SERVICE LINE < 4\" Ø$", "GAS", "No soldable por arco < 4\" Ø (principal o servicio)"),
    (r"^ARC WELDABLE PIPELINES > 3\" Ø$", "OTRA_TUBERIA", "Soldable por arco > 3\" Ø"),
    (r"^(RAILROAD TRACK|CENTERLINE OF TRACK|BELOW RAILROAD TRACK)$", "VIA_FERREA", ""),
    (r"^CURB & GUTTER$", "BORDILLO", ""),
    (r"^CATCH BASIN$", "SUMIDERO", ""),
    (r"^MAINTENANCE HOLE$", "BUZON", ""),
    (r"^COVER$", "SUPERFICIE", ""),
]

# Condición de la fila (columnas «GAS MAIN TYPE» / «WATER MAIN SIZE»).
CONDICION_DE = {
    "HIGH PRESSURE GAS LINE": "Alta presión – línea principal",
    "HIGH PRESSURE SERVICE LINE": "Alta presión – línea de servicio",
    "HIGH PRESSURE MAIN LINE": "Alta presión – línea principal",
    "MEDIUM PRESSURE MAIN LINE": "Media presión – línea principal",
    "MEDIUM PRESSURE SERVICE LINE": "Media presión – línea de servicio",
    'STEEL GAS MAIN LINE > 12" Ø': 'Acero > 12" Ø – principal',
    'STEEL GAS SERVICE LINE > 12" Ø & PE SERVICES > 6" Ø': 'Acero > 12" Ø – servicio, y PE > 6" Ø',
    'ARC WELDABLE GAS MAIN LINE < 12" & > 4" Ø': 'Soldable por arco 4"–12" Ø – principal',
    'ARC WELDABLE GAS SERVICE LINE < 12" & > 4" Ø': 'Soldable por arco 4"–12" Ø – servicio',
    'NON-ARC WELDABLE GAS MAIN LINE < 4" Ø': 'No soldable por arco < 4" Ø – principal',
    'NON-ARC WELDABLE GAS SERVICE LINE < 4" Ø': 'No soldable por arco < 4" Ø – servicio',
    '<12"': 'Ø < 12"', '≥12"': 'Ø ≥ 12"',
}

# Texto que sigue al valor → cómo se mide.
MEDIDO_DE = [
    (r"FROM (CL|CENTERLINE) OF TRACK TO (THE )?CENTERLINE", "Eje de vía → eje de tubería"),
    (r"FROM CENTERLINE.{0,4} OF TRACK TO OUTER EDGE", "Eje de vía → borde exterior de tubería"),
    (r"FROM (CL|CENTERLINE) OF TRACK TO WALL", "Eje de vía → pared de buzón"),
    (r"FROM CL OF TRACK", "Eje de vía → borde de tubería"),
    (r"BELOW TOP OF RAIL", "Bajo el tope del riel"),
    (r"FROM FLOWLINE TO CENTERLINE", "Línea de flujo → eje de tubería"),
    (r"FROM CURB FACE TO EDGE", "Cara de bordillo → borde de tubería"),
    (r"BETWEEN .*MAINTENANCE HOLE .*VAULT", "Buzón → bóveda de otra utilidad"),
    (r"FROM OTHER UTILITIES", "Buzón → otras utilidades"),
]
MEDIDO_DEFECTO = {"separacion_horizontal": "Borde a borde (libre)",
                  "separacion_vertical": "Borde a borde (libre)",
                  "recubrimiento": "Superficie → corona de la tubería"}


def _txt(v):
    return "" if v is None else str(v).strip()


def referencias_en(texto):
    """['1', '12'] de «10' MIN. FROM WATER MAIN¹'¹²»."""
    return [m.translate(SUP) for m in _RE_SUP.findall(texto or "")]


def sin_superindices(texto):
    return _RE_SUP.sub("", texto or "").strip()


def interpretar_valor(texto, tipo_tabla):
    """(tipo, mínimo_ft, máximo_ft, medido_desde, asterisco, limpio) de un valor."""
    limpio = sin_superindices(texto)
    m = _RE_VAL.match(limpio)
    if not m:
        return "requisito", None, None, "", "*" in limpio[:2], False
    ast, v1, u1, v2, u2 = m.groups()
    a = float(v1) / (12.0 if u1 == '"' else 1.0)
    b = float(v2) / (12.0 if u2 == '"' else 1.0) if v2 else None
    resto = limpio[m.end():].strip()
    resto_sin = re.sub(r"^MIN\.?\s*\*?\s*", "", resto, flags=re.I).strip(" .*")
    medido = next((nom for pat, nom in MEDIDO_DE if re.search(pat, resto.upper())), "")
    mn, mx = (a, b) if b is not None else (a, None)
    if "BELOW TOP OF RAIL" in resto.upper():
        tipo_tabla = "separacion_vertical"
    if not medido:
        medido = MEDIDO_DEFECTO.get(tipo_tabla, "")
    # «OK» solo si lo que sigue al valor es nada o una forma de medir conocida, sin
    # condiciones ni excepciones (esas quedan en «Revisar» con su texto original).
    condicional = re.search(r"[;(]|EXCEPT|REQUIRE|UNLESS|IF |ONLY", resto.upper())
    reconocido = bool(re.search("|".join(p for p, _ in MEDIDO_DE), resto.upper()))
    limpio_ok = not condicional and (not resto_sin or reconocido)
    return tipo_tabla, mn, mx, medido, bool(ast) or "*" in resto, limpio_ok


def _contra(encabezado):
    h = sin_superindices(encabezado).upper().strip()
    for pat, contra, cond in CONTRA_DE:
        if re.match(pat, h):
            return contra, cond, True
    return h, "", False


class _Lector:
    def __init__(self, wb):
        self.wb = wb
        self.usadas = set()                 # (hoja, fila, col) ya volcadas
        self.reglas, self.notas, self.refs_hoja = [], [], {}
        self.documento = {}
        self._n = {}

    def usar(self, hoja, f, c):
        self.usadas.add((hoja, f, c))

    def _id(self, util, tipo):
        clave = (util, tipo)
        self._n[clave] = self._n.get(clave, 0) + 1
        letra = {"separacion_horizontal": "H", "separacion_vertical": "V",
                 "recubrimiento": "C", "requisito": "R"}[tipo]
        return f"{ABREV.get(util, util[:2])}-{letra}-{self._n[clave]:02d}"

    def hoja(self, ws):
        filas = [[_txt(c.value) for c in fila] for fila in ws.iter_rows()]
        nombre = ws.title
        f = 0
        while f < len(filas):
            fila = filas[f]
            a = fila[0] if fila else ""
            mt = re.match(r"^(\w+) (HORIZONTAL|VERTICAL) CLEARANCE TABLE$", a.upper())
            if mt:
                self.usar(nombre, f, 0)
                self.documento.setdefault("tablas", []).append({"hoja": nombre, "texto": a})
                f = self._tabla(nombre, filas, f + 1, UTILIDAD_DE_TITULO.get(mt.group(1), mt.group(1)),
                                "separacion_horizontal" if mt.group(2) == "HORIZONTAL" else "separacion_vertical")
                continue
            if a.upper().startswith("REFERENCES"):
                self.usar(nombre, f, 0)
                f = self._referencias(nombre, filas, f + 1)
                continue
            if a.upper().startswith("NOTES"):
                self.usar(nombre, f, 0)
                self.notas.append({"hoja": nombre, "aplica": "", "texto": a})
                f = self._notas(nombre, filas, f + 1)
                continue
            f += 1

    def _tabla(self, hoja, filas, f, util, tipo):
        while f < len(filas) and not any(filas[f]):
            f += 1
        if f >= len(filas):
            return f
        cab = filas[f]
        for c, v in enumerate(cab):
            if v:
                self.usar(hoja, f, c)
        con_condicion = cab[0].upper() in ("GAS MAIN TYPE", "WATER MAIN SIZE")
        if con_condicion:                                   # rótulo de la columna de condiciones
            self.documento["tablas"][-1]["texto"] += f" — filas: {cab[0]}"
        f += 1
        while f < len(filas):
            fila = filas[f]
            a = fila[0].upper() if fila else ""
            sola = sum(1 for v in fila if v) == 1             # una nota ocupa una sola celda
            if (not any(fila) or a.startswith("REFERENCES") or "CLEARANCE TABLE" in a
                    or (sola and (a.startswith("*") or a.startswith("SEE SHEET") or a.startswith("NOTES")))):
                return f
            cond_orig = fila[0] if con_condicion else ""
            if con_condicion:
                self.usar(hoja, f, 0)
            for c in range(1 if con_condicion else 0, len(fila)):
                if not fila[c]:
                    continue
                self.usar(hoja, f, c)
                self._regla(hoja, util, tipo, cab[c] if c < len(cab) else "", cond_orig, fila[c])
            f += 1
        return f

    def _regla(self, hoja, util, tipo_tabla, encabezado, cond_orig, valor):
        contra, cond_contra, conocido = _contra(encabezado)
        tipo, mn, mx, medido, asterisco, limpio = interpretar_valor(valor, tipo_tabla)
        if contra == "SUPERFICIE":
            tipo = "recubrimiento" if tipo != "requisito" else tipo
            medido = medido if medido != MEDIDO_DEFECTO.get(tipo_tabla) else MEDIDO_DEFECTO["recubrimiento"]
        refs = referencias_en(valor) + referencias_en(encabezado)
        params = {
            "contra": contra, "condicion": CONDICION_DE.get(cond_orig, cond_orig),
            "condicion_contra": cond_contra, "minimo": mn, "maximo": mx,
            "medido_desde": medido if tipo != "requisito" else "",
            "referencias": [f"{hoja}#{r}" for r in dict.fromkeys(refs)],
            "notas": [f"{hoja}#*"] if asterisco else [],
            "texto_original": valor, "encabezado_original": encabezado,
            "condicion_original": cond_orig, "hoja": hoja,
            "estado": "OK" if (limpio and conocido and tipo != "requisito") else "Revisar",
        }
        self.reglas.append({"id": self._id(util, tipo), "tipo": tipo, "utilidades": [util],
                            "obligatoria": True, "activa": True, "params": params})

    def _referencias(self, hoja, filas, f):
        while f < len(filas):
            a = filas[f][0] if filas[f] else ""
            m = re.match(r"^(\d+)\s*:\s*(.+)$", a)
            if not m:
                return f
            self.usar(hoja, f, 0)
            self.refs_hoja.setdefault(hoja, {})[m.group(1)] = m.group(2).strip()
            f += 1
        return f

    def _notas(self, hoja, filas, f):
        while f < len(filas):
            a = filas[f][0] if filas[f] else ""
            if not a:
                f += 1
                continue
            if re.match(r"^\d+\.\s", a) or a.startswith("·") or a.startswith("•"):
                self.usar(hoja, f, 0)
                self.notas.append({"hoja": hoja, "aplica": "", "texto": a})
                f += 1
                continue
            return f
        return f

    def resto(self):
        """Toda celda con texto que no se usó → nota (título, asteriscos, «SEE SHEET»…)."""
        for ws in self.wb.worksheets:
            for f, fila in enumerate(ws.iter_rows()):
                for c, celda in enumerate(fila):
                    v = _txt(celda.value)
                    if not v or (ws.title, f, c) in self.usadas:
                        continue
                    self.usar(ws.title, f, c)
                    if f == 0 and c == 0:
                        self.documento.setdefault("titulos", []).append({"hoja": ws.title, "texto": v})
                    elif v.startswith("*"):
                        self.notas.append({"hoja": ws.title, "aplica": f"{ws.title}#*", "texto": v})
                    else:
                        self.notas.append({"hoja": ws.title, "aplica": "Sin clasificar", "texto": v})


def es_formato_clearance(wb):
    for ws in wb.worksheets:
        for fila in ws.iter_rows(max_row=40, values_only=True):
            if any("CLEARANCE TABLE" in _txt(v).upper() for v in fila):
                return True
    return False


def convertir(wb, archivo=""):
    """(reglas, anexos) a partir del libro de clearance tables."""
    lec = _Lector(wb)
    for ws in wb.worksheets:
        lec.hoja(ws)
    lec.resto()
    # «SEE SHEET G-3 FOR SUPERSCRIPT REFERENCES»: esa hoja usa las referencias de otra.
    for n in lec.notas:
        m = re.match(r"^SEE SHEET (\S+) FOR SUPERSCRIPT REFERENCES", n["texto"].upper())
        if m:
            destino = next((h for h in lec.refs_hoja if h.upper().startswith(m.group(1))), None)
            if destino and n["hoja"] not in lec.refs_hoja:
                lec.refs_hoja[n["hoja"]] = lec.refs_hoja[destino]
    # Referencias únicas: el mismo texto en varias hojas = un solo id.
    unicas, mapa = {}, {}
    for hoja, refs in lec.refs_hoja.items():
        for num, texto in refs.items():
            clave = re.sub(r"\s+", " ", texto.upper()).strip()
            if clave not in unicas:
                unicas[clave] = (f"REF-{len(unicas) + 1:02d}", texto, [])
            unicas[clave][2].append(f"{hoja} ({num})")
            mapa[f"{hoja}#{num}"] = unicas[clave][0]
    referencias = {rid: {"texto": texto, "origen": "; ".join(orig)} for rid, texto, orig in unicas.values()}
    # Notas con id; las de asterisco quedan ligadas a las reglas con «*» de su hoja.
    notas, ast_de_hoja = [], {}
    for i, n in enumerate(lec.notas, 1):
        nid = f"NOTA-{i:02d}"
        notas.append({"id": nid, "hoja": n["hoja"], "texto": n["texto"],
                      "aplica": "" if n["aplica"] in ("", f"{n['hoja']}#*") else n["aplica"]})
        if n["aplica"] == f"{n['hoja']}#*":
            ast_de_hoja.setdefault(n["hoja"], []).append(nid)
    for r in lec.reglas:
        p = r["params"]
        faltan = [x for x in p["referencias"] if x not in mapa]
        p["referencias"] = [mapa[x] for x in p["referencias"] if x in mapa]
        if faltan:
            p["estado"] = "Revisar"
        p["notas"] = [nid for x in p["notas"] for nid in ast_de_hoja.get(x.split("#")[0], [])]
    documento = {"archivo": archivo, "titulos": lec.documento.get("titulos", []),
                 "tablas": lec.documento.get("tablas", [])}
    return lec.reglas, {"referencias": referencias, "notas": notas, "documento": documento}


def celdas_no_usadas(wb):
    """Auditoría: textos del libro que el conversor no volcó (debe ser vacío)."""
    lec = _Lector(wb)
    for ws in wb.worksheets:
        lec.hoja(ws)
    lec.resto()
    return [(ws.title, f, c) for ws in wb.worksheets for f, fila in enumerate(ws.iter_rows())
            for c, celda in enumerate(fila) if _txt(celda.value) and (ws.title, f, c) not in lec.usadas]
