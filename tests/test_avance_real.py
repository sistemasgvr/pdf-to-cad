"""Toda barra de 0 a 100 % dice un avance REAL (pedido del usuario 2026-11-17: «si nos informan un porcentaje de 0 a 100
que está cargando, tiene que ser todo real»; la tarjeta del reconocimiento decía «Vista provisional · N %» y en la
hoja compuesta de DU06 marcaba 93–99 % a un cuarto del tiempo).

- `nucleo/avance_aprendido.Seguidor`: dice cómo se midió la cifra (`medida`), sin historia no se dispara, una etapa
  sin cuenta se estima con la velocidad de ESTA carga y entre dos avisos no se adelanta a la cuenta;
- quien avisa «i de n» manda lo YA hecho y «n de n» solo al terminar (antes, i+1 al EMPEZAR: la barra marcaba la etapa
  entera antes de hacerla);
- `recognize_page` pesa cada capa por sus trazos y avisa el ajuste de las rutas y los diámetros como etapas propias;
- la tarjeta del reconocimiento: «42 %» con cuenta real, «≈ 42 %» si es una estimación; lo que viene después de las
  capas es otra etapa, no «capas» con la cuenta de la última.
"""
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
AQUI = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(AQUI, "..", "app"))

from nucleo import avance  # noqa: E402
from nucleo import avance_aprendido as AA  # noqa: E402

ESC = os.path.join(AQUI, "escenarios", "cruces", "escenarios_prueba.digproj")
DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ── el seguidor ────────────────────────────────────────────────────────────────
def test_sin_historia_una_carga_larga_no_marca_casi_el_final_a_la_mitad():
    r = Reloj()
    s = AA.Seguidor(None, r)
    s.etapa("Leyendo")
    r.t = 60.0                                     # a la mitad de una carga de 2 minutos
    assert s.fraccion() < 0.75 and s.medida() == "tiempo"     # (antes: 89 %)


def test_la_cifra_dice_como_se_midio():
    r = Reloj()
    s = AA.Seguidor(None, r)
    s.etapa("Leyendo"); r.t += 1.0
    s.etapa("Hoja", 0, 4); r.t += 1.0
    perfil = s.cerrar()
    s = AA.Seguidor(perfil, r)
    s.etapa("Leyendo")
    assert s.medida() == "perfil"                 # sin cuenta: lo que duró la vez anterior (≈)
    s.etapa("Hoja", 1, 4)
    assert s.medida() == "cuenta"
    s.etapa("Algo que la vez anterior no estuvo")
    assert s.medida() == "tiempo"


def test_etapa_sin_cuenta_se_estima_con_la_velocidad_de_esta_carga():
    """Perfil de una hoja suelta (1 s + 1 s); ahora una compuesta diez veces más lenta: a la mitad de la etapa sin
    cuenta la barra no puede estar casi al final (antes: 99 %)."""
    r = Reloj()
    s = AA.Seguidor(None, r)
    s.etapa("Capas", 0, 4)
    for i in range(1, 5):
        r.t += 0.25
        s.etapa("Capas", i, 4)
    s.etapa("Diámetros"); r.t += 1.0
    perfil = s.cerrar()
    s = AA.Seguidor(perfil, r)
    for i in range(5):
        s.etapa("Capas", i, 4)
        r.t += 2.5 if i < 4 else 0.0
    s.etapa("Diámetros")
    r.t += 5.0                                     # la mitad de sus 10 s
    assert s.fraccion() < 0.85


def test_un_paso_largo_no_adelanta_la_barra_a_la_cuenta():
    """Telecom de la compuesta de DU06: 8 capas chicas en 0.2 s y la última (62 % de los trazos) 5 s. Entre un aviso
    y el siguiente la barra no pasa de un paso medio más allá de lo contado."""
    r = Reloj()
    s = AA.Seguidor(None, r)
    s.etapa("Capas", 0, 100); r.t += 1.0
    s.etapa("Capas", 100, 100)
    perfil = s.cerrar()
    s = AA.Seguidor(perfil, r)
    for h in (0, 5, 10, 20, 38):
        s.etapa("Capas", h, 100)
        r.t += 0.02
    r.t += 30.0                                    # la capa grande tarda muchísimo
    assert s.fraccion() <= 0.38 + 0.9 * 38 / 4 / 100 + 1e-6


def test_nunca_retrocede_ni_llega_al_final_antes_de_terminar():
    r = Reloj()
    perfil = {"T": 2.0, "etapas": [[AA.INICIO, 0.1], ["a", 0.9], ["b", 1.0]]}
    s = AA.Seguidor(perfil, r)
    vistas = []
    for texto, i, n in (("a", None, None), ("otra", None, None), ("b", 0, 3), ("b", 3, 3)):
        s.etapa(texto, i, n)
        for _ in range(20):
            r.t += 1.0
            vistas.append(s.fraccion())
    assert vistas == sorted(vistas) and vistas[-1] <= AA.TOPE < 1.0


# ── «i de n» = lo YA hecho ─────────────────────────────────────────────────────
def _escenario():
    m = json.loads(zipfile.ZipFile(ESC).read("model.json"))
    return m["pipes"], m["structures"]


def _avisos(fn):
    vistos = []
    with avance.escuchar(lambda t, i, n: vistos.append((t, i, n))):
        fn()
    return vistos


def _empieza_en_cero_y_termina_en_n(vistos, texto):
    mios = [(i, n) for t, i, n in vistos if t == texto and n]
    assert mios, texto
    assert mios[0][0] == 0, (texto, mios[:3])                # al empezar no hay nada hecho (antes: 1 de n)
    assert mios[-1][0] == mios[-1][1], (texto, mios[-3:])     # «n de n» al terminar
    assert all(a[0] <= b[0] for a, b in zip(mios, mios[1:]))


@pytest.mark.skipif(not os.path.isfile(ESC), reason="escenario no disponible")
def test_limpieza_y_tablas_avisan_lo_ya_hecho():
    from nucleo import limpieza, quiebres_curvas, tabla_excel
    pipes, structures = _escenario()
    vistos = _avisos(lambda: limpieza.limpiar(pipes, structures, 0.1))
    for etapa in ("duplicadas", "puntas", "tramos", "sueltas"):
        _empieza_en_cero_y_termina_en_n(vistos, etapa)
    vistos = _avisos(lambda: tabla_excel.tabla_vertices(pipes, lambda x, y: (x, y)))
    _empieza_en_cero_y_termina_en_n(vistos, "tabla_vertices")
    pipes, structures = _escenario()
    vistos = _avisos(lambda: quiebres_curvas.curvas_en_quiebres(pipes, structures, 0.1))
    _empieza_en_cero_y_termina_en_n(vistos, vistos[0][0])


# ── el reconocimiento ──────────────────────────────────────────────────────────
@pytest.mark.skipif(not DU06.is_file(), reason="PDF DU06 no disponible")
def test_reconocer_pesa_las_capas_por_sus_trazos_y_avisa_cada_etapa():
    from reconocimiento import recognition_trabajo as RT
    from traduccion.i18n_core import t as _tr
    eventos = []
    vistos = _avisos(lambda: RT.reconocer_parte(str(DU06), 3, "TELECOM", "prueba-avance", zoom=1.0,
                                                roles_by_utility={}, progreso=lambda *a: eventos.append(a)))
    capas = [a for a in eventos if a[0] == "capa"]
    m = capas[0][5]
    assert [a[4] for a in capas] == list(range(m + 1))       # 0 … m: el último, al TERMINAR la última capa
    hechos = [a[6] for a in capas]
    assert hechos[0] == 0 and hechos == sorted(hechos) and hechos[-1] == capas[-1][7] > m   # trazos, no capas
    _empieza_en_cero_y_termina_en_n(vistos, _tr("Uniendo las líneas en rutas y ajustando sus curvas…"))
    assert any(t == _tr("Leyendo los diámetros y rótulos del plano…") for t, _i, _n in vistos)


def test_tarjeta_dice_si_la_cifra_es_real_o_estimada(qapp=None):
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.comun.busy import cifra
    assert cifra(0.42, "cuenta") == "42 %"
    assert cifra(0.42, "perfil") == "≈ 42 %" and cifra(0.42, "tiempo") == "≈ 42 %"
    assert cifra(1.3, "cuenta") == "100 %"


def test_lo_que_sigue_a_las_capas_no_es_la_etapa_capas():
    """Antes, todo aviso posterior a la primera capa seguía en la etapa «capas» con la cuenta de la última: la barra
    marcaba 8 de 9 capas mientras faltaban tres cuartos del trabajo."""
    from ui.ventana.ventana_reconocer_cola import ReconocerColaMixin

    class Tarjeta:
        def __init__(self):
            self.pasos = []

        def step(self, **kw):
            self.pasos.append(kw)

    class Ventana(ReconocerColaMixin):
        _recog_linea = "Telecom · capa 9 de 9"

    w, card = Ventana(), Tarjeta()
    w._rec_etapa(card, "Reconstruyendo las líneas de la capa N-COMM…", 631, 1664)
    assert card.pasos[-1]["clave"] == "capas" and "done" not in card.pasos[-1]     # la cuenta es la de los trazos
    w._rec_etapa(card, "Uniendo las líneas en rutas y ajustando sus curvas…", 50, 1664)
    assert "clave" not in card.pasos[-1] and card.pasos[-1]["done"] == 50 and card.pasos[-1]["total"] == 1664
    w._rec_etapa(card, "Midiendo las bóvedas y buzones y uniendo sus líneas…", None, None)
    assert "clave" not in card.pasos[-1] and card.pasos[-1]["total"] is None


def test_hoja_compuesta_avisa_lo_ya_hecho():
    import pymupdf as fitz
    from hoja import composite as C
    from traduccion.i18n_core import t as _tr
    doc = fitz.open()
    for _ in range(3):
        pg = doc.new_page(width=300, height=200)
        pg.draw_line((10, 100), (290, 100))
    comp = C.Composite(pieces=[C.Piece(source=0, page=k, clip=[0, 0, 1, 1], x=300 * k) for k in range(3)])
    vistos = _avisos(lambda: C.compute_bridges(comp, [doc]))
    _empieza_en_cero_y_termina_en_n(vistos, _tr("Buscando las líneas que cruzan cada costura…"))
    vistos = _avisos(lambda: C.build_document(comp, [doc]))
    _empieza_en_cero_y_termina_en_n(vistos, _tr("Copiando cada hoja con sus vectores, capas y textos…"))
