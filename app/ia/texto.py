"""Utilidades de texto de la IA (PURO): normalizar y partir en palabras (para buscar en la memoria y en los
datos), los NÚMEROS de un texto (para revisar que la IA no invente cifras) y leer el JSON que devuelve."""
from __future__ import annotations

import json
import re
import unicodedata

_PALABRA = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_NUMERO = re.compile(r"(?<![\w.,])[-+]?\d+(?:[.,]\d+)?")
VACIAS = frozenset(
    "a al algo ante como con cual cuales cuando de del desde donde el ella en entre es esta este esto hay la las "
    "le les lo los mas me mi muy no o para pero por que se si sin sobre son su sus te tiene un una uno unos y ya "
    "the of and or to in is are what which how many much where".split())


def normalizar(texto: str) -> str:
    """minúsculas y sin acentos: «Tubería» → «tuberia»."""
    s = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def palabras(texto: str) -> list[str]:
    """Palabras útiles para buscar (sin las vacías). «AGUA-5» queda entero como «agua-5»."""
    return [p for p in _PALABRA.findall(normalizar(texto)) if p not in VACIAS and len(p) > 1 or p.isdigit()]


def raiz(p: str) -> str:
    """Raíz tosca para que «tuberías» encuentre «tubería» y «cruces» a «cruce» (sin diccionario)."""
    for fin in ("iones", "ones", "es", "s"):
        if len(p) > len(fin) + 3 and p.endswith(fin):
            return p[:-len(fin)]
    return p


def raices(texto: str) -> set[str]:
    return {raiz(p) for p in palabras(texto)}


def numeros(texto: str) -> list[float]:
    """Los números escritos en el texto («0.4», «0,4», «12»). Los de un código «AGUA-5» o «C-12» no cuentan."""
    out = []
    for m in _NUMERO.finditer(str(texto or "")):
        ini = m.start()
        if ini > 0 and texto[ini - 1] == "-" and ini > 1 and texto[ini - 2].isalpha():
            continue                                   # «C-12», «AGUA-5»: es un código, no una cifra
        try:
            out.append(float(m.group().replace(",", ".")))
        except ValueError:
            pass
    return out


def respaldado(valor: float, conocidos, tol_abs=0.051, tol_rel=0.001) -> bool:
    """`valor` es uno de los `conocidos` redondeado (a un decimal, a entero o al 0.1 %)."""
    entero = float(valor).is_integer()
    return any(abs(valor - c) <= max(tol_abs, abs(c) * tol_rel) or (entero and abs(valor - c) < 0.5)
               for c in conocidos)


def no_respaldados(texto: str, conocidos, libres=(0, 1, 2)) -> list[float]:
    """Números del texto que NO salen de `conocidos` (con redondeo). `libres` = enteros que se usan al
    redactar («las 2 tuberías») y no son datos."""
    conocidos = list(conocidos)
    return [v for v in numeros(texto) if not (v in libres or respaldado(v, conocidos) or respaldado(-v, conocidos))]


def leer_json(texto: str):
    """El primer objeto JSON del texto (los modelos a veces lo rodean de ```json …```). None si no hay."""
    s = str(texto or "").strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    ini, fin = s.find("{"), s.rfind("}")
    if 0 <= ini < fin:
        try:
            return json.loads(s[ini:fin + 1])
        except ValueError:
            return None
    return None
