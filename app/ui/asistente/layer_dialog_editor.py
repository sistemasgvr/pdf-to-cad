"""layer_dialog_editor.py — «Capas de la hoja» en modo EDITOR = la vista «Capas y estilos…» del panel «Reconocer»
(plan 2026-11-16, «reconocimiento desde el editor», Tarea 8).

Es el MISMO `SheetLayersDialog` (árbol, asignar utilidad y rol, estilos sugeridos, elegir un estilo con un clic en su
tinta, símbolos de fuente, leyenda, tarjetas «por las letras», escala), con `editor=True`:
  · sin barra de pasos (no hay asistente: es la hoja del editor) ni «◀ Hoja N / M ▶»;
  · sin la tarjeta «Reconocer» (las filas del panel la reemplazan, una por utilidad) ni su interruptor en el árbol;
  · «Aplicar» en lugar de «Continuar», siempre activo: lo que falta para reconocer lo dice cada fila del panel
    («Todas sus capas están ocultas», «Asigna al menos un estilo…»).
La hoja se ve en la vista propia del diálogo (la misma imagen y el mismo resaltado que en el asistente).

`dialogo_editor` lo arma con la interpretación de la hoja (`hoja.interpretar_trabajo`), si la hay: le pasa sus capas,
su leyenda, lo que se ve y los estilos sugeridos como hace `capas_previas`, así la ventana no vuelve a leer la hoja.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from hoja import leyenda_estandar, pdf_layers
from traduccion.i18n import t as _tr

_ROLE_SUB = QtCore.Qt.UserRole + 2          # = layer_dialog._ROLE_SUB (subgrupo de su fila)


class ModoEditorMixin:
    _editor = False

    def _modo_editor(self):
        """Lo que en el editor no va (ver el docstring del módulo)."""
        self._cabecera.hide()
        self.pastilla_hoja.hide()
        box = getattr(self, "_recog_box", None)
        if box is not None:
            box.hide()
        self.tree.setColumnHidden(1, True)
        if not self._flat_sheet():                    # sin el interruptor «reconocer»: la ayuda no lo nombra
            self._hint_capas.setText(_tr("Pulsa una línea del PDF para identificar y resaltar su capa. "
                                         "Casilla = mostrar · ▸ = capa por capa"))
        self.btn_ok.setText(_tr("Aplicar"))
        self.btn_ok.setEnabled(True)
        self.setWindowTitle(_tr("Capas y estilos"))

    def enfocar_parte(self, parte):
        """Abre en la utilidad de la fila (`parte`): su grupo desplegado y a la vista; las válvulas, en su
        subgrupo «Válvulas» de cada utilidad. Diámetros, rótulos o None: el árbol como siempre."""
        parte = str(parte or "").strip().upper()
        if parte == "VALVULAS":
            primera = None
            for grp in self._groups.values():
                for j in range(grp.childCount()):
                    sub = grp.child(j)
                    if sub.data(0, _ROLE_SUB) == leyenda_estandar.SUB_VALVULAS:
                        grp.setExpanded(True)
                        sub.setExpanded(True)
                        primera = primera or sub
            if primera is not None:
                self.tree.scrollToItem(primera, QtWidgets.QAbstractItemView.PositionAtTop)
            return
        grp = self._groups.get(parte)
        if grp is None:
            return
        grp.setExpanded(True)
        self.tree.scrollToItem(grp, QtWidgets.QAbstractItemView.PositionAtTop)


def previa_de_interpretacion(doc, hoja: int, interp: dict):
    """`capas_previas.Previa` con lo que leyó la interpretación (sin imagen: la hoja se dibuja como siempre). Deja la
    leyenda y los estilos sugeridos en las cachés del documento, donde el diálogo los busca. Las casillas = las capas
    ocultas AHORA en el documento (la interpretación se leyó con todas encendidas)."""
    from ui.asistente.capas_previas import Previa
    hoja = int(hoja)
    ocultas = pdf_layers.hidden_layers(doc)
    layers = [dict(L, on=L["name"] not in ocultas) for L in (interp.get("layers") or [])]
    if interp.get("leyenda") is not None:
        doc.__dict__.setdefault("_pdfcad_leyenda_mapa", {}).setdefault(hoja, interp["leyenda"])
    if "sugeridos" in interp and interp["sugeridos"] is not None:
        doc.__dict__.setdefault("_pdfcad_estilos_sugeridos", {}).setdefault(hoja, interp["sugeridos"])
    return Previa(hoja, layers, frozenset(interp.get("visibles") or ()), pdf_layers.encendidas(doc), None)


def dialogo_editor(parent, doc, page_index: int, interp=None, en_proceso=False, **kw):
    """El diálogo en modo editor, o None si la hoja no tiene capas ni estilos (escaneo). `kw` = los de
    `SheetLayersDialog` (layout, letters_off, roles_by_utility, scale_ft_per_pt, legend_sources, legend_cache…)."""
    from ui.asistente import capas_previas, layer_dialog
    from ui.comun.busy import busy, detalle_de
    with busy(parent, _tr("Leyendo las capas de la hoja…"), _tr("Contando los trazos de cada capa")) as ov:
        previa = None
        if interp:
            previa = previa_de_interpretacion(doc, page_index, interp)
        elif en_proceso:
            previa = capas_previas.leer(doc, page_index, layer_dialog._PREVIEW_ZOOM, al_avanzar=lambda a: (
                ov.step(detail=detalle_de(a[1], a[2], a[3]), pump=False)
                if a and a[0] == "detalle" and ov.active else None))
        layers = previa.layers if previa is not None else pdf_layers.page_layers(doc, page_index)
        if not layers:
            return None
        dlg = layer_dialog.SheetLayersDialog(parent, doc, page_index, layers=layers, previa=previa,
                                             en_proceso=en_proceso, editor=True, **kw)
        dlg._escala_entrada = kw.get("scale_ft_per_pt")
    return dlg


def resultado(dlg) -> tuple:
    """Lo mismo que `choose_sheet_layers(include_roles=True)` al continuar."""
    return (dlg.hidden_names(), dlg.page_index(), dlg.recognition_utilities(), dlg.letters_off(),
            dlg.roles_by_utility(), dlg.scale_ft_per_pt())
