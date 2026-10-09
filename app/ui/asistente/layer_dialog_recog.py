"""layer_dialog_recog.py — Tarjeta «Reconocer» del diálogo «Capas de la hoja».

Qué utilidades se leen del plano: «Todas» + una casilla por utilidad con su color. Solo
se marcan las que la hoja tiene; sin ninguna marcada no se puede continuar.

**Reconocer una utilidad con sus capas ocultas no puede ser** (pedido del usuario
2026-10-07): si una utilidad marcada tiene TODAS sus capas de línea ocultas en «Capas del
plano» (o, sin líneas, las de sus estructuras; `leyenda_estandar.sin_capas_visibles`, con
los mismos roles que el reconocimiento), su casilla lleva un aviso, debajo se dice cuál y
«Continuar» se apaga hasta resolverlo: «Mostrar sus capas» o «No reconocerla».

`RecogCardMixin` de `SheetLayersDialog`: usa `self._layers`, `hidden_names()`,
`set_utility_visible()`, `_layer_items()`, `btn_ok` y `_on_item_changed`.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun.icons import icon as _icon
from hoja import leyenda_estandar as le
from hoja import pdf_layers
from reconocimiento import recognition
from ui.comun import theme as _theme
from ui.comun.ui_common import aci_qcolor, layer_qcolor, swatch_icon

# Etiqueta corta de cada utilidad reconocible (recognition.SUPPORTED_UTILITIES)
# para sus casillas de «Reconocer».
_UTILITY_RECOG_LABEL = dict(recognition.UTILITY_LABELS)

_ROLE_NAME = QtCore.Qt.UserRole            # nombre completo de la capa en el árbol (None en grupos)


def utility_qcolor(key: str) -> QtGui.QColor:
    """Color de una utilidad: el de su capa de salida (igual que en la app);
    «Otras» en gris."""
    if key == pdf_layers.UTILITY_OTHER:
        return aci_qcolor(8)
    return layer_qcolor(key)


def card(title: str) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout, QtWidgets.QHBoxLayout]:
    """Tarjeta con título (y un hueco a la derecha del título para acciones)."""
    t = _theme.tokens()
    box = QtWidgets.QFrame()
    box.setObjectName("layerCard")
    box.setStyleSheet(f"QFrame#layerCard {{ background:{t.surface}; border:1px solid {t.border};"
                      " border-radius:8px; }")
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(8)
    head = QtWidgets.QHBoxLayout(); head.setSpacing(8)
    lbl = QtWidgets.QLabel(title)
    f = lbl.font(); f.setBold(True); f.setPointSize(f.pointSize() + 1); lbl.setFont(f)
    head.addWidget(lbl, 1)
    lay.addLayout(head)
    return box, lay, head


def _label(key: str) -> str:
    return _tr(_UTILITY_RECOG_LABEL.get(key, key))


class RecogCardMixin:
    """Tarjeta «Reconocer» (ver el docstring del módulo)."""

    def _build_recog_card(self, panel: QtWidgets.QVBoxLayout, recognition_utilities=None):
        t = _theme.tokens()
        box, lay, head = card(_tr("Reconocer"))
        self.chk_recog_all = QtWidgets.QCheckBox(_tr("Todas"))
        self.chk_recog_all.setToolTip(_tr("Marcar o desmarcar todas las utilidades que tiene la hoja"))
        self.chk_recog_all.clicked.connect(self._on_recog_all_clicked)
        head.addWidget(self.chk_recog_all)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10); grid.setVerticalSpacing(6)
        self._recog_checks: dict[str, QtWidgets.QCheckBox] = {}
        self._recog_hidden: list[str] = []          # marcadas con todas sus capas ocultas
        selected = recognition.normalize_utilities(recognition_utilities)
        for n, key in enumerate(recognition.SUPPORTED_UTILITIES):
            cb = QtWidgets.QCheckBox(_label(key))
            cb.setIcon(swatch_icon(utility_qcolor(key)))
            cb.setChecked(key in selected)
            cb.toggled.connect(self._on_recog_utility_toggled)
            self._recog_checks[key] = cb
            # 2 columnas: con 3 los nombres se cortaban en un panel estrecho
            grid.addWidget(cb, n // 2, n % 2)
        for c in range(2):
            grid.setColumnStretch(c, 1)
        lay.addLayout(grid)
        self.lbl_recog_warn = QtWidgets.QLabel(_tr("Marca al menos una utilidad para reconocer."))
        self.lbl_recog_warn.setStyleSheet(f"color:{t.danger}; font-weight:bold;")
        self.lbl_recog_warn.hide()
        lay.addWidget(self.lbl_recog_warn)
        self.lbl_recog_hidden = QtWidgets.QLabel()
        self.lbl_recog_hidden.setWordWrap(True)
        self.lbl_recog_hidden.setTextFormat(QtCore.Qt.RichText)
        self.lbl_recog_hidden.setStyleSheet(f"color:{t.danger};")
        self.lbl_recog_hidden.linkActivated.connect(self._on_recog_fix)
        self.lbl_recog_hidden.hide()
        lay.addWidget(self.lbl_recog_hidden)
        panel.addWidget(box)

    def recognition_utilities(self) -> tuple[str, ...]:
        chosen = tuple(key for key in recognition.SUPPORTED_UTILITIES
                       if self._recog_checks[key].isChecked())
        return recognition.normalize_utilities(chosen)

    def _refresh_recog_checks(self):
        """Solo se marcan las utilidades que la hoja tiene; «Todas» refleja el
        conjunto; sin ninguna marcada no se puede continuar."""
        available = {u for layer in self._layers if int(layer.get("path_count") or 0) > 0
                     for u in [layer.get("utility")] + list(layer.get("letter_utilities") or ())}
        for key, cb in self._recog_checks.items():
            has = key in available
            cb.setEnabled(has)
            cb.setToolTip("" if has else _tr("Esta hoja no tiene capas de {u}").format(u=_label(key)))
        self._sync_recog_all()

    def _enabled_recog(self):
        return [cb for cb in self._recog_checks.values() if cb.isEnabled()]

    def _sync_recog_all(self):
        enabled = self._enabled_recog()
        n_on = sum(1 for cb in enabled if cb.isChecked())
        self.chk_recog_all.blockSignals(True)
        self.chk_recog_all.setTristate(0 < n_on < len(enabled))
        self.chk_recog_all.setCheckState(
            QtCore.Qt.Checked if enabled and n_on == len(enabled) else
            QtCore.Qt.PartiallyChecked if n_on else QtCore.Qt.Unchecked)
        self.chk_recog_all.setEnabled(bool(enabled))
        self.chk_recog_all.blockSignals(False)
        ok = n_on > 0 or not enabled          # hoja sin utilidades: se puede seguir (avisa el preview)
        self.lbl_recog_warn.setVisible(not ok)
        hidden = self._check_recog_hidden()
        self.btn_ok.setEnabled(ok and not hidden)

    def _on_recog_all_clicked(self, _checked=False):
        enabled = self._enabled_recog()
        target = not all(cb.isChecked() for cb in enabled)
        for cb in enabled:
            cb.blockSignals(True); cb.setChecked(target); cb.blockSignals(False)
        self._sync_recog_all()

    def _on_recog_utility_toggled(self, _on: bool):
        self._sync_recog_all()

    # ── utilidades marcadas con sus capas ocultas ──
    def _check_recog_hidden(self) -> list[str]:
        """Marca (casilla con aviso + frase con arreglos) las utilidades que se reconocerían
        sin ninguna capa visible; las devuelve."""
        chosen = [k for k, cb in self._recog_checks.items() if cb.isChecked() and cb.isEnabled()]
        bad = le.sin_capas_visibles(self._layers, self.hidden_names(), chosen)
        self._recog_hidden = bad
        danger = QtGui.QColor(_theme.tokens().danger)
        for key, cb in self._recog_checks.items():
            if key in bad:
                cb.setIcon(_icon("mdi:alert-outline", color=danger.name()))
                cb.setToolTip(_tr("Sus capas están ocultas en «Capas del plano»: no se reconocería nada."))
            else:
                cb.setIcon(swatch_icon(utility_qcolor(key)))
                if cb.isEnabled():
                    cb.setToolTip("")
        if bad:
            what = " · ".join(_label(k) for k in bad)
            msg = (_tr("{u}: sus capas están ocultas, no se reconocería nada.") if len(bad) == 1 else
                   _tr("{u}: sus capas están ocultas, no se reconocería nada de ellas.")).format(u=what)
            css = f"color:{_theme.tokens().accent}; font-weight:bold"     # como los enlaces del compositor
            links = "<a href='show' style='{c}'>{a}</a> · <a href='skip' style='{c}'>{b}</a>".format(
                c=css, a=_tr("Mostrar sus capas"),
                b=_tr("No reconocerlas") if len(bad) > 1 else _tr("No reconocerla"))
            self.lbl_recog_hidden.setText(f"<b>{msg}</b><br>{links}")
        self.lbl_recog_hidden.setVisible(bool(bad))
        return bad

    def _on_recog_fix(self, link: str):
        bad = list(self._recog_hidden)
        if link == "skip":
            for key in bad:
                cb = self._recog_checks[key]
                cb.blockSignals(True); cb.setChecked(False); cb.blockSignals(False)
            self._sync_recog_all()
            return
        # «Mostrar sus capas»: su grupo entero (lo que hace su casilla en el árbol) y, por
        # si alguna está en otro grupo, cada capa que el reconocimiento toma
        for key in bad:
            self.set_utility_visible(key, True)
        want = set()
        for key in bad:
            lineas, estructuras = le.capas_que_reconoce(self._layers, key)
            want |= set(lineas or estructuras)
        for it in self._layer_items():
            if it.data(0, _ROLE_NAME) in want and it.checkState(0) != QtCore.Qt.Checked:
                it.setCheckState(0, QtCore.Qt.Checked)
        self._sync_recog_all()
