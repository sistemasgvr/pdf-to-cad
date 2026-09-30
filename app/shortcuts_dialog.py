"""Atajos de teclado: ventana con buscador y los atajos agrupados en tarjetas
(HTML en un QTextBrowser: solo tablas y colores, que es lo que Qt renderiza).

Los atajos de menú se leen de las QAction de la ventana (grupo = título de su
menú); los de ratón, lista de utilidades (selección masiva) y teclas sueltas
van fijos aquí."""
from __future__ import annotations

import html

from PySide6 import QtCore, QtGui, QtWidgets

import theme as _theme
from i18n import t as _tr, N_

# (clave, descripción) — textos fijos que no salen de una QAction.
_FIXED = [
    (N_("Lista de utilidades · selección masiva"), [
        (N_("Ctrl + clic"), N_("Agregar o quitar una utilidad de la selección")),
        (N_("Shift + clic"), N_("Seleccionar un rango de utilidades")),
        ("Ctrl+A", N_("Seleccionar todas las utilidades (con la lista activa)")),
        (N_("Clic derecho"), N_("Con varias seleccionadas: eliminar, cambiar tipo, crear o asignar bancoducto, quitarlo")),
        (N_("Clic derecho"), N_("Seleccionar todas las de un mismo tipo")),
        ("Supr", N_("Eliminar las utilidades seleccionadas (pide confirmación)")),
    ]),
    (N_("Diseñador de bancoducto"), [
        (N_("Pasar el mouse"), N_("En «Asignar a:», miniatura de la utilidad sobre el plano")),
        ("Esc", N_("Soltar la herramienta activa sin cerrar la ventana")),
    ]),
    (N_("Lienzo y ratón"), [
        ("Enter", N_("Aplicar: finaliza utilidad/zona, o agrega texto/edición")),
        ("Esc", N_("Quitar la selección; si no hay, salir del modo")),
        (N_("Doble clic"), N_("Sobre un texto: editarlo")),
        (N_("Clic derecho"), N_("Finaliza línea/zona; en editar, elimina el vértice")),
        (N_("Rueda"), N_("Zoom · Botón central + arrastrar: desplazar")),
        (N_("Pasar el mouse"), N_("En la lista «Bancoductos», miniatura de la sección")),
    ]),
]


def _menu_groups(win):
    """{título de menú: [(atajo, texto)]} desde las QAction con atajo."""
    groups, seen = {}, set()
    for a in win.findChildren(QtGui.QAction):
        sc = a.shortcut().toString(QtGui.QKeySequence.NativeText)
        txt = a.text().replace("&", "").strip()
        if not sc or not txt or sc in seen:
            continue
        seen.add(sc)
        menu = next((o for o in a.associatedObjects() if isinstance(o, QtWidgets.QMenu)
                     and o.title()), None)
        g = menu.title().replace("&", "") if menu else _tr("General")
        groups.setdefault(g, []).append((sc, txt))
    return groups


def _chips(key, t):
    """«Ctrl+Shift+Z» → teclas como etiquetas."""
    parts = [p.strip() for p in key.replace(" + ", "+").split("+")] if key != "+" else ["+"]
    chip = (f'<span style="background-color:{t.surface_alt}; color:{t.text}; '
            f'font-family:Consolas,monospace; font-weight:600;">&nbsp;{{}}&nbsp;</span>')
    sep = f'<span style="color:{t.text_muted};"> + </span>'
    return sep.join(chip.format(html.escape(p)) for p in parts if p)


def _render(groups, query, t):
    q = query.strip().lower()
    cards = []
    for title, rows in groups:
        rows = [(k, d) for k, d in rows if not q or q in k.lower() or q in d.lower()
                or q in title.lower()]
        if not rows:
            continue
        body = "".join(
            f'<tr><td width="42%" style="padding:6px 10px;">{_chips(k, t)}</td>'
            f'<td style="padding:6px 10px; color:{t.text};">{html.escape(d)}</td></tr>'
            for k, d in rows)
        cards.append(
            f'<table width="100%" cellspacing="0" cellpadding="0" '
            f'style="margin-bottom:14px; background-color:{t.surface};" border="0">'
            f'<tr><td colspan="2" style="padding:8px 10px; background-color:{t.accent}; '
            f'color:{t.text_on_accent}; font-weight:700; font-size:15px;">{html.escape(title)}</td></tr>'
            f'{body}</table>')
    if not cards:
        return f'<p style="color:{t.text_muted}; padding:20px;">{html.escape(_tr("Ningún atajo coincide con la búsqueda."))}</p>'
    return "".join(cards)


def show_shortcuts(win):
    t = _theme.tokens()
    groups = [(g, rows) for g, rows in sorted(_menu_groups(win).items())]
    groups += [(_tr(title), [(_tr(k), _tr(d)) for k, d in rows]) for title, rows in _FIXED]

    dlg = QtWidgets.QDialog(win)
    dlg.setWindowTitle(_tr("Atajos de teclado"))
    dlg.resize(760, 640)
    lay = QtWidgets.QVBoxLayout(dlg); lay.setContentsMargins(16, 16, 16, 12); lay.setSpacing(10)
    head = QtWidgets.QLabel(
        f'<span style="font-size:20px; font-weight:700;">{html.escape(_tr("Atajos de teclado"))}</span><br>'
        f'<span style="color:{t.text_muted};">{html.escape(_tr("Teclas y gestos de la app, agrupados por menú. Escribe para filtrar."))}</span>')
    lay.addWidget(head)
    search = QtWidgets.QLineEdit(); search.setPlaceholderText(_tr("Buscar atajo o acción…"))
    search.setClearButtonEnabled(True); search.setMinimumHeight(32)
    lay.addWidget(search)
    tb = QtWidgets.QTextBrowser()
    tb.setStyleSheet(f"QTextBrowser {{ background:{t.window}; color:{t.text}; font-size:14px;"
                     f" border:1px solid {t.border}; border-radius:6px; padding:8px; }}")
    lay.addWidget(tb, 1)
    btn = QtWidgets.QPushButton(_tr("Cerrar")); btn.setMinimumHeight(32); btn.clicked.connect(dlg.accept)
    row = QtWidgets.QHBoxLayout(); row.addStretch(1); row.addWidget(btn); lay.addLayout(row)

    def refresh(text=""):
        tb.setHtml(_render(groups, text, t))
    search.textChanged.connect(refresh)
    refresh()
    search.setFocus()
    dlg.exec()
