"""recognition_preview_draw.py — lo que la vista previa del reconocimiento pinta sobre la hoja.

Movido de recognition_dialog (mismas funciones y nombres). Cada función devuelve los
ítems que agregó a la escena: así la vista previa puede RESALTAR lo de una capa
(halo del color de la utilidad) y atenuar lo demás cuando el usuario hace clic en
«Capas usadas» (pedido del usuario 2026-10-03).
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from ui.comun.ui_common import QA_UNCOVERED

DIM_OPACITY = 0.15        # lo que no es de la capa elegida en «Capas usadas»
HALO_PX = 11              # ancho (en pantalla) del halo de lo resaltado
HALO_ALPHA = 110


def _draw_poly(scene, pts, color, width=2.0, dots=False, z=5, dashed=False, dotted=False):
    """Misma convención visual que Main._poly para pipes finalizados."""
    pen = QtGui.QPen(color, width)
    pen.setCosmetic(True)
    if dashed:
        pen.setDashPattern([6.0, 4.0])
    if dotted:                              # trazos fuera de patrón: a puntos (forma, no solo color)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setDashPattern([0.1, 2.2])
    items = []
    for a, b in zip(pts, pts[1:]):
        it = scene.addLine(a[0], a[1], b[0], b[1], pen)
        it.setZValue(z)
        items.append(it)
    if dots:
        for (x, y) in pts:
            it = scene.addEllipse(
                x - 3, y - 3, 6, 6, pen, QtGui.QBrush(color))
            it.setZValue(z)
            items.append(it)
    return items


def _display_runs(pl):
    """Tramos rectos para DIBUJAR: en un codo la recta llega hasta A (tangencia)
    y se reanuda en B; el arco entre A y B se pinta aparte (`_draw_fillet`)."""
    fillets = getattr(pl, "fillets", None) or {}
    if not fillets:
        return [pl.pts_pdf]
    runs, cur = [], []
    for i, p in enumerate(pl.pts_pdf):
        f = fillets.get(i)
        if f:
            cur.append(f["a"]); runs.append(cur); cur = [f["b"]]
        else:
            cur.append(p)
    runs.append(cur)
    return [r for r in runs if len(r) >= 2]


def _fillet_path(f: dict) -> QtGui.QPainterPath:
    """Arco del codo entre A y B (el camino corto sobre su círculo)."""
    cx, cy = f["center"]; r = f["r_px"]
    a0 = math.degrees(math.atan2(-(f["a"][1] - cy), f["a"][0] - cx))
    a1 = math.degrees(math.atan2(-(f["b"][1] - cy), f["b"][0] - cx))
    span = (a1 - a0 + 540.0) % 360.0 - 180.0          # el camino corto
    path = QtGui.QPainterPath()
    path.arcMoveTo(QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r), a0)
    path.arcTo(QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r), a0, span)
    return path


def _draw_fillet(scene, corner, f: dict, color, z=6):
    """Arco del codo (círculo ajustado al PDF) entre A y B, la esquina C punteada
    y el radio en la etiqueta."""
    pen = QtGui.QPen(color, 2.5); pen.setCosmetic(True)
    if f.get("loose"):
        # codo APROXIMADO: la curva del plano no es un arco tangente exacto (polilínea
        # «a mano»); el arco queda a ≤3 pt de ella. Se pinta a trazos para que se note.
        pen.setStyle(QtCore.Qt.DashLine)
    it = scene.addPath(_fillet_path(f), pen); it.setZValue(z)
    items = [it]
    dash = QtGui.QPen(color, 1); dash.setCosmetic(True); dash.setStyle(QtCore.Qt.DashLine)
    for q in (f["a"], f["b"]):
        ln = scene.addLine(q[0], q[1], corner[0], corner[1], dash); ln.setZValue(z)
        items.append(ln)
    # con ItemIgnoresTransformations el rectángulo se mide en píxeles de pantalla
    # desde la POSICIÓN del ítem: va centrado en (0,0) y el ítem en la esquina (antes,
    # en coordenadas de la hoja, el cuadrito salía corrido con cualquier zoom ≠ 1)
    m = scene.addRect(-4, -4, 8, 8, QtGui.QPen(QtGui.QColor("#ffffff"), 1.5), QtGui.QBrush(color))
    m.setPos(corner[0], corner[1])
    m.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations); m.setZValue(z + 2)
    items.append(m)
    return items


def _draw_vault_outline(scene, vg: dict, color, z=5):
    """Rectángulo (o círculo) del símbolo de bóveda tal como está en el PDF, con
    el MISMO color de la utilidad que usan las cajas en el editor (una sola
    regla de color en toda la app), y «ancho × largo ft» al lado. Solo informa:
    el vértice de la línea sigue siendo el punto de referencia."""
    color = QtGui.QColor(color)
    pen = QtGui.QPen(color, 2)
    pen.setCosmetic(True)
    fill = QtGui.QColor(color); fill.setAlpha(40)
    if vg.get("corners"):
        poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in vg["corners"]])
        it = scene.addPolygon(poly, pen, QtGui.QBrush(fill))
    elif vg.get("circle"):                 # buzón redondo: el anillo dibujado en el PDF
        cx, cy, r = vg["circle"]
        it = scene.addEllipse(cx - r, cy - r, 2 * r, 2 * r, pen, QtGui.QBrush(fill))
    else:
        cx, cy = vg["center"]
        r = max(4.0, 0.5 * vg.get("width_ft", 0.0) / max(1e-9, 1.0))   # radio aprox. en px lo pone el llamador
        it = scene.addEllipse(cx - r, cy - r, 2 * r, 2 * r, pen)
    it.setZValue(z)
    items = [it]
    if vg.get("width_ft") and vg.get("length_ft"):
        label = f"{vg['width_ft']:.1f} × {vg['length_ft']:.1f} ft" + (" (AB)" if vg.get("abandoned") else "")
        txt = scene.addSimpleText(label)
        txt.setBrush(QtGui.QBrush(color))
        txt.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        xs = [x for x, _ in vg["corners"]] if vg.get("corners") else [vg["center"][0]]
        ys = [y for _, y in vg["corners"]] if vg.get("corners") else [vg["center"][1]]
        txt.setPos(max(xs) + 3, min(ys))
        txt.setZValue(z + 1)
        items.append(txt)
    return items


def _draw_vault(scene, x, y, color, z=6, r=None):
    """Punto de bóveda ≈ caja del lienzo (elipse rellena)."""
    pen = QtGui.QPen(QtGui.QColor("#ffffff"), 1.5)
    pen.setCosmetic(True)
    brush = QtGui.QBrush(color)
    r = 6.0 if r is None else float(r)
    it = scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, brush)
    it.setZValue(z)
    return it


def _draw_orphan(scene, x, y, z=6, r=6.0):
    """Bóveda sin línea: ANILLO magenta (control de calidad), no el punto relleno
    del color de la utilidad (antes, un punto naranja: se confundía con telecom)."""
    pen = QtGui.QPen(QtGui.QColor(QA_UNCOVERED), 3)
    pen.setCosmetic(True)
    it = scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, QtGui.QBrush(QtCore.Qt.NoBrush))
    it.setZValue(z)
    return it


# ─────────── resaltado de una capa («Capas usadas», 2026-10-03) ───────────
def _halo_pen(color) -> QtGui.QPen:
    tint = QtGui.QColor(color); tint.setAlpha(HALO_ALPHA)
    pen = QtGui.QPen(tint, HALO_PX, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
    pen.setCosmetic(True)
    return pen


def draw_line_halo(scene, pl, color, z=4.5):
    """Halo ancho del color de la utilidad DEBAJO de una línea (tramos + arcos)."""
    pen = _halo_pen(color)
    items = []
    for run in _display_runs(pl):
        path = QtGui.QPainterPath(QtCore.QPointF(*run[0]))
        for p in run[1:]:
            path.lineTo(QtCore.QPointF(*p))
        items.append(scene.addPath(path, pen))
    for f in (getattr(pl, "fillets", None) or {}).values():
        items.append(scene.addPath(_fillet_path(f), pen))
    for it in items:
        it.setZValue(z)
    return items


def draw_vault_halo(scene, vg: dict, color, z=4.5):
    """Halo alrededor del contorno (o anillo) de una bóveda."""
    pen = _halo_pen(color)
    if vg.get("corners"):
        poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in vg["corners"]])
        it = scene.addPolygon(poly, pen)
    elif vg.get("circle"):
        cx, cy, r = vg["circle"]
        it = scene.addEllipse(cx - r, cy - r, 2 * r, 2 * r, pen)
    else:
        cx, cy = vg["center"]
        it = scene.addEllipse(cx - 6, cy - 6, 12, 12, pen)
    it.setZValue(z)
    return [it]


def vault_points(vg: dict):
    """Puntos que ocupa una bóveda (para encuadrarla)."""
    if vg.get("corners"):
        return list(vg["corners"])
    if vg.get("circle"):
        cx, cy, r = vg["circle"]
        return [(cx - r, cy - r), (cx + r, cy + r)]
    return [tuple(vg["center"])]
