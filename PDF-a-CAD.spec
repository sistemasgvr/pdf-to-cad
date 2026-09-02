# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

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
