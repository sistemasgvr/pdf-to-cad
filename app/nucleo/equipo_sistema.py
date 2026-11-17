"""Datos del EQUIPO para el diagnóstico (pedido del usuario 2026-11-17, tras el error de la Vista 3D en el equipo de
un cliente: «que se guarde un txt con todas las especificaciones detectadas de la máquina, lo máximo posible»).

Sin Qt: Windows (registro, `GlobalMemoryStatusEx`, `GetSystemMetrics`) y UNA llamada a PowerShell (CIM/WMI) que
devuelve todo en JSON. Cada parte va en su try: lo que no se pueda leer queda como «?» con el motivo; el diagnóstico
nunca se cae. La parte de OpenGL está en `ui.comun.equipo_opengl` (necesita Qt).

`secciones()` → [(título, [(campo, valor)])] en el orden del informe.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

GB = 1024 ** 3
MB = 1024 ** 2

# Una sola llamada a PowerShell: cada consulta en su try (una clase CIM que falta no tumba las demás).
_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Q($cls, $props, $ns = 'root/cimv2') {
  try { @(Get-CimInstance -Namespace $ns -ClassName $cls -ErrorAction Stop | Select-Object $props) } catch { @() }
}
$o = [ordered]@{}
$o.so = Q 'Win32_OperatingSystem' @('Caption','Version','BuildNumber','OSArchitecture','InstallDate','LastBootUpTime','TotalVirtualMemorySize','FreeVirtualMemory','MUILanguages','Locale')
$o.equipo = Q 'Win32_ComputerSystem' @('Manufacturer','Model','SystemType','TotalPhysicalMemory','NumberOfProcessors','NumberOfLogicalProcessors','HypervisorPresent','PCSystemType')
$o.bios = Q 'Win32_BIOS' @('Manufacturer','SMBIOSBIOSVersion','ReleaseDate')
$o.placa = Q 'Win32_BaseBoard' @('Manufacturer','Product')
$o.cpu = Q 'Win32_Processor' @('Name','Manufacturer','NumberOfCores','NumberOfLogicalProcessors','MaxClockSpeed','L2CacheSize','L3CacheSize','VirtualizationFirmwareEnabled')
$o.ram = Q 'Win32_PhysicalMemory' @('Capacity','Speed','ConfiguredClockSpeed','Manufacturer','PartNumber','SMBIOSMemoryType')
$o.gpu = Q 'Win32_VideoController' @('Name','AdapterCompatibility','DriverVersion','DriverDate','AdapterRAM','VideoProcessor','CurrentHorizontalResolution','CurrentVerticalResolution','CurrentRefreshRate','Status','PNPDeviceID','InstalledDisplayDrivers')
$o.monitores = Q 'Win32_DesktopMonitor' @('Name','ScreenWidth','ScreenHeight')
$o.discos = Q 'Win32_LogicalDisk' @('DeviceID','DriveType','FileSystem','Size','FreeSpace','VolumeName')
$o.fisicos = Q 'Win32_DiskDrive' @('Model','MediaType','Size','InterfaceType')
$o.energia = Q 'Win32_Battery' @('Name','EstimatedChargeRemaining','BatteryStatus')
$o.antivirus = Q 'AntiVirusProduct' @('displayName','productState') 'root/SecurityCenter2'
try {
  $o.vram = @(Get-ItemProperty 'HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction Stop |
    Where-Object { $_.DriverDesc } | Select-Object DriverDesc, DriverVersion, DriverDate, @{n='MemoriaBytes';e={$_.'HardwareInformation.qwMemorySize'}})
} catch { $o.vram = @() }
try { $o.plan = (powercfg /getactivescheme) -join ' ' } catch { $o.plan = '' }
$o | ConvertTo-Json -Depth 4 -Compress
"""


def _ps(timeout=45):
    """Todo lo de CIM/WMI en un dict (vacío con '_error' si PowerShell no está o tarda)."""
    if sys.platform != "win32":
        return {"_error": "no es Windows"}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", _PS], capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        texto = r.stdout.decode("utf-8", "replace").strip()
        if not texto:
            return {"_error": f"PowerShell sin salida (código {r.returncode}): "
                              f"{r.stderr.decode('utf-8', 'replace').strip()[:300]}"}
        return json.loads(texto[texto.find("{"):])
    except Exception as e:                                       # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}


def _fecha(v):
    """`/Date(1653955200000)/` (así salen las fechas en el JSON de PowerShell 5) → «2022-05-31»."""
    import re
    m = re.search(r"/Date\((-?\d+)", str(v or ""))
    if not m:
        return str(v) if v else "?"
    import datetime
    return datetime.datetime.fromtimestamp(int(m.group(1)) / 1000, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _lista(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _gb(b):
    try:
        return f"{int(b) / GB:.1f} GB"
    except (TypeError, ValueError):
        return "?"


def _reg(clave, valor, raiz="HKLM"):
    try:
        import winreg
        base = winreg.HKEY_LOCAL_MACHINE if raiz == "HKLM" else winreg.HKEY_CURRENT_USER
        with winreg.OpenKey(base, clave) as k:
            return winreg.QueryValueEx(k, valor)[0]
    except Exception:                                            # noqa: BLE001
        return None


def _memoria():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError("GlobalMemoryStatusEx")
    return m


def _metrica(n):
    try:
        return int(ctypes.windll.user32.GetSystemMetrics(n))
    except Exception:                                            # noqa: BLE001
        return None


def _escribible(carpeta):
    try:
        os.makedirs(carpeta, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=carpeta, prefix="prueba-", delete=True) as f:
            f.write(b"ok")
        return "sí"
    except Exception as e:                                       # noqa: BLE001
        return f"NO ({type(e).__name__}: {e})"


def _autodesk():
    """AutoCAD/Civil 3D instalados (registro) y el plugin de la app."""
    out = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Autodesk\AutoCAD") as k:
            i = 0
            while True:
                try:
                    r = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                with winreg.OpenKey(k, r) as kr:
                    j = 0
                    while True:
                        try:
                            prod = winreg.EnumKey(kr, j)
                        except OSError:
                            break
                        j += 1
                        base = rf"SOFTWARE\Autodesk\AutoCAD\{r}\{prod}"
                        nombre = _reg(base, "ProductName")
                        if not nombre:                   # subclaves sin producto (idiomas, «InstalledProducts»)
                            continue
                        lugar = _reg(base, "AcadLocation") or _reg(base, "Location") or "?"
                        idioma = _reg(base, "Language") or ""
                        out.append((f"{r} {prod}", f"{nombre} · {lugar} {idioma}".strip()))
    except Exception as e:                                       # noqa: BLE001
        out.append(("AutoCAD (registro)", f"no se pudo leer: {type(e).__name__}"))
    if not out:
        out.append(("AutoCAD / Civil 3D", "no encontrado en el registro"))
    pf = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    bundle = os.path.join(pf, "Autodesk", "ApplicationPlugins", "AsistenteC3D.bundle")
    xml = os.path.join(bundle, "PackageContents.xml")
    if os.path.isfile(xml):
        try:
            import re
            t = open(xml, encoding="utf-8", errors="replace").read()
            ver = re.search(r'AppVersion="([^"]+)"', t)
            series = re.findall(r'SeriesMin="([^"]+)"', t)
            out.append(("Plugin AsistenteC3D.bundle", f"instalado · versión {ver.group(1) if ver else '?'} · "
                                                      f"AutoCAD desde {', '.join(series) or '?'}"))
        except Exception as e:                                   # noqa: BLE001
            out.append(("Plugin AsistenteC3D.bundle", f"instalado, no se pudo leer: {e}"))
        dlls = []
        for raiz, _d, archivos in os.walk(os.path.join(bundle, "Contents")):
            dlls += [os.path.join(raiz, a) for a in archivos if a.lower().endswith(".dll")]
        out.append(("Plugin: DLL", f"{len(dlls)} archivos"))
    else:
        out.append(("Plugin AsistenteC3D.bundle", f"no instalado ({bundle})"))
    return out


def _proceso_hijo():
    """¿Arranca un proceso hijo «spawn» (como `ui.comun.proceso`)? Los antivirus a veces lo bloquean."""
    import multiprocessing as mp
    t = time.time()
    try:
        ctx = mp.get_context("spawn")
        with ctx.Pool(1) as p:
            r = p.apply_async(os.getpid).get(timeout=60)
        return f"sí (pid {r}, {time.time() - t:.1f} s)"
    except Exception as e:                                       # noqa: BLE001
        return f"NO ({type(e).__name__}: {e})"


def _ollama(url):
    try:
        import urllib.request
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=3) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        return f"responde · {len(d.get('models') or [])} modelos"
    except Exception as e:                                       # noqa: BLE001
        return f"no responde ({type(e).__name__})"


def secciones(ia=None, hijo=True):
    """Todo lo del equipo. `ia` = (proveedor, url, modelo) de la configuración (sin la clave)."""
    S = []
    w = _ps()
    err_ps = w.get("_error")

    # ── sistema operativo
    so = (_lista(w.get("so")) or [{}])[0]
    cv = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    filas = [("Windows", _reg(cv, "ProductName") or so.get("Caption") or platform.platform()),
             ("Versión", f"{_reg(cv, 'DisplayVersion') or '?'} · compilación {_reg(cv, 'CurrentBuild') or so.get('BuildNumber') or '?'}"
                         f".{_reg(cv, 'UBR') or '?'}"),
             ("Edición", _reg(cv, "EditionID") or "?"),
             ("Arquitectura", f"{so.get('OSArchitecture') or platform.machine()} · Python {platform.architecture()[0]}"),
             ("platform", platform.platform()),
             ("Idioma / región", f"{so.get('MUILanguages') or '?'} · locale {so.get('Locale') or '?'}"),
             ("Encendido desde", _fecha(so.get("LastBootUpTime"))),
             ("Nombre del equipo", platform.node() or "?"),
             ("Escritorio remoto", "sí" if _metrica(0x1000) else "no"),
             ("Monitores (GetSystemMetrics)", str(_metrica(80) or "?"))]
    if err_ps:
        filas.append(("Consulta WMI", f"falló: {err_ps}"))
    S.append(("Sistema operativo", filas))

    # ── equipo
    eq = (_lista(w.get("equipo")) or [{}])[0]
    bios = (_lista(w.get("bios")) or [{}])[0]
    placa = (_lista(w.get("placa")) or [{}])[0]
    tipo_pc = {1: "escritorio", 2: "portátil", 3: "estación de trabajo", 4: "servidor"}.get(eq.get("PCSystemType"), "?")
    S.append(("Equipo", [
        ("Fabricante / modelo", f"{eq.get('Manufacturer') or '?'} · {eq.get('Model') or '?'}"),
        ("Tipo", tipo_pc),
        ("Máquina virtual", "probable" if any(x in f"{eq.get('Manufacturer')} {eq.get('Model')}".lower()
                                             for x in ("virtual", "vmware", "qemu", "kvm", "xen", "parallels")) else "no"),
        ("Hipervisor activo (Hyper-V / VBS / WSL)", "sí" if eq.get("HypervisorPresent") else "no"),
        ("Placa base", f"{placa.get('Manufacturer') or '?'} · {placa.get('Product') or '?'}"),
        ("BIOS", f"{bios.get('Manufacturer') or '?'} · {bios.get('SMBIOSBIOSVersion') or '?'} · {_fecha(bios.get('ReleaseDate'))[:10]}"),
        ("Batería", "; ".join(f"{b.get('Name')} {b.get('EstimatedChargeRemaining')} %" for b in _lista(w.get("energia")))
         or "no tiene"),
        ("Plan de energía", (w.get("plan") or "?").strip()),
    ]))

    # ── procesador
    filas = []
    for c in _lista(w.get("cpu")) or [{}]:
        filas += [("Procesador", c.get("Name") or _reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                                                       "ProcessorNameString") or platform.processor()),
                  ("Núcleos / hilos", f"{c.get('NumberOfCores') or '?'} / {c.get('NumberOfLogicalProcessors') or os.cpu_count()}"),
                  ("Frecuencia máx.", f"{c.get('MaxClockSpeed') or '?'} MHz"),
                  ("Caché L2 / L3", f"{c.get('L2CacheSize') or '?'} KB / {c.get('L3CacheSize') or '?'} KB"),
                  ("Virtualización en firmware", str(c.get("VirtualizationFirmwareEnabled")))]
    filas.append(("os.cpu_count()", str(os.cpu_count())))
    S.append(("Procesador", filas))

    # ── memoria
    filas = []
    try:
        m = _memoria()
        filas += [("RAM total", _gb(m.ullTotalPhys)), ("RAM libre ahora", f"{_gb(m.ullAvailPhys)} ({100 - m.dwMemoryLoad} %)"),
                  ("Memoria virtual (con paginación)", f"{_gb(m.ullTotalPageFile)} · libre {_gb(m.ullAvailPageFile)}")]
    except Exception as e:                                       # noqa: BLE001
        filas.append(("RAM", f"? ({type(e).__name__})"))
    tipos = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5", 35: "LPDDR5"}
    for k, r in enumerate(_lista(w.get("ram")), 1):
        filas.append((f"Módulo {k}", f"{_gb(r.get('Capacity'))} · {tipos.get(r.get('SMBIOSMemoryType'), r.get('SMBIOSMemoryType'))} · "
                                     f"{r.get('ConfiguredClockSpeed') or r.get('Speed') or '?'} MT/s · "
                                     f"{(r.get('Manufacturer') or '').strip()} {(r.get('PartNumber') or '').strip()}"))
    S.append(("Memoria", filas))

    # ── tarjetas de video (Windows: driver, fecha, memoria)
    filas = []
    vram = {v.get("DriverDesc"): v for v in _lista(w.get("vram"))}
    for k, g in enumerate(_lista(w.get("gpu")), 1):
        v = vram.get(g.get("Name")) or {}
        mem = v.get("MemoriaBytes")
        mem = _gb(mem) if isinstance(mem, (int, float)) and mem else (_gb(g.get("AdapterRAM")) + " (≤4 GB visibles por WMI)")
        filas += [(f"GPU {k}", g.get("Name") or "?"),
                  (f"GPU {k} fabricante", g.get("AdapterCompatibility") or "?"),
                  (f"GPU {k} driver", f"{g.get('DriverVersion') or '?'} · fecha {_fecha(g.get('DriverDate'))[:10] if g.get('DriverDate') else v.get('DriverDate') or '?'}"),
                  (f"GPU {k} memoria dedicada", mem),
                  (f"GPU {k} resolución", f"{g.get('CurrentHorizontalResolution') or '?'}×{g.get('CurrentVerticalResolution') or '?'}"
                                          f" @ {g.get('CurrentRefreshRate') or '?'} Hz"),
                  (f"GPU {k} estado", g.get("Status") or "?"),
                  (f"GPU {k} dispositivo", g.get("PNPDeviceID") or "?")]
    S.append(("Tarjetas de video (Windows)", filas or [("GPU", "no se pudo leer")]))

    # ── discos
    filas = []
    for d in _lista(w.get("discos")):
        if d.get("DriveType") in (2, 3, 4):
            filas.append((d.get("DeviceID") or "?", f"{d.get('VolumeName') or ''} {d.get('FileSystem') or ''} · "
                                                    f"{_gb(d.get('FreeSpace'))} libres de {_gb(d.get('Size'))}".strip()))
    for d in _lista(w.get("fisicos")):
        filas.append(("Disco físico", f"{d.get('Model') or '?'} · {_gb(d.get('Size'))} · {d.get('InterfaceType') or ''}"))
    for nombre, carpeta in (("Temporal", tempfile.gettempdir()),
                            ("Datos locales", os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))):
        try:
            u = shutil.disk_usage(carpeta)
            filas.append((f"Libre en {nombre}", f"{_gb(u.free)} ({carpeta})"))
        except Exception:                                        # noqa: BLE001
            pass
    S.append(("Discos", filas))

    # ── antivirus
    av = [f"{a.get('displayName')} (estado {a.get('productState')})" for a in _lista(w.get("antivirus"))]
    S.append(("Antivirus", [("Productos", "; ".join(av) or "no informado")]))

    # ── Civil 3D
    S.append(("AutoCAD / Civil 3D", _autodesk()))

    # ── carpetas y procesos de la app
    loc = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    app_ = os.environ.get("APPDATA") or os.path.expanduser("~")
    filas = [(f"Escribir en {c}", _escribible(c)) for c in (
        os.path.join(loc, "pdf-to-cad", "diagnosticos"), os.path.join(loc, "pdf-to-cad", "recuperacion"),
        os.path.join(app_, "pdf-to-cad"), tempfile.gettempdir())]
    if hijo:
        filas.append(("Proceso de trabajo (spawn)", _proceso_hijo()))
    S.append(("Carpetas y procesos de la app", filas))

    # ── IA
    if ia:
        prov, url, modelo = ia
        filas = [("Proveedor", prov or "sin configurar"), ("Modelo", modelo or "?")]
        if (prov or "").lower().startswith("ollama") and url:
            filas.append((f"Ollama en {url}", _ollama(url)))
        S.append(("Asistente IA", filas))

    # ── variables de entorno que cambian el comportamiento
    env = [(k, v) for k, v in sorted(os.environ.items())
           if k.startswith(("QT_", "PDFCAD_", "OPENBLAS", "OMP_", "MKL_", "PYTHON"))]
    S.append(("Variables de entorno", env or [("(ninguna relevante)", "")]))
    return S
