"""2.0.0 — Campos del inspector en SECCIONES, como el prototipo (General · Catálogo de Civil 3D · Cotas · Estado ·
Normativa, y la sugerencia del asistente si la utilidad está en un conflicto).

Son los MISMOS widgets de siempre: solo cambian de fila dentro de su mismo formulario (`QFormLayout.takeRow` y
se vuelven a poner en otro orden, con títulos de sección entre medio). Nada cambia de grupo, así que la lógica
que mira `isVisibleTo(gprop)` sigue igual. Lo nuevo (interruptor «Abandonada», «Aprobar…», la tarjeta del
asistente) llama a los métodos de siempre.
"""
from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R


def _filas(form):
    """[(etiqueta o None, campo)] de un QFormLayout, sacándolas sin borrar los widgets."""
    filas = []
    while form.rowCount():
        r = form.takeRow(0)
        lab = r.labelItem.widget() if r.labelItem is not None else None
        campo = r.fieldItem.widget() if r.fieldItem is not None else None
        if campo is None and r.fieldItem is not None and r.fieldItem.layout() is not None:
            campo = r.fieldItem.layout()
        if campo is None:                       # fila que ocupa todo el ancho
            campo, lab = lab, None
        filas.append((lab, campo))
    return filas


def _titulo(clave):
    lbl = R.texto(clave, "sec")
    lbl.setContentsMargins(0, 10, 0, 0)
    return lbl


def _poner(form, filas):
    for fila in filas:
        if isinstance(fila, str):
            form.addRow(_titulo(fila))
            continue
        lab, campo = fila
        if lab is None:
            form.addRow(campo)
        else:
            lab.setProperty("rol", "t2")
            form.addRow(lab, campo)


def reorganizar(win):
    # ── utilidad ──
    f = win.gprop.layout()
    filas = _filas(f)
    por_campo = {id(c): (l, c) for l, c in filas}

    def fila(w):
        return por_campo.pop(id(w))

    win.gprop.setTitle("")
    win.gprop.setFlat(True)
    win.gprop.setStyleSheet("QGroupBox { margin-top: 0; padding-top: 0; border: none; }")
    # estado: interruptor «Abandonada» (lo mismo que «Cambiar tipo» con la casilla de la izquierda)
    win.sw_abandonada = R.fila_interruptor("Abandonada", "Se dibuja a trazos; en Civil 3D, a trazos en 3D")
    win.sw_abandonada.interruptor.toggled.connect(lambda on: _abandonada(win, on))
    # normativa: lo que dice el aviso de siempre + «Cumple» / «Aprobar…»
    win.box_normativa = R.transparente(QtWidgets.QWidget())
    nl = QtWidgets.QVBoxLayout(win.box_normativa)
    nl.setContentsMargins(0, 0, 0, 0)
    nl.setSpacing(4)
    win.lbl_normas_ok = QtWidgets.QLabel()
    _bind(win.lbl_normas_ok, "setText", "Cumple las normativas")
    nl.addWidget(win.lbl_normas_ok)
    fila_ap = QtWidgets.QHBoxLayout()
    fila_ap.addStretch(1)
    win.btn_aprobar_pipe = QtWidgets.QPushButton()
    _bind(win.btn_aprobar_pipe, "setText", "Aprobar…")
    win.btn_aprobar_pipe.setProperty("kind", "ghost")
    win.btn_aprobar_pipe.clicked.connect(lambda: _aprobar(win))
    fila_ap.addWidget(win.btn_aprobar_pipe)
    nl.addLayout(fila_ap)
    # sugerencia del asistente (solo con la utilidad en un conflicto)
    win.tarjeta_sugerencia = QtWidgets.QFrame()
    win.tarjeta_sugerencia.setObjectName("tarjetaSuave")
    sl = QtWidgets.QVBoxLayout(win.tarjeta_sugerencia)
    sl.setContentsMargins(12, 10, 12, 10)
    sl.setSpacing(6)
    cab = QtWidgets.QHBoxLayout()
    win._ic_sugerencia = QtWidgets.QLabel()
    cab.addWidget(win._ic_sugerencia)
    cab.addWidget(R.texto("Sugerencia del asistente", "h3"), 1)
    sl.addLayout(cab)
    win.lbl_sugerencia = R.texto("", "t2", True, traducir=False)
    sl.addWidget(win.lbl_sugerencia)
    bt = QtWidgets.QHBoxLayout()
    win.btn_sugerencia = QtWidgets.QPushButton()
    _bind(win.btn_sugerencia, "setText", "Ver opciones")
    win.btn_sugerencia.setProperty("kind", "primary")
    win.btn_sugerencia.clicked.connect(lambda: _ver_soluciones(win))
    bt.addWidget(win.btn_sugerencia)
    bt.addStretch(1)
    sl.addLayout(bt)

    orden = [fila(win.box_vertice), "General", fila(win.prop_name)]
    for l, c in list(por_campo.values()):            # «Tipo» va con su «+» en un contenedor
        if c is not None and c is not win.lbl_pendiente and l is not None and \
                l is not win.lbl_prop_amp and l not in (win.lbl_prop_inv0, win.lbl_prop_inv1,
                                                        win.lbl_prop_family, win.lbl_prop_size) and \
                c is not win.prop_nettype:
            orden.append(fila(c))
    orden += [fila(win.prop_amp), fila(win.prop_nettype),
              "Catálogo de Civil 3D", fila(win.prop_family), fila(win._prop_size_box),
              "Cotas", fila(win.prop_inv0), fila(win.prop_inv1), fila(win.lbl_pendiente),
              "Estado", (None, win.sw_abandonada),
              "Normativa", fila(win.lbl_normas_pipe), (None, win.box_normativa),
              (None, win.tarjeta_sugerencia)]
    orden += list(por_campo.values())                # lo que quede, al final (nada se pierde)
    _poner(f, orden)

    # ── buzón ──
    if getattr(win, "gprop_bz", None) is not None:
        fb = win.gprop_bz.layout()
        filas = _filas(fb)
        win.gprop_bz.setTitle("")
        win.gprop_bz.setFlat(True)
        win.gprop_bz.setStyleSheet("QGroupBox { margin-top: 0; padding-top: 0; border: none; }")
        nuevas = ["General"]
        for l, c in filas:
            if c is win._lbl_sld_len or l is win._lbl_sld_len:
                nuevas.append("Sólido 3D")
            nuevas.append((l, c))
        _poner(fb, nuevas)
    # ── curva ──
    if getattr(win, "gprop_curve", None) is not None:
        fc = win.gprop_curve.layout()
        filas = _filas(fc)
        win.gprop_curve.setTitle("")
        win.gprop_curve.setFlat(True)
        win.gprop_curve.setStyleSheet("QGroupBox { margin-top: 0; padding-top: 0; border: none; }")
        _poner(fc, ["Curva"] + filas)
    _theme.THEME_BUS.changed.connect(lambda _n: refrescar(win))


def refrescar(win):
    """Al cambiar la selección: interruptor, normativa y sugerencia de la utilidad elegida."""
    if getattr(win, "sw_abandonada", None) is None:
        return
    t = _theme.tokens()
    i = getattr(win, "sel_pipe", -1)
    hay = 0 <= i < len(win.pipes)
    cab = getattr(win, "cabecera_inspector", None)
    hay = hay and (cab is None or not cab.isHidden())          # sin nada elegido en la lista: nada
    sw = win.sw_abandonada.interruptor
    sw.blockSignals(True)
    sw.setChecked(bool(hay and win.pipes[i].get("ab")))
    sw.blockSignals(False)
    sw.update()
    avisos = _avisos(win, i) if hay else []
    win.lbl_normas_ok.setVisible(hay and not avisos)
    win.lbl_normas_ok.setStyleSheet(f"color:{t.success};")
    win.btn_aprobar_pipe.setVisible(bool(avisos))
    conf = [c for c in getattr(win, "_conflictos", None) or [] if i in (c.pipes or [])] if hay else []
    win.tarjeta_sugerencia.setVisible(bool(conf))
    if conf:
        c = conf[0]
        win.lbl_sugerencia.setText(_tr("{id}: {titulo}. El asistente propone soluciones y prueba cada una en una "
                                       "copia del proyecto.").format(id=c.id, titulo=_tr(c.titulo)))
        win._conflicto_sugerencia = c.id
        win._ic_sugerencia.setPixmap(_icon("mdi:creation", color=t.accent).pixmap(16, 16))


def _avisos(win, i):
    return [a for a in getattr(win, "_normas_avisos", None) or []
            if getattr(a, "pipe", None) == i and not getattr(a, "aprobado", False)]


def _abandonada(win, on):
    i = getattr(win, "sel_pipe", -1)
    if not (0 <= i < len(win.pipes)) or bool(win.pipes[i].get("ab")) == bool(on):
        return
    win._push()
    win.pipes[i]["ab"] = bool(on)
    win._dirty = True
    win._refresh_lists()
    win._reselect_pipes([i])
    win._redraw()


def _aprobar(win):
    i = getattr(win, "sel_pipe", -1)
    avisos = _avisos(win, i)
    if not avisos:
        return
    nota, ok = QtWidgets.QInputDialog.getText(win, _tr("Aprobar avisos"),
                                              _tr("Nota (opcional): por qué se aprueba"))
    if ok:
        win.aprobar_avisos(avisos, nota)


def _ver_soluciones(win):
    cid = getattr(win, "_conflicto_sugerencia", None)
    if cid:
        win.abrir_soluciones(cid)
