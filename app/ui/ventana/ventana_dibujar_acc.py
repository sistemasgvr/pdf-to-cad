"""Dibujar → «Accesorios» (pedido del usuario 2026-11-06): codo, Tee, Wye y cruz en agua y gas, en dos clics y con
vista previa (la válvula sigue siendo `ventana_valvulas`). La forma y su validación son puras
(`nucleo/dibujar_accesorios`); aquí van el modo «insert_acc», la vista previa verde/roja, los clics y el cambio
(un paso de deshacer).

Paso 1: clic en la PUNTA de la tubería (codo) o sobre un TRAMO RECTO (Tee, Wye, cruz). Paso 2: el cursor da el lado,
la dirección y el largo del tramo nuevo; clic = listo. Esc (o clic derecho) vuelve al paso 1; otro Esc sale.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import dibujar_accesorios as DA
from nucleo.accesorios import texto_angulo
from nucleo.model import Z_MARK
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

NOMBRES = {"codo": N_("Codo"), "tee": N_("Tee"), "wye": N_("Wye"), "cruz": N_("Cruz")}
VERDE = QtGui.QColor(30, 200, 60)
ROJO = QtGui.QColor(230, 50, 50)


def nombre_accesorio(tipo, angulo=None):
    n = _tr(NOMBRES.get(tipo, tipo))
    return f"{n} {texto_angulo(angulo)}" if tipo == "codo" and angulo else n


class DibujarAccesoriosMixin:
    # ── herramienta ──────────────────────────────────────────────────────
    def dibujar_accesorio(self, tipo, angulo=None):
        """Arranca la herramienta del accesorio `tipo` ("valvula" | "codo" | "tee" | "wye" | "cruz")."""
        if tipo == "valvula":
            self.insertar_valvula()                 # una sola válvula genérica (compuerta)
            return
        if not DA.hay_presion(self.pipes):
            self._info(motivo_sin_presion())
            return
        self._acc_dib = {"tipo": tipo, "angulo": angulo, "base": None}
        self.set_mode("insert_acc")
        self._info(self._texto_paso1())

    def _texto_paso1(self):
        d = getattr(self, "_acc_dib", None) or {}
        n = nombre_accesorio(d.get("tipo"), d.get("angulo"))
        if d.get("tipo") == "codo":
            return _tr("{n}: clic en la PUNTA de una tubería de agua o gas (Esc para salir).").format(n=n)
        return _tr("{n}: clic sobre un tramo recto de agua o gas (Esc para salir).").format(n=n)

    def _ft_px_acc(self):
        return self.scale / self.zoom if self.scale and self.zoom else 0.0

    def _cerca_acc(self, x, y, r):
        return self._utilidades_cerca(x, y, r, todas=True)

    def _base_acc(self, x, y):
        d = self._acc_dib
        r = 14.0 / max(self.canvas.transform().m11(), 1e-6)
        ft = self._ft_px_acc()
        if d["tipo"] == "codo":
            return DA.punta(self.pipes, self.structures, x, y, ft, r, cerca=self._cerca_acc)
        return DA.en_tramo(self.pipes, self.structures, x, y, ft, r, otras_valvulas=self._otras_valvulas(),
                           cerca=self._cerca_acc)

    def _propuesta_acc(self, x, y):
        d = self._acc_dib
        normas = None
        cat = getattr(self, "normas_cat", None)
        if cat:
            from nucleo import normas_validar as NV
            normas = NV.activas(cat)
        return DA.propuesta(d["tipo"], d["base"], x, y, self.pipes, self._ft_px_acc(), angulo=d.get("angulo"),
                            cerca=self._cerca_acc, normas=normas)

    # ── vista previa ─────────────────────────────────────────────────────
    def _quitar_pista_acc(self):
        sc = self.canvas.scene()
        for it in getattr(self, "_pista_acc", None) or []:
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._pista_acc = []

    def _pista_accesorio(self, x, y):
        self._quitar_pista_acc()
        if self.mode != "insert_acc" or not getattr(self, "_acc_dib", None):
            return
        d = self._acc_dib
        if d["base"] is None:
            b = self._base_acc(x, y)
            if b.ok:
                self._punto_pista(b.x, b.y, VERDE)
                txt = self._texto_paso1().split(":")[0] + ": " + _tr("clic para empezar aquí.")
                if b.movida:
                    txt += " " + _tr("Se corre para caber en el tramo recto.")
                self._info(txt)
            else:
                self._info(b.motivo)
            return
        pr = self._propuesta_acc(x, y)
        color = VERDE if pr.ok else ROJO
        for lin in pr.lineas:
            path = QtGui.QPainterPath(QtCore.QPointF(*lin[0]))
            for q in lin[1:]:
                path.lineTo(*q)
            pen = QtGui.QPen(color, 3)
            pen.setCosmetic(True)
            pen.setStyle(QtCore.Qt.DashLine)
            it = self.canvas.scene().addPath(path, pen)
            it.setZValue(Z_MARK + 20)
            self._pista_acc.append(it)
        self._punto_pista(d["base"].x, d["base"].y, color)
        if pr.ok:
            txt = _tr("{n} · tramo nuevo de {L} ft: clic para dibujarlo (Esc vuelve).").format(
                n=nombre_accesorio(d["tipo"], d.get("angulo")), L=f"{pr.largo_ft:.1f}")
            if pr.avisos:
                txt += "  ⚠ " + " · ".join(pr.avisos)
        else:
            txt = pr.motivo
        self._info(txt)

    def _punto_pista(self, x, y, color):
        R = 6.0
        pen = QtGui.QPen(color, 2.0)
        pen.setCosmetic(True)
        c = QtGui.QColor(color)
        c.setAlpha(70)
        it = self.canvas.scene().addEllipse(-R, -R, 2 * R, 2 * R, pen, QtGui.QBrush(c))
        it.setPos(x, y)
        it.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        it.setZValue(Z_MARK + 21)
        self._pista_acc.append(it)

    # ── clics ────────────────────────────────────────────────────────────
    def _clic_accesorio(self, x, y):
        d = getattr(self, "_acc_dib", None)
        if not d:
            return
        if d["base"] is None:
            b = self._base_acc(x, y)
            if not b.ok:
                self._info(b.motivo)
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), b.motivo, self.canvas)
                return
            d["base"] = b
            self._pista_accesorio(x, y)
            return
        pr = self._propuesta_acc(x, y)
        if not pr.ok:
            self._info(pr.motivo)
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), pr.motivo, self.canvas)
            return
        self._push()
        DA.aplicar(self.pipes, pr)
        self._dirty = True
        d["base"] = None
        self._quitar_pista_acc()
        self._refresh_lists(); self._update_ui(); self._redraw()
        texto = _tr("{n} dibujado. Clic para otro o Esc para salir (Ctrl+Z deshace).").format(
            n=nombre_accesorio(d["tipo"], d.get("angulo")))
        if pr.avisos:
            texto += "  ⚠ " + " · ".join(pr.avisos)
        self._info(texto)

    def _escape_accesorio(self):
        """Esc: del paso 2 vuelve al 1; del 1 sale."""
        d = getattr(self, "_acc_dib", None)
        self._quitar_pista_acc()
        if d and d.get("base") is not None:
            d["base"] = None
            self._info(self._texto_paso1())
            return
        self._acc_dib = None
        self.set_mode("idle")
        self._info(_tr("Dibujo de accesorio terminado."))


def motivo_sin_presion():
    return _tr("Accesorios: hace falta una tubería de agua o gas (van en redes a presión).")


# (tipo, ángulo, icono, texto, ayuda) del menú «Accesorios» de Dibujar
MENU = (
    ("valvula", None, "valve", N_("Válvula"), N_("Haz clic sobre un tramo recto de agua o gas.")),
    ("codo", None, "acc-codo", N_("Codo"), N_("Desde la punta de una tubería: el tramo nuevo gira ese ángulo.")),
    ("tee", None, "acc-tee", N_("Tee · ramal a 90°"), N_("Sobre un tramo recto: un ramal nuevo a 90°.")),
    ("wye", None, "acc-wye", N_("Wye · ramal a 45°"), N_("Sobre un tramo recto: un ramal nuevo a 45°, hacia adelante "
                                                          "o atrás.")),
    ("cruz", None, "acc-cruz", N_("Cruz"), N_("Sobre un tramo recto: una tubería nueva que lo cruza a 90°.")),
)


def llenar_menu(win, menu):
    """El desplegable de «Accesorios» (se rehace al abrirse: sin agua ni gas, todo apagado con el motivo)."""
    from ui.comun.icons import icon
    from ui.comun import theme as _theme
    menu.clear()
    menu.setToolTipsVisible(True)
    t = _theme.tokens()
    hay = DA.hay_presion(win.pipes)
    lbl = QtWidgets.QLabel(_tr("Agua y gas · redes a presión") if hay else motivo_sin_presion())
    lbl.setWordWrap(True)
    lbl.setMaximumWidth(260)
    lbl.setStyleSheet(f"color:{t.text_muted if hay else t.warning}; font-size:11px; padding:6px 12px 4px 12px;")
    wa = QtWidgets.QWidgetAction(menu)
    wa.setDefaultWidget(lbl)
    wa.setEnabled(False)
    menu.addAction(wa)
    d = getattr(win, "_acc_dib", None) if win.mode == "insert_acc" else None
    actual = (("valvula", None) if win.mode == "insert_valv"
              else ((d["tipo"], d.get("angulo")) if d else None))
    for tipo, _ang, ic, txt, ayuda in MENU:
        color = t.text if hay else t.text3
        if tipo == "codo":
            sub = menu.addMenu(icon("mdi:" + ic, color=color), _tr(txt))
            sub.setToolTipsVisible(True)
            sub.setEnabled(hay)
            sub.menuAction().setToolTip(_tr(ayuda))
            for a in DA.ANGULOS_CODO:
                act = sub.addAction(_tr("Codo de {a}").format(a=texto_angulo(a)),
                                    lambda a=a: win.dibujar_accesorio("codo", a))
                act.setToolTip(_tr(ayuda))
                act.setCheckable(True)
                act.setChecked(actual == ("codo", a))
            continue
        act = menu.addAction(icon("mdi:" + ic, color=color), _tr(txt),
                             lambda tp=tipo: win.dibujar_accesorio(tp))
        act.setToolTip(_tr(ayuda) if hay else motivo_sin_presion())
        act.setEnabled(hay)
        act.setCheckable(True)
        act.setChecked(actual is not None and actual[0] == tipo)
