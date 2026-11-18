"""Mide lo que sigue al reconocimiento en la ventana REAL: vista previa (curvas de los quiebres), importar y el
editor hasta quedar quieto (`docs/rendimiento/GUIA.md`).

    python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --textos-de origen.pdf
    python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --foto antes.json
    python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --comparar antes.json
    python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --perfil "importar"
    python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --exportar anot --foto-dxf antes_dxf.json
    python scripts/rendimiento/importar.py hoja.pdf 0 --sugerir --exportar todo --comparar-dxf antes_dxf.json

Reconoce la hoja UNA vez con el zoom de la ventana y guarda el resultado junto al PDF de medición
(`<pdf>.reconocido-<hoja>-<zoom>.pickle`; `--reconocer` lo rehace): así se mide la importación sin esperar el
reconocimiento cada vez. Ajustes y carpetas aparte (no toca los de la app). Sale con 1 si `--comparar` difiere.

`--exportar anot|todo` = el botón «Exportar» tras importar (solo lo dibujado / el PDF digitalizado + lo dibujado),
con el diálogo de guardar contestado y «seguir sin arreglar» en la revisión previa. La caché del PDF digitalizado
va a una carpeta aparte nueva: «todo» digitaliza siempre (la 1.ª exportación del usuario). `--foto-dxf` /
`--comparar-dxf`: cada entidad del DXF (tipo, capa, puntos redondeados a 1e-6, XDATA), sin la cabecera.
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time

import comun


def foto_de(w) -> dict:
    def r(v):
        return round(float(v), 6)

    tub = []
    for p in w.pipes:
        tub.append({"capa": p.get("layer"), "pts": [[r(x), r(y)] for x, y in p.get("pts") or ()],
                    "diam": p.get("diam"), "ab": bool(p.get("ab")),
                    "fillets": {str(k): v for k, v in sorted((p.get("fillets") or {}).items())}})
    est = [{k: (r(v) if isinstance(v, float) else str(v)) for k, v in sorted(s.items())
            if k in ("x", "y", "cod", "net", "hidden", "curve", "radius_ft", "shape", "standalone", "solid")}
           for s in w.structures]
    return {"tuberias": tub, "estructuras": est, "valvulas": len(getattr(w, "valvulas", []) or []),
            "avisos": sorted(str(getattr(a, "mensaje", a)) for a in (getattr(w, "_normas_avisos", None) or []))}


def foto_dxf(ruta) -> dict:
    import ezdxf
    doc = ezdxf.readfile(ruta)

    def r(v):
        return round(float(v), 6)

    out = []
    for e in doc.modelspace():
        d = {"tipo": e.dxftype(), "capa": e.dxf.get("layer", "")}
        for k in ("insert", "start", "end", "center", "location", "text_midpoint"):
            if e.dxf.hasattr(k):
                d[k] = [r(c) for c in e.dxf.get(k)]
        for k in ("radius", "height", "rotation", "start_angle", "end_angle", "const_width"):
            if e.dxf.hasattr(k):
                d[k] = r(e.dxf.get(k))
        if e.dxftype() == "LWPOLYLINE":
            d["pts"] = [[r(c) for c in p] for p in e.get_points("xyb")]
            d["cerrada"] = bool(e.closed)
        elif e.dxftype() == "POLYLINE":
            d["pts"] = [[r(c) for c in v.dxf.location] for v in e.vertices]
        if e.dxftype() in ("TEXT", "MTEXT"):
            d["texto"] = e.dxf.get("text", "") if e.dxftype() == "TEXT" else e.text
        if e.has_xdata("PDFCAD"):
            d["xdata"] = [str(v) for _c, v in e.get_xdata("PDFCAD")]
        out.append(d)
    out.sort(key=lambda d: repr(sorted(d.items())))
    return {"entidades": out, "capas": sorted(l.dxf.name for l in doc.layers)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("hoja", type=int, nargs="?", default=0)
    ap.add_argument("--sugerir", action="store_true"); ap.add_argument("--textos-de")
    ap.add_argument("--reconocer", action="store_true", help="volver a reconocer aunque haya resultado guardado")
    ap.add_argument("--perfil", nargs="*", default=None, help="pasos a perfilar (parte del nombre); sin nada, todos")
    ap.add_argument("--filas", type=int, default=25)
    ap.add_argument("--foto"); ap.add_argument("--comparar")
    ap.add_argument("--exportar", choices=("anot", "todo")); ap.add_argument("--foto-dxf"); ap.add_argument("--comparar-dxf")
    ap.add_argument("--pilas", type=float, default=0,
                    help="cada tantos segundos, la pila de cada hilo a <pdf>.pilas.txt (¿dónde está un paso que no termina?)")
    a = ap.parse_args()
    if a.pilas > 0:
        import faulthandler
        faulthandler.dump_traceback_later(a.pilas, repeat=True, file=open(a.pdf + ".pilas.txt", "w"))
    comun.preparar(con_qt=True)
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana import app_window
    app_window.Main._run_recognition_wizard = lambda self: None
    QtWidgets.QMessageBox.information = lambda *x, **k: None
    QtWidgets.QMessageBox.warning = lambda *x, **k: None

    def bombea(cond, tope=600):
        fin = time.time() + tope
        while time.time() < fin and not cond():
            app.processEvents(QtCore.QEventLoop.AllEvents, 20)

    def quieta():
        calc = getattr(w, "_calculo", None) or {"faltan": 0}
        return getattr(w, "_tandas", None) is None and not getattr(w, "_provisional", False) and not calc["faltan"]

    def medir(nombre, fn):
        perf = a.perfil is not None and (not a.perfil or any(s.lower() in nombre.lower() for s in a.perfil))
        if perf:
            res, seg, filas = comun.perfilar(fn, a.filas)
        else:
            (res, seg), filas = comun.cronometro(fn), None
        print(f"{nombre:38s} {seg:8.2f} s" + ("  (con perfil)" if perf else ""), flush=True)
        if filas:
            comun.imprimir_perfil(filas)
        return res

    w = app_window.Main(); w.resize(1600, 900); w.show(); app.processEvents()
    # la app arma la hoja compuesta y ya trae su escala (`_build_composite_doc` → `_scale_override`): aquí se lee
    # una vez del texto (`detect_scale`, ~28 s en Southwest) y se guarda junto al PDF, para medir lo mismo que la app
    escala = f"{a.pdf}.escala-{a.hoja}.txt"
    if not os.path.isfile(escala):
        import pymupdf as fitz
        import vector_pipeline as VP
        with fitz.open(a.pdf) as d:
            with open(escala, "w") as f:
                f.write(repr(float(VP.detect_scale(d[a.hoja]))))

    def abrir():
        w._open_pdf_path(a.pdf)
        with open(escala) as f:
            w._scale_override = float(f.read())
        w._load_page(a.hoja)
    medir("abrir el PDF y cargar la hoja", abrir)
    guardado = f"{a.pdf}.reconocido-{a.hoja}-{w.zoom:g}.pickle"
    if a.reconocer or not os.path.isfile(guardado):
        import pymupdf as fitz
        from reconocimiento import recognition as rec, recognition_trabajo as RT
        utilidades, roles = tuple(rec.SUPPORTED_UTILITIES), {}
        if a.sugerir:
            from hoja import estilos_sugeridos as ES
            with fitz.open(a.pdf) as d, fitz.open(a.textos_de or a.pdf) as o:
                s = ES.sugerir(d[a.hoja], textos=ES.textos_de_documento(o))
            utilidades = (s.utilidad,)
            roles = {s.utilidad: {rec.ROLE_LINEAS: list(s.lineas), rec.ROLE_BUZONES: []}}
        res = medir("reconocer (se guarda)", lambda: RT.reconocer_hoja(
            a.pdf, a.hoja, zoom=w.zoom, utilities=utilidades, roles_by_utility=roles))
        with open(guardado, "wb") as f:
            pickle.dump(res, f)
    with open(guardado, "rb") as f:
        resultados = pickle.load(f)
    print(f"    {sum(len(r.drawable) for r in resultados)} líneas reconocidas", flush=True)
    from reconocimiento import recognition_quiebres as RQ
    import copy
    medir("vista previa: curvas de los quiebres", lambda: RQ.curvas_de_quiebres(copy.deepcopy(resultados), w.zoom))
    medir("importar", lambda: w._import_recognized_pipes(resultados))
    medir("editor quieto (avisos y marcas)", lambda: bombea(quieta))
    print(f"    {len(w.pipes)} utilidades, {len(w.structures)} estructuras, "
          f"{len(getattr(w, 'valvulas', []) or [])} válvulas", flush=True)
    datos = foto_de(w)
    codigo_dxf = 0
    if a.exportar:
        import tempfile
        from ui.dialogos import limpieza_dialog
        limpieza_dialog.LimpiezaDialog.exec = lambda self: setattr(self, "accion", "seguir")
        salida = os.path.join(tempfile.mkdtemp(prefix="pdfcad_dxf"), "salida.dxf")
        QtWidgets.QFileDialog.getSaveFileName = lambda *x, **k: (salida, "")
        hecho = []
        cerrar = app_window.Main._cerrar_avance_export
        app_window.Main._cerrar_avance_export = lambda self: (cerrar(self), hecho.append(time.perf_counter()))

        def exportar():
            w.run_pipeline(a.exportar)
            bombea(lambda: hecho and os.path.isfile(salida), tope=1800)
        medir(f"exportar ({a.exportar})", exportar)
        if not os.path.isfile(salida):
            print("    no se escribió el DXF", flush=True)
        else:
            print(f"    DXF {os.path.getsize(salida) / 1e6:.1f} MB", flush=True)
            fd = foto_dxf(salida)
            if a.foto_dxf:
                comun.guardar_foto(a.foto_dxf, fd)
            if a.comparar_dxf:
                codigo_dxf = 1 if comun.comparar(a.comparar_dxf, fd) else 0
    w._dirty = False
    if a.foto:
        comun.guardar_foto(a.foto, datos)
    codigo = 1 if (a.comparar and comun.comparar(a.comparar, datos)) or codigo_dxf else 0
    sys.stdout.flush()
    os._exit(codigo)                                    # (sin esperar a los procesos de trabajo)


if __name__ == "__main__":
    main()
