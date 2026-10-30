"""Contexto de las hojas originales, incluidas las zonas fuera de los recortes.

Los originales permanecen en src_pdfs / sources del proyecto. Este índice no
modifica la composición ni convierte notas globales en rótulos de una tubería.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import hashlib
import os
import re

import fitz
from shapely.geometry import LineString, Polygon, box

from hoja import composite as C

MAX_TEXTO = 7000
MAX_BLOQUES = 48
MAX_CAPTURAS = 3  # además del recorte local ya existente


def _abrir(fuentes, indice, pila, docs, trabajo):
    if indice in docs:
        return docs[indice]
    if not fuentes and indice == 0 and trabajo is not None:
        docs[indice] = trabajo
    else:
        fuente = fuentes[indice]
        data = fuente.get("data")
        doc = fitz.open(stream=data, filetype="pdf") if data else fitz.open(fuente["path"])
        docs[indice] = pila.enter_context(doc)
    return docs[indice]


def _lineas(geom):
    if geom.geom_type == "LineString":
        return [list(geom.coords)] if geom.length > 0.01 else []
    return [p for g in getattr(geom,"geoms",()) for p in _lineas(g)]


def _muestra(lineas):
    out=[]
    for linea in lineas[:3]:
        indices=sorted({round(k*(len(linea)-1)/min(11,len(linea)-1)) for k in range(min(12,len(linea)))})
        out.append([[round(linea[k][0],6),round(linea[k][1],6)] for k in indices])
    return out


def _indice(page, huella, cache):
    clave = (huella, page.number, page.rotation)
    if clave in cache:
        return cache[clave]
    textos = []
    for b in page.get_text("blocks"):
        if len(b) < 7 or b[6] != 0 or not str(b[4]).strip():
            continue
        r = fitz.Rect(b[:4]) * page.rotation_matrix
        textos.append(dict(id=f"T{len(textos)+1}",texto=" ".join(str(b[4]).split()),
                           caja_pt=[round(v,2) for v in r]))
    from reconocimiento.recognition_grosor_texto import lineas_texto, rotulos
    # Agrupar el texto en su orientación nativa; después llevar sus cajas a la
    # vista girada. Girarlo antes convierte rótulos horizontales en verticales.
    rot, _ = rotulos(lineas_texto(page, lambda q:q, 1.0))
    refs = [dict(texto=r.texto,diam_in=r.pulg,utilidad=r.utilidad,
                 caja_pt=list(fitz.Rect(r.bbox)*page.rotation_matrix))
            for r in rot if r.utilidad and r.varios == 1 and not r.otros]
    # No hay límite en el índice conservado; solo en lo enviado a una consulta.
    out = dict(textos=textos,referencias=refs)
    cache[clave] = out
    return out


def reunir(fuentes, comp, puntos, pagina=0, utilidad="", referencias=(), cache=None, trabajo=None):
    """(contexto enviado, plan de imágenes, índice completo auditable).

    puntos: coordenadas de la hoja de trabajo, en puntos visibles (px / zoom).
    Resuelve traslación, giro, escala y recortes poligonales con la misma geometría
    del compositor. Los bytes originales son prioritarios sobre rutas externas.
    """
    cache = cache if cache is not None else {}
    contexto = dict(hojas=[],advertencias=[],alcance="Contexto de hojas originales; asociación con esta línea por comprobar")
    if len(puntos) < 2:
        return contexto, [], []
    with ExitStack() as pila:
        docs = {}
        def doc(src):
            return _abrir(fuentes,src,pila,docs,trabajo)
        objetivos = {}
        try:
            if comp is not None and not comp.is_single_full_page():
                def size(pz):
                    r = doc(pz.source)[pz.page].rect
                    return r.width,r.height
                _,_,dx,dy = C.sheet_geometry(comp,size)
                visibles=puntos
                if trabajo is not None and 0 <= pagina < len(trabajo) and trabajo[pagina].rotation:
                    visibles=[tuple(fitz.Point(q)*trabajo[pagina].derotation_matrix) for q in puntos]
                linea = LineString([(x-dx,y-dy) for x,y in visibles])
                for pz in comp.pieces:
                    poligono = Polygon(C.piece_outline(pz,size(pz),comp.target_scale()))
                    partes = _lineas(linea.intersection(poligono))
                    if not partes:
                        continue
                    inv = C.piece_unmap(pz,size(pz),comp.target_scale())
                    obj = objetivos.setdefault((pz.source,pz.page),dict(lineas=[],areas=[]))
                    obj["lineas"] += [[inv(x,y) for x,y in parte] for parte in partes]
                    w,h = size(pz)
                    if pz.polygon:
                        obj["areas"].append([(x*w,y*h) for x,y in pz.polygon])
                    else:
                        x0,y0,x1,y1 = C.clip_rect_pt((w,h),pz.clip)
                        obj["areas"].append([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
            else:
                src = comp.pieces[0].source if comp and comp.pieces else 0
                page = doc(src)[pagina]
                objetivos[(src,pagina)] = dict(lineas=[puntos],areas=[list(map(tuple,
                    [(0,0),(page.rect.width,0),(page.rect.width,page.rect.height),(0,page.rect.height)]))])
        except (ValueError,IndexError,KeyError,RuntimeError,FileNotFoundError) as e:
            contexto["advertencias"].append("No se pudo recuperar una hoja original: "+str(e)[:150])
        planes, completos = [], []
        anteriores=cache.get("_bytes_actuales",{})
        actuales={}
        tokens = set(re.findall(r"\b(?:CB\s*-?\s*\d+(?:\.\d+)?|[A-Z]{1,3}\d{3,5})\b",
                                " ".join(referencias).upper()))
        presupuesto = MAX_TEXTO
        for (src,hoja),obj in objetivos.items():
            try:
                page = doc(src)[hoja]
                fuente = fuentes[src] if fuentes else {}
                nombre = fuente.get("name") or os.path.basename(page.parent.name or "") or "PDF original"
                dato = fuente.get("data")
                if dato:
                    hit=actuales.get(id(dato)) or anteriores.get(id(dato))
                    huella=hit[1] if hit is not None and hit[0] is dato else hashlib.sha256(dato).hexdigest()
                    actuales[id(dato)]=(dato,huella)
                else:
                    huella=hashlib.sha256(page.parent.tobytes(no_new_id=True)).hexdigest()
                indice = _indice(page,huella,cache)
                area = Polygon(obj["areas"][0])
                for pol in obj["areas"][1:]:
                    area = area.union(Polygon(pol))
                r = area.bounds
                filas=[]
                for t in indice["textos"]:
                    texto=t["texto"]
                    caja=box(*t["caja_pt"])
                    fuera=not area.covers(caja)
                    x0,y0,x1,y1=t["caja_pt"]
                    zona=("membrete" if y0 >= page.rect.height*.86 else
                          "superior / perfiles" if y1 <= r[1]+1 else
                          "lateral / notas" if x0 >= r[2]-1 or x1 <= r[0]+1 else "resto de la hoja")
                    puntos_score = (6 if fuera else 0) + (5 if zona != "resto de la hoja" else 0)
                    puntos_score += 20*sum(tok in texto.upper() for tok in tokens)
                    puntos_score += 4*bool(re.search(r"\b(NOTES?|NOTAS?|LEGEND|PROFILE|LATERAL|DIAM|PIPE|SCALE|SUBMITTAL)\b",texto,re.I))
                    filas.append((puntos_score,dict(t,id=f"O{src+1}P{hoja+1}{t['id']}",zona=zona,fuera_del_area=fuera)))
                seleccion=[]
                cuota=min(presupuesto,max(3500,MAX_TEXTO//max(1,len(objetivos))))
                orden=sorted(filas,key=lambda v:-v[0])
                representantes=[]
                for zona in ("membrete","superior / perfiles","lateral / notas"):
                    representantes.extend([f for f in orden if f[1]["zona"]==zona][:3])
                ids={t["id"] for _,t in representantes}
                orden=representantes+[f for f in orden if f[1]["id"] not in ids]
                for _,t in orden:
                    if cuota <= 0 or len(seleccion)>=max(1,MAX_BLOQUES//max(1,len(objetivos))):
                        break
                    txt=t["texto"][:min(cuota,2400)]
                    seleccion.append(dict(t,texto=txt,recortado=len(txt)<len(t["texto"])))
                    cuota-=len(txt);presupuesto-=len(txt)
                cabecera=dict(fuente=src,pagina=hoja+1,documento=nombre,sha256_pdf=huella,
                              bloques_totales=len(filas),bloques_enviados=len(seleccion),
                              lineas_en_original=_muestra(obj["lineas"]),fragmentos_totales=len(obj["lineas"]),
                              areas_utilizadas=[[[round(x,6),round(y,6)] for x,y in l] for l in obj["areas"]])
                refs=[ref for ref in indice["referencias"] if ref["utilidad"]==utilidad
                      and any(box(*ref["caja_pt"]).intersects(box(*t["caja_pt"])) for t in seleccion)]
                contexto["hojas"].append(dict(cabecera,textos=seleccion,diametros_contextuales=refs[:16]))
                completos.append(dict(cabecera,textos=[t for _,t in filas]))
                planes.append(dict(fuente=src,pagina=hoja,documento=nombre,zona="hoja completa",
                                   region=list(page.rect),lineas=obj["lineas"],prioridad=1000))
                w,h=page.rect.width,page.rect.height
                # Las franjas reales descartadas, o zonas de apoyo en hoja entera.
                bandas=[("superior / perfiles",(0,0,w,max(r[1],h*.5))),
                        ("lateral / notas",(min(r[2],w*.72),0,w,h*.86)),
                        ("membrete",(0,r[3] if r[3]<h*.92 else h*.86,w,h))]
                for zona,region in bandas:
                    if region[2]-region[0]<20 or region[3]-region[1]<20:
                        continue
                    puntuacion=sum(score for score,t in filas if box(*region).intersects(box(*t["caja_pt"])))
                    if puntuacion:
                        base={"superior / perfiles":20,"lateral / notas":19,"membrete":12}[zona]
                        planes.append(dict(fuente=src,pagina=hoja,documento=nombre,zona=zona,region=list(region),
                                           lineas=[],prioridad=base+puntuacion/max(1,len(filas))))
            except (ValueError,IndexError,KeyError,RuntimeError,FileNotFoundError) as e:
                contexto["advertencias"].append("Contexto original no disponible: "+str(e)[:150])
        cache["_bytes_actuales"]=actuales
        elegidos=sorted(planes,key=lambda p:-p["prioridad"])[:MAX_CAPTURAS]
        contexto["capturas_previstas"]=[dict({k:v for k,v in p.items() if k not in ("lineas","prioridad")},
                                              pagina=p["pagina"]+1) for p in elegidos]
        return contexto,elegidos,completos


def capturas(fuentes, planes, trabajo=None):
    """PNG con procedencia explícita y línea marcada en la vista general."""
    resultado=[]
    with ExitStack() as pila:
        docs={}
        for plan in planes:
            doc=_abrir(fuentes,plan["fuente"],pila,docs,trabajo)
            page=doc[plan["pagina"]]
            r=fitz.Rect(plan["region"]) & page.rect
            if r.is_empty:
                continue
            factor=1280/max(r.width,r.height)
            pix=page.get_pixmap(matrix=fitz.Matrix(factor,factor),clip=r,alpha=False)
            # Copia para anotar, sin alterar las capas ni los bytes originales.
            with fitz.open() as copia:
                p=copia.new_page(width=pix.width,height=pix.height)
                p.insert_image(p.rect,pixmap=pix)
                for linea in plan["lineas"]:
                    p.draw_polyline([((x-r.x0)*factor,(y-r.y0)*factor) for x,y in linea],
                                    color=(1,0,1),width=3)
                png=p.get_pixmap(alpha=False).tobytes("png")
            info={k:v for k,v in plan.items() if k not in ("lineas","prioridad")}
            info["pagina"]=plan["pagina"]+1
            info.update(imagen=base64.b64encode(png).decode("ascii"),sha256_png=hashlib.sha256(png).hexdigest())
            resultado.append(info)
    return resultado
