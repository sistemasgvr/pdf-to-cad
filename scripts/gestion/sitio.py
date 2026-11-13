"""Sitio PÚBLICO del cliente (se publica en Cloudflare Pages; cualquiera con el link lo ve). Solo lleva lo
aprobado: el `estado` oficial de cada función y pieza, las versiones con `publicada = true` y textos para el
cliente. Nunca: propuesto, aprobado, notas internas, responsables, issues."""
from __future__ import annotations

import html
import os
import shutil

import datos as D

E = html.escape

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2730;--muted:#5d6b76;--line:#e1e6ea;--accent:#4f46e5;--soft:#eef0fd}
@media (prefers-color-scheme:dark){:root{--bg:#12161b;--card:#1b2128;--text:#e6ebef;--muted:#9aa7b1;
--line:#2c343d;--accent:#8b85ff;--soft:#24264a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif}
a{color:var(--accent)}header.top{background:var(--card);border-bottom:1px solid var(--line)}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
header.top .wrap{display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap;
padding-top:14px;padding-bottom:14px}
.marca{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px}
.marca i{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:9px;background:var(--accent);
color:#fff;font-style:normal}
nav a{margin-left:14px;text-decoration:none;color:var(--muted);font-weight:600}nav a.on{color:var(--accent)}
h1{font-size:26px;margin:28px 0 4px}h2{font-size:19px;margin:30px 0 10px}.sub{color:var(--muted);margin:0 0 18px}
.leyenda{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 11px;font-size:13px;
font-weight:600;border:1px solid transparent;cursor:default;white-space:nowrap}
button.pill{cursor:pointer;font:inherit;font-size:13px;font-weight:600}button.pill.off{opacity:.35}
.barra{display:flex;height:10px;border-radius:6px;overflow:hidden;background:var(--line);margin:6px 0 2px}
.area{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:18px 0}
.area>h2{margin:0}.area .sub{margin:2px 0 8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-top:12px}
.grupo{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--bg)}
.grupo h3{font-size:15px;margin:0}.grupo .det{color:var(--muted);font-size:13px}
.grupo ul{list-style:none;padding:0;margin:8px 0 0}.grupo li{display:flex;gap:8px;align-items:flex-start;
padding:4px 0;font-size:14px}.dot{flex:0 0 11px;height:11px;border-radius:50%;margin-top:5px}
.grupo li .est{margin-left:auto;font-size:11px;color:var(--muted);white-space:nowrap}
.buscar{width:100%;max-width:340px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;
background:var(--card);color:var(--text);font:inherit}
.vers{display:grid;gap:10px}.ver{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 16px;text-decoration:none;color:var(--text)}.ver b{font-size:16px}.ver span{color:var(--muted)}
.nov{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:8px 0}
.nov b{display:block}.nov .det{color:var(--muted)}.nov .obs{font-size:12px;color:var(--accent);margin-top:4px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card .img{aspect-ratio:4/3;background:var(--bg);display:grid;place-items:center;color:var(--muted)}
.card img{width:100%;height:100%;object-fit:contain}.card .t{padding:10px 12px}.card .t b{display:block}
.card .t .det{color:var(--muted);font-size:13px}.mas{font-size:12px;color:var(--muted)}
footer{color:var(--muted);font-size:12px;padding:30px 0}.oculto{display:none!important}
"""


def pill(estado, cliente=True, extra=""):
    n_int, n_cli, fondo, letra = D.ESTADOS.get(estado, D.ESTADOS[""])
    texto = n_cli if cliente else n_int
    return (f'<span class="pill" style="background:{fondo};color:{letra}">{E(texto or "—")}{extra}</span>'
            if (texto or not cliente) else "")


def barra(c):
    total = sum(c.values()) or 1
    return '<div class="barra">' + "".join(
        f'<span style="width:{100 * n / total:.2f}%;background:{D.ESTADOS[e][2]}"></span>'
        for e, n in c.items() if n) + "</div>"


def pagina(pr, titulo, cuerpo, activo, admin=False):
    nav = [("index.html", "Funciones"), ("versiones.html", "Versiones"), ("catalogo.html", "Piezas")]
    enlaces = "".join(f'<a href="{h}" class="{"on" if h == activo else ""}">{t}</a>' for h, t in nav)
    if admin:
        enlaces = '<a href="/" class="on">Administrador</a>'
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{E(titulo)} · {E(pr.nombre)}</title><style>{CSS}</style></head><body>
<header class="top"><div class="wrap"><div class="marca"><i>P</i>{E(pr.nombre)}</div><nav>{enlaces}</nav></div></header>
<main class="wrap">{cuerpo}</main><footer class="wrap">{E(pr.nombre)} · versión {E(pr.version_actual)}</footer>
</body></html>"""


# ───────────────────────── vista general ─────────────────────────

def _items_area(pr, area):
    out = []
    for g in _grupos_con_algo(pr, area.id):
        out += pr.funciones_de(g.id)
    return out


def _grupos_con_algo(pr, gid):
    out = []
    g = pr.grupo(gid)
    if g and (pr.funciones_de(gid) or g.catalogo):
        out.append(g)
    for h in pr.hijos(gid):
        out += _grupos_con_algo(pr, h.id)
    return out


def _leyenda(c, filtrable=True):
    partes = []
    for e in D.ORDEN_ESTADOS:
        if not c.get(e) or not D.ESTADOS[e][1]:
            continue
        _i, nombre, fondo, letra = D.ESTADOS[e]
        if filtrable:
            partes.append(f'<button class="pill" data-estado="{e}" style="background:{fondo};color:{letra}" '
                          f'aria-pressed="true">{E(nombre)} · {c[e]}</button>')
        else:
            partes.append(pill(e, extra=f" · {c[e]}"))
    return '<div class="leyenda">' + "".join(partes) + "</div>"


def grupo_html(pr, g, cliente=True, sufijo_item=None):
    items = []
    for f in pr.funciones_de(g.id):
        _i, n_cli, fondo, _l = D.ESTADOS.get(f.estado, D.ESTADOS[""])
        extra = sufijo_item(f) if sufijo_item else ""
        items.append(f'<li data-estado="{E(f.estado)}" data-texto="{E(f.nombre.lower())}" id="f-{E(f.id)}">'
                     f'<span class="dot" style="background:{fondo}"></span><span>{E(f.nombre)}{extra}</span>'
                     f'<span class="est">{E(n_cli if cliente else D.ESTADOS[f.estado][0])}</span></li>')
    if g.catalogo:
        piezas = [fi for fi in pr.fichas_de(g.catalogo) if fi.estado or not cliente]
        c = D.conteo(piezas)
        items.append(f'<li><span class="dot" style="background:var(--accent)"></span><span>'
                     f'<a href="catalogo.html#{E(g.catalogo)}">{len(piezas)} pieza(s) en el catálogo</a>'
                     f'{"" if not piezas else " · " + str(c["probado"]) + " disponibles"}</span></li>')
    det = f'<div class="det">{E(g.detalle)}</div>' if g.detalle else ""
    return f'<div class="grupo"><h3>{E(g.nombre)}</h3>{det}<ul>{"".join(items)}</ul></div>'


JS_FILTRO = """<script>
const est=new Set();document.querySelectorAll('button.pill[data-estado]').forEach(b=>b.onclick=()=>{
const e=b.dataset.estado;est.has(e)?est.delete(e):est.add(e);b.classList.toggle('off',est.has(e));
b.setAttribute('aria-pressed',!est.has(e));fil()});const q=document.getElementById('q');q&&(q.oninput=fil);
function fil(){const t=(q&&q.value||'').toLowerCase();document.querySelectorAll('li[data-estado]').forEach(li=>
li.classList.toggle('oculto',est.has(li.dataset.estado)||(t&&!li.dataset.texto.includes(t))));
document.querySelectorAll('.grupo').forEach(g=>g.classList.toggle('oculto',
!!t&&!g.querySelector('li[data-estado]:not(.oculto)')))}</script>"""


def vista_general(pr):
    c = D.conteo(pr.funciones)
    partes = [f"<h1>Funciones del proyecto</h1><p class='sub'>Vista general · versión {E(pr.version_actual)} · "
              f"{len(pr.funciones)} funciones</p>", barra(c), _leyenda(c),
              '<input id="q" class="buscar" placeholder="Buscar una función…" aria-label="Buscar una función">']
    for area in pr.raices():
        fs = _items_area(pr, area)
        grupos = _grupos_con_algo(pr, area.id)
        if not grupos:
            continue
        partes.append(f'<section class="area"><h2>{E(area.nombre)}</h2>'
                      f'<p class="sub">{E(area.detalle)}{" · " if area.detalle else ""}{len(fs)} funciones</p>'
                      f'{barra(D.conteo(fs))}<div class="grid">'
                      + "".join(grupo_html(pr, g) for g in grupos) + "</div></section>")
    return pagina(pr, "Funciones", "".join(partes) + JS_FILTRO, "index.html")


# ───────────────────────── versiones ─────────────────────────

def publicadas(pr):
    return [v for v in pr.versiones if v.publicada]


def lista_versiones(pr):
    vs = publicadas(pr)
    cuerpo = ["<h1>Versiones</h1><p class='sub'>Lo que trae cada entrega.</p><div class='vers'>"]
    for v in vs:
        c = {t: sum(1 for n in v.novedades if n.get("tipo") == t) for t in D.TIPOS_NOVEDAD}
        resumen = " · ".join(f"{n} {D.TIPOS_NOVEDAD[t].lower()}" for t, n in c.items() if n)
        cuerpo.append(f'<a class="ver" href="version-{E(v.numero)}.html"><b>Versión {E(v.numero)}</b> '
                      f'<span>{E(v.fecha)}</span><div>{E(v.titulo)}</div><span>{E(resumen)}</span></a>')
    if not vs:
        cuerpo.append("<p class='sub'>Aún no hay versiones publicadas.</p>")
    return pagina(pr, "Versiones", "".join(cuerpo) + "</div>", "versiones.html")


def novedades_html(v, nombres_funcion=None):
    partes = []
    for tipo, titulo in D.TIPOS_NOVEDAD.items():
        ns = [n for n in v.novedades if n.get("tipo") == tipo]
        if not ns:
            continue
        partes.append(f"<h2>{titulo}</h2>")
        for n in ns:
            obs = f'<div class="obs">Atiende: {E(n["observacion"])}</div>' if n.get("observacion") else ""
            det = f'<div class="det">{E(n.get("detalle", ""))}</div>' if n.get("detalle") else ""
            fun = ""
            if nombres_funcion and n.get("funciones"):
                fun = '<div class="mas">' + " · ".join(
                    f'<a href="index.html#f-{E(fid)}">{E(nombres_funcion.get(fid, fid))}</a>'
                    for fid in n["funciones"]) + "</div>"
            partes.append(f'<div class="nov"><b>{E(n.get("titulo", ""))}</b>{det}{obs}{fun}</div>')
    if v.pendientes:
        partes.append("<h2>Para la próxima entrega</h2>")
        partes += [f'<div class="nov"><b>{E(p.get("titulo", ""))}</b>'
                   f'{"<div class=det>" + E(p["detalle"]) + "</div>" if p.get("detalle") else ""}</div>'
                   for p in v.pendientes]
    return "".join(partes)


def pagina_version(pr, v):
    nombres = {f.id: f.nombre for f in pr.funciones}
    cab = (f"<h1>Versión {E(v.numero)}</h1><p class='sub'>{E(v.fecha)}{' · ' if v.fecha else ''}{E(v.titulo)}</p>"
           + (f"<p>{E(v.resumen)}</p>" if v.resumen else ""))
    return pagina(pr, f"Versión {v.numero}", cab + novedades_html(v, nombres), "versiones.html")


# ───────────────────────── catálogo ─────────────────────────

def catalogo(pr, publico=True, ruta_img=lambda fi, a: f"catalogo/{fi.id}/{a}"):
    fichas = [fi for fi in pr.fichas if fi.estado or not publico]
    areas = {}
    for fi in fichas:
        areas.setdefault(fi.area or "otras", []).append(fi)
    nombres_area = {g.catalogo: g.nombre for g in pr.grupos if g.catalogo}
    partes = ["<h1>Catálogo de piezas</h1><p class='sub'>Piezas que el sistema crea de forma automática.</p>"]
    if not fichas:
        partes.append("<p class='sub'>Aún no hay piezas publicadas.</p>")
    for area, fs in areas.items():
        partes.append(f'<h2 id="{E(area)}">{E(nombres_area.get(area, area))}</h2>{_leyenda(D.conteo(fs), False)}'
                      '<div class="cards">')
        for fi in sorted(fs, key=lambda x: (x.tipo, x.nombre)):
            img = (f'<img src="{E(ruta_img(fi, fi.capturas[0]))}" alt="{E(fi.nombre)}" loading="lazy">'
                   if fi.capturas else "Sin captura")
            tam = f'<div class="mas">Tamaños: {E(fi.tamanos)}</div>' if fi.tamanos else ""
            partes.append(f'<div class="card"><div class="img">{img}</div><div class="t">'
                          f'<span class="mas">{E(fi.tipo)}</span><b>{E(fi.nombre)}</b>'
                          f'<div class="det">{E(fi.descripcion)}</div>{tam}'
                          f'<div style="margin-top:6px">{pill(fi.estado, cliente=publico)}</div></div></div>')
        partes.append("</div>")
    return "".join(partes)


# ───────────────────────── generar ─────────────────────────

def generar(pr, destino):
    """Escribe el sitio público en `destino` (lo vacía antes). Devuelve la lista de archivos."""
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    os.makedirs(destino)
    archivos = {"index.html": vista_general(pr), "versiones.html": lista_versiones(pr),
                "catalogo.html": pagina(pr, "Piezas", catalogo(pr), "catalogo.html")}
    for v in publicadas(pr):
        archivos[f"version-{v.numero}.html"] = pagina_version(pr, v)
    for nombre, texto in archivos.items():
        with open(os.path.join(destino, nombre), "w", encoding="utf-8") as f:
            f.write(texto)
    for fi in pr.fichas:
        if fi.estado:
            dst = os.path.join(destino, "catalogo", *fi.id.split("/"))
            os.makedirs(dst, exist_ok=True)
            for a in fi.capturas:
                shutil.copy2(os.path.join(fi.carpeta, a), os.path.join(dst, a))
    with open(os.path.join(destino, "_headers"), "w", encoding="utf-8") as f:
        f.write("/*\n  X-Robots-Tag: noindex\n")
    return sorted(archivos)
