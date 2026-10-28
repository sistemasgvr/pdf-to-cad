"""2.0.0 — pie de la vista previa (prototipo «faltante»): «Tramos unidos | Tramos sueltos» como segmentado.

Refleja el `chk_routes` de siempre en los dos sentidos (el dato y la lógica siguen en él)."""
from PySide6 import QtWidgets

from traduccion.i18n import t as _tr


def segmentado_tramos(chk_routes):
    f = QtWidgets.QFrame()
    f.setObjectName("segmentado")
    lay = QtWidgets.QHBoxLayout(f)
    lay.setContentsMargins(3, 3, 3, 3)
    lay.setSpacing(2)
    grupo = QtWidgets.QButtonGroup(f)
    unidos = QtWidgets.QPushButton(_tr("Tramos unidos"))
    sueltos = QtWidgets.QPushButton(_tr("Tramos sueltos"))
    for b in (unidos, sueltos):
        b.setProperty("kind", "seg")
        b.setCheckable(True)
        b.setAutoDefault(False)
        b.setToolTip(chk_routes.toolTip())
        grupo.addButton(b)
        lay.addWidget(b)
    unidos.setChecked(chk_routes.isChecked())
    sueltos.setChecked(not chk_routes.isChecked())
    unidos.toggled.connect(lambda on: chk_routes.isChecked() != on and chk_routes.setChecked(on))
    chk_routes.toggled.connect(lambda on: (unidos if on else sueltos).setChecked(True))
    f.unidos, f.sueltos = unidos, sueltos
    return f
