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


def _resolve_family_guid(win, fid, kind):
    """GUID estable de la familia (Catalog_PartID del XML). El plugin C# lo usa
    para emparejar la familia EXACTA sin depender del idioma. '' si no aplica
    (familia custom sin GUID, presión, o sin catálogo detectado)."""
    if not fid or "|" in fid: return ""
    year = getattr(win, "civil_year", None)
    if year is None: return ""
    try: return _cc.family_guid(year, fid, kind) or ""
    except Exception: return ""


def _no_manhole_vertex_indices(win, p):
    """Índices (0-based, dentro de p['pts']) de los vértices de ESTA tubería que
    coinciden con una estructura marcada curve=True. ImportarRed.cs ya sabe leer
    NO_MANHOLE_VERTS del XDATA PDFCAD_PIPE y saltarse la creación de buzón ahí
    (deja los dos tramos rectos sueltos en ese vértice) — sin este campo, el
    importador cae al buzón por defecto porque no hay PDFCAD_STRUCT que matchee."""
    curves = [s for s in getattr(win, "structures", None) or [] if s.get("curve") and not s.get("world")]
    if not curves: return []
    tol2 = 14.0 ** 2
    out = []
    for i, (px, py) in enumerate(p["pts"]):
        for s in curves:
            sx, sy = s.get("x"), s.get("y")
            if sx is None or sy is None: continue
            if (sx - px) ** 2 + (sy - py) ** 2 <= tol2:
                out.append(i); break
    return out


def _pipe_at_point(win, x, y, tol=14.0):
    """Tubería (dict) con un vértice a distancia <= tol de (x,y), o None. La curva
    hereda familia/tamaño de esta tubería — nunca lleva los suyos aparte."""
    tol2 = tol * tol
    for p in win.pipes:
        if p.get("world") or not p.get("pts"): continue
        for (vx, vy) in p["pts"]:
            if (vx - x) ** 2 + (vy - y) ** 2 <= tol2:
                return p
    return None


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
        no_manhole = _no_manhole_vertex_indices(win, p) if p.get("pts") and not p.get("world") else []
        vi_out = p.get("vertex_inv_out") or p.get("vertex_inv") or {}
        vi_in  = p.get("vertex_inv_in") or p.get("vertex_inv") or {}
        vertex_inv_str = ";".join(f"{i}~{z}" for i, z in vi_out.items())
        vertex_inv_in_str = ";".join(f"{i}~{z}" for i, z in vi_in.items())
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
            (1000, f"PIPE_GUID={_resolve_family_guid(win, p.get('pipe_family') or '', 'pipe')}"),
            (1000, f"PIPE_SIZE={p.get('pipe_size') or ''}"),
            (1000, f"NO_MANHOLE_VERTS={','.join(str(i) for i in no_manhole)}"),
            (1000, f"VERTEX_INV={vertex_inv_str}"),
            (1000, f"VERTEX_INV_IN={vertex_inv_in_str}"),
        ])
    _export_structures(win, doc, msp)
    _export_ref_centerlines(win, doc, msp)
    _export_cs_code(win, doc, msp)
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


def _export_cs_code(win, doc, msp):
    """Escribe el código de sistema de coordenadas (Huso) elegido en la
    georreferenciación como un punto-metadato con XDATA PDFCAD_META. El plugin C#
    (IMPORTAR_RED) lo lee y setea DrawingSettings.UnitZoneSettings.CoordinateSystemCode
    en el dibujo. Solo se emite si la georref está activa y hay código."""
    geo = getattr(win, "georef", None)
    code = (getattr(geo, "cs_code", "") or "").strip() if geo is not None else ""
    if not code or not (geo.active() if geo is not None else False):
        return
    if "PDFCAD" not in doc.appids: doc.appids.add("PDFCAD")
    VP.ensure_layer(doc, "PDFCAD_META")
    # El punto solo PORTA el XDATA (su posición no la usa el plugin). Se coloca
    # SOBRE el dibujo — en el primer vértice/estructura disponible — para que no
    # aparezca perdido lejísimos (en el origen del mundo real, a kilómetros del
    # plano georreferenciado). Va en su propia capa PDFCAD_META, que puedes apagar.
    anchor = _cs_meta_anchor(win)
    pt = msp.add_point((anchor[0], anchor[1], 0), dxfattribs={"layer": "PDFCAD_META"})
    pt.set_xdata("PDFCAD", [
        (1000, "PDFCAD_META"),
        (1000, f"CS_CODE={code}"),
    ])


def _cs_meta_anchor(win):
    """Un punto (en coords CAD reales) SOBRE el dibujo para anclar el metadato:
    primer vértice de la primera utilidad, o la primera estructura, o (0,0) si no
    hay nada."""
    for p in getattr(win, "pipes", None) or []:
        if p.get("world") and p.get("wstart"):
            return (float(p["wstart"][0]), float(p["wstart"][1]))
        if p.get("pts"):
            return win._to_cad(*p["pts"][0])
    for s in getattr(win, "structures", None) or []:
        if s.get("world") and s.get("x") is not None:
            return (float(s["x"]), float(s["y"]))
        if s.get("x") is not None:
            return win._to_cad(s["x"], s["y"])
    return (0.0, 0.0)


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
        if s.get("curve"):
            _export_curve_corner(win, doc, msp, s, cx, cy, show_labels)
            continue
        pt = msp.add_point((cx, cy, 0), dxfattribs={"layer": "PDFCAD_BZ"})
        rim, sump = s.get("rim"), s.get("sump")
        # rim/sump = 0.0 o None → no seteado por el usuario → enviar vacío
        # para que C# calcule sump = invert de la tubería conectada.
        rim_str = f"{rim}" if rim else ""
        sump_str = f"{sump}" if sump else ""
        height_ft = s.get("height_ft") or 0.0
        pt.set_xdata("PDFCAD", [
            (1000, "PDFCAD_STRUCT"),
            (1000, f"STRUCT_ID={s.get('cod') or ''}"),
            (1000, f"RIM={rim_str}"),
            (1000, f"SUMP={sump_str}"),
            (1000, f"PART={_resolve_family(win, s.get('part') or '', 'structure')}"),
            (1000, f"PART_GUID={_resolve_family_guid(win, s.get('part') or '', 'structure')}"),
            (1000, f"PART_SIZE={s.get('part_size') or ''}"),
            (1000, f"COVERED={1 if s.get('covered', True) else 0}"),
            (1000, f"NET_KIND={s.get('net') or 'gravity'}"),
            (1000, f"HEIGHT_FT={height_ft if height_ft else ''}"),
            # El nodo SÍ se exporta (la red necesita el punto para conectar
            # tramos) pero marcado — ImportarRed.cs usa la familia "Estructura
            # nula" (invisible) ahí en vez de un buzón real. No se omite el
            # punto: omitirlo haría que Civil3D caiga al buzón por defecto
            # (visible), no a uno invisible.
            (1000, f"HIDDEN={1 if s.get('hidden') else 0}"),
        ])
        if show_labels and s.get("cod") and not s.get("hidden"):
            h = LEADER_TEXT_FT * 0.3                 # etiquetas compactas al lado del buzón
            t = msp.add_text(s["cod"], height=h,
                             dxfattribs={"layer": "ETIQUETAS_BUZONES", "style": "CAD_TEXT"})
            t.set_placement((cx + h * 0.8, cy + h * 0.4), align=TextEntityAlignment.LEFT)


def _export_ref_centerlines(win, doc, msp):
    """Centerlines DIBUJADOS a mano (distintos de las utilidades) — referencia
    propia de una calle para calzar contra la calle real al georreferenciar.
    Se exportan como polilíneas simples en su propia capa, con el código al
    lado; no llevan XDATA porque no representan una utilidad ni un nodo de
    red — el proyecto Python (.digproj) sigue siendo la fuente de verdad."""
    cls = getattr(win, 'ref_centerlines', None)
    if not cls: return
    if "REF_CENTERLINES" not in doc.layers:
        doc.layers.new("REF_CENTERLINES", dxfattribs={"color": 6})   # magenta
    if "CAD_TEXT" not in doc.styles:
        doc.styles.add("CAD_TEXT", font=C.TEXT_FONT)
    for c in cls:
        pts = c.get("pts") or []
        if len(pts) < 2: continue
        pts_cad = [win._to_cad(x, y) for (x, y) in pts]
        msp.add_lwpolyline(pts_cad, dxfattribs={"layer": "REF_CENTERLINES"})
        if c.get("cod"):
            h = LEADER_TEXT_FT * 0.3
            t = msp.add_text(c["cod"], height=h,
                             dxfattribs={"layer": "REF_CENTERLINES", "style": "CAD_TEXT"})
            t.set_placement((pts_cad[0][0] + h * 0.8, pts_cad[0][1] + h * 0.4), align=TextEntityAlignment.LEFT)


def _export_curve_corner(win, doc, msp, s, cx, cy, show_labels):
    """Exporta la ESQUINA de un elemento curvo (p.ej. codo de bancoducto) como un
    punto informativo en la capa PDFCAD_CURVA con marcador PDFCAD_CURVE — en vez
    del PDFCAD_STRUCT de un buzón. A propósito NO crea una estructura: las dos
    tuberías rectas que llegan a este vértice se importan sueltas ahí (sin nodo
    que las une). ImportarRed.cs lee este punto y genera él mismo la tubería
    curva tangente (radio explícito o 6× el ancho de la tubería si RADIUS_FT
    viene vacío) — no depende del addin ElementosCurvos/AGREGAR_TUBO_CURVO.
    PIPE_FAMILY/PIPE_SIZE se heredan de la tubería recta de este vértice (nunca
    se eligen aparte), para que la curva calce siempre con los tramos rectos."""
    VP.ensure_layer(doc, "PDFCAD_CURVA")
    pt = msp.add_point((cx, cy, 0), dxfattribs={"layer": "PDFCAD_CURVA"})
    p = _pipe_at_point(win, s.get("x"), s.get("y"))
    fam = _resolve_family(win, (p.get("pipe_family") if p else "") or "", "pipe")
    size = (p.get("pipe_size") if p else "") or ""
    radius = s.get("radius_ft") or ""
    pt.set_xdata("PDFCAD", [
        (1000, "PDFCAD_CURVE"),
        (1000, f"STRUCT_ID={s.get('cod') or ''}"),
        (1000, f"NET_KIND={s.get('net') or 'gravity'}"),
        (1000, f"PIPE_FAMILY={fam}"),
        (1000, f"PIPE_SIZE={size}"),
        (1000, f"RADIUS_FT={radius}"),
    ])
    if show_labels and s.get("cod"):
        h = LEADER_TEXT_FT * 0.3
        t = msp.add_text(s["cod"], height=h,
                         dxfattribs={"layer": "ETIQUETAS_BUZONES", "style": "CAD_TEXT"})
        t.set_placement((cx + h * 0.8, cy + h * 0.4), align=TextEntityAlignment.LEFT)
