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
import civil_catalog as _cc
from ezdxf.enums import TextEntityAlignment
from geometry import point_in_poly
from model import (LEADER_TEXT_FT, network_kind, default_network_type,
                   mannings_n, COVER_MIN_FT)


def _encode_seg_overrides(win, p):
    """Serializa p['seg_overrides'] al formato XDATA: 'idx~family~size;idx~family~size'.
    La familia se resuelve a Description real (misma lógica que _resolve_family),
    para que el matcher del addin la encuentre por Description."""
    ov = p.get("seg_overrides") or {}
    if not ov: return ""
    parts = []
    for k in sorted(ov.keys(), key=lambda x: int(x)):
        entry = ov[k] or {}
        fid = entry.get("pipe_family") or ""
        sz  = entry.get("pipe_size") or ""
        fam = _resolve_family(win, fid, "pipe") if fid else ""
        parts.append(f"{int(k)}~{fam}~{sz}")
    return ";".join(parts)


def _resolve_family(win, fid, kind):
    """Traduce un fid (basename del .xml) a la Description real (PrtD) que ve
    Civil 3D. Así el matcher del addin (compara por Description) encuentra la
    familia correcta, incluso para familias custom como Bancoductos/BuzonesElectricas
    donde el basename no comparte tokens con la Description.
    Los fid de presión (formato '<subcat>|<name>') salen de un catálogo SQLite —
    no tienen XML, se devuelven tal cual."""
    if not fid: return ""
    if "|" in fid: return fid                                  # presión: catálogo SQLite
    year = getattr(win, "civil_year", None)
    if year is None: return fid
    try: return _cc.family_description(year, fid, kind) or fid
    except Exception: return fid


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
    if "PDFCAD" not in doc.appids: doc.appids.add("PDFCAD")
    work_unit = getattr(win, 'work_unit', 'ft')
    for p in win.pipes:
        layer = p["layer"]; VP.ensure_layer(doc, layer)
        att = {"layer": layer}
        if p.get("world") and p.get("wstart") and p.get("wend"):
            pts_cad = [tuple(p["wstart"]), tuple(p["wend"])]
        elif p.get("pts"):
            lt = C.LAYER_LINETYPE_AB.get(layer) if p.get("ab") else C.LAYER_LINETYPE.get(layer)
            if lt and lt in doc.linetypes: att["linetype"] = lt
            pts_cad = [win._to_cad(x, y) for (x, y) in p["pts"]]
        else:
            continue
        poly = msp.add_lwpolyline(pts_cad, dxfattribs=att)
        kind = network_kind(layer)
        nt_raw = (p.get("net_type") or "").strip()
        net_type = nt_raw if nt_raw in ("pipe", "pressure") else default_network_type(layer)
        inv_s = p.get("inv_start")
        inv_e = p.get("inv_end")
        mat = p.get('material') or ''
        manning = mannings_n(mat)
        cover = COVER_MIN_FT.get(layer, 3.0)
        poly.set_xdata("PDFCAD", [
            (1000, "PDFCAD_PIPE"),
            (1000, f"DIAMETER={p.get('diam') or 0}"),
            (1000, f"UNIT={work_unit}"),
            (1000, f"MATERIAL={mat}"),
            (1000, f"NET_KIND={kind}"),
            (1000, f"NET_TYPE={net_type}"),
            (1000, f"INV_START={inv_s if inv_s is not None else ''}"),
            (1000, f"INV_END={inv_e if inv_e is not None else ''}"),
            (1000, f"MANNINGS_N={manning}"),
            (1000, f"COVER_MIN={cover}"),
            (1000, f"PIPE_FAMILY={_resolve_family(win, p.get('pipe_family') or '', 'pipe')}"),
            (1000, f"PIPE_SIZE={p.get('pipe_size') or ''}"),
            (1000, f"NO_MANHOLE_VERTS={','.join(str(i) for i in (p.get('no_manhole_verts') or []))}"),
            (1000, f"SEG_OVERRIDES={_encode_seg_overrides(win, p)}"),
        ])
    _export_structures(win, doc, msp)
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
    if add_simple_leader_dxf(win, doc, msp, ld, geo): return
    # si el visor/plantilla no soporta la entidad LEADER nativa, se dibuja explícito.
    add_leader_explicit(win, doc, msp, ld, geo)


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


def _export_structures(win, doc, msp):
    structs = getattr(win, 'structures', None)
    if not structs: return
    VP.ensure_layer(doc, "PDFCAD_BZ")
    show_labels = bool(getattr(win, "show_bz_labels", False))
    if show_labels:
        VP.ensure_layer(doc, "ETIQUETAS_BUZONES")
        if "CAD_TEXT" not in doc.styles:
            doc.styles.add("CAD_TEXT", font=C.TEXT_FONT)
    for s in structs:
        # Se exportan buzones de gravedad (BZ-N) y cajas de conduit (CAJA-N).
        # Los de presión se filtran (no llevan nodos automáticos).
        if (s.get("net") or "gravity") not in ("gravity", "conduit"): continue
        x, y = s.get("x"), s.get("y")
        if x is None or y is None: continue
        cx, cy = (float(x), float(y)) if s.get("world") else win._to_cad(x, y)
        pt = msp.add_point((cx, cy, 0), dxfattribs={"layer": "PDFCAD_BZ"})
        rim, sump = s.get("rim"), s.get("sump")
        pt.set_xdata("PDFCAD", [
            (1000, "PDFCAD_STRUCT"),
            (1000, f"STRUCT_ID={s.get('cod') or ''}"),
            (1000, f"RIM={rim if rim is not None else ''}"),
            (1000, f"SUMP={sump if sump is not None else ''}"),
            (1000, f"PART={_resolve_family(win, s.get('part') or '', 'structure')}"),
            (1000, f"PART_SIZE={s.get('part_size') or ''}"),
            (1000, f"COVERED={1 if s.get('covered', True) else 0}"),
            (1000, f"NET_KIND={s.get('net') or 'gravity'}"),
        ])
        if show_labels and s.get("cod"):
            h = LEADER_TEXT_FT * 0.3                 # etiquetas compactas al lado del buzón
            t = msp.add_text(s["cod"], height=h,
                             dxfattribs={"layer": "ETIQUETAS_BUZONES", "style": "CAD_TEXT"})
            t.set_placement((cx + h * 0.8, cy + h * 0.4), align=TextEntityAlignment.LEFT)
