"""Recorre el flujo REAL de abrir un PDF hasta el editor y dice dónde la ventana se queda quieta
(`docs/rendimiento/GUIA.md`; pedido del usuario 2026-11-16: «cada carga con su barra de 0 a 100 % y a detalle;
evitar que el programa se quede en No responde»).

    python scripts/rendimiento/flujo.py plano.pdf > flujo.log
    python scripts/rendimiento/flujo.py plano.pdf --tiempos tiempos.json

Abre el PDF como el usuario (asistente incluido: Componer hoja → Capas de la hoja → reconocer → Vista previa →
importar) y pulsa «Continuar» en cada paso en cuanto queda libre. Mientras tanto mide:

  · CARGAS: cada tarjeta «Cargando…» que apareció, cuánto duró, cuántas veces se pintó, el hueco más largo sin
    pintarse (la barra quieta) y de qué a qué porcentaje fue;
  · PAUSAS: cada vez que la ventana estuvo más de `--pausa` s sin atender eventos, si había una tarjeta a la
    vista y en qué función estaba (pila del hilo de la ventana, muestreada desde otro hilo).

Una pausa SIN tarjeta = falta un cargador. Una pausa con tarjeta y la barra quieta = trabajo en una biblioteca en
C que no suelta el intérprete: va a otro proceso (`ui/comun/proceso`). Ajustes y carpetas aparte.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback

import comun


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos sin atender eventos que cuentan como pausa")
    ap.add_argument("--tope", type=float, default=1500.0, help="segundos como máximo")
    ap.add_argument("--tiempos", help="guardar aquí lo aprendido de cada carga (JSON)")
    ap.add_argument("--con-tiempos", help="empezar con lo aprendido de este JSON (la 2.ª vez del usuario)")
    a = ap.parse_args()
    comun.preparar(con_qt=True)
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import busy, progreso_reconocimiento, tiempos_carga
    from ui.ventana import app_window
    if a.con_tiempos:
        with open(a.con_tiempos, encoding="utf-8") as f:
            tiempos_carga._perfiles = json.load(f)
    for nombre in ("information", "warning", "critical"):
        setattr(QtWidgets.QMessageBox, nombre, staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Ok))
    QtWidgets.QMessageBox.question = staticmethod(lambda *x, **k: QtWidgets.QMessageBox.Yes)

    t0 = time.perf_counter()
    pinturas = []                       # (t, id tarjeta, título, detalle, fracción)
    activas = {}                        # id tarjeta → título (las que están a la vista)

    def anotar(tarjeta):
        try:
            titulo = tarjeta.text()
            if titulo:
                pinturas.append((time.perf_counter() - t0, id(tarjeta), titulo, tarjeta.detail(),
                                 tarjeta.fraccion()))
        except Exception:               # noqa: BLE001
            pass

    pintar = busy.BusyOverlay.paintEvent
    busy.BusyOverlay.paintEvent = lambda self, ev: (anotar(self), pintar(self, ev))[1]
    colocar = progreso_reconocimiento.ProgresoReconocimiento._colocar
    progreso_reconocimiento.ProgresoReconocimiento._colocar = lambda self: (
        anotar(self) if self.active else None, colocar(self))[1]
    for clase in (busy.BusyOverlay, progreso_reconocimiento.ProgresoReconocimiento):
        empezar, terminar = clase.begin, clase.end

        def begin(self, text, *x, _e=empezar, **k):
            activas[id(self)] = text
            return _e(self, text, *x, **k)

        def end(self, *x, _t=terminar, **k):
            r = _t(self, *x, **k)
            if not self.active:
                activas.pop(id(self), None)
            return r
        clase.begin, clase.end = begin, end

    # ── el latido de la ventana y quien la mira desde otro hilo ──
    latido = [time.perf_counter()]
    pausas = []                         # (inicio, duración, tarjeta a la vista o "", {función: muestras})
    principal = threading.main_thread().ident
    fin = threading.Event()

    def mirar():
        en_pausa = None
        while not fin.is_set():
            time.sleep(0.05)
            quieta = time.perf_counter() - latido[0]
            if quieta > a.pausa:
                if en_pausa is None:
                    en_pausa = {"desde": latido[0] - t0, "tarjeta": " | ".join(activas.values()), "pila": {}}
                marco = sys._current_frames().get(principal)
                propias = [f"{os.path.basename(fs.filename)}:{fs.name}" for fs in traceback.extract_stack(marco)
                           if os.sep + "pdf-to-cad" + os.sep in fs.filename and "rendimiento" not in fs.filename]
                clave = " ← ".join(reversed(propias[-3:])) or "(fuera del proyecto)"
                en_pausa["pila"][clave] = en_pausa["pila"].get(clave, 0) + 1
                en_pausa["dur"] = quieta
            elif en_pausa is not None:
                pausas.append(en_pausa)
                en_pausa = None
    threading.Thread(target=mirar, daemon=True).start()
    QtCore.QTimer(app, interval=20, timeout=lambda: latido.__setitem__(0, time.perf_counter())).start()

    # ── la ventana y el «usuario» que pulsa Continuar ──
    w = app_window.Main()
    w.resize(1600, 900)
    w.show()
    app.processEvents()
    pasos = []                          # (t, diálogo)
    visto = {}

    def usuario():
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is None or activas:
            return
        clave = id(modal)
        ahora = time.perf_counter()
        if clave not in visto:
            visto[clave] = ahora
            pasos.append((ahora - t0, type(modal).__name__))
            return
        if ahora - visto[clave] < 1.0:                    # (que termine de acomodarse)
            return
        boton = getattr(modal, "btn_ok", None)
        if boton is None:
            modal.accept()
            return
        if not boton.isEnabled():
            usar = getattr(modal, "_use_page", None)       # «Componer hoja» sin hoja elegida: la primera
            if usar is not None and not getattr(modal, "_flujo_usada", False):
                modal._flujo_usada = True
                usar(0)
            return
        visto[clave] = ahora + 3.0                         # (un clic; si el paso sigue, se espera)
        boton.click()
    QtCore.QTimer(app, interval=250, timeout=usuario).start()

    hecho = []

    def abrir():
        try:
            w._open_pdf_path(a.pdf)
        finally:
            hecho.append(time.perf_counter() - t0)
    QtCore.QTimer.singleShot(0, abrir)

    def quieta():
        calc = getattr(w, "_calculo", None) or {"faltan": 0}
        return (hecho and not activas and QtWidgets.QApplication.activeModalWidget() is None
                and getattr(w, "_recog_worker", None) is None
                and getattr(w, "_tandas", None) is None and not getattr(w, "_provisional", False)
                and not calc["faltan"])

    limite = time.time() + a.tope
    calma = None
    while time.time() < limite:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if quieta():
            calma = calma or time.time()
            if time.time() - calma > 3.0:
                break
        else:
            calma = None
    fin.set()
    total = time.perf_counter() - t0

    # ── informe ──
    print(f"PDF: {os.path.basename(a.pdf)} · {total:.1f} s · {len(w.pipes)} utilidades, "
          f"{len(getattr(w, 'valvulas', []) or [])} válvulas", flush=True)
    print("\nPASOS DEL ASISTENTE")
    for t, nombre in pasos:
        print(f"  {t:7.1f} s  {nombre}")
    print("\nCARGAS (tarjeta: duración · veces pintada · hueco máx sin pintarse · barra de→a · etapas)")
    cargas = []
    for t, quien, titulo, detalle, frac in pinturas:
        c = cargas[-1] if cargas else None
        if c is None or c["quien"] != quien or c["titulo"] != titulo or t - c["fin"] > 2.0 or frac < c["a"] - 0.2:
            c = {"quien": quien, "titulo": titulo, "ini": t, "fin": t, "n": 0, "hueco": 0.0, "de": frac, "a": frac,
                 "etapas": []}
            cargas.append(c)
        c["hueco"] = max(c["hueco"], t - c["fin"])
        c["fin"], c["a"], c["n"] = t, max(c["a"], frac), c["n"] + 1
        linea = (detalle.splitlines() or [""])[-1]
        if linea and (not c["etapas"] or c["etapas"][-1] != linea):
            c["etapas"].append(linea)
    for c in cargas:
        dur = c["fin"] - c["ini"]
        if dur < 0.3:
            continue
        print(f"  {c['ini']:7.1f} s  {c['titulo'][:60]:60s} {dur:6.1f} s · {c['n']:4d} · {c['hueco']:5.2f} s · "
              f"{int(c['de'] * 100):3d}→{int(c['a'] * 100):3d} % · {len(c['etapas'])} etapas")
        for linea in c["etapas"][:3] + (["…"] if len(c["etapas"]) > 4 else []) + c["etapas"][3:][-1:]:
            print(f"               · {linea[:110]}")
    print(f"\nPAUSAS de la ventana (> {a.pausa:g} s sin atender eventos)")
    if not pausas:
        print("  ninguna")
    for p in sorted(pausas, key=lambda p: -p.get("dur", 0)):
        donde = max(p["pila"], key=p["pila"].get) if p["pila"] else "?"
        print(f"  {p['desde']:7.1f} s  {p.get('dur', 0):5.1f} s  "
              f"{'CON tarjeta: ' + p['tarjeta'][:50] if p['tarjeta'] else 'SIN TARJETA'}\n               en {donde}")
    peor = max((c["hueco"] for c in cargas), default=0.0)
    print(f"\nRESUMEN: {len(pausas)} pausas, la mayor {max((p.get('dur', 0) for p in pausas), default=0):.1f} s; "
          f"{sum(1 for p in pausas if not p['tarjeta'])} sin tarjeta; barra quieta como máximo {peor:.1f} s")
    if a.tiempos:
        with open(a.tiempos, "w", encoding="utf-8") as f:
            json.dump(tiempos_carga._cargar(), f, ensure_ascii=False, indent=1)
    w._dirty = False
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
