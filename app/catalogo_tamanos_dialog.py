"""Ventana «Agregar tamaño» (botón verde «+» junto a cada desplegable de tamaño).

Pide las medidas del tamaño nuevo (diámetro, o ancho × alto/largo), muestra los
datos que se calculan solos (grosor de pared, diámetro exterior… editables) y
las instalaciones de Civil 3D donde se escribirá (todas las ≥ 2025, en cada
idioma). La escritura la hace `catalogo_tamanos.agregar`."""
from __future__ import annotations

from PySide6 import QtWidgets

import catalogo_tamanos as T
from i18n import t as _tr


def _spin(unidad, valor=None, minimo=0.01):
    sp = QtWidgets.QDoubleSpinBox()
    sp.setRange(minimo, 10000.0)
    sp.setDecimals(4 if unidad == "in" else 3)
    sp.setSuffix(" " + unidad)                         # in / ft: como en los desplegables de tamaño
    sp.setMinimumWidth(150)
    sp.setMinimumHeight(34)
    if valor is not None:
        sp.setValue(float(valor))
    return sp


class AgregarTamanoDialog(QtWidgets.QDialog):
    def __init__(self, parent, kind, fid, familia, year, lang):
        super().__init__(parent)
        self.kind, self.fid, self.year, self.lang = kind, fid, year, lang
        self.formato = T.formato(kind, fid, year, lang)
        self.resultado_texto = ""                      # tamaño agregado (para elegirlo en la lista)
        self._tocados = set()
        self.setWindowTitle(_tr("Agregar tamaño"))
        self.setMinimumWidth(520)
        lay = QtWidgets.QVBoxLayout(self); lay.setSpacing(12)

        tit = QtWidgets.QLabel(_tr("Agregar un tamaño a «{f}»").format(f=familia))
        f = tit.font(); f.setPointSizeF(f.pointSizeF() * 1.25); f.setBold(True); tit.setFont(f)
        tit.setWordWrap(True)
        lay.addWidget(tit)
        if self.formato and self.formato.existentes:
            muestra = ", ".join(self.formato.existentes[:14]) + (" …" if len(self.formato.existentes) > 14 else "")
            ex = QtWidgets.QLabel(_tr("Tamaños actuales: {lista}").format(lista=muestra))
            ex.setWordWrap(True); ex.setProperty("muted", True)
            lay.addWidget(ex)

        # Medidas que pide el usuario.
        caja = QtWidgets.QGroupBox(_tr("Medidas del tamaño nuevo")); form = QtWidgets.QFormLayout(caja)
        self.ejes = {}
        for e in self.formato.ejes:
            sp = _spin(e.unidad)
            sp.setAccessibleName(e.etiqueta)
            sp.valueChanged.connect(self._recalcular)
            form.addRow(e.etiqueta + ":", sp)
            self.ejes[e.clave] = sp
        lay.addWidget(caja)
        if self.formato.modo == "listas" and len(self.formato.ejes) == 2:
            nota = QtWidgets.QLabel(_tr("En esta familia las dos medidas se combinan con las que ya existen: "
                                        "el valor nuevo de cada una se podrá usar con todas las de la otra."))
            nota.setWordWrap(True); nota.setProperty("muted", True)
            lay.addWidget(nota)

        # Datos calculados (editables).
        self.extras = {}
        if self.formato.extras:
            cx = QtWidgets.QGroupBox(_tr("Otros datos (calculados de los tamaños vecinos; puedes corregirlos)"))
            fx = QtWidgets.QFormLayout(cx)
            for e in self.formato.extras:
                sp = _spin(e.unidad, minimo=0.0)
                sp.setAccessibleName(e.etiqueta)
                sp.valueChanged.connect(lambda _v, c=e.clave: self._tocados.add(c))
                fx.addRow(e.etiqueta + ":", sp)
                self.extras[e.clave] = sp
            lay.addWidget(cx)

        # Dónde se escribe.
        cd = QtWidgets.QGroupBox(_tr("Agregar en")); vd = QtWidgets.QVBoxLayout(cd)
        self.destinos = []
        for y, lg in T.instalaciones():
            ch = QtWidgets.QCheckBox(T.nombre_instalacion(y, lg))
            hay = T.ubicar(kind, fid, y, lg) is not None
            ch.setChecked(hay); ch.setEnabled(hay)
            if not hay:
                ch.setText(ch.text() + "  " + _tr("(no tiene esta familia)"))
            vd.addWidget(ch)
            self.destinos.append(((y, lg), ch))
        lay.addWidget(cd)
        aviso = QtWidgets.QLabel(
            _tr("Si Civil 3D está abierto y el catálogo de presión no se puede escribir, ciérralo y vuelve a intentarlo.")
            if kind == "pressure" else
            _tr("Civil 3D regenera su catálogo solo la próxima vez que importes la red (o con el comando PREPARAR_FAMILIAS)."))
        aviso.setWordWrap(True); aviso.setProperty("muted", True)
        lay.addWidget(aviso)

        bb = QtWidgets.QDialogButtonBox()
        self.btn_ok = bb.addButton(_tr("Agregar tamaño"), QtWidgets.QDialogButtonBox.AcceptRole)
        self.btn_ok.setDefault(True); self.btn_ok.setMinimumHeight(36)
        bb.addButton(_tr("Cancelar"), QtWidgets.QDialogButtonBox.RejectRole).setMinimumHeight(36)
        bb.accepted.connect(self._agregar); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._recalcular()
        next(iter(self.ejes.values())).setFocus()

    def valores(self):
        return {k: sp.value() for k, sp in self.ejes.items()}

    def _recalcular(self, *_):
        if not self.extras:
            return
        try:
            prop = T.proponer(self.kind, self.fid, self.year, self.lang, self.valores())
        except (OSError, ValueError, KeyError):
            prop = {}
        for k, sp in self.extras.items():
            if k in self._tocados or prop.get(k) is None:
                continue
            sp.blockSignals(True); sp.setValue(float(prop[k])); sp.blockSignals(False)

    def _agregar(self):
        destinos = [d for d, ch in self.destinos if ch.isChecked()]
        if not destinos:
            QtWidgets.QMessageBox.information(self, _tr("Agregar tamaño"), _tr("Marca al menos una instalación de Civil 3D."))
            return
        extras = {k: sp.value() for k, sp in self.extras.items()} or None
        res = T.agregar(self.kind, self.fid, self.valores(), destinos, extras)
        estados = {"agregado": _tr("agregado"), "ya_existia": _tr("ya existía"),
                   "sin_familia": _tr("no tiene esta familia"), "error": _tr("error")}
        lineas = [f"• {T.nombre_instalacion(r.year, r.lang)}: {estados.get(r.estado, r.estado)}"
                  + (f" — {r.mensaje}" if r.mensaje else "") for r in res]
        ok = [r for r in res if r.estado in ("agregado", "ya_existia")]
        if not ok:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar tamaño"), _tr("No se pudo agregar el tamaño:") + "\n\n" + "\n".join(lineas))
            return
        self.resultado_texto = T.texto_tamano(self.kind, self.fid, self.valores(), self.year, self.lang)
        caja = QtWidgets.QMessageBox.information if len(ok) == len(res) else QtWidgets.QMessageBox.warning
        caja(self, _tr("Agregar tamaño"),
             _tr("Tamaño {s}:").format(s=self.resultado_texto) + "\n\n" + "\n".join(lineas))
        self.accept()


def abrir(parent, kind, fid, familia, year, lang):
    """Abre la ventana; devuelve el texto del tamaño agregado ('' si se canceló o
    la familia no admite tamaños nuevos)."""
    if not T.formato(kind, fid, year, lang):
        QtWidgets.QMessageBox.information(parent, _tr("Agregar tamaño"),
                                          _tr("Esta familia no tiene una tabla de tamaños que la app pueda ampliar."))
        return ""
    dlg = AgregarTamanoDialog(parent, kind, fid, familia, year, lang)
    return dlg.resultado_texto if dlg.exec() == QtWidgets.QDialog.Accepted else ""

