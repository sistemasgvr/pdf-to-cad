"""georef_sistema.py — el diálogo «Georreferenciar…» en CUALQUIER sistema de coordenadas (2026-11-18).

Antes el diálogo estaba atado a EPSG 2229 (Los Ángeles, calles y parcelas de NavigateLA). Ahora trabaja en el
sistema del proyecto (`self.epsg`): el de la georreferencia que ya tiene (p. ej. la automática de los mapas de
Phoenix, EPSG 2868) o el que escribe el usuario. En 2229 todo sigue igual; en otro sistema no hay calles de
referencia: la dirección se busca con el geocodificador genérico y se reproyecta, el mapa de fondo (teselas) se
dibuja en ese sistema, el clic en el mapa no tiene imán y se guarda con ese EPSG.

Funciones PURAS arriba; la mezcla `SistemaGeorefMixin` (Qt) la usa `GeorefDialog`.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

LA_EPSG = 2229          # el único sistema con calles y parcelas de referencia (NavigateLA)
MARGEN_FT = 400.0       # alrededor de los pares al abrir sin calles de referencia


def sistema_de(georef) -> int:
    """El sistema con el que abre el diálogo: el de la georreferencia que ya tiene el proyecto, si no 2229."""
    try:
        if georef is not None and georef.active() and georef.epsg:
            return int(georef.epsg)
    except Exception:  # noqa: BLE001
        pass
    return LA_EPSG


def mundo_de(punto: dict) -> Optional[Tuple[float, float]]:
    """Coordenadas del mundo de un par guardado: «world» (diálogo) o «utm» (versiones anteriores de la
    georreferencia automática)."""
    w = punto.get("world") or punto.get("utm")
    if w and len(w) == 2:
        return float(w[0]), float(w[1])
    return None


def con_calles(epsg: int) -> bool:
    return int(epsg) == LA_EPSG


def nombre(epsg) -> Optional[str]:
    """Nombre del sistema (pyproj) o None si el código no existe o no es proyectado."""
    try:
        from pyproj import CRS
        crs = CRS.from_epsg(int(epsg))
        return crs.name if crs.is_projected else None
    except Exception:  # noqa: BLE001
        return None


def cs_sugerido(epsg: int) -> str:
    """Código de Civil 3D del sistema (`sistemas_cs.codigo_civil3d`), o "" si no se conoce."""
    try:
        from nucleo import sistemas_cs
        return sistemas_cs.codigo_civil3d(int(epsg)) or ""
    except Exception:  # noqa: BLE001
        return ""


def extension(puntos: Sequence[Tuple[float, float]], margen: float = MARGEN_FT):
    """(x0, y0, x1, y1) que contiene los puntos con margen, o None sin puntos."""
    if not puntos:
        return None
    xs = [p[0] for p in puntos]; ys = [p[1] for p in puntos]
    return min(xs) - margen, min(ys) - margen, max(xs) + margen, max(ys) + margen


def zona_de_direccion(query: str, epsg: int, radio: float):
    """Fuera de 2229: (centro, extensión, etiqueta) de una dirección con el geocodificador genérico, reproyectada
    al sistema. Lanza RuntimeError si no se encuentra (red)."""
    from geo import georef
    from geo.georef_dialog import geocode
    lat, lon, etiqueta = geocode(query)
    x, y = georef.lonlat_to_utm(lon, lat, epsg)
    return (x, y), (x - radio, y - radio, x + radio, y + radio), etiqueta


# ───────────────────────── mezcla del diálogo (Qt) ─────────────────────────

class SistemaGeorefMixin:
    """Campo «Sistema (EPSG)» y el modo del diálogo según el sistema."""

    def _armar_sistema(self, init_georef):
        from PySide6 import QtGui, QtWidgets

        from traduccion.i18n import t
        self.epsg = sistema_de(init_georef)
        self._extension = None              # mapa sin calles de referencia: lo que se ve
        self.ed_epsg = QtWidgets.QLineEdit(str(self.epsg))
        self.ed_epsg.setValidator(QtGui.QIntValidator(1000, 999999, self.ed_epsg))
        self.ed_epsg.setFixedWidth(72)
        self.ed_epsg.setToolTip(t("Sistema de coordenadas (código EPSG) en el que se georreferencia. "
                                  "2229 = Los Ángeles, con calles y parcelas de referencia. "
                                  "Otro sistema: mapa de fondo y búsqueda de dirección, sin imán a las calles."))
        self.ed_epsg.editingFinished.connect(self._cambiar_sistema)
        return [QtWidgets.QLabel(t("EPSG")), self.ed_epsg]

    def _aplicar_modo_sistema(self):
        from traduccion.i18n import t
        la = con_calles(self.epsg)
        self.sp_buffer.setEnabled(True)
        self.ed_addr.setPlaceholderText(t("Dirección o intersección… ej: Colfax Ave & Chandler Blvd") if la
                                        else t("Dirección o intersección… ej: 67th Ave & Indian School Rd, Phoenix"))
        self.b_fetch.setToolTip(t("Buscar y descargar") if la else t("Buscar la dirección y mostrar el mapa de fondo"))
        if not la:
            self.hint.setText(t("Sistema EPSG {epsg} ({nombre}): sin calles de referencia. Clic en el plano y luego "
                                "en el mismo punto del mapa de fondo (sin imán). Mínimo 3 pares.")
                              .format(epsg=self.epsg, nombre=nombre(self.epsg) or ""))

    def _cambiar_sistema(self):
        from PySide6 import QtWidgets

        from traduccion.i18n import t
        txt = self.ed_epsg.text().strip()
        if not txt or int(txt) == self.epsg:
            self.ed_epsg.setText(str(self.epsg)); return
        nuevo = int(txt)
        if nombre(nuevo) is None:
            QtWidgets.QMessageBox.warning(self, t("Sistema de coordenadas"),
                t("EPSG {epsg} no es un sistema proyectado conocido.").format(epsg=nuevo))
            self.ed_epsg.setText(str(self.epsg)); return
        if self.pairs:
            QtWidgets.QMessageBox.information(self, t("Sistema de coordenadas"),
                t("Los pares están en EPSG {epsg}. Quítalos («Limpiar todos») antes de cambiar de sistema.")
                .format(epsg=self.epsg))
            self.ed_epsg.setText(str(self.epsg)); return
        cs_viejo = cs_sugerido(self.epsg)
        self.epsg = nuevo
        if not self.ed_cs_code.text().strip() or self.ed_cs_code.text().strip() == cs_viejo:
            self.ed_cs_code.setText(cs_sugerido(nuevo))
        self.centerlines, self.parcels, self.arc_centers = [], [], []
        self._extension = None; self._zona_txt = ""
        self._fit_result = None; self.b_save.setEnabled(False)
        self._dialog_dirty = True
        self._aplicar_modo_sistema()
        self._draw_map_base(); self._actualizar_pasos()

    def _abrir_sin_calles(self, mundos):
        """Al abrir fuera de 2229 con pares: el mapa de fondo alrededor de ellos (nada que descargar)."""
        self._extension = extension(mundos)
        self._draw_map_base()
        self._actualizar_pasos()
