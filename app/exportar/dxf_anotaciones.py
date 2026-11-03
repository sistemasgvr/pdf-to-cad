"""dxf_anotaciones.py — los rótulos del plano reconocidos (`Main.anotaciones`) al DXF (pedido 2026-11-03).

Cada MLeader del PDF sale como MULTILEADER (texto MText + su guía con los vértices del plano, la flecha en la
punta) y cada MText de un mapa como MTEXT con su giro, en la capa `PDFCAD_ANOTACIONES`. Llevan XDATA `PDFCAD`:

    PDFCAD_ANOT, TIPO=multileader|mtext, TEXTO, UTILIDAD, DIAMETER, MATERIAL, ESTADO=leido|ilegible,
    FUENTE=pdf|ia|usuario, PIPE_IDX (la utilidad que señala, −1 = ninguna)

Un rótulo «ilegible» (texto SHX que no es texto del PDF) que nadie leyó sale con «?» y ESTADO=ilegible. Si la
entidad MULTILEADER no se puede armar, la guía va como polilínea + MTEXT (como `add_leader_explicit`).
"""
from __future__ import annotations

import math

CAPA = "PDFCAD_ANOTACIONES"
ALTO_LETRA = 0.7               # alto de mayúscula / tamaño de letra del PDF
MAX_XDATA = 250


def _xdata(a: dict, pipe_idx) -> list:
    texto = " / ".join((a.get("texto") or "").splitlines())[:MAX_XDATA]
    d = a.get("diam_in")
    return [(1000, "PDFCAD_ANOT"), (1000, f"TIPO={a.get('tipo') or ''}"), (1000, f"TEXTO={texto}"[:MAX_XDATA]),
            (1000, f"UTILIDAD={a.get('utilidad') or ''}"), (1000, f"DIAMETER={'' if d is None else f'{d:g}'}"),
            (1000, f"MATERIAL={a.get('material') or ''}"), (1000, f"ESTADO={a.get('estado') or ''}"),
            (1000, f"FUENTE={a.get('fuente') or ''}"), (1000, f"PIPE_IDX={-1 if pipe_idx is None else int(pipe_idx)}")]


def _marco(win, a: dict):
    """(punto de inserción CAD arriba a la izquierda del texto, giro en grados, alto de letra en unidades CAD)."""
    x0, y0, x1, y1 = a["caja"]
    ang = math.radians(float(a.get("angulo") or 0.0))
    d = (math.cos(ang), -math.sin(ang))                  # px, y hacia abajo
    up = (d[1], -d[0])
    esquinas = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    tl = max(esquinas, key=lambda c: (c[0] * up[0] + c[1] * up[1]) - (c[0] * d[0] + c[1] * d[1]))
    p0, p1 = win._to_cad(*tl), win._to_cad(tl[0] + d[0], tl[1] + d[1])
    rot = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    q = win._to_cad(tl[0] + up[0], tl[1] + up[1])
    px_cad = math.hypot(q[0] - p0[0], q[1] - p0[1])      # unidades CAD por px
    alto = max(0.05, ALTO_LETRA * float(a.get("tam") or 0.0) * px_cad) if a.get("tam") else max(
        0.05, 0.35 * abs(y1 - y0) * px_cad)
    return p0, rot, alto


def _contenido(a: dict) -> str:
    t = (a.get("texto") or "").strip()
    return "\\P".join(t.splitlines()) if t else "?"


def _multileader(win, doc, msp, a, p0, rot, alto):
    from ezdxf.math import Vec2
    from ezdxf.render import mleader
    ml = msp.add_multileader_mtext("Standard")
    ml.set_content(_contenido(a), char_height=alto, alignment=mleader.TextAlignment.left)
    for cad, punta in zip(a.get("guias") or (), a.get("puntas") or ()):
        if len(cad) < 2:
            continue
        verts = [Vec2(*win._to_cad(*punta))] + [Vec2(*win._to_cad(*p)) for p in reversed(cad[1:-1])]
        lado = (mleader.ConnectionSide.left if cad[0][0] <= (a["caja"][0] + a["caja"][2]) / 2.0
                else mleader.ConnectionSide.right)
        ml.add_leader_line(lado, verts)
    ml.build(insert=Vec2(*p0), rotation=rot)
    return ml.multileader


def _explicita(win, doc, msp, a, p0, rot, alto):
    ents = []
    for cad, punta in zip(a.get("guias") or (), a.get("puntas") or ()):
        pts = [win._to_cad(*p) for p in cad] + [win._to_cad(*punta)]
        ents.append(msp.add_lwpolyline(pts, dxfattribs={"layer": CAPA}))
    m = msp.add_mtext(_contenido(a), dxfattribs={"layer": CAPA, "char_height": alto})
    m.set_location(p0, rotation=rot, attachment_point=1)
    ents.append(m)
    try:
        g = doc.groups.new()
        with g.edit_data() as data:
            data.extend(ents)
    except Exception:                                      # noqa: BLE001
        pass
    return m


def exportar(win, doc, msp) -> int:
    """Escribe los rótulos de `win.anotaciones`; devuelve cuántos."""
    from nucleo import anotaciones as AN
    from vector_pipeline import ensure_layer
    lista = getattr(win, "anotaciones", None) or []
    if not lista:
        return 0
    if "PDFCAD" not in doc.appids:
        doc.appids.add("PDFCAD")
    ensure_layer(doc, CAPA)
    n = 0
    for a in lista:
        try:
            p0, rot, alto = _marco(win, a)
        except Exception:                                  # noqa: BLE001 (caja rota: se salta)
            continue
        ent = None
        if a.get("tipo") == "multileader" and a.get("guias"):
            try:
                ent = _multileader(win, doc, msp, a, p0, rot, alto)
            except Exception:                              # noqa: BLE001
                ent = None
            if ent is None:
                ent = _explicita(win, doc, msp, a, p0, rot, alto)
        else:
            ent = msp.add_mtext(_contenido(a), dxfattribs={"layer": CAPA, "char_height": alto})
            ent.set_location(p0, rotation=rot, attachment_point=1)
        ent.dxf.layer = CAPA
        ent.set_xdata("PDFCAD", _xdata(a, AN.senala(a, win.pipes)))
        n += 1
    return n
