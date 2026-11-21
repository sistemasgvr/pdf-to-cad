"""vigilante.py — registro de TIEMPOS y CONGELAMIENTOS de toda la aplicación (pedido del usuario 2026-11-20).

«Que la app nunca quede en No responde» se logra encontrando cada trozo que traba la ventana y arreglándolo; y
«mejorar el reconocimiento» midiendo dónde se va el tiempo. Este módulo (sin Qt) anota, en una carpeta por SESIÓN
(`carpeta()`, un archivo `proc-<pid>.jsonl` por proceso: la ventana, cada trabajador, las teselas, los grupos de
procesos), una línea JSON por suceso:

  · «inicio»        el proceso empieza (nombre, versión, núcleos, RAM);
  · «etapa»         cada etapa que el código ya avisa con `nucleo.avance.avisar` (aunque nadie la muestre), con lo
                    que duró, su «i de n» y dentro de qué bloque iba (p. ej. «Reconocer utilidad · AGUA»);
  · «bloque»        `with medir(nombre, **datos):` — un paso con nombre (reconocer una utilidad, importar, redibujar…);
  · «trabajo»       `with trabajo(objetivo):` — un trabajo entero de un proceso, con su PERFIL por muestreo: cada
                    `MUESTREO_S` se mira la pila del hilo y se suma el tiempo a cada función (propio = la función de
                    arriba; total = la función en cualquier parte de la pila). Así sale TODO el código que corre,
                    sin tener que marcarlo a mano; una llamada larga en C (PyMuPDF) se le cuenta a quien la llamó;
  · «congelamiento» (lo escribe `Guardia`) la ventana no atendió sus eventos durante más de `UMBRAL_CONGELA_S`:
                    cuánto, en qué funciones (perfil de la pila del hilo de la ventana durante la pausa) y qué se
                    estaba haciendo (carga a la vista, etapa, bloques abiertos);
  · «sistema»       (lo escribe `Guardia` cada `SISTEMA_S`) memoria y CPU de la ventana y de TODOS sus procesos hijos;
  · «acumulado»     sumas de cosas muy repetidas (teselas), cada `ACUMULAR_S`.

La ventana crea la sesión (`activar("ventana")`) y la deja en la variable de entorno `ENV_CARPETA`: los procesos
hijos («spawn» heredan el entorno) escriben en la MISMA carpeta. Sin sesión (pruebas, scripts) un hijo no anota
nada. `PDFCAD_VIGILANTE=0` lo apaga. Lo lee `nucleo/vigilante_informe.py` (y `scripts/rendimiento/vigilante.py`).

Nunca tumba nada: todo error del propio registro se descarta.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
from typing import Dict, List, Optional

ENV_CARPETA = "PDFCAD_VIGILANTE_DIR"
ENV_APAGADO = "PDFCAD_VIGILANTE"
MAX_SESIONES = 30            # carpetas de sesión que se conservan (las más viejas se borran al abrir la app)
MUESTREO_S = 0.02            # perfil por muestreo: cada cuánto se mira la pila (≈2 % de costo; 0.01 ≈ 4 %)
PERFIL_TOP = 40              # funciones que se guardan por perfil
PERFIL_RUTAS = 25            # pilas completas más pesadas que se guardan
PROFUNDIDAD = 80             # marcos de la pila que se miran (de abajo hacia arriba)
UMBRAL_CONGELA_S = 0.2       # la ventana sin atender eventos más que esto = congelamiento
NO_RESPONDE_S = 5.0          # Windows marca «No responde» a los ~5 s
LATIDO_MS = 50               # la ventana late cada tanto (`vigilante_ui`)
MIRAR_S = 0.01               # la guardia mira el latido cada tanto
SISTEMA_S = 2.0              # memoria y CPU de los procesos
ACUMULAR_S = 5.0
SUSPENSION_S = 300.0         # una «pausa» mayor = el equipo se suspendió (no es la app)

_lock = threading.Lock()
_archivo = None
_carpeta: Optional[str] = None
_nombre = ""
_estado: Dict[int, dict] = {}            # por hilo: {"etapa": [...], "bloques": [...]}
_acum: Dict[str, list] = {}
_ui = {"carga": ""}                      # lo que la capa «Cargando…» de la ventana muestra ahora
_vaciado = [0.0]
_cola: "queue.Queue[dict]" = queue.Queue()
_hilo_escritor: Optional[threading.Thread] = None
VACIAR_S = 1.0
_AL_MOMENTO = frozenset({"inicio", "trabajo", "trabajo_inicio", "congelamiento", "encargo", "fin", "carga"})
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # raíz del repo


def apagado() -> bool:
    return os.environ.get(ENV_APAGADO, "1") == "0"


def base() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "pdf-to-cad", "rendimiento")


def activo() -> bool:
    return _archivo is not None


def carpeta() -> Optional[str]:
    return _carpeta


def nombre_proceso() -> str:
    return _nombre


# ── escribir ──────────────────────────────────────────────────────────────────────────────────────────────
def activar(nombre: str, nueva_sesion: bool = False, carpeta_sesion: Optional[str] = None) -> bool:
    """Empieza a anotar en este proceso. `nueva_sesion` (solo la ventana): crea la carpeta de la sesión y la deja
    en el entorno para los hijos; si no, usa la de `ENV_CARPETA` (sin ella, no anota: pruebas y scripts)."""
    global _archivo, _carpeta, _nombre
    if _archivo is not None or apagado():
        return _archivo is not None
    try:
        if carpeta_sesion:
            dirn = carpeta_sesion
        elif nueva_sesion:
            _limpiar_viejas()
            sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            dirn = os.path.join(base(), f"{sello}-{os.getpid()}")
        else:
            dirn = os.environ.get(ENV_CARPETA) or ""
            if not dirn:
                return False
        os.makedirs(dirn, exist_ok=True)
        if nueva_sesion or carpeta_sesion:
            os.environ[ENV_CARPETA] = dirn
        _archivo = open(os.path.join(dirn, f"proc-{os.getpid()}.jsonl"), "a", encoding="utf-8")
        import atexit
        atexit.register(_vaciar)
        _carpeta, _nombre = dirn, str(nombre)
    except OSError:
        _archivo = None
        return False
    evento("inicio", nombre=_nombre, version=_version(), python=sys.version.split()[0],
           ppid=os.getppid(), nucleos=os.cpu_count(), argv=list(sys.argv[:3]),
           fecha=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
    return True


def desactivar() -> None:
    """Cierra el registro de este proceso (pruebas)."""
    global _archivo, _carpeta, _nombre
    _vaciar()
    with _lock:
        f, _archivo = _archivo, None
    _carpeta, _nombre = None, ""
    _estado.clear()
    _acum.clear()
    if f is not None:
        try:
            f.close()
        except OSError:
            pass


def evento(tipo: str, **datos) -> None:
    f = _archivo
    if f is None:
        return
    d = {"t": round(time.time(), 4), "tipo": tipo, "pid": os.getpid(), "proc": _nombre,
         "hilo": threading.current_thread().name}
    d.update(datos)
    _arrancar_escritor()
    _cola.put(d)                 # lo escribe `_escritor`: quien anota (la ventana) nunca espera al disco ni al lock


def _escribir(d: dict) -> None:
    try:
        linea = json.dumps(d, ensure_ascii=False, default=str)
        with _lock:
            if _archivo is not None:
                _archivo.write(linea + "\n")
                ahora = time.perf_counter()
                # a disco cada `VACIAR_S` (escribir cada línea costaba ~7 ms con el antivirus) y siempre lo importante
                if d.get("tipo") in _AL_MOMENTO or ahora - _vaciado[0] >= VACIAR_S:
                    _vaciado[0] = ahora
                    _archivo.flush()
    except (OSError, ValueError, TypeError):
        pass


def _escritor() -> None:
    while True:
        try:
            d = _cola.get(timeout=VACIAR_S)
        except queue.Empty:
            _a_disco()
            continue
        try:
            _escribir(d)
        finally:
            _cola.task_done()


def _arrancar_escritor() -> None:
    global _hilo_escritor
    if _hilo_escritor is None or not _hilo_escritor.is_alive():
        with _lock:
            if _hilo_escritor is None or not _hilo_escritor.is_alive():
                _hilo_escritor = threading.Thread(target=_escritor, name="vigilante-escritor", daemon=True)
                _hilo_escritor.start()


def _a_disco() -> None:
    try:
        with _lock:
            if _archivo is not None:
                _archivo.flush()
    except (OSError, ValueError):
        pass


def _vaciar() -> None:
    """Escribe lo que espera en la cola y lo manda a disco (al salir, en las pruebas, antes de cerrar)."""
    if _hilo_escritor is not None and _hilo_escritor.is_alive():
        _cola.join()
    _a_disco()


def _version() -> str:
    try:
        from nucleo import model
        return str(getattr(model, "VERSION", "?"))
    except Exception:
        return "?"


def _limpiar_viejas() -> None:
    try:
        b = base()
        if not os.path.isdir(b):
            return
        dirs = sorted(d for d in os.listdir(b) if os.path.isdir(os.path.join(b, d)))
        for d in dirs[:max(0, len(dirs) - (MAX_SESIONES - 1))]:
            shutil.rmtree(os.path.join(b, d), ignore_errors=True)
    except OSError:
        pass


# ── etapas y bloques (por hilo) ───────────────────────────────────────────────────────────────────────────
def _st(ident: Optional[int] = None) -> dict:
    ident = threading.get_ident() if ident is None else ident
    s = _estado.get(ident)
    if s is None:
        s = _estado[ident] = {"etapa": None, "bloques": []}
    return s


def _contexto(s: dict) -> str:
    return " › ".join(b[0] for b in s["bloques"])


def al_avisar(texto: str, i=None, n=None) -> None:
    """Lo llama `nucleo.avance.avisar` (aunque nadie escuche): una etapa nueva cierra la anterior."""
    if _archivo is None:
        return
    s = _st()
    e = s["etapa"]
    ahora = time.perf_counter()
    if e is not None and e[0] == texto:
        e[2], e[3] = i, n
        return
    _cerrar_etapa(s, ahora)
    s["etapa"] = [texto, ahora, i, n, _contexto(s)]
    evento("etapa_inicio", texto=texto, dentro=s["etapa"][4])      # el monitor muestra qué hace AHORA


def _cerrar_etapa(s: dict, ahora: float) -> None:
    e, s["etapa"] = s["etapa"], None
    if e is not None:
        evento("etapa", texto=e[0], dur=round(ahora - e[1], 4), i=e[2], n=e[3], dentro=e[4])


def cerrar_etapa() -> None:
    if _archivo is not None:
        _cerrar_etapa(_st(), time.perf_counter())


@contextlib.contextmanager
def medir(nombre: str, **datos):
    """Un paso con nombre: anota «bloque» con lo que duró. Las etapas que se avisan dentro llevan su nombre."""
    if _archivo is None:
        yield
        return
    s = _st()
    t0 = time.perf_counter()
    extra = datos.get("utilidad") or datos.get("parte")
    s["bloques"].append((nombre + (f" · {extra}" if extra else ""), t0))
    error = ""
    try:
        yield
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        ahora = time.perf_counter()
        if s["etapa"] is not None and s["etapa"][1] >= t0:
            _cerrar_etapa(s, ahora)
        dentro = _contexto({"bloques": s["bloques"][:-1]})
        if s["bloques"]:
            s["bloques"].pop()
        evento("bloque", nombre=nombre, dur=round(ahora - t0, 4), dentro=dentro, error=error,
               **{k: v for k, v in datos.items() if v is not None})


def instrumentar(objeto, nombres, prefijo: str = "") -> List[str]:
    """Envuelve los métodos `nombres` de una CLASE (o módulo) con `medir`: sirve para medir pasos de la ventana sin
    tocar su código. Devuelve los que envolvió (los que no existen se saltan)."""
    import functools
    hechos = []
    for n in nombres:
        f = getattr(objeto, n, None)
        if f is None or not callable(f) or getattr(f, "_vigilado", False):
            continue

        def envolver(fn, etiqueta):
            @functools.wraps(fn)
            def w(*a, **k):
                if _archivo is None:
                    return fn(*a, **k)
                with medir(etiqueta):
                    return fn(*a, **k)
            w._vigilado = True
            return w
        try:
            setattr(objeto, n, envolver(f, prefijo + n))
            hechos.append(n)
        except (AttributeError, TypeError):
            pass
    return hechos


def acumular(nombre: str, dur: float) -> None:
    """Sucesos muy repetidos (una tesela): se suman y se anotan cada `ACUMULAR_S`."""
    if _archivo is None:
        return
    a = _acum.get(nombre)
    ahora = time.perf_counter()
    if a is None:
        a = _acum[nombre] = [ahora, 0, 0.0, 0.0]
    a[1] += 1
    a[2] += dur
    a[3] = max(a[3], dur)
    if ahora - a[0] >= ACUMULAR_S:
        evento("acumulado", nombre=nombre, cuantos=a[1], dur=round(a[2], 4), max=round(a[3], 4),
               ventana_s=round(ahora - a[0], 2))
        _acum[nombre] = [ahora, 0, 0.0, 0.0]


def poner_carga(texto: str, inicio: bool = False, fin_dur: Optional[float] = None) -> None:
    """La capa «Cargando…» de la ventana (`ui/comun/busy`): el texto a la vista; al terminar, «carga» con lo que
    duró (lo que el usuario esperó viendo la tarjeta)."""
    if _archivo is None:
        return
    if fin_dur is not None:
        evento("carga", texto=_ui["carga"], dur=round(fin_dur, 4))
        _ui["carga"] = ""
        return
    _ui["carga"] = texto or ""


def contexto_de(ident: int) -> dict:
    """Qué hace el hilo `ident` (para un congelamiento): etapa y bloques abiertos."""
    s = _estado.get(ident) or {}
    e = s.get("etapa")
    return {"etapa": e[0] if e else "", "bloques": [b[0] for b in s.get("bloques") or []]}


# ── perfil por muestreo ───────────────────────────────────────────────────────────────────────────────────
def _nombre_marco(code) -> str:
    fn = code.co_filename
    try:
        rel = os.path.relpath(fn, _RAIZ)
    except ValueError:
        rel = fn
    if rel.startswith(".."):
        partes = fn.replace("\\", "/").split("/")
        if "site-packages" in partes:
            rel = "/".join(partes[partes.index("site-packages") + 1:])
        else:
            rel = partes[-1]
    rel = rel.replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.startswith("app/"):
        rel = rel[4:]
    qual = getattr(code, "co_qualname", code.co_name)
    return f"{rel.replace('/', '.')}:{qual}"


class Perfil:
    """Suma, por función, el tiempo que el hilo `ident` pasó en ella. `muestra(dt)` mira la pila UNA vez y le
    cuenta `dt` segundos (lo hace la guardia de la ventana); `iniciar()` lanza un hilo que muestrea solo."""

    def __init__(self, ident: int):
        self.ident = ident
        self.propio: Dict[str, float] = {}
        self.total: Dict[str, float] = {}
        self.rutas: Dict[str, float] = {}
        self.muestras = 0
        self._parar = threading.Event()
        self._hilo = None
        self._nombres: dict = {}

    def muestra(self, dt: float) -> None:
        f = sys._current_frames().get(self.ident)
        if f is None:
            return
        pila = []
        while f is not None and len(pila) < PROFUNDIDAD:
            c = f.f_code
            n = self._nombres.get(c)
            if n is None:
                n = self._nombres[c] = _nombre_marco(c)
            pila.append(n)
            f = f.f_back
        self.sumar_pila(pila, dt)

    def sumar_pila(self, pila: List[str], dt: float) -> None:
        """Cuenta `dt` segundos a una pila (de arriba hacia abajo)."""
        if not pila:
            return
        self.muestras += 1
        self.propio[pila[0]] = self.propio.get(pila[0], 0.0) + dt
        for n in set(pila):
            self.total[n] = self.total.get(n, 0.0) + dt
        ruta = " ← ".join(pila[:12])
        self.rutas[ruta] = self.rutas.get(ruta, 0.0) + dt

    def iniciar(self) -> "Perfil":
        def lazo():
            antes = time.perf_counter()
            while not self._parar.wait(MUESTREO_S):
                ahora = time.perf_counter()
                try:
                    self.muestra(ahora - antes)
                except Exception:
                    pass
                antes = ahora
        self._hilo = threading.Thread(target=lazo, name="vigilante-perfil", daemon=True)
        self._hilo.start()
        return self

    def parar(self) -> dict:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(1.0)
        return self.resumen()

    def resumen(self) -> dict:
        def top(d, k):
            return [[n, round(v, 4)] for n, v in sorted(d.items(), key=lambda kv: -kv[1])[:k]]
        propio = top(self.propio, PERFIL_TOP)
        total = top(self.total, PERFIL_TOP)
        ya = {n for n, _v in total}
        total += [[n, round(self.total.get(n, 0.0), 4)] for n, _v in propio if n not in ya]   # cada «propio» con su total
        return {"muestras": self.muestras, "propio": propio, "total": total, "rutas": top(self.rutas, PERFIL_RUTAS)}


@contextlib.contextmanager
def trabajo(objetivo: str, **datos):
    """Un trabajo entero (en un proceso trabajador o un hilo): «trabajo» con lo que duró, memoria y su perfil."""
    if _archivo is None:
        yield
        return
    from nucleo import vigilante_sistema as VS
    perfil = Perfil(threading.get_ident()).iniciar()
    mem0 = VS.memoria_propia_mb()
    t0 = time.perf_counter()
    error = ""
    evento("trabajo_inicio", objetivo=objetivo, **datos)
    try:
        with medir("Trabajo " + objetivo):
            yield
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        dur = time.perf_counter() - t0
        evento("trabajo", objetivo=objetivo, dur=round(dur, 4), error=error, mem_antes_mb=mem0,
               mem_despues_mb=VS.memoria_propia_mb(), mem_pico_mb=VS.memoria_pico_mb(),
               perfil=perfil.parar(), **datos)


# ── guardia de la ventana ─────────────────────────────────────────────────────────────────────────────────
_LINEA_HILO = re.compile(r"^(?:Current thread|Thread) (0x[0-9a-fA-F]+)")
_LINEA_MARCO = re.compile(r'^\s+File "(.+)", line \d+ in (.+?)\s*$')


def leer_volcados(texto: str, ident: int) -> List[List[str]]:
    """Pilas del hilo `ident` en los volcados de `faulthandler.dump_traceback_later` (una por volcado, de arriba
    hacia abajo, con los nombres de `_nombre_marco`)."""
    pilas, actual, mio = [], None, False
    for linea in texto.splitlines():
        if linea.startswith("Timeout ("):
            actual, mio = None, False
            continue
        m = _LINEA_HILO.match(linea)
        if m:
            mio = int(m.group(1), 16) == ident
            actual = [] if mio else None
            if mio:
                pilas.append(actual)
            continue
        m = _LINEA_MARCO.match(linea)
        if m and mio and actual is not None:
            actual.append(_nombre_ruta(m.group(1), m.group(2)))
    return [p for p in pilas if p]


class _Codigo:
    def __init__(self, ruta, func):
        self.co_filename, self.co_name, self.co_qualname = ruta, func, func


def _nombre_ruta(ruta: str, func: str) -> str:
    return _nombre_marco(_Codigo(ruta, func))


class Latido:
    """Hora del último latido de la ventana en un archivo de 8 bytes mapeado en memoria (`latido-<pid>.bin`): el
    MONITOR (otro proceso) lo lee y sabe si la ventana responde AHORA, aunque esté trabada y no pueda escribir nada.
    `leer(ruta)` → la hora (time.time) del último latido, o None."""

    def __init__(self, ruta: str):
        import mmap
        self._f = open(ruta, "w+b")
        self._f.write(bytes(8))
        self._f.flush()
        self._m = mmap.mmap(self._f.fileno(), 8)

    def escribir(self, t: float) -> None:
        import struct
        struct.pack_into("<d", self._m, 0, t)

    def cerrar(self) -> None:
        try:
            self._m.close()
            self._f.close()
        except (OSError, ValueError):
            pass

    @staticmethod
    def leer(ruta: str) -> Optional[float]:
        import struct
        try:
            with open(ruta, "rb") as f:
                b = f.read(8)
            t = struct.unpack("<d", b)[0] if len(b) == 8 else 0.0
            return t or None
        except OSError:
            return None


class Guardia:
    """Vigila el LATIDO de la ventana (`latido()`, desde un QTimer del hilo de la interfaz, cada `LATIDO_MS`).

    La pausa la mide el propio latido: si entre dos latidos pasó más de `UMBRAL_CONGELA_S`, hubo un congelamiento
    de esa duración (exacto aunque ningún otro hilo haya podido correr). Para saber DÓNDE estaba, dos fuentes:
      · este hilo muestrea la pila de la ventana cada `MIRAR_S` mientras no late (si consigue correr);
      · `faulthandler.dump_traceback_later` (rearmado al latir) vuelca la pila de todos los hilos cada `VOLCADO_S`
        sin latir; funciona aunque la ventana tenga tomado el intérprete (una llamada larga en C, p. ej. PyMuPDF
        dibujando), justo cuando el muestreo no puede correr.
    También anota memoria y CPU de la ventana y sus procesos cada `SISTEMA_S`; con el congelamiento va lo que la
    capa «Cargando…» mostraba (`poner_carga`) y la etapa y bloques abiertos de la ventana."""

    VOLCADO_S = 0.3
    # `faulthandler.dump_traceback_later` lee las pilas de TODOS los hilos desde un hilo nativo, SIN el GIL, cada
    # `VOLCADO_S` mientras la ventana no late: si el hilo de la ventana cambia sus marcos en ese instante (un `import`,
    # una llamada que vuelve), lee memoria ya liberada → «access violation» en `python314.dll` y la app se cerraba
    # sola justo en las pausas largas (2026-11-21: 3 volcados idénticos, `<invalid frame>` en `feature_import`).
    # Apagado por defecto; `PDFCAD_VIGILANTE_VOLCADOS=1` lo enciende solo para depurar una pausa dentro de C.
    USAR_VOLCADOS = os.environ.get("PDFCAD_VIGILANTE_VOLCADOS") == "1"

    def __init__(self, ident_ventana: int, volcados: Optional[str] = None):
        self.ident = ident_ventana
        self._ultimo = time.perf_counter()
        self._armado = 0.0
        self._huecos: List[tuple] = []
        self._parar = threading.Event()
        self._hilo = None
        self._volcados = None
        self._leido = 0
        self._vistos: Dict[float, tuple] = {}
        self.congelamientos = 0
        self.peor_s = 0.0
        self.error = ""
        self._latido = None
        if _carpeta:
            try:
                self._latido = Latido(os.path.join(_carpeta, f"latido-{os.getpid()}.bin"))
            except (OSError, ValueError):
                self._latido = None
        if volcados is None and _carpeta:
            volcados = os.path.join(_carpeta, f"volcados-{os.getpid()}.txt")
        if volcados:
            try:
                self._volcados = open(volcados, "w+", encoding="utf-8")
            except OSError:
                self._volcados = None

    def latido(self) -> None:
        ahora = time.perf_counter()
        if ahora - self._ultimo > UMBRAL_CONGELA_S + LATIDO_MS / 1000.0:
            self._huecos.append((self._ultimo, ahora))
        self._ultimo = ahora
        if self._latido is not None:
            self._latido.escribir(time.time())
        if self.USAR_VOLCADOS and self._volcados is not None and ahora - self._armado > LATIDO_MS / 1000.0 * 1.5:
            self._armado = ahora
            try:
                import faulthandler
                faulthandler.dump_traceback_later(self.VOLCADO_S, repeat=True, file=self._volcados)
            except (RuntimeError, ValueError, OSError):
                self._volcados = None

    def iniciar(self) -> "Guardia":
        self._hilo = threading.Thread(target=self._lazo, name="vigilante-guardia", daemon=True)
        self._hilo.start()
        return self

    def parar(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(2.0)
        if self._volcados is not None:
            try:
                import faulthandler
                faulthandler.cancel_dump_traceback_later()
            except Exception:
                pass
        if self._latido is not None:
            self._latido.escribir(-1.0)       # la ventana se cerró (no es que esté trabada)
        try:
            self._revisar()                   # lo que quedó pendiente
        except Exception as exc:
            self.error = repr(exc)

    def _lazo(self):
        from nucleo import vigilante_sistema as VS
        medidor = VS.Medidor()
        prox_sis = 0.0
        vivo = None                   # (inicio, perfil, contexto, carga) del congelamiento que se está viendo
        antes = time.perf_counter()
        while not self._parar.wait(MIRAR_S):
            ahora = time.perf_counter()
            try:
                ultimo = self._ultimo
                if vivo is None and ahora - ultimo > UMBRAL_CONGELA_S:
                    vivo = (ultimo, Perfil(self.ident), contexto_de(self.ident), _ui["carga"])
                    vivo[1].muestra(ahora - ultimo)
                elif vivo is not None:
                    if ultimo > vivo[0]:
                        self._vistos[vivo[0]] = vivo
                        vivo = None
                    else:
                        vivo[1].muestra(ahora - antes)
                if self._huecos:
                    self._revisar()
                if ahora >= prox_sis:
                    prox_sis = ahora + SISTEMA_S
                    evento("sistema", congelada=vivo is not None, **medidor.medir())
            except Exception as exc:          # el vigilante nunca tumba nada; queda el último error para revisarlo
                self.error = repr(exc)
            antes = ahora

    def _nuevos_volcados(self) -> List[List[str]]:
        f = self._volcados
        if f is None:
            return []
        try:
            f.flush()
            f.seek(self._leido)
            texto = f.read()
            self._leido = f.tell()
        except (OSError, ValueError):
            return []
        return leer_volcados(texto, self.ident)

    def _revisar(self) -> None:
        huecos, self._huecos = self._huecos, []
        if not huecos:
            return
        pilas = self._nuevos_volcados()
        largo = max(huecos, key=lambda h: h[1] - h[0])
        for ini, fin in huecos:
            visto = self._vistos.pop(ini, None)
            dur = fin - ini - LATIDO_MS / 1000.0      # el latido normal ya trae esa espera
            if dur < UMBRAL_CONGELA_S:
                continue
            if visto is not None:
                perfil, ctx, carga, fuente = visto[1], visto[2], visto[3], "muestreo"
            else:
                perfil, ctx, carga, fuente = Perfil(self.ident), contexto_de(self.ident), _ui["carga"], "volcados"
            mias = pilas if (ini, fin) == largo else []
            if mias and perfil.muestras < 3:       # el muestreo casi no pudo correr: lo dicen los volcados
                perfil = Perfil(self.ident)
                for p in mias:
                    perfil.sumar_pila(p, dur / len(mias))
                fuente = "volcados"
            self.congelamientos += 1
            self.peor_s = max(self.peor_s, dur)
            evento("congelamiento", dur=round(dur, 4), no_responde=dur >= NO_RESPONDE_S,
                   suspension=dur >= SUSPENSION_S, carga=carga, etapa=ctx.get("etapa", ""),
                   bloques=ctx.get("bloques", []), fuente=fuente, perfil=perfil.resumen())
        for k in [k for k in self._vistos if k < largo[0]]:
            self._vistos.pop(k, None)
