"""Filtro de recorte en GPU, portable. Exige controlador y doble precisión.

Un dispositivo sin FP64 se excluye: la precisión geométrica no se baja. Cada ruta tiene su contexto,
su cola y sus búferes acotados. Solo recibe copias numéricas: aquí nunca entran objetos de MuPDF ni de Qt.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

LOG = logging.getLogger(__name__)
_SOURCE = r"""
#if defined(cl_khr_fp64)
#pragma OPENCL EXTENSION cl_khr_fp64 : enable
#elif defined(cl_amd_fp64)
#pragma OPENCL EXTENSION cl_amd_fp64 : enable
#endif
__kernel void clip_bounds(__global const double4 *boxes,
    double x0, double y0, double x1, double y1,
    double ix0, double iy0, double ix1, double iy1,
    double tol, int interior, int count, __global char *state) {
    int i = get_global_id(0);
    if (i >= count) return;
    double4 p = boxes[i];
    int valid = isfinite(p.x) && isfinite(p.y) && isfinite(p.z) && isfinite(p.w)
        && p.x <= p.z && p.y <= p.w;
    int outside = p.z < x0-tol || p.w < y0-tol || p.x > x1+tol || p.y > y1+tol;
    int inside = interior && ix0 <= p.x && iy0 <= p.y && p.z <= ix1 && p.w <= iy1;
    state[i] = valid ? (inside ? 1 : (outside ? -1 : 0)) : 0;
}
"""


class Backend:
    kind = "opencl"

    def __init__(self, cl, device, key):
        self.cl, self.device, self.key = cl, device, key
        self.name = f"{device.vendor.strip()} {device.name.strip()}"
        self._context = self._queue = self._kernel = None
        self._input = self._output = None
        self._capacity = 0
        self._lock = threading.Lock()

    def run(self, boxes, exterior, interior, tol):
        boxes = np.ascontiguousarray(boxes, dtype=np.float64).reshape((-1, 4))
        result = np.empty(len(boxes), dtype=np.int8)
        if not len(boxes):
            return result
        with self._lock:  # nadie pisa los argumentos ni los búferes a medio cálculo
            cl = self.cl
            if self._context is None:
                self._context = cl.Context([self.device])
                self._queue = cl.CommandQueue(self._context)
                program = cl.Program(self._context, _SOURCE).build()
                self._kernel = cl.Kernel(program, "clip_bounds")
            if len(boxes) > self._capacity:
                self._input = cl.Buffer(self._context, cl.mem_flags.READ_ONLY, boxes.nbytes)
                self._output = cl.Buffer(self._context, cl.mem_flags.WRITE_ONLY, len(boxes))
                self._capacity = len(boxes)
            cl.enqueue_copy(self._queue, self._input, boxes, is_blocking=False)
            args = [np.float64(v) for v in (*exterior, *(interior or (0., 0., 0., 0.)), tol)]
            self._kernel(self._queue, (len(boxes),), None, self._input, *args,
                         np.int32(interior is not None), np.int32(len(boxes)), self._output)
            # Lectura bloqueante: los tiempos medidos incluyen el cálculo y las copias.
            cl.enqueue_copy(self._queue, result, self._output, is_blocking=True)
        return result


def descubrir():
    """Las GPU que sirven de todas las plataformas OpenCL; el fallo de una plataforma no afecta a las demás."""
    try:
        import pyopencl as cl
        platforms = cl.get_platforms()
    except Exception as exc:
        LOG.info("OpenCL no disponible; se conserva la ruta CPU (%s)", exc)
        return []
    backends = []
    for pi, platform in enumerate(platforms):
        try:
            devices = platform.get_devices(device_type=cl.device_type.GPU)
        except Exception:
            continue
        for di, device in enumerate(devices):
            try:
                # Por lo que el dispositivo puede hacer, no por una lista de marcas o modelos.
                if (not device.available or not device.compiler_available
                        or not device.double_fp_config or device.global_mem_size < 16 * 1024**2):
                    continue
                backends.append(Backend(cl, device, f"opencl:{pi}:{di}"))
            except Exception as exc:
                LOG.info("Dispositivo OpenCL omitido: %s", exc)
    return backends
