"""IA que sugiere el diámetro del plano (spec docs/superpowers/specs/2026-10-29-ia-diametro-plano-design.md):
evidencia del reconocimiento (`recognition_grosor_cerca`), proveedor con imágenes, petición/lectura/comprobación
(`ia/diametro_ia`) y recorte marcado (`hoja/recorte_diametro`)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from nucleo import diametro_plano  # noqa: E402
from reconocimiento import recognition_grosor as G  # noqa: E402
from reconocimiento import recognition_grosor_cerca as C  # noqa: E402
from reconocimiento.recognition_grosor_texto import Rotulo  # noqa: E402

DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


def _rot(texto, pulg, x, y, util="", material="", bloque=-1, **k):
    return Rotulo(texto, pulg, (x, y, x + 40.0, y + 6.0), 6.0, util, material, bloque, **k)


# ── Tarea 1: evidencia `cerca` ─────────────────────────────────────────
LINEA = [(0.0, 0.0), (200.0, 0.0)]
OTRA = [(0.0, 50.0), (200.0, 50.0)]


def test_cerca_rotulo_con_guia_a_la_linea():
    r = _rot('18" RCP SD', 18.0, 60.0, -30.0, util="DRENAJE", material="RCP")
    hoja = G.Hoja([r], [(r, [(70.0, -24.0), (80.0, 0.0)], (80.0, 0.0))], [], [None])
    out = C.cerca(LINEA, hoja, "DRENAJE", 1.0, 1.0 / 12.0)
    assert len(out) == 1
    e = out[0]
    assert (e["id"], e["guia"], e["diam_in"], e["util"], e["es_de"]) == ("R1", "esta", 18.0, "DRENAJE", True)
    assert e["dist_pt"] == pytest.approx(0.0)
    assert e["caja"] == list(r.bbox)


def test_cerca_rotulo_que_apunta_a_otra():
    r = _rot('8" W', 8.0, 60.0, 20.0, util="AGUA")
    hoja = G.Hoja([r], [(r, [(70.0, 26.0), (80.0, 50.0)], (80.0, 50.0))], [], [None])
    out = C.cerca(LINEA, hoja, "AGUA", 1.0, 1.0 / 12.0, otras=[(OTRA, "C-WATR-UNGD-E")])
    assert out[0]["guia"] == "otra"
    assert out[0]["otra"]["capa"] == "C-WATR-UNGD-E"


def test_cerca_guia_sobre_tinta_de_otra_utilidad():
    r = _rot('84" RCP', 84.0, 60.0, 20.0, material="RCP")
    hoja = G.Hoja([r], [(r, [(70.0, 26.0), (80.0, 40.0)], (80.0, 40.0))], [], ["DRENAJE"])
    out = C.cerca(LINEA, hoja, "AGUA", 1.0, 1.0 / 12.0)
    assert out[0]["guia"] == "otra" and out[0]["otra"]["utilidad"] == "DRENAJE"
    assert out[0]["es_de"] is False


def test_cerca_respeta_max_y_orden():
    rots = [_rot(f'{6 + k}" W', 6.0 + k, 10.0 * k, 5.0 + 4.0 * k) for k in range(12)]
    hoja = G.Hoja(rots, [], [], [])
    out = C.cerca(LINEA, hoja, "AGUA", 1.0, 1.0 / 12.0)
    assert len(out) == C.MAX_CERCA
    assert [e["id"] for e in out] == [f"R{k + 1}" for k in range(C.MAX_CERCA)]
    assert [e["dist_pt"] for e in out] == sorted(e["dist_pt"] for e in out)
    assert all(e["guia"] == "sin" for e in out)


def test_cerca_lejos_no_cuenta():
    r = _rot('8" W', 8.0, 60.0, C.CERCA_PT + 50.0)
    assert C.cerca(LINEA, G.Hoja([r], [], [], []), "AGUA", 1.0, 1.0 / 12.0) == []


def test_cerca_junta_el_bloque():
    a = _rot("LAT CB-226", 18.0, 60.0, -30.0, bloque=3)
    b = _rot('18" RCP', 18.0, 60.0, -22.0, bloque=3)
    out = C.cerca(LINEA, G.Hoja([a, b], [], [], []), "DRENAJE", 1.0, 1.0 / 12.0)
    assert out[0]["texto"] == 'LAT CB-226 / 18" RCP'


def test_de_grosor_copia_cerca():
    g = {"estado": "sin_dato", "cerca": [{"id": "R1", "diam_in": 8.0}]}
    assert diametro_plano.de_grosor(g)["cerca"] == [{"id": "R1", "diam_in": 8.0}]


@pytest.mark.skipif(not DU06.is_file(), reason="DU06 no disponible")
def test_du06_cerca_no_cambia_estados():
    """Foto tomada ANTES de agregar `cerca` (DU06 hoja índice 3, 6 utilidades): mismos estados y diámetros."""
    os.environ.setdefault("PDFCAD_PROCESO", "0")
    from collections import Counter
    from reconocimiento import recognition_trabajo as RT
    res = RT.reconocer_hoja(str(DU06), 3, zoom=1.0,
                            utilities=("DRENAJE", "AGUA", "ALCANTARILLADO", "GAS", "ELECTRICO", "TELECOM"))
    foto = {r.utility: [dict(Counter((p.grosor or {}).get("estado", "-") for p in r.polylines)),
                        sorted(p.diam_in for p in r.polylines if p.diam_in)] for r in res}
    assert foto == {
        "AGUA": [{"-": 1, "leido": 2, "sin_dato": 23}, [8.0, 8.0]],
        "ALCANTARILLADO": [{"leido": 1, "sin_dato": 12}, [18.0]],
        "DRENAJE": [{"dudoso": 1, "leido": 9, "sin_dato": 12}, [18.0] * 5 + [24.0, 24.0, 33.0, 84.0]],
        "ELECTRICO": [{"-": 1, "sin_dato": 13}, []],
        "GAS": [{"sin_dato": 6}, []],
        "TELECOM": [{"sin_dato": 15}, []],
    }
    agua = next(r for r in res if r.utility == "AGUA")
    assert any((p.grosor or {}).get("cerca") for p in agua.polylines if (p.grosor or {}).get("estado") == "sin_dato")
    # lo leído por su rótulo no lleva evidencia (lo que pasa a «leido» después, por los perfiles, la conserva)
    assert not any("cerca" in (p.grosor or {}) for r in res for p in r.polylines
                   if (p.grosor or {}).get("estado") == "leido" and (p.grosor or {}).get("fuente") != "perfil")


# ── Tarea 2: imágenes y visión en el proveedor ─────────────────────────
from ia import proveedor as PV  # noqa: E402
from tests.ollama_falso import OllamaFalso  # noqa: E402


def _prov(falso, modelo="qwen3-vl:8b"):
    return PV.crear({"proveedor": "ollama", "url": falso.url, "modelo": modelo})


def test_vision_segun_capacidades():
    with OllamaFalso(lambda c: "{}", capacidades=("completion", "vision")) as f:
        assert _prov(f).vision() is True
    with OllamaFalso(lambda c: "{}", capacidades=("completion",)) as f:
        assert _prov(f).vision() is False
    assert PV.crear({"proveedor": "ollama", "url": "http://127.0.0.1:9", "modelo": "x"}).vision() is False


def test_chat_manda_imagenes():
    with OllamaFalso(lambda c: "ok") as f:
        _prov(f).chat([{"role": "user", "content": "hola", "images": ["QUJD"]}])
        assert f.pedidos[-1]["messages"][-1]["images"] == ["QUJD"]


# ── Tarea 3: petición, lectura y comprobación ──────────────────────────
import json  # noqa: E402

from ia import diametro_ia as DI  # noqa: E402
from ia import memoria as MEM  # noqa: E402
from nucleo import normas_reglas as NR  # noqa: E402


def _e(id_, d, util="", guia="esta", varios=1, es_de=True, normativa=True, texto=None):
    return dict(id=id_, texto=texto or f'{d:g}" X', diam_in=d, material="", util=util, es_de=es_de, dist_pt=2.0,
                guia=guia, otra=None, caja=[0, 0, 1, 1], estacion=False, union=False, varios=varios,
                normativa=normativa)


def _ficha(*rot, util="DRENAJE"):
    return dict(utilidad=util, utilidad_nombre=util.title(), capa="C-STRM-UNGD-E", sistema="", estado_capa="",
                abandonada=False, largo_ft=40.0, por_defecto_in=12.0, estado_plano="sin_dato", paredes_in=None,
                perfil_in=[], rotulos=list(rot))


def _resp(rot, conf="alta"):
    return json.dumps({"rotulo": rot, "confianza": conf, "motivo": "porque sí", "pista": None})


def _sugerir(f, respuestas, **k):
    cola = list(respuestas)
    with OllamaFalso(lambda c: cola.pop(0) if cola else _resp(None)) as falso:
        s = DI.sugerir(_prov(falso), f, **k)
        return s, falso.pedidos


def test_sugiere_el_rotulo_elegido():
    s, pedidos = _sugerir(_ficha(_e("R1", 18.0), _e("R2", 84.0, guia="otra")), [_resp("R1"), _resp("R1")])
    assert (s.diam_in, s.rotulo, s.origen) == (18.0, "R1", "ia")
    assert len(pedidos) == 2


def test_id_inexistente_se_descarta():
    s, _p = _sugerir(_ficha(_e("R1", 18.0)), [_resp("R7"), _resp("R7")])
    assert s.diam_in is None and s.origen == "descartada"


def test_rotulo_de_otra_utilidad_se_descarta():
    s, _p = _sugerir(_ficha(_e("R1", 84.0, util="DRENAJE", es_de=False), _e("R2", 8.0), util="AGUA"),
                     [_resp("R1"), _resp("R1")])
    assert s.diam_in is None and s.origen == "descartada"


def test_rotulo_varios_se_descarta():
    s, _p = _sugerir(_ficha(_e("R1", 4.0, varios=2), _e("R2", 8.0)), [_resp("R1"), _resp("R1")])
    assert s.diam_in is None and s.origen == "descartada"


def test_guia_a_otra_linea_se_descarta():
    s, _p = _sugerir(_ficha(_e("R1", 18.0, guia="otra"), _e("R2", 8.0)), [_resp("R1"), _resp("R1")])
    assert s.diam_in is None and s.origen == "descartada"


def test_no_permitido_por_normativa_se_descarta():
    s, _p = _sugerir(_ficha(_e("R1", 18.0, normativa=False), _e("R2", 8.0)), [_resp("R1"), _resp("R1")])
    assert s.diam_in is None and s.origen == "descartada"


def test_confianza_baja_se_descarta():
    s, _p = _sugerir(_ficha(_e("R1", 18.0)), [_resp("R1", "baja"), _resp("R1", "baja")])
    assert s.diam_in is None and s.origen == "descartada"


def test_dos_pasadas_distintas_no_sugieren():
    s, _p = _sugerir(_ficha(_e("R1", 18.0), _e("R2", 24.0)), [_resp("R1"), _resp("R2")])
    assert s.diam_in is None and s.origen == "desacuerdo"


def test_null_es_una_respuesta_y_no_repite():
    s, pedidos = _sugerir(_ficha(_e("R1", 18.0)), [_resp(None)])
    assert s.diam_in is None and s.origen == "ia" and len(pedidos) == 1


def test_sin_rotulos_no_pregunta():
    s, pedidos = _sugerir(_ficha(), [])
    assert s.origen == "sin_rotulos" and pedidos == []


def test_cache_no_repite():
    mem = MEM.Memoria()
    f = _ficha(_e("R1", 18.0))
    s1, p1 = _sugerir(f, [_resp("R1"), _resp("R1")], memoria=mem)
    s2, p2 = _sugerir(f, [], memoria=mem)
    assert (s1.diam_in, len(p1)) == (18.0, 2)
    assert (s2.diam_in, s2.origen, len(p2)) == (18.0, "memoria", 0)


def test_imagen_solo_en_la_primera_pasada_y_con_vision():
    cola = [_resp("R1"), _resp("R1")]
    with OllamaFalso(lambda c: cola.pop(0), capacidades=("completion", "vision")) as falso:
        DI.sugerir(_prov(falso), _ficha(_e("R1", 18.0)), imagen="QUJD")
        assert falso.pedidos[0]["messages"][-1].get("images") == ["QUJD"]
        assert "images" not in falso.pedidos[1]["messages"][-1]
    cola = [_resp("R1"), _resp("R1")]
    with OllamaFalso(lambda c: cola.pop(0)) as falso:          # sin visión: no se manda
        DI.sugerir(_prov(falso), _ficha(_e("R1", 18.0)), imagen="QUJD")
        assert "images" not in falso.pedidos[0]["messages"][-1]


def test_pedido_numera_y_explica():
    sistema, mensajes = DI.pedido(_ficha(_e("R1", 18.0), _e("R2", 84.0, guia="otra")))
    assert "null" in sistema and "MAGENTA" in sistema
    from ia.diametro_ia_ejemplos import EJEMPLOS
    assert len(mensajes) == 2 * len(EJEMPLOS) + 1 and len(EJEMPLOS) == 3
    ultimo = mensajes[-1]["content"]
    assert "R1:" in ultimo and "R2:" in ultimo and ultimo.index("R1:") < ultimo.index("R2:")
    _s, inv = DI.pedido(_ficha(_e("R1", 18.0), _e("R2", 84.0)), invertir=True)
    assert inv[-1]["content"].index("R2:") < inv[-1]["content"].index("R1:")


def test_correcciones_del_equipo_van_en_el_pedido():
    mem = MEM.Memoria()
    f = _ficha(_e("R1", 18.0, texto='LAT CB-226 / 18" RCP'))
    DI.aprender_error(mem, f, DI.Sugerencia(18.0, "R1", "alta", ""))
    cola = [_resp(None)]
    with OllamaFalso(lambda c: cola.pop(0)) as falso:
        DI.sugerir(_prov(falso), f, memoria=mem)
        assert "Correcciones del equipo" in falso.pedidos[0]["messages"][-1]["content"]


def test_permitido_por_normativa():
    cat = {"version": 2, "tipos": {}, "reglas": [NR.regla_vacia(utilidad="AGUA", revisar="diametro",
                                                                 valores=[4.0, 6.0, 8.0, 12.0])]}
    p = {"layer": "AGUA", "pts": [(0, 0), (100, 0)], "diam": 12.0}
    assert diametro_plano.permitido(cat, p, 8.0) is True
    assert diametro_plano.permitido(cat, p, 84.0) is False
    assert diametro_plano.permitido(None, p, 84.0) is True


# ── Tarea 4: recorte marcado del plano ─────────────────────────────────
import fitz  # noqa: E402

from hoja import recorte_diametro as RC  # noqa: E402


def _pagina(rotar=0):
    doc = fitz.open()
    pg = doc.new_page(width=600, height=400)
    pg.draw_line((50, 200), (550, 200), color=(0, 0, 0), width=1)
    pg.insert_text((300, 180), '18" RCP', fontsize=8)
    if rotar:
        pg.set_rotation(rotar)
    return doc, pg


def _magenta_en(png, fila_frac=None, col_frac=None):
    pix = fitz.Pixmap(png)
    n = pix.n
    filas = range(pix.height) if fila_frac is None else [int(fila_frac * pix.height)]
    cols = range(pix.width) if col_frac is None else [int(col_frac * pix.width)]
    for y in filas:
        for x in cols:
            r, g, b = pix.pixel(x, y)[:3]
            if r > 200 and g < 80 and b > 200:
                return True
    _ = n
    return False


def test_recorte_marca_la_linea():
    _doc, pg = _pagina()
    png = RC.recorte(pg, [(50.0, 200.0), (550.0, 200.0)], {"R1": (300.0, 172.0, 340.0, 182.0)})
    pix = fitz.Pixmap(png)
    assert max(pix.width, pix.height) == RC.LADO_PX
    assert _magenta_en(png)


def _tinta_dentro(png, z, caja):
    """¿Hay píxeles oscuros (el texto del PDF) dentro de `caja` (pt de la vista) en el recorte de la zona `z`?"""
    pix = fitz.Pixmap(png)
    k = pix.width / z.width
    x0, y0 = int((caja[0] - z.x0) * k) + 4, int((caja[1] - z.y0) * k) + 4
    x1, y1 = int((caja[2] - z.x0) * k) - 4, int((caja[3] - z.y0) * k) - 4
    return any(max(pix.pixel(x, y)[:3]) < 90 for y in range(y0, y1) for x in range(x0, x1))


def test_recorte_en_hoja_girada():
    """En la VISTA de una hoja girada 90° todo va girado: el texto queda dentro de su marco."""
    for rotar in (0, 90):
        _doc, pg = _pagina(rotar)
        m = pg.rotation_matrix
        caja = tuple(pg.search_for('18" RCP')[0] * m)
        a, b = fitz.Point(50, 200) * m, fitz.Point(550, 200) * m
        pts = [(a.x, a.y), (b.x, b.y)]
        png = RC.recorte(pg, pts, {"R1": caja})
        assert _tinta_dentro(png, RC.zona(pts, {"R1": caja}) & pg.rect, caja), rotar
        assert _magenta_en(png)


def test_permitido_no_usa_reglas_de_diseno_con_condiciones():
    """«Mínimo 24" si mide ≥ 100 ft» es de diseño: no descarta un 18" que el plano dice construido."""
    cat = {"version": 2, "tipos": {}, "reglas": [NR.regla_vacia(utilidad="DRENAJE", revisar="diametro", min=24.0,
                                                                 si_largo=[100.0, None])]}
    p = {"layer": "DRENAJE", "pts": [(0, 0), (300, 0)], "diam": 12.0}
    assert diametro_plano.permitido(cat, p, 18.0) is True


def test_sin_rotulos_elegibles_no_pregunta():
    """Si la app ya sabe que ningún rótulo puede ser de esta línea (otra utilidad, guía a otra línea, varios
    conductos o fuera de la normativa), responde sin preguntar a la IA."""
    f = _ficha(_e("R1", 84.0, util="DRENAJE", es_de=False), _e("R2", 8.0, guia="otra"), _e("R3", 4.0, varios=2),
               util="ELECTRICO")
    s, pedidos = _sugerir(f, [])
    assert pedidos == [] and s.diam_in is None and s.origen == "sin_rotulos"


def test_guia_ambigua_no_sugiere():
    """DU06 h.índice 3: la punta de «84" RCP SD, LACFCD» cae en la unión de un lateral con la principal de 84":
    la IA la eligió para el lateral. Una guía que llega a dos líneas no da sugerencia."""
    s, _p = _sugerir(_ficha(_e("R1", 84.0, guia="ambigua"), _e("R2", 8.0)), [_resp("R1"), _resp("R1")])
    assert s.diam_in is None and s.origen == "descartada"


def test_cerca_trae_las_puntas_de_la_guia():
    r = _rot('18" RCP SD', 18.0, 60.0, -30.0, util="DRENAJE")
    hoja = G.Hoja([r], [(r, [(70.0, -24.0), (80.0, 0.0)], (80.0, 0.0))], [], [None])
    assert C.cerca(LINEA, hoja, "DRENAJE", 1.0, 1.0 / 12.0)[0]["puntas"] == [[80.0, 0.0]]


def test_recorte_incluye_las_puntas_y_rotula_los_ids():
    _doc, pg = _pagina()
    caja = (300.0, 172.0, 340.0, 182.0)
    z = RC.zona([(50.0, 200.0), (550.0, 200.0)], {"R1": caja}, puntos=[(420.0, 260.0)])
    assert z.contains(fitz.Point(420.0, 260.0))
    png = RC.recorte(pg, [(50.0, 200.0), (550.0, 200.0)], {"R1": caja}, puntos=[(420.0, 260.0)])
    pix = fitz.Pixmap(png)
    k = pix.width / (z & pg.rect).width
    # el texto blanco «R1» sobre su etiqueta turquesa, justo encima de la caja
    x0, y0 = int((caja[0] - z.x0) * k), int((caja[1] - z.y0) * k)
    blancos = sum(1 for y in range(max(0, y0 - 24), y0) for x in range(x0, x0 + 40)
                  if min(pix.pixel(x, y)[:3]) > 230)
    assert blancos > 10


def test_guia_que_casi_llega_dice_a_cuanto_queda():
    """DU06 h.índice 4: «EX. FH, 6" WATER ABND» termina su guía a ~5 pt del ramal del hidrante (fuera de la
    tolerancia): la ficha debe decir a cuánto queda, no solo «no llega a ninguna línea»."""
    r = _rot('EX. FH, 6" WATER ABND', 6.0, 60.0, -30.0, util="AGUA")
    hoja = G.Hoja([r], [(r, [(70.0, -24.0), (80.0, -5.4)], (80.0, -5.4))], [], [None])
    e = C.cerca(LINEA, hoja, "AGUA", 1.0, 0.3)[0]
    assert e["guia"] == "nada" and e["punta_pt"] == pytest.approx(5.4)
    texto = DI.texto_ficha(_ficha(dict(e, normativa=True), util="AGUA"))
    assert "5.4 pt" in texto


def test_recorte_no_pasa_del_tamano_maximo():
    """DU06 h.índice 4: con rótulos a 120 pt el recorte abarcaba ~600 pt (hasta los perfiles) y la letra quedaba
    chica para un modelo de 9B. La zona no pasa de `ZONA_MAX_PT` y queda centrada en los rótulos."""
    pts = [(50.0, 200.0), (550.0, 200.0)]
    cajas = {"R1": (300.0, 172.0, 340.0, 182.0), "R2": (40.0, 20.0, 80.0, 30.0), "R3": (520.0, 380.0, 560.0, 390.0)}
    z = RC.zona(pts, cajas, puntos=[(560.0, 395.0)])
    assert max(z.width, z.height) <= RC.ZONA_MAX_PT + 1e-6
    assert z.contains(fitz.Point(320.0, 177.0))          # el rótulo más cercano a la línea queda adentro


def test_id_visible_aunque_el_rotulo_empiece_fuera_del_recorte():
    """Compuesta DU06: «EX. FH, 6" WATER ABND» empieza a la izquierda del recorte y su «R1» quedaba afuera."""
    _doc, pg = _pagina()
    pts = [(50.0, 200.0), (550.0, 200.0)]
    caja = (-200.0, 150.0, 330.0, 160.0)                  # empieza fuera de la hoja
    png = RC.recorte(pg, pts, {"R1": caja})
    pix = fitz.Pixmap(png)
    z = RC.zona(pts, {"R1": caja}) & pg.rect
    k = pix.width / z.width
    y0 = int((caja[1] - z.y0) * k)
    relleno = sum(1 for y in range(max(0, y0 - 22), max(0, y0 - 6)) for x in range(0, 30)
                  if pix.pixel(x, y)[:3] == (0, 140, 153))
    assert relleno > 150                                  # la etiqueta rellena, pegada al borde izquierdo
