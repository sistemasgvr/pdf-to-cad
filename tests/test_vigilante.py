"""Vigilante de tiempos y congelamientos (`nucleo/vigilante.py`, pedido del usuario 2026-11-20)."""
import os
import sys
import threading
import time

import pytest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nucleo import avance, vigilante as V, vigilante_informe as VI, vigilante_sistema as VS  # noqa: E402


@pytest.fixture
def sesion(tmp_path, monkeypatch):
    V.desactivar()
    monkeypatch.delenv(V.ENV_CARPETA, raising=False)
    monkeypatch.setattr(V, "base", lambda: str(tmp_path / "rendimiento"))
    assert V.activar("ventana", nueva_sesion=True)
    yield V.carpeta()
    V.desactivar()


def _sucesos(carpeta, tipo=None):
    V._vaciar()
    return [e for e in VI.leer(carpeta) if tipo is None or e["tipo"] == tipo]


def _ocupado(s):
    fin = time.perf_counter() + s
    x = 0
    while time.perf_counter() < fin:
        x += 1
    return x


def test_sin_sesion_un_proceso_hijo_no_anota_nada(monkeypatch, tmp_path):
    V.desactivar()
    monkeypatch.delenv(V.ENV_CARPETA, raising=False)
    assert not V.activar("trabajador")
    with V.medir("algo"), V.trabajo("x:y"):
        avance.avisar("etapa")
    assert not V.activo()


def test_etapas_y_bloques_con_su_duracion_y_donde_iban(sesion):
    with V.medir("Reconocer utilidad", utilidad="AGUA"):
        avance.avisar("Leyendo los trazos…")
        time.sleep(0.05)
        avance.avisar("Leyendo los trazos…", 1, 3)       # misma etapa
        avance.avisar("Uniendo las líneas…")
        time.sleep(0.02)
    etapas = _sucesos(sesion, "etapa")
    assert [e["texto"] for e in etapas] == ["Leyendo los trazos…", "Uniendo las líneas…"]
    assert etapas[0]["dur"] >= 0.04 and etapas[0]["i"] == 1 and etapas[0]["n"] == 3
    assert all(e["dentro"] == "Reconocer utilidad · AGUA" for e in etapas)
    (b,) = _sucesos(sesion, "bloque")
    assert b["nombre"] == "Reconocer utilidad" and b["utilidad"] == "AGUA" and b["dur"] >= 0.06


def test_trabajo_con_perfil_que_dice_en_que_funcion_se_fue_el_tiempo(sesion):
    with V.trabajo("reconocimiento.recognition_trabajo:reconocer_hoja", tid=1):
        _ocupado(0.3)
    (t,) = _sucesos(sesion, "trabajo")
    assert t["dur"] >= 0.29 and t["mem_antes_mb"] >= 0
    propio = dict(t["perfil"]["propio"])
    assert any(n.endswith(":_ocupado") for n in propio)
    assert max(propio, key=propio.get).endswith(":_ocupado")
    r = VI.resumir(VI.leer(sesion))
    assert r["perfil_reconocer_propio"][0][0].endswith(":_ocupado")


def test_la_guardia_anota_un_congelamiento_con_la_funcion_que_trababa(sesion, monkeypatch):
    monkeypatch.setattr(V, "SISTEMA_S", 0.2)
    monkeypatch.setattr(V.Guardia, "USAR_VOLCADOS", True)    # (opcional: aquí se prueba esa fuente)
    g = V.Guardia(threading.get_ident()).iniciar()
    try:
        V.poner_carga("Armando la hoja compuesta…")
        for _ in range(10):                 # latiendo: nada que anotar
            g.latido()
            time.sleep(0.03)
        _trabar_la_ventana(0.6)
        g.latido()
        time.sleep(0.1)
        g.latido()
    finally:
        g.parar()
    (c,) = _sucesos(sesion, "congelamiento")
    assert 0.4 <= c["dur"] <= 1.0 and not c["no_responde"]
    assert c["carga"] == "Armando la hoja compuesta…"
    assert any(n.endswith(":_trabar_la_ventana") for n, _v in c["perfil"]["total"])
    sis = _sucesos(sesion, "sistema")
    assert sis and any(p["pid"] == os.getpid() for p in sis[0]["procesos"])


def _trabar_la_ventana(s):
    _ocupado(s)


def test_medidor_ve_este_proceso_y_sus_hijos():
    import subprocess
    hijo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        time.sleep(0.3)
        m = VS.Medidor()
        m.medir()
        d = m.medir()
        pids = {p["pid"] for p in d["procesos"]}
        assert os.getpid() in pids
        if os.name == "nt":
            assert hijo.pid in pids
            yo = next(p for p in d["procesos"] if p["pid"] == os.getpid())
            assert yo["priv_mb"] > 10 and yo["cpu_pct"] is not None
            assert d["ram_total_mb"] > d["ram_libre_mb"] > 0
    finally:
        hijo.kill()


def test_instrumentar_mide_un_metodo_sin_cambiar_lo_que_devuelve(sesion):
    class C:
        def paso(self, x, y=1):
            return x + y
    assert V.instrumentar(C, ["paso", "no_existe"]) == ["paso"]
    assert C().paso(2, y=3) == 5
    (b,) = _sucesos(sesion, "bloque")
    assert b["nombre"] == "paso"


def test_trabajador_real_anota_en_la_misma_sesion(sesion, monkeypatch):
    """La ventana deja la sesión en el entorno: el proceso trabajador escribe su propio archivo en la misma
    carpeta, con el trabajo y su perfil; la ventana anota el encargo (espera y duración)."""
    from PySide6 import QtCore, QtWidgets
    from ui.comun import proceso
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    tr = proceso.Trabajador("prueba")
    try:
        out = {}
        lazo = QtCore.QEventLoop()
        t = proceso.Tarea("ui.comun.proceso_hijo:eco", ("hola",), {"pasos": 2})
        t.terminado.connect(lambda r, e: (out.update(r=r, e=e), lazo.quit()))
        tr.enviar(t)
        QtCore.QTimer.singleShot(60000, lazo.quit)
        lazo.exec()
        assert out["e"] == ""
        pid = out["r"][1]
    finally:
        tr.parar()
    ev = VI.leer(sesion)
    inicio = [e for e in ev if e["tipo"] == "inicio" and e["pid"] == pid]
    assert inicio and inicio[0]["nombre"] == "pdfcad-prueba"
    trabajo = [e for e in ev if e["tipo"] == "trabajo" and e["pid"] == pid]
    assert trabajo and trabajo[0]["objetivo"] == "ui.comun.proceso_hijo:eco"
    (enc,) = [e for e in ev if e["tipo"] == "encargo"]
    assert enc["estado"] == "ok" and enc["trabajador"] == "prueba" and enc["total"] >= enc["dur"] >= 0


def test_informe_y_comparacion(sesion):
    with V.medir("Importar"):
        time.sleep(0.02)
    V.poner_carga("Abriendo el PDF…")
    V.poner_carga("", fin_dur=1.5)
    V._vaciar()
    a = VI.resumir(VI.leer(sesion))
    md = VI.markdown(a)
    assert "Importar" in md and "Abriendo el PDF" in md and "## Congelamientos" in md
    b = dict(a, bloques=[dict(x, media=x["media"] / 2) for x in a["bloques"]])
    comp = VI.comparar(a, b)
    assert "Importar" in comp and "-50 %" in comp


def test_sesiones_viejas_se_borran(tmp_path, monkeypatch):
    V.desactivar()
    monkeypatch.setattr(V, "base", lambda: str(tmp_path))
    monkeypatch.setattr(V, "MAX_SESIONES", 3)
    for i in range(5):
        os.makedirs(tmp_path / f"2026010{i}-000000-1")
    assert V.activar("ventana", nueva_sesion=True)
    V.desactivar()
    assert len(os.listdir(tmp_path)) == 3


def _regex_lento():
    import re
    return re.match(r"(a+)+$", "a" * 26 + "b")     # ~1.5 s dentro de C sin soltar el intérprete


def test_congelamiento_dentro_de_c_con_el_interprete_tomado(sesion, monkeypatch):
    """Una llamada larga en C (como PyMuPDF dibujando) no deja correr al hilo de muestreo: la pausa la mide el
    latido y DÓNDE estaba lo dicen los volcados de `faulthandler` (opcionales: `USAR_VOLCADOS`)."""
    monkeypatch.setattr(V.Guardia, "USAR_VOLCADOS", True)
    g = V.Guardia(threading.get_ident()).iniciar()
    try:
        for _ in range(6):
            g.latido()
            time.sleep(0.03)
        t0 = time.perf_counter()
        _regex_lento()
        trabado = time.perf_counter() - t0
        g.latido()
        time.sleep(0.15)
        g.latido()
    finally:
        g.parar()
    (c,) = _sucesos(sesion, "congelamiento")
    assert abs(c["dur"] - trabado) < 0.15
    assert c["fuente"] == "volcados"
    assert any(n.endswith(":_regex_lento") for n, _v in c["perfil"]["total"])


def test_leer_volcados_de_faulthandler():
    texto = ("Timeout (0:00:00.300000)!\n"
             "Thread 0x0000000000001234 (most recent call first):\n"
             '  File "C:\\x\\otro.py", line 3 in espera\n\n'
             "Current thread 0x00000000000000ff (most recent call first):\n"
             '  File "C:\\x\\lento.py", line 10 in calcular\n'
             '  File "C:\\x\\main.py", line 2 in main\n')
    (p,) = V.leer_volcados(texto, 0xff)
    assert p[0].endswith(":calcular") and p[1].endswith(":main")


def test_el_vigilante_no_vuelca_pilas_desde_otro_hilo_por_defecto():
    """2026-11-21: `faulthandler.dump_traceback_later` leía las pilas sin el GIL y la app se cerraba sola (access
    violation en `python314.dll`) en las pausas largas: apagado salvo `PDFCAD_VIGILANTE_VOLCADOS=1`."""
    import faulthandler
    assert V.Guardia.USAR_VOLCADOS is False
    g = V.Guardia(0)
    llamadas = []
    original = faulthandler.dump_traceback_later
    faulthandler.dump_traceback_later = lambda *a, **k: llamadas.append(a)
    try:
        g._armado = 0.0
        g.latido()
        g.latido()
    finally:
        faulthandler.dump_traceback_later = original
    assert llamadas == []
