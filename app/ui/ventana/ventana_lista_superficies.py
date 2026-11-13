"""Inventario → «Superficies» (pedido del usuario 2026-11-12: «saber si se importaron bien o no») y el aviso breve
al importar.

Cada superficie se REVISA (`_sup_revisar`) con lo mismo que usa para dibujarse y exportarse:
  - el archivo del cliente está en el proyecto y es el mismo (sha1);
  - se vuelve a leer y da los mismos puntos y triángulos que al importar;
  - se lleva al sistema del dibujo sin error y sin puntos inválidos (cotas mínima/máxima);
  - sobre el plano: sin georreferencia no se ve (viaja igual a Civil 3D); si queda FUERA de la hoja, lo más
    probable es que el sistema de coordenadas elegido no sea el del archivo.
Nivel: «ok», «aviso» (se importó, pero mira esto) o «error» (no va a llegar bien a Civil 3D).

Clic en una fila → el plano la encuadra; clic derecho → encender/apagar o quitar.
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import superficies as S
from nucleo import superficies_leer as L
from nucleo.model import TAB_SUP
from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon
from ui.comun.ui_common import fila_lista

OK, AVISO, ERROR = "ok", "aviso", "error"


def _miles(n):
    return f"{int(n):,}".replace(",", " ")


class ListaSuperficiesMixin:
    # ── revisión ─────────────────────────────────────────────────────────
    def _sup_revisar(self, reg) -> tuple:
        """(nivel, resumen corto, [líneas de detalle]) de una superficie del proyecto."""
        det = []
        datos = (getattr(self, "_superficies_datos", None) or {}).get(reg.get("sha1"))
        if datos is None:
            return ERROR, _tr("Falta el archivo"), [_tr("El archivo «{a}» no está en el proyecto.").format(
                a=reg.get("archivo", ""))]
        if L.sha1(datos) != reg.get("sha1"):
            return ERROR, _tr("Archivo distinto"), [_tr("El archivo guardado no es el que se importó.")]
        det.append(_tr("✔ Archivo guardado en el proyecto: {a}").format(a=reg.get("archivo", "")))
        try:
            pts, tri, _inv, unidad = self._sup_geometria(reg)
        except (L.ErrorSuperficie, S.ErrorSistema, IndexError) as e:
            return ERROR, _tr("No se puede leer"), det + [str(e)]
        if len(pts) != reg.get("n_puntos") or len(tri) != reg.get("n_triangulos"):
            return ERROR, _tr("Cifras distintas"), det + [_tr(
                "Ahora da {p} puntos y {t} triángulos; al importar eran {p0} y {t0}.").format(
                p=_miles(len(pts)), t=_miles(len(tri)), p0=_miles(reg.get("n_puntos", 0)),
                t0=_miles(reg.get("n_triangulos", 0)))]
        if not len(pts) or not np.all(np.isfinite(pts)):
            return ERROR, _tr("Puntos inválidos"), det + [_tr("Hay puntos sin coordenadas válidas.")]
        u = {"foot": _tr("pies"), "USSurveyFoot": _tr("pies US"), "meter": _tr("metros")}.get(unidad, unidad)
        det.append(_tr("✔ {p} puntos y {t} triángulos, los mismos del archivo").format(
            p=_miles(len(pts)), t=_miles(len(tri))))
        det.append(_tr("✔ Cotas de {a:.2f} a {b:.2f} {u}").format(a=float(pts[:, 2].min()),
                                                                     b=float(pts[:, 2].max()), u=u))
        crs, _uxy, _uz = self._sup_destino()
        origen = reg.get("crs") or crs
        if crs:
            det.append(_tr("✔ Sistema: {o} → {d}").format(o=origen, d=crs) if origen != crs else
                       _tr("✔ Sistema: {d}").format(d=crs))
        nivel, resumen = OK, _tr("Importada bien")
        if not crs:
            nivel, resumen = AVISO, _tr("No se ve en el plano")
            det.append(_tr("⚠ El plano no está georreferenciado: no se dibuja, pero viaja a Civil 3D con sus "
                           "coordenadas."))
        else:
            fuera = self._sup_fuera_de_la_hoja(pts)
            if fuera:
                nivel, resumen = AVISO, _tr("Fuera de la hoja")
                det.append(_tr("⚠ Queda fuera de la hoja. ¿El sistema de coordenadas del archivo es el correcto?"))
        if not reg.get("visible", True):
            det.append(_tr("Apagada en «Capas ▾»."))
        return nivel, resumen, det

    def _sup_fuera_de_la_hoja(self, pts) -> bool:
        """True si el recuadro de la superficie no toca la hoja del plano (sin hoja: no se sabe → False)."""
        plano = self._sup_a_plano(pts[:, :2])
        if plano is None or not np.all(np.isfinite(plano)):
            return plano is not None
        try:
            tam = self.canvas.tam_hoja()
        except Exception:                                          # noqa: BLE001
            return False
        if not tam:
            return False
        w, h = tam
        if not w or not h:
            return False
        x0, y0 = plano.min(axis=0)
        x1, y1 = plano.max(axis=0)
        return x1 < 0 or y1 < 0 or x0 > w or y0 > h

    # ── lista ────────────────────────────────────────────────────────────
    def _build_lista_superficies(self):
        from ui.comun import rediseno as R
        w = R.transparente(QtWidgets.QWidget())
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.sup_list = QtWidgets.QListWidget()
        self.sup_list.setAccessibleName(_tr("Superficies importadas"))
        self.sup_list.currentRowChanged.connect(self._sel_superficie)
        self.sup_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.sup_list.customContextMenuRequested.connect(self._menu_lista_superficies)
        v.addWidget(self.sup_list, 1)
        self.lbl_sup_info = QtWidgets.QLabel()
        self.lbl_sup_info.setWordWrap(True)
        self.lbl_sup_info.setProperty("rol", "t3")
        self.lbl_sup_info.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        v.addWidget(self.lbl_sup_info)
        self._sup_revision = []
        self._sup_tab_widget = w
        return w

    def _llenar_lista_superficies(self):
        lista = getattr(self, "sup_list", None)
        if lista is None:
            return
        fila_antes = lista.currentRow()
        lista.blockSignals(True)
        lista.clear()
        self._sup_revision = []
        from ui.comun import theme
        tk = theme.tokens()
        for reg in getattr(self, "superficies", ()) or ():
            nivel, resumen, det = self._sup_revisar(reg)
            self._sup_revision.append((nivel, resumen, det))
            texto = " · ".join([reg["nombre"], resumen, reg.get("formato", ""),
                                _tr("{p} puntos").format(p=_miles(reg.get("n_puntos", 0)))])
            ic = {OK: ("mdi:check-circle-outline", tk.success), AVISO: ("mdi:alert-outline", tk.warning),
                  ERROR: ("mdi:alert-circle-outline", tk.danger)}[nivel]
            it = fila_lista(lista, texto, _icon(ic[0], color=ic[1]))
            it.setToolTip("\n".join([reg["nombre"]] + det))
        if lista.count() == 0:
            self.lbl_sup_info.setText(_tr("Sin superficies. Hoja y PDF → Importar superficies…"))
        else:
            lista.setCurrentRow(min(max(fila_antes, 0), lista.count() - 1))
        lista.blockSignals(False)
        self._datos_superficie()
        if hasattr(self, "_filtrar_inventario") and self._current_tab() == TAB_SUP:
            self._filtrar_inventario()

    def _datos_superficie(self):
        k = self.sup_list.currentRow()
        if 0 <= k < len(self._sup_revision):
            _n, _r, det = self._sup_revision[k]
            self.lbl_sup_info.setText("\n".join(det))
        elif self.sup_list.count():
            self.lbl_sup_info.setText("")

    def _sel_superficie(self, k):
        self._datos_superficie()
        if not 0 <= k < len(self.superficies):
            return
        for it in getattr(self, "_sup_items", []) or []:          # el contorno (no la pastilla) de esa superficie
            if isinstance(it, QtWidgets.QGraphicsPathItem) and it.data(0) == ("superficie", k):
                r = it.sceneBoundingRect()
                m = max(r.width(), r.height()) * 0.08
                self.canvas.fitInView(r.adjusted(-m, -m, m, m), QtCore.Qt.KeepAspectRatio)
                return

    def _menu_lista_superficies(self, pos):
        k = self.sup_list.currentRow()
        it = self.sup_list.itemAt(pos)
        if it is not None:
            k = self.sup_list.row(it)
        if not 0 <= k < len(self.superficies):
            return
        menu = QtWidgets.QMenu(self.sup_list)
        vis = self.superficies[k].get("visible", True)
        a_vis = menu.addAction(_tr("Apagar") if vis else _tr("Encender"))
        a_quitar = menu.addAction(_icon("mdi:delete-outline"), _tr("Quitar"))
        elegida = menu.exec(self.sup_list.viewport().mapToGlobal(pos))
        if elegida is a_vis:
            self._cambiar_superficie(k, not vis)
        elif elegida is a_quitar:
            self.quitar_superficie(k)

    # ── aviso breve al importar ──────────────────────────────────────────
    def _sup_avisar_importacion(self, nuevas, fallidas):
        """Toast con el resultado: `nuevas` = índices en `self.superficies` recién importados, `fallidas` =
        [(archivo, motivo)] que no se pudieron leer. Sin la ventana en pantalla (pruebas): la barra de estado."""
        malas, avisos, buenas = [], [], []
        for k in nuevas:
            nivel, resumen, _det = self._sup_revisar(self.superficies[k])
            nombre = self.superficies[k]["nombre"]
            (buenas if nivel == OK else avisos if nivel == AVISO else malas).append(f"{nombre}: {resumen}")
        lineas = avisos + malas + [_tr("No se pudo leer {a}: {m}").format(a=a, m=m) for a, m in fallidas]
        n_ok = len(nuevas) - len(malas)
        if malas or fallidas:
            titulo = (_tr("No se importó") if not n_ok else
                      _tr("Importadas {n} de {t}").format(
                          n=n_ok, t=len(nuevas) + len(fallidas)))
            tono = "aviso"
        elif avisos:
            titulo = (_tr("Importada, con un aviso") if len(nuevas) == 1 else
                      _tr("{n} importadas, con avisos").format(n=len(nuevas)))
            tono = "aviso"
        else:
            titulo = (_tr("Superficie importada") if len(nuevas) == 1 else
                      _tr("{n} superficies importadas").format(n=len(nuevas)))
            tono = "ok"
            lineas = [_tr("Llegaron bien: {n}").format(n=", ".join(b.split(":")[0] for b in buenas))]
        ub = getattr(self, "_sup_ubicado", None)
        if ub and not ub[0]:
            lineas.insert(0, _tr("No se pudo ubicar el plano: {m}").format(m=ub[2]))
            tono = "aviso"
        elif ub:
            lineas.insert(0, _tr("El plano quedó en {crs}{cs}, centrado sobre «{n}». Afínalo con Georreferenciar si "
                                 "hace falta.").format(crs=ub[0], cs=f" ({ub[1]})" if ub[1] else "", n=ub[2]))
        detalle = "\n".join(lineas)
        self._ultimo_aviso_sup = (tono, titulo, detalle)
        if hasattr(self, "_incrustar_ok") and self._incrustar_ok():
            from ui.comun import aviso_breve
            aviso_breve.mostrar(self, titulo, detalle, (_tr("Ver"), self._ver_superficies), tono)
        else:
            self._info(titulo + (" · " + detalle.replace("\n", " · ") if detalle else ""))

    def _ver_superficies(self):
        """Abre Inventario → Superficies."""
        if hasattr(self, "_abrir_inventario"):
            self._abrir_inventario()
        self._show_tab(TAB_SUP)
