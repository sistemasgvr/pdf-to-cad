"""composite_suggest.py — «Composición sugerida» en el compositor (mezcla de `CompositeDialog`).

Pedido del usuario 2026-10-14: la hoja carga normal y, APARTE, se revisan todas las
hojas del PDF para sugerir cómo se unen. Mientras tanto una tarjeta arriba del
compositor dice «Buscando cómo se unen las hojas… (hoja 12 de 38)»; al terminar:

  · un grupo claro → «Composición sugerida: 14 hojas (UD-201 → UD-214 · STA 556+25 →
    508+00)» con «Usar sugerencia» (reemplaza la hoja compuesta y lleva a «Hoja
    compuesta» para revisarla; «Deshacer» la devuelve como estaba);
  · la hoja abierta / elegida en «Origen» decide el grupo (y con él la serie: UR-602
    o UR-602A); si no está en ninguno y hay varios juegos, se PREGUNTA cuál;
  · si el mapa índice nombra hojas que están en otro PDF de la carpeta («…_South»),
    se pregunta antes de agregarlo; al agregarlo se vuelve a analizar.

El análisis (`hoja.composicion_trabajo`) corre en el proceso trabajador «fondo»
(`ui.comun.proceso`: prioridad baja, la ventana no se traba; con `PDFCAD_PROCESO=0`, en un
hilo) y el resultado queda en memoria por PDF: volver a abrir el compositor no lo repite.
`PDFCAD_SUGERENCIA=0` lo apaga (las pruebas lo ponen así por defecto).

Requiere de la clase: `self.sources`, `self.docs`, `self.comp`, `self.view`,
`self._cur_source`, `self._cur_page`, `self.lst_pages`, `self.cmb_source`, `self._fitted`,
`self._editing` y los métodos `_refresh_scale_combo`, `_refresh_summary`,
`_on_pieces_changed`, `_fill_sources` y `_go_tab`.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Dict, Optional, Sequence

import fitz
from PySide6 import QtCore, QtWidgets

from hoja import composite as C
from hoja import composicion_sugerida as G
from hoja.composicion_trabajo import MAX_FICHAS_EN_MEMORIA, Resultado, calcular, clave_de  # noqa: F401
from traduccion.i18n import t as _tr
from ui.comun.busy import busy
from ui.comun.icons import icon as _icon
from ui.comun import theme as _theme

ENV = "PDFCAD_SUGERENCIA"
TAB_SHEET = 2


def activa() -> bool:
    return os.environ.get(ENV, "1") not in ("0", "no", "false")


class _Hilo(QtCore.QThread):
    avance = QtCore.Signal(object, str, int, int)
    terminado = QtCore.Signal(object, object)

    def __init__(self, fuentes, fichas_cache):
        super().__init__()
        self.fuentes = [dict(f) for f in fuentes]
        self.clave = clave_de(self.fuentes)
        self.fichas_cache = fichas_cache
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        try:
            res = calcular(self.fuentes, lambda e, i, n: self.avance.emit(self.clave, e, i, n),
                           lambda: self._cancelar, self.fichas_cache)
        except Exception as exc:                       # nunca tumbar el compositor
            res = Resultado(self.clave, None, error=str(exc))
        self.terminado.emit(self.clave, res)


class Servicio(QtCore.QObject):
    """Un análisis por juego de PDFs, en segundo plano y guardado en memoria."""
    progreso = QtCore.Signal(object, str, int, int)     # clave, etapa, i, n
    listo = QtCore.Signal(object, object)               # clave, Resultado | None

    def __init__(self):
        super().__init__()
        self._fichas: Dict[str, list] = OrderedDict()
        self._res: Dict[tuple, Resultado] = {}
        self._hilos: Dict[tuple, _Hilo] = {}
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.parar)

    def pedir(self, fuentes: Sequence[dict]) -> tuple:
        clave = clave_de(fuentes)
        if clave in self._res:
            res = self._res[clave]
            QtCore.QTimer.singleShot(0, lambda: self.listo.emit(clave, res))
        elif clave not in self._hilos:
            from ui.comun import proceso
            if proceso.activo():
                t = proceso.Tarea("hoja.composicion_trabajo:analizar",
                                  ([{k: f.get(k) for k in ("data", "name", "path")} for f in fuentes],))
                t.avance.connect(lambda a, clave=clave: self._avance(clave, *a) if a and a[0] != "detalle" else None)
                t.terminado.connect(lambda r, e, clave=clave: self._terminado(
                    clave, r if not e else (None if e == "cancelado" else Resultado(clave, None, error=e))))
                self._hilos[clave] = t
                proceso.trabajador("fondo").enviar(t)
            else:
                hilo = _Hilo(fuentes, self._fichas)
                hilo.avance.connect(self._avance)
                hilo.terminado.connect(self._terminado)
                self._hilos[clave] = hilo
                hilo.start(QtCore.QThread.LowPriority)
        return clave

    def resultado(self, clave) -> Optional[Resultado]:
        return self._res.get(clave)

    def corriendo(self, clave) -> bool:
        return clave in self._hilos

    @QtCore.Slot(object, str, int, int)
    def _avance(self, clave, etapa, i, n):
        self.progreso.emit(clave, etapa, i, n)

    @QtCore.Slot(object, object)
    def _terminado(self, clave, res):
        hilo = self._hilos.pop(clave, None)
        if isinstance(hilo, QtCore.QThread):
            hilo.wait(2000)
            hilo.deleteLater()
        if res is not None and res.analisis is not None:
            self._res[clave] = res
        self.listo.emit(clave, res)

    def parar(self):
        for hilo in list(self._hilos.values()):
            hilo.cancelar()
        for hilo in list(self._hilos.values()):
            if isinstance(hilo, QtCore.QThread):
                hilo.wait(5000)


_SERVICIO: Optional[Servicio] = None


def servicio() -> Servicio:
    global _SERVICIO
    if _SERVICIO is None:
        _SERVICIO = Servicio()
    return _SERVICIO


# ─────────────────────────── textos ───────────────────────────
def describir(g: G.Grupo, an: G.Analisis) -> str:
    d = G.resumen_datos(g, an.fichas)
    txt = _tr("{n} hojas ({desde} → {hasta})").format(n=d["n"], desde=d["desde"], hasta=d["hasta"])
    if "sta" in d:
        txt += " · " + _tr("STA {a} → {b}").format(a=d["sta"][0], b=d["sta"][1])
    if len(d["pdfs"]) > 1:
        txt += " · " + _tr("{n} PDF").format(n=len(d["pdfs"]))
    return txt


def _celdas_txt(celdas) -> str:
    if not celdas:
        return ""
    a, b = celdas[0], celdas[-1]
    return "%d-%d" % a if a == b else "%d-%d … %d-%d" % (a[0], a[1], b[0], b[1])


# ─────────────────────────── tarjeta ───────────────────────────
class SuggestionMixin:
    def _sug_card(self) -> QtWidgets.QFrame:
        """Tarjeta «Composición sugerida» (oculta hasta que haya algo que decir)."""
        t = _theme.tokens()
        self._sug_res: Optional[Resultado] = None
        self._sug_clave = None
        self._sug_antes: Optional[dict] = None      # hoja compuesta antes de usar la sugerencia
        self._sug_usada: Optional[G.Grupo] = None
        self._sug_oculta = False
        self._sug_no_hermano = False
        box = QtWidgets.QFrame()
        box.setObjectName("sugCard")
        box.setStyleSheet(
            f"QFrame#sugCard {{ background:{t.surface_alt}; border:1px solid {t.accent}; "
            f"border-left:4px solid {t.accent}; border-radius:4px; }}"
            f"QFrame#sugCard QLabel {{ background:transparent; border:none; }}")
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(10, 6, 8, 6); lay.setSpacing(4)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(8)
        ic = QtWidgets.QLabel()
        ic.setPixmap(_icon("mdi:vector-combine", color=t.accent).pixmap(QtCore.QSize(20, 20)))
        row.addWidget(ic, 0, QtCore.Qt.AlignVCenter)
        self.lbl_sug = QtWidgets.QLabel()
        self.lbl_sug.setWordWrap(True)
        self.lbl_sug.setTextFormat(QtCore.Qt.RichText)
        row.addWidget(self.lbl_sug, 1)
        self.bar_sug = QtWidgets.QProgressBar()
        self.bar_sug.setTextVisible(False)
        self.bar_sug.setFixedSize(160, 6)
        row.addWidget(self.bar_sug, 0, QtCore.Qt.AlignVCenter)
        self.cmb_sug = QtWidgets.QComboBox()
        self.cmb_sug.setMinimumHeight(30)
        self.cmb_sug.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.cmb_sug.currentIndexChanged.connect(lambda _i: self._sug_refrescar())
        row.addWidget(self.cmb_sug)
        self.btn_sug_usar = QtWidgets.QPushButton(_icon("mdi:check", color=t.text_on_accent), _tr("Usar sugerencia"))
        self.btn_sug_usar.setAutoDefault(False)
        self.btn_sug_usar.setToolTip(_tr("Reemplaza la hoja compuesta por la sugerida (se puede deshacer)"))
        self.btn_sug_usar.clicked.connect(self._sug_usar)
        row.addWidget(self.btn_sug_usar)
        self.btn_sug_deshacer = QtWidgets.QPushButton(_icon("mdi:undo-variant"), _tr("Deshacer"))
        self.btn_sug_deshacer.setProperty("secondary", True)
        self.btn_sug_deshacer.setAutoDefault(False)
        self.btn_sug_deshacer.setToolTip(_tr("Volver a la hoja compuesta de antes de usar la sugerencia"))
        self.btn_sug_deshacer.clicked.connect(self._sug_deshacer)
        row.addWidget(self.btn_sug_deshacer)
        btn_x = QtWidgets.QToolButton()
        btn_x.setIcon(_icon("mdi:close")); btn_x.setAutoRaise(True)
        btn_x.setToolTip(_tr("Ocultar la sugerencia"))
        btn_x.clicked.connect(self._sug_ocultar)
        row.addWidget(btn_x, 0, QtCore.Qt.AlignTop)
        lay.addLayout(row)
        # el PDF hermano (Norte/Sur): se pregunta antes de agregarlo
        self.sug_hermano = QtWidgets.QWidget()
        hrow = QtWidgets.QHBoxLayout(self.sug_hermano); hrow.setContentsMargins(28, 0, 0, 0); hrow.setSpacing(8)
        self.lbl_sug_hermano = QtWidgets.QLabel()
        self.lbl_sug_hermano.setWordWrap(True)
        hrow.addWidget(self.lbl_sug_hermano, 1)
        self.btn_sug_hermano = QtWidgets.QPushButton(_icon("mdi:file-plus-outline", color=t.soft_text), _tr("Agregar PDF"))
        self.btn_sug_hermano.setProperty("soft", True)
        self.btn_sug_hermano.setAutoDefault(False)
        self.btn_sug_hermano.clicked.connect(self._sug_agregar_hermano)
        hrow.addWidget(self.btn_sug_hermano)
        btn_no = QtWidgets.QPushButton(_tr("No"))
        btn_no.setProperty("secondary", True)
        btn_no.setAutoDefault(False)
        btn_no.clicked.connect(self._sug_rechazar_hermano)
        hrow.addWidget(btn_no)
        self.sug_hermano.hide()
        lay.addWidget(self.sug_hermano)
        box.hide()
        self.sug_card = box
        return box

    # ── análisis ────────────────────────────────────────────────────────
    def _sug_iniciar(self):
        if self.comp.manual or not activa() or not self.sources:
            return
        srv = servicio()
        srv.progreso.connect(self._sug_progreso)
        srv.listo.connect(self._sug_listo)
        self._sug_conectada = True
        self.lst_pages.currentRowChanged.connect(lambda _r: self._sug_refrescar())
        self.cmb_source.currentIndexChanged.connect(lambda _i: self._sug_refrescar())
        self._sug_pedir()

    def _sug_pedir(self):
        self._sug_res = None
        self._sug_clave = servicio().pedir(self.sources)
        if self._sug_res is None and not self._sug_oculta:
            self._sug_mostrar_busqueda(_tr("Buscando cómo se unen las hojas…"), 0, 0)

    def _sug_desconectar(self):
        srv = _SERVICIO
        if srv is None or not getattr(self, "_sug_conectada", False):
            return
        self._sug_conectada = False
        for sig, slot in ((srv.progreso, self._sug_progreso), (srv.listo, self._sug_listo)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _sug_progreso(self, clave, etapa, i, n):
        if clave != self._sug_clave or self._sug_oculta:
            return
        textos = {"hojas": _tr("Buscando cómo se unen las hojas… (hoja {i} de {n})").format(i=i, n=n),
                  "uniones": _tr("Confirmando las uniones con el dibujo…"),
                  "armar": _tr("Armando la composición sugerida…"),
                  "hermano": _tr("Buscando en la carpeta el PDF con las hojas vecinas…")}
        self._sug_mostrar_busqueda(textos.get(etapa, ""), i, n)

    def _sug_mostrar_busqueda(self, texto: str, i: int, n: int):
        self.lbl_sug.setText(texto)
        self.bar_sug.setRange(0, n if n else 0)
        if n:
            self.bar_sug.setValue(i)
        self.bar_sug.show()
        for w in (self.cmb_sug, self.btn_sug_usar, self.btn_sug_deshacer):
            w.hide()
        self.sug_hermano.hide()
        self.sug_card.show()

    def _sug_listo(self, clave, res):
        if clave != self._sug_clave:
            return
        self._sug_res = res
        self._sug_llenar_combo()
        self._sug_refrescar()

    # ── qué sugerir ─────────────────────────────────────────────────────
    def _sug_llenar_combo(self):
        self.cmb_sug.blockSignals(True)
        self.cmb_sug.clear()
        an = self._sug_res.analisis if self._sug_res else None
        if an is not None and len(an.grupos) > 1:
            self.cmb_sug.addItem(_tr("Elegir el juego de hojas…"), -1)
            for k, g in enumerate(an.grupos):
                serie = " / ".join(s.replace("#", "…") for s in g.series) if g.tipo == "estaciones" else ""
                txt = describir(g, an)
                self.cmb_sug.addItem((serie + " · " + txt) if serie else txt, k)
        self.cmb_sug.blockSignals(False)

    def _sug_grupo(self):
        """(grupo, hay que preguntar). La hoja abierta / elegida manda; si no está en
        ningún grupo y hay varios juegos, el usuario elige en la lista."""
        an = self._sug_res.analisis if self._sug_res else None
        if an is None or not an.grupos:
            return None, False
        g = an.grupo_de((self._cur_source, self._cur_page))
        if g is not None:
            return g, False
        if len(an.grupos) == 1:
            return an.grupos[0], False
        k = self.cmb_sug.currentData()
        if k is None or k < 0:
            return None, True
        return an.grupos[int(k)], True

    def _sug_refrescar(self):
        if not hasattr(self, "sug_card") or self._sug_res is None or self._sug_oculta:
            return
        t = _theme.tokens()
        self.bar_sug.hide()
        res = self._sug_res
        an = res.analisis
        if an is None:
            self.sug_card.hide()
            return
        if self._sug_usada is not None:
            self.lbl_sug.setText(_tr("✔ Composición sugerida en la hoja compuesta: {txt}.").format(
                txt=describir(self._sug_usada, an)))
            self.cmb_sug.hide(); self.btn_sug_usar.hide(); self.btn_sug_deshacer.show()
        else:
            g, preguntar = self._sug_grupo()
            self.btn_sug_deshacer.hide()
            self.cmb_sug.setVisible(preguntar)
            if g is None and preguntar:
                self.lbl_sug.setText(_tr("Encontré {n} juegos de hojas que se unen. ¿Cuál quieres usar?").format(
                    n=len(an.grupos)))
                self.btn_sug_usar.show(); self.btn_sug_usar.setEnabled(False)
            elif g is None:
                self.lbl_sug.setText(f"<span style='color:{t.text_muted}'>"
                                     + _tr("No encontré hojas que se unan solas: compón la hoja a mano.")
                                     + "</span>")
                self.btn_sug_usar.hide()
            else:
                self.lbl_sug.setText("<b>" + _tr("Composición sugerida:") + "</b> " + describir(g, an))
                self.btn_sug_usar.show(); self.btn_sug_usar.setEnabled(g.composite is not None)
        herm = res.hermano
        if herm is not None and not self._sug_no_hermano and herm.ruta not in [s.get("path") for s in self.sources]:
            self.lbl_sug_hermano.setText(_tr("Las hojas vecinas {celdas} ({n}) están en «{pdf}». ¿Agregarlo a la composición?").format(
                celdas=_celdas_txt(herm.celdas), n=len(herm.celdas), pdf=os.path.basename(herm.ruta)))
            self.sug_hermano.show()
        else:
            self.sug_hermano.hide()
        self.sug_card.show()

    # ── acciones ────────────────────────────────────────────────────────
    def _sug_usar(self):
        g, _preg = self._sug_grupo()
        if g is None or g.composite is None:
            return
        comp = g.composite
        self._sug_antes = self.comp.to_dict()
        self._sug_antes_vista = (self._cur_source, self._cur_page)
        with busy(self, _tr("Armando la composición sugerida…"),
                  _tr("{n} hojas · vectores, capas y textos intactos").format(n=len(comp.pieces))):
            self._sug_poner(C.Composite.from_dict(comp.to_dict()))
            # la hoja a la vista pasa a ser una de la composición: si no, «Continuar»
            # preguntaba por la portada abierta («hoja sin tomar»)
            p0 = self.comp.pieces[0]
            self._sug_ver_hoja(p0.source, p0.page)
        self._sug_usada = g
        self._sug_refrescar()
        self._fitted.discard(TAB_SHEET)
        self._go_tab(TAB_SHEET)

    def _sug_poner(self, comp: C.Composite):
        """La hoja compuesta pasa a ser `comp` (mismas piezas, escala y uniones)."""
        self.view.select(-1)
        self.comp.pieces[:] = comp.pieces
        self.comp.scale_ft_per_pt = comp.scale_ft_per_pt
        self._editing = -1
        self._refresh_scale_combo()
        self.view.rebuild()
        self._refresh_summary()
        self._on_pieces_changed()

    def _sug_ver_hoja(self, src: int, page: int):
        """Muestra esa hoja en «Origen» / «Área a tomar» sin tocar la hoja compuesta."""
        if src != self._cur_source:
            self._cur_source, self._cur_page = src, page
            self.cmb_source.blockSignals(True)
            self.cmb_source.setCurrentIndex(src)
            self.cmb_source.blockSignals(False)
            self._fill_pages()
        elif page != self._cur_page:
            self.lst_pages.setCurrentRow(page)

    def _sug_deshacer(self):
        if self._sug_antes is None:
            return
        with busy(self, _tr("Volviendo a la hoja compuesta anterior…")):
            self._sug_poner(C.Composite.from_dict(self._sug_antes))
            vista = getattr(self, "_sug_antes_vista", None)
            if vista is not None and vista[0] < len(self.docs):
                self._sug_ver_hoja(*vista)
        self._sug_antes = None
        self._sug_usada = None
        self._sug_refrescar()
        self._fitted.discard(TAB_SHEET)
        self._go_tab(TAB_SHEET if len(self.comp.pieces) > 1 else 0)

    def _sug_ocultar(self):
        self._sug_oculta = True
        self.sug_card.hide()

    def _sug_rechazar_hermano(self):
        self._sug_no_hermano = True
        self.sug_hermano.hide()

    def _sug_agregar_hermano(self):
        herm = self._sug_res.hermano if self._sug_res else None
        if herm is None:
            return
        try:
            with open(herm.ruta, "rb") as fp:
                data = fp.read()
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, _tr("Agregar PDF"),
                                          _tr("No se pudo abrir el PDF:\n\n{e}").format(e=exc))
            return
        self.sources.append({"name": os.path.basename(herm.ruta), "data": data, "path": herm.ruta})
        self.docs.append(doc)
        self._fill_sources()                      # se sigue viendo la misma hoja
        self._sug_no_hermano = True
        self.sug_hermano.hide()
        self._sug_pedir()                          # de nuevo, ahora con los dos PDF
