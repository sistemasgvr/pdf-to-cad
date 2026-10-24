"""Lo que la IA APRENDE (PURO): UN solo archivo JSON en la carpeta del repo (pedido del usuario 2026-10-23:
«que se guarde en el propio proyecto, en un solo JSON… yo lo entreno, le mando mis cambios por Git a Santos, él
también lo entrena y me manda los suyos»; más adelante irá a un servidor).

    pdf-to-cad/entrenamiento_ia/desarrollo.json      (o produccion.json / cliente.json, ver ENTORNOS)
    {
      "version": 1,
      "ensenanzas":     [ {id, fecha, autor, proyecto, tipo, texto, …}, … ],   notas, correcciones, valoraciones,
                                                                              soluciones aplicadas
      "conversaciones": [ {id, fecha, autor, proyecto, pregunta, respuesta, modelo, …}, … ],
      "redaccion":      { clave: {texto, modelo, fecha, autor, ambito}, … }   textos ya redactados (informe,
                                                                              reglas explicadas, ayuda del manual)
    }

ENTORNOS (pedido del usuario 2026-10-24; «Configurar IA…» → «Entorno de entrenamiento», `rutas`):
  desarrollo  (desde el repo) escribe `entrenamiento_ia/desarrollo.json`, que se pasa por Git, y lee producción;
  producción  (el .exe del cliente) lee `entrenamiento_ia/produccion.json`, que viaja en el instalador y nunca
              se escribe, y guarda lo que enseña el cliente en `%APPDATA%/pdf-to-cad/entrenamiento_ia/cliente.json`
              (no se borra al actualizar; luego se le pide que lo comparta).

Para que Git junte lo de dos personas sin conflictos: cada registro lleva un `id` al azar y las listas se
escriben ORDENADAS por id (lo nuevo cae en cualquier lugar, no siempre al final), un campo por línea, y la
redacción por clave ordenada. La app siempre LEE el archivo antes de escribir y junta por id (un `git pull` con
la app abierta no se pisa). Un archivo roto (conflicto de Git sin resolver) no tumba la app: se avisa en
`error` y no se escribe encima.

Las enseñanzas valen para TODOS los proyectos (es lo que se entrena entre los dos); `proyecto` (nombre del
.digproj) queda de referencia y las del mismo proyecto pesan más al buscar. Las notas para redactar el informe
son las del proyecto. La IA no se reentrena: antes de cada consulta, `buscar` trae las enseñanzas más parecidas
y van en el pedido.
"""
from __future__ import annotations

import datetime as _dt
import getpass
import json
import math
import os
import sys
import threading
import uuid

from ia.texto import raices

ENSENANZAS, CONVERSACIONES, REDACCION = "ensenanzas", "conversaciones", "redaccion"
NOTA, CORRECCION, VALORACION, SOLUCION = "nota", "correccion", "valoracion", "solucion"
CARPETA = "entrenamiento_ia"
DESARROLLO, PRODUCCION = "desarrollo", "produccion"
ENTORNOS = (DESARROLLO, PRODUCCION)
ARCHIVO_DESARROLLO, ARCHIVO_PRODUCCION, ARCHIVO_CLIENTE = "desarrollo.json", "produccion.json", "cliente.json"
VERSION = 1
MISMO_PROYECTO = 1.5                  # peso de una enseñanza del mismo proyecto al buscar
SUFIJO = " - IA"                      # carpeta vieja junto al .digproj (se importa una vez: `importar_carpeta`)


def ahora():
    return _dt.datetime.now().isoformat(timespec="seconds")


def autor():
    try:
        return getpass.getuser()
    except Exception:                                      # noqa: BLE001
        return ""


def entorno_por_defecto():
    """Programa instalado (.exe) = producción; desde el repo = desarrollo."""
    return PRODUCCION if getattr(sys, "frozen", False) else DESARROLLO


_entorno = None


def configurar(entorno):
    """El entorno elegido en «Configurar IA…» (lo llama la ventana al leer la configuración)."""
    global _entorno
    _entorno = entorno if entorno in ENTORNOS else None


def entorno():
    return _entorno or entorno_por_defecto()


def _carpeta_programa():
    """`entrenamiento_ia/` del repo (junto a `app/`) o, en el .exe, la que viaja dentro (`_MEIPASS`)."""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), CARPETA)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), CARPETA)


def rutas(ent=None):
    """(archivo donde se ESCRIBE, [archivos que solo se LEEN]) según el entorno.

    desarrollo  escribe `entrenamiento_ia/desarrollo.json` (repo, se pasa por Git) y lee también producción;
    producción  lee `produccion.json` (viaja en el instalador, solo lectura) y escribe lo del cliente en
                `%APPDATA%/pdf-to-cad/entrenamiento_ia/cliente.json` (una actualización no lo borra; luego se le
                pide que lo comparta). `PDFCAD_ENTRENAMIENTO_IA` (+ `_BASE`) los cambia (pruebas)."""
    env = os.environ.get("PDFCAD_ENTRENAMIENTO_IA")
    if env:
        base = os.environ.get("PDFCAD_ENTRENAMIENTO_IA_BASE")
        return env, [base] if base else []
    prod = os.path.join(_carpeta_programa(), ARCHIVO_PRODUCCION)
    if (ent or entorno()) == PRODUCCION:
        datos = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "pdf-to-cad")
        return os.path.join(datos, CARPETA, ARCHIVO_CLIENTE), [prod]
    return os.path.join(_carpeta_programa(), ARCHIVO_DESARROLLO), [prod]


def ruta_archivo():
    """Donde se escribe lo aprendido (según el entorno)."""
    return rutas()[0]


def nombre_proyecto(ruta):
    """«C:/obra/Mi proyecto.digproj» → «Mi proyecto». None sin proyecto guardado."""
    if not ruta:
        return None
    base = os.path.splitext(os.path.basename(str(ruta).rstrip("/\\")))[0]
    return base[:-len(SUFIJO)] if base.endswith(SUFIJO) else base


def carpeta_de(ruta_proyecto):
    """Carpeta VIEJA de aprendizaje junto al .digproj («Mi proyecto - IA»), para importarla."""
    if not ruta_proyecto:
        return None
    return os.path.splitext(ruta_proyecto)[0] + SUFIJO


class Almacen:
    """El archivo JSON compartido (uno por ruta, para todo el proceso)."""
    _todos = {}
    _lock_todos = threading.Lock()

    @classmethod
    def de(cls, ruta=None):
        ruta = os.path.abspath(ruta or ruta_archivo())
        with cls._lock_todos:
            a = cls._todos.get(ruta)
            if a is None:
                a = cls._todos[ruta] = cls(ruta)
            return a

    def __init__(self, ruta):
        self.ruta = ruta
        self.carpeta = os.path.dirname(ruta)
        self.lock = threading.RLock()
        self.error = ""
        self._mtime = None
        self.datos = self._vacio()
        self.recargar()

    @staticmethod
    def _vacio():
        return {"version": VERSION, ENSENANZAS: [], CONVERSACIONES: [], REDACCION: {}}

    def _leer_disco(self):
        if not os.path.isfile(self.ruta):
            return self._vacio()
        with open(self.ruta, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("no es un objeto JSON")
        out = self._vacio()
        for k in (ENSENANZAS, CONVERSACIONES):
            out[k] = [r for r in d.get(k) or [] if isinstance(r, dict)]
        out[REDACCION] = {k: v for k, v in (d.get(REDACCION) or {}).items() if isinstance(v, dict)}
        return out

    def recargar(self):
        """Relee el archivo si cambió (otro proceso, un `git pull`, una edición a mano). Devuelve True si cambió."""
        with self.lock:
            try:
                m = os.path.getmtime(self.ruta) if os.path.isfile(self.ruta) else None
                if m == self._mtime and self._mtime is not None:
                    return False
                disco = self._leer_disco()
            except (OSError, ValueError) as e:
                self.error = f"{self.ruta}: {e}"
                return False
            self.datos = disco                          # lo del disco manda: borrar a mano una línea vale
            self._mtime = m
            self.error = ""
            return True

    def _juntar(self, otro):
        for k in (ENSENANZAS, CONVERSACIONES):
            ids = {r.get("id") for r in self.datos[k]}
            self.datos[k] += [r for r in otro[k] if r.get("id") not in ids]
        for k, v in otro[REDACCION].items():
            self.datos[REDACCION].setdefault(k, v)

    def escribir(self, juntar=True):
        """Junta con lo que hay en el disco (lo que llegó entre leer y escribir) y escribe (ordenado, atómico)."""
        with self.lock:
            try:
                if juntar and os.path.isfile(self.ruta):
                    self._juntar(self._leer_disco())
            except (OSError, ValueError) as e:              # archivo roto (conflicto de Git): no pisarlo
                self.error = f"{self.ruta}: {e}"
                return False
            d = {"version": VERSION,
                 ENSENANZAS: sorted(self.datos[ENSENANZAS], key=lambda r: str(r.get("id"))),
                 CONVERSACIONES: sorted(self.datos[CONVERSACIONES], key=lambda r: str(r.get("id"))),
                 REDACCION: dict(sorted(self.datos[REDACCION].items()))}
            try:
                os.makedirs(self.carpeta, exist_ok=True)
                tmp = self.ruta + ".tmp"
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
                    f.write("\n")
                os.replace(tmp, self.ruta)
                self._mtime = os.path.getmtime(self.ruta)
                self.error = ""
                return True
            except OSError as e:
                self.error = f"{self.ruta}: {e}"
                return False


class Memoria:
    """Lo aprendido, visto desde UN proyecto (`proyecto` = ruta o nombre del .digproj; None = sin guardar)."""

    def __init__(self, proyecto=None, archivo=None, ambito="proyecto", **_viejo):
        escribir, leer = rutas()
        self.almacen = Almacen.de(archivo or escribir)
        # solo lectura (producción): nunca se escriben desde la app
        self.bases = [] if archivo else [Almacen.de(b) for b in leer
                                         if os.path.abspath(b) != os.path.abspath(escribir)]
        self.ambito = ambito
        self.proyecto = nombre_proyecto(proyecto)
        self._sin_proyecto = []                    # registros creados antes de guardar el proyecto
        self._indice_n = -1
        self._indice = []

    # ── dónde ──
    @property
    def carpeta(self):
        return self.almacen.carpeta

    @property
    def ruta(self):
        return self.almacen.ruta

    @property
    def error(self):
        return self.almacen.error

    def vincular(self, proyecto):
        """El proyecto se guardó (o se guardó como…): lo aprendido sin proyecto pasa a ser de él."""
        self.proyecto = nombre_proyecto(proyecto)
        if self._sin_proyecto and self.proyecto:
            ids = set(self._sin_proyecto)
            with self.almacen.lock:
                self.almacen.recargar()
                for seccion in (ENSENANZAS, CONVERSACIONES):
                    for reg in self.almacen.datos[seccion]:
                        if reg.get("id") in ids:
                            reg["proyecto"] = self.proyecto
                self._sin_proyecto = []
                self.almacen.escribir(juntar=False)

    copiar_a = vincular

    # ── escribir ──
    def agregar(self, seccion, **datos):
        reg = {"id": uuid.uuid4().hex, "fecha": ahora(), "autor": autor(), "proyecto": self.proyecto, **datos}
        with self.almacen.lock:
            self.almacen.recargar()
            self.almacen.datos[seccion].append(reg)
        if not self.proyecto:
            self._sin_proyecto.append(reg["id"])
        self.almacen.escribir()
        return reg

    def ensenar(self, tipo, texto, **extra):
        return self.agregar(ENSENANZAS, tipo=tipo, texto=str(texto).strip(), **extra)

    def guardar_redaccion(self, clave, texto, modelo=""):
        with self.almacen.lock:
            previa = self.almacen.datos[REDACCION].get(clave)
            if previa and previa.get("texto") == texto:
                return
            self.almacen.datos[REDACCION][clave] = {"texto": texto, "modelo": modelo, "fecha": ahora(),
                                                    "autor": autor(), "ambito": self.ambito}
        self.almacen.escribir()

    # ── leer ──
    def registros(self, seccion):
        """Enseñanzas: todas (de cualquier proyecto). Conversaciones: las de este proyecto."""
        regs, ids = [], set()
        for a in [self.almacen] + self.bases:
            a.recargar()
            with a.lock:
                for reg in a.datos.get(seccion) or []:
                    if reg.get("id") not in ids:
                        ids.add(reg.get("id"))
                        regs.append(reg)
        if seccion == CONVERSACIONES:
            regs = [r for r in regs if r.get("proyecto") == self.proyecto]
        return sorted(regs, key=lambda r: (str(r.get("fecha") or ""), str(r.get("id"))))

    def redaccion(self, clave):
        for a in [self.almacen] + self.bases:
            a.recargar()
            with a.lock:
                r = a.datos[REDACCION].get(clave)
            if r:
                return r.get("texto")
        return None

    def _indice_ens(self):
        regs = self.registros(ENSENANZAS)
        if len(regs) != self._indice_n or (regs and self._indice and regs[-1] is not self._indice[-1][1]):
            self._indice = [(raices(" ".join(str(r.get(k) or "") for k in ("texto", "pregunta"))), r) for r in regs]
            self._indice_n = len(regs)
        return self._indice

    def buscar(self, texto, k=5, minimo=1):
        """Las `k` enseñanzas más parecidas a `texto` (palabras en común, pesadas por lo raras que son y por
        el largo). Las notas y correcciones pesan más que una respuesta solo valorada, y las del mismo proyecto
        más que las de otros; las valoradas como «no útil» sin corrección no se traen."""
        q = raices(texto)
        if not q:
            return []
        indice = self._indice_ens()
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
            s *= MISMO_PROYECTO if self.proyecto and reg.get("proyecto") == self.proyecto else 1.0
            puntos.append((s, orden, reg))         # a igual puntaje, la más nueva
        puntos.sort(key=lambda x: (-x[0], -x[1]))
        return [reg for _s, _o, reg in puntos[:k]]

    def notas(self):
        """Las notas del equipo para ESTE proyecto, en orden."""
        return [r for r in self.registros(ENSENANZAS) if r.get("tipo") == NOTA and r.get("proyecto") == self.proyecto]

    # ── la carpeta vieja («<proyecto> - IA», JSONL) ──
    def importar_carpeta(self, carpeta):
        """Pasa al JSON lo que había en la carpeta vieja junto al .digproj (una vez: por id derivado del
        contenido, repetir no duplica). Devuelve cuántos registros entraron."""
        import hashlib
        if not carpeta or not os.path.isdir(carpeta):
            return 0
        nuevos = 0
        with self.almacen.lock:
            self.almacen.recargar()
            for seccion, archivo in ((ENSENANZAS, "ensenanzas.jsonl"), (CONVERSACIONES, "conversaciones.jsonl"),
                                     (REDACCION, "redaccion.jsonl")):
                for reg in _leer_jsonl(os.path.join(carpeta, archivo)):
                    if seccion == REDACCION:
                        if reg.get("clave") and reg["clave"] not in self.almacen.datos[REDACCION]:
                            self.almacen.datos[REDACCION][reg["clave"]] = {
                                "texto": reg.get("texto") or "", "modelo": reg.get("modelo", ""),
                                "fecha": reg.get("fecha", ""), "autor": autor(), "ambito": self.ambito}
                            nuevos += 1
                        continue
                    rid = hashlib.sha1(json.dumps(reg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
                    if any(r.get("id") == rid for r in self.almacen.datos[seccion]):
                        continue
                    self.almacen.datos[seccion].append({"autor": autor(), "proyecto": self.proyecto, **reg,
                                                        "id": rid})
                    nuevos += 1
        if nuevos:
            self.almacen.escribir()
        return nuevos


def _leer_jsonl(ruta):
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
                continue
            if isinstance(reg, dict):
                out.append(reg)
    return out
