# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    # Iconos SVG (Iconify/Material Design Icons) — `icons.py` los busca en
    # `<carpeta-de-icons.py>/icons/<set>/<name>.svg`. Al bundelar, PyInstaller
    # extrae `icons.py` a la raíz del bundle (_MEIPASS), así que el destino
    # correcto es 'icons' (NO 'app/icons') para que _ICONS_DIR los encuentre.
    ('app/icons', 'icons'),
    # Documentos por idioma (manual.es.html, manual.en.html): `i18n.load_doc`
    # los busca en `<carpeta-de-i18n.py>/docs`, que en el bundle es _MEIPASS/docs.
    ('app/docs', 'docs'),
]
binaries = []
hiddenimports = []

# Iconos SVG MDI (app/icons/mdi/*.svg) — sin esto el exe muestra X rojas
# (_fallback_icon). Destino 'icons' al lado de icons.py en _MEIPASS.
datas += [('app/icons', 'icons')]

# Paquetes cuyo código + DATOS + submódulos hay que empaquetar completos para que
# funcionen dentro del .exe. Si alguno no está instalado, se ignora (no rompe el build).
#   - pyproj: reproyección (calles/parcelas de NavigateLA).
#   - contextily / xyzservices / rasterio / mercantile: el MAPA BASE (landbase) de
#     la georreferenciación. Sin empaquetarlos, `import contextily` falla en el .exe
#     y el basemap no carga nunca (aunque calles y parcelas sí, porque usan pyproj).
#   - certifi: CA bundle para el HTTPS de los tiles del mapa base.
for _pkg in ("pyproj", "contextily", "xyzservices", "rasterio", "mercantile", "certifi"):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d; binaries += _b; hiddenimports += _h
    except Exception:
        pass


a = Analysis(
    ['app\\main.py'],
    pathex=['app', '.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # La app usa PySide6. Si el entorno tiene tambien PyQt5/PyQt6/PySide2
    # instalados (matplotlib, mplcursors, etc. suelen arrastrarlos), PyInstaller
    # aborta al encontrar dos bindings de Qt a la vez. Se excluyen aca.
    excludes=['PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Asistente C3D',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
