"""Verifica que el instalador lleve TODO lo que necesita (2026-11-11, pedido del usuario: «prevenir que todo
funcione bien en el instalador»). Lo llama `build_all.bat` después de PyInstaller y antes de Inno Setup; también
se puede correr solo:

    python scripts/verificar_instalador.py            # todo (exige dist/ e installer/ ya armados)
    python scripts/verificar_instalador.py --estatico # solo lo que no necesita compilar (lo usa tests/test_instalador.py)

Revisa:
  1. Spec de PyInstaller: cada carpeta/archivo de `datas` existe; cada trabajo «modulo:funcion» del código va en
     `hiddenimports` y en la autoprueba.
  2. setup.iss: cada `Source` existe; PdfCadMcp va donde la app lo busca ({app}\\PdfCadMcp); versión = la de
     PackageContents.xml y la de la app (nucleo.model.VERSION).
  3. Plugin: el bundle trae TODAS las DLL que publica dotnet (antes faltaban Sqlite, SixLabors.Fonts…).
  4. PdfCadMcp.exe: arranca y da su catálogo de herramientas (no necesita Civil 3D).
  5. El .exe de la app: `--autoprueba` (módulos, datos, proceso hijo real) y los «missing module» de PyInstaller
     que sean de la app.
Sale con 0 si todo está bien y 1 si algo falla (y lo explica).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(RAIZ, "PDF-a-CAD.spec")
ISS = os.path.join(RAIZ, "installer", "setup.iss")
PKG = os.path.join(RAIZ, "installer", "PackageContents.xml")
PUBLISH = os.path.join(RAIZ, "installer", "publish")
BUNDLE = os.path.join(RAIZ, "installer", "AsistenteC3D.bundle", "Contents")
MCP_DIR = os.path.join(RAIZ, "installer", "PdfCadMcp")
EXE = os.path.join(RAIZ, "dist", "Asistente C3D.exe")
WARN = os.path.join(RAIZ, "build", "PDF-a-CAD", "warn-PDF-a-CAD.txt")
PAQUETES_APP = ("ui", "nucleo", "hoja", "ia", "reconocimiento", "exportar", "catalogo", "geo", "traduccion",
                "autoprueba", "digitize", "vector_pipeline", "raster_pipeline", "detect", "config", "geometry",
                "project_io")
OBJETIVO = re.compile(r"\"([a-z_]+(?:\.[a-z_0-9]+)+):[a-zA-Z_0-9]+\"")


def _leer(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        return f.read()


# ── 1. spec ──
def revisar_spec():
    errores = []
    spec = _leer(SPEC)
    for origen in re.findall(r"\(\s*'([^']+)'\s*,\s*'[^']*'\s*\)", spec):
        if not os.path.exists(os.path.join(RAIZ, origen)):
            errores.append(f"PDF-a-CAD.spec: datas apunta a «{origen}», que no existe")
    sys.path.insert(0, os.path.join(RAIZ, "app"))
    import autoprueba
    objetivos = set()
    for base, _d, archivos in os.walk(os.path.join(RAIZ, "app")):
        for a in archivos:
            if a.endswith(".py"):
                objetivos |= set(OBJETIVO.findall(_leer(os.path.join(base, a))))
    for m in sorted(objetivos):
        if f'"{m}"' not in spec:
            errores.append(f"PDF-a-CAD.spec: falta «{m}» en hiddenimports (se carga por nombre: en el .exe falla)")
        if m not in autoprueba.MODULOS_POR_NOMBRE:
            errores.append(f"app/autoprueba.py: falta «{m}» en MODULOS_POR_NOMBRE")
    return errores


# ── 2. setup.iss ──
def _version_iss(iss):
    m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', iss)
    return m.group(1) if m else None


def revisar_iss(compilado=True):
    errores = []
    iss = _leer(ISS)
    if not re.search(r'Source:\s*"PdfCadMcp\\\*".*DestDir:\s*"\{app\}\\PdfCadMcp"', iss):
        errores.append("setup.iss: no instala PdfCadMcp en {app}\\PdfCadMcp (la app lo busca ahí)")
    bat = _leer(os.path.join(RAIZ, "installer", "build_plugin.bat"))
    if "PdfCadMcp.csproj" not in bat or 'installer\\PdfCadMcp' not in bat:
        errores.append("build_plugin.bat: no publica PdfCadMcp en installer\\PdfCadMcp")
    v_iss = _version_iss(iss)
    m = re.search(r'AppVersion="([^"]+)"', _leer(PKG))
    if not m or m.group(1) != v_iss:
        errores.append(f"Versión distinta: setup.iss {v_iss} / PackageContents.xml {m.group(1) if m else '?'}")
    if compilado:
        base = os.path.dirname(ISS)
        defines = dict(re.findall(r'#define\s+(\w+)\s+"([^"]*)"', iss))
        for src in re.findall(r'^Source:\s*"([^"]+)"', iss, flags=re.M):
            linea = next(l for l in iss.splitlines() if l.startswith("Source:") and f'"{src}"' in l)
            for k, v in defines.items():
                src = src.replace("{#" + k + "}", v)
            ruta = os.path.normpath(os.path.join(base, src))
            existe = os.path.exists(ruta) if "*" not in ruta else os.path.isdir(os.path.dirname(ruta)) and any(
                True for _ in os.scandir(os.path.dirname(ruta)))
            if not existe and "skipifsourcedoesntexist" not in linea:
                errores.append(f"setup.iss: no existe «{ruta}» (¿falta compilar?)")
    return errores


def revisar_version_app():
    sys.path.insert(0, os.path.join(RAIZ, "app"))
    from nucleo import model
    v_iss = _version_iss(_leer(ISS))
    if v_iss and v_iss.split(".")[:2] != str(model.VERSION).split(".")[:2]:
        return [f"Aviso: setup.iss dice {v_iss} y la app (nucleo/model.py) {model.VERSION}"]
    return []


# ── 3. plugin ──
def revisar_bundle():
    if not os.path.isdir(PUBLISH):
        return [f"No existe {PUBLISH} (corre installer\\build_plugin.bat)"]
    publicadas = {f for f in os.listdir(PUBLISH) if f.lower().endswith(".dll")}
    en_bundle = {f for f in os.listdir(BUNDLE) if f.lower().endswith(".dll")} if os.path.isdir(BUNDLE) else set()
    faltan = sorted(publicadas - en_bundle)
    errores = [f"El bundle del plugin no trae {f} (sí se publica: el plugin instalado fallaría al usarla)"
               for f in faltan]
    if "proyecto1.dll" not in en_bundle:
        errores.append("El bundle del plugin no trae proyecto1.dll")
    return errores


# ── 4. PdfCadMcp ──
def revisar_mcp():
    exe = os.path.join(MCP_DIR, "PdfCadMcp.exe")
    if not os.path.isfile(exe):
        return [f"No existe {exe} (installer\\build_plugin.bat lo publica)"]
    sys.path.insert(0, os.path.join(RAIZ, "app"))
    from ia import civil3d_mcp
    try:
        c = civil3d_mcp.ClienteMCP(exe=exe)
        try:
            n = len(c.herramientas())
        finally:
            c.cerrar()
    except Exception as e:                         # noqa: BLE001
        return [f"PdfCadMcp.exe no arranca: {e}"]
    return [] if n > 0 else ["PdfCadMcp.exe arrancó pero no dio herramientas"]


# ── 5. el .exe ──
def revisar_warn():
    if not os.path.isfile(WARN):
        return []
    errores = []
    for linea in _leer(WARN).splitlines():
        m = re.match(r"missing module named '?([\w.]+)'? - imported by (.*)", linea)
        if not m:
            continue
        mod = m.group(1)
        if mod.split(".")[0] in PAQUETES_APP and "conditional" not in m.group(2) and "optional" not in m.group(2):
            errores.append(f"PyInstaller no encontró el módulo de la app «{mod}» ({m.group(2)[:120]})")
    return errores


def revisar_exe(espera_s=300):
    if not os.path.isfile(EXE):
        return [f"No existe {EXE} (corre PyInstaller)"], None
    salida = os.path.join(tempfile.mkdtemp(prefix="pdfcad_autoprueba_"), "informe.json")
    try:
        subprocess.run([EXE, "--autoprueba", salida], timeout=espera_s, check=False)
    except subprocess.TimeoutExpired:
        return [f"El .exe no terminó la autoprueba en {espera_s} s"], None
    if not os.path.isfile(salida):
        return ["El .exe no escribió el informe de la autoprueba (¿se cerró al arrancar?)"], None
    with open(salida, encoding="utf-8") as f:
        inf = json.load(f)
    errores = []
    if not inf.get("frozen"):
        errores.append("La autoprueba no corrió dentro del .exe")
    for grupo in ("modulos", "terceros", "datos"):
        for k, v in (inf.get(grupo) or {}).items():
            errores.append(f".exe · {grupo}: {k} → {v}")
    hijo = inf.get("hijo") or {}
    if not hijo.get("ok"):
        errores.append(f".exe · proceso hijo: {hijo.get('fallas')}")
    if inf.get("error"):
        errores.append(f".exe · {inf['error']}")
    return errores, inf


def main(argv):
    estatico = "--estatico" in argv
    errores, avisos = [], []
    errores += revisar_spec()
    errores += revisar_iss(compilado=not estatico)
    avisos += revisar_version_app()
    if not estatico:
        errores += revisar_bundle()
        errores += revisar_mcp()
        errores += revisar_warn()
        e, inf = revisar_exe()
        errores += e
        if inf:
            for k, v in (inf.get("opcionales") or {}).items():
                avisos.append(f"Opcional ausente en el .exe: {k} ({v}) — esa función queda sin usar")
    for a in avisos:
        print("  AVISO  " + a)
    for e in errores:
        print("  ERROR  " + e)
    print(("\n  OK: el instalador lleva todo lo necesario." if not errores
           else f"\n  {len(errores)} problema(s): revisar antes de entregar el instalador."))
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
