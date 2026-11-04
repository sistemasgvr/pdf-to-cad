"""Las zonas de la hoja original que la IA del diámetro puede pedir ver (fitz, sin Qt; pedido del usuario 2026-11-03:
«que la IA decida de qué lado tomar la captura, o el membrete, o la leyenda»).

`menu` da cada zona con un adelanto de lo que dice, para que la IA elija con criterio y no a ciegas; `leer` da su
captura, su texto y los diámetros escritos. Trabaja sobre las hojas de ORIGEN (`contexto_original`): lo que el recorte
dejó fuera sigue ahí, y por eso sirve igual con capas, en los mapas y en los PDF sin capas ni leyenda. Los lados son los
de la hoja como se ve, tomados desde la línea. Coordenadas en pt de la vista.
"""
from __future__ import annotations

import re
from contextlib import ExitStack

import fitz

from hoja import contexto_diametro, contexto_original
from traduccion.i18n_core import N_

LADOS = ("izquierda", "derecha", "arriba", "abajo")
TITULOS = {"izquierda": N_("a la izquierda de la línea"), "derecha": N_("a la derecha de la línea"),
           "arriba": N_("arriba de la línea"), "abajo": N_("abajo de la línea"), "membrete": N_("el membrete"),
           "leyenda": N_("la leyenda"), "notas": N_("las notas")}
LADO_MIN_PT, LADO_MAX_PT = 260.0, 520.0
ZONA_MIN_PT = 40.0            # una franja más angosta no tiene nada que mostrar
FRANJA = 0.14                 # el membrete va en una franja del borde de la hoja (abajo, salvo que otra lo diga)
TITULO_LETRAS = 24            # «GENERAL NOTES» abre su bloque: «NOTA DEL LADO…» en medio de otro texto no es un título
HOJAS_MAX = 60                # la leyenda puede estar en otra hoja del PDF: hasta aquí se busca
ADELANTO = 140
MAX_DIAMETROS = 6
MAX_TEXTO = 2500
DIAM_MIN_IN, DIAM_MAX_IN = 0.25, 144.0

RX_MEMBRETE = re.compile(r"\b(?:SHEET|DWG|DRAWN|DESIGNED|CHECKED|APPROVED|REVISIONS?|PROJECT|CONTRACT|TITLE|"
                         r"LAMINA|PLANO|REVISI[OÓ]N)\b", re.I)
RX_LEYENDA = re.compile(r"\b(?:LEGEND|LEYENDA|SYMBOLS?|ABBREVIATIONS)\b", re.I)
RX_NOTAS = re.compile(r"\b(?:NOTES?|NOTAS?)\b", re.I)
# «3/4"», «1-1/4"», «12"»; no «2-4"» (dos conductos) ni «1" = 100'» (la escala)
RX_DIAM = re.compile(r"(?<![\d/.\-])(\d+-\d+/\d+|\d+/\d+|\d{1,3}(?:\.\d+)?)\s*(?:\"|”|″)(?!\s*=)")


def _pulgadas(txt: str):
    try:
        if "-" in txt:
            a, b = txt.split("-", 1)
            return int(a) + _pulgadas(b)
        if "/" in txt:
            a, b = txt.split("/", 1)
            return int(a) / int(b)
        return float(txt)
    except (ValueError, ZeroDivisionError):
        return None


def diametros(texto: str) -> list:
    out = []
    for m in RX_DIAM.finditer(texto or ""):
        d = _pulgadas(m.group(1))
        if d and DIAM_MIN_IN <= d <= DIAM_MAX_IN and d not in out:
            out.append(d)
    return out


def _textos(page) -> list:
    """[(caja en la vista, texto)] de la hoja."""
    out = []
    for b in contexto_diametro.bloques(page, leer_forma=True):
        if len(b) >= 7 and b[6] == 0 and re.search(r"[^\W_]{2}", str(b[4])):      # sin puntos ni símbolos sueltos
            out.append((fitz.Rect(b[:4]) * page.rotation_matrix, " ".join(str(b[4]).split())))
    return out


def _dentro(textos, region) -> list:
    r = fitz.Rect(region)
    return [t for c, t in textos if c.intersects(r)]


def _caja(lineas) -> fitz.Rect:
    pts = [q for linea in lineas for q in linea]
    return fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _lados(page, lineas) -> dict:
    b = _caja(lineas)
    lado = min(LADO_MAX_PT, max(LADO_MIN_PT, b.width, b.height))
    cx, cy = (b.x0 + b.x1) / 2.0, (b.y0 + b.y1) / 2.0
    alto, ancho = max(b.height, lado) / 2.0, max(b.width, lado) / 2.0
    out = {"izquierda": fitz.Rect(b.x0 - lado, cy - alto, b.x0, cy + alto),
           "derecha": fitz.Rect(b.x1, cy - alto, b.x1 + lado, cy + alto),
           "arriba": fitz.Rect(cx - ancho, b.y0 - lado, cx + ancho, b.y0),
           "abajo": fitz.Rect(cx - ancho, b.y1, cx + ancho, b.y1 + lado)}
    return {k: r & page.rect for k, r in out.items()
            if not (r & page.rect).is_empty and min((r & page.rect).width, (r & page.rect).height) >= ZONA_MIN_PT}


def _membrete(page, textos, con_imagen=False):
    w, h = page.rect.width, page.rect.height
    franjas = [fitz.Rect(0, h * (1 - FRANJA), w, h), fitz.Rect(w * (1 - FRANJA), 0, w, h),
               fitz.Rect(0, 0, w * FRANJA, h), fitz.Rect(0, 0, w, h * FRANJA)]
    puntos = [sum(bool(RX_MEMBRETE.search(t)) for t in _dentro(textos, f)) for f in franjas]
    if max(puntos):
        return franjas[puntos.index(max(puntos))]
    return franjas[0] if con_imagen or _dentro(textos, franjas[0]) else None


def _bajo_titulo(page, textos, rx):
    """La zona bajo el título «LEGEND» / «NOTES»: los cuadros van bajo su encabezado."""
    cajas = [c for c, t in textos if rx.search(t[:TITULO_LETRAS])]
    if not cajas:
        return None
    c = cajas[0]
    w, h = page.rect.width, page.rect.height
    return fitz.Rect(c.x0 - 20, c.y0 - 10, c.x0 + w * 0.3, c.y0 + h * 0.4) & page.rect


def _en_otra_hoja(doc, actual, rx):
    """La primera hoja del PDF con ese título, si no está en la que se mira."""
    for n in range(min(len(doc), HOJAS_MAX)):
        if n != actual and rx.search(doc[n].get_text("text")[:20000] or ""):
            return n
    return None


def _plan_de(planes):
    """La hoja donde más línea hay (`contexto_original.reunir`)."""
    con = [p for p in planes or () if p.get("lineas")]
    return max(con, key=lambda p: sum(len(x) for x in p["lineas"]), default=None)


def menu(fuentes, planes, trabajo=None, con_imagen=False) -> list:
    """[{id, titulo, documento, pagina (1…), fuente, hoja, region, lineas, adelanto, diametros}]: las zonas con algo
    que mirar. Una zona sin texto solo vale si el modelo puede ver la imagen."""
    plan = _plan_de(planes)
    if plan is None:
        return []
    out = []
    with ExitStack() as pila:
        doc = contexto_original._abrir(fuentes, plan["fuente"], pila, {}, trabajo)
        page = doc[plan["pagina"]]
        textos = _textos(page)
        zonas = [(k, plan["pagina"], r) for k, r in _lados(page, plan["lineas"]).items()]
        m = _membrete(page, textos, con_imagen)
        if m is not None:
            zonas.append(("membrete", plan["pagina"], m))
        for clave, rx in (("leyenda", RX_LEYENDA), ("notas", RX_NOTAS)):
            r = _bajo_titulo(page, textos, rx)
            hoja = plan["pagina"]
            if r is None and (otra := _en_otra_hoja(doc, hoja, rx)) is not None:
                hoja, r = otra, _bajo_titulo(doc[otra], _textos(doc[otra]), rx)
            if r is not None:
                zonas.append((clave, hoja, r))
        for clave, hoja, r in zonas:
            ts = _dentro(textos if hoja == plan["pagina"] else _textos(doc[hoja]), r)
            if not ts and not con_imagen:
                continue
            ts.sort(key=lambda x: not diametros(x))        # lo que dice un diámetro va primero en el adelanto
            junto = " · ".join(ts)
            out.append(dict(id=clave, titulo=TITULOS[clave], documento=plan["documento"], pagina=hoja + 1,
                            fuente=plan["fuente"], hoja=hoja, region=[round(v, 2) for v in r],
                            lineas=plan["lineas"] if hoja == plan["pagina"] else [], adelanto=junto[:ADELANTO],
                            diametros=diametros(junto)[:MAX_DIAMETROS]))
    return out


def leer(fuentes, zona: dict, trabajo=None) -> dict:
    """{"texto", "opciones": [{diam_in, texto}], "captura"} de una zona del `menu`."""
    with ExitStack() as pila:
        doc = contexto_original._abrir(fuentes, zona["fuente"], pila, {}, trabajo)
        ts = _dentro(_textos(doc[zona["hoja"]]), zona["region"])
    opciones = []
    for t in ts:
        for d in diametros(t):
            if all(o["diam_in"] != d for o in opciones):
                opciones.append(dict(diam_in=d, texto=t[:200]))
    plan = dict(fuente=zona["fuente"], pagina=zona["hoja"], documento=zona["documento"], zona=zona["titulo"],
                region=zona["region"], lineas=zona["lineas"])
    capturas = contexto_original.capturas(fuentes, [plan], trabajo=trabajo)
    return dict(texto=" · ".join(ts)[:MAX_TEXTO], opciones=opciones[:MAX_DIAMETROS],
                captura=capturas[0] if capturas else None)
