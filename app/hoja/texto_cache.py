"""texto_cache.py — Caché EN DISCO de lo que `texto_pdf` lee de una hoja (PURO: sin Qt).

Pedido 2026-11-21 (sesión del usuario: Water South + Sewer + SD de Phoenix): «Leyendo las letras del mapa (por la forma
de cada letra)…» se repetía en MUCHOS procesos con los mismos PDF — la composición sugerida (fondo), la georreferencia
automática (georef: 35 s), el área sugerida (area), la interpretación de la hoja compuesta (reconocer: ~10 s por
compuesta), el índice de texto (fondo: 13 s) y hasta la ventana al abrir «Componer hoja». Cada proceso leía cada glifo
y volvía a decodificar las fuentes Type3 (dibujar cada glifo y compararlo con Arial).

Aquí se guarda, entre procesos y entre aperturas de la app:

  · la TABLA de cada fuente Type3 (`texto_pdf._decodificar`) por la huella de su CONTENIDO (glifos + FontMatrix): una
    hoja compuesta copia las fuentes de sus hojas de origen, así que cada fuente se decodifica una vez;
  · los GLIFOS de cada hoja (`texto_pdf.glifos`) por la huella de la hoja: bytes del PDF (archivo o `stream`), número
    de hoja, contenido de la hoja, nº de objetos y capas encendidas.

Lo guardado depende SOLO de eso y del código que lo calcula (`version_codigo`: `texto_pdf.py`, este archivo, PyMuPDF,
numpy y las fuentes Arial del sistema con que se comparan los glifos); con todo igual, es lo MISMO que saldría de
calcularlo otra vez (mismos valores y mismos tipos: las cajas de tinta son `np.float64`, como al calcularlas).

Carpeta: %LOCALAPPDATA%/pdf-to-cad/texto_pdf (`PDFCAD_CACHE_TEXTO` la cambia; vacía = sin caché; las pruebas la
apagan). Un archivo roto o ilegible = como si no estuviera. Se guardan los más recientes hasta `MAX_MB`.
"""
from __future__ import annotations

import glob
import hashlib
import os
import pickle
import sys
import tempfile
from typing import Dict, List, Optional

import numpy as np

MAX_MB = 768
FORMATO = 1
_AQUI = os.path.dirname(os.path.abspath(__file__))
_VERSION: Optional[str] = None
_HUELLAS_ARCHIVO: Dict[tuple, str] = {}      # (ruta, tamaño, mtime) → sha1 del archivo (en este proceso)


def carpeta() -> Optional[str]:
    d = os.environ.get("PDFCAD_CACHE_TEXTO")
    if d is None:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        d = os.path.join(base, "pdf-to-cad", "texto_pdf")
    if not d:
        return None
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


def version_codigo() -> str:
    """Huella del código que lee el texto: en el .exe, la versión y el propio ejecutable; desde el código fuente,
    `texto_pdf.py` y este archivo. Además PyMuPDF (dibuja los glifos), numpy y las Arial de referencia."""
    global _VERSION
    if _VERSION is None:
        import fitz
        from nucleo.model import VERSION
        h = hashlib.sha1(f"{VERSION}|{FORMATO}|{fitz.VersionBind}|{np.__version__}".encode("utf-8"))
        if getattr(sys, "frozen", False):
            st = os.stat(sys.executable)
            h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        else:
            for ruta in (os.path.join(_AQUI, "texto_pdf.py"), os.path.abspath(__file__)):
                with open(ruta, "rb") as f:
                    h.update(os.path.basename(ruta).encode("utf-8"))
                    h.update(f.read())
        from hoja import texto_pdf
        fdir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for _k, archivo, _b in texto_pdf._ARIAL:
            ruta = os.path.join(fdir, archivo)
            try:
                st = os.stat(ruta)
                h.update(f"{archivo}:{st.st_size}:{st.st_mtime_ns}".encode())
            except OSError:
                h.update(f"{archivo}:-".encode())
        _VERSION = h.hexdigest()
    return _VERSION


def _ruta(tipo: str, clave: str) -> Optional[str]:
    d = carpeta()
    if d is None:
        return None
    h = hashlib.sha1((tipo + "|" + clave + "|" + version_codigo()).encode("utf-8")).hexdigest()
    return os.path.join(d, tipo + "-" + h + ".pkl")


def _leer(tipo: str, clave: Optional[str]):
    if clave is None:
        return None
    r = _ruta(tipo, clave)
    if r is None or not os.path.isfile(r):
        return None
    try:
        with open(r, "rb") as f:
            v = pickle.load(f)
        try:
            os.utime(r, None)
        except OSError:
            pass
        if not (isinstance(v, tuple) and len(v) == 2 and v[0] == clave):
            return None
        return v[1]
    except Exception:
        return None


def _guardar(tipo: str, clave: Optional[str], valor) -> None:
    if clave is None:
        return
    r = _ruta(tipo, clave)
    if r is None:
        return
    tmp = r + ".%d.tmp" % os.getpid()
    try:
        with open(tmp, "wb") as f:
            pickle.dump((clave, valor), f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, r)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return
    _recortar(os.path.dirname(r))


def _recortar(d: str) -> None:
    """Deja los más recientes que entran en `MAX_MB`."""
    try:
        archivos = sorted((os.stat(p).st_mtime, os.path.getsize(p), p) for p in glob.glob(os.path.join(d, "*.pkl")))
    except OSError:
        return
    total = sum(s for _t, s, _p in archivos)
    for _t, s, p in archivos:
        if total <= MAX_MB * 1024 * 1024:
            break
        try:
            os.remove(p)
            total -= s
        except OSError:
            pass


# ── fuentes Type3 ───────────────────────────────────────────────────────────
def clave_fuente(procs: Dict[int, bytes], fm: List[float]) -> str:
    """Huella del CONTENIDO de una fuente Type3: su FontMatrix y cada glifo (código + contenido)."""
    h = hashlib.sha1(repr([float(v) for v in fm]).encode("ascii"))
    h.update(repr([type(v).__name__ for v in fm]).encode("ascii"))
    for c in sorted(procs):
        b = procs[c]
        h.update(b"%d:%d:" % (c, len(b)))
        h.update(b)
    return h.hexdigest()


def leer_fuente(clave: str):
    return _leer("f", clave)


def guardar_fuente(clave: str, valor) -> None:
    _guardar("f", clave, valor)


# ── glifos de una hoja ──────────────────────────────────────────────────────
def huella_documento(doc) -> Optional[str]:
    """sha1 de los bytes del PDF (el archivo o el `stream` con que se abrió); None si no se sabe."""
    got = doc.__dict__.get("_pdfcad_huella_texto")
    if got is not None:
        return got or None
    h = ""
    try:
        s = getattr(doc, "stream", None)
        if isinstance(s, (bytes, bytearray, memoryview)) and len(s):
            h = hashlib.sha1(s).hexdigest()
        elif doc.name and os.path.isfile(doc.name):
            ruta = os.path.abspath(doc.name)
            st = os.stat(ruta)
            k = (ruta, st.st_size, st.st_mtime_ns)
            h = _HUELLAS_ARCHIVO.get(k, "")
            if not h:
                sh = hashlib.sha1()
                with open(ruta, "rb") as f:
                    for bloque in iter(lambda: f.read(1 << 22), b""):
                        sh.update(bloque)
                h = _HUELLAS_ARCHIVO[k] = sh.hexdigest()
    except Exception:
        h = ""
    doc.__dict__["_pdfcad_huella_texto"] = h
    return h or None


def clave_hoja(page) -> Optional[str]:
    """Huella de la hoja para sus glifos (ver el docstring); None = no se guarda."""
    if carpeta() is None:
        return None
    doc = page.parent
    hd = huella_documento(doc)
    if hd is None:
        return None
    try:
        contenido = hashlib.sha1(page.read_contents()).hexdigest()
        capas = tuple(bool(c.get("on")) for c in (doc.layer_ui_configs() or ()))
        return f"{hd}|{page.number}|{page.rotation}|{doc.xref_length()}|{len(doc)}|{contenido}|{capas}"
    except Exception:
        return None


def leer_glifos(page):
    """Los glifos guardados de la hoja (la MISMA lista que daría `texto_pdf._glifos`) o None."""
    clave = clave_hoja(page)
    v = _leer("g", clave)
    if v is None:
        return None
    try:
        return _desempacar(v)
    except Exception:
        return None


def guardar_glifos(page, glifos) -> None:
    clave = clave_hoja(page)
    if clave is None:
        return
    try:
        v = _empacar(glifos)
    except Exception:
        return
    _guardar("g", clave, v)


def _k(v):
    """Clave EXACTA de un valor: tipo y, en los números de punto flotante, sus bits (0.0 ≠ -0.0)."""
    if isinstance(v, float):
        return (type(v), float.hex(v))
    if isinstance(v, tuple):
        return (tuple, tuple(_k(x) for x in v))
    return (type(v), v)


def _tabla(valores):
    """(lista de valores distintos, índice de cada uno) — conserva el objeto de su primera aparición."""
    pos: dict = {}
    por_id: dict = {}          # los glifos de una corrida comparten el MISMO objeto (y todos siguen vivos aquí)
    distintos, idx = [], []
    for v in valores:
        i = por_id.get(id(v))
        if i is None:
            k = _k(v)
            i = pos.get(k)
            if i is None:
                i = pos[k] = len(distintos)
                distintos.append(v)
            por_id[id(v)] = i
        idx.append(i)
    return distintos, np.asarray(idx, dtype=np.int32)


def _empacar(glifos) -> dict:
    """Columnas: tablas de letras, direcciones, colores y fuentes; números en matrices (float64: exactos)."""
    n = len(glifos)
    letras, li = _tabla([g.letra for g in glifos])
    dirs, di = _tabla([g.dir for g in glifos])
    colores, ci = _tabla([g.color for g in glifos])
    fuentes, fi = _tabla([g.fuente for g in glifos])
    tams, ti = _tabla([g.tam for g in glifos])
    con = np.array([g.tinta is not None for g in glifos], dtype=bool)
    # tipo de cada número de la caja de tinta: np.float64 (lo normal) o float (por si acaso): se repone igual
    tinta = np.array([g.tinta for g in glifos if g.tinta is not None], dtype=np.float64).reshape(-1, 4)
    tipos_tinta = sorted({type(v).__name__ for g in glifos if g.tinta is not None for v in g.tinta})
    if any(t not in ("float64", "float") for t in tipos_tinta) or len(tipos_tinta) > 1:
        raise ValueError("tipos de caja de tinta no previstos")
    for g in glifos:
        if type(g.gid) is not int or type(g.seqno) is not int or type(g.origen[0]) is not float \
                or type(g.origen[1]) is not float or len(g.origen) != 2:
            raise ValueError("tipos de glifo no previstos")
    return {
        "n": n, "letras": letras, "li": li, "dirs": dirs, "di": di, "colores": colores, "ci": ci,
        "fuentes": fuentes, "fi": fi, "tams": tams, "ti": ti,
        "gid": np.array([g.gid for g in glifos], dtype=np.int64),
        "seqno": np.array([g.seqno for g in glifos], dtype=np.int64),
        "ox": np.array([g.origen[0] for g in glifos], dtype=np.float64),
        "oy": np.array([g.origen[1] for g in glifos], dtype=np.float64),
        "con": con, "tinta": tinta, "tipo_tinta": tipos_tinta[0] if tipos_tinta else "float64",
    }


def _desempacar(v: dict):
    from hoja.texto_pdf import Glifo
    n = int(v["n"])
    letras, dirs, colores, fuentes, tams = v["letras"], v["dirs"], v["colores"], v["fuentes"], v["tams"]
    li, di, ci, fi, ti = (v[k].tolist() for k in ("li", "di", "ci", "fi", "ti"))
    gid, seq, ox, oy = v["gid"].tolist(), v["seqno"].tolist(), v["ox"].tolist(), v["oy"].tolist()
    con = v["con"].tolist()
    t = v["tinta"]
    vals = list(t.ravel()) if v["tipo_tinta"] == "float64" else t.ravel().tolist()
    if len(con) != n or len(vals) != 4 * sum(con):
        raise ValueError("caché incompleta")
    out = []
    agregar = out.append
    k = 0
    for i in range(n):
        if con[i]:
            caja = (vals[k], vals[k + 1], vals[k + 2], vals[k + 3])
            k += 4
        else:
            caja = None
        agregar(Glifo(letras[li[i]], gid[i], (ox[i], oy[i]), tams[ti[i]], dirs[di[i]], colores[ci[i]],
                      fuentes[fi[i]], caja, seq[i]))
    return out
