"""Diálogo «Importar superficies» (2026-11-11, versión 2.1.0; diseño: una tarjeta por superficie, una sola
acción principal).

Cada tarjeta: casilla «importar», nombre editable, formato, cifras, unidad, sistema de coordenadas del archivo
(EPSG o código CS-MAP de Civil 3D, ver `nucleo.sistemas_cs`; vacío = el del proyecto) y un estado: Lista (verde), Aviso (ámbar: se importa pero no se verá sobre el
plano) o Error (rojo: no se puede importar, con el motivo). El botón principal dice cuántas se importan.

No lee archivos ni toca la ventana: recibe los candidatos ya leídos (`Candidato`) y devuelve los elegidos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from PySide6 import QtCore, QtWidgets

from nucleo import sistemas_cs
from nucleo import superficies as S
from traduccion.i18n import t as _tr
from ui.comun import ia_estilo, theme

LISTA, AVISO, ERROR = "lista", "aviso", "error"


@dataclass
class Candidato:
    archivo: str                       # nombre del archivo (para mostrar)
    sha: str = ""
    indice: int = 0
    sup: Optional[object] = None       # superficies_leer.Superficie, o None si no se pudo leer
    error: str = ""
    nombre: str = ""                   # lo que el usuario deja (editable)
    crs: str = ""                      # «EPSG:n» del archivo (o el elegido)
    elegido: bool = True
    avisos: List[str] = field(default_factory=list)


def _unidad_txt(u):
    return {"meter": _tr("metros"), "foot": _tr("pies"), "USSurveyFoot": _tr("pies US")}.get(u, u)


def _miles(n):
    return f"{int(n):,}".replace(",", " ")


def validar_crs(texto) -> tuple:
    """(«EPSG:n» o "", error). Acepta número EPSG, código de Civil 3D (CS-MAP) o lo que entienda pyproj."""
    crs, err, _desc = sistemas_cs.resolver(texto)
    return crs, err


class _Tarjeta(QtWidgets.QFrame):
    cambio = QtCore.Signal()

    def __init__(self, cand: Candidato, crs_proyecto: str, georef: bool, parent=None):
        super().__init__(parent)
        self.cand, self.crs_proyecto, self.georef = cand, crs_proyecto, georef
        self.setObjectName("tarjetaSup")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        fila = QtWidgets.QHBoxLayout()
        self.chk = QtWidgets.QCheckBox()
        self.chk.setChecked(cand.sup is not None and cand.elegido)
        self.chk.setEnabled(cand.sup is not None)
        self.chk.setAccessibleName(_tr("Importar esta superficie"))
        self.chk.toggled.connect(self._al_cambiar)
        fila.addWidget(self.chk)
        self.nombre = QtWidgets.QLineEdit(cand.nombre or (cand.sup.nombre if cand.sup else cand.archivo))
        self.nombre.setAccessibleName(_tr("Nombre de la superficie"))
        self.nombre.setEnabled(cand.sup is not None)
        self.nombre.textChanged.connect(self._al_cambiar)
        fila.addWidget(self.nombre, 1)
        self.estado = QtWidgets.QLabel()
        self.estado.setObjectName("chipEstado")
        fila.addWidget(self.estado)
        v.addLayout(fila)
        self.detalle = QtWidgets.QLabel()
        self.detalle.setProperty("rol", "t3")
        self.detalle.setWordWrap(True)
        v.addWidget(self.detalle)
        self.fila_crs = QtWidgets.QWidget()
        self.fila_crs.setObjectName("filaCrs")
        self.fila_crs.setStyleSheet("#filaCrs { background: transparent; }")
        h = QtWidgets.QHBoxLayout(self.fila_crs)
        h.setContentsMargins(0, 0, 0, 0)
        lbl = QtWidgets.QLabel(_tr("Sistema del archivo:"))
        h.addWidget(lbl)
        self.crs = QtWidgets.QLineEdit((cand.crs or "").removeprefix("EPSG:"))
        self.crs.setToolTip(_tr("Número EPSG (32717) o código de Civil 3D (UTM84-17S, CA83-VF…). Vacío = el del "
                                "proyecto."))
        self.crs.setPlaceholderText(_tr("EPSG o código de Civil 3D"))
        self.crs.setMinimumWidth(200)
        self.crs.setMaximumWidth(220)
        self.crs.setAccessibleName(_tr("Sistema de coordenadas del archivo: EPSG o código de Civil 3D"))
        self.crs.textChanged.connect(self._al_cambiar)
        lbl.setBuddy(self.crs)
        h.addWidget(self.crs)
        self.crs_desc = QtWidgets.QLabel()
        self.crs_desc.setProperty("rol", "t3")
        self.crs_desc.setStyleSheet("background: transparent;")
        h.addWidget(self.crs_desc, 1)
        self.fila_crs.setVisible(cand.sup is not None)
        v.addWidget(self.fila_crs)
        self.motivo = QtWidgets.QLabel()
        self.motivo.setWordWrap(True)
        v.addWidget(self.motivo)
        theme.al_tema(self, lambda _n=None: self._pintar())
        self._al_cambiar()

    def estado_actual(self) -> tuple:
        """(estado, texto del motivo)."""
        c = self.cand
        if c.sup is None:
            return ERROR, c.error
        if not self.nombre.text().strip():
            return ERROR, _tr("Escribe un nombre.")
        _crs, err, desc = sistemas_cs.resolver(self.crs.text())
        self.crs_desc.setText(desc)
        self.crs_desc.setToolTip(desc)
        if err:
            return ERROR, err
        if not self.georef:
            return AVISO, _tr("El plano no está georreferenciado: no se verá sobre él, pero viaja a Civil 3D con "
                              "sus coordenadas.")
        if not (self.crs.text().strip() or self.crs_proyecto):
            return AVISO, _tr("Sin sistema de coordenadas: se toma como el del proyecto.")
        return LISTA, ""

    def importa(self) -> bool:
        return self.chk.isChecked() and self.estado_actual()[0] != ERROR

    def _al_cambiar(self, *_a):
        c = self.cand
        if c.sup is not None:
            fmt = c.sup.formato
            self.detalle.setText(_tr("{fmt} · {p} puntos · {t} triángulos · {u} · {arch}").format(
                fmt=fmt, p=_miles(len(c.sup.puntos)), t=_miles(len(c.sup.triangulos)), u=_unidad_txt(c.sup.unidad),
                arch=c.archivo))
        else:
            self.detalle.setText(c.archivo)
        self._pintar()
        self.cambio.emit()

    def _pintar(self):
        tk = theme.tokens()
        est, motivo = self.estado_actual()
        color, fondo, texto = {LISTA: (tk.success, tk.success_soft, _tr("Lista")),
                               AVISO: (tk.warning, tk.warning_soft, _tr("Aviso")),
                               ERROR: (tk.danger, tk.danger_soft, _tr("Error"))}[est]
        self.estado.setText(texto)
        self.estado.setAccessibleName(_tr("Estado: {e}").format(e=texto))
        self.estado.setStyleSheet(f"#chipEstado {{ color: {color}; background: {fondo}; border-radius: 10px;"
                                  f" padding: 2px 10px; font-weight: 600; }}")
        self.motivo.setText(motivo)
        self.motivo.setVisible(bool(motivo))
        self.motivo.setStyleSheet(f"color: {color if est == ERROR else tk.text_muted}; background: transparent;")
        self.setStyleSheet(ia_estilo.tarjeta("tarjetaSup", tk, borde_izq=color))

    def resultado(self) -> Candidato:
        c = self.cand
        c.nombre = self.nombre.text().strip()
        c.crs = validar_crs(self.crs.text())[0]
        c.elegido = self.importa()
        return c


class SuperficiesDialog(QtWidgets.QDialog):
    def __init__(self, candidatos: List[Candidato], crs_proyecto: str, georef: bool, parent=None, escala=""):
        super().__init__(parent)
        self.georef, self.escala = georef, escala
        self.setWindowTitle(_tr("Importar superficies"))
        self.setMinimumWidth(560)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        v.addWidget(ia_estilo.Encabezado("mdi:terrain", _tr("Importar superficies"),
                                         _tr("Terreno en LandXML (.xml) o GeoTIFF (.tif). Viaja a Civil 3D junto a las "
                                             "redes, con los mismos puntos y triángulos.")))
        self.lbl_proyecto = QtWidgets.QLabel(
            _tr("Sistema del proyecto: {crs}").format(crs=crs_proyecto) if georef and crs_proyecto else
            _tr("El plano no está georreferenciado (Hoja y PDF → Georreferenciar…)."))
        self.lbl_proyecto.setProperty("rol", "t2")
        self.lbl_proyecto.setWordWrap(True)
        v.addWidget(self.lbl_proyecto)
        self.rb_ubicar = self.rb_asi = None
        if not georef:
            v.addWidget(self._opciones_sin_georef())
        caja = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(caja)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(8)
        self.tarjetas = []
        for c in candidatos:
            tj = _Tarjeta(c, crs_proyecto, georef)
            tj.cambio.connect(self._actualizar)
            cv.addWidget(tj)
            self.tarjetas.append(tj)
        cv.addStretch(1)
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.NoFrame)
        area.setWidget(caja)
        area.setMinimumHeight(min(440, 175 * max(1, len(candidatos))))
        v.addWidget(area, 1)
        pie = QtWidgets.QHBoxLayout()
        pie.addStretch(1)
        self.btn_cancelar = QtWidgets.QPushButton(_tr("Cancelar"))
        self.btn_cancelar.clicked.connect(self.reject)
        pie.addWidget(self.btn_cancelar)
        self.btn_ok = QtWidgets.QPushButton()
        self.btn_ok.setProperty("kind", "primary")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        pie.addWidget(self.btn_ok)
        v.addLayout(pie)
        self._actualizar()

    def _opciones_sin_georef(self):
        """Plano sin georreferencia (pedido 2026-11-12): ubicarlo en el sistema de la superficie o importar así."""
        caja = QtWidgets.QFrame()
        caja.setObjectName("opcionesGeo")
        lay = QtWidgets.QVBoxLayout(caja)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)
        self.grupo_geo = QtWidgets.QButtonGroup(caja)
        self.rb_ubicar = QtWidgets.QRadioButton(_tr("Ubicar el plano en el sistema de la superficie"))
        self.lbl_ubicar = QtWidgets.QLabel()
        self.rb_asi = QtWidgets.QRadioButton(_tr("Importar sin georreferenciar"))
        self.lbl_asi = QtWidgets.QLabel(_tr("La superficie viaja a Civil 3D con sus coordenadas, pero no se ve sobre "
                                            "el plano."))
        for rb, lbl in ((self.rb_ubicar, self.lbl_ubicar), (self.rb_asi, self.lbl_asi)):
            self.grupo_geo.addButton(rb)
            rb.toggled.connect(lambda _c: self._actualizar())
            lbl.setProperty("rol", "t3")
            lbl.setWordWrap(True)
            lbl.setContentsMargins(26, 0, 0, 4)
            lbl.setStyleSheet("background: transparent;")
            lay.addWidget(rb)
            lay.addWidget(lbl)
        self.rb_ubicar.setChecked(True)
        self._geo_auto = True                               # hasta que el usuario elija, se sugiere «Ubicar»
        self.grupo_geo.buttonClicked.connect(lambda _b: setattr(self, "_geo_auto", False))

        def _pintar(_n=None):
            tk = theme.tokens()
            caja.setStyleSheet(f"#opcionesGeo {{ background: {tk.surface_alt}; border-radius: 10px; }}"
                               "#opcionesGeo QRadioButton { background: transparent; font-weight: 600; }")
        theme.al_tema(caja, _pintar)
        _pintar()
        return caja

    def crs_para_ubicar(self) -> tuple:
        """(«EPSG:n», texto escrito, Candidato) de la primera superficie que se importa y dice su sistema; o ("", "",
        None)."""
        for tj in self.tarjetas:
            if not tj.importa():
                continue
            crs, err, _d = sistemas_cs.resolver(tj.crs.text())
            if crs and not err:
                return crs, tj.crs.text().strip(), tj.cand
        return "", "", None

    def ubicar(self) -> bool:
        return bool(self.rb_ubicar is not None and self.rb_ubicar.isChecked() and self.rb_ubicar.isEnabled())

    def cuantas(self) -> int:
        return sum(1 for tj in self.tarjetas if tj.importa())

    def _actualizar(self):
        if not hasattr(self, "tarjetas"):
            return
        if self.rb_ubicar is not None:
            crs, texto, cand = self.crs_para_ubicar()
            self.rb_ubicar.setEnabled(bool(crs))
            antes, self._crs_antes = getattr(self, "_crs_antes", ""), crs
            if crs and not antes and self._geo_auto:         # recién se sabe el sistema: se sugiere «Ubicar»
                self.rb_ubicar.setChecked(True)
            if crs:
                nombre = (cand.nombre or "") if cand else ""
                self.lbl_ubicar.setText(_tr(
                    "El plano toma {crs} y queda centrado sobre «{n}», sin giro, a la escala de la hoja{e}. "
                    "Después puedes afinarlo con Georreferenciar.").format(
                    crs=texto if texto.upper().removeprefix("EPSG:") != crs.removeprefix("EPSG:") else crs, n=nombre,
                    e=(" (" + self.escala + ")") if self.escala else ""))
            else:
                self.lbl_ubicar.setText(_tr("Escribe el sistema del archivo en la tarjeta (p. ej. UTM84-17S) para usar "
                                            "esta opción."))
                if self.rb_ubicar.isChecked():
                    self.rb_asi.setChecked(True)
            ubica = self.ubicar()
            for tj in self.tarjetas:                       # con el plano ubicado, la superficie sí se verá
                tj.georef = ubica
                tj.crs_proyecto = crs if ubica else ""
                tj._pintar()
        n = self.cuantas()
        self.btn_ok.setText(_tr("Importar 1 superficie") if n == 1 else
                            _tr("Importar {n} superficies").format(n=n))
        self.btn_ok.setEnabled(n > 0)

    def elegidos(self) -> List[Candidato]:
        return [c for c in (tj.resultado() for tj in self.tarjetas) if c.elegido]


__all__ = ["Candidato", "SuperficiesDialog", "validar_crs", "LISTA", "AVISO", "ERROR", "S"]
