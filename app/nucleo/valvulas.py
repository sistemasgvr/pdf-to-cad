"""valvulas.py — las válvulas del proyecto (PURO; pedido del usuario 2026-11-05).

Las lee `reconocimiento/recognition_valvulas` y viven en `Main.valvulas` (px de la vista, .digproj, deshacer), aparte
de las estructuras: una válvula no parte la tubería ni cambia la red. Cada una es un dict:

    x, y        centro (px de la vista)
    utilidad    capa de la app («AGUA», «GAS»…) o "" si el plano no lo dice y no hay línea cerca
    tipo        solo si el PDF lo dice («De línea», «Purga»…); "" = válvula sin más
    estado      "abierta" | "cerrada" | ""
    origen      capa | leyenda | forma | manual
    certeza     segura | por_confirmar
    capa_pdf    capa o símbolo de donde salió

La tubería, el giro y el diámetro se calculan al pedirlos (`relacion`): un índice guardado quedaría viejo al borrar
utilidades, y así el diámetro sigue a la tubería si el usuario lo cambia.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

CAPA = "VALVULAS"                  # clave en «Capas ▾» (`Main.capas_apagadas`)
SEGURA, POR_CONFIRMAR = "segura", "por_confirmar"
CAPA_PDF, LEYENDA, FORMA, MANUAL = "capa", "leyenda", "forma", "manual"
MISMA_PX = 2.0                     # dos válvulas de la misma utilidad a menos de esto (px) = la misma
EN_LINEA_PT = 1.5                  # sobre una línea cualquiera: a ≤ esto (pt de la hoja)
UNIR_PT = 5.0                      # con su utilidad conocida, su tubería puede estar hasta aquí (topografía vs. diseño)


def tol_pt(v: dict) -> float:
    """Sin utilidad, solo vale una línea encima: más lejos podría ser la de otra red."""
    return UNIR_PT if v.get("utilidad") else EN_LINEA_PT


def nueva(x, y, utilidad="", tipo="", estado="", origen=CAPA_PDF, certeza=SEGURA, capa_pdf="") -> dict:
    return dict(x=float(x), y=float(y), utilidad=utilidad or "", tipo=tipo or "", estado=estado or "",
                origen=origen, certeza=certeza, capa_pdf=capa_pdf or "")


def juntar(existentes: Sequence[dict], nuevas: Sequence[dict]) -> List[dict]:
    """Las de antes + las nuevas que no estaban. Reimportar la misma hoja no las repite."""
    out = list(existentes)
    for v in nuevas:
        if not any(a.get("utilidad") == v.get("utilidad")
                   and math.hypot(a["x"] - v["x"], a["y"] - v["y"]) <= MISMA_PX for a in out):
            out.append(v)
    return out


def _pie(x, y, a, b) -> Tuple[float, float]:
    """(distancia al tramo a–b, rumbo del tramo en grados 0–180, con la y hacia arriba)."""
    ax, ay = a[0], a[1]
    dx, dy = b[0] - ax, b[1] - ay
    largo2 = dx * dx + dy * dy
    t = 0.0 if not largo2 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / largo2))
    return math.hypot(x - ax - t * dx, y - ay - t * dy), math.degrees(math.atan2(-dy, dx)) % 180.0


def mas_cercana(x, y, candidatas, tol, utilidad="") -> Optional[Tuple[int, float, float]]:
    """(índice, distancia, rumbo) de la línea más cercana a ≤ tol. `candidatas` = [(índice, capa, puntos)]; con
    `utilidad`, solo las de esa capa."""
    mejor = None
    for i, capa, pts in candidatas:
        if utilidad and capa != utilidad:
            continue
        for a, b in zip(pts, pts[1:]):
            d, rumbo = _pie(x, y, a, b)
            if d <= tol and (mejor is None or d < mejor[1]):
                mejor = (i, d, rumbo)
    return mejor


def relacion(v: dict, pipes: Sequence[dict], tol_px: float, cerca=None) -> Optional[Tuple[int, float, float]]:
    """La tubería de la válvula: (índice, distancia px, rumbo). `cerca(x, y, r)` = índices a revisar (índice de la
    ventana); sin él, todas."""
    indices = range(len(pipes)) if cerca is None else cerca(v["x"], v["y"], tol_px)
    return mas_cercana(v["x"], v["y"], [(i, pipes[i].get("layer"), pipes[i].get("pts") or ()) for i in indices],
                       tol_px, v.get("utilidad") or "")


N_ = lambda s: s          # noqa: E731  (marca para la traducción; los valores son datos)
TEXTOS = (N_("Válvula"), N_("De línea"), N_("Purga"), N_("Retención"), N_("Retención doble"),
          N_("Reguladora de presión"), N_("Mariposa"), N_("Aire"), N_("Compuerta"), N_("Riego"), N_("abierta"),
          N_("cerrada"))


def nombre(v: dict) -> str:
    """Tipo legible en español (el dato; la interfaz lo traduce con `t()`)."""
    return v.get("tipo") or "Válvula"
