"""dialogs.py — Diálogos de la app que no forman parte del flujo principal.

Ventanas de ayuda/info (Acerca de, Manual, Atajos) y de gestión de familias
personalizadas del catálogo (instalar / desinstalar). Cada función recibe la
ventana principal `win` (la clase Main de app_window.py) como padre y para leer
su estado (versión/idioma de Civil 3D, refrescar paneles, etc.).

Extraído de app_window.py sin cambios de comportamiento: las mismas ventanas, con
las mismas conexiones; en app_window.py quedan métodos delgados que delegan aquí,
así los menús y llamadas existentes (self.show_about, self.open_install_family_dialog…)
siguen funcionando igual.
"""
import os

from PySide6 import QtCore, QtGui, QtWidgets

from model import VERSION, CHANGELOG
from ui_common import DOWNLOADS
import theme as _theme
from i18n import t as _tr


# ─────────────────────────── Familias personalizadas ───────────────────────────
def open_install_family_dialog(win):
    """Instala UNA familia personalizada en el catálogo Civil 3D del año e
    idioma seleccionados en la UI. Adaptación del script `install_c3d_family.py`
    que ya está validado.

    Flujo:
      1. Usuario elige la carpeta de la familia (con .xml, .dwg, .bmp adentro).
      2. Se detecta kind/units/shape leyendo el XML y el nombre.
      3. Se copia la carpeta al subcatálogo correcto del año/idioma activos.
      4. Se registra la familia en el .apc (backup automático con timestamp).
      5. Se le dice al usuario que corra PREPARAR_FAMILIAS en Civil 3D (que
         regenera el catálogo y añade las familias a una PartsList)."""
    import civil_catalog as _cc

    if not win.civil_year:
        QtWidgets.QMessageBox.warning(
            win, _tr("Sin versión de Civil 3D"),
            _tr("Elige una versión de Civil 3D en el toolbar antes de instalar familias."))
        return
    cur_lang = _cc._current_lang
    if not cur_lang:
        QtWidgets.QMessageBox.warning(
            win, _tr("Sin idioma seleccionado"),
            _tr("Elige un idioma en el toolbar antes de instalar familias."))
        return

    dlg = QtWidgets.QDialog(win)
    dlg.setWindowTitle(_tr("Instalar familia personalizada — Civil 3D {anio} / {idioma}").format(
        anio=win.civil_year, idioma=cur_lang))
    dlg.resize(760, 480)
    lay = QtWidgets.QVBoxLayout(dlg)

    header = QtWidgets.QLabel(_tr(
        "<b>Elige la carpeta de UNA familia</b> — debe contener el "
        "<code>.xml</code>, el <code>.dwg</code> del Part Builder y el "
        "<code>.bmp</code> (miniatura).<br><br>"
        "Se instalará en el catálogo de <b>Civil 3D {anio} ({idioma})</b>. "
        "El script detecta automáticamente si es tubería o estructura, sus unidades "
        "y la forma, copia los archivos y registra la familia en el <code>.apc</code> "
        "(con backup).<br><br>"
        "Al terminar, ejecuta <b>PREPARAR_FAMILIAS</b> en Civil 3D — regenera el "
        "catálogo y te deja elegir qué familias añadir a la lista de piezas del dibujo.").format(
            anio=win.civil_year, idioma=cur_lang))
    header.setWordWrap(True); lay.addWidget(header)

    # Selector carpeta origen
    row = QtWidgets.QHBoxLayout()
    row.addWidget(QtWidgets.QLabel(_tr("Carpeta de la familia:")))
    win._if_src = QtWidgets.QLineEdit(); win._if_src.setReadOnly(True)
    prev = getattr(win, "_last_family_folder", None)
    if prev and os.path.isdir(prev): win._if_src.setText(prev)
    btn_browse = QtWidgets.QPushButton(_tr("Elegir…"))
    row.addWidget(win._if_src, 1); row.addWidget(btn_browse)
    lay.addLayout(row)

    # Preview de lo que se detectó
    preview_lbl = QtWidgets.QLabel(_tr("<i>Elige una carpeta para ver qué se detecta.</i>"))
    preview_lbl.setWordWrap(True); preview_lbl.setTextFormat(QtCore.Qt.RichText)
    t = _theme.tokens()
    preview_lbl.setStyleSheet(f"color:{t.text_muted}; background:{t.surface_alt}; padding:8px; border-radius:4px;")
    lay.addWidget(preview_lbl, 1)

    bb = QtWidgets.QDialogButtonBox()
    btn_install = bb.addButton(_tr("Instalar familia"), QtWidgets.QDialogButtonBox.AcceptRole)
    btn_close = bb.addButton(_tr("Cerrar"), QtWidgets.QDialogButtonBox.RejectRole)
    btn_install.setEnabled(False)
    lay.addWidget(bb)

    def _refresh_preview(path):
        btn_install.setEnabled(False)
        if not path or not os.path.isdir(path):
            preview_lbl.setText(_tr("<i>Elige una carpeta para ver qué se detecta.</i>"))
            return
        fams = _cc.scan_family_folder_preview(path)
        if not fams:
            preview_lbl.setText(
                _tr("<span style='color:#e06060;'>❌ No encontré ningún .xml con "
                ".dwg hermano en esta carpeta.</span>"))
            return

        def _dot(v):
            if v: return f"<span style='color:#3fbf3f;'>{v}</span>"
            return "<span style='color:#e06060;'>⚠</span>"

        lines = ["<b>" + _tr("{n} familia(s) detectadas en la carpeta:").format(n=len(fams)) + "</b>",
                 "<span style='color:#8fa6bf;'>" + _tr("Se copiará la carpeta al subcatálogo "
                 "correspondiente y cada .xml se registrará como familia independiente "
                 "en el .apc.") + "</span>", ""]
        for f in fams:
            lines.append(
                f"• <code>{f['name']}</code> — "
                + _tr("tipo {tipo} · unidades {unidades} · shape {shape}").format(
                    tipo=_dot(f['kind']), unidades=_dot(f['units']), shape=_dot(f['shape']))
                + ("" if f['bmp_ok'] else
                   "  &nbsp;<span style='color:#e0a020;'>" + _tr("(sin .bmp)") + "</span>"))
        # Destinos por (kind,units)
        grupos = {}
        for f in fams:
            if f['kind'] and f['units']:
                grupos.setdefault((f['kind'], f['units']),  []).append(f['name'])
        if grupos:
            lang_root = _cc._lang_root(win.civil_year, cur_lang)
            lines.append("")
            lines.append("<b>" + _tr("Destinos:") + "</b>")
            for (k, u), names in grupos.items():
                cat = _cc._CATALOG_DIRS.get((k, u), "?")
                dest = os.path.join(lang_root or "?", "Pipes Catalog", cat)
                lines.append("  " + _tr("{n} familia(s) → {destino}").format(
                    n=len(names), destino=f"<code>{dest}</code>"))
        preview_lbl.setText("<br>".join(lines))
        btn_install.setEnabled(any(f['kind'] and f['units'] and f['shape'] for f in fams))

    def _pick():
        start = getattr(win, "_last_family_folder", None) or DOWNLOADS
        path = QtWidgets.QFileDialog.getExistingDirectory(
            dlg, _tr("Carpeta de familias (.xml + .dwg + .bmp por familia)"), start)
        if not path: return
        win._last_family_folder = path
        win._if_src.setText(path); _refresh_preview(path)

    def _do_install():
        src = win._if_src.text().strip()
        if not src or not os.path.isdir(src): return
        res = _cc.install_family_folder(src, win.civil_year, cur_lang)
        if not res["ok"]:
            QtWidgets.QMessageBox.critical(dlg, _tr("Error al instalar"), res["error"] or res["summary"])
            return
        msg = res["summary"] + "\n\n" + _tr(
            "AHORA en Civil 3D:\n"
            "  · Ejecuta el comando  PREPARAR_FAMILIAS\n"
            "    (regenera el catálogo y te deja elegir qué familias\n"
            "    añadir a la Parts List del dibujo actual).")
        # Refrescar inmediatamente el combo de familias del panel activo
        # para que el usuario vea las familias recién instaladas sin
        # tener que deseleccionar/re-seleccionar la utilidad.
        try: win._refresh_catalog_panels()
        except Exception: pass
        QtWidgets.QMessageBox.information(dlg, _tr("Familias instaladas"), msg)

    btn_browse.clicked.connect(_pick)
    btn_install.clicked.connect(_do_install)
    btn_close.clicked.connect(dlg.reject)
    if win._if_src.text(): _refresh_preview(win._if_src.text())
    dlg.exec()


def open_uninstall_family_dialog(win):
    import civil_catalog as _cc
    if not win.civil_year:
        QtWidgets.QMessageBox.warning(win, _tr("Sin versión"),
            _tr("Elige una versión de Civil 3D en el toolbar antes de desinstalar familias."))
        return
    cur_lang = getattr(win, "civil_lang", None) or (
        win.cmb_lang.currentData() if hasattr(win, "cmb_lang") else None)
    if not cur_lang:
        QtWidgets.QMessageBox.warning(win, _tr("Sin idioma"),
            _tr("Elige un idioma en el toolbar antes de desinstalar familias."))
        return

    fams = _cc.installed_custom_families(win.civil_year)
    if not fams:
        QtWidgets.QMessageBox.information(win, _tr("Sin familias personalizadas"),
            _tr("No se encontraron familias personalizadas instaladas en Civil 3D {anio}.").format(
                anio=win.civil_year))
        return

    dlg = QtWidgets.QDialog(win)
    dlg.setWindowTitle(_tr("Desinstalar familias — Civil 3D {anio} / {idioma}").format(
        anio=win.civil_year, idioma=cur_lang))
    dlg.setMinimumSize(500, 400)
    lay = QtWidgets.QVBoxLayout(dlg)

    lay.addWidget(QtWidgets.QLabel(_tr(
        "<b>Familias personalizadas en Civil 3D {anio}</b><br>"
        "Marca las que deseas desinstalar:").format(anio=win.civil_year)))

    lw = QtWidgets.QListWidget()
    lw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
    for f in fams:
        tipo = "Estructura" if f["kind"] == "structure" else "Tubería"
        text = f"{f['display_name']}  ({tipo} — {f['subfolder']})"
        item = QtWidgets.QListWidgetItem(text)
        item.setData(256, f)
        lw.addItem(item)
    lay.addWidget(lw)

    bb = QtWidgets.QDialogButtonBox()
    btn_del = bb.addButton(_tr("Desinstalar seleccionadas"), QtWidgets.QDialogButtonBox.AcceptRole)
    btn_del.setProperty("danger", True)
    btn_close = bb.addButton(_tr("Cerrar"), QtWidgets.QDialogButtonBox.RejectRole)
    lay.addWidget(bb)

    def _do_uninstall():
        sel = [lw.item(i).data(256) for i in range(lw.count()) if lw.item(i).isSelected()]
        if not sel:
            QtWidgets.QMessageBox.warning(dlg, _tr("Sin selección"), _tr("Selecciona al menos una familia."))
            return
        names = "\n".join(f"  · {s['display_name']}" for s in sel)
        r = QtWidgets.QMessageBox.question(
            dlg, _tr("Confirmar desinstalación"),
            _tr("¿Desinstalar {n} familia(s)?\n\n{nombres}\n\n"
                "Se quitarán del catálogo de Civil 3D. Esta acción se puede revertir "
                "reinstalando las familias desde su carpeta original.").format(
                n=len(sel), nombres=names),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if r != QtWidgets.QMessageBox.Yes:
            return
        ok_count = 0
        errors = []
        for s in sel:
            res = _cc.uninstall_family(
                win.civil_year, s["name"], s["kind"], s["subfolder"], cur_lang)
            if res["ok"]:
                ok_count += 1
            else:
                errors.append(f"{s['display_name']}: {res['error']}")
        try:
            win._refresh_catalog_panels()
        except Exception:
            pass
        if errors:
            QtWidgets.QMessageBox.warning(dlg, _tr("Errores"),
                _tr("Se desinstalaron {ok} de {n} familias.\n\nErrores:\n{errores}").format(
                    ok=ok_count, n=len(sel), errores="\n".join(errors)))
        else:
            QtWidgets.QMessageBox.information(dlg, _tr("Familias desinstaladas"),
                _tr("Se desinstalaron {ok} familia(s) correctamente.\n\n"
                    "En Civil 3D ejecuta PREPARAR_FAMILIAS para actualizar la Parts List.").format(
                    ok=ok_count))
        dlg.accept()

    btn_del.clicked.connect(_do_uninstall)
    btn_close.clicked.connect(dlg.reject)
    dlg.exec()


# ─────────────────────────── Ayuda / info ───────────────────────────
def show_html(win, title, html, w=780, h=660):
    dlg = QtWidgets.QDialog(win); dlg.setWindowTitle(title); dlg.resize(w, h)
    lay = QtWidgets.QVBoxLayout(dlg); tb = QtWidgets.QTextBrowser(); tb.setOpenExternalLinks(True)
    t = _theme.tokens()
    tb.setStyleSheet(f"background:{t.surface};color:{t.text};font-size:14px;"); tb.setHtml(html)
    btn = QtWidgets.QPushButton(_tr("Cerrar")); btn.clicked.connect(dlg.accept)
    lay.addWidget(tb); lay.addWidget(btn); dlg.exec()


def show_about(win):
    dlg = QtWidgets.QDialog(win); dlg.setWindowTitle(_tr("Acerca de")); dlg.resize(760, 680)
    lay = QtWidgets.QVBoxLayout(dlg)
    head = QtWidgets.QLabel(
        f"<h2>Asistente C3D</h2>"
        f"<p><b>{_tr('Versión')} {VERSION}</b> · " + _tr("para ingeniería civil (agua, alcantarillado, gas, "
        "eléctrico, telefonía, drenaje).") + "</p>"
        "<p>" + _tr("Convierte un PDF de plano a DXF y te deja marcar utilidades, Multileaders y notas "
        "sobre la imagen, exportando todo en las mismas coordenadas para abrirlo en Civil 3D.") + "</p>"
        f"<p style='color:#888;'>GVR Engineering · sistemas.gvrpe@gmail.com</p>")
    head.setWordWrap(True)
    t = _theme.tokens()
    head.setStyleSheet(f"color:{t.text};"); lay.addWidget(head)
    box = QtWidgets.QToolBox()
    box.setStyleSheet(f"QToolBox::tab{{background:{t.surface_alt};color:{t.text};border:1px solid {t.border};}}"
                      f"QToolBox::tab:selected{{background:{t.accent};color:{t.text_on_accent};font-weight:bold;}}")
    icon = {"added":   ("#5fd35f", "✚ " + _tr("nueva")),
            "removed": ("#e06060", "✖ " + _tr("quitada")),
            "fixed":   ("#6cc5e0", "✎ " + _tr("corregida")),
            "changed": ("#e0c060", "↻ " + _tr("cambiada")),
            "base":    ("#cfcfcf", "•")}
    default = ("#cfcfcf", "•")
    for ver, items in CHANGELOG:
        tb = QtWidgets.QTextBrowser(); tb.setStyleSheet(f"background:{t.surface};color:{t.text};border:none;")
        # Nota: `t` en el f-string aquí es el mensaje del changelog, sombreando
        # a `_theme.tokens()`. Se traduce cada entrada por separado.
        lis = "".join(f'<li style="color:{icon.get(s, default)[0]};margin-bottom:4px;">'
                      f'<b>[{icon.get(s, default)[1]}]</b> {_tr(t)}</li>' for s, t in items)
        tb.setHtml(f"<ul>{lis}</ul>"); box.addItem(tb, f"v{ver}")
    lay.addWidget(box, 1)
    btn = QtWidgets.QPushButton(_tr("Cerrar")); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
    dlg.exec()


def show_manual(win):
    """Manual de usuario: visor por capítulos (ver manual_dialog.py). El texto
    vive en ``docs/manual.<idioma>.html`` (ver ``i18n.load_doc``)."""
    from manual_dialog import show_manual as _mostrar
    _mostrar(win)


def show_shortcuts(win):
    t = _theme.tokens()
    rows = []
    for a in win.findChildren(QtGui.QAction):
        sc = a.shortcut().toString()
        txt = a.text().replace("&", "")
        if sc and txt:
            rows.append((sc, txt))
    for sc_w in win.findChildren(QtGui.QShortcut):
        sc = sc_w.key().toString()
        if sc:
            rows.append((sc, ""))
    seen = set()
    unique = []
    for k, d in rows:
        if k not in seen:
            seen.add(k); unique.append((k, d))
    extra = [("Enter",        _tr("Aplicar: finaliza utilidad/zona, o agrega texto/edición")),
             ("Escape",       _tr("Quitar la selección; si no hay, salir del modo")),
             (_tr("Doble clic"),   _tr("Sobre un texto: editarlo")),
             (_tr("Clic derecho"), _tr("Finaliza línea/zona; en editar, elimina el vértice")),
             (_tr("Rueda"),        _tr("Zoom · Botón central + arrastrar: desplazar"))]
    for k, d in extra:
        if k not in seen:
            seen.add(k); unique.append((k, d))
    body = "".join(f'<tr><td style="padding:4px 14px;color:{t.accent};"><b>{k}</b></td>'
                   f'<td style="padding:4px;">{d}</td></tr>' for k, d in unique)
    title = _tr("Atajos de teclado")
    show_html(win, title, f"<h2>{title}</h2><table>{body}</table>", 640, 500)


# ─────────────────────────── Opciones (Preferencias) ───────────────────────────
def show_options(win):
    """Diálogo de opciones globales de la app. Hoy solo trae **Idioma** (con
    intención de crecer). Al aceptar, aplica los cambios en vivo — cambiar el
    idioma emite ``LANG_BUS.changed`` y los widgets suscritos se re-traducen.

    Textos ya materializados que NO estén suscritos al bus (algunos labels
    puntuales o menús contextuales creados dinámicamente) pueden requerir
    reabrir su ventana para verse en el nuevo idioma. Se avisa al usuario."""
    import i18n as _i18n

    dlg = QtWidgets.QDialog(win)
    dlg.setWindowTitle(_i18n.t("Opciones"))
    dlg.setMinimumWidth(420)
    dlg.setModal(True)

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(20, 20, 20, 16); root.setSpacing(14)

    # ── Sección: Idioma ──
    grp_lang = QtWidgets.QGroupBox(_i18n.t("Idioma"))
    gl = QtWidgets.QFormLayout(grp_lang)
    cmb = QtWidgets.QComboBox()
    # Mostramos el nombre en el idioma ACTIVO (así "Español" / "Spanish" según
    # cómo tenga configurada la UI ahora).
    cmb.addItem(_i18n.t("Español"), _tr("es"))
    cmb.addItem(_i18n.t("Inglés"), _tr("en"))
    current = _i18n.get_lang()
    for i in range(cmb.count()):
        if cmb.itemData(i) == current:
            cmb.setCurrentIndex(i); break
    gl.addRow(_i18n.t("Idioma") + ":", cmb)
    hint = QtWidgets.QLabel(
        _i18n.t("El cambio se aplica al instante en menús y paneles principales. "
                "Algunas ventanas ya abiertas pueden requerir cerrarse y volver "
                "a abrirse para verse completamente en el nuevo idioma."))
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color:{_theme.tokens().text_muted}; font-size:12px;")
    gl.addRow(hint)
    root.addWidget(grp_lang)

    # ── Botones (Aceptar / Cancelar) ──
    btns = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    btns.button(QtWidgets.QDialogButtonBox.Ok).setText(_i18n.t("Aceptar"))
    btns.button(QtWidgets.QDialogButtonBox.Cancel).setText(_i18n.t("Cancelar"))
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    root.addWidget(btns)

    if dlg.exec() == QtWidgets.QDialog.Accepted:
        new_lang = cmb.currentData()
        if new_lang != _i18n.get_lang():
            _i18n.set_lang(new_lang)   # emite LANG_BUS.changed
