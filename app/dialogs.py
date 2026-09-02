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

from PySide6 import QtCore, QtWidgets

from model import VERSION, CHANGELOG
from ui_common import DOWNLOADS


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
            win, "Sin versión de Civil 3D",
            "Elige una versión de Civil 3D en el toolbar antes de instalar familias.")
        return
    cur_lang = _cc._current_lang
    if not cur_lang:
        QtWidgets.QMessageBox.warning(
            win, "Sin idioma seleccionado",
            "Elige un idioma en el toolbar antes de instalar familias.")
        return

    dlg = QtWidgets.QDialog(win)
    dlg.setWindowTitle(f"Instalar familia personalizada — Civil 3D {win.civil_year} / {cur_lang}")
    dlg.resize(760, 480)
    lay = QtWidgets.QVBoxLayout(dlg)

    header = QtWidgets.QLabel(
        f"<b>Elige la carpeta de UNA familia</b> — debe contener el "
        f"<code>.xml</code>, el <code>.dwg</code> del Part Builder y el "
        f"<code>.bmp</code> (miniatura).<br><br>"
        f"Se instalará en el catálogo de <b>Civil 3D {win.civil_year} ({cur_lang})</b>. "
        f"El script detecta automáticamente si es tubería o estructura, sus unidades "
        f"y la forma, copia los archivos y registra la familia en el <code>.apc</code> "
        f"(con backup).<br><br>"
        f"Al terminar, ejecuta <b>PREPARAR_FAMILIAS</b> en Civil 3D — regenera el "
        f"catálogo y te deja elegir qué familias añadir a la lista de piezas del dibujo.")
    header.setWordWrap(True); lay.addWidget(header)

    # Selector carpeta origen
    row = QtWidgets.QHBoxLayout()
    row.addWidget(QtWidgets.QLabel("Carpeta de la familia:"))
    win._if_src = QtWidgets.QLineEdit(); win._if_src.setReadOnly(True)
    prev = getattr(win, "_last_family_folder", None)
    if prev and os.path.isdir(prev): win._if_src.setText(prev)
    btn_browse = QtWidgets.QPushButton("Elegir…")
    row.addWidget(win._if_src, 1); row.addWidget(btn_browse)
    lay.addLayout(row)

    # Preview de lo que se detectó
    preview_lbl = QtWidgets.QLabel("<i>Elige una carpeta para ver qué se detecta.</i>")
    preview_lbl.setWordWrap(True); preview_lbl.setTextFormat(QtCore.Qt.RichText)
    preview_lbl.setStyleSheet("color:#b8c6df; background:#333a4a; padding:8px; border-radius:4px;")
    lay.addWidget(preview_lbl, 1)

    bb = QtWidgets.QDialogButtonBox()
    btn_install = bb.addButton("Instalar familia", QtWidgets.QDialogButtonBox.AcceptRole)
    btn_close = bb.addButton("Cerrar", QtWidgets.QDialogButtonBox.RejectRole)
    btn_install.setEnabled(False)
    lay.addWidget(bb)

    def _refresh_preview(path):
        btn_install.setEnabled(False)
        if not path or not os.path.isdir(path):
            preview_lbl.setText("<i>Elige una carpeta para ver qué se detecta.</i>")
            return
        fams = _cc.scan_family_folder_preview(path)
        if not fams:
            preview_lbl.setText(
                "<span style='color:#e06060;'>❌ No encontré ningún .xml con "
                ".dwg hermano en esta carpeta.</span>")
            return

        def _dot(v):
            if v: return f"<span style='color:#3fbf3f;'>{v}</span>"
            return "<span style='color:#e06060;'>⚠</span>"

        lines = [f"<b>{len(fams)} familia(s) detectadas en la carpeta:</b>",
                 "<span style='color:#8fa6bf;'>Se copiará la carpeta al subcatálogo "
                 "correspondiente y cada .xml se registrará como familia independiente "
                 "en el .apc.</span>", ""]
        for f in fams:
            lines.append(
                f"• <code>{f['name']}</code> — tipo {_dot(f['kind'])} · "
                f"unidades {_dot(f['units'])} · shape {_dot(f['shape'])}"
                + ("" if f['bmp_ok'] else "  &nbsp;<span style='color:#e0a020;'>(sin .bmp)</span>"))
        # Destinos por (kind,units)
        grupos = {}
        for f in fams:
            if f['kind'] and f['units']:
                grupos.setdefault((f['kind'], f['units']),  []).append(f['name'])
        if grupos:
            lang_root = _cc._lang_root(win.civil_year, cur_lang)
            lines.append("")
            lines.append("<b>Destinos:</b>")
            for (k, u), names in grupos.items():
                cat = _cc._CATALOG_DIRS.get((k, u), "?")
                dest = os.path.join(lang_root or "?", "Pipes Catalog", cat)
                lines.append(f"  {len(names)} familia(s) → <code>{dest}</code>")
        preview_lbl.setText("<br>".join(lines))
        btn_install.setEnabled(any(f['kind'] and f['units'] and f['shape'] for f in fams))

    def _pick():
        start = getattr(win, "_last_family_folder", None) or DOWNLOADS
        path = QtWidgets.QFileDialog.getExistingDirectory(
            dlg, "Carpeta de familias (.xml + .dwg + .bmp por familia)", start)
        if not path: return
        win._last_family_folder = path
        win._if_src.setText(path); _refresh_preview(path)

    def _do_install():
        src = win._if_src.text().strip()
        if not src or not os.path.isdir(src): return
        res = _cc.install_family_folder(src, win.civil_year, cur_lang)
        if not res["ok"]:
            QtWidgets.QMessageBox.critical(dlg, "Error al instalar", res["error"] or res["summary"])
            return
        msg = res["summary"] + (
            "\n\nAHORA en Civil 3D:\n"
            "  · Ejecuta el comando  PREPARAR_FAMILIAS\n"
            "    (regenera el catálogo y te deja elegir qué familias\n"
            "    añadir a la Parts List del dibujo actual).")
        # Refrescar inmediatamente el combo de familias del panel activo
        # para que el usuario vea las familias recién instaladas sin
        # tener que deseleccionar/re-seleccionar la utilidad.
        try: win._refresh_catalog_panels()
        except Exception: pass
        QtWidgets.QMessageBox.information(dlg, "Familias instaladas", msg)

    btn_browse.clicked.connect(_pick)
    btn_install.clicked.connect(_do_install)
    btn_close.clicked.connect(dlg.reject)
    if win._if_src.text(): _refresh_preview(win._if_src.text())
    dlg.exec()


def open_uninstall_family_dialog(win):
    import civil_catalog as _cc
    if not win.civil_year:
        QtWidgets.QMessageBox.warning(win, "Sin versión",
            "Elige una versión de Civil 3D en el toolbar antes de desinstalar familias.")
        return
    cur_lang = getattr(win, "civil_lang", None) or (
        win.cmb_lang.currentData() if hasattr(win, "cmb_lang") else None)
    if not cur_lang:
        QtWidgets.QMessageBox.warning(win, "Sin idioma",
            "Elige un idioma en el toolbar antes de desinstalar familias.")
        return

    fams = _cc.installed_custom_families(win.civil_year)
    if not fams:
        QtWidgets.QMessageBox.information(win, "Sin familias personalizadas",
            f"No se encontraron familias personalizadas instaladas en Civil 3D {win.civil_year}.")
        return

    dlg = QtWidgets.QDialog(win)
    dlg.setWindowTitle(f"Desinstalar familias — Civil 3D {win.civil_year} / {cur_lang}")
    dlg.setMinimumSize(500, 400)
    lay = QtWidgets.QVBoxLayout(dlg)

    lay.addWidget(QtWidgets.QLabel(
        f"<b>Familias personalizadas en Civil 3D {win.civil_year}</b><br>"
        "Marca las que deseas desinstalar:"))

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
    btn_del = bb.addButton("Desinstalar seleccionadas", QtWidgets.QDialogButtonBox.AcceptRole)
    btn_del.setProperty("danger", True)
    btn_close = bb.addButton("Cerrar", QtWidgets.QDialogButtonBox.RejectRole)
    lay.addWidget(bb)

    def _do_uninstall():
        sel = [lw.item(i).data(256) for i in range(lw.count()) if lw.item(i).isSelected()]
        if not sel:
            QtWidgets.QMessageBox.warning(dlg, "Sin selección", "Selecciona al menos una familia.")
            return
        names = "\n".join(f"  · {s['display_name']}" for s in sel)
        r = QtWidgets.QMessageBox.question(
            dlg, "Confirmar desinstalación",
            f"¿Desinstalar {len(sel)} familia(s)?\n\n{names}\n\n"
            "Se quitarán del catálogo de Civil 3D. Esta acción se puede revertir "
            "reinstalando las familias desde su carpeta original.",
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
            QtWidgets.QMessageBox.warning(dlg, "Errores",
                f"Se desinstalaron {ok_count} de {len(sel)} familias.\n\nErrores:\n" +
                "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(dlg, "Familias desinstaladas",
                f"Se desinstalaron {ok_count} familia(s) correctamente.\n\n"
                "En Civil 3D ejecuta PREPARAR_FAMILIAS para actualizar la Parts List.")
        dlg.accept()

    btn_del.clicked.connect(_do_uninstall)
    btn_close.clicked.connect(dlg.reject)
    dlg.exec()


# ─────────────────────────── Ayuda / info ───────────────────────────
def show_html(win, title, html, w=780, h=660):
    dlg = QtWidgets.QDialog(win); dlg.setWindowTitle(title); dlg.resize(w, h)
    lay = QtWidgets.QVBoxLayout(dlg); tb = QtWidgets.QTextBrowser(); tb.setOpenExternalLinks(True)
    tb.setStyleSheet("background:#1e1e1e;color:#e8e8e8;font-size:14px;"); tb.setHtml(html)
    btn = QtWidgets.QPushButton("Cerrar"); btn.clicked.connect(dlg.accept)
    lay.addWidget(tb); lay.addWidget(btn); dlg.exec()


def show_about(win):
    dlg = QtWidgets.QDialog(win); dlg.setWindowTitle("Acerca de"); dlg.resize(760, 680)
    lay = QtWidgets.QVBoxLayout(dlg)
    head = QtWidgets.QLabel(
        f"<h2>Asistente C3D</h2>"
        f"<p><b>Versión {VERSION}</b> · para ingeniería civil (agua, alcantarillado, gas, "
        f"eléctrico, telefonía, drenaje).</p>"
        f"<p>Convierte un PDF de plano a DXF y te deja marcar utilidades, Multileaders y notas "
        f"sobre la imagen, exportando todo en las mismas coordenadas para abrirlo en Civil 3D.</p>"
        f"<p style='color:#888;'>GVR Engineering · sistemas.gvrpe@gmail.com</p>")
    head.setWordWrap(True); head.setStyleSheet("color:#e8e8e8;"); lay.addWidget(head)
    box = QtWidgets.QToolBox()
    box.setStyleSheet("QToolBox::tab{background:#333;color:#ddd;border:1px solid #555;}"
                      "QToolBox::tab:selected{background:#3c5a99;color:white;font-weight:bold;}")
    icon = {"added": ("#5fd35f", "✚ nueva"), "removed": ("#e06060", "✖ quitada"),
            "fixed": ("#6cc5e0", "✎ corregida"), "changed": ("#e0c060", "↻ cambiada"),
            "base": ("#cfcfcf", "•")}
    default = ("#cfcfcf", "•")
    for ver, items in CHANGELOG:
        tb = QtWidgets.QTextBrowser(); tb.setStyleSheet("background:#1e1e1e;color:#e8e8e8;border:none;")
        lis = "".join(f'<li style="color:{icon.get(s, default)[0]};margin-bottom:4px;">'
                      f'<b>[{icon.get(s, default)[1]}]</b> {t}</li>' for s, t in items)
        tb.setHtml(f"<ul>{lis}</ul>"); box.addItem(tb, f"v{ver}")
    lay.addWidget(box, 1)
    btn = QtWidgets.QPushButton("Cerrar"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
    dlg.exec()


def show_manual(win):
    """Ventana del manual de usuario. Es HTML sencillo dentro de un
    QTextBrowser (visor de texto enriquecido); nada de red ni servidor."""
    html = """
    <h2>Manual de usuario — v1.0.1</h2>
    <p><i>Pipeline PDF → CAD → Civil 3D para redes de utilidad (agua, alcantarillado,
    drenaje, gas, electricidad, telecomunicaciones). Trabaja en unidades imperiales (pies).</i></p>

    <h3>1. Abrir el plano</h3>
    <p><b>Archivo → Abrir PDF…</b> (o arrastralo). Cambia de página y ajusta la
    transparencia en la sección <b>Vista y páginas</b>. Rueda = zoom, botón central = pan.</p>

    <h3>2. Dibujar una utilidad</h3>
    <p>Acordeón <b>Dibujar utilidad</b> → elige el tipo (agua, alcantarillado, drenaje,
    gas, eléctrico, telecom) → clic en cada vértice, <b>Enter</b> finaliza.</p>

    <h3>3. Propiedades de la tubería</h3>
    <p>Selecciona la tubería en el inventario. En <b>Propiedades</b>:</p>
    <ul>
      <li><b>Familia de tubería</b> y <b>Tamaño</b>: se leen del catálogo Civil 3D
          instalado (selecciónalo en la barra superior).</li>
      <li><b>Elev. rasante inicial/final</b> en pies (opcional; el plugin puede autoderivar).</li>
      <li><b>Material</b> (lista fija que se mapea al catálogo).</li>
      <li><b>Cotas por tramo</b> (pestaña Utilidades, tubería de gravedad): tabla con la
          cota de Inicio/Fin de cada tramo. Pulsa <b>«Activar edición por tramo»</b> para
          editar cada valor de forma independiente (aparecen las etiquetas T1, T2… en el
          lienzo); apagado, se usan solo las rasantes inicial/final con interpolación
          lineal.</li>
    </ul>

    <h3>4. Buzones y cajas</h3>
    <p>Los buzones (gravedad, prefijo <code>BZ-</code>) y las cajas (conduit eléctrico/telecom,
    prefijo <code>CAJA-</code>) se detectan automáticamente en cada vértice. Cambia
    familia, tamaño y cotas en la pestaña <b>Buzones</b>. También puedes insertar uno
    en medio de una línea con <b>Herramientas → Insertar buzón en línea…</b> El botón
    <b>Ocultar buzón</b> saca un vértice de la vista y del DXF/Civil 3D como manhole
    visible (se exporta igual como "Estructura nula", invisible, para no romper la
    topología de la red) — útil para vértices auto-detectados que en realidad no son
    un acceso físico.</p>

    <h3>5. Leaders, texto, borrar zona</h3>
    <p><b>Leader</b>: orientación H/V/D, clic cabeza y final. <b>Texto libre</b>: clic +
    <b>Enter</b> para aplicar (<b>Ctrl+Shift+Enter</b> salto de línea). <b>Borrar zona</b>:
    polilínea cerrada; al exportar se elimina el plano dentro. El cajetín/membrete del
    PDF ya no se separa: se digitaliza como el resto del plano (capa
    <code>PDF_DIGITALIZADO</code>).</p>
    <p>Junto al botón de escala está <b>«Opacidad»</b>: abre un deslizable que atenúa
    solo el PDF y un botón para poner el fondo detrás del PDF en blanco o negro.</p>

    <h3>6. Versión e idioma de Civil 3D</h3>
    <p>Los selectores <b>Civil 3D</b> e <b>Idioma</b> de la barra superior fijan la
    versión (2025/2026/2027) y el idioma del catálogo contra los que se listan las
    familias y tamaños. Los nombres de familia se muestran en ese idioma. La selección
    se <b>guarda en el proyecto</b> y se repone sola al reabrirlo.</p>

    <h3>7. Centerlines de referencia (opcional)</h3>
    <p>Distintos de las utilidades — no representan ninguna tubería. Sirven de referencia
    visual e imán al colocar puntos de control en la georreferenciación. Acordeón
    <b>Trazar centerline</b> → clic en cada vértice sobre el eje de una calle →
    <b>Enter</b> finaliza. Se gestionan en la pestaña <b>Centerlines</b> (código,
    longitud); seleccioná uno desde la lista o clickeándolo en el lienzo. Se exportan al
    DXF en su propia capa <code>REF_CENTERLINES</code>.</p>

    <h3>8. Georreferenciación (opcional)</h3>
    <p><b>Herramientas → Georreferenciar…</b> — ventana redimensionable/maximizable,
    2 paneles:</p>
    <ul>
      <li><b>Izquierda (plano)</b>: el PDF con una barra de <b>opacidad</b> (solo
          atenúa el PDF, nunca las líneas dibujadas encima — utilidades y centerlines
          se ven siempre nítidas, no pixelan al hacer zoom). Clic = punto de control,
          con imán a la línea/centerline más cercana, o al <b>cruce exacto</b> si hay
          2 líneas que se cortan cerca del clic.</li>
      <li><b>Derecha (mapa)</b>: buscá una dirección/intersección (con indicador de
          carga mientras descarga) → trae calles y parcelas reales de Los Ángeles
          (NavigateLA) sobre mapa base. Misma navegación que el plano, e imán a
          vértice/cruce exacto y a las <b>esquinas redondeadas de las parcelas</b>.</li>
    </ul>
    <p><b>Ctrl+Z</b> deshace el último punto agregado, en cualquiera de los 2
    paneles.</p>
    <p>Con 3+ pares (idealmente en 2 cruces distintos, o combinando el cruce que
    tengas + esquinas de parcela), pulsá
    <b>«Ajustar + RMSE»</b>: calcula una transformación de <b>similaridad</b> (rota y
    escala parejo, sin deformar el plano). El <b>RMSE</b> es el error PROMEDIO en pies
    entre cada punto y donde el ajuste lo ubica — con menos de 3 clics bien puestos el
    RMSE sube y te avisa. Podés escribir además el <b>código de sistema de coordenadas
    (Huso)</b> — el código CS-MAP nativo de Civil 3D (ej. <code>CA83VF</code> para
    EPSG:2229): el dibujo quedará seteado con ese sistema al importar la red. Luego
    <b>«💾 Guardar georreferenciación»</b> guarda el proyecto. Solo para anteproyecto —
    el dato topográfico de precisión viene del levantamiento.</p>

    <h3>9. Exportar a DXF y abrir en Civil 3D</h3>
    <ul>
      <li><b>Ctrl+S</b> guarda el proyecto como <code>.digproj</code>.</li>
      <li><b>Exportar DXF</b> genera el DXF completo (dibujado + red 3D como XDATA).</li>
      <li>En Civil 3D: <code>NETLOAD</code> del plugin → <code>PANEL_REDES</code> →
          <b>Importar red desde DXF</b>. Se crean automáticamente las redes de
          gravedad, presión y conduit con sus familias y tamaños. Los tramos curvos
          generan tubería y <b>eje (alineamiento) curvos</b> con el mismo radio, y si
          fijaste un código de Huso el dibujo queda con ese sistema de coordenadas.</li>
      <li><b>Agregar tubería curva</b> (en el panel): seleccionás dos tuberías y un
          radio opcional, y crea la curva tangente entre ellas redondeando también el
          eje — como el <i>Free curve fillet</i> de Civil 3D.</li>
    </ul>

    <h3>10. Property Sets a tuberías (flujo con Excel)</h3>
    <p>En el panel de Civil 3D, tras importar la red:</p>
    <ol>
      <li><b>Exportar tuberías a Excel</b> genera un <code>.xlsx</code> con columnas
          <b>Nombre</b> y <b>Tipo</b> (una fila por tubería, gravedad y presión).</li>
      <li>Agrega en Excel las columnas que quieras (una por Property Set); por ejemplo
          <code>Material_Especificacion</code>, <code>Fecha_Instalacion</code>. Rellena
          los valores por tubería (deja vacío para omitir).</li>
      <li><b>Importar Property Sets desde Excel</b>: se crean las definiciones que
          falten (una propiedad <code>Valor</code> por PS) y se adjuntan a cada tubería
          por nombre. Es idempotente — puedes reimportar el mismo archivo sin duplicar.</li>
      <li>Verifica en Civil 3D: selecciona una pipe → Properties → <b>Extended Data</b>.</li>
    </ol>
    """
    show_html(win, "Manual de usuario", html, 880, 780)


def show_shortcuts(win):
    rows = [("Ctrl+Z / Ctrl+Shift+Z", "Deshacer / Rehacer"),
            ("Enter", "Aplicar: finaliza utilidad/zona, o agrega texto/edición"),
            ("Ctrl+Shift+Enter", "Salto de línea dentro de un texto"),
            ("Escape", "Quitar la selección; si no hay, salir del modo"),
            ("Ctrl+T", "Editar/mover lo seleccionado"),
            ("Ctrl+S / Ctrl+Shift+S", "Guardar proyecto / Guardar como…"),
            ("Ctrl+W", "Cerrar proyecto (pregunta si hay cambios)"),
            ("Doble clic", "Sobre un texto: editarlo"),
            ("Clic derecho", "Finaliza línea/zona; en editar, elimina el vértice"),
            ("◀ ▶", "Página anterior / siguiente"),
            ("Rueda", "Zoom · Botón central + arrastrar: desplazar")]
    body = "".join(f'<tr><td style="padding:4px 14px;color:#8bd;"><b>{k}</b></td>'
                   f'<td style="padding:4px;">{d}</td></tr>' for k, d in rows)
    show_html(win, "Atajos de teclado", f"<h2>Atajos de teclado</h2><table>{body}</table>", 640, 500)
