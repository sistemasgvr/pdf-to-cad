"""Índices de mapas en cuadrícula guardados como DATOS (2026-11-18, georreferencia automática).

Cada jurisdicción es un archivo `app/geo/indices/<id>.json.gz` (lo arma un script de `scripts/datos/`, la app
nunca consulta la red): sistema de coordenadas, palabras que confirman la jurisdicción y el polígono REAL de
cada celda (los cuartos de sección del PLSS no son cuadrados exactos) con su sección PLSS. Para otra ciudad
basta otro archivo. PURO: sin Qt."""
from __future__ import annotations

import functools
import gzip
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


def carpeta() -> str:
    """`app/geo/indices` (en el .exe, `_MEIPASS/geo/indices`, ver PDF-a-CAD.spec)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "geo", "indices")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "indices")


@dataclass(frozen=True)
class Celda:
    poligono: Tuple[Tuple[float, float], ...]
    plss: Tuple[str, str, int, str] = ("", "", 0, "")   # municipio «2N», rango «1E», sección, cuarto «NE»

    def centroide(self) -> Tuple[float, float]:
        n = len(self.poligono)
        return (sum(p[0] for p in self.poligono) / n, sum(p[1] for p in self.poligono) / n)

    def centro_caja(self) -> Tuple[float, float]:
        """Centro del recuadro de la celda: el mapa de cada hoja va centrado en él (el promedio de los vértices se
        corre hacia donde el polígono tiene más vértices: 260 pt en «16-25» de Phoenix, 2026-11-19)."""
        xs = [p[0] for p in self.poligono]
        ys = [p[1] for p in self.poligono]
        return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


@dataclass
class Indice:
    id: str
    nombre: str
    epsg: int
    palabras: List[str] = field(default_factory=list)
    fecha: str = ""
    fuente_url: str = ""
    recuadro_ft: float = 0.0                       # ancho en el mundo del recuadro del mapa de cada hoja (0 = no se sabe)
    celdas: Dict[str, Celda] = field(default_factory=dict)          # clave = el TEXTO de la celda («24-04»)

    def por_numero(self, fila: int, col: int) -> List[Tuple[str, Celda]]:
        """Celdas con esos números. En Phoenix «24-04» (al oeste del meridiano) y «24-4» (al este) son cuadros
        DISTINTOS: la hoja da números (`Ficha.celda`), así que puede haber más de una (desempata el PLSS)."""
        return [(k, self.celdas[k]) for k in self._numeros.get((fila, col), [])]

    def __post_init__(self):
        self._numeros: Dict[Tuple[int, int], List[str]] = {}
        for k in sorted(self.celdas):
            f, c = k.split("-")
            self._numeros.setdefault((int(f), int(c)), []).append(k)


def disponibles() -> List[str]:
    try:
        return sorted(f[:-len(".json.gz")] for f in os.listdir(carpeta()) if f.endswith(".json.gz"))
    except OSError:
        return []


@functools.lru_cache(maxsize=None)
def cargar(id_: str) -> Indice:
    with gzip.open(os.path.join(carpeta(), id_ + ".json.gz"), "rt", encoding="utf-8") as f:
        d = json.load(f)
    celdas = {}
    for k, v in d["celdas"].items():
        pl = v.get("plss") or ["", "", 0, ""]
        celdas[k] = Celda(tuple((float(x), float(y)) for x, y in v["p"]),
                                    (str(pl[0]), str(pl[1]), int(pl[2]), str(pl[3])))
    return Indice(d["id"], d.get("nombre", ""), int(d["epsg"]), [p.upper() for p in d.get("palabras", [])],
                  d.get("fecha", ""), d.get("fuente_url", ""), float(d.get("recuadro_ft") or 0.0), celdas)
