"""«¿Qué significa esta regla?» (PURO). Pedido del usuario 2026-10-23: en Normativas, elegir una regla y que la IA
la explique en palabras sencillas, GUARDANDO la respuesta: la misma regla no se vuelve a preguntar; si la regla
cambia (cualquier celda), sí.

La explicación se guarda en el entrenamiento compartido de la IA (`ia.memoria`: `entrenamiento_ia/
entrenamiento_ia.json`, sección «redaccion», ámbito «normas»; las reglas valen para todos los proyectos). Clave =
las celdas de la regla + idioma + versión del pedido (el modelo NO: cambiar de modelo no vuelve a gastar).

La IA recibe la fila, la regla leída como frase (`normas_tablas.frase`) y qué mide su REVISAR
(`normas_excel_ayuda.EXPLICA`). Las cifras que escriba y no estén en la regla se marcan (como en el chat).
"""
from __future__ import annotations

import hashlib
import json
import os

from ia.consulta import idioma
from ia.memoria import Memoria
from ia.texto import no_respaldados, numeros
from nucleo import normas_catalogo as nc
from nucleo import normas_excel_ayuda as ayuda
from nucleo import normas_reglas as NR
from nucleo import normas_tablas as NT
from traduccion.i18n_core import t

VERSION_PROMPT = 1

SISTEMA = """Explicas normativas de diseño de redes de utilidades (agua, alcantarillado, drenaje, gas, eléctrico y \
telecomunicaciones) a personas que no son especialistas. Escribe en {idioma}, claro y breve.
Reglas:
1. Usa SOLO los datos de la regla. No inventes normas, valores ni excepciones.
2. Los únicos números que puedes escribir son los de la regla; en los ejemplos usa esos mismos valores (el límite).
3. De 3 a 6 frases, sin títulos ni listas: qué revisa y por qué importa, a qué tuberías o elementos aplica, qué \
valor pide, cuándo sale un aviso y qué hacer en la app si sale (cambiar el diámetro, las cotas, el material…)."""

_cache = {}


def carpeta():
    """La carpeta del entrenamiento compartido (`ia.memoria`)."""
    return memoria().carpeta


def memoria():
    from ia.memoria import ruta_archivo
    r = ruta_archivo()
    m = _cache.get(r)
    if m is None:
        m = _cache[r] = Memoria(ambito="normas")
    return m


def _celdas(fila):
    return {col: str(v).strip() for col, v in zip(NR.COLUMNAS, fila) if str(v).strip()}


def clave(fila):
    celdas = _celdas(fila)
    return hashlib.sha1(json.dumps(["norma", VERSION_PROMPT, idioma(), celdas], ensure_ascii=False,
                                   sort_keys=True).encode("utf-8")).hexdigest()


def datos(fila):
    """Lo que recibe la IA, o None si la fila no es una regla completa (celdas sin llenar o que no se entienden)."""
    r, mal = NR.leer_fila(fila)
    if r is None or mal:
        return None
    d = {"regla": _celdas(fila), "leida": NT.frase(fila), "que_mide": ayuda.EXPLICA.get(r["revisar"], "")}
    return d


def guardada(fila):
    return memoria().redaccion(clave(fila))


def plantilla(fila):
    """Sin IA: la regla leída como frase + qué mide."""
    d = datos(fila)
    if d is None:
        return ""
    return d["leida"] + ("\n\n" + d["que_mide"] if d["que_mide"] else "")


def explicar(proveedor, fila, al_texto=None, cancelado=None):
    """(texto, origen) con origen «memoria» o «ia». Lanza `ErrorIA` si la IA no responde y ValueError si la fila
    no es una regla completa."""
    d = datos(fila)
    if d is None:
        raise ValueError(t("La regla tiene celdas sin completar o que no se entienden: guárdala primero."))
    k = clave(fila)
    previa = memoria().redaccion(k)
    if previa:
        return previa, "memoria"
    msg = t("Explica esta regla de la tabla de normativas:") + "\n" + json.dumps(d, ensure_ascii=False)
    r = proveedor.chat([{"role": "user", "content": msg}], sistema=SISTEMA.format(idioma=idioma()),
                       al_texto=al_texto, cancelado=cancelado)
    texto = " ".join(r.texto.split())
    if texto and not (cancelado and cancelado()):
        memoria().guardar_redaccion(k, texto, r.modelo)
    return texto, "ia"


def cifras_sin_respaldo(fila, texto):
    d = datos(fila)
    return no_respaldados(texto, numeros(json.dumps(d, ensure_ascii=False))) if d else []
