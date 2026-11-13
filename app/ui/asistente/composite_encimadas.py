"""«Continuar» con hojas ENCIMADAS en «Componer hoja»: avisar antes de reconocer.

Reporte 2026-11-13 (cliente en fase beta, mapas de alcantarillado de Phoenix): la composición
sugerida no apareció y el usuario tomó 10–15 hojas una por una, sin ordenarlas; quedaron unas
encima de otras. En el reconocimiento la tinta y la leyenda de una hoja tapaban a la de abajo (las
líneas salían de otra utilidad) y el proceso podía cerrarse. Ahora, al continuar, si hay piezas
que se tapan en buena parte (`composite_checks.encimadas`), se pregunta: usar la composición
sugerida (si la hay), volver a acomodarlas o continuar así. Nada se mueve solo. Los escaneos
(`comp.manual`) se acomodan a mano a propósito: no se revisan. Mezcla de `CompositeDialog`.
"""
from __future__ import annotations

from PySide6 import QtWidgets

from hoja import composite as C
from hoja import composite_checks as CK
from traduccion.i18n import t as _tr

MAX_NOMBRES = 4


class EncimadasMixin:
    def _piezas_encimadas(self):
        """[(i, j, fracción)] de las piezas de la hoja compuesta que se tapan."""
        if getattr(self.comp, "manual", False) or len(self.comp.pieces) < 2:
            return []
        try:
            t = self.comp.target_scale()
            rects = [C.piece_rect(p, self.view.page_size(p), t) for p in self.comp.pieces]
        except Exception:
            return []
        return CK.encimadas(rects)

    def _nombre_pieza(self, p) -> str:
        multi = len({q.source for q in self.comp.pieces}) > 1
        if multi:
            return _tr("{pdf} · hoja {n}").format(pdf=self.sources[p.source]["name"], n=p.page + 1)
        return _tr("Hoja {n}").format(n=p.page + 1)

    def _revisar_encimadas(self) -> str:
        """'ok' (seguir) | 'back' (quedarse en el compositor)."""
        pares = self._piezas_encimadas()
        if not pares:
            return "ok"
        piezas = self.comp.pieces
        lineas = [_tr("{a} y {b} ({pct}% encimadas)").format(
                      a=self._nombre_pieza(piezas[i]), b=self._nombre_pieza(piezas[j]), pct=round(f * 100))
                  for i, j, f in pares[:MAX_NOMBRES]]
        if len(pares) > MAX_NOMBRES:
            lineas.append(_tr("… y {n} pares más").format(n=len(pares) - MAX_NOMBRES))
        g = None
        try:
            g, _preg = self._sug_grupo()
        except Exception:
            g = None
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle(_tr("Hojas encimadas"))
        box.setText(_tr("Hay hojas puestas una encima de otra en la hoja compuesta."))
        box.setInformativeText(
            "\n".join("• " + s for s in lineas) + "\n\n"
            + _tr("Al reconocer, la tinta y la leyenda de una hoja tapan a la de abajo: las líneas pueden salir "
                  "con la utilidad equivocada o el reconocimiento no terminar. Acomódalas borde con borde "
                  "(pestaña «Hoja compuesta») antes de continuar."))
        b_sug = None
        if g is not None and g.composite is not None:
            b_sug = box.addButton(_tr("Usar la composición sugerida"), QtWidgets.QMessageBox.AcceptRole)
        b_back = box.addButton(_tr("Volver a acomodarlas"), QtWidgets.QMessageBox.RejectRole)
        b_seguir = box.addButton(_tr("Continuar así"), QtWidgets.QMessageBox.DestructiveRole)
        for b in (b_seguir,):
            b.setProperty("secondary", True)
        for b in box.buttons():
            b.style().unpolish(b); b.style().polish(b)
        box.setDefaultButton(b_sug or b_back)
        box.setEscapeButton(b_back)
        box.exec()
        clicked = box.clickedButton()
        if b_sug is not None and clicked is b_sug:
            self._sug_usar()
            return "back"                      # que la vea antes de continuar
        if clicked is b_seguir:
            return "ok"
        try:
            self._go_tab(CK.TAB_SHEET)
            self.view.select(pares[0][1])       # la pieza que tapa a otra, lista para moverla
        except Exception:
            pass
        return "back"
