import base64
import hashlib
import json
from types import SimpleNamespace

import fitz

from ia import diametro_ia as DI
from nucleo import diametro_contexto as DC, normas_catalogo as nc
from hoja import contexto_diametro, recorte_diametro


def _linea(pts, d=12, elegido=False, u="AGUA"):
    return dict(pts=pts, layer=u, diam=d, diam_elegido=elegido,
                tipo="DISTRIBUCION PRINCIPAL",diam_plano={"estado":"sin_dato","cerca":[]})


def test_trayecto_y_contactos_no_confunden_cruces_o_defectos():
    p=_linea([(0,0),(100,0),(100,100)])
    confirmada=_linea([(100,100),(300,100)],8,True)
    defecto=_linea([(-100,0),(0,0)])
    cruce=_linea([(50,-50),(50,50)],20,True)
    otra_red=_linea([(0,0),(-50,50)],24,True,"DRENAJE")
    c=DC.reunir(p,[p,confirmada,defecto,cruce,otra_red],1)
    assert c["trayecto"]["largo_ft"]==200
    assert c["trayecto"]["giros_mayores_10_grados"]==1
    assert len(c["contactos"])==2
    assert [e["diam_in"] for e in c["evidencias"] if e.get("diam_in")] == [8]
    assert c["trayecto"]["puntos_relativos"][-1]==[100,100]


def test_contexto_y_diametros_confirmados_cambian_la_ficha_y_cache():
    p=_linea([(0,0),(100,0)])
    q=_linea([(100,0),(200,0)],10,True)
    c=DC.reunir(p,[p,q],1)
    f=DI.ficha(p,"Agua",largo_ft=100,catalogo=nc.nuevo(),contexto=c)
    # 10 no está en la lista de distribución principal: no se ofrece.
    assert 10 not in {o["diam_in"] for o in f["normativa"]}
    q["diam"]=8
    g=DI.ficha(p,"Agua",largo_ft=100,catalogo=nc.nuevo(),contexto=DC.reunir(p,[p,q],1))
    assert DI.clave_de(f)!=DI.clave_de(g)
    assert {o["diam_in"] for o in g["normativa"]} >= {6,8,12,16}


def test_normativa_con_imagen_analiza_y_conserva_datos_enviados():
    p=_linea([(0,0),(100,0)])
    q=_linea([(100,0),(200,0)],8,True)
    c=DC.reunir(p,[p,q],1)
    f=DI.ficha(p,"Agua",largo_ft=100,catalogo=nc.nuevo(),contexto=c)
    opcion=next(o for o in f["normativa"] if o["diam_in"]==8)
    e=next(e for e in c["evidencias"] if e.get("diam_in")==8)
    pedidos=[]
    def chat(mensajes,**kwargs):
        pedidos.append((mensajes,kwargs))
        return SimpleNamespace(texto=json.dumps(dict(opcion=opcion["id"],evidencias=[e["id"],"E999"],
                                                      motivo="Continuidad de la red",observacion_visual="Línea paralela a la calle")))
    prov=SimpleNamespace(config=SimpleNamespace(modelo="vision"),vision=lambda:True,chat=chat)
    s=DI.sugerir(prov,f,imagen="cG5n")
    assert s.diam_in==8 and "confirmados" in s.motivo
    assert pedidos[0][0][0]["images"]==["cG5n"]
    assert s.analisis["imagen_usada"] and s.analisis["imagen_sha256"]==hashlib.sha256(b"cG5n").hexdigest()
    assert s.analisis["entrada"]["contexto"]==c
    assert [x["id"] for x in s.analisis["evidencias"]]==[e["id"]]
    assert "Fuente:" not in s.motivo and len(s.motivo)<240
    assert DI.Sugerencia.de_dict(s.a_dict()).analisis==s.analisis


def test_recorte_y_textos_existen_aun_sin_rotulos():
    doc=fitz.open()
    page=doc.new_page(width=600,height=600)
    page.insert_text((40,180),"SEWER MAIN - UTILITY DATA")
    page.insert_text((40,550),"FAR AWAY")
    pts=[(50,200),(500,200)]
    textos=contexto_diametro.textos(page,pts)
    assert any("SEWER MAIN" in t["texto"] for t in textos)
    assert not any("FAR AWAY" in t["texto"] for t in textos)
    png=recorte_diametro.recorte(page,pts,{},trayecto_completo=True)
    pix=fitz.Pixmap(png)
    assert max(pix.width,pix.height)==1024
    assert png.startswith(b"\x89PNG")
    zona=recorte_diametro.zona([(400,400),(500,400)],{})
    assert zona.x0 > 300 and zona.y0 > 300


def test_texto_en_pagina_girada_usa_coordenadas_de_la_vista():
    doc=fitz.open()
    page=doc.new_page(width=600,height=600)
    page.insert_text((40,180),"SEWER MAIN")
    page.set_rotation(90)
    textos=contexto_diametro.textos(page,[(400,40),(400,200)])
    assert textos and "SEWER MAIN" in textos[0]["texto"]
    assert textos[0]["caja_pt"][0]>400


def test_la_cache_cambia_si_cambia_la_imagen():
    f=DI.ficha(_linea([(0,0),(100,0)]),"Agua",largo_ft=100,catalogo=nc.nuevo())
    llamadas=[]
    memoria={}
    mem=SimpleNamespace(redaccion=lambda k:memoria.get(k),guardar_redaccion=lambda k,v,m:memoria.update({k:v}),
                        buscar=lambda *a,**k:[])
    def chat(*a,**k):
        llamadas.append(a)
        return SimpleNamespace(texto='{"opcion":"N1","evidencias":["E1"]}')
    prov=SimpleNamespace(config=SimpleNamespace(modelo="vision"),vision=lambda:True,chat=chat)
    DI.sugerir(prov,f,imagen="imagen1",memoria=mem)
    DI.sugerir(prov,f,imagen="imagen1",memoria=mem)
    DI.sugerir(prov,f,imagen="imagen2",memoria=mem)
    assert len(llamadas)==2


def test_resumen_es_interpretacion_y_descarta_cifras_o_conexiones_inventadas():
    f=DI.ficha(_linea([(0,0),(100,0)]),"Agua",largo_ft=100,catalogo=nc.nuevo())
    assert DI._interpretacion({"motivo":'Propongo 8" para una posible distribución principal por su trazado.'},f).startswith("Interpretación:")
    assert not DI._interpretacion({"motivo":'El diámetro es 900".'},f)
    assert not DI._interpretacion({"motivo":'La conexión hidráulica está confirmada.'},f)
    assert not DI._interpretacion({"motivo":'El rótulo de drenaje prueba este diámetro.'},f)
