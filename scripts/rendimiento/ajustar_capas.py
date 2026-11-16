"""Cuánto tarda en abrirse «Ajustar capas…» del panel «Reconocer» (reporte del usuario 2026-11-16, «esta opción
demora bastante»), en la ventana real con la hoja ya interpretada.

    python scripts/rendimiento/ajustar_capas.py hoja_compuesta.pdf [UTILIDAD]

Abre el PDF (su hoja 0 entera), espera la interpretación en segundo plano y mide `ajustar_capas_parte` hasta que el
diálogo de roles está a la vista (se cierra solo).
"""
import os
import sys
import time

import comun


def main():
    pdf = sys.argv[1]
    util = sys.argv[2] if len(sys.argv) > 2 else "DRENAJE"
    comun.preparar(con_qt=True)
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import fitz
    import vector_pipeline as VP
    from hoja import composite as C
    from ui.comun import proceso
    from ui.ventana import app_window
    for n in ("information", "warning", "critical"):
        setattr(QtWidgets.QMessageBox, n, staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Ok))

    def componer(parent, sources, comp, hidden, current_page=0, manual=False, **kw):
        with fitz.open(stream=sources[0]["data"], filetype="pdf") as d:
            esc = float(VP.detect_scale(d[0]))
        return C.Composite([C.Piece(0, 0, [0, 0, 1, 1], src_scale=esc)], bridges=False), sources, hidden
    app_window.composite_dialog.compose_sheet = componer
    QtWidgets.QDialog.exec = lambda self: (self.show(), app.processEvents(), self.reject(), 0)[-1]
    w = app_window.Main()
    w.resize(1600, 900)
    w.show()
    app.processEvents()
    w._open_pdf_path(pdf)
    while w.interpretando():
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
    t = time.perf_counter()
    w.ajustar_capas_parte(util)
    print(f"interpretada: {w._interpretacion is not None} · «Ajustar capas…» {util}: "
          f"{time.perf_counter() - t:.2f} s", flush=True)
    for tr in list(proceso._TRABAJADORES.values()):
        tr.parar()
    w._dirty = False
    w.close()


if __name__ == "__main__":
    main()
