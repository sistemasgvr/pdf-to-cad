import base64
import json

import fitz
import pytest

from hoja import composite as C, contexto_original as CO
from nucleo import archivo_zip
from ia import diametro_ia as DI
from types import SimpleNamespace


def _fuente():
    doc=fitz.open()
    p=doc.new_page(width=600,height=500)
    p.insert_text((50,70),'PROFILE CB-237 / 18" RCP SD')
    p.insert_text((470,180),'CONSTRUCTION NOTES\nKEEP EXISTING PIPE',fontsize=7)
    p.insert_text((80,470),'PROJECT METRO DRAWING UD-210')
    p.draw_line((100,200),(400,200))
    return doc


def _datos(giro=0):
    doc=_fuente()
    fuentes=[dict(name="original.pdf",data=doc.tobytes())]
    pz=C.Piece(0,0,[.1,.3,.75,.8],x=173,y=-43,rotation=giro,src_scale=40/72)
    comp=C.Composite([pz],scale_ft_per_pt=20/72)
    _,_,dx,dy=C.sheet_geometry(comp,lambda p:(600,500))
    fn=C.piece_map(pz,(600,500),comp.target_scale())
    pts=[(fn(x,y)[0]+dx,fn(x,y)[1]+dy) for x,y in [(100,200),(400,200)]]
    return fuentes,comp,pts


@pytest.mark.parametrize("giro",[0,90,30,180])
def test_conserva_notas_perfiles_membrete_fuera_de_recorte(giro):
    fuentes,comp,pts=_datos(giro)
    contexto,plan,completos=CO.reunir(fuentes,comp,pts,utilidad="DRENAJE",referencias=['CB-237'])
    assert not contexto["advertencias"]
    hoja=contexto["hojas"][0]
    assert hoja["pagina"]==1 and hoja["documento"]=="original.pdf"
    textos=hoja["textos"]
    assert any("CONSTRUCTION NOTES" in t["texto"] and t["fuera_del_area"] for t in textos)
    assert any("PROJECT METRO" in t["texto"] and t["zona"]=="membrete" for t in textos)
    assert any("PROFILE CB-237" in t["texto"] and t["zona"]=="superior / perfiles" for t in textos)
    for esperado,real in zip([(100,200),(400,200)],hoja["lineas_en_original"][0]):
        assert real==pytest.approx(esperado)
    assert {p["zona"] for p in plan} >= {"hoja completa"}
    capturas=CO.capturas(fuentes,plan)
    assert len(capturas)==len(plan)
    assert all(c["pagina"]==1 for c in capturas)
    assert any(t["texto"].startswith("PROJECT METRO") for t in completos[0]["textos"])


def test_solo_hoja_asociada_y_recorte_poligonal():
    fuentes,comp,pts=_datos()
    doc=fitz.open(stream=fuentes[0]["data"],filetype="pdf")
    doc.new_page(width=600,height=500).insert_text((20,20),"OTHER PAGE 99 INCH")
    fuentes[0]["data"]=doc.tobytes()
    comp.pieces.append(C.Piece(0,1,[0,0,1,1],x=2000))
    _,_,dx,dy=C.sheet_geometry(comp,lambda p:(600,500))
    fn=C.piece_map(comp.pieces[0],(600,500),comp.target_scale())
    pts=[(fn(x,y)[0]+dx,fn(x,y)[1]+dy) for x,y in [(100,200),(400,200)]]
    contexto,_,_=CO.reunir(fuentes,comp,pts)
    assert [h["pagina"] for h in contexto["hojas"]]==[1]
    assert "OTHER PAGE" not in json.dumps(contexto)


def test_originales_persistidos_funcionan_sin_archivo_externo(tmp_path):
    fuentes,comp,pts=_datos(90)
    original=fuentes[0]["data"]
    with fitz.open(stream=original,filetype="pdf") as doc:
        trabajo=C.build_document(comp,[doc])
    ruta=str(tmp_path/"prueba.digproj")
    archivo_zip.escribir(ruta,[("model.json",json.dumps(dict(composite=comp.to_dict(),src_names=["original.pdf"]))),
                              ("source.pdf",trabajo.tobytes()),("sources/000.pdf",original)])
    data=archivo_zip.leer(ruta)
    modelo=json.loads(data["model.json"])
    reabiertas=[dict(name=modelo["src_names"][0],data=data["sources/000.pdf"])]
    contexto,plan,_=CO.reunir(reabiertas,C.Composite.from_dict(modelo["composite"]),pts)
    assert "PROJECT METRO" in json.dumps(contexto)
    assert all(c["imagen"] for c in CO.capturas(reabiertas,plan))
    assert reabiertas[0]["data"]==original


def test_envio_multimodal_tiene_texto_y_procedencia_de_originales():
    fuentes,comp,pts=_datos()
    contexto,plan,_=CO.reunir(fuentes,comp,pts,utilidad="DRENAJE")
    capturas=CO.capturas(fuentes,plan)
    f=dict(utilidad="DRENAJE",utilidad_nombre="Drenaje",capa="C-STRM",sistema="",estado_capa="",largo_ft=100,
           rotulos=[],tipo="",contexto=dict(hojas_originales=contexto),
           normativa=[dict(id="N1",diam_in=24,tipo="COLECTOR",tipo_supuesto=True,fuente="Norma",criterio='mínimo 24"')])
    pedidos=[]
    def chat(m,**kwargs):
        pedidos.append(m)
        return SimpleNamespace(texto='{"opcion":"N1","motivo":"Propuesta por el trazado"}')
    prov=SimpleNamespace(config=SimpleNamespace(modelo="vision"),vision=lambda:True,chat=chat)
    s=DI.sugerir(prov,f,imagen="local",capturas=capturas)
    assert len(pedidos[0][0]["images"])==1+len(capturas)
    assert "CONSTRUCTION NOTES" in pedidos[0][0]["content"]
    assert len(s.analisis["capturas_originales"])==len(capturas)
    assert all("imagen" not in c for c in s.analisis["capturas_originales"])
    assert base64.b64decode(capturas[0]["imagen"]).startswith(b"\x89PNG")


def test_indice_completo_no_se_pierde_al_limitar_lo_enviado(monkeypatch):
    fuentes,comp,pts=_datos()
    monkeypatch.setattr(CO,"MAX_TEXTO",80)
    contexto,_,completos=CO.reunir(fuentes,comp,pts)
    hoja=contexto["hojas"][0]
    assert sum(len(t["texto"]) for t in hoja["textos"])<=80
    assert len(completos[0]["textos"])==hoja["bloques_totales"]
    assert any("KEEP EXISTING PIPE" in t["texto"] for t in completos[0]["textos"])


def test_referencias_en_original_con_rotate_se_relacionan_con_cajas_visibles():
    doc=_fuente()
    doc[0].set_rotation(90)
    fuentes=[dict(name="girado.pdf",data=doc.tobytes())]
    contexto,_,_=CO.reunir(fuentes,None,[(300,100),(300,400)],utilidad="DRENAJE")
    assert any(r["diam_in"]==18 for r in contexto["hojas"][0]["diametros_contextuales"])


def test_cambio_de_captura_original_invalida_cache_visual():
    cache={}
    llamadas=[]
    mem=SimpleNamespace(redaccion=lambda k:cache.get(k),guardar_redaccion=lambda k,v,m:cache.update({k:v}),buscar=lambda *a,**k:[])
    def chat(*a,**k):
        llamadas.append(a)
        return SimpleNamespace(texto='{"opcion":"N1"}')
    prov=SimpleNamespace(config=SimpleNamespace(modelo="vision"),vision=lambda:True,chat=chat)
    f=dict(utilidad="AGUA",utilidad_nombre="Agua",capa="",rotulos=[],contexto={},
           normativa=[dict(id="N1",diam_in=8,tipo="",tipo_supuesto=False,criterio="",fuente="")])
    c=[dict(imagen="apoyo1",sha256_png="hash1",pagina=0,documento="a.pdf")]
    DI.sugerir(prov,f,imagen="local",capturas=c,memoria=mem)
    DI.sugerir(prov,f,imagen="local",capturas=c,memoria=mem)
    c[0]=dict(c[0],imagen="apoyo2",sha256_png="hash2")
    DI.sugerir(prov,f,imagen="local",capturas=c,memoria=mem)
    assert len(llamadas)==2


def test_giro_de_la_hoja_de_trabajo_no_pierde_procedencia():
    fuentes,comp,pts=_datos()
    doc=fitz.open(stream=fuentes[0]["data"],filetype="pdf")
    trabajo=C.build_document(comp,[doc])
    trabajo[0].set_rotation(90)
    visibles=[tuple(fitz.Point(p)*trabajo[0].rotation_matrix) for p in pts]
    contexto,_,_=CO.reunir(fuentes,comp,visibles,trabajo=trabajo)
    for esperado,real in zip([(100,200),(400,200)],contexto["hojas"][0]["lineas_en_original"][0]):
        assert real==pytest.approx(esperado)


def test_contexto_cambia_si_se_modifica_el_pdf_sin_fuentes_externas():
    doc=_fuente()
    cache={}
    a,_,_=CO.reunir([],None,[(100,200),(400,200)],cache=cache,trabajo=doc)
    repetida,_,_=CO.reunir([],None,[(100,200),(400,200)],cache=cache,trabajo=doc)
    assert a==repetida
    doc[0].insert_text((50,400),'NEW ORIGINAL NOTE')
    b,_,_=CO.reunir([],None,[(100,200),(400,200)],cache=cache,trabajo=doc)
    assert a['hojas'][0]['sha256_pdf']!=b['hojas'][0]['sha256_pdf']
    assert 'NEW ORIGINAL NOTE' in json.dumps(b)
