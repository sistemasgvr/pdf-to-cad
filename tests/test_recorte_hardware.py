"""Differential geometry tests against the pre-acceleration clipping rules."""
from types import SimpleNamespace

import fitz
import numpy as np
import pytest

from hoja import leyenda_trazos as T, recorte_lotes as R
from reconocimiento import recognition as C, recognition_geom as G


@pytest.fixture(autouse=True)
def _selector_aislado(monkeypatch):
    for name, value in (("_backends", {}), ("_fallidos", set()), ("_validados", set()),
                        ("_elecciones", {}), ("_sondeos", {}), ("_preparador", None)):
        monkeypatch.setattr(R, name, value)


class _Backend:
    def __init__(self, run, key="cuda:0", kind="cuda"):
        self.run, self.key, self.kind, self.name = run, key, kind, "test GPU"


def _line(a, b, layer="WATER", level=2):
    return dict(type="s", items=[("l", fitz.Point(*a), fitz.Point(*b))],
                rect=fitz.Rect(min(a[0], b[0]), min(a[1], b[1]),
                               max(a[0], b[0]), max(a[1], b[1])),
                layer=layer, level=level)


def _clip(poly, level=1):
    pts = [fitz.Point(*p) for p in poly]
    return dict(type="clip", level=level,
                items=[("l", a, b) for a, b in zip(pts, pts[1:] + pts[:1])])


def _original(path, polys):
    if not polys:
        return path
    r = path.get("rect")
    rects = [T._rect_poly(pg) for pg in polys]
    if r is not None and all(b is not None and b[0] <= r.x0 and b[1] <= r.y0
                             and r.x1 <= b[2] and r.y1 <= b[3] for b in rects):
        return path
    return G.clip_path(path, polys)


def _reference(paths, page_rect, recognition=True):
    clips, candidates, profiles = {}, [], []
    for path in paths:
        lvl, kind = path.get("level", 0), path["type"]
        if kind in ("clip", "group"):
            clips = {k: v for k, v in clips.items() if k < lvl}
            if kind == "clip":
                clips[lvl] = C._clip_polygon(path, page_rect)
            continue
        if not path.get("items"):
            continue
        shown = _original(path, [p for k, p in clips.items() if k < lvl and p])
        if shown is None:
            continue
        if C.PROFILE_LAYER_TOKEN in T.pdf_layers.short_name(path.get("layer", "")).upper():
            bb = G._path_bbox(shown)
            if bb is not None:
                profiles.append(bb)
        if recognition and shown.get("clipped") and C._path_length(shown) < C.CLIP_SLIVER_PT:
            continue
        candidates.append((path, shown))
    regions = C._merge_close_boxes(profiles, C.PROFILE_REGION_PAD_PT) if profiles and recognition else []
    return [(p, s) for p, s in candidates if not (regions and C._region_hit(G._path_bbox(s), regions))]


def _signature(result):
    return [(id(p), bool(s.get("clipped")), G._path_chains(s), s.get("cut_pts", [])) for p, s in result]


@pytest.mark.parametrize("batch", [1, 257])
@pytest.mark.parametrize("recognition", [False, True])
def test_matches_original_nested_rotated_curved_and_profile_clips(monkeypatch, batch, recognition):
    rng = np.random.default_rng(71)
    page = SimpleNamespace(rect=fitz.Rect(0, 0, 1000, 1000))
    square = [(100, 100), (300, 100), (300, 300), (100, 300)]
    diamond = [(200, 80), (320, 200), (200, 320), (80, 200)]
    paths = [_clip(square)]
    paths += [_line(a, b) for a, b in rng.uniform(0, 400, (600, 2, 2))]
    # At/beside the edge: the 0.25 pt visibility tolerance must survive rejection.
    paths += [_line((100 - d, 150), (100 - d, 250)) for d in (0., .1, .25, .25001)]
    paths += [_clip(diamond, 2)]
    paths += [_line(a, b, level=3) for a, b in rng.uniform(0, 400, (600, 2, 2))]
    curve = dict(type="s", level=3, layer="WATER", rect=fitz.Rect(20, 20, 380, 380),
                 items=[("c", fitz.Point(20, 200), fitz.Point(380, 20),
                         fitz.Point(20, 380), fitz.Point(380, 200))])
    paths += [curve, _line((150, 180), (260, 180), C.PROFILE_LAYER_TOKEN, 3)]
    # Transparency group closes BOTH preceding clips, followed by shallower paths.
    paths += [dict(type="group", level=0), _line((10, 10), (50, 50), level=1)]
    paths += [_clip(square), _line((350, 350), (390, 390), level=1)]
    monkeypatch.setenv("PDFCAD_ACELERACION", "cpu")
    monkeypatch.setattr(R, "LOTE", batch)
    monkeypatch.setattr(R, "MIN_VECTOR", 1)
    monkeypatch.setattr(T.pdf_styles, "drawings", lambda *a, **kw: paths)
    expected = _reference(paths, page.rect, recognition)
    actual = T.trazos_visibles(page, para_reconocimiento=recognition)
    assert _signature(actual) == _signature(expected)
    if recognition:
        assert T.capas_visibles(page) == {p.get("layer") or "" for p, s in expected}


def test_prefilter_keeps_ambiguous_and_invalid_boxes(monkeypatch):
    monkeypatch.setenv("PDFCAD_ACELERACION", "cpu")
    boxes = [(1, 1, 2, 2), (-2, 1, -1, 2), (-.2, 1, -.1, 2),
             (-1, 1, 2, 2), (np.nan, 1, 2, 2), (5, 1, 2, 2)]
    assert R.clasificar(boxes, (0, 0, 10, 10), (0, 0, 10, 10), .25).tolist() == [1, -1, 0, 0, 0, 0]
    # A polygon's bounding box is insufficient proof that a path is inside it.
    assert R.clasificar([(1, 1, 2, 2)], (0, 0, 10, 10), None, .25).tolist() == [0]


def test_cuda_failure_retries_on_cpu(monkeypatch):
    monkeypatch.setenv("PDFCAD_ACELERACION", "cuda")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    def fail(*a):
        raise RuntimeError("Out of GPU memory")
    monkeypatch.setattr(R, "_backends", {"cuda:0": _Backend(fail)})
    assert R.clasificar([(1, 1, 2, 2)], (0, 0, 10, 10), None, .25).tolist() == [0]
    assert "cuda:0" in R._fallidos
    assert R._ultimo == "cpu"


def test_no_cuda_keeps_working(monkeypatch):
    monkeypatch.setenv("PDFCAD_ACELERACION", "cuda")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    assert R.clasificar([(20, 20, 21, 21)], (0, 0, 10, 10), None, .25).tolist() == [-1]


def test_auto_rejects_incorrect_cuda_results(monkeypatch):
    monkeypatch.setenv("PDFCAD_ACELERACION", "auto")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    monkeypatch.setattr(R, "_backends", {"cuda:0": _Backend(lambda *a: np.array([1], dtype=np.int8))})
    assert R._calibrar(np.array([(20, 20, 21, 21)]), (0, 0, 10, 10), None, .25) == "cpu"
    assert "cuda:0" in R._fallidos


def test_auto_does_not_wait_for_cold_cuda(monkeypatch):
    from concurrent.futures import Future
    class Preparing:
        def submit(self, *args):
            return Future()  # not completed: waiting here would hang the PDF task
    monkeypatch.setenv("PDFCAD_ACELERACION", "auto")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    monkeypatch.setattr(R, "_sin_cuda", False)
    monkeypatch.setattr(R, "_elecciones", {})
    monkeypatch.setattr(R, "_sondeos", {})
    monkeypatch.setattr(R, "_preparador", Preparing())
    assert R.clasificar([(20, 20, 21, 21)], (0, 0, 10, 10), None, .25).tolist() == [-1]
    assert R._ultimo == "cpu"


@pytest.mark.parametrize("faster", [False, True])
def test_auto_uses_completed_measurement(monkeypatch, faster):
    from concurrent.futures import Future
    done = Future()
    done.set_result("cuda:0" if faster else "cpu")
    monkeypatch.setenv("PDFCAD_ACELERACION", "auto")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    monkeypatch.setattr(R, "_sin_cuda", False)
    monkeypatch.setattr(R, "_elecciones", {})
    monkeypatch.setattr(R, "_sondeos", {(1, False): done})
    monkeypatch.setattr(R, "_backends", {"cuda:0": _Backend(lambda *a: np.array([-1], dtype=np.int8))})
    assert R.clasificar([(20, 20, 21, 21)], (0, 0, 10, 10), None, .25).tolist() == [-1]
    assert R._ultimo == ("cuda" if faster else "cpu")
    assert not R._sondeos


def test_batches_shrink_under_memory_pressure(monkeypatch):
    monkeypatch.setattr(R, "recursos", lambda: {"ram_disponible": 8 * 1024**2})
    assert R.tamano_lote() == 256
    monkeypatch.setattr(R, "recursos", lambda: {"ram_disponible": 8 * 1024**3})
    assert R.tamano_lote() == R.LOTE


def test_failed_detection_future_keeps_cpu(monkeypatch):
    from concurrent.futures import Future
    failed = Future()
    failed.set_exception(RuntimeError("driver unavailable"))
    monkeypatch.setenv("PDFCAD_ACELERACION", "auto")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    monkeypatch.setattr(R, "_sondeos", {(1, False): failed})
    assert R.clasificar([(20, 20, 21, 21)], (0, 0, 10, 10), None, .25).tolist() == [-1]
    assert R._ultimo == "cpu"


def test_benchmark_selects_fastest_valid_device(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(R.time, "perf_counter", lambda: clock[0])
    def cpu(*args):
        clock[0] += 1.
        return np.array([-1], dtype=np.int8)
    def gpu(delay):
        def run(*args):
            clock[0] += delay
            return np.array([-1], dtype=np.int8)
        return run
    monkeypatch.setattr(R, "_calcular", cpu)
    monkeypatch.setattr(R, "_backends", {
        "cuda:0": _Backend(gpu(.5)),
        "opencl:0:0": _Backend(gpu(.25), "opencl:0:0", "opencl"),
        "opencl:1:0": _Backend(gpu(2.), "opencl:1:0", "opencl")})
    assert R._calibrar(np.array([(20, 20, 21, 21)]), (0, 0, 10, 10), None, .25) == "opencl:0:0"


def test_opencl_failure_can_use_another_gpu(monkeypatch):
    def fail(*a):
        raise RuntimeError("device lost")
    monkeypatch.setenv("PDFCAD_ACELERACION", "opencl")
    monkeypatch.setattr(R, "MIN_CUDA", 1)
    monkeypatch.setattr(R, "_backends", {
        "opencl:0:0": _Backend(fail, "opencl:0:0", "opencl"),
        "opencl:1:0": _Backend(lambda *a: np.array([-1], dtype=np.int8), "opencl:1:0", "opencl")})
    assert R.clasificar([(20, 20, 21, 21)], (0, 0, 10, 10), None, .25).tolist() == [-1]
    assert R._ultimo == "opencl"
    assert R._fallidos == {"opencl:0:0"}


def test_opencl_discovery_rejects_insufficient_precision(monkeypatch):
    import sys
    from hoja.recorte_opencl import descubrir
    good = dict(available=True, compiler_available=True, double_fp_config=1,
                global_mem_size=1024**3, vendor="test", name="test")
    class Platform:
        def get_devices(self, **kw):
            return [SimpleNamespace(**dict(good, double_fp_config=0)), SimpleNamespace(**good)]
    class BrokenPlatform:
        def get_devices(self, **kw):
            raise RuntimeError("platform broken")
    fake = SimpleNamespace(get_platforms=lambda: [BrokenPlatform(), Platform()], device_type=SimpleNamespace(GPU=4))
    monkeypatch.setitem(sys.modules, "pyopencl", fake)
    found = descubrir()
    assert [b.key for b in found] == ["opencl:1:1"]


def test_real_opencl_devices_match_cpu(monkeypatch):
    from hoja.recorte_opencl import descubrir
    devices = descubrir()
    if not devices:
        pytest.skip("No OpenCL GPU with FP64 available")
    rng = np.random.default_rng(93)
    points = rng.uniform(-100, 100, (65536, 2, 2))
    boxes = np.concatenate([points.min(axis=1), points.max(axis=1)], axis=1)
    boxes[:5] = [[np.nan, 0, 1, 1], [0, 0, np.inf, 1], [-.25, 1, -.1, 2],
                 [5, 1, 2, 2], [np.nextafter(-.25, -np.inf), 1, -.25, 2]]
    for device in devices:
        for interior in (None, (0., 0., 10., 10.)):
            for data in (boxes, boxes[::2], boxes[:97], boxes[:0]):
                expected = R._calcular(np, data, (0., 0., 10., 10.), interior, .25)
                assert np.array_equal(device.run(data, (0., 0., 10., 10.), interior, .25), expected), device.name


def test_real_cuda_matches_cpu_if_installed(monkeypatch):
    try:
        import cupy as cp
    except ImportError:
        pytest.skip("CuPy opcional no instalado")
    if not cp.cuda.runtime.getDeviceCount():
        pytest.skip("No CUDA GPU")
    rng = np.random.default_rng(92)
    points = rng.uniform(-1000, 1000, (65536, 2, 2))
    boxes = np.concatenate([points.min(axis=1), points.max(axis=1)], axis=1)
    boxes[:4] = [[np.nan, 0, 1, 1], [0, 0, np.inf, 1], [-.25, 1, -.1, 2], [5, 1, 2, 2]]
    monkeypatch.setattr(R, "_kernel", None)
    for interior in (None, (0., 0., 10., 10.)):
        expected = R._calcular(np, boxes, (0., 0., 10., 10.), interior, .25)
        actual = R._en_cuda(cp, boxes, (0., 0., 10., 10.), interior, .25)
        assert np.array_equal(expected, actual)
        actual = R._en_cuda(cp, boxes[::2], (0., 0., 10., 10.), interior, .25)
        assert np.array_equal(expected[::2], actual)
