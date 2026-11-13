"""Superficies (terreno) en la ventana (2026-11-11, versión 2.1.0): «Importar superficies…», verlas en el plano
(contorno + nombre), encenderlas/apagarlas o quitarlas en «Capas ▾» y llevarlas a Civil 3D con el DXF.

`Main.superficies` = registros (`nucleo.superficies.registro`: sin geometría) y `Main._superficies_datos` =
{sha1: bytes del archivo del cliente}. Los dos van al .digproj (`superficies/<sha1>.<ext>`), al deshacer
(solo la lista) y al respaldo del asistente. La geometría se vuelve a leer del archivo y se lleva al sistema
de la georreferencia (`nucleo.superficies.normalizar`); el MISMO TIN se dibuja aquí y se escribe en LandXML
junto al DXF (`escribir_para_dxf`).
"""
from __future__ import annotations

import os

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import superficies as S
from nucleo import superficies_leer as L
from nucleo.model import Z_PDF
from traduccion.i18n import t as _tr

Z_SUPERFICIE = Z_PDF + 0.8         # sobre el PDF, debajo de lo dibujado
COLOR = "#8a6d3b"                  # tierra (no es color de ninguna utilidad)


class SuperficiesMixin:
    # ── importar ──────────────────────────────────────────────────────────
    def _sup_destino(self):
        """(crs, unidad X/Y, unidad Z) del dibujo; sin georreferencia: ("", "", pies)."""
        geo = getattr(self, "georef", None)
        if geo is not None and geo.active():
            return S.destino(geo.epsg)
        return "", "", S.UNIDAD_PIES

    def _sup_candidatos(self, rutas):
        from ui.dialogos.superficies_dialog import Candidato
        cands = []
        usados = {r["nombre"] for r in getattr(self, "superficies", ())}
        for ruta in rutas:
            nombre = os.path.basename(ruta)
            try:
                with open(ruta, "rb") as f:
                    datos = f.read()
                sha = L.sha1(datos)
                sups = L.leer(nombre, datos)
            except (OSError, L.ErrorSuperficie) as e:
                cands.append(Candidato(archivo=nombre, error=str(e)))
                continue
            self._superficies_datos[sha] = datos
            for k, s in enumerate(sups):
                libre = S.nombre_libre(s.nombre, usados)          # el nombre que quedará, ya en el diálogo
                usados.add(libre)
                cands.append(Candidato(archivo=nombre, sha=sha, indice=k, sup=s, nombre=libre, crs=s.crs,
                                       avisos=list(s.avisos)))
        return cands

    def importar_superficies(self, rutas=None, elegir=None, ubicar=None):
        """«Importar superficies…». `rutas`, `elegir(candidatos) -> elegidos` y `ubicar` («EPSG:n» o código de Civil
        3D: ubicar el plano sin georreferencia en ese sistema) son para pruebas (sin diálogos)."""
        if not hasattr(self, "_superficies_datos"):
            self._superficies_datos = {}
        self._sup_ubicado = None
        if isinstance(rutas, bool):                         # QAction.triggered manda `checked`
            rutas = None
        if rutas is None:
            rutas, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self, _tr("Importar superficies"), "", _tr("Superficies (*.xml *.tif *.tiff)"))
            if not rutas:
                return 0
        cands = self._sup_candidatos(rutas)
        fallidas = [(c.archivo, c.error) for c in cands if c.sup is None]
        crs, _uxy, _uz = self._sup_destino()
        georef = bool(crs)
        if cands and not any(c.sup is not None for c in cands):     # ninguna se pudo leer: nada que elegir
            self._sup_avisar_importacion([], fallidas)
            return 0
        if elegir is None:
            from ui.dialogos.superficies_dialog import SuperficiesDialog
            dlg = SuperficiesDialog(cands, crs, georef, self, escala=self._sup_escala_txt())
            if dlg.exec() != QtWidgets.QDialog.Accepted:
                return 0
            elegidos = dlg.elegidos()
            if dlg.ubicar():
                _crs, ubicar, _c = dlg.crs_para_ubicar()
        else:
            elegidos = elegir(cands)
        if not elegidos:
            return 0
        self._push()
        if ubicar and not georef:
            try:
                self._sup_ubicar_plano(ubicar, elegidos)
            except (S.ErrorSistema, L.ErrorSuperficie, ValueError, np.linalg.LinAlgError) as e:
                self._sup_ubicado = ("", "", str(e))                  # el aviso lo dice
        primero = len(self.superficies)
        usados = {r["nombre"] for r in self.superficies}
        for c in elegidos:
            reg = S.registro(c.sup, c.archivo, c.sha, c.indice, c.crs)
            reg["nombre"] = S.nombre_libre(c.nombre or c.sup.nombre, usados)
            usados.add(reg["nombre"])
            self.superficies.append(reg)
        self._sup_firma = None
        self._redraw()
        self._sync_boton_capas()
        self._llenar_lista_superficies()
        self._sup_avisar_importacion(list(range(primero, len(self.superficies))), fallidas)
        return len(elegidos)

    def _sup_escala_txt(self):
        try:
            v = float(self.scale) * 72.0
        except (TypeError, ValueError):
            return ""
        return f"1\"={v:.0f}'" if v > 0 else ""

    def _sup_ubicar_plano(self, texto_crs, elegidos):
        """Plano sin georreferencia → georreferencia en el sistema de la superficie (pedido 2026-11-12): la escala de
        la hoja (cajetín), sin giro, con el centro de la hoja sobre el centro de la primera superficie elegida que
        está en ese sistema (o la primera). `Georef.cs_code` = el código de Civil 3D, así el dibujo queda en él."""
        from geo import georef as georef_mod
        from nucleo import sistemas_cs
        from geometry import to_cad
        crs, err, _d = sistemas_cs.resolver(texto_crs)
        if err or not crs:
            raise S.ErrorSistema(err or _tr("Sin sistema de coordenadas para ubicar el plano."))
        unidad = S.unidad_de_epsg(crs) or "meter"
        base = next((c for c in elegidos if (c.crs or crs) == crs), elegidos[0])
        pts = S.normalizar(base.sup, base.crs or crs, crs, unidad, S.UNIDAD_PIES)
        x0, y0, x1, y1 = S.recuadro(pts)
        tam = self.canvas.tam_hoja() or (1000.0, 1000.0)
        matriz = S.matriz_sobre_superficie(
            lambda x, y: to_cad(x, y, self.scale, self.rot, self.W, self.H, self.derot, self.zoom),
            float(tam[0]), float(tam[1]), ((x0 + x1) / 2.0, (y0 + y1) / 2.0), unidad)
        self.georef = georef_mod.Georef(matrix=matriz, epsg=int(crs.removeprefix("EPSG:")), kind="affine",
                                        cs_code=sistemas_cs.codigo_civil3d(texto_crs))
        self._sup_ubicado = (crs, self.georef.cs_code, base.nombre or base.sup.nombre)
        self._dirty = True
        if hasattr(self, "_update_geo_status"):
            self._update_geo_status()

    # ── geometría ─────────────────────────────────────────────────────────
    def _sup_superficie(self, reg):
        datos = (getattr(self, "_superficies_datos", None) or {}).get(reg["sha1"])
        if datos is None:
            raise L.ErrorSuperficie(_tr("Falta el archivo de la superficie «{n}».").format(n=reg["nombre"]))
        cache = self.__dict__.setdefault("_sup_leidas", {})
        clave = (reg["sha1"], reg["archivo"])
        if clave not in cache:
            cache[clave] = L.leer(reg["archivo"], datos)
        return cache[clave][int(reg.get("indice", 0))]

    def _sup_geometria(self, reg):
        """(puntos en el sistema del dibujo, triángulos, invisibles, unidad X/Y del LandXML)."""
        crs, uxy, uz = self._sup_destino()
        cache = self.__dict__.setdefault("_sup_geo", {})
        clave = (reg["sha1"], reg["archivo"], reg.get("indice", 0), reg.get("crs", ""), crs, uxy, uz)
        if clave not in cache:
            sup = self._sup_superficie(reg)
            origen = reg.get("crs") or crs
            pts = S.normalizar(sup, origen, crs, uxy, uz)
            # unidad del LandXML = la de las cotas (pies, o pies US con un CRS en pies US): el dibujo de Civil 3D
            # es en pies (INSUNITS=2) y el plugin iguala <Units> al dibujo para que nada se convierta
            cache[clave] = (pts, sup.triangulos, sup.invisibles, uz)
        return cache[clave]

    def _sup_a_plano(self, xy):
        """Coordenadas del dibujo → px del plano (inversa de la georreferencia) o None sin georreferencia."""
        geo = getattr(self, "georef", None)
        if geo is None or not geo.active():
            return None
        m = np.array(geo.matrix, dtype=np.float64)
        inv = np.linalg.inv(m)
        h = np.column_stack([xy[:, 0], xy[:, 1], np.ones(len(xy))])
        p = h @ inv.T
        return p[:, :2] / p[:, 2:3]

    def _superficies_3d(self):
        """Para la Vista 3D (2026-11-12): [{px, z, tri}] de cada superficie ENCENDIDA, en px del lienzo (la inversa
        de la georreferencia) y cota en pies; sin las caras invisibles. Sin georreferencia: [] (no hay dónde
        ponerla respecto a las redes)."""
        out = []
        for reg in getattr(self, "superficies", ()) or ():
            if not reg.get("visible", True):
                continue
            try:
                pts, tri, inv, _u = self._sup_geometria(reg)
            except (L.ErrorSuperficie, S.ErrorSistema):
                continue
            plano = self._sup_a_plano(pts[:, :2])
            if plano is None:
                return []
            tri = np.asarray(tri)
            if inv is not None and len(inv):
                tri = tri[~np.asarray(inv, dtype=bool)]
            out.append(dict(px=plano, z=np.asarray(pts[:, 2], np.float64), tri=tri))
        return out

    # ── dibujo ────────────────────────────────────────────────────────────
    def _superficies_al_dia(self):
        """Contorno + nombre de cada superficie visible (ítems propios: no pasan por `_overlay`)."""
        sc = self.canvas.scene()
        firma = (tuple((r["sha1"], r["nombre"], r.get("crs", ""), r.get("visible", True)) for r in self.superficies),
                 repr(getattr(self.georef, "matrix", None)) if self.georef.active() else None, id(sc))
        viejos = getattr(self, "_sup_items", [])
        if firma == getattr(self, "_sup_firma", None) and all(it.scene() is sc for it in viejos):
            return
        for it in viejos:
            try:
                if it.scene() is not None:
                    it.scene().removeItem(it)
            except RuntimeError:
                pass
        self._sup_items, self._sup_firma = [], firma
        QtCore.QTimer.singleShot(0, self, self._llenar_lista_superficies)    # Inventario → Superficies
        if not self.georef.active():
            return
        pluma = QtGui.QPen(QtGui.QColor(COLOR), 2)
        pluma.setCosmetic(True)
        pluma.setStyle(QtCore.Qt.DashLine)
        relleno = QtGui.QColor(COLOR)
        relleno.setAlpha(28)
        for k, reg in enumerate(self.superficies):
            if not reg.get("visible", True):
                continue
            try:
                pts, tri, inv, _u = self._sup_geometria(reg)
            except (L.ErrorSuperficie, S.ErrorSistema) as e:
                self._info(str(e))
                continue
            plano = self._sup_a_plano(pts[:, :2])
            camino = QtGui.QPainterPath()
            for lazo in S.contorno(tri, inv):
                xy = plano[lazo]
                camino.moveTo(*xy[0])
                for x, y in xy[1:]:
                    camino.lineTo(x, y)
            it = QtWidgets.QGraphicsPathItem(camino)
            it.setPen(pluma)
            it.setBrush(relleno)
            it.setZValue(Z_SUPERFICIE)
            it.setToolTip(_tr("Superficie {n} · {p} puntos · {t} triángulos").format(
                n=reg["nombre"], p=reg["n_puntos"], t=reg["n_triangulos"]))
            it.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            it.setData(0, ("superficie", k))
            sc.addItem(it)
            # nombre en una pastilla del color de la tierra (como las etiquetas C-n), encima del contorno y apilada
            txt = QtWidgets.QGraphicsSimpleTextItem(reg["nombre"])
            f = txt.font(); f.setPixelSize(11); f.setBold(True); txt.setFont(f)
            txt.setBrush(QtGui.QColor(255, 255, 255))
            rt = txt.boundingRect().adjusted(-4, -2, 4, 2)
            caja = QtWidgets.QGraphicsRectItem(rt)
            caja.setBrush(QtGui.QColor(COLOR))
            caja.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            txt.setParentItem(caja)
            r = camino.boundingRect()
            caja.setPos(r.left(), r.top())
            caja.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
            n_vis = sum(1 for q in self.superficies[:k] if q.get("visible", True))
            caja.setTransform(QtGui.QTransform.fromTranslate(4, -(rt.height() + 3) * (n_vis + 1)))
            caja.setZValue(Z_SUPERFICIE)
            caja.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            caja.setToolTip(it.toolTip())
            sc.addItem(caja)
            txt = caja
            self._sup_items += [it, txt]

    # ── capas ─────────────────────────────────────────────────────────────
    def _filas_superficies(self):
        from ui.comun import capas_popup as CP
        return [CP.Fila(CP.SUPERFICIE, k, r["nombre"], r.get("visible", True), QtGui.QColor(COLOR),
                        f"{r['n_puntos']:,}".replace(",", " "),
                        _tr("{f} · {a} · clic derecho: quitar").format(f=r["formato"], a=r["archivo"]),
                        quitable=True)
                for k, r in enumerate(self.superficies)]

    def _cambiar_superficie(self, k, visible):
        if 0 <= k < len(self.superficies):
            self.superficies[k]["visible"] = bool(visible)
            self._superficies_al_dia()
            self._llenar_lista_superficies()
            if hasattr(self, "_vista3d_al_dia"):
                self._vista3d_al_dia()
            self._sync_boton_capas()

    def quitar_superficie(self, k):
        if not 0 <= k < len(self.superficies):
            return
        nombre = self.superficies[k]["nombre"]
        self._push()
        del self.superficies[k]
        self._superficies_al_dia()
        self._llenar_lista_superficies()
        if hasattr(self, "_vista3d_al_dia"):
            self._vista3d_al_dia()
        self._sync_boton_capas()
        self._info(_tr("Superficie quitada: {n} (Ctrl+Z la devuelve).").format(n=nombre))

    # ── proyecto ──────────────────────────────────────────────────────────
    def _sup_entradas_zip(self):
        """[(«superficies/<sha1>.<ext>», bytes)] de los archivos que usan las superficies del proyecto."""
        datos = getattr(self, "_superficies_datos", None) or {}
        vistos, out = set(), []
        for r in getattr(self, "superficies", ()) or ():
            sha = r.get("sha1")
            if sha in datos and sha not in vistos:
                vistos.add(sha)
                ext = os.path.splitext(r.get("archivo", ""))[1].lower() or ".bin"
                out.append((f"superficies/{sha}{ext}", datos[sha]))
        return out

    # ── DXF ───────────────────────────────────────────────────────────────
    def escribir_para_dxf(self, ruta_dxf):
        """Escribe el LandXML de cada superficie junto al DXF (`<dxf>_superficies/`) y devuelve
        [(registro, puntos, triángulos, ruta relativa, ruta absoluta, sha1, unidad)]."""
        if not self.superficies:
            return []
        import datetime as _dt
        base = os.path.splitext(ruta_dxf)[0] + "_superficies"
        os.makedirs(base, exist_ok=True)
        ahora = _dt.datetime.now()
        salida, usados = [], set()
        for reg in self.superficies:
            pts, tri, inv, unidad = self._sup_geometria(reg)
            nombre = S.nombre_archivo(reg["nombre"])
            while nombre.lower() in usados:
                nombre = "_" + nombre
            usados.add(nombre.lower())
            datos = S.escribir_landxml(reg["nombre"], pts, tri, unidad, inv,
                                       ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"))
            ruta = os.path.join(base, nombre)
            with open(ruta, "wb") as f:
                f.write(datos)
            rel = os.path.basename(base) + "/" + nombre
            salida.append((reg, pts, tri, rel, os.path.abspath(ruta), L.sha1(datos), unidad))
        return salida

