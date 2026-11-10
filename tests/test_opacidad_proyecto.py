"""La opacidad del PDF y el fondo del lienzo (blanco/negro) se guardan en el .digproj
y se reponen al abrir (pedido del usuario 2026-11-06)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui  # noqa: E402

from test_autoguardado import _ventana  # noqa: E402


def test_opacidad_y_fondo_viajan_en_el_proyecto(monkeypatch, tmp_path):
    app, w = _ventana(monkeypatch)
    w.canvas.set_pdf_opacity(0.4)
    w.canvas.set_pdf_bg(QtGui.QColor(0, 0, 0))
    ruta = str(tmp_path / "p.digproj")
    w._write_project(ruta)
    app2, w2 = _ventana(monkeypatch)
    assert w2.canvas.pdf_opacity == 1.0
    w2._open_project_path(ruta)
    assert abs(w2.canvas.pdf_opacity - 0.4) < 1e-6
    assert w2.canvas.pdf_bg_color.value() < 128
    assert w2.lbl_opacity.text() == "40%"
    for v in (w, w2):
        v._dirty = False; v.close()
