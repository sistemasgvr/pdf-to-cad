"""Lo que la IA APRENDE de un proyecto (PURO), en TEXTO PLANO en una carpeta junto al .digproj (pedido del
usuario 2026-10-23: «que se guarde en la misma carpeta del proyecto»).

    Mi proyecto.digproj
    Mi proyecto - IA/
        LEEME.txt              qué es cada archivo
        ensenanzas.jsonl       lo que el equipo le enseñó: notas, correcciones, respuestas valoradas y soluciones aplicadas
        conversaciones.jsonl   cada pregunta y su respuesta (historial)
        redaccion.jsonl        textos del informe ya redactados (para no volver a pedirlos)

JSONL = una línea JSON por registro, UTF-8: se lee con el Bloc de notas, se puede copiar a otro proyecto o
juntar después en una base central (el formato no cambia). Sin proyecto guardado todo queda en memoria y se
escribe al guardar (`vincular`). La IA no se reentrena: antes de cada consulta, `buscar` trae las enseñanzas
más parecidas y van en el pedido.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import shutil
import threading

from ia.texto import raices

ENSENANZAS, CONVERSACIONES, REDACCION = "ensenanzas.jsonl", "conversaciones.jsonl", "redaccion.jsonl"
NOTA, CORRECCION, VALORACION, SOLUCION = "nota", "correccion", "valoracion", "solucion"
SUFIJO = " - IA"
LEEME = """Carpeta de aprendizaje de la IA de PDF-a-CAD para este proyecto.

ensenanzas.jsonl      Lo que el equipo le enseñó a la IA: notas («recuerda que…»), correcciones de respuestas,
                      respuestas marcadas como útiles o no y las soluciones de conflictos que se aplicaron. La IA
                      las vuelve a leer antes de responder.
conversaciones.jsonl  Historial de «Pregúntale al proyecto»: cada pregunta, su respuesta y el modelo que respondió.
redaccion.jsonl       Textos del informe automático ya redactados por la IA (evita pedirlos otra vez).

Son archivos de texto: una línea por registro. Se pueden revisar, borrar una línea o copiar la carpeta a otro
proyecto. Si se borra la carpeta, la IA olvida lo aprendido en este proyecto (el proyecto no cambia).
"""


def carpeta_de(ruta_proyecto):
    """«C:/obra/Mi proyecto.digproj» → «C:/obra/Mi proyecto - IA». None sin proyecto guardado."""
    if not ruta_proyecto:
        return None
    base, _ext = os.path.splitext(ruta_proyecto)
    return base + SUFIJO


def ahora():
    return _dt.datetime.now().isoformat(timespec="seconds")


class Memoria:
    def __init__(self, carpeta=None, leeme=LEEME):
        self._lock = threading.Lock()
        self._leeme = leeme
        self._datos = {ENSENANZAS: [], CONVERSACIONES: [], REDACCION: []}
        self._pendientes = []                     # (archivo, registro) sin escribir (proyecto sin guardar)
        self._indice = []                         # (raíces, registro) de las enseñanzas, para `buscar`
        self._cache = {}                          # clave → texto (redacción)
        self.carpeta = None
        self.error = ""
        if carpeta:
            self.vincular(carpeta)

    # ── carpeta ──
    def vincular(self, carpeta):
        """Usa `carpeta` (la lee si existe) y escribe ahí lo que quedó pendiente."""
        with self._lock:
            self.carpeta = carpeta
            for k in self._datos:
                self._datos[k] = []
            self._indice, self._cache = [], {}
            for archivo in self._datos:
                for reg in _leer(os.path.join(carpeta, archivo)):
                    self._sumar(archivo, reg)
            pend, self._pendientes = self._pendientes, []
        for archivo, reg in pend:                  # lo de antes de guardar el proyecto, al final
            self._guardar(archivo, reg, sumar=True)

    def copiar_a(self, carpeta_nueva):
        """«Guardar como…»: la memoria sigue al proyecto (copia la carpeta si la nueva no existe)."""
        if self.carpeta and os.path.isdir(self.carpeta) and not os.path.exists(carpeta_nueva):
            try:
                shutil.copytree(self.carpeta, carpeta_nueva)
            except OSError as e:
                self.error = str(e)
        self.vincular(carpeta_nueva)

    # ── escribir ──
    def agregar(self, archivo, **datos):
        reg = {"fecha": ahora(), **datos}
        self._guardar(archivo, reg, sumar=True)
        return reg

    def ensenar(self, tipo, texto, **extra):
        return self.agregar(ENSENANZAS, tipo=tipo, texto=str(texto).strip(), **extra)

    def _guardar(self, archivo, reg, sumar):
        with self._lock:
            if sumar:
                self._sumar(archivo, reg)
            if not self.carpeta:
                self._pendientes.append((archivo, reg))
                return
            try:
                os.makedirs(self.carpeta, exist_ok=True)
                leeme = os.path.join(self.carpeta, "LEEME.txt")
                if not os.path.exists(leeme):
                    with open(leeme, "w", encoding="utf-8") as f:
                        f.write(self._leeme)
                with open(os.path.join(self.carpeta, archivo), "a", encoding="utf-8") as f:
                    f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                self.error = ""
            except OSError as e:                   # carpeta de solo lectura: sigue en memoria
                self.error = str(e)
                self._pendientes.append((archivo, reg))

    def _sumar(self, archivo, reg):
        self._datos.setdefault(archivo, []).append(reg)
        if archivo == ENSENANZAS:
            self._indice.append((raices(" ".join(str(reg.get(k) or "") for k in ("texto", "pregunta"))), reg))
        elif archivo == REDACCION and reg.get("clave"):
            self._cache[reg["clave"]] = reg.get("texto") or ""

    # ── leer ──
    def registros(self, archivo):
        with self._lock:
            return list(self._datos.get(archivo, []))

    def redaccion(self, clave):
        return self._cache.get(clave)

    def guardar_redaccion(self, clave, texto, modelo=""):
        if self._cache.get(clave) != texto:
            self.agregar(REDACCION, clave=clave, texto=texto, modelo=modelo)

    def buscar(self, texto, k=5, minimo=1):
        """Las `k` enseñanzas más parecidas a `texto` (palabras en común, pesadas por lo raras que son y por
        el largo). Las notas y correcciones pesan más que una respuesta solo valorada; las valoradas como
        «no útil» sin corrección no se traen."""
        q = raices(texto)
        if not q:
            return []
        with self._lock:
            indice = list(self._indice)
        n = len(indice) or 1
        df = {}
        for r, _reg in indice:
            for p in r & q:
                df[p] = df.get(p, 0) + 1
        puntos = []
        for orden, (r, reg) in enumerate(indice):
            if reg.get("tipo") == VALORACION and (reg.get("valor") or 0) < 0:
                continue
            comun = r & q
            if len(comun) < minimo:
                continue
            s = sum(math.log(1 + n / df[p]) for p in comun) / math.sqrt(len(r) or 1)
            s *= 1.5 if reg.get("tipo") in (NOTA, CORRECCION, SOLUCION) else 1.0
            puntos.append((s, orden, reg))         # a igual puntaje, la más nueva
        puntos.sort(key=lambda x: (-x[0], -x[1]))
        return [reg for _s, _o, reg in puntos[:k]]

    def notas(self):
        """Todas las notas del equipo (reglas del proyecto), en orden."""
        return [r for r in self.registros(ENSENANZAS) if r.get("tipo") == NOTA]


def _leer(ruta):
    if not os.path.isfile(ruta):
        return []
    out = []
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except ValueError:
                continue                           # una línea rota (editada a mano) no tumba la memoria
            if isinstance(reg, dict):
                out.append(reg)
    return out
