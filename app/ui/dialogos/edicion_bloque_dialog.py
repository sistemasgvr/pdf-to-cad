"""Ventana «Editar en bloque» / «Pegar propiedades» (varias utilidades del mismo tipo).

Cada campo arranca en «(sin cambios)»: solo se escribe lo que el usuario elige. Al
pegar propiedades arranca con los valores de la utilidad copiada (se puede dejar
cualquiera en «(sin cambios)»). La escritura la hace `nucleo.edicion_bloque.aplicar`.
"""
from __future__ import annotations

from PySide6 import QtWidgets

from nucleo import model_ops
from traduccion.i18n import t as _tr

SIN = "__sin_cambios__"      # dato del ítem «(sin cambios)»


def _combo():
    cb = QtWidgets.QComboBox()
    cb.setMinimumHeight(34)
    cb.setMinimumWidth(260)
    return cb


def _elegir(cb, dato):
    i = cb.findData(dato)
    if i >= 0:
        cb.setCurrentIndex(i)


class EdicionBloqueDialog(QtWidgets.QDialog):
    """`familias` = [(id, texto)] del catálogo de Civil 3D (vacía sin catálogo),
    `tamanos_de(fid)` = tamaños de esa familia, `familia_comun` = la familia que
    comparten todas (None si son distintas), `materiales`/`tipos_red` = [(texto, dato)]
    como en el panel de propiedades, `inicial` = valores a pegar (o None) y `datos` =
    campos del usuario que se pueden pegar."""

    def __init__(self, parent, titulo, n, tipo, familias, tamanos_de, familia_comun,
                 materiales, tipos_red, inicial=None, datos=None, con_bancoducto=0, saltadas=0,
                 tipos=(), con_amperaje=False):
        super().__init__(parent)
        self.tamanos_de = tamanos_de
        self.familia_comun = familia_comun
        self.datos = dict(datos or {})
        self.setWindowTitle(titulo)
        self.setMinimumWidth(560)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(12)

        tit = QtWidgets.QLabel(_tr("{n} utilidades de tipo «{tipo}»").format(n=n, tipo=tipo))
        f = tit.font(); f.setPointSizeF(f.pointSizeF() * 1.2); f.setBold(True); tit.setFont(f)
        tit.setWordWrap(True)
        lay.addWidget(tit)
        ayuda = QtWidgets.QLabel(_tr("Solo cambia lo que elijas; lo que quede en «(sin cambios)» se respeta "
                                     "en cada utilidad. Se puede deshacer con Ctrl+Z."))
        ayuda.setWordWrap(True); ayuda.setProperty("muted", True)
        lay.addWidget(ayuda)

        caja = QtWidgets.QGroupBox(_tr("Propiedades"))
        form = QtWidgets.QFormLayout(caja)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.cmb_familia = _combo()
        self.cmb_familia.setAccessibleName(_tr("Familia"))
        self.cmb_familia.addItem(_tr("(sin cambios)"), SIN)
        if familias:
            self.cmb_familia.addItem(_tr("(por defecto)"), "")
            for fid, texto in familias:
                self.cmb_familia.addItem(texto, fid)
        else:
            self.cmb_familia.setEnabled(False)
            self.cmb_familia.setToolTip(_tr("Sin catálogo de Civil 3D: elige la versión en la barra superior."))
        form.addRow(_tr("Familia:"), self.cmb_familia)
        self.cmb_tamano = _combo()
        self.cmb_tamano.setAccessibleName(_tr("Tamaño (diámetro)"))
        form.addRow(_tr("Tamaño (diámetro):"), self.cmb_tamano)
        self.cmb_red = _combo()
        self.cmb_red.setAccessibleName(_tr("Tipo de tubería"))
        self.cmb_red.addItem(_tr("(sin cambios)"), SIN)
        for texto, dato in tipos_red:
            self.cmb_red.addItem(texto, dato)
        form.addRow(_tr("Tipo de tubería:"), self.cmb_red)
        self.cmb_material = _combo()
        self.cmb_material.setAccessibleName(_tr("Material"))
        self.cmb_material.addItem(_tr("(sin cambios)"), SIN)
        for texto, dato in materiales:
            self.cmb_material.addItem(texto, dato)
        form.addRow(_tr("Material:"), self.cmb_material)
        self.cmb_estado = _combo()
        self.cmb_estado.setAccessibleName(_tr("Estado"))
        self.cmb_estado.addItem(_tr("(sin cambios)"), SIN)
        self.cmb_estado.addItem(_tr("Activa"), False)
        self.cmb_estado.addItem(_tr("Abandonada (AB)"), True)
        form.addRow(_tr("Estado:"), self.cmb_estado)
        # Tipo (normativas) y amperaje (solo eléctrico).
        self.cmb_tipo = _combo()
        self.cmb_tipo.setAccessibleName(_tr("Tipo"))
        self.cmb_tipo.addItem(_tr("(sin cambios)"), SIN)
        self.cmb_tipo.addItem(_tr("(sin tipo)"), "")
        for tp in tipos:
            self.cmb_tipo.addItem(tp, tp)
        form.addRow(_tr("Tipo:"), self.cmb_tipo)
        self.spn_amp = None
        if con_amperaje:
            self.spn_amp = QtWidgets.QDoubleSpinBox()
            self.spn_amp.setRange(-1.0, 100000.0); self.spn_amp.setDecimals(1); self.spn_amp.setSuffix(" A")
            self.spn_amp.setSpecialValueText(_tr("(sin cambios)")); self.spn_amp.setValue(-1.0)
            self.spn_amp.setMinimumHeight(34)
            self.spn_amp.setToolTip(_tr("0 = sin dato."))
            form.addRow(_tr("Amperaje:"), self.spn_amp)
        lay.addWidget(caja)

        self.chk_datos = None
        if self.datos:
            self.chk_datos = QtWidgets.QCheckBox(_tr("Pegar también los datos extendidos del usuario ({n})").format(
                n=len(self.datos)))
            self.chk_datos.setChecked(True)
            self.chk_datos.setToolTip("\n".join(f"{k}: {v}" for k, v in list(self.datos.items())[:12]))
            lay.addWidget(self.chk_datos)

        self.lbl_nota = QtWidgets.QLabel()
        self.lbl_nota.setWordWrap(True); self.lbl_nota.setProperty("muted", True)
        lay.addWidget(self.lbl_nota)
        notas = []
        if con_bancoducto:
            notas.append(_tr("Con bancoducto ({k}): su familia y tamaño no cambian (los define el bancoducto).").format(
                k=con_bancoducto))
        if saltadas:
            notas.append(_tr("Las de otro tipo ({k}) no se tocan.").format(k=saltadas))
        self._notas = notas

        bb = QtWidgets.QDialogButtonBox()
        self.btn_ok = bb.addButton(_tr("Aplicar a {n} utilidades").format(n=n), QtWidgets.QDialogButtonBox.AcceptRole)
        self.btn_ok.setDefault(True); self.btn_ok.setMinimumHeight(36)
        c = bb.addButton(_tr("Cancelar"), QtWidgets.QDialogButtonBox.RejectRole)
        c.setMinimumHeight(36); c.setProperty("secondary", True)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.cmb_familia.currentIndexChanged.connect(self._llenar_tamanos)
        if inicial:
            if familias:
                _elegir(self.cmb_familia, inicial.get("familia", ""))
            _elegir(self.cmb_red, inicial.get("net_type", ""))
            _elegir(self.cmb_material, inicial.get("material", ""))
            _elegir(self.cmb_estado, bool(inicial.get("ab")))
            if "tipo" in inicial:
                if self.cmb_tipo.findData(inicial["tipo"] or "") < 0:
                    self.cmb_tipo.addItem(inicial["tipo"], inicial["tipo"])
                _elegir(self.cmb_tipo, inicial["tipo"] or "")
            if self.spn_amp is not None and inicial.get("amperaje") is not None:
                self.spn_amp.setValue(float(inicial["amperaje"]))
        self._llenar_tamanos()
        if inicial and self.cmb_tamano.isEnabled():
            _elegir(self.cmb_tamano, inicial.get("tamano", ""))

    def _llenar_tamanos(self, *_):
        """Los tamaños dependen de la familia: con la familia «(sin cambios)» solo si
        todas comparten una; al cambiar de familia el tamaño arranca por defecto."""
        fam = self.cmb_familia.currentData()
        cb = self.cmb_tamano
        cb.clear()
        defecto = _tr("{d} (Por defecto)").format(d=f'{model_ops.DIAM_DEFECTO_IN:g}"')
        nota = ""
        if fam == SIN:
            fid = self.familia_comun
            if fid:
                cb.addItem(_tr("(sin cambios)"), SIN)
                cb.addItem(defecto, "")
                for sz in self.tamanos_de(fid):
                    cb.addItem(sz, sz)
            else:
                cb.addItem(_tr("(sin cambios)"), SIN)
                if fid is None:
                    nota = _tr("Tienen familias distintas: elige una familia para cambiar el tamaño.")
        elif fam:
            cb.addItem(defecto, "")
            for sz in self.tamanos_de(fam):
                cb.addItem(sz, sz)
        else:
            cb.addItem(defecto, "")
        cb.setEnabled(cb.count() > 1)
        self.lbl_nota.setText("\n".join([n for n in [nota] + self._notas if n]))
        self.lbl_nota.setVisible(bool(self.lbl_nota.text()))

    def cambios(self):
        """{campo: valor} solo con lo que cambia (formato de edicion_bloque.aplicar)."""
        out = {}
        fam = self.cmb_familia.currentData()
        tam = self.cmb_tamano.currentData()
        if fam != SIN:
            out["familia"] = fam or ""
            out["tamano"] = tam if tam not in (None, SIN) else ""
        elif tam not in (None, SIN) and self.cmb_tamano.isEnabled():
            out["tamano"] = tam
        for clave, cb in (("net_type", self.cmb_red), ("material", self.cmb_material), ("ab", self.cmb_estado),
                          ("tipo", self.cmb_tipo)):
            if cb.currentData() != SIN:
                out[clave] = cb.currentData()
        if self.spn_amp is not None and self.spn_amp.value() >= 0:
            out["amperaje"] = self.spn_amp.value() or None
        if self.chk_datos is not None and self.chk_datos.isChecked():
            out["datos"] = dict(self.datos)
        return out
