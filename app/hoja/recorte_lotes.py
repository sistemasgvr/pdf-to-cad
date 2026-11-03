"""Filtro previo y conservador del recorte: CPU, OpenCL portable y CUDA (CuPy) opcional.

Solo clasifica cajas. Los casos en el borde siguen por la geometría de siempre, con sus tolerancias.
Ningún objeto de MuPDF entra en hilos ni en la GPU. Los búferes son acotados y la GPU es opcional: un
fallo del controlador o de memoria vuelve a la CPU.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from nucleo.hardware import recursos

LOG = logging.getLogger(__name__)
LOTE = 65536                      # < 10 MiB de números, sea cual sea el tamaño del PDF
MIN_VECTOR = 256
MIN_CUDA = 32768
_cuda = None
_kernel = None
_sin_cuda = False
_elecciones = {}
_sondeos = {}
_preparador = None
_ultimo = "cpu"
_dispositivo = None
_backends = None
_fallidos = set()
_validados = set()


def tamano_lote():
    libre = recursos()["ram_disponible"]
    # ≤ 1/1024 de la RAM libre en coordenadas; con poca memoria, lotes más chicos.
    return min(LOTE, max(256, libre // (1024 * 32))) if libre else min(LOTE, 4096)


def _cargar_cuda():
    global _cuda, _sin_cuda
    if _sin_cuda:
        return None
    if _cuda is None:
        try:
            import cupy as cp
            if cp.cuda.runtime.getDeviceCount() < 1:
                raise RuntimeError("No CUDA device")
            _cuda = cp
        except Exception as exc:
            _sin_cuda = True
            LOG.info("Recorte por CPU: CUDA no disponible (%s)", exc)
    return _cuda


def _calcular(xp, cajas, exterior, interior, tolerancia):
    a, b, c, d = exterior
    fuera = ((cajas[:, 2] < a - tolerancia) | (cajas[:, 3] < b - tolerancia)
             | (cajas[:, 0] > c + tolerancia) | (cajas[:, 1] > d + tolerancia))
    # Una caja con NaN o inválida va siempre por la geometría.
    validas = (xp.isfinite(cajas).all(axis=1) & (cajas[:, 0] <= cajas[:, 2])
               & (cajas[:, 1] <= cajas[:, 3]))
    estado = xp.where(fuera & validas, -1, 0).astype(xp.int8)
    if interior is not None:
        a, b, c, d = interior
        dentro = ((a <= cajas[:, 0]) & (b <= cajas[:, 1])
                  & (cajas[:, 2] <= c) & (cajas[:, 3] <= d) & validas)
        estado = xp.where(dentro, 1, estado).astype(xp.int8)
    return estado


def _en_cuda(cp, cajas, exterior, interior, tol):
    global _kernel
    if _kernel is None:
        # Todas las condiciones en una sola llamada, no muchas operaciones chicas en la GPU.
        _kernel = cp.ElementwiseKernel(
            "raw float64 boxes, float64 x0, float64 y0, float64 x1, float64 y1, "
            "float64 ix0, float64 iy0, float64 ix1, float64 iy1, float64 tol, bool interior",
            "int8 state",
            """
            const double a = boxes[4*i], b = boxes[4*i+1];
            const double c = boxes[4*i+2], d = boxes[4*i+3];
            const bool valid = isfinite(a) && isfinite(b) && isfinite(c)
                && isfinite(d) && a <= c && b <= d;
            const bool outside = c < x0-tol || d < y0-tol || a > x1+tol || b > y1+tol;
            const bool inside = interior && ix0 <= a && iy0 <= b && c <= ix1 && d <= iy1;
            state = valid ? (inside ? 1 : (outside ? -1 : 0)) : 0;
            """, "pdfcad_clip_bounds")
    # asnumpy sincroniza: los tiempos incluyen la copia de ida y vuelta.
    return cp.asnumpy(_kernel(cp.ascontiguousarray(cp.asarray(cajas)), *exterior,
                             *(interior or (0., 0., 0., 0.)), tol,
                             interior is not None, size=len(cajas)))


class _CUDABackend:
    kind = "cuda"

    def __init__(self, cp, device):
        self.cp, self.device = cp, device
        self.key = f"cuda:{device}"
        self.name = cp.cuda.runtime.getDeviceProperties(device)["name"].decode()

    def run(self, cajas, exterior, interior, tol):
        with self.cp.cuda.Device(self.device):
            return _en_cuda(self.cp, cajas, exterior, interior, tol)


def _disponibles():
    global _backends
    if _backends is None:
        encontrados = {}
        cp = _cargar_cuda()  # sigue siendo opcional: no está en requirements.txt
        if cp is not None:
            for i in range(cp.cuda.runtime.getDeviceCount()):
                try:
                    with cp.cuda.Device(i):
                        if cp.cuda.runtime.memGetInfo()[0] < 16 * 1024**2:
                            continue
                    b = _CUDABackend(cp, i)
                    encontrados[b.key] = b
                except Exception as exc:
                    LOG.info("GPU CUDA omitida: %s", exc)
        from hoja.recorte_opencl import descubrir
        for b in descubrir():
            encontrados[b.key] = b
        _backends = encontrados
    return {k: b for k, b in _backends.items() if k not in _fallidos}


def _ejecutar(backend, cajas, exterior, interior, tol):
    result = backend.run(cajas, exterior, interior, tol)
    if backend.key not in _validados:
        expected = _calcular(np, cajas, exterior, interior, tol)
        if not np.array_equal(expected, result):
            raise RuntimeError("GPU/CPU clipping prefilter mismatch")
        _validados.add(backend.key)
    return result


def _calibrar(cajas, exterior, interior, tol):
    """Compara en segundo plano los dispositivos que sirven, sin bajar la precisión."""
    inicio = time.perf_counter()
    backends = _disponibles()
    LOG.info("Detección GPU: %d rutas en %.3f s", len(backends), time.perf_counter() - inicio)
    referencia = _calcular(np, cajas, exterior, interior, tol)
    tiempos = []
    for _ in range(3):
        inicio = time.perf_counter()
        _calcular(np, cajas, exterior, interior, tol)
        tiempos.append(time.perf_counter() - inicio)
    tc = sorted(tiempos)[1]
    mejor, limite = "cpu", tc * .8
    for key, backend in backends.items():
        try:
            inicio = time.perf_counter()
            obtenido = _ejecutar(backend, cajas, exterior, interior, tol)
            arranque = time.perf_counter() - inicio
            if not np.array_equal(referencia, obtenido):
                raise RuntimeError("GPU/CPU clipping prefilter mismatch")
            tiempos = []
            for _ in range(3):
                inicio = time.perf_counter()
                backend.run(cajas, exterior, interior, tol)
                tiempos.append(time.perf_counter() - inicio)
            tg = sorted(tiempos)[1]
            LOG.info("Recorte lote=%d %s (%s): CPU=%.3f ms GPU=%.3f ms arranque=%.3f s",
                     len(cajas), key, backend.name, tc * 1000, tg * 1000, arranque)
            if tg < limite:
                mejor, limite = key, tg
        except Exception as exc:
            _fallidos.add(key)
            LOG.warning("GPU %s descartada; se conserva CPU: %s", key, exc)
    LOG.info("Recorte lote=%d elegido=%s", len(cajas), mejor)
    return mejor


def clasificar(cajas, exterior, interior, tol):
    """-1 = seguro fuera; 1 = dentro de los recortes rectangulares; 0 = decide la geometría exacta.

    PDFCAD_ACELERACION=cpu (por defecto), auto, opencl o cuda. La GPU es solo a petición: en 65 535 cajas
    ahorra ~0,4 ms de los ~200 ms de la etapa (docs/aceleracion-hardware.md). En auto se mide por tamaño
    de lote en cada trabajador y se exige ganar al menos un 20 %, copias incluidas. Con un modo GPU
    explícito, si la ruta falla también se vuelve a la CPU.
    """
    global _ultimo, _dispositivo, _preparador
    cajas = np.ascontiguousarray(cajas, dtype=np.float64).reshape((-1, 4))
    modo = os.environ.get("PDFCAD_ACELERACION", "cpu").lower()
    cpu = lambda: _calcular(np, cajas, exterior, interior, tol)
    if modo == "cpu" or len(cajas) < MIN_CUDA:
        _ultimo = "cpu"
        _dispositivo = None
        return cpu()
    clave = (len(cajas).bit_length(), interior is not None)
    if modo not in ("cuda", "opencl") and clave not in _elecciones:
        sondeo = _sondeos.get(clave)
        if sondeo is None:
            try:
                if _preparador is None:
                    _preparador = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdfcad-gpu")
                _sondeos[clave] = _preparador.submit(_calibrar, cajas.copy(), exterior, interior, tol)
            except Exception as exc:
                _elecciones[clave] = "cpu"
                LOG.info("No se pudo preparar GPU; se conserva CPU: %s", exc)
        elif sondeo.done():
            try:
                _elecciones[clave] = sondeo.result()
            except Exception as exc:
                _elecciones[clave] = "cpu"
                LOG.warning("Detección GPU falló; se conserva CPU: %s", exc)
            _sondeos.pop(clave, None)  # suelta el lote de la medición
        # Leer el PDF nunca espera a que se cree el contexto ni se compile para la GPU.
        if clave not in _elecciones:
            _ultimo = "cpu"
            _dispositivo = None
            return cpu()
    elegido = _elecciones.get(clave, "cpu")
    if modo not in ("cuda", "opencl") and elegido == "cpu":
        _ultimo = "cpu"
        _dispositivo = None
        return cpu()
    backends = _disponibles()
    candidatos = ([b for b in backends.values() if b.kind == modo]
                  if modo in ("cuda", "opencl") else [backends[elegido]] if elegido in backends else [])
    for backend in candidatos:
        try:
            resultado = _ejecutar(backend, cajas, exterior, interior, tol)
            _ultimo, _dispositivo = backend.kind, backend.name
            return resultado
        except Exception as exc:
            _fallidos.add(backend.key)
            _elecciones.pop(clave, None)
            LOG.warning("GPU %s falló; se continúa en CPU: %s", backend.key, exc)
    _ultimo = "cpu"
    _dispositivo = None
    return cpu()


class Plan:
    """Las cajas de los recortes, calculadas una vez por estado de recorte y no por trazo."""

    def __init__(self, polys, rects, tol):
        self.polys, self.rects, self.tol = polys, rects, tol
        bounds = [(min(p[0] for p in pg), min(p[1] for p in pg),
                   max(p[0] for p in pg), max(p[1] for p in pg))
                  for pg in polys if len(pg) >= 3]
        self.exterior = self._interseccion(bounds) if bounds else None
        self.interior = self._interseccion(rects) if rects and all(r is not None for r in rects) else None

    @staticmethod
    def _interseccion(bounds):
        return (max(r[0] for r in bounds), max(r[1] for r in bounds),
                min(r[2] for r in bounds), min(r[3] for r in bounds))

    def estados(self, paths):
        if not self.polys:
            return [1] * len(paths)
        if self.exterior is None:
            return [0] * len(paths)
        cajas = []
        for path in paths:
            r = path.get("rect")
            cajas.append((r.x0, r.y0, r.x1, r.y1) if r is not None else (np.nan,) * 4)
        return clasificar(cajas, self.exterior, self.interior, self.tol).tolist()
