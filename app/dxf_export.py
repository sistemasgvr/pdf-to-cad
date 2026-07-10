"""
dxf_export.py — Exportación a DXF del plano digitalizado + anotaciones.

Todas las funciones reciben `win` (la ventana Main) para acceder a los datos del
modelo (win.pipes, win.leaders, win.text_marks, win.erase_regions) y a las
conversiones de coordenadas/geometría de directriz (win._to_cad, win._leader_geo).
El comportamiento es idéntico al que tenían estos métodos dentro de Main.
"""
import math
import config as C
import vector_pipeline as VP
from ezdxf.enums import TextEntityAlignment
from geometry import point_in_poly
from model import LEADER_TEXT_FT


def text_style(doc, font, bold):
    name = f"TXT_{font}_{'B' if bold else 'N'}".replace(" ", "_")[:60]
    if name not in doc.styles:
        try: doc.styles.add(name, font=font)
        except Exception: return "CAD_TEXT"
    return name


def merge_into(win, doc, marks=True):
    VP.setup_linetypes(doc); msp = doc.modelspace()
    apply_erase(win, msp)                             # las zonas de borrado recortan el plano base
    if not marks:                                     # 'solo PDF': no agregar utilidades/leaders/textos
        return
    if "PDFCAD" not in doc.appids: doc.appids.add("PDFCAD")   # para XDATA de propiedades
    for p in win.pipes:
        if not p.get("pts"): continue                 # tramos importados (world): van al JSON de red, no al DXF
        layer = p["layer"]; VP.ensure_layer(doc, layer)
        # El linetype con letra (─ W ─, ─ SS ─…) se aplica SOLO a la entidad que dibujas,
        # NO a la capa: así el contenido del plano base (en la misma capa) no se restilea.
        lt = C.LAYER_LINETYPE_AB.get(layer) if p.get("ab") else C.LAYER_LINETYPE.get(layer)
        att = {"layer": layer}
        if lt and lt in doc.linetypes: att["linetype"] = lt
        poly = msp.add_lwpolyline([win._to_cad(x, y) for (x, y) in p["pts"]], dxfattribs=att)
        # Propiedades de la utilidad como dato (XDATA)
        if p.get("name") or p.get("diam"):
            poly.set_xdata("PDFCAD", [(1000, f"NOMBRE={p.get('name', '')}"),
                                      (1000, f"DIAMETRO={p.get('diam', 0)}"),
                                      (1000, f"UNIDAD={p.get('unit', '')}")])
    VP.ensure_layer(doc, "ANOTACION")
    if "CAD_TEXT" not in doc.styles: doc.styles.add("CAD_TEXT", font=C.TEXT_FONT)
    for ld in win.leaders:
        if ld.get("arrow") and ld.get("tp"): add_leader(win, doc, msp, ld)
    for tm in win.text_marks:
        if tm.get("free"): add_free_text(win, doc, msp, tm)
        else: replace_text(win, doc, msp, tm)


def apply_erase(win, msp):
    regions = [r for r in win.erase_regions if r.get("enabled", True)]
    if not regions: return
    polys = [[win._to_cad(px, py) for (px, py) in r["pts"]] for r in regions]
    def inside(pt): return any(point_in_poly(pt[0], pt[1], poly) for poly in polys)
    for e in list(msp):
        t = e.dxftype()
        try:
            if t == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in e.get_points()]
                hit = inside((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
            elif t == "LINE":
                a, b = e.dxf.start, e.dxf.end; hit = inside(((a.x + b.x) / 2, (a.y + b.y) / 2))
            elif t in ("TEXT", "MTEXT"):
                ins = e.dxf.insert; hit = inside((ins.x, ins.y))
            elif t in ("CIRCLE", "ARC"):
                c = e.dxf.center; hit = inside((c.x, c.y))
            else: hit = False
            if hit: msp.delete_entity(e)
        except Exception: continue


def add_leader(win, doc, msp, ld):
    geo = win._leader_geo(ld)
    if ld.get("simple"):                                 # Leader simple → entidad LEADER nativa
        if add_simple_leader_dxf(win, doc, msp, ld, geo): return
    else:                                                # Multileader → entidad MULTILEADER nativa
        if add_multileader_dxf(win, doc, msp, ld, geo): return
    # si el visor/plantilla no soporta la entidad nativa, se dibuja explícito como respaldo
    add_leader_explicit(win, doc, msp, ld, geo)


def mleader_style(doc, arrow_ft, char_ft):
    """Estilo MLEADER propio con el tamaño de flecha/altura de texto dados (pies)."""
    name = f"PDFCAD_ML_{int(round(arrow_ft * 10))}_{int(round(char_ft * 10))}"
    try:
        if name not in doc.mleader_styles:
            doc.mleader_styles.duplicate_entry("Standard", name)
        st = doc.mleader_styles.get(name)
        st.dxf.arrow_head_size = arrow_ft; st.dxf.char_height = char_ft
        return name
    except Exception:
        return "Standard"


def add_multileader_dxf(win, doc, msp, ld, geo):
    """Exporta el Multileader como entidad MULTILEADER nativa (flecha + directriz + texto).
    Devuelve True si se creó."""
    if not ld.get("text"): return False
    try:
        from ezdxf.math import Vec2
        from ezdxf.render.mleader import ConnectionSide, TextAlignment
    except Exception:
        return False
    ch = max(0.1, geo.get("cad_h", LEADER_TEXT_FT))
    asz = max(0.05, ch * 0.6)
    style = mleader_style(doc, asz, ch)
    # segs[0] va [punta(flecha) … landing]; el MULTILEADER quiere [insert(landing) … punta]
    cad_v = [win._to_cad(x, y) for (x, y) in geo["segs"][0]][::-1]
    if len(cad_v) < 2: return False
    insert, tip = cad_v[0], cad_v[-1]
    side = ConnectionSide.left if tip[0] < insert[0] else ConnectionSide.right
    align = TextAlignment.left if side == ConnectionSide.right else TextAlignment.right
    leader_pts = [Vec2(x, y) for (x, y) in cad_v[1:]]
    try:
        mb = msp.add_multileader_mtext(style)
        mb.set_content(ld["text"], char_height=ch, alignment=align)
        mb.add_leader_line(side, leader_pts)
        mb.build(insert=Vec2(insert[0], insert[1]))
        try: mb.multileader.dxf.layer = "ANOTACION"
        except Exception: pass
        return True
    except Exception:
        return False


def add_simple_leader_dxf(win, doc, msp, ld, geo):
    """Exporta el Leader simple como entidad LEADER (con punta de flecha) siguiendo
    sus vértices: cabeza → (bisagra) → final. Devuelve True si se creó."""
    verts = [win._to_cad(x, y) for (x, y) in geo["segs"][0]]   # el 1er vértice lleva la flecha
    asz = max(0.05, geo.get("cad_h", LEADER_TEXT_FT) * 0.6)     # tamaño de la punta (unidades CAD)
    dimstyle = "EZDXF" if "EZDXF" in doc.dimstyles else ("Standard" if "Standard" in doc.dimstyles else None)
    if dimstyle is None: return False
    try:
        msp.add_leader(verts, dimstyle=dimstyle, override={"dimasz": asz, "dimscale": 1.0},
                       dxfattribs={"layer": "ANOTACION"})
        return True
    except Exception:
        return False


def add_leader_explicit(win, doc, msp, ld, geo):
    """Multileader (o respaldo del Leader simple): geometría exacta (línea + punta + texto)
    agrupada en un GROUP, igual que en la vista previa."""
    ents = []
    for s in geo["segs"]:
        ents.append(msp.add_lwpolyline([win._to_cad(x, y) for (x, y) in s], dxfattribs={"layer": "ANOTACION"}))
    a = win._to_cad(*ld["arrow"]); b = win._to_cad(*geo["segs"][0][1])
    ang = math.atan2(a[1] - b[1], a[0] - b[0]); L = geo.get("cad_h", LEADER_TEXT_FT) * 0.9
    p1 = (a[0] - L * math.cos(ang - 0.28), a[1] - L * math.sin(ang - 0.28))
    p2 = (a[0] - L * math.cos(ang + 0.28), a[1] - L * math.sin(ang + 0.28))
    ents.append(msp.add_solid([a, p1, p2, a], dxfattribs={"layer": "ANOTACION"}))
    if ld["text"]:                                       # Leader simple: solo línea + punta, sin texto
        font = ld.get("font", C.TEXT_FONT); bold = bool(ld.get("bold")); ch = geo.get("cad_h", LEADER_TEXT_FT)
        style = text_style(doc, font, bold)
        content = ld["text"].replace("\n", "\\P")
        if bold: content = f"{{\\f{font}|b1;{content}}}"
        m = msp.add_mtext(content, dxfattribs={"layer": "ANOTACION", "style": style, "char_height": ch})
        m.set_location(win._to_cad(*geo["tcenter_px"]), rotation=float(geo.get("cad_rot", 0)), attachment_point=5)
        ents.append(m)
    try:
        g = doc.groups.new()
        with g.edit_data() as data: data.extend(ents)
    except Exception: pass


def add_free_text(win, doc, msp, tm):
    font = tm.get("font", C.TEXT_FONT); bold = bool(tm.get("bold")); h = tm.get("size_ft", LEADER_TEXT_FT)
    style = text_style(doc, font, bold)
    body = tm["text"].replace("\n", "\\P")
    if bold: body = f"{{\\f{font}|b1;{body}}}"
    m = msp.add_mtext(body, dxfattribs={"layer": "ANOTACION", "style": style, "char_height": h})
    m.set_location(win._to_cad(*tm["pos"]), rotation=float(tm.get("rot", 0) or 0), attachment_point=1)


def replace_text(win, doc, msp, tm):
    bx, by, bw, bh = tm.get("box", (tm["pos"][0] - 30, tm["pos"][1] - 10, 60, 20))
    cs = [win._to_cad(bx, by), win._to_cad(bx + bw, by), win._to_cad(bx, by + bh), win._to_cad(bx + bw, by + bh)]
    xs = [c[0] for c in cs]; ys = [c[1] for c in cs]; pad = LEADER_TEXT_FT * 2
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    for e in list(msp.query("TEXT MTEXT")):
        if e.dxf.layer in ("ANOTACION", "TEXTO"):
            ins = e.dxf.insert
            if x0 <= ins.x <= x1 and y0 <= ins.y <= y1: msp.delete_entity(e)
    t = msp.add_text(tm["text"], height=LEADER_TEXT_FT, dxfattribs={"layer": "ANOTACION", "style": "CAD_TEXT"})
    t.set_placement(win._to_cad(tm["pos"][0], tm["pos"][1]), align=TextEntityAlignment.MIDDLE_CENTER)
