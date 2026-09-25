"""Diálogo «Nuevo lienzo»: crear un proyecto en blanco, sin PDF de fondo.

Hasta ahora la app exigía abrir un PDF de plano para empezar. Este diálogo
permite dibujar sobre una hoja vacía, eligiendo su tamaño físico (presets ISO /
norteamericanos, o medidas a mano en mm o pulgadas) y la ESCALA del plano.

La escala es imprescindible: con un PDF se detecta del titleblock
(`vector_pipeline.detect_scale`), pero en una hoja en blanco no hay de dónde
leerla, y sin ella el DXF saldría con dimensiones arbitrarias. Se pide en
escalas de ingeniería imperiales (1" = X pies), que es la notación de los planos
del proyecto.

Devuelve un dict con la hoja ya resuelta a PUNTOS PDF (72 pt = 1 in), que es la
unidad en la que trabaja la transformación a coordenadas CAD.
"""
from PySide6 import QtWidgets, QtCore

from i18n import t as _tr, N_

# Tamaños de hoja en MILÍMETROS (nombre, ancho, alto) en vertical.
HOJAS_ISO = [
    ("A4", 210.0, 297.0),
    ("A3", 297.0, 420.0),
    ("A2", 420.0, 594.0),
    ("A1", 594.0, 841.0),
    ("A0", 841.0, 1189.0),
]
# Tamaños en PULGADAS.
HOJAS_US = [
    (N_("Carta (Letter)"), 8.5, 11.0),
    (N_("Oficio (Legal)"), 8.5, 14.0),
    (N_("Tabloide (Ledger)"), 11.0, 17.0),
    ("ANSI A", 8.5, 11.0),
    ("ANSI B", 11.0, 17.0),
    ("ANSI C", 17.0, 22.0),
    ("ANSI D", 22.0, 34.0),
    ("ANSI E", 34.0, 44.0),
    ("ARCH C", 18.0, 24.0),
    ("ARCH D", 24.0, 36.0),
    ("ARCH E", 36.0, 48.0),
]
# Escalas de ingeniería imperiales: 1 pulgada del plano = X pies reales. Son
# las que usan los planos de redes de utilidad del proyecto.
ESCALAS_ING = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 100.0, 200.0]

MM_POR_PULGADA = 25.4
PT_POR_PULGADA = 72.0


def _a_puntos(valor, unidad):
    """Convierte una medida de hoja a puntos PDF (la unidad de `W`/`H`)."""
    if unidad == "mm":
        return valor / MM_POR_PULGADA * PT_POR_PULGADA
    return valor * PT_POR_PULGADA


def choose_canvas(parent, escala_actual=20.0):
    """Pide tamaño de hoja y escala. Devuelve dict o None si se cancela.

    dict: {name, w_pt, h_pt, scale_ft_per_pt, ft_per_inch, unit, landscape}
    """
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(_tr("Nuevo lienzo"))
    dlg.setModal(True)
    lay = QtWidgets.QVBoxLayout(dlg)

    # ── Tamaño de hoja ──────────────────────────────────────────────────
    gb_hoja = QtWidgets.QGroupBox(_tr("Tamaño de hoja"))
    fl = QtWidgets.QFormLayout(gb_hoja)

    cmb = QtWidgets.QComboBox()
    for nombre, an, al in HOJAS_ISO:
        cmb.addItem(_tr(nombre) + f"  ({an:g} × {al:g} mm)", ("mm", an, al, nombre))
    for nombre, an, al in HOJAS_US:
        cmb.addItem(_tr(nombre) + f"  ({an:g} × {al:g} in)", ("in", an, al, nombre))
    cmb.addItem(_tr("Personalizado…"), None)
    cmb.setCurrentIndex(1)                       # A3 por defecto
    fl.addRow(_tr("Formato:"), cmb)

    # Medidas a mano: se habilitan solo en "Personalizado".
    cmb_unidad = QtWidgets.QComboBox()
    cmb_unidad.addItem(_tr("milímetros (mm)"), _tr("mm"))
    cmb_unidad.addItem(_tr("pulgadas (in)"), _tr("in"))
    fl.addRow(_tr("Unidad:"), cmb_unidad)

    spn_an = QtWidgets.QDoubleSpinBox()
    spn_an.setRange(1.0, 100000.0); spn_an.setDecimals(2); spn_an.setValue(297.0)
    spn_al = QtWidgets.QDoubleSpinBox()
    spn_al.setRange(1.0, 100000.0); spn_al.setDecimals(2); spn_al.setValue(420.0)
    fl.addRow(_tr("Ancho:"), spn_an)
    fl.addRow(_tr("Alto:"), spn_al)

    rb_vert = QtWidgets.QRadioButton(_tr("Vertical"))
    rb_horiz = QtWidgets.QRadioButton(_tr("Horizontal"))
    rb_horiz.setChecked(True)                    # los planos suelen ir apaisados
    hb_or = QtWidgets.QHBoxLayout()
    hb_or.addWidget(rb_vert); hb_or.addWidget(rb_horiz); hb_or.addStretch(1)
    fl.addRow(_tr("Orientación:"), hb_or)
    lay.addWidget(gb_hoja)

    # ── Escala del plano ────────────────────────────────────────────────
    gb_esc = QtWidgets.QGroupBox(_tr("Escala del plano"))
    fe = QtWidgets.QFormLayout(gb_esc)
    cmb_esc = QtWidgets.QComboBox()
    for ft in ESCALAS_ING:
        cmb_esc.addItem(f"1\" = {ft:g}'", ft)
    cmb_esc.addItem(_tr("Personalizada…"), None)
    # Preselecciona la escala actual del proyecto si coincide con un preset.
    idx_esc = next((i for i, ft in enumerate(ESCALAS_ING)
                    if abs(ft - escala_actual) < 1e-6), 1)
    cmb_esc.setCurrentIndex(idx_esc)
    fe.addRow(_tr("Escala:"), cmb_esc)

    spn_esc = QtWidgets.QDoubleSpinBox()
    spn_esc.setRange(0.01, 100000.0); spn_esc.setDecimals(2)
    spn_esc.setValue(float(escala_actual) if escala_actual else 20.0)
    spn_esc.setSuffix(" " + _tr("pies por pulgada"))
    fe.addRow(_tr("Valor:"), spn_esc)

    lbl_cobertura = QtWidgets.QLabel()
    lbl_cobertura.setWordWrap(True)
    fe.addRow(_tr("Cubre:"), lbl_cobertura)
    lay.addWidget(gb_esc)

    # ── Lógica de habilitado y previsualización ─────────────────────────
    def _medidas():
        """(ancho_pt, alto_pt, nombre) según el estado actual del diálogo."""
        datos = cmb.currentData()
        if datos is None:                        # personalizado
            unidad = cmb_unidad.currentData()
            an = _a_puntos(spn_an.value(), unidad)
            al = _a_puntos(spn_al.value(), unidad)
            nombre = "Personalizado"          # clave neutra: se guarda en el .digproj
        else:
            unidad, an_u, al_u, nombre = datos
            an = _a_puntos(an_u, unidad)
            al = _a_puntos(al_u, unidad)
        if rb_horiz.isChecked():
            an, al = max(an, al), min(an, al)
        else:
            an, al = min(an, al), max(an, al)
        return an, al, nombre

    def _ft_por_pulgada():
        d = cmb_esc.currentData()
        return float(d) if d is not None else float(spn_esc.value())

    def _actualizar():
        es_custom = cmb.currentData() is None
        spn_an.setEnabled(es_custom)
        spn_al.setEnabled(es_custom)
        cmb_unidad.setEnabled(es_custom)
        spn_esc.setEnabled(cmb_esc.currentData() is None)
        # Cuánto terreno real abarca la hoja: es la comprobación de sensatez
        # que evita elegir una escala con la que no cabe el proyecto.
        an_pt, al_pt, _ = _medidas()
        ftpp = _ft_por_pulgada() / PT_POR_PULGADA
        lbl_cobertura.setText(
            _tr("{w:,.0f} × {h:,.0f} pies reales").format(
                w=an_pt * ftpp, h=al_pt * ftpp))

    for w in (cmb, cmb_unidad, cmb_esc):
        w.currentIndexChanged.connect(_actualizar)
    for w in (spn_an, spn_al, spn_esc):
        w.valueChanged.connect(_actualizar)
    rb_vert.toggled.connect(_actualizar)
    _actualizar()

    btns = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    btns.button(QtWidgets.QDialogButtonBox.Ok).setText(_tr("Crear"))
    btns.button(QtWidgets.QDialogButtonBox.Cancel).setText(_tr("Cancelar"))
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None

    an_pt, al_pt, nombre = _medidas()
    ft_in = _ft_por_pulgada()
    return {
        "name": nombre,
        "w_pt": an_pt,
        "h_pt": al_pt,
        "ft_per_inch": ft_in,
        # La escala interna de la app es pies por PUNTO (72 pt = 1 in).
        "scale_ft_per_pt": ft_in / PT_POR_PULGADA,
        "unit": cmb_unidad.currentData(),
        "landscape": rb_horiz.isChecked(),
    }
