"""Tarea 12 del plan 2026-11-16 («reconocimiento desde el editor»): el flujo NUEVO en la ventana real, con los
trabajadores de verdad (procesos), y las PAUSAS de la ventana.

    python scripts/rendimiento/flujo_editor.py plano.pdf 3 > editor.log

Abre el PDF (la hoja N entera: «Componer hoja» aceptado al instante), mide cuándo el editor queda usable (vuelve
`_open_pdf_path` con la hoja a la vista), cuándo termina la interpretación en segundo plano y cuánto tarda «▶ Todo»
(utilidades → válvulas → diámetros → rótulos). Un hilo mira el latido de la ventana (QTimer de 20 ms): toda pausa
de más de `--pausa` s se anota con la función del proyecto donde estaba la ventana.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import traceback

import comun


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("hoja", type=int, nargs="?", default=0)
    ap.add_argument("--pausa", type=float, default=0.2)
    ap.add_argument("--tope", type=float, default=1800.0)
    a = ap.parse_args()
    comun.preparar(con_qt=True)
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import fitz
    import vector_pipeline as VP
    from hoja import composite as C
    from ui.comun import proceso
    from ui.ventana import app_window
    for nombre in ("information", "warning", "critical"):
        setattr(QtWidgets.QMessageBox, nombre, staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Ok))
    QtWidgets.QMessageBox.question = staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Yes)

    def componer(parent, sources, comp, hidden, current_page=0, manual=False, **kw):
        with fitz.open(stream=sources[0]["data"], filetype="pdf") as d:
            escala = float(VP.detect_scale(d[a.hoja]))
        return C.Composite([C.Piece(0, a.hoja, [0.0, 0.0, 1.0, 1.0], src_scale=escala)], bridges=False), sources, hidden
    app_window.composite_dialog.compose_sheet = componer

    t0 = time.perf_counter()
    latido = [t0]
    pausas, etapa = [], ["abrir"]
    principal = threading.main_thread().ident
    fin = threading.Event()

    def mirar():
        en = None
        while not fin.is_set():
            time.sleep(0.02)
            quieta = time.perf_counter() - latido[0]
            if quieta > a.pausa:
                if en is None:
                    en = {"desde": latido[0] - t0, "etapa": etapa[0], "pila": {}}
                marco = sys._current_frames().get(principal)
                propias = [f"{os.path.basename(fs.filename)}:{fs.name}" for fs in traceback.extract_stack(marco)
                           if os.sep + "pdf-to-cad" + os.sep in fs.filename and "rendimiento" not in fs.filename]
                clave = " ← ".join(reversed(propias[-3:])) or "(fuera del proyecto)"
                en["pila"][clave] = en["pila"].get(clave, 0) + 1
                en["dur"] = quieta
            elif en is not None:
                pausas.append(en)
                en = None
    threading.Thread(target=mirar, daemon=True).start()
    QtCore.QTimer(app, interval=20, timeout=lambda: latido.__setitem__(0, time.perf_counter())).start()

    w = app_window.Main()
    w.resize(1600, 900)
    w.show()
    app.processEvents()
    marcas = {}

    def esperar(cond, nombre):
        limite = time.time() + a.tope
        while not cond():
            app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            if time.time() > limite:
                raise SystemExit(f"tiempo agotado esperando {nombre}")
        marcas[nombre] = time.perf_counter() - t0

    t_abrir = time.perf_counter()
    w._open_pdf_path(a.pdf)
    marcas["editor usable"] = time.perf_counter() - t0
    print(f"abrir → editor usable: {time.perf_counter() - t_abrir:.2f} s (hoja a la vista: "
          f"{w.canvas.pixmap_item is not None}, interpretando: {w.interpretando()})", flush=True)
    etapa[0] = "interpretar"
    esperar(lambda: not w.interpretando(), "interpretada")
    filas = {p: f.estado for p, f in w.reconocer_estado.filas.items()}
    print(f"interpretación: {marcas['interpretada'] - marcas['editor usable']:.2f} s · filas {filas}", flush=True)
    etapa[0] = "▶ Todo"
    tiempos_partes, actual = {}, [None, 0.0]

    def seguir():
        act = w._rec_actual
        parte = act["pasos"][0][0] if act and act.get("pasos") else None
        if parte != actual[0]:
            if actual[0] is not None:
                tiempos_partes[actual[0]] = time.perf_counter() - actual[1]
            actual[:] = [parte, time.perf_counter()]
            if parte:
                etapa[0] = f"▶ {parte}"
    seguidor = QtCore.QTimer(app, interval=10, timeout=seguir)
    seguidor.start()
    t_todo = time.perf_counter()
    w.reconocer_todo()
    esperar(lambda: w._rec_actual is None and not w._rec_cola, "▶ Todo")
    seguidor.stop()
    if actual[0] is not None:
        tiempos_partes[actual[0]] = time.perf_counter() - actual[1]
    etapa[0] = "editor quieto"
    calma = time.time()
    while time.time() - calma < 3.0:                    # que termine el cálculo de fondo y el redibujo
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if getattr(w, "_provisional", False) or getattr(w, "_tandas", None) is not None:
            calma = time.time()
    fin.set()
    print(f"▶ Todo: {time.perf_counter() - t_todo:.2f} s · {len(w.pipes)} utilidades, "
          f"{len(getattr(w, 'valvulas', []) or [])} válvulas, {len(getattr(w, 'anotaciones', []) or [])} rótulos")
    for p, s in tiempos_partes.items():
        print(f"   {p:16s} {s:7.2f} s")
    print(f"filas: { {p: f.estado for p, f in w.reconocer_estado.filas.items()} }")
    print(f"\nPAUSAS de la ventana (> {a.pausa:g} s): {len(pausas)} · máxima "
          f"{max((p['dur'] for p in pausas), default=0.0):.2f} s")
    for p in sorted(pausas, key=lambda p: -p["dur"])[:12]:
        donde = max(p["pila"].items(), key=lambda kv: kv[1])[0]
        print(f"  {p['desde']:7.1f} s  {p['dur']:5.2f} s  [{p['etapa']}]  {donde}")
    w._dirty = False
    for t in list(proceso._TRABAJADORES.values()):
        t.parar()
    w.close()


if __name__ == "__main__":
    main()
