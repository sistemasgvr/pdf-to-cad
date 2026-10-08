"""recognition_layers_view.py — «Capas usadas» de la vista previa del reconocimiento.

Lista informativa de las capas que se tomaron como líneas / bóvedas (asignadas
solas por su nombre). Clic en una fila = verla en la hoja (pedido del usuario
2026-10-03): la vista previa resalta lo reconocido de esa capa, atenúa lo demás y
encuadra la zona. Vale para una capa, para «Líneas»/«Bóvedas» de una utilidad o
para la utilidad entera (su encabezado). Otro clic en la misma fila, o «Ver todo»,
lo quita. Con el teclado: flechas + Enter.

El panel solo emite `focusChanged(dict | None)` —{utility, kind, ocg, label}; kind =
"line" | "structure" | None, ocg = None para un encabezado— y muestra el texto que
le pasa la vista previa (`set_status`).
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr, N_
from ui.comun.icons import icon
from nucleo.model import TIPOS
from ui.comun.ui_common import swatch_icon
from reconocimiento import recognition as rec
from ui.comun import theme as _theme

_UTILITY_LABEL = {key: label for label, key in TIPOS}
_STRUCT_LABEL = {"ELECTRICO": N_("Bóvedas"), "ALCANTARILLADO": N_("Buzones"), "GAS": N_("Bóvedas"),
                 "TELECOM": N_("Bóvedas")}
FOCUS_ROLE = QtCore.Qt.UserRole + 1


class _LayersList(QtWidgets.QListWidget):
    """Pide el alto de su contenido (hasta un tope) y crece con el panel si sobra
    sitio. Enter/Espacio sobre la fila actual = clic."""

    CAP = 240

    def sizeHint(self):
        rows = sum(self.sizeHintForRow(i) for i in range(self.count())) + 2 * self.frameWidth() + 4
        return QtCore.QSize(super().sizeHint().width(), max(self.minimumHeight(), min(self.CAP, rows)))

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space) and self.currentItem():
            self.itemClicked.emit(self.currentItem())
            return
        super().keyPressEvent(e)


def _focus_of(item) -> dict | None:
    data = item.data(FOCUS_ROLE) if item is not None else None
    return dict(data) if data else None


class UsedLayersPanel(QtWidgets.QWidget):
    focusChanged = QtCore.Signal(object)

    def __init__(self, results, colors: dict, parent=None):
        super().__init__(parent)
        t = _theme.tokens()
        self._focus: dict | None = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)

        head = QtWidgets.QHBoxLayout(); head.setSpacing(6)
        title = QtWidgets.QLabel(_tr("Capas usadas"))
        f = title.font(); f.setBold(True); title.setFont(f)
        head.addWidget(title, 0)
        info = QtWidgets.QLabel()
        info.setPixmap(icon("mdi:information-outline", color=t.text_muted).pixmap(16, 16))
        info.setToolTip(_tr("Se asignan automáticamente por su nombre. «Ajustar capas…» solo hace "
                            "falta si el plano usa otros nombres."))
        head.addWidget(info, 0)
        head.addStretch(1)
        hidden = sorted({name for r in results for name in (getattr(r, "hidden_ocgs", None) or [])})
        if hidden:
            hid = QtWidgets.QLabel(_tr("{n} ocultas por ti").format(n=len(hidden)))
            hid.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
            hid.setToolTip(_tr("Capas ocultas por ti: {n} (no se dibujan ni se reconocen)").format(
                n=len(hidden)) + "\n\n" + "\n".join(hidden))
            head.addWidget(hid, 0)
        self.btn_all = QtWidgets.QToolButton()
        self.btn_all.setText(_tr("Ver todo"))
        self.btn_all.setIcon(icon("mdi:close", color=t.text))
        self.btn_all.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.btn_all.setToolTip(_tr("Quitar el resaltado y ver toda la hoja."))
        self.btn_all.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_all.clicked.connect(self.clear_focus)
        self.btn_all.hide()
        head.addWidget(self.btn_all, 0)
        lay.addLayout(head)

        self.lbl_status = QtWidgets.QLabel()
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        self.set_status(None)

        lst = _LayersList()
        lst.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        lst.viewport().setCursor(QtCore.Qt.PointingHandCursor)
        click_tip = _tr("Clic: verla resaltada en la hoja (otro clic la quita).")
        multi = len(results) > 1
        for r in results:
            u_label = _tr(_UTILITY_LABEL.get(r.utility, r.utility))
            if multi:
                hdr = QtWidgets.QListWidgetItem(swatch_icon(colors[r.utility], 12), u_label)
                bf = hdr.font(); bf.setBold(True); hdr.setFont(bf)
                hdr.setData(FOCUS_ROLE, {"utility": r.utility, "kind": None, "ocg": None, "label": u_label})
                hdr.setToolTip(click_tip)
                lst.addItem(hdr)
            for kind_key, kind in ((rec.utility_line_kind(r.utility), "line"), ("structure", "structure")):
                rows = [x for x in r.ocg_summary if x.get("kind") == kind_key]
                if not rows:
                    continue
                k_label = _tr(_STRUCT_LABEL.get(r.utility, N_("Estructuras")) if kind == "structure"
                              else N_("Líneas"))
                kh = QtWidgets.QListWidgetItem(k_label)
                kh.setForeground(QtGui.QColor(t.text_muted))
                kh.setData(FOCUS_ROLE, {"utility": r.utility, "kind": kind, "ocg": None,
                                        "label": f"{k_label} · {u_label}" if multi else k_label})
                kh.setToolTip(click_tip)
                lst.addItem(kh)
                for x in rows:
                    short = x["ocg"].split("|")[-1] if "|" in x["ocg"] else x["ocg"]
                    tag = "  (AB)" if x.get("abandoned") else ""
                    it = QtWidgets.QListWidgetItem(f"    {short}  ({x.get('path_count', 0)}){tag}")
                    it.setData(FOCUS_ROLE, {"utility": r.utility, "kind": kind, "ocg": x["ocg"], "label": short})
                    it.setToolTip("\n".join((x["ocg"], click_tip)))
                    lst.addItem(it)
        lst.setMinimumHeight(110)
        lst.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        lst.itemClicked.connect(self._on_clicked)
        self.list = lst
        lay.addWidget(lst, 1)

    @property
    def focus(self) -> dict | None:
        return self._focus

    def _on_clicked(self, item):
        target = _focus_of(item)
        if target is None:
            return
        if self._focus is not None and target == self._focus:     # otro clic en la misma: quitar
            self.clear_focus()
            return
        self._focus = target
        self.list.setCurrentItem(item)
        item.setSelected(True)
        self.btn_all.show()
        self.focusChanged.emit(dict(target))

    def clear_focus(self):
        if self._focus is None:
            return
        self._focus = None
        self.list.clearSelection()
        self.btn_all.hide()
        self.set_status(None)
        self.focusChanged.emit(None)

    def set_status(self, text: str | None):
        """Texto bajo el título: la indicación de uso, o qué se está resaltando."""
        t = _theme.tokens()
        if text:
            self.lbl_status.setText(text)
            self.lbl_status.setStyleSheet(f"color:{t.text}; font-size:12px;")
        else:
            self.lbl_status.setText(_tr("Clic en una capa para verla en la hoja."))
            self.lbl_status.setStyleSheet(f"color:{t.text_muted}; font-size:12px;")
