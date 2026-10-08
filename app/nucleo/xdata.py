"""xdata.py — Datos extendidos de utilidades y estructuras (puro, sin Qt).

Como los Property Sets / XDATA de Civil 3D: información que no es parte del
modelo de la red (tipo, diámetro, cotas…) pero conviene conservar como
referencia. Cada pipe o estructura puede llevar::

    obj["xdata"] = {"auto": {campo: valor, …},   # del PDF: solo lectura
                    "user": {campo: valor, …}}   # del usuario: editable

`auto` sale del reconocimiento: la capa OCG de origen (la línea sigue siendo
Drenaje / Eléctrico; la capa solo queda como referencia) y lo que su nombre NCS
dice —disciplina, sistema, ubicación, estado— más el PDF y la hoja de donde
salió. El DXF los exporta como claves extra de PDFCAD_PIPE / PDFCAD_STRUCT
(`XD_*` automáticos, `XDU_*` del usuario); el plugin ignora las que no conoce.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

AUTO, USER = "auto", "user"

# Campos automáticos, en el orden en que se muestran → clave del DXF.
F_OCG = "Capa OCG"
F_XREF = "Xref de origen"
F_LAYER = "Capa"
F_DISC = "Disciplina"
F_SYSTEM = "Sistema"
F_LOCATION = "Ubicación"
F_STATUS = "Estado (según capa)"
F_MODS = "Modificadores"
F_ORIGIN = "Origen"
AUTO_DXF_KEYS = {
    F_OCG: "XD_CAPA_OCG", F_XREF: "XD_XREF", F_LAYER: "XD_CAPA", F_DISC: "XD_DISCIPLINA",
    F_SYSTEM: "XD_SISTEMA", F_LOCATION: "XD_UBICACION", F_STATUS: "XD_ESTADO",
    F_MODS: "XD_MODIFICADORES", F_ORIGIN: "XD_ORIGEN",
}

# Estándar BOE (City of Los Angeles, «CADD Standards» §8.1, basado en AIA/NCS):
# DISCIPLINA-GRUPOMAYOR-grupo menor…-ESTADO. Disciplina = 1 letra (nivel 1)
# + opcional 1 letra de subconjunto (nivel 2: CU = Civil Utilities); grupos de
# 4 caracteres, rellenos con «~» si hace falta; estado/fase de 1 carácter.
# Además se aceptan las variantes de los planos reales (UNGD, UNDG, HDWL, MANH,
# sufijo de paquete «__UA2-3»…).
DISCIPLINES = {                                       # §8.1.3 (J, K, N, U, Y: no usadas)
    "A": "Arquitectura", "B": "Geotecnia", "C": "Civil", "D": "Procesos",
    "E": "Eléctrica", "F": "Protección contra incendios", "G": "General",
    "H": "Materiales peligrosos", "I": "Interiores / instrumentación", "L": "Paisajismo",
    "M": "Mecánica", "O": "Operaciones", "P": "Plomería", "Q": "Equipamiento",
    "R": "Recursos", "S": "Estructural", "T": "Telecomunicaciones",
    "V": "Levantamiento / cartografía", "W": "Distribución de energía",
    "X": "Otras disciplinas", "Z": "Contratista / planos de taller",
}
DISCIPLINE_SUBSETS = {"CI": "Civil – mejoras", "CU": "Civil – utilidades"}   # §1.3.1
SYSTEMS = {
    "STRM": "Pluvial (drenaje de tormenta)", "SSWR": "Alcantarillado sanitario",
    "WATR": "Agua", "FIRE": "Contra incendios", "NGAS": "Gas natural", "GAS": "Gas",
    "ELEC": "Eléctrico", "POWR": "Eléctrico (potencia)", "STLT": "Alumbrado público",
    "COMM": "Comunicaciones", "TELE": "Telefonía", "CATV": "Televisión por cable",
    "STEM": "Vapor", "ROAD": "Vías", "CURB": "Sardineles", "SWLK": "Aceras",
    "PKNG": "Estacionamiento", "SITE": "Sitio", "TOPO": "Topografía",
    "TINN": "Red de triángulos (TIN)", "DTM": "Modelo digital del terreno",
    "ANNO": "Anotación", "PROF": "Perfil", "ALGN": "Alineamiento", "PROP": "Propiedad",
    "BLDG": "Edificaciones", "WALL": "Muros", "UTIL": "Utilidades",
    "DETL": "Detalle", "ELEV": "Elevación", "SECT": "Sección",
}
LOCATIONS = {"UNGD": "Subterránea", "UGND": "Subterránea", "UNDG": "Subterránea", "OVHD": "Aérea"}
MODIFIERS = {
    # drenaje / alcantarillado (tabla de capas BOE)
    "PIPE": "tubería", "FORC": "tubería de impulsión", "LATL": "lateral", "MHOL": "buzón",
    "MANH": "buzón", "HWAL": "cabezal", "HDWL": "cabezal", "STRC": "estructura",
    "CTCH": "sumidero", "BASN": "sumidero", "CBSN": "sumidero", "INST": "instrumentación",
    "CNTR": "eje", "DIAG": "diagrama", "STAN": "estacionado", "PROF": "perfil",
    # materiales
    "RCON": "concreto reforzado", "CMTL": "metal corrugado", "STEL": "acero",
    "ASPH": "asfalto", "CONC": "concreto",
    # geometría auxiliar / anotación (§8.2: IDEN, MBND, MCUT, OTLN, PATT)
    "VALT": "bóveda", "WALL": "muro", "CASE": "camisa", "DUCT": "ducto", "LID": "tapa",
    "BNDY": "límite", "CURB": "sardinel", "WALK": "acera", "NPLT": "no imprimible",
    "TEXT": "texto", "ANNO": "anotación", "DIMS": "cotas", "IDEN": "identificación",
    "MBND": "match line", "MCUT": "línea de corte", "OTLN": "contorno", "PATT": "achurado",
    "DETL": "detalle", "ELEV": "elevación", "SECT": "sección",
}
STATUSES = {                                          # §8.1.6 «Status (phase)»
    "A": "Abandonada", "D": "Existente a demoler", "E": "Existente (se conserva)",
    "F": "Trabajo futuro", "M": "A retirar", "N": "Nueva (obra nueva)",
    "T": "Temporal", "X": "Fuera de contrato",
    **{str(n): f"Fase {n}" for n in range(1, 10)},
}
_VIEW_NUMBER = re.compile(r"^[A-Z]\d{3}$")            # §8.2.1 «ANNN»: número de vista


def parse_layer(ocg: str) -> Dict[str, str]:
    """Nombre de capa OCG → campos legibles (solo los que se pueden deducir).

    'PS89616000-A1-UD-REF|C-STRM-UNGD-N' → Xref 'PS89616000-A1-UD-REF',
    Capa 'C-STRM-UNGD-N', Disciplina 'C — Civil', Sistema 'STRM — Pluvial…',
    Ubicación 'UNGD — Subterránea', Estado 'N — Nueva (propuesta)'."""
    ocg = (ocg or "").strip()
    out: Dict[str, str] = {}
    if not ocg:
        return out
    out[F_OCG] = ocg
    xref, _, short = ocg.rpartition("|")
    short = short.strip()
    if xref:
        out[F_XREF] = xref.strip()
    out[F_LAYER] = short
    base, _, package = short.upper().partition("__")      # `C-ELEC-UGND-N__UA2-3`: sufijo del paquete
    toks = [t for t in re.split(r"[-_ ]+", base.replace("~", "")) if t]   # «~» = relleno (§8.1.4)
    if not toks:
        return out
    used = set()
    if len(toks[0]) == 1 and toks[0].isalpha():
        out[F_DISC] = _label(toks[0], DISCIPLINES)
        used.add(0)
    elif len(toks[0]) == 2 and toks[0].isalpha() and toks[0][0] in DISCIPLINES:
        sub = DISCIPLINE_SUBSETS.get(toks[0])             # nivel 2 (§1.3.1): CU-STRM-…
        out[F_DISC] = (f"{toks[0]} — {sub}" if sub else
                       f"{toks[0]} — {DISCIPLINES[toks[0][0]]} (subconjunto {toks[0][1]})")
        used.add(0)
    sys_i = 1 if 0 in used else 0
    if sys_i < len(toks) and toks[sys_i] not in LOCATIONS and not (
            len(toks[sys_i]) == 1 and toks[sys_i] in STATUSES):
        out[F_SYSTEM] = _label(toks[sys_i], SYSTEMS)
        used.add(sys_i)
    for i, t in enumerate(toks):
        if i not in used and t in LOCATIONS:
            out[F_LOCATION] = _label(t, LOCATIONS)
            used.add(i)
            break
    for i in range(len(toks) - 1, -1, -1):          # estado: la última letra suelta
        if i not in used and len(toks[i]) == 1 and toks[i] in STATUSES:
            out[F_STATUS] = _label(toks[i], STATUSES)
            used.add(i)
            break
    mods = [t for i, t in enumerate(toks) if i not in used]
    if package:
        mods.append("__" + package)
    if mods:
        words = []
        for t in mods:
            w = (MODIFIERS.get(t) or (f"vista {t}" if _VIEW_NUMBER.match(t) else None)
                 or (f"paquete {t[2:]}" if t.startswith("__") else None))
            if w and w not in words:
                words.append(w)
        out[F_MODS] = "-".join(mods) + (f" ({', '.join(words)})" if words else "")
    return out


def _label(code: str, table: Dict[str, str]) -> str:
    name = table.get(code)
    return f"{code} — {name}" if name else code


def auto_fields(ocg: Optional[str], origin: Optional[str] = None) -> Dict[str, str]:
    """Datos automáticos de un objeto reconocido (capa + origen)."""
    out = parse_layer(ocg or "")
    if origin:
        out[F_ORIGIN] = origin
    return out


def make(ocg: Optional[str], origin: Optional[str] = None) -> Optional[dict]:
    """`xdata` nuevo para un objeto reconocido; None si no hay nada que guardar."""
    auto = auto_fields(ocg, origin)
    return {AUTO: auto, USER: {}} if auto else None


def get(obj: dict) -> dict:
    """`xdata` normalizado del objeto (sin modificarlo)."""
    xd = obj.get("xdata") if isinstance(obj, dict) else None
    if not isinstance(xd, dict):
        return {AUTO: {}, USER: {}}
    return {AUTO: dict(xd.get(AUTO) or {}), USER: dict(xd.get(USER) or {})}


def set_user(obj: dict, user: Dict[str, str]) -> None:
    """Reemplaza los campos del usuario (los automáticos no se tocan)."""
    xd = get(obj)
    xd[USER] = {str(k).strip(): str(v) for k, v in (user or {}).items() if str(k).strip()}
    if xd[AUTO] or xd[USER]:
        obj["xdata"] = xd
    else:
        obj.pop("xdata", None)


def set_auto(obj: dict, auto: Dict[str, str]) -> None:
    """Reemplaza los campos automáticos conservando los del usuario (re-importar
    una bóveda no borra lo que el usuario anotó en ella)."""
    xd = get(obj)
    xd[AUTO] = dict(auto or {})
    if xd[AUTO] or xd[USER]:
        obj["xdata"] = xd
    else:
        obj.pop("xdata", None)


def validate_user(user_rows: Sequence[Tuple[str, str]], auto: Dict[str, str]) -> Optional[str]:
    """Mensaje de error si los campos del usuario no son válidos (None = OK):
    nombre vacío con valor, nombres repetidos o iguales a un campo automático."""
    seen = set()
    reserved = {k.casefold() for k in auto}
    for name, value in user_rows:
        name = (name or "").strip()
        if not name:
            if (value or "").strip():
                return "Hay un valor sin nombre de campo."
            continue
        key = name.casefold()
        if key in reserved:
            return f"«{name}» es un campo automático del PDF: usa otro nombre."
        if key in seen:
            return f"El campo «{name}» está repetido."
        seen.add(key)
    return None


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return s or "CAMPO"


def dxf_items(obj: dict, max_len: int = 250) -> List[str]:
    """Cadenas «CLAVE=valor» para el XDATA del DXF (cada una ≤ `max_len`, límite
    de un grupo 1000). Automáticos: `XD_*`; del usuario: `XDU_<nombre>`."""
    xd = get(obj)
    out: List[str] = []
    for field, value in xd[AUTO].items():
        key = AUTO_DXF_KEYS.get(field, "XD_" + _slug(field))
        out.append(_clip(f"{key}={_one_line(value)}", max_len))
    used = set()
    for field, value in xd[USER].items():
        key = "XDU_" + _slug(field)
        base, n = key, 2
        while key in used:
            key = f"{base}_{n}"; n += 1
        used.add(key)
        out.append(_clip(f"{key}={_one_line(value)}", max_len))
    return out


def _one_line(v) -> str:
    return " ".join(str(v).split())


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n]


def origin_label(pts_pt: Sequence[Tuple[float, float]],
                 pieces: Sequence[Tuple[Tuple[float, float, float, float], str]],
                 default: str = "") -> str:
    """Hoja de origen de un objeto en la hoja de trabajo: la pieza de la hoja
    compuesta que contiene su punto medio (`pieces` = [(rect pt, etiqueta)]);
    `default` si no cae en ninguna o no hay piezas."""
    if not pts_pt:
        return default
    mid = pts_pt[len(pts_pt) // 2]
    if len(pts_pt) % 2 == 0 and len(pts_pt) >= 2:
        a, b = pts_pt[len(pts_pt) // 2 - 1], pts_pt[len(pts_pt) // 2]
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    for (x0, y0, x1, y1), label in pieces:
        if x0 <= mid[0] <= x1 and y0 <= mid[1] <= y1:
            return label
    return default
