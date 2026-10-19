"""composite_fundir.py — «Fundir bordes» en la hoja compuesta VECTORIAL (PURO, solo fitz).

Pedido del usuario 2026-10-19: lo que ya hacían los escaneos (modo OSCURECER: donde dos piezas
se superponen se ve la tinta de las dos y lo blanco de una no tapa las líneas de la otra) también
en los PDF ploteados (con capas) y en los vectoriales sin capas (mapas SIG de Phoenix).

Un escaneo es UNA imagen por pieza y el modo oscurecer va directo (`composite.build_document`).
Un PDF vectorial trae miles de objetos y, con el modo directo, cada uno se oscurece contra lo de
debajo DENTRO de su propia hoja: el fondo blanco de un rótulo (la «10+00» de DU08 h.22) o el cuadro
opaco de una leyenda dejaban ver la línea que tapan. Por eso la pieza vectorial va como GRUPO de
transparencia AISLADO (`/Group <</S/Transparency/I true>>` en su XObject «fzFrm»): se dibuja
entera como siempre y solo el resultado se oscurece contra las piezas anteriores. Sobre el papel
blanco (fuera de la superposición) oscurecer no cambia ni un píxel.

Y solo van fundidas las piezas que se SUPERPONEN a una anterior más de `SOLAPE_MIN_PT`: borde con
borde (imán, costura por match line, composición sugerida) el PDF sale idéntico al de siempre —sin
grupos que leer ni memoria de más al dibujar—.
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Sequence, Set, Tuple

import fitz

Pt = Tuple[float, float]

# Ancho mínimo (pt de la hoja compuesta) de la franja común para que una pieza cuente como
# superpuesta: el imán y la costura por match line dejan las piezas borde con borde con
# diferencias de centésimas, y la franja blanca de un lado (`covers`) sale 0.5 pt por fuera.
SOLAPE_MIN_PT = 1.0

GRUPO_AISLADO = "<</S/Transparency/I true>>"


def _area(poly: Sequence[Pt]) -> float:
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                     for i in range(n))


def interseccion(sujeto: Sequence[Pt], recorte: Sequence[Pt]) -> List[Pt]:
    """Parte común de dos polígonos CONVEXOS (Sutherland–Hodgman: `sujeto` recortado lado
    por lado por `recorte`). Lista vacía si no se tocan."""
    out = [tuple(p) for p in sujeto]
    sign = 1.0 if _area(recorte) >= 0 else -1.0
    n = len(recorte)
    for i in range(n):
        if not out:
            break
        a, b = recorte[i], recorte[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]

        def lado(p):                     # > 0 = del lado de adentro de la recta a→b
            return sign * (ex * (p[1] - a[1]) - ey * (p[0] - a[0]))

        prev, out = out, []
        for k in range(len(prev)):
            p, q = prev[k - 1], prev[k]
            dp, dq = lado(p), lado(q)
            if dq >= 0:
                if dp < 0:
                    t = dp / (dp - dq)
                    out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
                out.append(q)
            elif dp >= 0:
                t = dp / (dp - dq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def ancho(poly: Sequence[Pt]) -> float:
    """Ancho de un polígono convexo: la menor de sus alturas sobre cada lado (una franja
    de 800 × 0.1 pt mide 0.1)."""
    if len(poly) < 3 or abs(_area(poly)) < 1e-9:
        return 0.0
    best = math.inf
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-9:
            continue
        alto = max(abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / L for p in poly)
        best = min(best, alto)
    return 0.0 if best is math.inf else best


def solapadas(contornos: Sequence[Sequence[Pt]], minimo: float = SOLAPE_MIN_PT) -> Set[int]:
    """Índices de las piezas que se superponen a una ANTERIOR (en el orden en que se dibujan)
    en una franja de más de `minimo` pt. Solo ésas necesitan fundirse: oscurecer importa donde
    una pieza cae ENCIMA de otra. `contornos` = `composite.piece_outline` de cada pieza."""
    out: Set[int] = set()
    for k in range(1, len(contornos)):
        for j in range(k):
            if ancho(interseccion(contornos[k], contornos[j])) > minimo:
                out.add(k)
                break
    return out


_FRM = re.compile(rb"/(fzFrm\d+)\s+Do")


def aislar_ultima_pieza(doc: fitz.Document, page: fitz.Page) -> Optional[int]:
    """Marca como grupo de transparencia aislado el XObject «fzFrm» que acaba de poner
    `show_pdf_page` (el último contenido de la hoja). Devuelve su xref (None si no lo halla)."""
    xref = page.get_contents()[-1]
    m = _FRM.search(doc.xref_stream(xref) or b"")
    if not m:
        return None
    name = m.group(1).decode()
    for x, nombre, invoker, _bbox in page.get_xobjects():
        if nombre == name and invoker == 0:
            doc.xref_set_key(x, "Group", GRUPO_AISLADO)
            return x
    return None
