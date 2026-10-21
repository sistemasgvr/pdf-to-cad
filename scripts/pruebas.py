"""Pruebas por GRUPOS y en paralelo (pedido del usuario 2026-10-19: «evitar tanto tiempo de
procesamiento»). Cada archivo de pruebas corre en su propio proceso de pytest, varios a la vez
(sin pytest-xdist), y al final un resumen con el tiempo de cada uno.

Uso (desde la raíz del proyecto):
    python scripts/pruebas.py                 # lista los grupos
    python scripts/pruebas.py mapas           # un grupo
    python scripts/pruebas.py mapas compositor -j 4
    python scripts/pruebas.py tests/test_routes.py tests/test_pdf_styles.py   # archivos sueltos
    python scripts/pruebas.py todo            # todo, en paralelo
    python scripts/pruebas.py mapas -k leyenda   # lo que va después de los grupos pasa a pytest

Grupos: ver `GRUPOS`. Un archivo de pruebas nuevo que no esté en ningún grupo sale en «otros»
(y `todo` lo incluye igual)."""
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRUPOS = {
    # mapas SIG sin capas (Phoenix): capas por estilo, leyenda, acometidas, hoja compuesta de mapas
    "mapas": ["test_pdf_styles", "test_mapas_leyenda", "test_mapas_sin_capas", "test_acometidas_gravedad",
              "test_mapas_compuestos"],
    # componer hoja: piezas, costuras CAD, sugerencia, escaneos, hoja enorme y nitidez
    "compositor": ["test_composite", "test_composite_checks", "test_composite_seam", "test_composite_dialog",
                   "test_composicion_sugerida", "test_piezas_exactas", "test_scan_composition", "test_scan_tools",
                   "test_esquinas_libres", "test_fundir_vectorial", "test_area_sugerida",
                   "test_hoja_enorme", "test_nitidez_zoom", "test_teselas", "test_sheet_crops", "test_sheet_layout"],
    # «Capas de la hoja», leyendas BOE y del PDF, vista previa
    "capas": ["test_layer_dialog", "test_layer_legend", "test_layer_standard", "test_leyenda_cruce",
              "test_leyenda_estandar", "test_pdf_layers", "test_organized_layers", "test_organized_recognition",
              "test_recognition_dialog", "test_recognition_summary", "test_recognition_cache",
              "test_respaldo_editor"],
    # reconocimiento de planos CAD (núcleo geométrico, curvas, bóvedas, letras)
    "reconocimiento": ["test_recognition", "test_recognition_geom", "test_recognition_arcs", "test_recognition_ends",
                       "test_recognition_letters", "test_recognition_no_inventar", "test_recognition_text_gaps",
                       "test_recognition_vault_snap", "test_recognition_walls", "test_routes", "test_angulos_quiebres",
                       "test_bovedas_no_inventar", "test_codos_abiertos", "test_cruces_con_tinta",
                       "test_curvas_encadenadas", "test_curve_precision", "test_curve_structure_contacts",
                       "test_curvitas_una_curva",
                       "test_letra_en_el_hueco", "test_detect", "test_lectura_unica"],
    # perfiles por utilidad (ventana real → DXF)
    "utilidades": ["test_water_profile", "test_sewer_profile", "test_sewer_integration", "test_gas_profile",
                   "test_gas_integration", "test_telecom_profile", "test_telecom_integration"],
    # editor, modelo, exportar, catálogo, 3D, normas
    "editor": ["test_model_ops", "test_project_io", "test_xdata", "test_curvas_editor", "test_quiebres_curvas",
               "test_mover_vertice", "test_unir_utilidades", "test_limpieza", "test_edicion_bloque",
               "test_duct_bank", "test_duct_bank_multi", "test_solido_cota", "test_vault_import", "test_nombre_red",
               "test_export_hoja_de_trabajo", "test_vista3d", "test_conflictos_excel", "test_normas",
               "test_normas_aprobacion", "test_civil_catalog", "test_catalogo_tamanos",
               "test_catalogo_tamanos_ventana", "test_georef", "test_model_georef"],
    # interfaz general
    "interfaz": ["test_i18n", "test_icons", "test_theme", "test_paneles", "test_autoguardado", "test_proceso"],
}


def _archivos_de(nombre: str):
    if nombre in GRUPOS:
        return [os.path.join("tests", f + ".py") for f in GRUPOS[nombre]
                if os.path.exists(os.path.join(RAIZ, "tests", f + ".py"))]
    if nombre == "otros":
        todos = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(RAIZ, "tests", "test_*.py"))}
        en_grupo = {f for fs in GRUPOS.values() for f in fs}
        return [os.path.join("tests", f + ".py") for f in sorted(todos - en_grupo)]
    if nombre == "todo":
        return sorted(os.path.relpath(p, RAIZ) for p in glob.glob(os.path.join(RAIZ, "tests", "test_*.py")))
    if os.path.exists(os.path.join(RAIZ, nombre)):
        return [nombre]
    raise SystemExit(f"No conozco «{nombre}». Grupos: {', '.join(GRUPOS)}, otros, todo.")


def _correr(archivo: str, extra):
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", archivo, *extra],
                       cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return archivo, p.returncode, time.time() - t0, p.stdout + p.stderr


def main(argv):
    if not argv:
        print(__doc__)
        for g, fs in GRUPOS.items():
            print(f"  {g:15s} {len(fs)} archivos")
        print(f"  {'otros':15s} {len(_archivos_de('otros'))} archivos (sin grupo)")
        return 0
    j = max(1, (os.cpu_count() or 2) // 2)
    nombres, extra = [], []
    it = iter(argv)
    for a in it:
        if a == "-j":
            j = int(next(it))
        elif extra or a.startswith("-"):
            extra.append(a)
        else:
            nombres.append(a)
    archivos = list(dict.fromkeys(f for n in nombres for f in _archivos_de(n)))
    t0 = time.time()
    print(f"{len(archivos)} archivos, {j} a la vez…", flush=True)
    malos = []
    with ThreadPoolExecutor(j) as ex:
        for archivo, rc, dt, salida in ex.map(lambda f: _correr(f, extra), archivos):
            ultima = [l for l in salida.strip().splitlines() if l.strip()][-1:] or [""]
            estado = "ok " if rc in (0, 5) else "MAL"
            print(f"  {estado} {dt:6.1f} s  {archivo}  {ultima[0][:90]}", flush=True)
            if rc not in (0, 5):
                malos.append((archivo, salida))
    for archivo, salida in malos:
        print("\n" + "=" * 30, archivo, "=" * 30)
        print(salida[-4000:])
    print(f"\n{len(archivos) - len(malos)} de {len(archivos)} archivos bien · {time.time() - t0:.0f} s en total")
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
