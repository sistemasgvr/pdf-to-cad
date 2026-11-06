"""Válvulas en la ventana (pedido del usuario 2026-11-05): `self.valvulas` (`nucleo/valvulas`), su capa en el lienzo, la
fila de «Capas ▾», el globo, el clic derecho y los datos de la Tabla y del DXF. No tocan pipes ni estructuras.
"""
from nucleo import model_ops
from nucleo import valvulas as V
from ui.comun.capa_valvulas import CapaValvulas
from ui.ventana.ventana_comun import *  # noqa: F401,F403

CLIC_PX = 10.0                     # radio del clic, en pantalla
GRIS = "#8a8f98"                   # válvula sin utilidad: ninguna capa le da color


class ValvulasMixin:
    def _guardar_valvulas(self, results) -> int:
        """Al importar: las de la hoja (la misma lista en cada utilidad) se suman a las del proyecto."""
        if not getattr(self, "_reconocer_valvulas", True):
            return 0
        nuevas = next((list(r.valvulas) for r in results if getattr(r, "valvulas", None)), [])
        antes = len(self.valvulas)
        self.valvulas = V.juntar(self.valvulas, nuevas)
        return len(self.valvulas) - antes

    def _valvula_rel(self, v):
        return V.relacion(v, self.pipes, V.tol_pt(v) * float(self.zoom or 1.0), self._cerca_de_valvula)

    def _cerca_de_valvula(self, x, y, r):
        return self._utilidades_cerca(x, y, r, todas=True) if self.pipes else []

    def _diam_de_valvula(self, rel):
        """El diámetro de su tubería, solo si no es el de por defecto (no se inventa)."""
        if rel is None:
            return None
        d, por_defecto = model_ops.diametro(self.pipes[rel[0]])
        return None if por_defecto else d

    def _dibujar_valvulas(self, sc):
        self._capa_valvulas = None
        if not self.valvulas:
            return
        entradas = []
        for v in self.valvulas:
            rel = self._valvula_rel(v)
            color = layer_qcolor(v["utilidad"]) if v.get("utilidad") else QtGui.QColor(GRIS)
            entradas.append((v["x"], v["y"], rel[2] if rel else 0.0, color, v.get("certeza") == V.POR_CONFIRMAR))
        capa = CapaValvulas(Z_MARK + 1, entradas, getattr(self, "_valvula_sel", -1))
        sc.addItem(capa)
        self._overlay.append(capa)
        self._capa_valvulas = capa
        self._sync_capa_valvulas()

    def _sync_capa_valvulas(self):
        capa = getattr(self, "_capa_valvulas", None)
        if capa is not None:
            capa.setVisible(V.CAPA not in self.capas_apagadas)

    def _valvula_en(self, x, y) -> int:
        """Índice de la válvula bajo el punto (px de la hoja), o −1. Con su capa apagada no se elige."""
        if not self.valvulas or V.CAPA in self.capas_apagadas:
            return -1
        r = CLIC_PX / max(1e-6, self.canvas.transform().m11())
        mejor, dist = -1, r
        for i, v in enumerate(self.valvulas):
            d = math.hypot(v["x"] - x, v["y"] - y)
            if d <= dist:
                mejor, dist = i, d
        return mejor

    def _texto_valvula(self, v) -> str:
        """Una línea para el globo y la barra de estado."""
        partes = [_tr(V.nombre(v))]
        if v.get("utilidad"):
            partes.append(self._tipo(v["utilidad"]))
        if v.get("estado"):
            partes.append(_tr(v["estado"]))
        d = self._diam_de_valvula(self._valvula_rel(v))
        if d:
            partes.append(f'{d:g}"')
        if v.get("certeza") == V.POR_CONFIRMAR:
            partes.append(_tr("por confirmar"))
        return " · ".join(partes)

    def _elegir_valvula(self, x, y) -> bool:
        i = self._valvula_en(x, y)
        if i < 0:
            if getattr(self, "_valvula_sel", -1) >= 0:
                self._valvula_sel = -1
                capa = getattr(self, "_capa_valvulas", None)
                if capa is not None:
                    capa.elegida = -1
                    capa.update()
            return False
        self._valvula_sel = i
        capa = getattr(self, "_capa_valvulas", None)
        if capa is not None:
            capa.elegida = i
            capa.update()
        self._info(self._texto_valvula(self.valvulas[i]))
        return True

    def _menu_valvula(self, x, y) -> bool:
        """Clic derecho sobre una válvula. True si había una."""
        i = self._valvula_en(x, y)
        if i < 0:
            return False
        menu = QtWidgets.QMenu(self)
        titulo = menu.addAction(self._texto_valvula(self.valvulas[i]))
        titulo.setEnabled(False)
        menu.addSeparator()
        if self.valvulas[i].get("certeza") == V.POR_CONFIRMAR:
            menu.addAction(_tr("Confirmar válvula"), lambda: self._confirmar_valvula(i))
        menu.addAction(_tr("Borrar válvula"), lambda: self._borrar_valvula(i))
        menu.exec(QtGui.QCursor.pos())
        return True

    def _confirmar_valvula(self, i):
        self._push()
        self.valvulas[i] = dict(self.valvulas[i], certeza=V.SEGURA)
        self._redraw()

    def _borrar_valvula(self, i):
        self._push()
        del self.valvulas[i]
        self._valvula_sel = -1
        self._redraw()
        self._sync_boton_capas()

    def _filas_valvulas(self):
        """[(válvula, índice de su tubería o None, diámetro o None, rumbo)] para la Tabla y el DXF."""
        out = []
        for v in self.valvulas:
            rel = self._valvula_rel(v)
            out.append((v, rel[0] if rel else None, self._diam_de_valvula(rel), rel[2] if rel else 0.0))
        return out
