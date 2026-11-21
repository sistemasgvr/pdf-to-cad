"""Inventario de las acciones de la interfaz y de cuáles llevan el aro de «cargando» (2026-11-21).

    python scripts/inventario_acciones.py [salida.md]      # por defecto docs/loader_acciones.md

Abre la ventana principal sin pantalla y recorre CADA botón y CADA acción (barra, riel, paneles, menús, paleta).
Un botón de acción lleva el aro automáticamente (`ui/comun/accion_cargando`); las casillas, selectores y
conmutadores no (alternan un ajuste al instante); las acciones de menú no tienen botón: las cubre la tarjeta
«Cargando…» (`ui/comun/busy`) y el vigía. Esos números salen de la ventana real, no de una lista a mano."""
import collections
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(RAIZ, "app"), RAIZ]


def _zona(w):
    """El panel o diálogo al que pertenece (el ancestro con nombre de objeto o clase propia, no genérico)."""
    p = w.parentWidget()
    while p is not None:
        n = p.objectName()
        if n and not n.startswith("qt_"):
            return n
        c = type(p).__name__
        if c not in ("QWidget", "QFrame", "QStackedWidget", "QScrollArea", "QToolBar", "QDockWidget",
                     "QSplitter", "QGroupBox") and not c.startswith("Q"):
            return c
        p = p.parentWidget()
    return "ventana"


def main():
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from traduccion import i18n_core
    i18n_core._current_lang = "es"
    from ui.comun import accion_cargando as AC
    from ui.ventana.app_window import Main
    w = Main()
    w.resize(1400, 900)
    w.show()
    QtWidgets.QApplication.processEvents()
    botones = w.findChildren(QtWidgets.QAbstractButton)
    zonas = collections.defaultdict(lambda: {"aro": [], "sin": collections.defaultdict(list)})
    for b in botones:
        motivo = AC.sin_aro_por(b, estado=False)
        nombre = (b.text() or b.toolTip() or b.objectName() or type(b).__name__).strip().replace("\n", " ")[:50]
        z = zonas[_zona(b)]
        (z["aro"].append(nombre) if motivo is None else z["sin"][motivo].append(nombre))
    acciones = [a for a in w.findChildren(__import__("PySide6.QtGui", fromlist=["QAction"]).QAction)
                if not a.isSeparator() and a.text()]
    con_boton = {a for b in botones for a in b.actions()}
    sin_boton = [a for a in acciones if a not in con_boton and not a.menu()]
    total_aro = sum(len(z["aro"]) for z in zonas.values())
    total_sin = sum(len(v) for z in zonas.values() for v in z["sin"].values())
    L = ["# Aro de «cargando» en cada acción", "",
         "Generado por `scripts/inventario_acciones.py` desde la ventana real (2026-11-21).", "",
         "**Regla:** todo botón de acción lleva, al pulsarlo, un aro que gira mientras lo que lanzó sigue en marcha "
         "(`ui/comun/accion_cargando`). Se ve si el manejador bloquea la ventana más de 0.25 s (el vigía lo pinta) o "
         "si lanza trabajo en otro proceso/hilo, la tarjeta «Cargando…» o un trabajo por pasos "
         "(`nucleo/actividad`). Las casillas, selectores y conmutadores no la llevan: alternan un ajuste al "
         "instante.", "",
         f"- Botones con aro: **{total_aro}**",
         f"- Botones sin aro por ser ajustes o menús: **{total_sin}**",
         f"- Acciones de menú/atajo sin botón (las cubre la tarjeta «Cargando…» y el vigía): **{len(sin_boton)}**", ""]
    for zona in sorted(zonas):
        z = zonas[zona]
        L += [f"## {zona}", ""]
        if z["aro"]:
            L.append(f"**Con aro ({len(z['aro'])}):** " + " · ".join(sorted(set(z["aro"]))))
            L.append("")
        for motivo, ns in sorted(z["sin"].items()):
            L.append(f"*Sin aro — {motivo} ({len(ns)}):* " + " · ".join(sorted(set(ns))))
            L.append("")
    L += ["## Acciones sin botón (menús, atajos, paleta Ctrl+K)", "",
          " · ".join(sorted({a.text().replace("&", "") for a in sin_boton})), ""]
    salida = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "docs", "loader_acciones.md")
    with open(salida, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"{total_aro} botones con aro, {total_sin} sin aro, {len(sin_boton)} acciones sin botón -> {salida}")
    w._dirty = False
    os._exit(0)


if __name__ == "__main__":
    main()
