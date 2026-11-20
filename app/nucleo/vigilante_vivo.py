"""vigilante_vivo.py — la sesión del vigilante leída EN VIVO (para el monitor; sin Qt).

`Sesion(carpeta).actualizar()` lee solo lo nuevo de cada `proc-<pid>.jsonl` (una línea a medias se guarda para la
próxima vuelta) y mantiene:
  · `procesos` {pid: Proceso}: nombre, último dato de memoria y CPU, trabajo y etapa EN CURSO, vivo o no;
  · `sucesos` (todo menos «sistema», que va resumido en `serie`);
  · `serie` [(t, memoria total MB, memoria de la ventana MB, CPU total %)] para la gráfica;
  · `ventana()` → estado de la ventana AHORA por su latido compartido (`vigilante.Latido`): responde / ocupada /
    no responde / cerrada, y desde cuándo.
"""
from __future__ import annotations

import glob
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from nucleo import vigilante as V

MAX_SERIE = 1800               # puntos de memoria (1 h a un punto cada 2 s)
RESPONDE, OCUPADA, NO_RESPONDE, CERRADA, SIN_DATO = "responde", "ocupada", "no_responde", "cerrada", "sin_dato"
MUERTO_S = 8.0                 # un proceso sin aparecer en la medición de sistema este tiempo = terminó


@dataclass
class Proceso:
    pid: int
    nombre: str = ""
    inicio: float = 0.0
    priv_mb: Optional[float] = None
    pico_mb: float = 0.0
    cpu_pct: Optional[float] = None
    hilos: int = 0
    visto: float = 0.0
    trabajo: Optional[Tuple[str, float]] = None      # (objetivo, desde)
    etapa: Optional[Tuple[str, float]] = None        # (texto, desde)
    trabajos: int = 0
    vivo: bool = True


@dataclass
class Sesion:
    carpeta: str
    procesos: Dict[int, Proceso] = field(default_factory=dict)
    sucesos: List[dict] = field(default_factory=list)
    serie: List[tuple] = field(default_factory=list)
    ram_total_mb: Optional[float] = None
    ram_libre_mb: Optional[float] = None
    pid_ventana: Optional[int] = None
    cambios: int = 0                                 # sube cada vez que llega algo que no es «sistema»
    _pos: Dict[str, int] = field(default_factory=dict)
    _resto: Dict[str, str] = field(default_factory=dict)

    def actualizar(self) -> int:
        """Lee lo nuevo. Devuelve cuántos sucesos llegaron."""
        nuevos = []
        for ruta in sorted(glob.glob(os.path.join(self.carpeta, "proc-*.jsonl"))):
            try:
                with open(ruta, "rb") as f:
                    f.seek(self._pos.get(ruta, 0))
                    datos = f.read()
                    self._pos[ruta] = f.tell()
            except OSError:
                continue
            if not datos:
                continue
            texto = self._resto.pop(ruta, "") + datos.decode("utf-8", "replace")
            lineas = texto.split("\n")
            if lineas[-1]:
                self._resto[ruta] = lineas[-1]       # a medias: la próxima vez
            for linea in lineas[:-1]:
                if linea.strip():
                    try:
                        nuevos.append(json.loads(linea))
                    except ValueError:
                        pass
        nuevos.sort(key=lambda e: e.get("t", 0))
        for e in nuevos:
            self._aplicar(e)
        self._marcar_muertos()
        return len(nuevos)

    def _proc(self, pid) -> Proceso:
        p = self.procesos.get(pid)
        if p is None:
            p = self.procesos[pid] = Proceso(pid=pid)
        return p

    def _aplicar(self, e: dict) -> None:
        tipo, pid, t = e.get("tipo"), e.get("pid"), e.get("t", 0.0)
        if tipo == "sistema":
            self._sistema(e)
            return
        self.sucesos.append(e)
        self.cambios += 1
        p = self._proc(pid)
        p.visto = max(p.visto, t)
        if tipo == "inicio":
            p.nombre, p.inicio = e.get("nombre") or p.nombre, t
            if e.get("nombre") == "ventana":
                self.pid_ventana = pid
        elif tipo == "trabajo_inicio":
            p.trabajo, p.etapa = (e.get("objetivo") or "?", t), None
        elif tipo == "trabajo":
            p.trabajo, p.etapa = None, None
            p.trabajos += 1
        elif tipo == "etapa_inicio" and e.get("hilo") == "MainThread":
            p.etapa = (e.get("texto") or "", t)
        elif tipo == "fin":
            p.vivo = False
        elif tipo == "monitor" and e.get("pid_monitor"):
            self._proc(e["pid_monitor"]).nombre = "monitor"

    def _sistema(self, e: dict) -> None:
        t = e.get("t", 0.0)
        self.ram_total_mb = e.get("ram_total_mb", self.ram_total_mb)
        self.ram_libre_mb = e.get("ram_libre_mb", self.ram_libre_mb)
        total = cpu = 0.0
        ventana = None
        for d in e.get("procesos") or []:
            p = self._proc(d.get("pid"))
            if not p.nombre:
                p.nombre = d.get("exe") or ""
            p.priv_mb, p.cpu_pct, p.hilos = d.get("priv_mb"), d.get("cpu_pct"), d.get("hilos") or 0
            p.pico_mb = max(p.pico_mb, d.get("pico_mb") or 0.0, p.priv_mb or 0.0)
            p.visto, p.vivo = t, True
            total += p.priv_mb or 0.0
            cpu += p.cpu_pct or 0.0
            if p.pid == e.get("pid"):
                ventana = p.priv_mb
        self.serie.append((t, round(total, 1), ventana, round(cpu, 1)))
        if len(self.serie) > MAX_SERIE:
            del self.serie[:len(self.serie) - MAX_SERIE]

    def _marcar_muertos(self) -> None:
        if not self.serie:
            return
        ultimo = self.serie[-1][0]
        for p in self.procesos.values():
            if p.vivo and p.visto and ultimo - p.visto > MUERTO_S:
                p.vivo = False
                p.trabajo = p.etapa = None

    def ventana(self, ahora: Optional[float] = None) -> Tuple[str, float]:
        """(estado, segundos): responde / ocupada (sin latir > umbral) / no_responde (≥ 5 s) / cerrada / sin_dato."""
        if self.pid_ventana is None:
            return SIN_DATO, 0.0
        t = V.Latido.leer(os.path.join(self.carpeta, f"latido-{self.pid_ventana}.bin"))
        if t is None:
            return SIN_DATO, 0.0
        if t < 0:
            return CERRADA, 0.0
        quieto = (ahora or time.time()) - t
        if quieto >= V.NO_RESPONDE_S:
            return NO_RESPONDE, quieto
        if quieto > V.UMBRAL_CONGELA_S + V.LATIDO_MS / 1000.0:
            return OCUPADA, quieto
        return RESPONDE, quieto

    def de_tipo(self, *tipos) -> List[dict]:
        return [e for e in self.sucesos if e.get("tipo") in tipos]

    def nombre(self, pid) -> str:
        p = self.procesos.get(pid)
        return (p.nombre if p else "") or str(pid)

    def dentro_de(self, trabajo: dict) -> List[dict]:
        """Bloques y etapas del mismo proceso y hilo durante ese trabajo (para su detalle)."""
        fin = trabajo.get("t", 0.0)
        ini = fin - (trabajo.get("dur") or 0.0) - 0.01
        return [e for e in self.sucesos if e.get("pid") == trabajo.get("pid") and e.get("hilo") == trabajo.get("hilo")
                and e.get("tipo") in ("bloque", "etapa") and ini <= e.get("t", 0.0) <= fin + 0.01
                and not (e.get("nombre") or "").startswith("Trabajo ")]
