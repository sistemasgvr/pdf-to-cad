"""Barras de carga precisas (pedido del usuario 2026-10-20): abrir y guardar el proyecto, revisar y limpiar,
Tabla de datos y su Excel, y el recálculo de conflictos y avisos. Lo que cambió por dentro para poder avisar
(leer/escribir el zip por bloques, la Tabla por filas…) da EXACTAMENTE lo mismo que antes."""
import os
import random
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import archivo_zip, avance  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")


def _entradas():
    rng = random.Random(5)
    grande = bytes(rng.getrandbits(8) for _ in range(3 * archivo_zip.BLOQUE + 777))
    repetido = (b"pdf-to-cad " * 400000)[:2 * archivo_zip.BLOQUE + 5]
    return [("model.json", '{"pipes": []}' * 1000), ("page.png", grande), ("source.pdf", repetido),
            ("external/000.pdf", b""), ("sources/000.pdf", b"x" * 10)]


def test_zip_por_bloques_igual_que_writestr(tmp_path):
    a, b = str(tmp_path / "a.zip"), str(tmp_path / "b.zip")
    avisos = []
    with avance.escuchar(lambda t, i, n: avisos.append((t, i, n))):
        archivo_zip.escribir(a, _entradas())
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, d in _entradas():
            z.writestr(nombre, d)
    za, zb = zipfile.ZipFile(a), zipfile.ZipFile(b)
    assert [i.filename for i in za.infolist()] == [i.filename for i in zb.infolist()]
    for ia, ib in zip(za.infolist(), zb.infolist()):
        assert (ia.CRC, ia.file_size, ia.compress_size, ia.compress_type, ia.external_attr) == \
               (ib.CRC, ib.file_size, ib.compress_size, ib.compress_type, ib.external_attr)
        assert za.read(ia) == zb.read(ib)
    with open(a, "rb") as fa, open(b, "rb") as fb:              # los datos comprimidos, byte a byte
        da, db = fa.read(), fb.read()
    for ia, ib in zip(za.infolist(), zb.infolist()):
        assert da[ia.header_offset + 30 + len(ia.filename):][:ia.compress_size] == \
               db[ib.header_offset + 30 + len(ib.filename):][:ib.compress_size]
    pasos = [i for t, i, n in avisos if t == "comprimir"]
    assert pasos == sorted(pasos) and pasos[-1] == sum(len(d if isinstance(d, bytes) else d.encode())
                                                       for _n, d in _entradas())
    leido = archivo_zip.leer(a)
    assert leido == {n: (d.encode() if isinstance(d, str) else d) for n, d in _entradas()}


def test_abrir_y_guardar_con_su_barra_dan_el_mismo_proyecto(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import barra_pesada
    from ui.ventana.app_window import Main
    vistos = []
    original = barra_pesada.AvancePesado._mostrar
    monkeypatch.setattr(barra_pesada.AvancePesado, "_mostrar",
                        lambda self, pump: vistos.append((self.barra.milesimas, self._detalle)) or original(self, pump))
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    abrir = [d for _m, d in vistos]
    assert any("Leyendo el archivo" in d for d in abrir) and any("Dibujando" in d for d in abrir)
    assert [m for m, _d in vistos] == sorted(m for m, _d in vistos)
    n = len(w.pipes)
    vistos.clear()
    ruta = str(tmp_path / "copia.digproj")
    w._write_project(ruta)
    assert any("Comprimiendo" in d for _m, d in vistos)
    original_z, copia_z = zipfile.ZipFile(ESC), zipfile.ZipFile(ruta)
    assert {i.filename for i in original_z.infolist()} <= {i.filename for i in copia_z.infolist()}
    assert copia_z.read("page.png") == original_z.read("page.png")
    w2 = Main(); w2._info = lambda *a, **k: None
    w2._open_project_path(ruta)
    assert len(w2.pipes) == n and w2.pipes == w.pipes
    from ui.comun import busy
    assert not busy.overlay_for(w).active and not busy.overlay_for(w2).active
    assert QtWidgets.QApplication.overrideCursor() is None
    for x in (w, w2):
        x._dirty = False; x.close()


def test_abrir_un_archivo_roto_no_toca_lo_abierto(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    pipes = list(w.pipes)
    malo = tmp_path / "malo.digproj"
    malo.write_bytes(b"no es un zip")
    errores = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: errores.append(a))
    w._dirty = False
    w._open_project_path(str(malo))
    assert errores and w.pipes == pipes
    from ui.comun import busy
    assert not busy.overlay_for(w).active
    w._dirty = False; w.close()


@pytest.mark.parametrize("_x", [0])
def test_texto_de_cada_etapa_se_traduce(_x):
    from ui.ventana import barras_carga as BC
    assert all("{i}" not in t or "{n}" in t for t in BC.TEXTOS_ARCHIVO.values())


def _contenido_xlsx(ruta):
    out = {}
    with zipfile.ZipFile(ruta) as z:
        for n in z.namelist():
            if not n.startswith("docProps/"):                  # (fecha de creación)
                out[n] = z.read(n)
    return out


def test_excel_con_su_barra_sale_igual(tmp_path):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from nucleo import tabla_excel
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    tablas = w._tablas_de_datos() + [tabla_excel.tabla_vertices(w.pipes, w._to_cad)]
    a, b = str(tmp_path / "a.xlsx"), str(tmp_path / "b.xlsx")
    tabla_excel.exportar(tablas, a)
    avisos = []
    with avance.escuchar(lambda t, i, n: avisos.append((t, i, n))):
        tabla_excel.exportar(tablas, b)
    assert _contenido_xlsx(a) == _contenido_xlsx(b)
    etapas = [t for t, _i, _n in avisos]
    assert {"excel_filas", "excel_formato", "excel_guardar"} <= set(etapas)
    assert avisos[-1][0] == "excel_guardar" and avisos[-1][1] == avisos[-1][2]
    from openpyxl.worksheet._writer import WorksheetWriter
    assert WorksheetWriter.write_row.__name__ == "write_row" and "contando" not in repr(WorksheetWriter.write_row)
    w._dirty = False; w.close()


def test_tabla_de_datos_y_limpieza_con_barra_que_llega_al_final(monkeypatch):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import barra_pesada, busy
    from ui.dialogos import limpieza_dialog, tabla_datos_dialog
    from ui.ventana.app_window import Main
    vistos = []
    original = barra_pesada.AvancePesado._mostrar
    monkeypatch.setattr(barra_pesada.AvancePesado, "_mostrar",
                        lambda self, pump: vistos.append((self.barra.milesimas, self._detalle)) or original(self, pump))
    monkeypatch.setattr(barra_pesada, "PINTAR_S", 0.0)
    w = Main(); w._info = lambda *a, **k: None
    w._open_project_path(ESC)
    vistos.clear()
    dlg = tabla_datos_dialog.TablaDatosDialog(w)
    mil = [m for m, _d in vistos]
    assert mil == sorted(mil) and mil[-1] == 1000
    assert any("Armando la tabla" in d for _m, d in vistos) and any("Ordenando" in d for _m, d in vistos)
    assert dlg.pestanas.count() == len(dlg.tablas) and not busy.overlay_for(w).active
    vistos.clear()
    monkeypatch.setattr(limpieza_dialog.LimpiezaDialog, "exec", lambda self: setattr(self, "accion", "cancelar"))
    antes = [dict(p) for p in w.pipes]
    w.revisar_dibujo()
    mil = [m for m, _d in vistos]
    assert mil and mil == sorted(mil) and mil[-1] == 1000 and w.pipes == antes     # (revisar no cambia nada)
    assert not busy.overlay_for(w).active and QtWidgets.QApplication.overrideCursor() is None
    dlg.close(); w._dirty = False; w.close()


def test_barra_del_calculo_de_fondo():
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana import calculo_avance
    from ui.ventana.app_window import Main
    w = Main(); w._info = lambda *a, **k: None
    av = calculo_avance.AvanceCalculo(w, 10000, [("cruces",), ("accesorios",)])
    bar = w._barra_calculo
    assert bar.isVisibleTo(w) and "Actualizando conflictos y avisos" in w.statusBar().currentMessage()
    av.aviso("cruces", ("detalle", "cruces", 500, 1000))
    m1 = av.barra.milesimas
    av.lista("cruces"); av.lista("accesorios")
    assert av.barra.milesimas > m1
    av.dibujando()
    assert "dibujando" in w.statusBar().currentMessage()
    av.cerrar()
    assert not bar.isVisibleTo(w) and not w.statusBar().currentMessage()
    w._dirty = False; w.close()
