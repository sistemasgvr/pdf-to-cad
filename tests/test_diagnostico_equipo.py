"""Diagnóstico del equipo (pedido del usuario 2026-11-17, tras el error de la Vista 3D del cliente —Intel Arc 140V sin
el modo rápido—): `--diagnostico` guarda en la carpeta del registro un .txt con todo lo que se pudo leer del equipo y
una prueba REAL de OpenGL con el formato de la Vista 3D; el código de salida dice si hay avisos."""
import os
import subprocess
import sys

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "app"))
MAIN = os.path.join(RAIZ, "app", "main.py")

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="lee el registro y WMI de Windows")


def _correr(tmp_path, **env_extra):
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}     # OpenGL de verdad, no «offscreen»
    env["PDFCAD_DIAGNOSTICOS"] = str(tmp_path)
    env.update(env_extra)
    res = tmp_path / "resumen.txt"
    r = subprocess.run([sys.executable, MAIN, "--diagnostico", "--resumen", str(res)], env=env,
                       capture_output=True, timeout=300)
    informes = list(tmp_path.glob("equipo-v*.txt"))
    assert len(informes) == 1, r.stderr.decode("utf-8", "replace")[-2000:]
    return r.returncode, informes[0].read_text(encoding="utf-8-sig"), res.read_text(encoding="utf-8-sig")


def test_diagnostico_guarda_el_informe_con_todas_las_secciones(tmp_path):
    codigo, texto, resumen = _correr(tmp_path)
    assert codigo in (0, 1, 2)
    for seccion in ("RESUMEN", "Aplicación", "Sistema operativo", "Equipo", "Procesador", "OpenGL (Vista 3D)",
                    "Memoria", "Tarjetas de video (Windows)", "Discos", "Antivirus", "AutoCAD / Civil 3D",
                    "Carpetas y procesos de la app", "Últimas sesiones del registro"):
        assert f"======= {seccion} =======" in texto, seccion
    assert "Vista 3D:" in resumen and "Informe completo:" in resumen
    # lo que hizo falta para entender el error del cliente: versión pedida/obtenida, GPU, driver e instancing
    for campo in ("versión pedida", "versión obtenida", "GPU", "GL_VERSION (incluye el driver)",
                  "GL_ARB_instanced_arrays", "Programa de instancias", "Subir un bloque de 256 MB"):
        assert campo in texto or "Contexto de la Vista 3D" in texto, campo


def test_sin_modo_rapido_avisa_y_sale_con_codigo_1(tmp_path):
    codigo, texto, resumen = _correr(tmp_path, PDFCAD_SIN_INSTANCING="1")
    if "no funcionará en este equipo" in resumen or "por software" in resumen:
        pytest.skip("este equipo no tiene OpenGL de verdad")
    assert "sin el modo rápido" in resumen and "Actualiza el driver" in resumen
    assert codigo >= 1


def test_resumen_y_codigo_segun_el_veredicto():
    import diagnostico_equipo as DE
    sec = [("OpenGL (Vista 3D)", [("GPU", "Intel(R) Arc(TM) 140V GPU (16GB)"),
                                  ("GL_VERSION (incluye el driver)", "2.1.0 - Build 32.0.101.6083")]),
           ("Carpetas y procesos de la app", [("Proceso de trabajo (spawn)", "sí")])]
    assert DE.codigo([s for s in DE.resumen(sec, "rapido") if "Memoria" not in s[1]]) == 0
    r = DE.resumen(sec, "respaldo")
    assert r[0][0] == DE.AVISO and "Intel(R) Arc(TM) 140V" in r[0][1] and DE.codigo(r) >= 1
    assert DE.codigo(DE.resumen(sec, "software")) == 2
    assert DE.codigo(DE.resumen(sec, "no")) == 2
    sec[1] = ("Carpetas y procesos de la app", [("Proceso de trabajo (spawn)", "NO (PermissionError)")])
    assert any("procesos de trabajo" in t for _s, t in DE.resumen(sec, "rapido"))


def test_la_app_lo_lanza_una_vez_por_version(tmp_path, monkeypatch):
    import diagnostico_equipo as DE
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    monkeypatch.delenv("PDFCAD_SIN_DIAGNOSTICO", raising=False)
    lanzados = []
    monkeypatch.setattr(DE.subprocess, "Popen", lambda *a, **k: lanzados.append(a[0]) or "proceso")
    assert DE.lanzar_si_falta() == "proceso" and "--diagnostico" in lanzados[0]
    (tmp_path / f"equipo-v{DE._version()}-20261117-100000.txt").write_text("x", encoding="utf-8")
    assert DE.lanzar_si_falta() is None and len(lanzados) == 1


def test_ayuda_abre_el_informe_con_copiar_y_carpeta(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.dialogos import diagnostico_dialog as D
    informe = tmp_path / "equipo-v2.1.0-x.txt"
    informe.write_text("Asistente C3D · Diagnóstico del equipo\n✔ Vista 3D: funcionará en modo rápido.\n", encoding="utf-8-sig")
    monkeypatch.setattr(D, "_correr", lambda: (str(informe), 0))
    vistos = []
    monkeypatch.setattr(D.DialogoDiagnostico, "exec", lambda self: vistos.append(self) or 0)
    monkeypatch.setattr(D.QtWidgets.QMessageBox, "warning", lambda *a, **k: pytest.fail(f"aviso inesperado: {a[2]}"))
    w = QtWidgets.QWidget()
    assert D.abrir(w) == str(informe)
    dlg = vistos[0]
    assert "modo rápido" in dlg.vista.toPlainText()
    dlg.copiar()
    assert "modo rápido" in app.clipboard().text()
