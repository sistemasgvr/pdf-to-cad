"""Reporte del cliente 2026-11-16 (Dell 16 Plus, Intel Arc 140V integrado, instalador): al abrir la Vista 3D salía
«OverflowError» al subir la escena a la tarjeta de video, el aviso volvía a salir en bucle al cerrarlo y en el registro
no había nada sobre su OpenGL. Ahora: el contexto OpenGL y el modo (instancing o respaldo, con su motivo) quedan en el
registro, un error al dibujar se anota una vez con su contexto, y la Vista 3D muestra el motivo sin repetir avisos."""
import os
import sys

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, RAIZ)

from PySide6 import QtWidgets  # noqa: E402


@pytest.fixture
def registro(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFCAD_DIAGNOSTICOS", str(tmp_path))
    from ui.comun import visor3d_diag as DG
    DG._anotados.clear()
    return tmp_path / f"sesion-{os.getpid()}.log"


class _Ctx:
    def __init__(self, v=(2, 1), ext=False):
        self.v, self.ext = v, ext

    def format(self):
        from PySide6 import QtGui
        f = QtGui.QSurfaceFormat()
        f.setVersion(*self.v)
        f.setProfile(QtGui.QSurfaceFormat.CompatibilityProfile)
        return f

    def hasExtension(self, _e):
        return self.ext


class _F:
    def glGetString(self, n):
        return {0x1F00: b"Intel", 0x1F01: b"Intel(R) Arc(TM) 140V GPU (16GB)",
                0x1F02: b"2.1.0 - Build 32.0.101.6083", 0x8B8C: b"1.20 - Build 32.0.101.6083"}[n]


def test_registro_dice_la_gpu_el_driver_y_por_que_no_hay_instancing(registro):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import visor3d_diag as DG
    from ui.comun import visor3d_instancias as VI
    ctx = _Ctx((2, 1), ext=False)
    info = DG.info_gl(ctx, _F())
    assert info["GPU"].startswith("Intel(R) Arc(TM) 140V") and info["versión obtenida"] == "2.1"
    assert "32.0.101.6083" in info["GL_VERSION (incluye el driver)"] and info["GL_ARB_instanced_arrays"] == "no"
    assert info["OpenGL por software"] == "no"
    DG.registrar_inicio(info, False, VI.motivo_no_soportado(ctx))
    log = registro.read_text(encoding="utf-8")
    assert "Vista 3D · OpenGL" in log and "Intel(R) Arc(TM) 140V" in log
    assert "respaldo" in log and "OpenGL 2.1 (hace falta 3.3)" in log


def test_un_error_al_dibujar_se_anota_una_vez_y_no_se_repite_en_cada_cuadro(registro, monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import visor3d_diag as DG
    from ui.comun.visor3d import Visor3D
    from nucleo import modelo3d as M3
    v = Visor3D()
    v._info_gl = {"GPU": "Intel(R) Arc(TM) 140V GPU"}
    v.f = None
    v._limpiar = lambda: None
    intentos = []

    def pintar():                                        # lo que hizo Qt en el equipo del cliente
        intentos.append(1)
        raise OverflowError("int too big to convert")
    monkeypatch.setattr(v, "_pintar", pintar)
    pts = np.zeros((3, 15), np.float32)
    esc = M3.Escena(base=pts, transparentes=pts[:0], suelo=pts[:0])
    v.set_escena(esc)
    avisos = []
    v.fallo.connect(avisos.append)
    for _ in range(30):                                  # cada repintado
        v.paintGL()
    QtWidgets.QApplication.processEvents()
    assert len(intentos) == 1 and len(avisos) == 1       # ni se reintenta en cada cuadro ni se avisa en bucle
    assert "demasiado grande" in avisos[0] and "sigue funcionando" in avisos[0] and str(registro) in avisos[0]
    log = registro.read_text(encoding="utf-8")
    assert log.count("Vista 3D · error al dibujar") == 1
    assert "OverflowError" in log and "Intel(R) Arc(TM) 140V" in log and "a subir a la GPU" in log
    v.set_escena(esc)                                    # otra escena: se vuelve a intentar (y no se anota de nuevo)
    v.paintGL()
    QtWidgets.QApplication.processEvents()
    assert len(intentos) == 2 and len(avisos) == 2
    assert registro.read_text(encoding="utf-8").count("Vista 3D · error al dibujar") == 1


def test_la_escena_se_sube_en_partes_de_triangulos_enteros_y_se_pide_opengl_33():
    """Segundo equipo de un cliente (2026-11-16, instalador 2.1.0): los dos cayeron al modo sin instancing y la escena
    de 29 000 utilidades (2.5 GB) pasaba el límite de Qt de 2 GB por bloque. Ahora va en partes; el dibujo es el
    mismo (comparado en una GPU real: idéntico píxel a píxel, en los dos modos)."""
    from ui.comun import visor3d as V
    paso = 60
    partes = V.partes_de(10_000, paso, 4096)
    assert partes[0] == (0, 66) and partes[-1][1] == 10_000
    assert all(b - a <= 4096 // paso and (b - a) % 3 == 0 for a, b in partes[:-1])
    assert all(partes[k][1] == partes[k + 1][0] for k in range(len(partes) - 1))     # sin huecos ni encimados
    grande = 2563 * 2 ** 20 // paso // 3 * 3                     # el proyecto del reporte, en el modo de respaldo
    assert all((b - a) * paso <= V.BLOQUE_MAX_BYTES < 2 ** 31 for a, b in V.partes_de(grande, paso, V.BLOQUE_MAX_BYTES))
    assert V.partes_de(0, paso, 4096) == []
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fmt = V.Visor3D().format()
    assert (fmt.majorVersion(), fmt.minorVersion()) == V.GL_PEDIDO == (3, 3)


def test_mensaje_segun_el_error():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun import visor3d_diag as DG
    grande = {"opacos": 3 * 2 ** 30}
    m = DG.mensaje(OverflowError("x"), grande, instancing=False)
    assert "demasiado grande" in m and "driver" in m
    assert "driver" not in DG.mensaje(OverflowError("x"), grande, instancing=True)
    assert "memoria" in DG.mensaje(MemoryError(), {}, True)
    assert "no pudo dibujar" in DG.mensaje(RuntimeError("?"), {}, True)
