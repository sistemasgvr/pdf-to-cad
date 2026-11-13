"""draw.io ↔ funciones.toml. `importar` lee el diagrama hecho a mano (cajas unidas por flechas; el color de cada
función es su estado) y `exportar` arma un .drawio con el MISMO aspecto desde los datos, para retocarlo a mano si
hace falta. La fuente de verdad es funciones.toml."""
from __future__ import annotations

import html
import re
import unicodedata
from xml.sax.saxutils import escape

import datos as D

# Leyenda del diagrama del equipo (2026-11-11): verde = OK, magenta = TESTEAR, rojo = OPTIMIZAR.
COLOR_A_ESTADO = {"#008a00": "probado", "#d80073": "falta_probar", "#e51400": "optimizar",
                  "#1ba1e2": "en_desarrollo", "#f0a30a": "optimizar", "#fa6800": "optimizar"}
ESTADO_A_COLOR = {"probado": "#008a00", "falta_probar": "#d80073", "optimizar": "#e51400",
                  "en_desarrollo": "#1ba1e2"}
COLORES_GRUPO = {"#2f4352"}                     # caja de grupo (aunque aún no tenga funciones)
COLORES_AREA = {"#5b6f7c", "#e0662f"}           # raíz y áreas (App, Plugin, MCP)
ID_AREA = (("mcp", "mcp"), ("plugin", "plugin"), ("aplicaci", "app"))   # (palabra del nombre, id)


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40] or "x"


def _celdas(xml):
    """→ ({id: (líneas de texto, color, x, y)}, [(origen, destino)])."""
    vertices, aristas = {}, []
    for m in re.finditer(r"<mxCell ([^>]*?)/?>\s*(<mxGeometry [^>]*>)?", xml):
        attrs, geo = m.group(1), m.group(2) or ""
        g = lambda k: (re.search(r"(?<![\w-])" + k + r'="([^"]*)"', attrs) or [None, None])[1]   # noqa: E731
        estilo = g("style") or ""
        if 'edge="1"' in attrs:
            aristas.append((g("source"), g("target")))
        elif 'vertex="1"' in attrs:
            v = html.unescape(html.unescape(g("value") or ""))
            partes = [re.sub(r"<[^>]+>", " ", p).strip() for p in re.split(r"<br\s*/?>|</div>|</b>", v)]
            partes = [re.sub(r"\s+", " ", p) for p in partes if p.strip()]
            color = (re.search(r"fillColor=([^;]+)", estilo) or [None, None])[1]
            num = lambda k: float((re.search(r"(?<![\w-])" + k + r'="([-\d.]+)"', geo) or [0, "0"])[1])   # noqa: E731
            vertices[g("id")] = (partes, (color or "").lower(), num("x"), num("y"))
    return vertices, aristas


def _ignorar(v):
    texto = " ".join(v[0]).strip()
    return (v[3] < 0 or len(texto) <= 2 or texto.strip("-") == ""
            or (not v[1] or v[1] == "none") and len(texto) < 6)


def importar(path, admin="Deyvy", version="2.0.0"):
    """→ Proyecto (sin versiones ni fichas). Raíz = caja con «Versión»; áreas = cajas naranja/gris; grupos = cajas
    oscuras; funciones = el resto. Las cajas SIN flecha se cuelgan de la caja que tienen justo encima en la misma
    columna (así se dibujan las listas); un grupo colgado de una función pasa a su área."""
    with open(path, encoding="utf-8") as f:
        vertices, aristas = _celdas(f.read())
    vertices = {k: v for k, v in vertices.items() if not _ignorar(v)}
    padre = {}
    for a, b in aristas:
        if a in vertices and b in vertices:
            padre.setdefault(b, a)
    raiz = next(k for k, v in vertices.items() if v[1] in COLORES_AREA and "Versi" in " ".join(v[0]))
    es_area = lambda k: vertices[k][1] in COLORES_AREA and k != raiz             # noqa: E731
    es_grupo = lambda k: vertices[k][1] in COLORES_GRUPO                         # noqa: E731
    for k, v in vertices.items():                        # áreas sueltas: cuelgan de la raíz
        if k != raiz and es_area(k):
            padre.setdefault(k, raiz)
    sueltos = sorted((k for k in vertices if k not in padre and k != raiz), key=lambda k: vertices[k][3])
    for k in sueltos:
        _t, _c, x, y = vertices[k]
        arriba = [o for o in vertices if o != k and abs(vertices[o][2] - x) <= 24 and 0 < y - vertices[o][3] <= 140]
        if arriba:
            o = max(arriba, key=lambda o: vertices[o][3])
            padre[k] = o if (es_grupo(o) and not es_grupo(k)) or es_area(o) else padre.get(o, raiz)
        elif es_grupo(k):
            area = min((a for a in vertices if es_area(a)), key=lambda a: abs(vertices[a][2] - x))
            padre[k] = area

    def area_de(k):
        while k in padre and not es_area(k) and k != raiz:
            k = padre[k]
        return k

    for k in list(padre):                                # grupo colgado de una función → a su área
        if es_grupo(k) and not es_area(padre[k]) and padre[k] != raiz:
            padre[k] = area_de(padre[k])
    hijos = {}
    for k in sorted(vertices, key=lambda k: (vertices[k][2], vertices[k][3])):
        if k in padre:
            hijos.setdefault(padre[k], []).append(k)
    for k in hijos:
        # en orden de lectura: filas de arriba abajo y, en cada fila, de izquierda a derecha
        hijos[k].sort(key=lambda h: (round(vertices[h][3] / 40), vertices[h][2]))
    grupos, funciones, usados = [], [], set()

    def nuevo_id(base):
        i, n = base, 2
        while i in usados:
            i, n = f"{base}-{n}", n + 1
        usados.add(i)
        return i

    def recorrer(nodo, padre_id):
        partes, color, _x, _y = vertices[nodo]
        nombre, detalle = partes[0], " · ".join(partes[1:])
        if es_area(nodo):
            gid = next((i for p, i in ID_AREA if p in nombre.lower()), slug(nombre))
            usados.add(gid)
            grupos.append(D.Grupo(id=gid, nombre=nombre, detalle=detalle))
        elif hijos.get(nodo) or es_grupo(nodo):
            gid = nuevo_id(padre_id + "." + slug(nombre))
            grupos.append(D.Grupo(id=gid, nombre=nombre, padre=padre_id, detalle=detalle))
        else:
            estado = COLOR_A_ESTADO.get(color, "")
            funciones.append(D.Funcion(id=nuevo_id(padre_id + "." + slug(nombre)), grupo=padre_id,
                                       nombre=" ".join(partes), estado=estado, desde=version,
                                       aprobado=f"{admin} (draw.io)" if estado else ""))
            return
        for h in hijos.get(nodo, []):
            recorrer(h, gid)

    for h in hijos.get(raiz, []):
        recorrer(h, "")
    nombre_proy = re.sub(r"\s*Versi[oó]n.*", "", " ".join(vertices[raiz][0])).strip()
    return D.Proyecto(nombre=nombre_proy, version_actual=version, admin=admin, sitio="", grupos=grupos,
                      funciones=funciones, versiones=[], fichas=[])


# ───────────────────────── exportar ─────────────────────────

ANCHO, ALTO_F, SEP = 230, 34, 8


def exportar(pr: D.Proyecto, path, version=None):
    """Árbol: proyecto arriba, áreas debajo, grupos en columnas con sus funciones apiladas (color = estado).
    Con `version`, solo las funciones que esa versión menciona (y sus grupos)."""
    filtro = None
    if version:
        v = next((x for x in pr.versiones if x.numero == version), None)
        filtro = {fid for n in (v.novedades if v else []) for fid in n.get("funciones", [])}
    celdas, ids = [], iter(range(10, 10 ** 7))

    def caja(texto, x, y, w, h, fondo, letra, tam=12, negrita=False):
        i = f"n{next(ids)}"
        valor = escape(f"<b>{texto}</b>" if negrita else texto, {'"': "&quot;"})
        celdas.append(f'<mxCell id="{i}" value="{valor}" style="rounded=1;whiteSpace=wrap;html=1;arcSize=12;'
                      f'fillColor={fondo};strokeColor=none;fontColor={letra};fontSize={tam};" vertex="1" '
                      f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return i

    def flecha(a, b):
        celdas.append(f'<mxCell id="n{next(ids)}" edge="1" parent="1" source="{a}" target="{b}" '
                      'style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;strokeColor=#8a99a3;">'
                      '<mxGeometry relative="1" as="geometry"/></mxCell>')

    def hojas(g):
        fs = [f for f in pr.funciones_de(g.id) if filtro is None or f.id in filtro]
        return fs

    x = 40
    raiz = caja(f"{pr.nombre}<br>Versión {version or pr.version_actual}", 40, 20, 320, 60, "#e0662f", "#ffffff",
                16, True)
    for area in pr.raices():
        grupos = [g for g in _descendientes(pr, area.id) if hojas(g)]
        if not grupos and filtro is not None:
            continue
        a = caja(area.nombre, x, 130, ANCHO, 50, "#5b6f7c", "#ffffff", 14, True)
        flecha(raiz, a)
        for g in grupos:
            gx = x
            gi = caja(g.nombre, gx, 220, ANCHO, 44, "#2f4352", "#ffffff", 13, True)
            flecha(a, gi)
            y = 280
            for f in hojas(g):
                _n, _c, fondo, letra = D.ESTADOS.get(f.estado, D.ESTADOS[""])
                if f.estado in ESTADO_A_COLOR:                  # los colores de la leyenda del equipo
                    fondo, letra = ESTADO_A_COLOR[f.estado], "#ffffff"
                fi = caja(f.nombre, gx + 16, y, ANCHO - 16, ALTO_F, fondo, letra, 11)
                flecha(gi, fi)
                y += ALTO_F + SEP
            x += ANCHO + 30
        x += 40
    xml = ('<mxfile host="pdf-a-cad"><diagram name="Funciones"><mxGraphModel grid="1" page="0"><root>'
           '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(celdas) + "</root></mxGraphModel></diagram></mxfile>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def _descendientes(pr, gid):
    """Grupos debajo de `gid` (en orden), incluido él si tiene funciones."""
    out = []
    g = pr.grupo(gid)
    if g and pr.funciones_de(gid):
        out.append(g)
    for h in pr.hijos(gid):
        out += _descendientes(pr, h.id)
    return out
