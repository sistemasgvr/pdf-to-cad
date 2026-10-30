import json
import math
from pathlib import Path

import pytest

from ia import diametro_ia as DI
from nucleo import diametro_normativa as DN, normas_catalogo as nc
from nucleo.normas_base import R
from ollama_falso import OllamaFalso
from test_diametro_ia import _prov


def pipe(u="DRENAJE", tipo="COLECTOR PRINCIPAL"):
    return dict(layer=u, tipo=tipo, diam=12, pts=[(0, 0), (200, 0)],
                diam_plano={"estado": "sin_dato", "cerca": []})


def test_minimo_y_condicion_largo():
    cat = nc.nuevo()
    p = pipe(tipo="CONEXION DE SUMIDERO")
    assert DN.opciones(cat, p, 80)[0]["diam_in"] == 18
    assert DN.opciones(cat, p, 100)[0]["diam_in"] == 24
    assert DN.opciones(cat, p, None) == []


def test_sin_tipo_no_inventa_y_explicita_hipotesis():
    ops = DN.opciones(nc.nuevo(), pipe("ALCANTARILLADO", ""), 50)
    assert {o["diam_in"] for o in ops} == {6, 8}
    assert all(o["tipo_supuesto"] and o["fuente"] for o in ops)
    assert DN.opciones({}, pipe(), 50) == []


def test_respeta_grupos_excepciones_y_desactivadas():
    ops = DN.opciones(nc.nuevo(), pipe("AGUA", "DISTRIBUCION PRINCIPAL"), 50)
    assert ops[0]["diam_in"] == 6  # 4 sólo en cul-de-sac
    cat = {"reglas": [R("DRENAJE", "", "TUBERIA", "diametro", minimo=18),
                       R("DRENAJE", "", "TUBERIA", "diametro", maximo=12, si_largo=[100, None])]}
    assert DN.opciones(cat, pipe(), 150) == []
    cat["reglas"][1]["activa"] = False
    assert DN.opciones(cat, pipe(), 150)[0]["diam_in"] == 18


def test_amperaje_desconocido_no_se_inventa():
    p = pipe("ELECTRICO", "INSTALACION DOMICILIARIA")
    assert DN.opciones(nc.nuevo(), p, 150) == []
    p["amperaje"] = 350
    assert DN.opciones(nc.nuevo(), p, 150)[0]["diam_in"] == 4


def test_sugerencia_normativa_con_fuente_sin_ia_remota():
    p = pipe()
    f = DI.ficha(p, "Drenaje", largo_ft=80, catalogo=nc.nuevo())
    with OllamaFalso(lambda c: "{}") as srv:
        s = DI.sugerir(_prov(srv), f)
        assert s.diam_in == 24 and s.rotulo is None and s.origen == "normativa"
        assert "Metro MRDC" in s.analisis["opcion"]["fuente"]
        assert "recorrido" in s.motivo and "Fuente:" not in s.motivo
        assert srv.pedidos == []
    assert p["diam"] == 12


def test_lectura_sin_certeza_pasa_a_normativa():
    p = pipe()
    p["diam_plano"]["cerca"] = [dict(id="R1", texto='18" RCP', diam_in=18, guia="esta")]
    f = DI.ficha(p, "Drenaje", largo_ft=80, catalogo=nc.nuevo())
    with OllamaFalso(lambda c: '{"rotulo":null,"confianza":"baja"}') as srv:
        s = DI.sugerir(_prov(srv), f)
        assert s.diam_in == 24 and s.origen == "normativa"
        assert len(srv.pedidos) == 1


def test_ia_elige_hipotesis_validada_no_numero_libre():
    f = DI.ficha(pipe("ALCANTARILLADO", ""), "Alcantarillado", largo_ft=80, catalogo=nc.nuevo())
    with OllamaFalso(lambda c: json.dumps({"opcion": "N1", "motivo": "El rótulo de agua prueba este diámetro"})) as srv:
        s = DI.sugerir(_prov(srv), f)
        assert s.diam_in == 8 and "Tipo supuesto: COLECTOR" in s.motivo
        assert "El rótulo de agua" not in s.motivo
        assert len(srv.pedidos) == 1
    with OllamaFalso(lambda c: '{"opcion":"N999","diam_in":900}') as srv:
        assert DI.sugerir(_prov(srv), f).diam_in is None


def test_referencias_normativas_descartan_otras_redes():
    p = pipe("ALCANTARILLADO", "")
    p["diam_plano"]["cerca"] = [dict(id="R1", texto='PROP 8" WATER', diam_in=8, util="AGUA", es_de=False),
                                    dict(id="R2", texto='SS', diam_in=8, util="ALCANTARILLADO", es_de=True)]
    f = DI.ficha(p, "Alcantarillado", largo_ft=80, catalogo=nc.nuevo())
    assert f["referencias"] == ["SS"]


def test_respuesta_vacia_es_error_de_ia_no_falta_de_tipo():
    from ia.proveedor import ErrorIA
    f = DI.ficha(pipe("ALCANTARILLADO", ""), "Alcantarillado", largo_ft=80, catalogo=nc.nuevo())
    with OllamaFalso(lambda c: "") as srv:
        with pytest.raises(ErrorIA, match="modelo instruct"):
            DI.sugerir(_prov(srv), f)


def test_cache_cambia_con_normativa():
    p = pipe()
    cat = nc.nuevo()
    f = DI.ficha(p, "Drenaje", largo_ft=80, catalogo=cat)
    for r in cat["reglas"]:
        if r["utilidad"] == "DRENAJE" and r["revisar"] == "diametro" and r["tipo"] == p["tipo"]:
            r["min"] = 30
    g = DI.ficha(p, "Drenaje", largo_ft=80, catalogo=cat)
    assert DI.clave_de(f) != DI.clave_de(g)


DU06 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf")


@pytest.mark.skipif(not DU06.is_file(), reason="DU06 no disponible")
def test_du06_real_propone_sin_cambiar_el_diametro():
    from reconocimiento import recognition_trabajo as RT
    from nucleo import diametro_plano
    res = RT.reconocer_hoja(str(DU06), 3, zoom=1.0, utilities=("DRENAJE",))
    revisadas = 0
    with OllamaFalso(lambda c: '{"opcion":"N1","motivo":"Propuesta para revisión"}') as srv:
        for r in res:
            for pl in r.polylines:
                dp = diametro_plano.de_grosor(pl.grosor)
                if dp.get("estado") not in ("sin_dato", "dudoso"):
                    continue
                p = dict(layer=r.utility, pts=pl.pts_pdf, diam=12, diam_plano=dp)
                largo = sum(math.dist(a, b) for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:])) * 20 / 72
                f = DI.ficha(p, "Drenaje", largo_ft=largo, catalogo=nc.nuevo())
                if not f["normativa"]:
                    continue
                # Prueba la alternativa normativa sobre referencias reales del PDF.
                s = DI.sugerir_normativa(_prov(srv), f)
                assert s.origen == "normativa" and s.diam_in > 0 and "Metro MRDC" in s.analisis["opcion"]["fuente"]
                assert p["diam"] == 12 and not p.get("diam_elegido")
                revisadas += 1
    assert revisadas > 0
