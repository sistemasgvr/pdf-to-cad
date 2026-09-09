"""duct_bank.py — Modelo de datos del Duct Bank (sin Qt).

Un "duct bank" es un bloque prismático de concreto que envuelve varios conductos
(circulares) por los que pasan otras utilidades (telecom, eléctrico, gas, …). En
este proyecto se representa por su SECCIÓN transversal:

  - Envolvente (rectángulo): ancho × alto en pulgadas.
  - Conductos (círculos): (cx, cy, diam) en pulgadas, referidos a la esquina
    superior-izquierda de la envolvente (X→derecha, Y→abajo, como en el lienzo).

La sección se dibuja una sola vez en Python y luego se "extruye" a lo largo del
alineamiento de la utilidad correspondiente:
  - Cada conducto → un tramo de Pipe Network con familia redonda del catálogo.
  - Envolvente → un sólido 3D independiente (capa "PDFCAD_DUCT_BANK") — no es
    una Pipe, solo geometría visual.

Este módulo NO importa Qt. Toda la lógica de validación y serialización es
testeable en headless.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

# Diámetros típicos para conductos de duct bank (pulgadas). No hay uno "estándar"
# fijo — depende del proyecto — pero cubrimos el 95% de lo que un cliente usa
# (telecom 2", eléctrico 4"–6"). Fuera de esta lista, el usuario puede tipear
# un valor libre en el campo de diámetro.
DUCT_DIAMETERS_IN = [2.0, 3.0, 4.0, 5.0, 6.0]

# Snap por defecto en pulgadas (0.25" = 1/4"). El grid del lienzo es cada 1".
DEFAULT_SNAP_IN = 0.25

# Límite duro de conductos para prevenir escenas absurdas. Un duct bank real
# rara vez pasa de ~30 conductos; a 200 el modelo sigue siendo válido pero la
# UI empieza a ir lenta y el usuario probablemente se equivocó.
MAX_CONDUITS = 200


@dataclass
class Conduit:
    """Un conducto circular dentro del duct bank. Todas las medidas en pulgadas."""
    cx: float          # centro X, desde borde izquierdo de la envolvente
    cy: float          # centro Y, desde borde superior de la envolvente
    diam: float        # diámetro (pulgadas)
    label: str = ""    # etiqueta opcional (ej. "T1", "E-4")

    def to_dict(self) -> Dict[str, Any]:
        return {"cx": float(self.cx), "cy": float(self.cy),
                "diam": float(self.diam), "label": self.label or ""}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Conduit":
        return cls(cx=float(d["cx"]), cy=float(d["cy"]),
                   diam=float(d["diam"]), label=str(d.get("label", "")))


@dataclass
class DuctBank:
    """Sección transversal de un duct bank."""
    name: str = ""
    width_in: float = 12.0       # ancho de la envolvente (pulgadas)
    height_in: float = 8.0       # alto de la envolvente (pulgadas)
    conduits: List[Conduit] = field(default_factory=list)

    # ── Margen interior (pulgadas) ───────────────────────────────────────
    # Zona de "resguardo" entre el borde de la envolvente y el área útil
    # donde se colocan conductos. Se dibuja como línea gris punteada dentro
    # de la envolvente, similar al margen de página en un procesador de
    # texto. Cuatro valores independientes: top / right / bottom / left.
    margin_top: float = 0.0
    margin_right: float = 0.0
    margin_bottom: float = 0.0
    margin_left: float = 0.0

    # ── Redondeo de esquinas (pulgadas) ──────────────────────────────────
    # Radio de la esquina, por esquina. 0 = escuadra viva.
    #   tl = superior izquierda, tr = superior derecha,
    #   br = inferior derecha,  bl = inferior izquierda.
    corner_tl: float = 0.0
    corner_tr: float = 0.0
    corner_br: float = 0.0
    corner_bl: float = 0.0

    # ── Guía interior (rejilla estilo Photoshop) ─────────────────────────
    # Divide el AREA INTERIOR (dentro del margen) en `guide_rows × guide_cols`
    # celdas iguales. Se dibuja como líneas finas y muestra la dimensión de
    # cada celda en pulgadas. Es una AYUDA VISUAL: no obliga a nada, no
    # snapea, solo se ve. Se activa/desactiva con `guide_show`.
    guide_show: bool = False
    guide_rows: int = 1
    guide_cols: int = 1

    # ── Asignación a pipe (alineamiento) ─────────────────────────────────
    # Índice de la pipe en win.pipes a la que se extruye este duct bank.
    # -1 = no asignado.
    pipe_idx: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name,
                "width_in": float(self.width_in),
                "height_in": float(self.height_in),
                "margin_top": float(self.margin_top),
                "margin_right": float(self.margin_right),
                "margin_bottom": float(self.margin_bottom),
                "margin_left": float(self.margin_left),
                "corner_tl": float(self.corner_tl),
                "corner_tr": float(self.corner_tr),
                "corner_br": float(self.corner_br),
                "corner_bl": float(self.corner_bl),
                "guide_show": bool(self.guide_show),
                "guide_rows": int(self.guide_rows),
                "guide_cols": int(self.guide_cols),
                "pipe_idx": int(self.pipe_idx),
                "conduits": [c.to_dict() for c in self.conduits]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DuctBank":
        return cls(name=str(d.get("name", "")),
                   width_in=float(d.get("width_in", 12.0)),
                   height_in=float(d.get("height_in", 8.0)),
                   margin_top=float(d.get("margin_top", 0.0)),
                   margin_right=float(d.get("margin_right", 0.0)),
                   margin_bottom=float(d.get("margin_bottom", 0.0)),
                   margin_left=float(d.get("margin_left", 0.0)),
                   corner_tl=float(d.get("corner_tl", 0.0)),
                   corner_tr=float(d.get("corner_tr", 0.0)),
                   corner_br=float(d.get("corner_br", 0.0)),
                   corner_bl=float(d.get("corner_bl", 0.0)),
                   guide_show=bool(d.get("guide_show", False)),
                   guide_rows=int(d.get("guide_rows", 1)),
                   guide_cols=int(d.get("guide_cols", 1)),
                   pipe_idx=int(d.get("pipe_idx", -1)),
                   conduits=[Conduit.from_dict(cc) for cc in d.get("conduits", [])])

    # ── Helpers derivados ────────────────────────────────────────────────
    def inner_rect(self):
        """Devuelve el rectángulo interior (envolvente menos márgenes), como
        tupla (x, y, w, h) en pulgadas relativas a la esquina superior-izq de la
        envolvente. Si algún margen es demasiado grande, ancho/alto van a 0."""
        x = self.margin_left
        y = self.margin_top
        w = max(0.0, self.width_in - self.margin_left - self.margin_right)
        h = max(0.0, self.height_in - self.margin_top - self.margin_bottom)
        return (x, y, w, h)

    def has_margin(self) -> bool:
        return any(m > 0 for m in (self.margin_top, self.margin_right,
                                    self.margin_bottom, self.margin_left))

    def has_rounded_corners(self) -> bool:
        return any(r > 0 for r in (self.corner_tl, self.corner_tr,
                                    self.corner_br, self.corner_bl))

    def guide_cell_size(self):
        """Devuelve (cell_w, cell_h) en pulgadas para las celdas de la guía
        interior. Reparte el interior en `guide_cols × guide_rows` celdas iguales.
        Si el interior colapsa (margen demasiado grande), devuelve (0, 0)."""
        _, _, iw, ih = self.inner_rect()
        cols = max(1, int(self.guide_cols))
        rows = max(1, int(self.guide_rows))
        return (iw / cols if iw > 0 else 0.0,
                ih / rows if ih > 0 else 0.0)

    def copy(self) -> "DuctBank":
        return DuctBank.from_dict(self.to_dict())


def snap(v: float, step: float = DEFAULT_SNAP_IN) -> float:
    """Ajusta v al múltiplo más cercano de step. step<=0 → sin ajuste."""
    if step <= 0:
        return float(v)
    return round(v / step) * step


def conduit_fits_envelope(db: DuctBank, c: Conduit, margin: float = 0.0) -> bool:
    """True si el conducto (círculo completo, más margen opcional) cabe dentro
    de la envolvente. margin en pulgadas — útil para exigir separación al borde."""
    r = c.diam / 2.0 + margin
    return (r <= c.cx <= db.width_in - r) and (r <= c.cy <= db.height_in - r)


def conduits_overlap(a: Conduit, b: Conduit, tol: float = 0.0) -> bool:
    """True si dos conductos se solapan (distancia entre centros < suma de radios).
    tol positivo → exige separación adicional; tol negativo → tolera solape leve."""
    dx = a.cx - b.cx
    dy = a.cy - b.cy
    dist2 = dx * dx + dy * dy
    min_dist = a.diam / 2.0 + b.diam / 2.0 + tol
    return dist2 < min_dist * min_dist


def validate(db: DuctBank) -> List[str]:
    """Devuelve una lista de mensajes de advertencia (nunca lanza excepción).
    Un duct bank es "válido para exportar" cuando esta lista está vacía."""
    errs: List[str] = []
    if db.width_in <= 0 or db.height_in <= 0:
        errs.append("La envolvente debe tener ancho y alto positivos.")
    if len(db.conduits) > MAX_CONDUITS:
        errs.append(f"Demasiados conductos ({len(db.conduits)} > {MAX_CONDUITS}).")
    for i, c in enumerate(db.conduits, start=1):
        if c.diam <= 0:
            errs.append(f"Conducto {i}: diámetro debe ser > 0.")
            continue
        if not conduit_fits_envelope(db, c):
            errs.append(f"Conducto {i}: sale de la envolvente.")
    # Solapes (marcado suave: informa pero no bloquea, algunos diseños tocan)
    for i in range(len(db.conduits)):
        for j in range(i + 1, len(db.conduits)):
            if conduits_overlap(db.conduits[i], db.conduits[j], tol=-1e-6):
                errs.append(f"Conductos {i + 1} y {j + 1} se solapan.")
    return errs
