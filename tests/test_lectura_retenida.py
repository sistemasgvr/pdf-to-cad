"""Reconocer POR PARTES sobre una lectura RETENIDA de la hoja (plan 2026-11-16, «reconocimiento desde el editor»,
Tarea 3): cada ▶ del panel reconoce una utilidad, las válvulas, los diámetros o los rótulos con el MISMO código de
`recognition_trabajo.reconocer_hoja` y la lectura cruda de la hoja queda en el trabajador «reconocer» para el
siguiente. El resultado tiene que ser IDÉNTICO al de hoy."""
import os
import sys

import pytest

fitz = pytest.importorskip("pymupdf")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts", "rendimiento"))
import reconocer as foto_mod                                       # noqa: E402  (serializador de --foto)

from reconocimiento import lectura_retenida as LR                  # noqa: E402
from reconocimiento import recognition as rec                      # noqa: E402
from reconocimiento import recognition_trabajo as RT               # noqa: E402

DOCS = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos")
DU06 = os.path.join(DOCS, "docs prueba", "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")
DU08 = os.path.join(DOCS, "docs prueba", "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")
PHOENIX = os.path.join(DOCS, "DOCS DE PRUEBA IND", "QS Water_Indian School_South.pdf")
# (hoja «h.N» = índice N-1, como en el resto de las pruebas)
HOJAS = [(DU06, 2), (DU06, 3), (DU06, 4), (DU08, 21), (DU08, 25), (PHOENIX, 3)]
KW = dict(zoom=1.0, hidden_ocgs=(), roles_by_utility={}, letters_off=(), join_routes=True, scale_ft_per_pt=None)


def _o_saltar(ruta):
    if not os.path.exists(ruta):
        pytest.skip(f"no está {os.path.basename(ruta)}")
    return ruta


def _foto(results):
    """La foto de `scripts/rendimiento/reconocer.py --foto` + las válvulas y los rótulos completos."""
    out = foto_mod.foto_de(results)
    for r in results:
        d = out[str(r.utility)]
        d["valvulas_todo"] = repr(list(getattr(r, "valvulas", None) or []))
        d["anotaciones_todo"] = repr(list(getattr(r, "anotaciones", None) or []))
        d["grosor_todo"] = [repr(sorted((pl.grosor or {}).items())) for pl in r.polylines]
    return out


def _por_partes(ruta, hoja, utilidades, firma="f"):
    """Lo que hará el panel: cada utilidad, luego VALVULAS y DIAMETROS con las ya reconocidas."""
    results = []
    for u in utilidades:
        got = RT.reconocer_parte(ruta, hoja, u, firma, **KW)
        assert isinstance(got, list) and len(got) == 1
        results += got
    v = RT.reconocer_parte(ruta, hoja, "VALVULAS", firma, resultados_previos=results, **KW)
    assert set(v) == {"valvulas", "avisos"}
    RT.poner_valvulas(results, v)
    results = RT.reconocer_parte(ruta, hoja, "DIAMETROS", firma, resultados_previos=results, **KW)
    return results


@pytest.fixture(autouse=True)
def _soltar():
    LR.soltar()
    yield
    LR.soltar()


@pytest.mark.parametrize("ruta,hoja", HOJAS)
def test_parte_igual_que_hoja_entera(ruta, hoja):
    """Una utilidad sola por partes (su ▶, luego válvulas y diámetros) == `reconocer_hoja` de esa utilidad."""
    _o_saltar(ruta)
    for u in rec.SUPPORTED_UTILITIES:
        hoy = _foto(RT.reconocer_hoja(ruta, hoja, zoom=1.0, utilities=(u,)))
        assert _foto(_por_partes(ruta, hoja, (u,))) == hoy, (os.path.basename(ruta), hoja, u)


@pytest.mark.parametrize("ruta,hoja", [(DU06, 3), (DU08, 25), (PHOENIX, 3)])
def test_valvulas_y_diametros_como_hoy(ruta, hoja):
    """Todas las utilidades por partes + VALVULAS + DIAMETROS == `reconocer_hoja` con todas; y ROTULOS == los
    rótulos que hoy toma la importación (los del primer resultado que los trae)."""
    _o_saltar(ruta)
    hoy = RT.reconocer_hoja(ruta, hoja, zoom=1.0, utilities=tuple(rec.SUPPORTED_UTILITIES))
    partes = _por_partes(ruta, hoja, rec.SUPPORTED_UTILITIES)
    assert _foto(partes) == _foto(hoy)
    importados = next((list(r.anotaciones) for r in hoy if r.anotaciones), [])
    solos = RT.reconocer_parte(ruta, hoja, "ROTULOS", "otra", **KW)            # sin utilidades reconocidas
    assert repr(solos["anotaciones"]) == repr(importados)
    con = RT.reconocer_parte(ruta, hoja, "ROTULOS", "otra", resultados_previos=partes, **KW)
    assert repr(con["anotaciones"]) == repr(importados)


def test_segundo_parte_no_relee(monkeypatch):
    _o_saltar(DU06)
    lecturas = []
    original = fitz.Page.get_drawings

    def contar(self, *a, **k):
        lecturas.append(self.number)
        return original(self, *a, **k)
    monkeypatch.setattr(fitz.Page, "get_drawings", contar)
    RT.reconocer_parte(DU06, 3, "DRENAJE", "f1", **KW)
    assert lecturas, "la primera parte lee la hoja"
    lecturas.clear()
    RT.reconocer_parte(DU06, 3, "ELECTRICO", "f1", **KW)
    assert lecturas == [], "la 2.ª parte con la misma firma reusa la lectura"
    RT.reconocer_parte(DU06, 3, "ELECTRICO", "f2", **KW)                     # otra firma: otra lectura
    assert lecturas


def test_otra_firma_suelta_la_anterior():
    _o_saltar(DU06)
    a = LR.abrir(DU06, "f1")
    assert LR.abrir(DU06, "f1") is a
    b = LR.abrir(DU06, "f2")
    assert b is not a and a.is_closed
    LR.soltar()
    assert b.is_closed and LR.retenida() is None


def test_las_capas_vuelven_como_al_abrir():
    """La interpretación deja todas las capas encendidas; cada parte arranca con el estado de un `fitz.open`."""
    _o_saltar(DU06)
    from hoja import interpretar_trabajo as IT, pdf_layers
    with fitz.open(DU06) as d:
        inicial = pdf_layers.encendidas(d)
    IT.interpretar(DU06, 3, firma="f1", escala=0.1)
    doc = LR.abrir(DU06, "f1")
    LR.reponer(doc)
    assert pdf_layers.encendidas(doc) == inicial
    assert getattr(doc, "_pdf_style_hidden", None) is None


def test_interpretar_y_partes_igual_que_hoy():
    """Interpretar (todas las capas encendidas) y luego reconocer con la MISMA lectura == hoy."""
    _o_saltar(DU06)
    from hoja import interpretar_trabajo as IT
    hoy = RT.reconocer_hoja(DU06, 4, zoom=1.0, utilities=("TELECOM", "DRENAJE"))
    IT.interpretar(DU06, 4, firma="f1", escala=None)
    assert LR.retenida() == "f1"
    assert _foto(_por_partes(DU06, 4, ("TELECOM", "DRENAJE"), firma="f1")) == _foto(hoy)


def test_con_capas_ocultas_roles_y_letras_igual_que_hoy():
    """Capas ocultas, roles puestos a mano y letras apagadas, y entre partes otras capas ocultas (la lectura
    retenida no arrastra nada de una parte a la siguiente)."""
    _o_saltar(DU06)
    from hoja import pdf_layers
    with fitz.open(DU06) as d:
        nombres = [L["name"] for L in pdf_layers.page_layers(d, 3) if L.get("path_count")]
    ocultas = tuple(n for n in nombres if "STRM" in n)[:2]
    elec = [n for n in nombres if "ELEC" in n and "UNGD" in n][:1]
    assert ocultas and elec
    roles = {"ELECTRICO": {rec.ROLE_LINEAS: elec, rec.ROLE_BUZONES: []}}
    kw = dict(KW, hidden_ocgs=ocultas, roles_by_utility=roles, letters_off=("G-XREF",))
    RT.reconocer_parte(DU06, 3, "DRENAJE", "f", **KW)                      # otra combinación antes
    for u in ("ELECTRICO", "DRENAJE", "TELECOM"):
        hoy = RT.reconocer_hoja(DU06, 3, zoom=1.0, utilities=(u,), hidden_ocgs=ocultas, roles_by_utility=roles,
                                letters_off=("G-XREF",))
        res = RT.reconocer_parte(DU06, 3, u, "f", **kw)
        v = RT.reconocer_parte(DU06, 3, "VALVULAS", "f", resultados_previos=res, **kw)
        RT.poner_valvulas(res, v)
        res = RT.reconocer_parte(DU06, 3, "DIAMETROS", "f", resultados_previos=res, **kw)
        assert _foto(res) == _foto(hoy), u


# ── el trabajador «reconocer» de verdad (Review Focus 2) ────────────────────────────────────────────────
@pytest.fixture
def con_proceso(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from ui.comun import proceso
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setenv("PDFCAD_PROCESO", "1")
    yield proceso
    proceso.trabajador("reconocer").parar()


def _en_proceso(proceso, parte, firma="f", **extra):
    kw = dict(KW, **extra)
    res, err = proceso.ejecutar("reconocimiento.recognition_trabajo:reconocer_parte",
                                DU06, 3, parte, firma, nombre="reconocer", **kw)
    assert err == "", err
    return res


def test_trabajador_muerto_relee_igual(con_proceso):
    _o_saltar(DU06)
    proceso = con_proceso
    t = proceso.trabajador("reconocer")
    a = _en_proceso(proceso, "DRENAJE")
    assert not t.recicla(), "con una lectura retenida el trabajador no se recicla"
    t._matar()                                       # memoria, cancelar…: la lectura se pierde
    assert t.recicla()
    b = _en_proceso(proceso, "DRENAJE")
    c = _en_proceso(proceso, "DRENAJE")              # ya retenida
    assert _foto(a) == _foto(b) == _foto(c)
    # y lo mismo que esa parte aquí mismo, sin proceso ni lectura retenida antes
    LR.soltar()
    assert _foto(RT.reconocer_parte(DU06, 3, "DRENAJE", "f", **KW)) == _foto(a)
    tarea = proceso.soltar_lectura()
    assert tarea is not None
    from PySide6 import QtCore
    lazo = QtCore.QEventLoop()
    tarea.terminado.connect(lambda r, e: lazo.quit())
    if not tarea.hecha:
        QtCore.QTimer.singleShot(60000, lazo.quit)
        lazo.exec()
    assert t.recicla()


def test_otro_trabajador_no_deja_de_reciclarse(con_proceso):
    """Retener la lectura es cosa del trabajador «reconocer»: `interpretar` en «principal» no le cambia el
    reciclado (si no, ~1 GB quedaba sin soltar y «principal» no volvía a reciclarse)."""
    _o_saltar(DU06)
    proceso = con_proceso
    t = proceso.trabajador("principal")
    try:
        res, err = proceso.ejecutar("hoja.interpretar_trabajo:interpretar", DU06, 3, firma="f1", escala=0.1,
                                    nombre="principal")
        assert err == "", err
        assert res["firma"] == "f1"
        assert t.recicla() and not t._retiene
    finally:
        t.parar()
