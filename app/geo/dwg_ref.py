"""
dwg_ref.py — DWG/DXF de referencia (ya en coordenadas reales del proyecto) para
georreferenciar el escaneo por comparación (Nivel 3).

- DXF: se lee directo con ezdxf.
- DWG: Python no lo lee nativo; se intenta convertir con ODA File Converter
  (ezdxf.addons.odafc, requiere instalar ODA gratis). Si no está, se avisa y se
  sugiere exportar a DXF.

Las coordenadas del dibujo se toman TAL CUAL (se asume que ya están en el CRS del
proyecto, p. ej. EPSG:2229 pies). Al hacer clic en el visor se obtiene esa
coordenada real directamente, sin satélite ni geocoder → grado topográfico.
"""
import math

from PySide6 import QtCore, QtGui, QtWidgets

# nº de segmentos para aproximar arcos/círculos
_ARC_SEG = 24


def _flatten_entity(e, segs, depth=0):
    """Reduce una entidad a una o más polilíneas [(x,y), …] en coordenadas de
    mundo y las agrega a `segs`. Soporta LINE/POLYLINE/ARC/CIRCLE e INSERT."""
    try:
        t = e.dxftype()
        if t == "LINE":
            segs.append([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
        elif t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if len(pts) >= 2:
                if getattr(e, "closed", False) or e.dxf.get("flags", 0) & 1:
                    pts.append(pts[0])
                segs.append(pts)
        elif t == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if len(pts) >= 2:
                segs.append(pts)
        elif t in ("ARC", "CIRCLE"):
            cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
            if t == "ARC":
                a0 = math.radians(e.dxf.start_angle); a1 = math.radians(e.dxf.end_angle)
                if a1 <= a0:
                    a1 += 2 * math.pi
            else:
                a0, a1 = 0.0, 2 * math.pi
            segs.append([(cx + r * math.cos(a0 + (a1 - a0) * i / _ARC_SEG),
                          cy + r * math.sin(a0 + (a1 - a0) * i / _ARC_SEG))
                         for i in range(_ARC_SEG + 1)])
        elif t == "INSERT" and depth < 5:                 # bloque: explota a mundo
            for ve in e.virtual_entities():
                _flatten_entity(ve, segs, depth + 1)
    except Exception:
        pass                                              # entidad rara: se ignora


def load_reference(path):
    """Devuelve (segs, bounds) del dibujo. segs = lista de polilíneas en mundo;
    bounds = (minx, miny, maxx, maxy). Lanza RuntimeError con un mensaje claro
    si no se puede leer (p. ej. .dwg sin ODA) o no hay geometría."""
    import ezdxf
    low = path.lower()
    if low.endswith(".dwg"):
        try:
            from ezdxf.addons import odafc
            doc = odafc.readfile(path)
        except Exception as e:
            raise RuntimeError(
                "Para cargar un .dwg necesitas ODA File Converter instalado (gratuito).\n"
                "Alternativa recomendada: exporta el plano a .dxf desde el CAD y cárgalo aquí.\n\n"
                f"Detalle: {e}")
    else:
        try:
            doc = ezdxf.readfile(path)
        except Exception as e:
            raise RuntimeError(f"No se pudo leer el DXF.\n\n{e}")
    segs = []
    for ent in doc.modelspace():
        _flatten_entity(ent, segs)
    if not segs:
        raise RuntimeError("El dibujo no tiene geometría de líneas/polilíneas/arcos reconocible.")
    xs = [p[0] for s in segs for p in s]; ys = [p[1] for s in segs for p in s]
    return segs, (min(xs), min(ys), max(xs), max(ys))


class DxfRefView(QtWidgets.QGraphicsView):
    """Visor del DWG/DXF de referencia. Clic izquierdo = punto en coordenadas
    REALES del dibujo (emite worldClicked(x, y)). Rueda = zoom."""
    worldClicked = QtCore.Signal(float, float)

    def __init__(self, segs, bounds):
        super().__init__()
        sc = QtWidgets.QGraphicsScene(self); self.setScene(sc)
        self.setRenderHints(QtGui.QPainter.Antialiasing)
        self.setBackgroundBrush(QtGui.QColor(20, 24, 33))
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)   # arrastrar = paneo
        pen = QtGui.QPen(QtGui.QColor("#7fd0ff")); pen.setCosmetic(True)
        # Se dibuja con Y invertida (en pantalla Y crece hacia abajo).
        for s in segs:
            path = QtGui.QPainterPath(); path.moveTo(s[0][0], -s[0][1])
            for (x, y) in s[1:]:
                path.lineTo(x, -y)
            sc.addPath(path, pen)
        minx, miny, maxx, maxy = bounds
        self.setSceneRect(minx, -maxy, maxx - minx, maxy - miny)
        self._mark = None
        QtCore.QTimer.singleShot(0, lambda: self.fitInView(sc.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio))

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint())
            wx, wy = sp.x(), -sp.y()                     # deshace la inversión de Y → mundo real
            if self._mark:
                self.scene().removeItem(self._mark)
            m = QtWidgets.QGraphicsEllipseItem(-5, -5, 10, 10)
            m.setBrush(QtGui.QBrush(QtGui.QColor("#ffd21e")))
            m.setPen(QtGui.QPen(QtGui.QColor("#ffd21e")))
            m.setPos(sp.x(), sp.y())
            m.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)   # tamaño fijo en pantalla
            self.scene().addItem(m); self._mark = m
            self.worldClicked.emit(wx, wy)
        else:
            super().mousePressEvent(e)
