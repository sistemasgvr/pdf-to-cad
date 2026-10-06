"""Autoguardado y recuperación del proyecto (pedido del usuario 2026-10-05).

Cada `INTERVALO_MS`, si el proyecto tiene cambios REALES sin guardar (la misma
huella de contenido que usa «¿Deseas guardar los cambios?»), se escribe una copia
en `<carpeta>/<sesión>/` con las mismas partes del .digproj:
  - `model.json` (los datos; pequeño) se reescribe en cada copia;
  - `page.png` (imagen del lienzo) y los PDF (`source.pdf`, `external/`,
    `sources/`) solo cuando cambian, y en un hilo aparte: así la app no se traba
    aunque la hoja sea grande;
  - `meta.json` (proyecto de origen, fecha, nº de utilidades) al final: una copia
    sin meta.json está a medias y no se ofrece.
Cada ventana abierta tiene un `<sesión>.lock` (QLockFile). Si la app se cierra de
golpe, el lock queda huérfano (su proceso ya no existe) y al abrir otra vez la
copia se ofrece para recuperar. La copia se borra al guardar, al descartar los
cambios y al cerrar la app normalmente.

Las pruebas usan otra carpeta con la variable de entorno `PDFCAD_RECUPERACION`.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
import zipfile

from PySide6 import QtCore

import project_io

INTERVALO_MS = 120_000          # 2 minutos
PNG_CALIDAD = 80                # PNG con compresión rápida (la copia no necesita la máxima)


def carpeta_base() -> str:
    """Carpeta de las copias: %LOCALAPPDATA%/pdf-to-cad/recuperacion (o la de las pruebas)."""
    env = os.environ.get("PDFCAD_RECUPERACION")
    if env:
        return env
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pdf-to-cad", "recuperacion")


def _escribir(path, data: bytes):
    """Escritura atómica (si se corta a medias, queda el archivo anterior)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def recuperables(base=None) -> list:
    """Copias de sesiones que se cerraron sin guardar (la más reciente primero).
    No incluye las de ventanas que siguen abiertas (su lock está tomado)."""
    base = base or carpeta_base()
    out = []
    if not os.path.isdir(base):
        return out
    for nombre in os.listdir(base):
        d = os.path.join(base, nombre)
        if not os.path.isdir(d):
            continue
        lock = QtCore.QLockFile(os.path.join(base, nombre + ".lock"))
        lock.setStaleLockTime(0)                   # solo cuenta si su proceso sigue vivo
        if not lock.tryLock(0):
            continue                               # otra ventana abierta todavía la usa
        lock.unlock()
        meta_p = os.path.join(d, "meta.json")
        if not all(os.path.isfile(os.path.join(d, p)) for p in ("meta.json", "model.json", "page.png")):
            shutil.rmtree(d, ignore_errors=True)  # copia a medias de una sesión muerta
            continue
        try:
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            shutil.rmtree(d, ignore_errors=True)
            continue
        meta["dir"] = d
        out.append(meta)
    out.sort(key=lambda m: m.get("fecha", 0), reverse=True)
    return out


def armar_digproj(d, destino) -> str:
    """Un .digproj (zip) con las partes de la copia de la carpeta `d`."""
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_STORED) as z:
        for raiz, _dirs, archivos in os.walk(d):
            for a in archivos:
                if a == "meta.json" or a.endswith(".tmp"):
                    continue
                full = os.path.join(raiz, a)
                z.write(full, os.path.relpath(full, d).replace("\\", "/"))
    return destino


def descartar(meta):
    shutil.rmtree(meta["dir"], ignore_errors=True)


class Autoguardado(QtCore.QObject):
    """Copias periódicas del proyecto abierto en la ventana `win` (Main)."""

    def __init__(self, win, base=None):
        super().__init__(win)
        self.win = win
        self.base = base or carpeta_base()
        self.sesion = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.dir = os.path.join(self.base, self.sesion)
        self._lock = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(INTERVALO_MS)
        self._timer.timeout.connect(self.guardar_ahora)
        self._claves = {}            # parte → clave de lo ya escrito (para no reescribir lo pesado)
        self._firma_escrita = None   # huella de la última copia completa
        self._hilo = None
        self._cancelar = threading.Event()
        self.ultimo = None           # hora de la última copia completa
        self.error = None
        self._error_avisado = None

    @property
    def activo(self):
        return self._lock is not None

    def iniciar(self):
        os.makedirs(self.base, exist_ok=True)
        self._lock = QtCore.QLockFile(os.path.join(self.base, self.sesion + ".lock"))
        self._lock.setStaleLockTime(0)
        self._lock.tryLock(0)
        self._timer.start()

    def esperar(self, timeout=30.0):
        """Espera a que termine la escritura en curso (pruebas y cierre)."""
        if self._hilo is not None:
            self._hilo.join(timeout)
        return self._hilo is None or not self._hilo.is_alive()

    # ── copia ──
    def guardar_ahora(self):
        """Hace una copia si hay cambios reales nuevos. True si empezó a escribir."""
        w = self.win
        self._avisar_error()
        if not self.activo or w.canvas.pixmap_item is None or not w._has_real_changes():
            return False
        if self._hilo is not None and self._hilo.is_alive():
            return False                            # la anterior aún escribe
        try:
            model = project_io.build_model_dict(w)
            texto = json.dumps(model)
        except Exception as e:                      # un dato raro no debe tumbar la app
            self.error = str(e)
            return False
        firma = hash(texto)
        if firma == self._firma_escrita:
            return False
        trabajos, presentes = self._preparar(texto)
        meta = {
            "version": 1, "sesion": self.sesion, "fecha": time.time(),
            "proyecto": w.project_path or "",
            "nombre": (os.path.basename(w.project_path) if w.project_path
                       else (model.get("pdf_name") or "")),
            "utilidades": len(getattr(w, "pipes", []) or []),
        }
        self._cancelar.clear()
        self._hilo = threading.Thread(target=self._escribir_todo, args=(trabajos, presentes, meta, firma),
                                      name="autoguardado", daemon=True)
        self._hilo.start()
        return True

    def _preparar(self, texto_modelo):
        """Lo que hay que escribir (en el hilo de la UI: aquí solo se juntan datos)."""
        w = self.win
        trabajos, presentes = [], {"model.json", "meta.json", "page.png"}
        pm = w.canvas.pixmap_item.pixmap()
        clave = ("png", pm.cacheKey())
        if self._claves.get("page.png") != clave:
            trabajos.append(("page.png", "png", pm.toImage(), clave))
        pdf = getattr(w, "pdf_path", None)
        if pdf and os.path.isfile(pdf):
            st = os.stat(pdf)
            clave = ("copia", pdf, st.st_mtime, st.st_size)
            presentes.add("source.pdf")
            if self._claves.get("source.pdf") != clave:
                trabajos.append(("source.pdf", "copia", pdf, clave))
        elif getattr(w, "doc", None) is not None:
            clave = ("doc", id(w.doc))
            presentes.add("source.pdf")
            if self._claves.get("source.pdf") != clave:
                datos = w._get_pdf_bytes()
                if datos:
                    trabajos.append(("source.pdf", "bytes", datos, clave))
                else:
                    presentes.discard("source.pdf")
        for i, s in enumerate(getattr(w, "sheet_external_pdfs", []) or []):
            rel = f"external/{i:03d}.pdf"
            presentes.add(rel)
            clave = ("ext", id(s["data"]), len(s["data"]))
            if self._claves.get(rel) != clave:
                trabajos.append((rel, "bytes", s["data"], clave))
        comp = getattr(w, "composite", None)
        src_pdfs = getattr(w, "src_pdfs", []) or []
        if comp is not None and (len(src_pdfs) > 1 or not comp.is_single_full_page()):
            for i, e in enumerate(src_pdfs):
                rel = f"sources/{i:03d}.pdf"
                presentes.add(rel)
                clave = ("src", id(e["data"]), len(e["data"]))
                if self._claves.get(rel) != clave:
                    trabajos.append((rel, "bytes", e["data"], clave))
        trabajos.append(("model.json", "bytes", texto_modelo.encode("utf-8"), None))
        return trabajos, presentes

    def _escribir_todo(self, trabajos, presentes, meta, firma):
        """Hilo de escritura: lo pesado primero, model.json y meta.json al final."""
        try:
            os.makedirs(self.dir, exist_ok=True)
            for rel, tipo, dato, clave in trabajos:
                if self._cancelar.is_set():
                    return
                dst = os.path.join(self.dir, rel)
                if tipo == "png":
                    ba = QtCore.QByteArray()
                    buf = QtCore.QBuffer(ba)
                    buf.open(QtCore.QIODevice.WriteOnly)
                    dato.save(buf, "PNG", PNG_CALIDAD)
                    buf.close()
                    _escribir(dst, bytes(ba))
                elif tipo == "copia":
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(dato, dst + ".tmp")
                    os.replace(dst + ".tmp", dst)
                else:
                    _escribir(dst, dato)
                if clave is not None:
                    self._claves[rel] = clave
            for raiz, _dirs, archivos in os.walk(self.dir):   # partes que ya no corresponden
                for a in archivos:
                    full = os.path.join(raiz, a)
                    rel = os.path.relpath(full, self.dir).replace("\\", "/")
                    if rel not in presentes and not a.endswith(".tmp"):
                        os.remove(full)
                        self._claves.pop(rel, None)
            if self._cancelar.is_set():
                return
            _escribir(os.path.join(self.dir, "meta.json"), json.dumps(meta).encode("utf-8"))
            self._firma_escrita = firma
            self.ultimo = time.time()
            self.error = None
        except Exception as e:                      # disco lleno, permisos…: se reintenta en la próxima
            self.error = str(e)

    def _avisar_error(self):
        if self.error and self.error != self._error_avisado:
            self._error_avisado = self.error
            try:
                from i18n import t as _tr
                self.win._info(_tr("No se pudo guardar la copia automática: {error}").format(error=self.error))
            except Exception:
                pass

    # ── fin de la copia ──
    def limpiar(self):
        """Borra la copia de esta sesión (proyecto guardado, descartado o cerrado)."""
        self._cancelar.set()
        if self._hilo is not None and self._hilo.is_alive():
            self._hilo.join(15.0)
        self._hilo = None
        shutil.rmtree(self.dir, ignore_errors=True)
        self._claves.clear()
        self._firma_escrita = None
        self.ultimo = None

    def cerrar(self):
        """Cierre normal de la app: sin copia ni lock."""
        self._timer.stop()
        self.limpiar()
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None
