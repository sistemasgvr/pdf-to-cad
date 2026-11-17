"""Propiedades de una superficie (pedido del usuario 2026-11-14: «al seleccionar la superficie en el lienzo o en el
inventario, en sus propiedades tiene que salir lo que tenga… al menos la ruta del archivo original, y otras
propiedades clásicas que también se ven en Civil 3D»).

- Inventario → «Superficies»: la fila elegida muestra sus propiedades en el panel derecho (`gprop_sup`).
- Lienzo: clic en el CONTORNO de la superficie o en su pastilla con el nombre la elige (Inventario → Superficies, sin
  mover el plano). Un clic dentro de la superficie no la elige: cubre todo el plano y no dejaría soltar lo elegido.
- Todo es de solo lectura: lo que dice el archivo (ruta original, formato, sistema, unidades) y las estadísticas del
  TIN (`nucleo.superficie_estadisticas`, las de Civil 3D) con el estado de su revisión (`_sup_revisar`).
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import superficie_estadisticas as E
from nucleo import superficies as S
from nucleo import superficies_leer as L
from nucleo.model import TAB_SUP
from traduccion.i18n import bind as _bind
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_
from ui.comun.responsive import ResponsiveGroupBox, WrapButton

CLIC_PX = 8.0                          # cuánto se busca el contorno alrededor del clic (px de pantalla)
MARCA_ESTADO = {"ok": "✔", "aviso": "⚠", "error": "✖"}     # como en Inventario → Superficies
_UNIDADES = {"meter": N_("metros"), "foot": N_("pies"), "USSurveyFoot": N_("pies US")}


def _miles(v, dec=0):
    return f"{v:,.{dec}f}".replace(",", " ")


class PropSuperficieMixin:
    # ── panel ────────────────────────────────────────────────────────────
    def _build_prop_superficie(self, rv):
        g = self.gprop_sup = ResponsiveGroupBox()
        g.setFlat(True)
        g.setStyleSheet("QGroupBox { margin-top: 0; padding-top: 0; border: none; }")
        f = QtWidgets.QFormLayout(g)
        f.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        f.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        f.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self._sup_campos = {}

        def titulo(texto):
            lbl = _bind(QtWidgets.QLabel(), "setText", texto)
            lbl.setProperty("rol", "sec")
            f.addRow(lbl)

        def fila(clave, texto):
            from ui.comun.texto_ajustado import TextoAjustado
            w = TextoAjustado("—")
            w.setWordWrap(True)
            w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            f.addRow(_bind(QtWidgets.QLabel(), "setText", texto), w)
            self._sup_campos[clave] = w
        titulo(N_("Información"))
        fila("nombre", N_("Nombre:"))
        fila("estado", N_("Estado:"))
        fila("ruta", N_("Archivo original:"))
        self.btn_sup_carpeta = _bind(WrapButton(), "setText", "Abrir la carpeta del archivo")
        self.btn_sup_carpeta.setProperty("kind", "ghost")
        self.btn_sup_carpeta.clicked.connect(self._sup_abrir_carpeta)
        f.addRow(self.btn_sup_carpeta)
        fila("formato", N_("Formato:"))
        fila("sistema", N_("Sistema de coordenadas:"))
        fila("unidades", N_("Unidades:"))
        fila("visible", N_("En el plano:"))
        titulo(N_("Estadísticas"))
        fila("puntos", N_("Puntos:"))
        fila("triangulos", N_("Triángulos:"))
        fila("cota_min", N_("Cota mínima:"))
        fila("cota_max", N_("Cota máxima:"))
        fila("cota_media", N_("Cota media:"))
        fila("area_2d", N_("Área 2D:"))
        fila("area_3d", N_("Área 3D:"))
        fila("pend_media", N_("Pendiente media:"))
        fila("pend_max", N_("Pendiente máxima:"))
        fila("lado", N_("Lado de triángulo (mín – máx):"))
        fila("area_tri", N_("Área de triángulo (mín – máx):"))
        fila("ext_x", N_("Extensión X:"))
        fila("ext_y", N_("Extensión Y:"))
        g.setVisible(False)
        rv.addWidget(g)
        return g

    def _sup_elegida(self):
        """Índice de la superficie elegida en Inventario → Superficies (con esa sección a la vista), o −1."""
        lista = getattr(self, "sup_list", None)
        if lista is None or self._current_tab() != TAB_SUP:
            return -1
        k = lista.currentRow()
        return k if 0 <= k < len(getattr(self, "superficies", ()) or ()) else -1

    def _sup_estadisticas(self, reg):
        """Estadísticas del TIN (memorizadas por superficie y sistema del dibujo) o None si no se puede leer."""
        crs, uxy, uz = self._sup_destino()
        clave = (reg.get("sha1"), reg.get("archivo"), reg.get("indice", 0), reg.get("crs", ""), crs, uxy, uz)
        cache = self.__dict__.setdefault("_sup_stats", {})
        if clave not in cache:
            try:
                pts, tri, inv, _u = self._sup_geometria(reg)
            except (L.ErrorSuperficie, S.ErrorSistema, IndexError):
                return None
            cache[clave] = E.estadisticas(pts, tri, inv, uxy or reg.get("unidad") or "foot")
        return cache[clave]

    def _sync_prop_superficie(self):
        g = getattr(self, "gprop_sup", None)
        if g is None:
            return
        k = self._sup_elegida()
        g.setVisible(k >= 0)
        if k < 0:
            return
        reg = self.superficies[k]
        c = self._sup_campos
        c["nombre"].setText(reg.get("nombre", ""))
        rev = getattr(self, "_sup_revision", None) or []
        nivel, resumen, det = rev[k] if k < len(rev) else self._sup_revisar(reg)
        c["estado"].setText(_tr("{m} {r}").format(m=MARCA_ESTADO.get(nivel, MARCA_ESTADO["aviso"]), r=resumen))
        c["estado"].setToolTip("\n".join(det))
        ruta = reg.get("ruta") or ""
        if ruta:
            c["ruta"].setText(ruta)
            c["ruta"].setToolTip(ruta if os.path.isfile(ruta) else
                                 _tr("Ya no está en esa carpeta. El proyecto guarda su propia copia del archivo."))
        else:
            c["ruta"].setText(_tr("{a} (importada antes de 2.1.0: no se guardó la carpeta)").format(
                a=reg.get("archivo", "")))
            c["ruta"].setToolTip("")
        self.btn_sup_carpeta.setVisible(bool(ruta) and os.path.isdir(os.path.dirname(ruta)))
        c["formato"].setText(reg.get("formato", "") or "—")
        crs, uxy, _uz = self._sup_destino()
        origen = reg.get("crs") or ""
        if crs and origen and origen != crs:
            sistema = _tr("{o} → {d} (el del dibujo)").format(o=origen, d=crs)
        else:
            sistema = origen or crs or _tr("El del archivo (el plano no está georreferenciado)")
        c["sistema"].setText(sistema)
        u_arch = _tr(_UNIDADES.get(reg.get("unidad", ""), reg.get("unidad", "") or "—"))
        u_dib = _tr(_UNIDADES.get(uxy, uxy)) if uxy else u_arch
        c["unidades"].setText(_tr("Archivo: {a} · Dibujo: X/Y en {x}, cotas en pies").format(a=u_arch, x=u_dib))
        c["visible"].setText(_tr("Encendida") if reg.get("visible", True) else _tr("Apagada en «Capas ▾»"))
        st = self._sup_estadisticas(reg) or {}
        ft = _tr("{v} ft")
        ft2 = _tr("{v} ft² ({ac} acres)")

        def poner(clave, texto):
            c[clave].setText(texto)
        poner("puntos", _miles(st.get("n_puntos", reg.get("n_puntos", 0))))
        poner("triangulos", _miles(st.get("n_triangulos", reg.get("n_triangulos", 0))))
        for clave, k_st in (("cota_min", "z_min"), ("cota_max", "z_max"), ("cota_media", "z_media")):
            poner(clave, ft.format(v=_miles(st[k_st], 2)) if k_st in st else "—")
        for clave, k_st in (("area_2d", "area_2d_ft2"), ("area_3d", "area_3d_ft2")):
            poner(clave, ft2.format(v=_miles(st[k_st], 1), ac=f"{st[k_st] / E.PIES2_POR_ACRE:.3f}")
                  if k_st in st else "—")
        for clave, k_st in (("pend_media", "pendiente_media_pct"), ("pend_max", "pendiente_max_pct")):
            poner(clave, f"{st[k_st]:.2f} %" if k_st in st else "—")
        poner("lado", _tr("{a} – {b} ft").format(a=_miles(st["lado_min_ft"], 2), b=_miles(st["lado_max_ft"], 2))
              if "lado_min_ft" in st else "—")
        poner("area_tri", _tr("{a} – {b} ft²").format(a=_miles(st["area_tri_min_ft2"], 2),
                                                     b=_miles(st["area_tri_max_ft2"], 1))
              if "area_tri_min_ft2" in st else "—")
        u = u_dib
        for clave, a, b in (("ext_x", "x_min", "x_max"), ("ext_y", "y_min", "y_max")):
            poner(clave, _tr("{a} a {b} {u}").format(a=_miles(st[a], 3), b=_miles(st[b], 3), u=u) if a in st else "—")

    def _sup_abrir_carpeta(self):
        k = self._sup_elegida()
        if k < 0:
            return
        ruta = self.superficies[k].get("ruta") or ""
        carpeta = os.path.dirname(ruta)
        if carpeta and os.path.isdir(carpeta):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(carpeta))

    # ── elegir en el lienzo ──────────────────────────────────────────────
    def _superficie_bajo_clic(self, x, y):
        """Índice de la superficie cuyo contorno (o pastilla con el nombre) está bajo el clic, o None."""
        items = getattr(self, "_sup_items", None) or []
        if not items:
            return None
        escala = max(self.canvas.transform().m11(), 1e-6)
        punto = QtCore.QPointF(x, y)
        vista = self.canvas.mapFromScene(punto)
        for it in self.canvas.items(vista):                    # la pastilla (ignora el zoom)
            dato = it.data(1)
            if isinstance(dato, tuple) and dato[:1] == ("superficie",) and not isinstance(
                    it, QtWidgets.QGraphicsPathItem):
                return int(dato[1])
        trazo = QtGui.QPainterPathStroker()
        trazo.setWidth(2.0 * CLIC_PX / escala)
        for it in items:
            dato = it.data(1)
            if isinstance(it, QtWidgets.QGraphicsPathItem) and isinstance(dato, tuple) and dato[:1] == ("superficie",):
                if trazo.createStroke(it.path()).contains(punto):
                    return int(dato[1])
        return None

    def _elegir_superficie(self, k):
        """Inventario → Superficies con la `k` elegida, sin mover el plano."""
        if hasattr(self, "_abrir_inventario"):
            self._abrir_inventario()
        self._show_tab(TAB_SUP)
        self._sup_sin_mover = True
        try:
            self.sup_list.setCurrentRow(k)
        finally:
            self._sup_sin_mover = False
        self._sync_prop_superficie()
        if getattr(self, "cabecera_inspector", None) is not None:
            self.cabecera_inspector.refrescar()
