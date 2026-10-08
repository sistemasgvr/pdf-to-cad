"""Coordenadas del lienzo → CAD, georreferencia del DXF y vista en planta.

Métodos de la ventana principal `Main` (app_window.py), movidos TAL CUAL a esta
clase mezcla para que app_window.py no pase de unas 2 000 líneas. `Main` la hereda:
los menús, atajos y pruebas siguen usando `win.<método>` como antes.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)


class CoordsMixin:
    # ─────────────────────────── coords ───────────────────────────
    def _to_cad(self, x, y):
        # Compuerta única: si hay georreferencia activa, píxel→UTM real; si no, escala del titleblock.
        if self.georef.active():
            return self.georef.to_world(x, y)
        return G.to_cad(x, y, self.scale, self.rot, self.W, self.H, self.derot, self.zoom)

    def _georef_base_doc(self, doc):
        """Con georreferencia activa, transforma TODO el plano base al mismo sistema
        REAL que las anotaciones. El plano base viene en coordenadas de titleblock
        (G.to_cad sin georref); ajustamos una afín base→real muestreando 3 puntos
        (base = G.to_cad(px), real = georef.to_world(px)) y la aplicamos a todas
        las entidades del modelspace. Así base + anotaciones quedan alineados."""
        from ezdxf.math import Matrix44
        pm = self.canvas.pixmap_item.pixmap()
        w, h = pm.width(), pm.height()
        samples = [(0.1 * w, 0.1 * h), (0.9 * w, 0.15 * h), (0.15 * w, 0.9 * h)]
        src = [G.to_cad(x, y, self.scale, self.rot, self.W, self.H, self.derot, self.zoom) for (x, y) in samples]
        dst = [self.georef.to_world(x, y) for (x, y) in samples]
        M, _, _ = georef_mod.fit(src, dst, "affine")
        a, b, c = M[0]; d, e, f = M[1]
        mat = Matrix44((a, d, 0, 0), (b, e, 0, 0), (0, 0, 1, 0), (c, f, 0, 1))
        msp = doc.modelspace()
        for ent in list(msp):
            try:
                ent.transform(mat)
            except Exception:
                pass                                     # entidad que no soporta transform: se deja

    def _set_geodata(self, doc):
        """Incrusta el sistema de coordenadas (EPSG del georef) como GeoData, para
        que el CAD reconozca el plano geolocalizado.
        Best-effort: si algo falla, no rompe la exportación."""
        if not self.georef.active():
            return
        try:
            epsg = int(self.georef.epsg)
            gd = doc.modelspace().new_geodata()
            gd.coordinate_system_definition = f"EPSG:{epsg}"
        except Exception:
            pass

    def _set_plan_view(self, doc):
        """Hace que el DXF se abra en vista de PLANTA (top) y encuadrado al dibujo,
        para que no aparezca como una hoja inclinada ni diminuta al abrirlo."""
        try:
            from ezdxf import bbox
            ext = bbox.extents(doc.modelspace())
            if not ext.has_data:
                return
            cx = (ext.extmin.x + ext.extmax.x) / 2.0
            cy = (ext.extmin.y + ext.extmax.y) / 2.0
            h = (ext.extmax.y - ext.extmin.y) or (ext.extmax.x - ext.extmin.x) or 100.0
            doc.set_modelspace_vport(h * 1.15, center=(cx, cy))   # vista top, centrada
        except Exception:
            pass

    def _maybe_export_dwg(self, doc, out):
        """Si el usuario lo activó, genera también un .dwg junto al .dxf usando el
        ODA File Converter (ezdxf.addons.odafc). Si ODA no está, avisa y deja el DXF."""
        if not (getattr(self, "act_dwg", None) and self.act_dwg.isChecked()):
            return
        dwg = os.path.splitext(out)[0] + ".dwg"
        try:
            from ezdxf.addons import odafc
            if not odafc.is_installed():
                QtWidgets.QMessageBox.information(self, "DWG",
                    _tr("Para generar DWG necesitas instalar el ODA File Converter (gratuito).\n"
                    "Se guardó solo el DXF; ábrelo en tu CAD y «Guardar como DWG» si lo necesitas ahora."))
                return
            odafc.export_dwg(doc, dwg, replace=True)
            self._info(_tr("DWG generado: {archivo}").format(archivo=os.path.basename(dwg)))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "DWG", _tr("No se pudo generar el DWG (se conserva el DXF).\n\n{e}").format(e=e))

    def _plan_bbox_real(self):
        """Recuadro del plano en coordenadas reales (del georef), desde las esquinas
        de la página. Devuelve (xmin, ymin, xmax, ymax)."""
        pm = self.canvas.pixmap_item.pixmap()
        w, h = pm.width(), pm.height()
        cs = [self.georef.to_world(x, y) for (x, y) in ((0, 0), (w, 0), (w, h), (0, h))]
        xs = [c[0] for c in cs]; ys = [c[1] for c in cs]
        return (min(xs), min(ys), max(xs), max(ys))

    def _maybe_add_la_reference(self, doc):
        """Si el usuario lo activó y el plano está georreferenciado a EPSG:2229,
        descarga de NavigateLA las calles (y opcional parcelas) del área y las
        añade como capas de referencia. Falla en silencio con aviso."""
        want_streets = getattr(self, "act_la_ref", None) and self.act_la_ref.isChecked()
        want_parcels = getattr(self, "act_la_parcels", None) and self.act_la_parcels.isChecked()
        if not (want_streets or want_parcels):
            return
        if not self.georef.active() or int(self.georef.epsg) != 2229:
            QtWidgets.QMessageBox.information(self, _tr("Capas de LA"),
                _tr("Las capas reales de LA solo se pueden agregar si el plano está "
                "georreferenciado a EPSG:2229 (State Plane de LA).")); return
        try:
            from geo.la_reference import add_reference_layers
            nc, npa = add_reference_layers(doc, self._plan_bbox_real(),
                                           streets=bool(want_streets), parcels=bool(want_parcels))
            self._info(_tr("Capas de LA agregadas: {calles} tramos de calle, {parcelas} parcelas.").format(calles=nc, parcelas=npa))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, _tr("Capas de LA"),
                _tr("No se pudieron descargar las capas de LA (¿internet?).\n\n{e}").format(e=e))
