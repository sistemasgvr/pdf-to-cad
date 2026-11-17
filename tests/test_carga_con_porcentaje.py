"""Toda carga muestra una barra de 0 a 100 % con su detalle, y la tarjeta no se queda quieta (pedido del usuario
2026-11-16: «cada acción, cada carga debe mostrar una barra de 0 a 100 %… si no el usuario cree que se quedó
bugeado»; «evitar que el programa se quede en No responde»).

- `nucleo/avance_aprendido`: la barra se reparte con lo que duró cada etapa la vez anterior, usa el «i de n» real,
  nunca retrocede y nunca llega al final antes de terminar;
- `ui/comun/busy`: la tarjeta pinta el porcentaje, lo aprende y lo recuerda;
- `ui/comun/vigia_carga`: un trabajo de Python que no avisa igual deja pintar la tarjeta.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from PySide6 import QtWidgets  # noqa: E402

from nucleo import avance_aprendido as AA  # noqa: E402
from ui.comun import busy, tiempos_carga, vigia_carga  # noqa: E402


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _carga(reloj, perfil, pasos):
    """Corre una carga simulada; `pasos` = [(segundos, texto, i, n)]. Devuelve (seguidor, fracciones)."""
    s = AA.Seguidor(perfil, reloj)
    vistas = []
    for seg, texto, i, n in pasos:
        s.etapa(texto, i, n)
        for _ in range(10):
            reloj.t += seg / 10.0
            vistas.append(s.fraccion())
    return s, vistas


def test_la_clave_de_una_etapa_no_depende_de_numeros_ni_nombres():
    assert AA.clave_de("Hoja 3 de 36 · «plano A.pdf» (1.234 px)") == AA.clave_de("Hoja 12 de 54 · «otro.pdf» (88 px)")
    assert AA.clave_de("Leyendo las capas…") != AA.clave_de("Dibujando la hoja…")


def test_primera_vez_avanza_sin_llegar_al_final_y_deja_un_perfil():
    reloj = Reloj()
    s, vistas = _carga(reloj, None, [(2.0, "Leyendo", None, None), (6.0, "Dibujando", None, None)])
    assert vistas == sorted(vistas) and 0 < vistas[0] and vistas[-1] < AA.SIN_PERFIL_TOPE
    perfil = s.cerrar()
    assert AA.perfil_valido(perfil) and abs(perfil["T"] - 8.0) < 1e-6
    assert [k for k, _d in perfil["etapas"]] == ["leyendo", "dibujando"]


def test_segunda_vez_la_barra_se_reparte_con_lo_que_duro_cada_etapa():
    reloj = Reloj()
    pasos = [(2.0, "Leyendo", None, None), (6.0, "Dibujando", None, None)]
    perfil = _carga(reloj, None, pasos)[0].cerrar()
    _s, vistas = _carga(reloj, perfil, pasos)
    assert vistas == sorted(vistas)
    assert abs(vistas[9] - 0.25) < 0.05            # al terminar «Leyendo» (2 de 8 s) va por el 25 %
    assert 0.55 < vistas[14] < 0.70                # a la mitad de «Dibujando»
    assert 0.9 < vistas[-1] <= AA.TOPE             # cerca del final, sin marcarlo


def test_una_etapa_con_cuenta_usa_la_cuenta_real_aunque_el_trabajo_sea_mucho_mas_largo():
    reloj = Reloj()
    perfil = _carga(reloj, None, [(1.0, "Abriendo", None, None)] + [
        (0.5, "Hoja", i, 4) for i in range(4)])[0].cerrar()
    # ahora 40 hojas y diez veces más lento: la barra sigue a la cuenta, no al reloj de la vez anterior
    s = AA.Seguidor(perfil, reloj)
    s.etapa("Abriendo")
    reloj.t += 1.0
    vistas = []
    for i in range(40):
        s.etapa("Hoja", i, 40)
        reloj.t += 5.0
        vistas.append(s.fraccion())
    assert vistas == sorted(vistas)
    assert 0.30 < vistas[0] < 0.42                 # «Abriendo» pesaba 1 de 3 s
    assert abs(vistas[19] - (1 / 3 + 2 / 3 * 0.5)) < 0.05      # hoja 20 de 40 = mitad de su parte
    assert vistas[-1] <= AA.TOPE


def test_entre_un_aviso_y_el_siguiente_la_barra_no_se_queda_quieta():
    reloj = Reloj()
    perfil = _carga(reloj, None, [(1.0, "Hoja", i, 4) for i in range(4)])[0].cerrar()
    s = AA.Seguidor(perfil, reloj)
    s.etapa("Hoja", 1, 4)
    a = s.fraccion()
    reloj.t += 0.5
    b = s.fraccion()
    reloj.t += 30.0                                 # el paso tarda muchísimo: avanza, pero no se pasa del siguiente
    c = s.fraccion()
    assert a < b < c < 0.5 + 1e-9


def test_una_etapa_nueva_no_frena_la_barra_ni_la_hace_retroceder():
    reloj = Reloj()
    perfil = _carga(reloj, None, [(2.0, "Leyendo", None, None), (2.0, "Dibujando", None, None)])[0].cerrar()
    s, vistas = _carga(reloj, perfil, [(2.0, "Leyendo", None, None), (3.0, "Otra cosa", None, None),
                                       (2.0, "Dibujando", None, None)])
    assert vistas == sorted(vistas) and vistas[19] > vistas[10] and vistas[-1] <= AA.TOPE


def test_carga_muy_corta_no_deja_perfil():
    reloj = Reloj()
    s = AA.Seguidor(None, reloj)
    reloj.t += 0.1
    assert s.cerrar() is None


# ── la tarjeta ────────────────────────────────────────────────────────────────
def _ventana():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = QtWidgets.QWidget()
    w.resize(800, 500)
    w.show()
    app.processEvents()
    return app, w


def _ocupar(seg):
    fin = time.perf_counter() + seg
    x = 0
    while time.perf_counter() < fin:               # Python puro, sin un solo aviso
        x += sum(i * i for i in range(500))
    return x


def test_la_tarjeta_muestra_el_porcentaje_y_lo_aprende_para_la_proxima(monkeypatch):
    app, w = _ventana()
    tiempos_carga.olvidar()
    ov = busy.overlay_for(w)
    titulo = "Carga de prueba del porcentaje…"

    def una():
        vistas = []
        with busy.busy(w, titulo, "Etapa uno") as b:
            _ocupar(0.5)
            vistas.append(ov.fraccion())
            b.step(detail="Etapa dos (1 de 2)", done=1, total=2)
            _ocupar(0.3)
            vistas.append(ov.fraccion())
        return vistas

    primera = una()
    assert 0 < primera[0] < primera[1] < 1
    assert AA.clave_de(titulo) in tiempos_carga._cargar()         # quedó aprendida
    segunda = una()
    assert segunda[0] > primera[0] and 0.4 < segunda[0] < 0.8     # «Etapa uno» pesa ~0.5 de 0.8 s
    assert segunda[1] > segunda[0]
    assert not ov.active and ov.fraccion() == 0.0
    w.close()


def test_el_vigia_pinta_la_tarjeta_aunque_el_trabajo_no_avise():
    app, w = _ventana()
    ov = busy.overlay_for(w)
    pinturas = []
    original = busy.BusyOverlay.paintEvent

    def contar(self, ev):
        pinturas.append(time.perf_counter())
        original(self, ev)

    busy.BusyOverlay.paintEvent = contar
    try:
        with busy.busy(w, "Carga de prueba del vigía…"):
            antes = len(pinturas)
            _ocupar(1.6)
            durante = len(pinturas) - antes
    finally:
        busy.BusyOverlay.paintEvent = original
    assert durante >= 3, durante                    # sin el vigía: 0 (nadie pinta hasta que el trabajo termina)
    huecos = [b - a for a, b in zip(pinturas, pinturas[1:])]
    assert max(huecos) < 1.0
    w.close()


def test_el_vigia_no_pinta_encima_de_una_pintura():
    """Con la ventana pintando (una función de pintar en la pila) el vigía espera a la próxima."""
    def paintEvent():                               # (el nombre es lo que mira el vigía)
        return vigia_carga.pintando_en_la_pila()

    def trabajo():
        return vigia_carga.pintando_en_la_pila()

    assert paintEvent() is True and trabajo() is False
