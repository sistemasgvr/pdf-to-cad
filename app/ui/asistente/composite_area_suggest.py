"""composite_area_suggest.py — «Área sugerida» en «Área a tomar» (mezcla de `CompositeDialog`).

Pedido del usuario 2026-10-20: al elegir una hoja, sugerir el área que conviene tomar y que
el usuario la ajuste. La cuenta (`hoja.area_sugerida`) corre en el proceso trabajador «area»
(`ui.comun.proceso`: prioridad baja, la ventana no se traba al pasar de hoja en hoja; con
`PDFCAD_PROCESO=0`, en un hilo) y queda en memoria por PDF y hoja.

La sugerencia se dibuja a trazos sobre la hoja (magenta: el naranja es el área marcada y el
turquesa las guías) con una tarjeta que dice por qué. «Usar área sugerida» la MARCA como si
el usuario la hubiera dibujado — se ajusta y se toma con «Tomar área» (o, si la hoja ya está
en edición, la actualiza) por el camino de siempre: el reconocimiento no cambia. Nada se
aplica solo. `PDFCAD_AREA_SUGERIDA=0` la apaga (las pruebas lo ponen así por defecto).

Requiere de la clase: `self.sources`, `self.docs`, `self.comp`, `self.crop`,
`self._cur_source`, `self._cur_page`.
"""
from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from hoja import area_sugerida as AS
from traduccion.i18n import t as _tr
from ui.comun import theme as _theme
from ui.comun.icons import icon as _icon

ENV = "PDFCAD_AREA_SUGERIDA"
TRABAJADOR = "area"
COLOR = "#c2188f"            # magenta: no es de ninguna utilidad ni del área marcada (naranja)
COINCIDE_PT = 15.0           # un área marcada a ≤ esto por lado ES la sugerida (con o sin borde)
MAX_EN_MEMORIA = 400

_CACHE: "OrderedDict[tuple, List[AS.Area]]" = OrderedDict()   # (sha1 del PDF, hoja) → áreas


def activa() -> bool:
    return os.environ.get(ENV, "1") not in ("0", "no", "false")


class AreaSugeridaMixin:
    # ── tarjeta y dibujo ────────────────────────────────────────────────
    def _area_card(self) -> QtWidgets.QFrame:
        """Tarjeta «Área sugerida» (oculta hasta que haya algo que sugerir) y el contorno a
        trazos sobre la hoja. Se llama con `self.crop` ya creado."""
        t = _theme.tokens()
        self._area_hash: Dict[int, str] = {}
        self._area_tarea = None              # (clave, Tarea) en curso
        self._area_pendiente: Optional[Tuple[int, int]] = None
        self._area_lista: List[AS.Area] = []
        self._area_idx = 0
        self._area_oculta = False
        box = QtWidgets.QFrame()
        box.setObjectName("areaSug")
        box.setStyleSheet(
            f"QFrame#areaSug {{ background:{t.surface_alt}; border:1px solid {COLOR}; "
            f"border-left:4px solid {COLOR}; border-radius:4px; }}"
            f"QFrame#areaSug QLabel {{ background:transparent; border:none; }}")
        row = QtWidgets.QHBoxLayout(box)
        row.setContentsMargins(10, 4, 6, 4); row.setSpacing(8)
        ic = QtWidgets.QLabel()
        ic.setPixmap(_icon("mdi:auto-fix", color=COLOR).pixmap(QtCore.QSize(20, 20)))
        row.addWidget(ic, 0, QtCore.Qt.AlignVCenter)
        self.lbl_area_sug = QtWidgets.QLabel()
        self.lbl_area_sug.setWordWrap(True)
        self.lbl_area_sug.setTextFormat(QtCore.Qt.RichText)
        row.addWidget(self.lbl_area_sug, 1)
        self.bar_area_sug = QtWidgets.QProgressBar()
        self.bar_area_sug.setTextVisible(False)
        self.bar_area_sug.setRange(0, 0)
        self.bar_area_sug.setFixedSize(120, 6)
        row.addWidget(self.bar_area_sug, 0, QtCore.Qt.AlignVCenter)
        self.btn_area_usar = QtWidgets.QPushButton(_icon("mdi:selection-search", color=t.soft_text),
                                                   _tr("Usar área sugerida"))
        self.btn_area_usar.setProperty("soft", True)
        self.btn_area_usar.setAutoDefault(False)
        self.btn_area_usar.setToolTip(_tr("Marca el área sugerida en la hoja; ajusta sus lados si hace "
                                          "falta y pulsa «Tomar área»"))
        self.btn_area_usar.clicked.connect(self._area_usar)
        row.addWidget(self.btn_area_usar)
        self.btn_area_otra = QtWidgets.QPushButton(_icon("mdi:swap-horizontal"), _tr("Otra vista"))
        self.btn_area_otra.setProperty("secondary", True)
        self.btn_area_otra.setAutoDefault(False)
        self.btn_area_otra.setToolTip(_tr("La hoja tiene otra vista con líneas de utilidades: sugerir esa"))
        self.btn_area_otra.clicked.connect(self._area_otra)
        row.addWidget(self.btn_area_otra)
        btn_x = QtWidgets.QToolButton()
        btn_x.setIcon(_icon("mdi:close")); btn_x.setAutoRaise(True)
        btn_x.setToolTip(_tr("No sugerir áreas"))
        btn_x.clicked.connect(self._area_ocultar)
        row.addWidget(btn_x, 0, QtCore.Qt.AlignTop)
        box.hide()
        self.area_box = box
        pen = QtGui.QPen(QtGui.QColor(COLOR), 2, QtCore.Qt.DashLine)
        pen.setCosmetic(True)
        fill = QtGui.QColor(COLOR); fill.setAlpha(22)
        self._area_item = self.crop.scene().addPolygon(QtGui.QPolygonF(), pen, QtGui.QBrush(fill))
        self._area_item.setZValue(2.5)                      # bajo el área marcada (3) y sus asas
        self._area_item.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self._area_item.hide()
        self.crop.selectionChanged.connect(lambda _r: self._area_estado())
        return box

    def _area_activa(self) -> bool:
        return hasattr(self, "area_box") and not self.comp.manual and activa() and not self._area_oculta

    # ── pedir ───────────────────────────────────────────────────────────
    def _area_clave(self, src: int, page: int) -> tuple:
        if src not in self._area_hash:
            self._area_hash[src] = hashlib.sha1(self.sources[src]["data"]).hexdigest()
        return self._area_hash[src], page

    def _area_pedir(self):
        """Hoja nueva a la vista: su sugerencia (de la memoria o al trabajador)."""
        if not self._area_activa():
            return
        self._area_lista, self._area_idx = [], 0
        self._area_item.hide()
        clave = self._area_clave(self._cur_source, self._cur_page)
        if clave in _CACHE:
            self._area_mostrar(_CACHE[clave])
            return
        self.lbl_area_sug.setText(f"<span style='color:{_theme.tokens().text_muted}'>"
                                  + _tr("Buscando el área de la hoja que conviene tomar…") + "</span>")
        self.bar_area_sug.show()
        for w in (self.btn_area_usar, self.btn_area_otra):
            w.hide()
        self.area_box.show()
        if self._area_tarea is not None:          # una a la vez: la última que se pidió va después
            self._area_pendiente = (self._cur_source, self._cur_page)
            return
        self._area_enviar(self._cur_source, self._cur_page)

    def _area_enviar(self, src: int, page: int):
        from ui.comun import proceso
        clave = self._area_clave(src, page)
        fuente = self.sources[src].get("path")
        if not (fuente and os.path.isfile(fuente)):
            fuente = self.sources[src]["data"]
        tarea = proceso.Tarea("hoja.area_sugerida:sugerir_en_pdf", (clave[0], fuente, page))
        tarea.terminado.connect(lambda res, err, clave=clave: self._area_hecha(clave, res, err))
        self._area_tarea = (clave, tarea)
        proceso.trabajador(TRABAJADOR).enviar(tarea)

    def _area_hecha(self, clave: tuple, res, err: str):
        self._area_tarea = None
        if err != "cancelado":
            _CACHE[clave] = list(res or []) if not err else []
            while len(_CACHE) > MAX_EN_MEMORIA:
                _CACHE.popitem(last=False)
        pend, self._area_pendiente = self._area_pendiente, None
        if pend is not None and self._area_clave(*pend) not in _CACHE and pend == (self._cur_source, self._cur_page):
            self._area_enviar(*pend)
            return
        if self._area_activa() and clave == self._area_clave(self._cur_source, self._cur_page):
            self._area_mostrar(_CACHE.get(clave, []))

    def _area_cerrar(self):
        """Al cerrar el diálogo: lo que falte ya no hace falta."""
        tarea = self._area_tarea
        self._area_tarea = self._area_pendiente = None
        if tarea is not None:
            try:
                tarea[1].terminado.disconnect()
            except (RuntimeError, TypeError):
                pass

    # ── mostrar ─────────────────────────────────────────────────────────
    def _area_rect(self) -> Optional[QtCore.QRectF]:
        if not self._area_lista:
            return None
        x0, y0, x1, y1 = self._area_lista[self._area_idx].rect
        return QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)

    def _area_esquinas(self) -> List[QtCore.QPointF]:
        """Esquinas del área sugerida (sup-izq, sup-der, inf-der, inf-izq): las de su marco si no es
        recto con la hoja, si no las del rectángulo."""
        a = self._area_lista[self._area_idx]
        if a.poligono:
            return [QtCore.QPointF(x, y) for x, y in a.poligono]
        r = self._area_rect()
        return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]

    def _area_mostrar(self, areas: List[AS.Area]):
        self._area_lista = list(areas or [])
        self._area_idx = 0
        self.bar_area_sug.hide()
        if not self._area_lista:
            self.area_box.hide()
            self._area_item.hide()
            return
        self.area_box.show()
        self._area_estado()

    def _area_texto(self, a: AS.Area) -> str:
        if a.tipo == "planta" and len(a.estaciones) >= 2:
            txt = _tr("la vista de planta entre las match lines STA {a} y STA {b}").format(
                a=a.estaciones[-1], b=a.estaciones[0])
        elif a.tipo == "planta" and a.estaciones:
            txt = _tr("la vista de planta hasta la match line STA {a}").format(a=a.estaciones[0])
        elif a.tipo == "planta":
            txt = _tr("la vista de planta del plano")
        elif a.tipo == "mapa":
            txt = (_tr("el marco del mapa {celda}, sin leyenda ni cajetín").format(celda=a.etiqueta)
                   if a.etiqueta else _tr("el marco del mapa, sin leyenda ni cajetín"))
        elif a.parte is not None:
            txt = _tr("la vista del plano con el {p} % de las líneas de utilidades de la hoja").format(
                p=round(100 * a.parte))
        else:
            txt = _tr("la vista del plano con las líneas de utilidades")
        return txt

    def _area_estado(self):
        """Texto y botones según el área marcada: si ya ES la sugerida, solo un ✔."""
        if not self._area_activa() or not self._area_lista:
            return
        a = self._area_lista[self._area_idx]
        esquinas = self._area_esquinas()
        sel = self.crop._selection
        if sel is None:
            marcadas = []
        elif getattr(self.crop, "free", False) and len(getattr(self.crop, "polygon", []) or []) == 4:
            marcadas = list(self.crop.polygon)
        else:
            marcadas = [sel.topLeft(), sel.topRight(), sel.bottomRight(), sel.bottomLeft()]
        marcada = len(marcadas) == 4 and all(
            abs(p.x() - q.x()) <= COINCIDE_PT and abs(p.y() - q.y()) <= COINCIDE_PT
            for p, q in zip(marcadas, esquinas))
        if marcada:
            self.lbl_area_sug.setText("✔ " + _tr("Área sugerida marcada: {txt}. Ajusta sus lados si hace "
                                                 "falta y pulsa «Tomar área».").format(txt=self._area_texto(a)))
            self._area_item.hide()
        else:
            txt = "<b>" + _tr("Área sugerida:") + "</b> " + self._area_texto(a) + "."
            if a.poligono:
                txt += " " + _tr("Sigue su borde inclinado (esquinas libres).")
            self.lbl_area_sug.setText(txt)
            self._area_item.setPolygon(QtGui.QPolygonF(esquinas))
            self._area_item.show()
        self.btn_area_usar.setVisible(not marcada)
        self.btn_area_otra.setVisible(len(self._area_lista) > 1)
        if len(self._area_lista) > 1:
            self.btn_area_otra.setText(_tr("Otra vista ({i}/{n})").format(
                i=self._area_idx + 1, n=len(self._area_lista)))

    # ── acciones ────────────────────────────────────────────────────────
    def _area_usar(self):
        """Marca el área sugerida: queda como si el usuario la hubiera dibujado."""
        rect = self._area_rect()
        if rect is None:
            return
        a = self._area_lista[self._area_idx]
        if a.poligono:                     # marco inclinado: esquina por esquina
            self.chk_corners.setChecked(True)
            self.crop.set_polygon(self._area_esquinas())
        else:
            self.crop.set_selection(rect)
        self.crop.setFocus()
        self._area_estado()

    def _area_otra(self):
        if len(self._area_lista) > 1:
            self._area_idx = (self._area_idx + 1) % len(self._area_lista)
            self._area_estado()

    def _area_ocultar(self):
        self._area_oculta = True
        self.area_box.hide()
        self._area_item.hide()
