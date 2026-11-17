"""Mide el EDITOR con un proyecto abierto: elegir una línea, Esc, avisos, capas, zoom (`docs/rendimiento/GUIA.md`).

    python scripts/rendimiento/editor.py proyecto.digproj
    python scripts/rendimiento/editor.py proyecto.digproj --valvulas 2000 --buzones 1500   # carga de más (simulada)
    python scripts/rendimiento/editor.py proyecto.digproj --perfil "clic en una línea" "redibujo sin cambios"
    python scripts/rendimiento/editor.py proyecto.digproj --solo "elegir" "clic"          # solo esas acciones

Abre la ventana REAL sin pantalla (offscreen), con ajustes aparte: no toca los de la app. Por acción da tres
tiempos: «acción» (la llamada, con la ventana congelada), «pintar» (eventos + repintar el plano) y «quieta» (lo
que sigue en segundo plano: cálculo de fondo y carga de marcas por tandas, con la ventana atendiendo).

`--valvulas/--buzones` agregan válvulas y buzones sobre las tuberías del proyecto para simular una hoja
compuesta de gas o alcantarillado cuando no se tiene ese proyecto a mano.
"""
from __future__ import annotations

import argparse
import os
import time

import comun


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proyecto")
    ap.add_argument("--valvulas", type=int, default=0); ap.add_argument("--buzones", type=int, default=0)
    ap.add_argument("--perfil", nargs="*", default=[], help="acciones a perfilar (parte del nombre)")
    ap.add_argument("--solo", nargs="*", default=[], help="solo estas acciones (parte del nombre)")
    ap.add_argument("--filas", type=int, default=25)
    a = ap.parse_args()
    comun.preparar(con_qt=True)
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana import app_window

    def bombea(seg=0.0, cond=None, tope=600):
        fin, t0 = time.time() + tope, time.time()
        while time.time() < fin:
            app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            if cond is not None:
                if cond():
                    break
            elif time.time() - t0 >= seg:
                break

    def quieta():
        calc = getattr(w, "_calculo", None) or {"faltan": 0}
        return getattr(w, "_tandas", None) is None and not getattr(w, "_provisional", False) and not calc["faltan"]

    def esperar():
        bombea(cond=quieta); bombea(0.5); bombea(cond=quieta)

    def medir(nombre, fn):
        if a.solo and not any(s.lower() in nombre.lower() for s in a.solo):
            return
        perfilar = any(s.lower() in nombre.lower() for s in a.perfil)

        def todo():
            t0 = time.perf_counter()
            fn()
            t1 = time.perf_counter()
            app.processEvents()
            w.canvas.viewport().repaint()
            return t1 - t0, time.perf_counter() - t1
        if perfilar:
            (accion, pintar), _seg, filas = comun.perfilar(todo, a.filas)
        else:
            (accion, pintar), filas = todo(), None
        t2 = time.perf_counter()
        bombea(cond=quieta, tope=300)
        print(f"{nombre:34s} acción {accion:7.3f} s   pintar {pintar:6.3f} s   quieta {time.perf_counter() - t2:6.3f} s"
              + ("   (con perfil)" if perfilar else ""), flush=True)
        if filas:
            comun.imprimir_perfil(filas)

    w = app_window.Main(); w.resize(1600, 900); w.show(); app.processEvents()
    t0 = time.perf_counter()
    w._open_project_path(a.proyecto)
    t1 = time.perf_counter()
    esperar()
    print(f"abrir {t1 - t0:.2f} s · avisos listos {time.perf_counter() - t1:.2f} s después · {len(w.pipes)} utilidades, "
          f"{len(w.structures)} estructuras, {len(getattr(w, 'valvulas', []) or [])} válvulas, "
          f"{sum(len(c.marcas) for c in w._marcas.capas.values())} marcas", flush=True)
    n = len(w.pipes)
    if not n:
        raise SystemExit("El proyecto no tiene utilidades.")
    if a.buzones or a.valvulas:
        from nucleo import valvulas as V
        con_pts = [p for p in w.pipes if len(p.get("pts") or ()) >= 2]
        for k, p in enumerate(con_pts[::max(1, len(con_pts) // max(a.buzones, 1))][:a.buzones]):
            x, y = p["pts"][0]
            w.structures.append({"x": x, "y": y, "cod": f"BZ-{k}", "net": "gravity", "standalone": True,
                                 "utility": "ALCANTARILLADO"})
        for p in con_pts[1::max(1, len(con_pts) // max(a.valvulas, 1))][:a.valvulas]:
            (x0, y0), (x1, y1) = p["pts"][0], p["pts"][1]
            w.valvulas.append(V.nueva((x0 + x1) / 2, (y0 + y1) / 2))
        t0 = time.perf_counter(); w._redraw()
        print(f"redibujo con {a.buzones} buzones y {a.valvulas} válvulas de más: {time.perf_counter() - t0:.2f} s", flush=True)
        esperar()
    w.canvas.viewport().repaint()

    medir("pintar la vista entera", lambda: None)
    medir("elegir en la lista", lambda: w.pipe_list.setCurrentRow(n // 2))
    medir("elegir otra en la lista", lambda: w.pipe_list.setCurrentRow(n // 3))
    if not a.buzones:                                   # (los buzones simulados no están en las listas)
        p = next(q for q in w.pipes[n // 4:] + w.pipes if len(q.get("pts") or ()) >= 2)["pts"]
        mx, my = (p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2
        medir("clic en una línea", lambda: w._pick(mx, my))
    medir("Esc", lambda: w._on_escape())
    medir("redibujo sin cambios", lambda: w._redraw())
    for nombre, accion in (("accesorios", w.act_show_acc), ("avisos de normativa", w.act_show_normas),
                           ("conflictos", w.chk_show_conflicts)):
        medir(f"{nombre}: apagar", lambda x=accion: x.setChecked(False))
        medir(f"{nombre}: encender", lambda x=accion: x.setChecked(True))
    capa = w.pipes[0].get("layer")

    def apagar():
        w.capas_apagadas = set(w.capas_apagadas) | {capa}; w._aplicar_capas()

    def encender():
        w.capas_apagadas = set(); w._aplicar_capas()
    medir(f"capa {capa}: apagar", apagar)
    medir(f"capa {capa}: encender", encender)
    medir("zoom ×4", lambda: w.canvas.scale(4, 4))
    medir("zoom ×4 más", lambda: w.canvas.scale(4, 4))
    medir("de cerca: elegir en la lista", lambda: w.pipe_list.setCurrentRow(n // 5))
    medir("de cerca: accesorios apagar", lambda: w.act_show_acc.setChecked(False))
    medir("de cerca: accesorios encender", lambda: w.act_show_acc.setChecked(True))
    w._dirty = False
    print("FIN", flush=True)
    os._exit(0)                                         # (sin esperar a los procesos de trabajo)


if __name__ == "__main__":
    main()
