"""Elegir un accesorio en el plano y ver sus propiedades (pedido del usuario 2026-11-06).

- Clic en un accesorio del lienzo (codo, Tee, Wye, cruz o válvula) → se elige: se abre Inventario → «Accesorios»
  con su fila elegida (sin mover el plano).
- Con UNA fila elegida, el panel derecho muestra sus propiedades (`gprop_acc`). Solo se editan las que aplican:
  la válvula (unión, material; quitarla) y, en un codo/Tee/Wye/cruz, «Poner este accesorio» (= «No hay …» de
  siempre). El tipo, el ángulo y los diámetros de un codo/Tee/Wye/cruz salen de la FORMA de las tuberías: se cambian
  cambiando las tuberías (por eso van de solo lectura, con su motivo en el globo).
"""
from __future__ import annotations

from ui.ventana.ventana_comun import *  # noqa: F401,F403  (mismos nombres que app_window)
from nucleo import accesorios as _A
from nucleo import valvulas as _V
from nucleo.model import TAB_ACC
from nucleo.normas_validar import NOMBRE_ACC
from traduccion.i18n_core import N_
from ui.comun.responsive import ResponsiveGroupBox, WrapButton, WrapCheckBox

RADIO_CLIC_PX = 14.0                   # cuánto se busca el accesorio alrededor del clic (px de pantalla)
_PAGINA_INVENTARIO = 2                 # página del riel (ventana_shell.PAGINAS)


class SeleccionAccesorioMixin:
    # ── clic en el plano ─────────────────────────────────────────────────
    def _accesorio_bajo_clic(self, x, y):
        """("valv", índice) | ("acc", dict) del accesorio a ≤ RADIO_CLIC_PX del clic, o None."""
        r = RADIO_CLIC_PX / max(self.canvas.transform().m11(), 1e-6)
        apagadas = self._lineas_apagadas()
        k = self._valvula_en(x, y)                      # (con su subgrupo apagado, −1)
        if k >= 0:
            return ("valv", k)
        ver = getattr(self, "act_show_acc", None)
        if ver is not None and not ver.isChecked():
            return None                                 # accesorios ocultos en el plano: no se eligen
        a = self.accesorio_en(x, y, r)
        if a is not None and (a.get("capa") or "") not in apagadas:
            return ("acc", a)
        return None

    def _elegir_accesorio_en(self, x, y):
        """Elige el accesorio bajo el clic (Inventario → Accesorios). True si había uno."""
        hit = self._accesorio_bajo_clic(x, y)
        if hit is None:
            return False
        clase, dato = hit
        self._abrir_inventario()
        self._show_tab(TAB_ACC)
        self._llenar_lista_accesorios(forzar=True)
        fila = -1
        for n, f in enumerate(self._acc_filas):
            if f.clase != clase:
                continue
            if clase == "valv" and f.dato == dato:
                fila = n
                break
            if clase == "acc" and abs(f.x - dato["x"]) < 1e-6 and abs(f.y - dato["y"]) < 1e-6:
                fila = n
                break
        if fila < 0:
            return False
        if self.acc_list.isRowHidden(fila):              # el filtro lo ocultaba: «Todos»
            self.filtro_accesorios.button(0).setChecked(True)
            self._filtrar_inventario()
        self._acc_sin_mover = True
        try:
            self.acc_list.clearSelection()
            self.acc_list.setCurrentRow(fila)
            it = self.acc_list.item(fila)
            if it is not None:
                it.setSelected(True)
                self.acc_list.scrollToItem(it, QtWidgets.QAbstractItemView.PositionAtCenter)
        finally:
            self._acc_sin_mover = False
        self._marcar_lugar(self._acc_filas[fila].x, self._acc_filas[fila].y)
        self.ver_propiedades()
        return True

    def _abrir_inventario(self):
        """Lleva el panel izquierdo a «Inventario» (si hay riel)."""
        from ui.ventana import ventana_shell
        if getattr(self, "paneles_riel", None) is None:
            return
        i = next((n for n, r in enumerate(ventana_shell.RIEL) if r[2] == _PAGINA_INVENTARIO), None)
        if i is not None and getattr(self, "_pagina_riel", None) != _PAGINA_INVENTARIO:
            self._ir_riel(i)

    # ── panel de propiedades ─────────────────────────────────────────────
    def _build_prop_accesorio(self, rv):
        # sin título: la cabecera del inspector ya dice qué es (como buzones y curvas en 2.0.0)
        g = self.gprop_acc = ResponsiveGroupBox()
        g.setFlat(True)
        g.setStyleSheet("QGroupBox { margin-top: 0; padding-top: 0; border: none; }")
        f = QtWidgets.QFormLayout(g)
        f.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)      # etiquetas cortas: siempre al lado
        f.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        f.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self._acc_form = f
        self._acc_campos = {}

        def fila(clave, texto, w):
            lbl = _bind(QtWidgets.QLabel(), "setText", texto)
            f.addRow(lbl, w)
            self._acc_campos[clave] = (lbl, w)
            return w

        def dato():
            from ui.comun.texto_ajustado import TextoAjustado
            w = TextoAjustado("—")                    # salto de línea sin que QFormLayout le dé alto de más/menos
            w.setWordWrap(True)
            w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            return w
        fila("tipo", N_("Tipo:"), dato())
        fila("angulo", N_("Ángulo:"), dato())
        fila("diam", N_("Diámetro:"), dato())
        fila("red", N_("Red:"), dato())
        self.acc_union = QtWidgets.QComboBox()
        for u, txt in (("FLG", "Unión con bridas (FLG)"), ("RG", "Junta mecánica (RG)")):
            self.acc_union.addItem(_tr(txt), u)
        _bind(self.acc_union, "setToolTip", "Cómo se une la válvula a la tubería. La junta mecánica (RG) llega "
                                            "hasta 16\"; desde 18\" va con bridas y operador de engranes.")
        self.acc_union.currentIndexChanged.connect(lambda _i: self._acc_prop_cambio("union"))
        fila("union", N_("Unión:"), self.acc_union)
        self.acc_material = QtWidgets.QComboBox()
        self.acc_material.addItem(_tr("El de la tubería"), "")
        for m in _V.MATERIALES:
            self.acc_material.addItem(m, m)
        self.acc_material.currentIndexChanged.connect(lambda _i: self._acc_prop_cambio("material"))
        fila("material", N_("Material:"), self.acc_material)
        fila("pieza", N_("Pieza:"), dato())
        fila("largo", N_("Largo:"), dato())
        from ui.comun import rediseno as _R
        self.acc_utils = _R.transparente(QtWidgets.QWidget())
        lay = QtWidgets.QHBoxLayout(self.acc_utils)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        fila("utils", N_("Utilidades:"), self.acc_utils)
        self.chk_acc_poner = _bind(WrapCheckBox(), "setText", "Poner este accesorio (también en Civil 3D)")
        _bind(self.chk_acc_poner, "setToolTip", "Apágalo si en este punto NO va el accesorio: las tuberías llegan "
                                                "sin conectarse (en la app y en Civil 3D). Ctrl+Z deshace.")
        self.chk_acc_poner.toggled.connect(lambda v: self._acc_prop_cambio("poner"))
        f.addRow("", self.chk_acc_poner)
        self.lbl_acc_forma = QtWidgets.QLabel()
        self.lbl_acc_forma.setWordWrap(True)
        self.lbl_acc_forma.setProperty("rol", "t3")
        f.addRow(self.lbl_acc_forma)
        self.btn_acc_quitar = _bind(WrapButton(), "setText", "Quitar la válvula")
        self.btn_acc_quitar.setProperty("danger", True)
        self.btn_acc_quitar.clicked.connect(lambda: self._acc_prop_cambio("quitar"))
        f.addRow(self.btn_acc_quitar)
        rv.addWidget(g)
        self.lbl_acc_hint = _bind(QtWidgets.QLabel(), "setText", "Haz clic en un accesorio de la lista (o en el plano) "
                                                                 "para ver sus propiedades.")
        self.lbl_acc_hint.setWordWrap(True)
        rv.addWidget(self.lbl_acc_hint)
        g.setVisible(False)
        self.lbl_acc_hint.setVisible(False)
        self._acc_guard = False

    # ── resaltado en el plano ────────────────────────────────────────────
    def _resaltar_accesorio(self, f):
        """El accesorio elegido se resalta como una utilidad elegida (pedido 2026-11-06): las tuberías que une, más
        gruesas en su color, en el largo del cuerpo del accesorio, y un anillo en el nodo. Sus propios ítems (no van en
        `_overlay`: un redibujo que no cambia la lista no vuelve a pedirlos)."""
        sc = self.canvas.scene()
        for it in getattr(self, "_acc_resalte", None) or []:
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._acc_resalte = []
        if f is None:
            return
        color = layer_qcolor(f.capa) if f.capa else QtGui.QColor(_theme.tokens().accent)
        escala = max(self.canvas.transform().m11(), 1e-6)
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        if f.clase == "valv":
            lug = (getattr(self, "_valv_lugares", None) or [None] * (f.dato + 1))[f.dato]
            medio = (lug.largo_ft / 2 / ft) if (lug is not None and lug.ok and ft) else 0.0
        else:
            diams = [float(self.pipes[j].get("diam") or 0) for j in f.pipes if 0 <= j < len(self.pipes)]
            medio = (1.7 * max(diams or [0]) / 12.0 / ft) if ft else 0.0
        r = max(medio, 22.0 / escala)                  # al menos ~22 px de pantalla: se ve también de lejos
        pen = QtGui.QPen(color, 6.0)
        pen.setCosmetic(True)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        for j in f.pipes:
            if not (0 <= j < len(self.pipes)):
                continue
            pts = self.pipes[j].get("pts") or []
            for a, b in zip(pts, pts[1:]):
                tramo = _dentro_del_circulo(a, b, (f.x, f.y), r)
                if tramo is not None:
                    it = sc.addLine(*tramo[0], *tramo[1], pen)
                    it.setZValue(Z_MARK + 1)
                    self._acc_resalte.append(it)
        anillo = QtGui.QPen(color, 2.5)
        anillo.setCosmetic(True)
        relleno = QtGui.QColor(color)
        relleno.setAlpha(60)
        R = 11.0
        it = sc.addEllipse(-R, -R, 2 * R, 2 * R, anillo, QtGui.QBrush(relleno))
        it.setPos(f.x, f.y)
        it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        it.setZValue(Z_HANDLE + 2)
        it.setToolTip(f.globo)
        self._acc_resalte.append(it)

    def _fila_acc_elegida(self):
        elegidas = self._filas_elegidas() if getattr(self, "acc_list", None) is not None else []
        return elegidas[0] if len(elegidas) == 1 else None

    def _ver_campo(self, clave, si):
        _lbl, w = self._acc_campos[clave]
        self._acc_form.setRowVisible(w, si)           # la fila entera (sin dejar su hueco)

    def _sync_prop_accesorio(self):
        g = getattr(self, "gprop_acc", None)
        if g is None:
            return
        en_tab = self._current_tab() == TAB_ACC
        f = self._fila_acc_elegida() if en_tab else None
        self._resaltar_accesorio(f)
        g.setVisible(f is not None)
        self.lbl_acc_hint.setVisible(en_tab and f is None and bool(getattr(self, "_acc_filas", None)))
        if f is None:
            return
        self._acc_guard = True
        try:
            self._llenar_prop_acc(f)
        finally:
            self._acc_guard = False
        cab = getattr(self, "cabecera_inspector", None)
        if cab is not None:
            cab.refrescar()

    def _llenar_prop_acc(self, f):
        pipes = self.pipes
        campo = lambda k: self._acc_campos[k][1]  # noqa: E731
        es_valv = f.clase == "valv"
        lug = None
        if es_valv:
            lugares = getattr(self, "_valv_lugares", None) or self._lugares_valvulas()
            lug = lugares[f.dato] if f.dato < len(lugares) else None
        ids = list(f.pipes)
        if es_valv:
            campo("tipo").setText(_tr("Válvula de compuerta"))
            campo("pieza").setText(lug.bloque if lug is not None and lug.ok else "—")
            campo("angulo").setText("—")
            d = f'{lug.diam_in:g}"' if lug is not None and lug.ok else "—"
            campo("diam").setText(d)
            v = self.valvulas[f.dato] if 0 <= f.dato < len(self.valvulas) else {}
            i = self.acc_union.findData(lug.union if lug is not None and lug.ok else (v.get("union") or "FLG"))
            self.acc_union.setCurrentIndex(max(0, i))
            rg = self.acc_union.model().item(self.acc_union.findData("RG"))
            if rg is not None:
                rg.setEnabled(not (lug is not None and lug.ok and lug.diam_in > _V.RG_MAX_IN))
            i = self.acc_material.findData(v.get("material") or "")
            self.acc_material.setCurrentIndex(max(0, i))
            sugerido = lug.material if lug is not None and lug.ok else "DI-A"
            self.acc_material.setItemText(0, _tr("El de la tubería ({m})").format(m=sugerido))
            campo("largo").setText(_tr("{L} ft").format(L=f"{lug.largo_ft:.2f}") if lug is not None and lug.ok else "—")
            self.lbl_acc_forma.setText("" if lug is None or lug.ok else
                                       _tr("Fuera de lugar: {m}").format(m=lug.motivo))
        else:
            a = f.dato
            tipo = a.get("tipo") or ""
            nombre = _tr(NOMBRE_ACC.get(tipo, tipo))
            campo("tipo").setText(nombre)
            ang = a.get("angulo")
            if ang is None:
                campo("angulo").setText("—")
            elif tipo == "codo":
                campo("angulo").setText(_tr("{a} (deflexión)").format(a=_A.texto_angulo(ang)))
            else:
                campo("angulo").setText(_tr("{a} (ramal)").format(a=_A.texto_angulo(ang)))
            diams = []
            orden = list(a.get("tronco") or []) + ([a["ramal"]] if a.get("ramal") is not None else [])
            for j in orden or ids:
                if 0 <= j < len(pipes):
                    d = f'{float(pipes[j].get("diam") or 0):g}"'
                    if d not in diams:
                        diams.append(d)
            texto = " × ".join(diams) or "—"
            if a.get("ramal") is not None and len(diams) > 1:
                texto += "  " + _tr("(principal × ramal)")
            campo("diam").setText(texto)
            self.chk_acc_poner.setChecked(True)
            self.lbl_acc_forma.setText(_tr("Sale de la forma de las tuberías: para cambiar el tipo, el ángulo o el "
                                           "diámetro, cambia sus tuberías."))
        capa = f.capa or ""
        red = (f.dato.get("red") if not es_valv else None) or capa
        campo("red").setText(f"{self._tipo(capa)} · {red}" if capa and red != capa else
                             (self._tipo(capa) if capa else "—"))
        for clave in ("union", "material", "pieza", "largo"):
            self._ver_campo(clave, es_valv)
        self._ver_campo("angulo", not es_valv)
        self.btn_acc_quitar.setVisible(es_valv)
        self.chk_acc_poner.setVisible(not es_valv)
        self.lbl_acc_forma.setVisible(bool(self.lbl_acc_forma.text()))
        lay = self.acc_utils.layout()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for j in ids:
            b = QtWidgets.QPushButton(f"#{j + 1}")
            b.setProperty("kind", "chip")
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setToolTip(_tr("Ir a la utilidad #{n}").format(n=j + 1))
            b.clicked.connect(lambda _=False, j=j, x=f.x, y=f.y: self._ir_a_elemento(x, y, "pipe", j))
            lay.addWidget(b)
        lay.addStretch(1)
        self._ver_campo("utils", bool(ids))

    def _acc_prop_cambio(self, que):
        if getattr(self, "_acc_guard", False):
            return
        f = self._fila_acc_elegida()
        if f is None:
            return
        if f.clase == "valv":
            if que == "union":
                self.cambiar_valvula(f.dato, union=self.acc_union.currentData())
            elif que == "material":
                self.cambiar_valvula(f.dato, material=self.acc_material.currentData())
            elif que == "quitar":
                self.quitar_valvula(f.dato)
        elif que == "poner" and not self.chk_acc_poner.isChecked():
            self.marcar_sin_accesorio(f.dato)


def _dentro_del_circulo(a, b, c, r):
    """La parte del segmento a→b a ≤ r de c, como (p, q), o None."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - c[0], a[1] - c[1]
    A = dx * dx + dy * dy
    if A <= 1e-12:
        return None
    B = 2 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - r * r
    disc = B * B - 4 * A * C
    if disc < 0:
        return None
    s = disc ** 0.5
    t0, t1 = max(0.0, (-B - s) / (2 * A)), min(1.0, (-B + s) / (2 * A))
    if t1 <= t0:
        return None
    return (a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1)
