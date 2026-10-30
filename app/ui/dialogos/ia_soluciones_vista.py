"""Piezas visuales de «Resolver conflictos» (rediseño pedido por el usuario 2026-10-30, según su maqueta): tarjeta por
propuesta con su opción, chip del número, lo que hace, cifras (Δ cota, separación libre), el resultado de PROBARLA y,
en la recomendada, el motivo. Solo muestra lo que la app calculó (`nucleo/soluciones.Propuesta`): nada inventado."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.comun import icons, theme


def chip(texto, fondo, color, borde=None, mono=False, negrita=False):
    lbl = QtWidgets.QLabel(texto)
    fam = "font-family: Consolas, 'Cascadia Mono', monospace;" if mono else ""
    peso = "font-weight: 600;" if negrita else ""
    lbl.setStyleSheet(f"QLabel {{ background: {fondo}; color: {color}; border: 1px solid {borde or fondo};"
                      f" border-radius: 6px; padding: 2px 7px; {fam} {peso} }}")
    lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
    return lbl


def resultado(p):
    """(texto, bueno) del resultado de probar la propuesta."""
    if p.valida:
        txt = _tr("Resuelve el conflicto sin crear otros problemas")
        if p.otros_resueltos:
            txt += " " + _tr("(y resuelve {n} más)").format(n=p.otros_resueltos)
        return txt, True
    if not p.resuelve:
        return _tr("No resuelve el conflicto"), False
    return _tr("Crearía: {p}").format(p="; ".join(p.nuevos[:3]) + ("…" if len(p.nuevos) > 3 else "")), False


def cifra_cota(p):
    if p.accion in ("subir", "bajar") and p.delta_ft:
        signo = "+" if p.accion == "subir" else "−"
        return _tr("Δ Cota: {v} ft").format(v=f"{signo}{abs(p.delta_ft):.2f}")
    if p.valor_ft is not None:
        return _tr("Cota: {v} ft").format(v=f"{p.valor_ft:.2f}")
    return ""


class TarjetaPropuesta(QtWidgets.QFrame):
    """Una propuesta. Clic en cualquier parte = elegirla (la opción la marca)."""
    elegida = QtCore.Signal(str)

    def __init__(self, p, recomendada, rotulo_rec, grupo, motivo=None):
        super().__init__()
        self.p = p
        self.setObjectName("tarjetaProp")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        tk = theme.tokens()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        self.opcion = QtWidgets.QRadioButton()
        self.opcion.setAccessibleName(f"{p.id}. {p.texto}")
        grupo.addButton(self.opcion)
        self.opcion.toggled.connect(lambda on: on and self.elegida.emit(self.p.id))
        lay.addWidget(self.opcion, 0, QtCore.Qt.AlignTop)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(6)
        fila = QtWidgets.QHBoxLayout()
        fila.setSpacing(8)
        fila.addWidget(chip(p.id, tk.surface_alt, tk.text, tk.border, mono=True, negrita=True), 0, QtCore.Qt.AlignTop)
        txt = QtWidgets.QLabel(p.texto)
        txt.setWordWrap(True)
        txt.setStyleSheet(f"color: {tk.text if p.valida else tk.text_muted}; font-weight: 600; background: transparent;")
        fila.addWidget(txt, 1)
        if recomendada:
            fila.addWidget(chip("★ " + rotulo_rec, tk.soft, tk.soft_text, tk.accent), 0, QtCore.Qt.AlignTop)
        col.addLayout(fila)
        meta = QtWidgets.QHBoxLayout()
        meta.setSpacing(8)
        c = cifra_cota(p)
        if c:
            meta.addWidget(chip(c, tk.success_soft if p.valida else tk.surface_alt,
                                tk.success if p.valida else tk.text_muted, mono=True))
        if p.separacion_ft:
            sep = QtWidgets.QLabel("• " + _tr("Separación libre: {v} ft").format(v=f"{p.separacion_ft:.2f}"))
            sep.setStyleSheet(f"color: {tk.text_muted}; background: transparent;")
            meta.addWidget(sep)
        r, bueno = resultado(p)
        res = QtWidgets.QLabel(("• " if (c or p.separacion_ft) else "") + r)
        res.setWordWrap(True)
        res.setStyleSheet(f"color: {tk.text_muted if bueno else tk.danger}; background: transparent;")
        meta.addWidget(res, 1)
        col.addLayout(meta)
        if motivo is not None:                           # el porqué de la recomendada, dentro de su tarjeta
            caja = QtWidgets.QFrame()
            caja.setObjectName("motivo")
            caja.setStyleSheet(f"#motivo {{ background: {tk.surface}; border: 1px solid {tk.border_soft};"
                               f" border-radius: 8px; }}")
            cl = QtWidgets.QVBoxLayout(caja)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(4)
            cab = QtWidgets.QHBoxLayout()
            ic = QtWidgets.QLabel()
            ic.setPixmap(icons.icon("mdi:information-outline", color=tk.accent).pixmap(16, 16))
            ic.setStyleSheet("background: transparent;")
            cab.addWidget(ic)
            t = QtWidgets.QLabel(_tr("Motivo de recomendación:"))
            t.setStyleSheet(f"color: {tk.soft_text}; font-weight: 600; background: transparent;")
            cab.addWidget(t, 1)
            cl.addLayout(cab)
            cl.addWidget(motivo)
            motivo.show()
            col.addWidget(caja)
        lay.addLayout(col, 1)
        self.marcar(False)

    def marcar(self, elegida):
        tk = theme.tokens()
        borde = f"2px solid {tk.accent}" if elegida else f"1px solid {tk.border_soft}"
        self.setStyleSheet(f"#tarjetaProp {{ background: {tk.surface}; border: {borde}; border-radius: 10px; }}"
                           f" #tarjetaProp:hover {{ border-color: {tk.accent}; }}")
        self.opcion.setStyleSheet(                       # opción redonda, como la maqueta
            f"QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 9px; border: 2px solid "
            f"{tk.accent if elegida else tk.border}; background: {tk.surface}; }}"
            f" QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5,"
            f" fy:0.5, stop:0 {tk.accent}, stop:0.55 {tk.accent}, stop:0.6 {tk.surface}, stop:1 {tk.surface}); }}")
        if self.opcion.isChecked() != elegida:
            self.opcion.blockSignals(True)
            self.opcion.setChecked(elegida)
            self.opcion.blockSignals(False)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.elegida.emit(self.p.id)
        super().mousePressEvent(e)


def boton_aplicar(texto):
    """Botón principal (azul) con el atajo a la derecha, como la maqueta."""
    b = QtWidgets.QPushButton()
    b.setProperty("kind", "primary")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    lay = QtWidgets.QHBoxLayout(b)
    lay.setContentsMargins(14, 0, 8, 0)
    lay.setSpacing(8)
    b._ico = QtWidgets.QLabel()
    b._txt = QtWidgets.QLabel(texto)
    b._atajo = QtWidgets.QLabel()
    b._atajo.setText(_tr("Ctrl+↵"))
    for w in (b._ico, b._txt, b._atajo):
        w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
    lay.addWidget(b._ico)
    lay.addWidget(b._txt, 1)
    lay.addWidget(b._atajo)
    b.setMinimumHeight(38)
    return b


def estilo_boton_aplicar(b):
    tk = theme.tokens()
    on = b.isEnabled()
    color = tk.text_on_accent if on else tk.text_disabled
    b._ico.setPixmap(icons.icon("mdi:check", color=color).pixmap(16, 16))
    b._txt.setStyleSheet(f"color: {color}; font-weight: 600; background: transparent;")
    b._atajo.setStyleSheet(f"color: {color}; border: 1px solid {color}; border-radius: 4px; padding: 0 4px;"
                           f" font-size: 11px; background: transparent;")
    w = b._txt.fontMetrics().horizontalAdvance(b._txt.text()) + b._atajo.sizeHint().width() + 16 + 8 * 2 + 22
    b.setMinimumWidth(w)
