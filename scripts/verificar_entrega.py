"""verificar_entrega.py — lista de entrega del instalador (pedido del usuario 2026-11-13: «que no le
llegue al cliente un error que nadie vio»). Lo corre `1. build_all.bat` en tres fases; si una
comprobación falla, el .bat se detiene y NO sale instalador. La regresión con los PDF dorados
(`scripts/regresion.py`) NO va aquí (pedido del usuario 2026-11-13): se corre aparte.

    python scripts/verificar_entrega.py fuentes --version X.Y.Z   antes de compilar
        · pruebas de la app (`scripts/pruebas.py todo`: cada archivo en su proceso)
        · arnés del plugin C# (`API-CIVIL/proyecto1/PerfilPruebas`, `dotnet run -c Release`)
    python scripts/verificar_entrega.py exe                        después de PyInstaller
        · `scripts/verificar_instalador.py` (autoprueba del .exe, DLL del plugin, PdfCadMcp, setup.iss)
    python scripts/verificar_entrega.py final --instalador RUTA    después de Inno Setup
        · anota el instalador (tamaño y SHA-256) y cierra el informe

Informe: `dist/informe_entrega.md` (versión, commit, si había cambios sin commit, Python y bibliotecas
con que se compiló, cada comprobación con su resultado y tiempo). La salida completa de cada paso
queda en `dist/entrega/<paso>.log`. La fase `fuentes` empieza un informe nuevo; las otras lo continúan.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(RAIZ, "dist")
INFORME = os.path.join(DIST, "informe_entrega.md")
LOGS = os.path.join(DIST, "entrega")
PERFIL_PRUEBAS = os.path.join(RAIZ, "API-CIVIL", "proyecto1", "PerfilPruebas")

# (nombre del paso, descripción, comando, carpeta) por fase
PASOS = {
    "fuentes": [
        ("pruebas", "Pruebas de la app (pytest, todas)",
         [sys.executable, os.path.join("scripts", "pruebas.py"), "todo"], RAIZ),
        ("plugin", "Arnés del plugin C# (PerfilPruebas)",
         ["dotnet", "run", "-c", "Release"], PERFIL_PRUEBAS),
    ],
    "exe": [
        ("instalador", "Verificación del .exe y del instalador (incluye la autoprueba del .exe)",
         [sys.executable, os.path.join("scripts", "verificar_instalador.py")], RAIZ),
    ],
}


def _git(*args) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _entorno() -> list[str]:
    """Python y bibliotecas con que se compila (las de requirements-build.txt)."""
    lineas = [f"- Python {'.'.join(map(str, sys.version_info[:3]))} (`{sys.executable}`)"]
    try:
        sys.path.insert(0, os.path.join(RAIZ, "scripts"))
        import verificar_entorno_build as V
        _py, paquetes = V.leer()
        for nombre in paquetes:
            lineas.append(f"- {nombre} {V._instalada(nombre) or 'NO INSTALADO'}")
    except Exception as e:                                      # noqa: BLE001
        lineas.append(f"- (no se pudieron leer las bibliotecas: {e})")
    return lineas


def _cabecera(version: str) -> list[str]:
    commit = _git("rev-parse", "--short", "HEAD") or "?"
    rama = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    sucio = _git("status", "--porcelain")
    lineas = [f"# Informe de entrega — versión {version or '?'}", "",
              f"- Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
              f"- Rama `{rama}`, commit `{commit}`"]
    if sucio:
        n = len(sucio.splitlines())
        lineas.append(f"- ⚠ Había {n} archivo(s) con cambios sin commit: el instalador no corresponde "
                      f"exactamente al commit.")
    lineas += ["", "## Entorno de compilación", ""] + _entorno() + ["", "## Comprobaciones", "",
                                                                    "| Paso | Resultado | Tiempo |", "|---|---|---|"]
    return lineas


def _ultimas(salida: str, n: int = 3) -> str:
    utiles = [l.strip() for l in salida.splitlines()
              if l.strip() and ": warning " not in l]           # avisos del compilador C#: no son el resultado
    return " · ".join(utiles[-n:])[:300]


def correr(nombre, descripcion, comando, carpeta) -> tuple[bool, str, float]:
    print(f"\n--- {descripcion} ---", flush=True)
    os.makedirs(LOGS, exist_ok=True)
    t0 = time.time()
    try:
        entorno = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")   # tildes de los pasos en Python
        p = subprocess.Popen(comando, cwd=carpeta, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", env=entorno)
    except OSError as e:
        msg = f"No se pudo ejecutar {comando[0]}: {e}"
        print("  " + msg)
        with open(os.path.join(LOGS, nombre + ".log"), "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        return False, msg, time.time() - t0
    partes = []
    for linea in p.stdout:                       # se ve en la consola mientras corre
        print("  " + linea.rstrip(), flush=True)
        partes.append(linea)
    rc = p.wait()
    salida = "".join(partes)
    with open(os.path.join(LOGS, nombre + ".log"), "w", encoding="utf-8") as f:
        f.write(salida)
    return rc == 0, _ultimas(salida), time.time() - t0


def _escribir(lineas, nuevo: bool):
    os.makedirs(DIST, exist_ok=True)
    with open(INFORME, "w" if nuevo else "a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def _sha256(ruta) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lista de entrega del instalador")
    ap.add_argument("fase", choices=["fuentes", "exe", "final"])
    ap.add_argument("--version", default="")
    ap.add_argument("--instalador", default="")
    args = ap.parse_args(argv)

    if args.fase == "final":
        lineas = ["", "## Instalador", ""]
        if args.instalador and os.path.isfile(args.instalador):
            try:
                nombre = os.path.relpath(args.instalador, RAIZ)
            except ValueError:                          # otra unidad
                nombre = os.path.abspath(args.instalador)
            lineas += [f"- `{nombre}`",
                       f"- {os.path.getsize(args.instalador) / 2**20:.1f} MB",
                       f"- SHA-256 `{_sha256(args.instalador)}`"]
            ok = True
        else:
            lineas.append(f"- ✖ No se encontró el instalador «{args.instalador}»")
            ok = False
        _escribir(lineas, nuevo=False)
        print(f"\nInforme: {INFORME}")
        return 0 if ok else 1

    if args.fase == "fuentes":
        _escribir(_cabecera(args.version), nuevo=True)
        try:
            import pytest  # noqa: F401
        except ImportError:
            msg = ("Falta pytest en el Python que compila. Instálalo una vez con:\n"
                   "    python -m pip install -r requirements-build.txt")
            print("\n[ERROR] " + msg)
            _escribir(["", "**No se generó el instalador:** " + msg.replace("\n", " ")], nuevo=False)
            return 1
    elif not os.path.isfile(INFORME):
        _escribir(_cabecera(args.version), nuevo=True)

    malos = []
    for nombre, descripcion, comando, carpeta in PASOS[args.fase]:
        ok, resumen, dt = correr(nombre, descripcion, comando, carpeta)
        estado = "✔ bien" if ok else "✖ FALLÓ"
        _escribir([f"| {descripcion} | {estado} — {resumen.replace('|', '/')} | {dt:.0f} s |"], nuevo=False)
        if not ok:
            malos.append((descripcion, nombre))
    if malos:
        _escribir(["", "**No se generó el instalador:** " + "; ".join(
            f"{d} (detalle en `dist/entrega/{n}.log`)" for d, n in malos)], nuevo=False)
        print("\n[ERROR] Falló: " + "; ".join(d for d, _ in malos))
        print(f"        Detalle en dist\\entrega\\  ·  informe: {INFORME}")
        return 1
    print(f"\n[OK] Fase «{args.fase}» sin problemas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
