"""Respuestas del usuario a una propuesta de cambio en el chat de Civil 3D (PURO).

Reporte del usuario 2026-11-10: con una propuesta pendiente escribió «No, cámbialo a -10» y la IA solo contestó con
texto (sin tarjeta nueva); luego «sí, aplícalo» y la IA dijo «Cambio aplicado» sin que nada cambiara en Civil 3D
(el modelo no puede aplicar: solo el botón del usuario). Ahora la APP decide antes de preguntarle al modelo:

- `clasificar(texto)` = "si" (aplicar lo pendiente), "no" (descartarlo) o None (otra cosa: corrección o pregunta).
- `pide_cambio(texto)` = ¿el mensaje pide cambiar algo? (corrección de una propuesta o pedido nuevo).
- `dice_aplicado(texto)` = ¿la IA afirma que ya cambió algo? (nunca puede: solo el usuario aplica).
"""
from __future__ import annotations

import re
import unicodedata


def _plano(texto):
    s = unicodedata.normalize("NFD", (texto or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9.+\-\s]", " ", s).split()


_SI = {"si", "ok", "okay", "vale", "dale", "hazlo", "aplica", "aplicalo", "aplicala", "aplicalos", "aplicalas",
       "aplicar", "confirmo", "confirma", "confirmalo", "adelante", "acepto", "aceptar", "claro", "perfecto",
       "procede", "listo", "yes", "apply", "go", "correcto", "bien", "de", "acuerdo", "por", "favor", "porfa",
       "porfavor", "ya", "eso", "esta", "todo", "todas", "todos", "la", "las", "lo", "los", "propuesta", "cambio",
       "el", "en", "civil", "3d", "y", "entonces", "pues", "please", "it", "do", "the", "change"}
_SI_CLAVE = {"si", "ok", "okay", "vale", "dale", "hazlo", "aplica", "aplicalo", "aplicala", "aplicalos", "aplicalas",
             "aplicar", "confirmo", "confirma", "confirmalo", "adelante", "acepto", "aceptar", "procede", "yes",
             "apply", "perfecto", "correcto"}
_NO = {"no", "descarta", "descartalo", "descartala", "descartar", "cancela", "cancelalo", "cancelala", "cancelar",
       "olvidalo", "dejalo", "nada", "mejor", "gracias", "por", "favor", "asi", "esta", "bien", "la", "lo",
       "propuesta", "cambio", "el", "ya", "no.", "cancel", "discard", "it", "don't", "dont", "thanks"}
_NO_CLAVE = {"no", "descarta", "descartalo", "descartala", "descartar", "cancela", "cancelalo", "cancelala",
             "cancelar", "olvidalo", "dejalo", "cancel", "discard"}

_CAMBIO = re.compile(r"\b(c[aá]mbi|sub[eií]|b[aá]j[aeé]|pon|p[oó]n|mueve|mu[eé]v|mov[eé]|ajust|corrig|quit|agreg|"
                     r"crea|reemplaz|d[eé]jal|aument|disminu|reduc|modific|p[aá]sal)", re.I)
_NUMERO = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_APLICADO = re.compile(r"\b(cambio aplicado|aplicad[oa]s?\b|ya (lo |la )?apliqu|apliqu[eé]\b|ahora (es|est[aá]|"
                       r"queda|mide)\b|ya (est[aá]|qued[oó]) (cambiad|en)|se (aplic[oó]|cambi[oó]|modific[oó]))",
                       re.I)


def clasificar(texto):
    """"si" | "no" | None. Solo mensajes CORTOS de puro asentimiento o rechazo, sin cifras: «sí, aplícalo»,
    «ok», «dale» = sí; «no», «descártalo» = no. «No, cámbialo a -10» = None (es una corrección)."""
    palabras = _plano(texto)
    if not palabras or len(palabras) > 8 or _NUMERO.search(texto or ""):
        return None
    if all(p in _SI for p in palabras) and any(p in _SI_CLAVE for p in palabras):
        return "si"
    if all(p in _NO for p in palabras) and any(p in _NO_CLAVE for p in palabras):
        return "no"
    return None


def pide_cambio(texto):
    """¿El mensaje pide cambiar algo del dibujo? (verbo de cambio, o un «no, …» con una cifra)."""
    t = texto or ""
    if _CAMBIO.search(t):
        return True
    plano = _plano_txt(t)
    return bool(_NUMERO.search(t)) and bool(re.match(r"\s*(no|mejor|mas bien|en vez|en lugar)\b", plano)
                                            or re.search(r"\bpero\b", plano))


def _plano_txt(texto):
    return " ".join(_plano(texto))


def dice_aplicado(texto):
    """¿La respuesta de la IA dice que ya cambió algo? (no puede: solo el usuario aplica con el botón)."""
    return bool(_APLICADO.search(texto or ""))
