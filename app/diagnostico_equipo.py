"""Diagnóstico del EQUIPO (pedido del usuario 2026-11-17, tras el error de la Vista 3D en el equipo de un cliente).

`Asistente C3D.exe --diagnostico [--resumen archivo.txt]` (en desarrollo `python app/main.py --diagnostico`) junta
todo lo que se puede saber de la máquina —Windows, equipo, procesador, memoria, GPU y driver, discos, pantallas,
antivirus, AutoCAD/Civil 3D y el plugin, carpetas, proceso de trabajo, IA y una prueba REAL de OpenGL con el formato
de la Vista 3D— y lo guarda en la carpeta del registro (`nucleo.diagnostico`, …/pdf-to-cad/diagnosticos) como
`equipo-v<versión>-<fecha>.txt`. Arriba va un RESUMEN en palabras simples (✔ / ⚠ / ✖).

Código de salida: 0 = todo bien, 1 = hay avisos, 2 = la Vista 3D no funcionará. Lo usan:
- el instalador, al terminar (setup.iss: si hay avisos los muestra);
- la app, la primera vez que abre cada versión (`lanzar_si_falta`, en otro proceso: no frena la ventana);
- Ayuda → «Diagnóstico del equipo…» (`ui.dialogos.diagnostico_dialog`).
"""
from __future__ import annotations

import datetime
import glob
import os
import subprocess
import sys
import time

OK, AVISO, MAL = "✔", "⚠", "✖"
RAM_MIN_GB = 16
DISCO_MIN_GB = 5


def carpeta():
    from nucleo import diagnostico
    return os.path.dirname(diagnostico.ruta())


def _version():
    try:
        from nucleo.model import VERSION
        return VERSION
    except Exception:                                    # noqa: BLE001
        return "?"


def _app():
    from nucleo import diagnostico
    return [("Versión", _version()),
            ("Ejecutable", sys.executable),
            ("Instalado (.exe)", "sí" if getattr(sys, "frozen", False) else "no (desarrollo)"),
            ("Python", sys.version.replace("\n", " ")),
            ("Bibliotecas", diagnostico._versiones())]


def _ia():
    try:
        from PySide6 import QtCore
        s = QtCore.QSettings("pdf-to-cad", "app")
        prov = s.value("ia/proveedor", "") or ""
        modelo = s.value("ia/modelo_gemini" if str(prov).lower().startswith("gemini") else "ia/modelo", "") or ""
        return str(prov), str(s.value("ia/url", "") or ""), str(modelo)
    except Exception:                                    # noqa: BLE001
        return None


def _registros():
    """Las últimas sesiones del registro y cuántos errores tiene cada una."""
    out = []
    try:
        logs = sorted(glob.glob(os.path.join(carpeta(), "sesion-*.log")), key=os.path.getmtime, reverse=True)[:8]
        for p in logs:
            t = open(p, encoding="utf-8", errors="replace").read()
            n = t.count("Excepción no controlada") + t.count("error al dibujar") + t.count("Windows fatal exception")
            fecha = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
            out.append((os.path.basename(p), f"{fecha} · {n} errores"))
    except Exception as e:                               # noqa: BLE001
        out.append(("Registros", f"no se pudieron leer: {e}"))
    return out or [("Registros", "ninguno")]


def _valor(secciones, titulo, campo):
    for t, filas in secciones:
        if t == titulo:
            for c, v in filas:
                if c == campo:
                    return v
    return None


def resumen(secciones, veredicto):
    """[(símbolo, texto)] en palabras simples. El peor símbolo decide el código de salida."""
    out = []
    gpu = _valor(secciones, "OpenGL (Vista 3D)", "GPU") or "?"
    drv = _valor(secciones, "OpenGL (Vista 3D)", "GL_VERSION (incluye el driver)") or "?"
    if veredicto == "rapido":
        out.append((OK, f"Vista 3D: funcionará en modo rápido ({gpu})."))
    elif veredicto == "respaldo":
        out.append((AVISO, f"Vista 3D: funcionará sin el modo rápido. En proyectos grandes será lenta y usará mucha "
                           f"memoria. Actualiza el driver de video ({gpu}, OpenGL {drv})."))
    elif veredicto == "software":
        out.append((MAL, f"Vista 3D: el OpenGL va por software ({gpu}): escritorio remoto, máquina virtual o driver de "
                         f"video sin instalar. La Vista 3D no será usable; el resto de la app sí."))
    else:
        out.append((MAL, "Vista 3D: no funcionará en este equipo (OpenGL no disponible). El resto de la app sí."))
    try:
        from nucleo.equipo_sistema import _memoria, GB
        ram = _memoria().ullTotalPhys / GB
        out.append((OK if ram >= RAM_MIN_GB else AVISO,
                    f"Memoria: {ram:.0f} GB" + ("." if ram >= RAM_MIN_GB else
                                               f" (se recomiendan {RAM_MIN_GB} GB para planos y proyectos grandes).")))
    except Exception:                                    # noqa: BLE001
        pass
    for c, v in next((f for t, f in secciones if t == "Discos"), []):
        if c.startswith("Libre en"):
            try:
                gb = float(v.split(" GB")[0])
                if gb < DISCO_MIN_GB:
                    out.append((AVISO, f"Disco: poco espacio libre ({v})."))
            except ValueError:
                pass
    if _valor(secciones, "Sistema operativo", "Escritorio remoto") == "sí":
        out.append((AVISO, "Se está usando por escritorio remoto: la Vista 3D puede no tener aceleración."))
    hijo = _valor(secciones, "Carpetas y procesos de la app", "Proceso de trabajo (spawn)") or ""
    if hijo.startswith("NO"):
        out.append((MAL, "La app no puede abrir sus procesos de trabajo (¿antivirus?): reconocer y armar hojas fallará."))
    for c, v in next((f for t, f in secciones if t == "Carpetas y procesos de la app"), []):
        if c.startswith("Escribir en") and str(v).startswith("NO"):
            out.append((AVISO, f"Sin permiso para {c[len('Escribir en '):]}."))
    c3d = next((f for t, f in secciones if t == "AutoCAD / Civil 3D"), [])
    if any("no encontrado" in str(v) for _c, v in c3d):
        out.append((AVISO, "No se encontró AutoCAD / Civil 3D: el plugin no podrá usarse en este equipo."))
    if any(c == "Plugin AsistenteC3D.bundle" and str(v).startswith("no instalado") for c, v in c3d):
        out.append((AVISO, "El plugin de Civil 3D no está instalado."))
    return out


def codigo(res):
    simbolos = {s for s, _t in res}
    return 2 if MAL in simbolos else 1 if AVISO in simbolos else 0


def generar(destino=None, hijo=True):
    """Hace el diagnóstico y lo guarda. → (ruta del .txt, veredicto 3D, resumen). Necesita una QGuiApplication."""
    from nucleo import equipo_sistema as ES
    from ui.comun import equipo_opengl as EG
    t0 = time.time()
    gl_filas, veredicto = EG.probar()
    secciones = ES.secciones(ia=_ia(), hijo=hijo)
    secciones.insert(0, ("Aplicación", _app()))
    secciones.insert(4, ("OpenGL (Vista 3D)", gl_filas))
    try:
        secciones.insert(5, ("Pantallas (Qt)", EG.pantallas()))
    except Exception:                                    # noqa: BLE001
        pass
    secciones.append(("Últimas sesiones del registro", _registros()))
    res = resumen(secciones, veredicto)
    ahora = datetime.datetime.now()
    lineas = ["Asistente C3D · Diagnóstico del equipo",
              f"Fecha: {ahora.astimezone().isoformat(timespec='seconds')} · tardó {time.time() - t0:.1f} s", "",
              "======= RESUMEN =======", ""] + [f"{s} {t}" for s, t in res]
    ancho = max((len(c) for _t, filas in secciones for c, _v in filas), default=20)
    ancho = min(ancho, 44)
    for titulo, filas in secciones:
        lineas += ["", f"======= {titulo} =======", ""]
        for c, v in filas:
            v = str(v).replace("\r", " ").replace("\n", " ")
            lineas.append(f"{c.ljust(ancho)}  {v}" if v else c)
    texto = "\n".join(lineas) + "\n"
    destino = destino or carpeta()
    os.makedirs(destino, exist_ok=True)
    ruta = os.path.join(destino, f"equipo-v{_version()}-{ahora:%Y%m%d-%H%M%S}.txt")
    with open(ruta, "w", encoding="utf-8-sig") as f:        # con BOM: el Bloc de notas muestra bien ✔ ⚠ ✖
        f.write(texto)
    return ruta, veredicto, res


def main(argv):
    """Línea de comandos (sin ventana). Devuelve el código de salida."""
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])   # noqa: F841
    ruta, _v, res = generar()
    if "--resumen" in argv:
        i = argv.index("--resumen")
        if len(argv) > i + 1:
            try:
                with open(argv[i + 1], "w", encoding="utf-8-sig") as f:   # con BOM: el instalador lo lee como UTF-8
                    f.write("\n".join(f"{s} {t}" for s, t in res) + f"\n\nInforme completo: {ruta}\n")
            except OSError:
                pass
    try:
        print(ruta)
    except Exception:                                    # noqa: BLE001
        pass
    return codigo(res)


def comando():
    """Cómo lanzar el diagnóstico en otro proceso (el .exe o `python app/main.py`)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--diagnostico"]
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), "--diagnostico"]


def ya_hecho():
    return bool(glob.glob(os.path.join(carpeta(), f"equipo-v{_version()}-*.txt")))


def lanzar_si_falta():
    """La primera vez que se abre cada versión: el diagnóstico en OTRO proceso, sin esperar ni mostrar nada."""
    if os.environ.get("PDFCAD_SIN_DIAGNOSTICO") == "1" or ya_hecho():
        return None
    try:
        return subprocess.Popen(comando(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:                                    # noqa: BLE001
        return None
