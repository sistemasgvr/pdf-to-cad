"""Tarea 12 (plan 2026-11-16): el EDITOR tras «▶ Todo» = el editor tras el flujo de antes (reconocer todo de una vez
con `reconocer_hoja` → `_import_recognized_pipes`), en la ventana real.

    python scripts/rendimiento/editor_igual.py plano.pdf 3

Compara utilidades, estructuras, válvulas y rótulos (sin los sellos `reconocida*` que pone el ▶). Sale con 1 si
difieren.
"""
import json
import os
import sys
import time

import comun


def main():
    pdf, hoja = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0
    os.environ["PDFCAD_PROCESO"] = "0"
    comun.preparar(con_qt=True)
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import pymupdf as fitz
    import vector_pipeline as VP
    from hoja import composite as C
    from reconocimiento import lectura_retenida as LR
    from reconocimiento import recognition as rec
    from reconocimiento import recognition_trabajo as RT
    from ui.ventana import app_window
    for nombre in ("information", "warning", "critical"):
        setattr(QtWidgets.QMessageBox, nombre, staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Ok))
    QtWidgets.QMessageBox.question = staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Yes)

    def componer(parent, sources, comp, hidden, current_page=0, manual=False, **kw):
        with fitz.open(stream=sources[0]["data"], filetype="pdf") as d:
            escala = float(VP.detect_scale(d[hoja]))
        return C.Composite([C.Piece(0, hoja, [0.0, 0.0, 1.0, 1.0], src_scale=escala)], bridges=False), sources, hidden
    app_window.composite_dialog.compose_sheet = componer

    def esperar(cond):
        fin = time.time() + 900
        while not cond():
            app.processEvents()
            time.sleep(0.01)
            assert time.time() < fin

    sellos = ("reconocida", "reconocida_idx", "reconocida_firma")

    def foto(w):
        limpio = lambda lista: [{k: v for k, v in d.items() if k not in sellos} for d in lista]  # noqa: E731
        return {"pipes": json.dumps(limpio(w.pipes), sort_keys=True, default=repr),
                "structures": json.dumps(limpio(w.structures), sort_keys=True, default=repr),
                "valvulas": json.dumps(getattr(w, "valvulas", []) or [], sort_keys=True, default=repr),
                "anotaciones": json.dumps(getattr(w, "anotaciones", []) or [], sort_keys=True, default=repr)}

    w = app_window.Main()
    w._open_pdf_path(pdf)
    esperar(lambda: not w.interpretando())
    w.reconocer_todo()
    esperar(lambda: w._rec_actual is None and not w._rec_cola)
    nuevo = foto(w)
    cuantos = (len(w.pipes), len(w.structures), len(w.valvulas or []), len(w.anotaciones or []))
    roles = w._roles_de_la_hoja(w.page_idx)
    ruta = w.work_pdf_path or w.pdf_path
    viejo_res = RT.reconocer_hoja(ruta, w.page_idx, zoom=w.zoom, utilities=tuple(rec.SUPPORTED_UTILITIES),
                                  hidden_ocgs=w.hidden_ocgs, roles_by_utility=roles, letters_off=w._letters_off,
                                  scale_ft_per_pt=w._scale_override)
    w._reset_model()
    w.valvulas, w.anotaciones = [], []
    w._import_recognized_pipes(viejo_res)
    viejo = foto(w)
    print(f"▶ Todo: {cuantos[0]} utilidades, {cuantos[1]} estructuras, {cuantos[2]} válvulas, {cuantos[3]} rótulos")
    print(f"antes:  {len(w.pipes)} utilidades, {len(w.structures)} estructuras, {len(w.valvulas or [])} válvulas, "
          f"{len(w.anotaciones or [])} rótulos")
    malas = [k for k in nuevo if nuevo[k] != viejo[k]]
    if "structures" in malas:
        # el ORDEN y los códigos (BZ-n) dependen del orden en que entran las utilidades: por lugar y sin código
        clave = lambda d: (round(float(d.get("x", 0)), 3), round(float(d.get("y", 0)), 3))  # noqa: E731
        sin_cod = lambda lista: sorted((json.dumps({k: v for k, v in d.items() if k != "cod"}, sort_keys=True)  # noqa: E731
                                        for d in lista), key=lambda t: clave(json.loads(t)))
        a, b = sin_cod(json.loads(nuevo["structures"])), sin_cod(json.loads(viejo["structures"]))
        if a == b:
            malas.remove("structures")
            print("estructuras: iguales por lugar (solo cambian el orden y los códigos BZ-n)")
        else:
            sa, sb = set(a), set(b)
            for t in sorted(sa - sb)[:6]:
                print("   solo ▶:   ", t[:200])
            for t in sorted(sb - sa)[:6]:
                print("   solo antes:", t[:200])
    print("IGUAL en todo" if not malas else f"DIFIEREN: {malas}")
    LR.soltar()
    w._dirty = False
    w.close()
    sys.exit(1 if malas else 0)


if __name__ == "__main__":
    main()
