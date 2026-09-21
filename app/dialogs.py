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
    t = _theme.tokens()
    preview_lbl.setStyleSheet(f"color:{t.text_muted}; background:{t.surface_alt}; padding:8px; border-radius:4px;")
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
    """Ventana del manual de usuario. Es HTML sencillo dentro de un
    QTextBrowser (visor de texto enriquecido); nada de red ni servidor.

    El manual entero se pasa como una sola clave a _tr(): si hay una traducción
    completa al idioma activo, esa se muestra; si no, se muestra el original en
    español. Añadir un idioma es una entrada más en TRANSLATIONS de i18n.py."""
    html = _tr("""
    <h2>Manual de usuario — v1.2.0</h2>
    <p><i>Pipeline PDF → CAD → Civil 3D para redes de utilidad (agua, alcantarillado,
    drenaje, gas, electricidad, telecomunicaciones). Trabaja en unidades imperiales (pies).</i></p>

    <h3>1. Abrir el plano</h3>
    <p><b>Archivo → Abrir PDF…</b> (o arrastralo). Cambia de página y ajusta la
    transparencia en la sección <b>Vista y páginas</b>. Rueda = zoom, botón central = pan.</p>
    <p>Si el PDF es <b>vectorial (bien ploteado)</b>, el asistente abre <b>Componer hoja de
    trabajo</b>: a la izquierda eliges el PDF y la hoja (puedes <b>agregar otros PDF</b>);
    en el centro marcas con un rectángulo el área del plano que
    necesitas (con <b>Imán a líneas</b> los lados saltan a las match lines, marcos y bordes largos, resaltados en celeste) y pulsas <b>Tomar área</b> (o <b>Tomar hoja completa</b>); a la derecha la
    pieza aparece en la <b>hoja compuesta</b>, donde la arrastras hasta su sitio. Con el
    <b>Imán</b> activo, al acercar una pieza a otra los extremos de sus líneas se pegan solos
    (o quedan en línea si dejas un hueco). Los extremos de línea se marcan con un punto en el
    borde de cada pieza; con <b>Puentes</b> activo, cada extremo se une con un trazo vectorial
    (en su misma capa, verde en la vista) al que tiene enfrente en la pieza vecina, hasta el
    <b>hueco máximo</b> indicado: así puedes recortar cada hoja por dentro de su match line, sin
    la línea divisoria, y la utilidad sigue de una pieza a otra. Con <b>Sin línea de borde</b>
    (activo por defecto) cada lado del área se lleva solo al centro de la match line o del marco que
    corra pegado a él y su tinta se tapa con una franja blanca: no se pierde ningún vector y dos hojas
    contiguas se unen borde con borde, sin hueco ni línea divisoria. Al seleccionar una pieza, el panel «Área a tomar» muestra su hoja y su área
    para ajustarla; <b>Nueva pieza</b> vuelve a marcar áreas nuevas.
    Cada pieza se puede girar (90° o ángulo fino) y corregir su <b>escala</b> si el texto de la
    hoja no la dice; la hoja compuesta usa una escala única y agranda/achica cada pieza para
    que todo quede coherente en pies. Las piezas conservan sus vectores, capas, textos y
    medidas: la hoja compuesta es un PDF real de una página y el reconocimiento corre sobre
    ella de una vez, así una línea que cruza de una hoja a la siguiente sale como una sola
    ruta. Una sola pieza = hoja completa equivale a trabajar la hoja original (◀ ▶ siguen
    funcionando). Al continuar se abre <b>Capas de la hoja</b>: las capas del plano agrupadas por
    utilidad (Agua, Alcantarillado, Drenaje, Gas, Eléctrico, Telefonía y Otras, cada una
    con su color) con casillas para mostrarlas u ocultarlas, con vista previa en vivo.
    En el panel <b>Utilidades</b>, desmarcar una utilidad apaga todas sus capas en la
    hoja y las quita de la lista (al marcarla de nuevo, cada capa vuelve como estaba);
    <b>Todas</b> actúa sobre el conjunto. El buscador solo filtra la lista y
    <b>Mostrar/Ocultar todas</b> actúa sobre lo que se ve. Con <b>◀ Hoja N / M ▶</b> puedes cambiar de
    hoja sin salir (las capas marcadas se conservan). Las capas ocultas no se dibujan en
    el lienzo ni se usan en el reconocimiento. Al continuar se reconocen las utilidades
    eléctricas (las capas de líneas y bóvedas se asignan solas por su nombre) y se muestra
    la <b>vista previa del reconocimiento</b>, con la utilidad, la hoja y las capas usadas.
    Desde ahí: <b>Continuar e importar</b>, <b>Componer hoja…</b> (compositor → capas
    → nueva vista previa) o <b>Ajustar capas…</b> (solo si el plot usa otros nombres).
    Después, al cambiar de hoja en el editor (◀ ▶ o nº de página) la nueva hoja se reconoce
    con las mismas capas. Las capas de estado <b>-A</b> (abandonadas, linetype ──/── e ──) se
    reconocen igual, se dibujan del mismo color y se importan marcadas <b>(AB)</b>, como la casilla «Abandonado».
    Sus marcadores «/» y «//» (dos barras o un solo trazo en zigzag, incluso barras largas)
    se descartan como glifos. Una línea cuenta como abandonada solo si está en la capa
    «-A» <b>y</b> lleva ese patrón de marcadores a paso regular en toda su longitud (dos
    barras sueltas no bastan; los ramales más cortos que el paso siguen a su capa); la
    vista previa avisa de las excepciones. El contorno de una bóveda abandonada dibujado
    en esa misma capa se reconoce como bóveda con medidas (etiqueta «(AB)» en la vista previa).
    La casilla <b>Unir tramos en rutas</b> (activada) encadena los tramos de la misma capa que
    siguen de frente; el ramal empieza otra ruta. No mueve puntos. Se puede desactivar antes de importar.
    Los <b>codos</b> del plano (trazo curvo tangente a dos guiones rectos) se importan como esquina
    + radio: la esquina es la intersección de las rectas de los guiones y el arco, el círculo
    tangente a ellas que pasa por el trazo curvo. En el lienzo la esquina curva se dibuja con su
    arco real (puntos de tangencia marcados), el mismo que generará Civil 3D; si va a trazos es
    que el radio no entra en los tramos y el plugin lo recortará. Una cadena de guiones rectos
    con quiebres nunca se convierte en curva.</p>

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
    """)
    show_html(win, _tr("Manual de usuario"), html, 880, 780)


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
    cmb.addItem(_i18n.t("Español"), "es")
    cmb.addItem(_i18n.t("Inglés"), "en")
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
