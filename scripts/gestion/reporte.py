"""Reporte de una entrega para el cliente: PDF corto (títulos y subtítulos, sin tecnicismos) + texto listo para
pegar en WhatsApp. Sale de `gestion/versiones/<numero>.toml`, el mismo que alimenta el sitio."""
from __future__ import annotations

import html
import os

import datos as D

E = html.escape

CSS_PDF = """
* { font-family: sans-serif; }
body { color: #1d2730; font-size: 10.5pt; }
h1 { font-size: 20pt; color: #4f46e5; margin: 0 0 2pt 0; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; color: #1d2730; border-bottom: 1px solid #d9dee3; }
p.sub { color: #5d6b76; margin: 0 0 8pt 0; }
p.t { font-weight: bold; margin: 6pt 0 0 0; }
p.d { color: #5d6b76; margin: 1pt 0 0 0; }
p.o { color: #4f46e5; font-size: 9pt; margin: 1pt 0 0 0; }
p.pie { color: #5d6b76; font-size: 9pt; margin-top: 16pt; }
"""


def _version(pr, numero):
    v = next((x for x in pr.versiones if x.numero == numero), None)
    if not v:
        raise ValueError(f"No existe gestion/versiones/{numero}.toml")
    return v


def html_reporte(pr, v):
    partes = [f"<h1>{E(pr.nombre)} · Versión {E(v.numero)}</h1>",
              f"<p class='sub'>{E(v.fecha)}{' · ' if v.fecha and v.titulo else ''}{E(v.titulo)}</p>"]
    if v.resumen:
        partes.append(f"<p>{E(v.resumen)}</p>")
    for tipo, titulo in D.TIPOS_NOVEDAD.items():
        ns = [n for n in v.novedades if n.get("tipo") == tipo]
        if not ns:
            continue
        partes.append(f"<h2>{titulo}</h2>")
        for n in ns:
            partes.append(f"<p class='t'>{E(n.get('titulo', ''))}</p>")
            if n.get("detalle"):
                partes.append(f"<p class='d'>{E(n['detalle'])}</p>")
            if n.get("observacion"):
                partes.append(f"<p class='o'>Atiende su observación: {E(n['observacion'])}</p>")
    if v.pendientes:
        partes.append("<h2>Para la próxima entrega</h2>")
        for p in v.pendientes:
            partes.append(f"<p class='t'>{E(p.get('titulo', ''))}</p>")
            if p.get("detalle"):
                partes.append(f"<p class='d'>{E(p['detalle'])}</p>")
    if pr.sitio:
        partes.append(f"<p class='pie'>Diagrama de funciones actualizado: {E(pr.sitio)}</p>")
    return "<body>" + "".join(partes) + "</body>"


def texto_whatsapp(pr, v):
    lineas = [f"*{pr.nombre} · Versión {v.numero}*" + (f" ({v.fecha})" if v.fecha else "")]
    if v.titulo:
        lineas.append(v.titulo)
    for tipo, titulo in D.TIPOS_NOVEDAD.items():
        ns = [n for n in v.novedades if n.get("tipo") == tipo]
        if ns:
            lineas += ["", f"*{titulo}*"] + [f"• {n.get('titulo', '')}" for n in ns]
    if v.pendientes:
        lineas += ["", "*Próxima entrega*"] + [f"• {p.get('titulo', '')}" for p in v.pendientes]
    if pr.sitio:
        lineas += ["", f"Diagrama de funciones: {pr.sitio}"]
    return "\n".join(lineas)


def generar(numero, pr=None, destino=None):
    """→ (ruta del PDF, ruta del .txt)."""
    import fitz
    pr = pr or D.leer()
    v = _version(pr, numero)
    destino = destino or D.ruta("_salida", "reportes")
    os.makedirs(destino, exist_ok=True)
    pdf = os.path.join(destino, f"Entrega-{v.numero}.pdf")
    story = fitz.Story(html=html_reporte(pr, v), user_css=CSS_PDF)
    escritor = fitz.DocumentWriter(pdf)
    pagina, margen = fitz.paper_rect("letter"), 54
    mas = True
    while mas:
        dev = escritor.begin_page(pagina)
        mas, _ = story.place(pagina + (margen, margen, -margen, -margen))
        story.draw(dev)
        escritor.end_page()
    escritor.close()
    txt = os.path.join(destino, f"Entrega-{v.numero}.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(texto_whatsapp(pr, v))
    return pdf, txt
