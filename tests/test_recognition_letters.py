"""Utilidad de una línea por las LETRAS de su linetype (pedido del usuario 2026-10-05).

DU08 h.26: la capa `U-TRPW-DBNK-P` («—TE—») caía en «Otras» y no se reconocía. Las
letras del linetype son vectores SHX: `recognition_letter_shapes` las lee y
`recognition_letters` decide, línea por línea, de qué utilidad es cada trazo. Según
la leyenda del propio PDF (DU08 h.3/h.33) «TE» = Traction Electrification y «SE» =
Station Electrification (eléctrico), «SC» = Signal & Communication (telecom).
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import recognition as rec  # noqa: E402
import recognition_letter_shapes as shapes  # noqa: E402
import recognition_letter_lines as lines  # noqa: E402
import recognition_letters as letters  # noqa: E402
import recognition_summary as rs  # noqa: E402

DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"
LABOE = DOCS / "Prev. LABOE E2020 Submittal No. 12324 - 85_ Sewer BOE Comments.pdf"

# «TE» tal como lo trae DU08 h.26 (txt.shx, alto 7.2 pt), en el marco del hueco: x a lo
# largo de la línea desde la punta del guión, y hacia ARRIBA del texto.
TE = [[(3.66, 3.42), (8.46, 3.42)], [(6.06, 3.42), (6.06, -3.78)],
      [(9.84, -3.78), (9.84, 3.42), (14.28, 3.42)], [(9.84, 0.0), (12.60, 0.0)],
      [(9.84, -3.78), (14.28, -3.78)]]


def _glyph(text, height=7.2, x0=3.6, space=1.4):
    """Texto armado con las plantillas (alto `height`, centrado en el eje)."""
    out, x = [], x0
    for ch in text:
        strokes = shapes.TEMPLATES[ch]
        bx0, by0, bx1, by1 = shapes._bbox(strokes)
        k = height / max(by1 - by0, 1e-6)
        out += [[(x + (px - bx0) * k, (py - by0) * k - height / 2) for px, py in s] for s in strokes]
        x += (bx1 - bx0) * k + space
    return out


def _path(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return {"items": [("l", a, b) for a, b in zip(pts, pts[1:])], "type": "s", "fill": None,
            "rect": (min(xs), min(ys), max(xs), max(ys))}


def _line(origin, angle_deg, glyph, n=6, dash=50.4, gap=19.4, flip=False):
    """Línea con linetype: guiones de `dash` y el rótulo `glyph` en cada hueco. El eje y
    del PDF va hacia abajo: «arriba» del texto es la normal izquierda del sentido de
    avance. `flip`: el texto se dibuja de pie en la HOJA aunque la línea vaya al revés."""
    a = math.radians(angle_deg)
    u = (math.cos(a), math.sin(a))
    nrm = (u[1], -u[0])

    def P(x, y):
        return (origin[0] + x * u[0] + y * nrm[0], origin[1] + x * u[1] + y * nrm[1])
    paths, x = [], 0.0
    for k in range(n):
        paths.append(_path([P(x, 0.0), P(x + dash, 0.0)]))
        x += dash
        if k < n - 1:
            for s in glyph:
                pts = [(gap - gx, -gy) for gx, gy in s] if flip else s
                paths.append(_path([P(x + gx, gy) for gx, gy in pts]))
            x += gap
    return paths


@pytest.mark.parametrize("text, code, utility, overhead", [
    ("TE", "TE", "ELECTRICO", False), ("SE", "SE", "ELECTRICO", False), ("e", "E", "ELECTRICO", False),
    ("SC", "SC", "TELECOM", False), ("t", "T", "TELECOM", False), ("w", "W", "AGUA", False),
    ("G", "G", "GAS", False), ("ss", "SS", "ALCANTARILLADO", False), ("S", "S", "ALCANTARILLADO", False),
    ("sd", "SD", "DRENAJE", False), ("/W", "W", "AGUA", False), ("e(oh)", "E", "ELECTRICO", True),
    ("unk", "UNK", None, False), ("o", "O", None, False),
])
def test_codigos_del_linetype(text, code, utility, overhead):
    assert letters.normalize_code(text) == (code, overhead)
    assert letters.code_utility(code) == utility


@pytest.mark.parametrize("angle", [0, 90, 180, 233])
def test_lee_te_en_cualquier_rumbo(angle):
    """El texto gira con la línea («TE» de una línea que va a la izquierda se ve «3⊥»)."""
    lt = letters.read_layer(_line((500, 500), angle, TE))
    assert dict(lt.codes) == {"TE": 5}
    assert lt.utility == "ELECTRICO" and lt.dedicated == "ELECTRICO"


def test_lee_te_de_pie_en_la_hoja():
    """Linetype «upright»: el texto queda de pie en la hoja aunque la línea vaya al revés."""
    lt = letters.read_layer(_line((900, 500), 180, TE, flip=True))
    assert dict(lt.codes) == {"TE": 5}


@pytest.mark.parametrize("text, code", [("SC", "SC"), ("SE", "SE"), ("w", "W"), ("G", "G"), ("ss", "SS"),
                                        ("sd", "SD"), ("t", "T"), ("e", "E")])
def test_lee_cada_codigo(text, code):
    lt = letters.read_layer(_line((100, 100), 0, _glyph(text)))
    assert lt.codes.most_common(1)[0] == (code, 5)


def test_capa_mezclada_se_reparte_linea_por_linea():
    """`_Xref` de DU10 h.11: «—G—» y «—W—» en la misma capa → cada trazo a la suya."""
    gas = _line((100, 100), 0, _glyph("G"))
    agua = _line((100, 400), 90, _glyph("W"))
    lt = letters.read_layer(gas + agua)
    assert lt.utility is None and lt.mixed == ["AGUA", "GAS"]
    assert {lt.by_path.get(letters.path_key(p)) for p in gas} == {"GAS"}
    assert {lt.by_path.get(letters.path_key(p)) for p in agua} == {"AGUA"}
    use = rec.letter_uses({"X|_Xref": lt})["X|_Xref"]
    assert use.utility is None and use.utilities == ["AGUA", "GAS"] and use.codes == {"AGUA": "W", "GAS": "G"}


def test_capa_generica_solo_aporta_su_linea_con_letras():
    """La capa «0» de LABOE h.26 trae comentarios, una vista de perfil y UNA línea «—S—»:
    no se toma entera (cobertura baja), solo los trazos de esa línea."""
    linea = _line((100, 100), 0, _glyph("S"))
    otros = [_path([(100, 300 + 9 * k), (1500, 300 + 9 * k)]) for k in range(12)]            # grilla
    otros += [_path([(200 + 37 * k, 600), (230 + 37 * k, 640)]) for k in range(20)]           # leaders
    lt = letters.read_layer(linea + otros)
    assert lt.utility == "ALCANTARILLADO" and lt.dedicated is None and lt.coverage < 0.5
    use = rec.letter_uses({"0": lt})["0"]
    assert use.utility is None
    assert all(use.paths.get(letters.path_key(p)) == "ALCANTARILLADO" for p in linea)
    assert not any(letters.path_key(p) in use.paths for p in otros)


def test_aerea_no_es_una_linea_de_red():
    lt = letters.read_layer(_line((100, 100), 0, _glyph("e(oh)", height=5.0), gap=36.0))
    assert "E(OH)" in lt.codes and not lt.utilities
    assert rec.letter_uses({"X|C-POWR-AERIAL": lt}) == {}


def test_lecturas_basura_no_clasifican():
    """DU06 h.2 `W-Plantry`: entre ~70 «letras» que no son código salían 3 «G»."""
    paths = _line((100, 100), 0, _glyph("II")) + _line((100, 300), 0, _glyph("NXN"))
    paths += _line((100, 500), 0, _glyph("G"), n=3)
    lt = letters.read_layer(paths)
    assert not lt.utilities and rec.letter_uses({"W-Plantry": lt}) == {}


def test_el_nombre_cede_ante_letras_unanimes():
    """`N-COMM-DUCT-BANK-PL-SE`: su nombre es de telecom, pero «SE» (leyenda de DU08)
    es electrificación de estación → eléctrico. Si las letras confirman el nombre, nada."""
    se = letters.read_layer(_line((100, 100), 0, _glyph("SE"), n=8))
    use = rec.letter_uses({"X|N-COMM-DUCT-BANK-PL-SE": se})["X|N-COMM-DUCT-BANK-PL-SE"]
    assert (use.utility, use.name_utility, use.code) == ("ELECTRICO", "TELECOM", "SE")
    t = letters.read_layer(_line((100, 100), 0, _glyph("t"), n=8))
    assert rec.letter_uses({"X|C-TELE-UNGD-E": t}) == {}
    assert rec.letter_uses({"X|V-ELEC-VALT": letters.read_layer(_line((1, 1), 0, _glyph("E"), n=8))}) == {}


def test_anotacion_y_aereas_no_se_leen():
    assert not letters.letters_candidate("X|G-ANNO-TEXT")          # la leyenda de DU08 h.33
    assert not letters.letters_candidate("X|C-TELE-OVHD-E")
    assert letters.letters_candidate("PS89616000_B3-NX-REF-MODL-001|U-TRPW-DBNK-P")


def test_aviso_para_verificar_y_ubicacion():
    w = ("Reconocidas por las letras de su línea (no por el nombre de la capa): 7 — «SE» "
         "N-COMM-DUCT-BANK-PL-SE (su nombre decía Telecomunicaciones), «TE» U-TRPW-DBNK-P.")
    n = rs.classify_warning(w, "ELECTRICO")
    assert (n.level, n.key, n.label) == (rs.REVIEW, "letters", "7 líneas reconocidas por sus letras")
    assert len(n.hint) > 40
    a = SimpleNamespace(pts_pdf=[(0, 0), (100, 0)], letters="TE")
    b = SimpleNamespace(pts_pdf=[(0, 50), (100, 50)], letters="")
    assert rs.targets_for("letters", SimpleNamespace(drawable=[a, b])) == [(0, 0, 100, 0)]


# ─────────────────────────────── PDF reales ───────────────────────────────
needs_du08 = pytest.mark.skipif(not DU08.exists(), reason="PDF de prueba DU08 no disponible")


def _gap_texts(paths):
    chains, _owner = lines.stroke_chains(paths)
    gaps, _touch = lines.gaps(lines.dash_ends(chains))
    out = set()
    for (_o, _u, _l, sure, _a, _b), members in zip(gaps, lines.group_members(chains, gaps)):
        got = letters.read_text([loc for _ci, loc in members], sure) if members else None
        if got:
            code, overhead = letters.normalize_code(got[0])
            out.add(code + ("(OH)" if overhead else ""))
    return out


@needs_du08
def test_leyenda_de_du08_se_lee_entera():
    """DU08 h.33: cada muestra de la leyenda de utilidades se lee con su código."""
    import fitz
    with fitz.open(str(DU08)) as doc:
        page = doc[32]
        paths = [d for d in page.get_drawings()
                 if 150 <= d["rect"].x0 and d["rect"].x1 <= 440 and 125 <= d["rect"].y0 and d["rect"].y1 <= 1205]
    got = _gap_texts(paths)
    assert {"E", "G", "O", "SS", "SD", "T", "UNK", "W", "SC", "SE", "TE", "E(OH)", "T(OH)"} <= got


@needs_du08
def test_du08_h26_te_es_electrico_y_se_reconoce():
    import fitz
    import pdf_layers
    with fitz.open(str(DU08)) as doc:
        found = rec.page_letters(doc[25])
        uses = {k.split("|")[-1]: u for k, u in rec.letter_uses(found).items()}
        te = uses["U-TRPW-DBNK-P"]
        assert (te.utility, te.code, te.name_utility) == ("ELECTRICO", "TE", "")
        se = uses["N-COMM-DUCT-BANK-PL-SE"]
        assert (se.utility, se.name_utility) == ("ELECTRICO", "TELECOM")
        assert uses["_Xref"].utilities == ["AGUA", "GAS"]
        assert "N-COMM-DUCT-BANK-PL-SC" not in uses and "C-UNKN-UNGD-E" not in uses

        elec = rec.recognize_page(None, 25, utility="ELECTRICO", zoom=2.0, doc=doc, letters=found)
        by_letters = [p for p in elec.drawable if p.letters]
        assert sum(1 for p in by_letters if p.layer_ocg.endswith("|U-TRPW-DBNK-P")) >= 5
        assert any(p.layer_ocg.endswith("|N-COMM-DUCT-BANK-PL-SE") for p in by_letters)
        assert any(w.startswith("Reconocidas por las letras de su línea") for w in elec.warnings)
        tele = rec.recognize_page(None, 25, utility="TELECOM", zoom=2.0, doc=doc, letters=found)
        layers = {p.layer_ocg.split("|")[-1] for p in tele.drawable}
        assert "N-COMM-DUCT-BANK-PL-SE" not in layers and "N-COMM-DUCT-BANK-PL-SC" in layers

        listed = {L["short"]: L for L in pdf_layers.page_layers(doc, 25)}
        assert listed["U-TRPW-DBNK-P"]["utility"] == "ELECTRICO"
        assert listed["U-TRPW-DBNK-P"]["letters"] == "TE"
        assert listed["N-COMM-DUCT-BANK-PL-SE"]["name_utility"] == "TELECOM"


@needs_du08
def test_du08_h26_diagonal_te_llega_a_la_linea_por_su_recta():
    """Reporte del usuario (2026-10-06): la diagonal «TE» que baja a la línea de abajo
    muere justo antes de la «TE» de esa línea. El nodo quedaba en el CENTRO de ese
    hueco (847.8, 579.5) y la diagonal se torcía hasta 2.4 pt fuera de su tinta; va
    al cruce de su recta con la línea (≈842.3, 579.45), dentro del hueco, y toda la
    diagonal queda a ≤0.15 pt de su tinta (con su recta ya bien, la pasada de codos
    reconoce además el arquito con el que nace de la horizontal)."""
    import fitz
    import math
    with fitz.open(str(DU08)) as doc:
        res = rec.recognize_page(None, 25, utility="ELECTRICO", zoom=2.0, doc=doc)
    ink_a, ink_b = (796.14, 552.9), (836.4, 576.12)       # tramo recto de la tinta de la diagonal
    L = math.dist(ink_a, ink_b)
    u = ((ink_b[0] - ink_a[0]) / L, (ink_b[1] - ink_a[1]) / L)
    off = lambda q: abs((q[0] - ink_a[0]) * u[1] - (q[1] - ink_a[1]) * u[0])  # noqa: E731
    hits = []
    for pl in res.drawable:
        pts = [(x / 2.0, y / 2.0) for x, y in pl.pts_pdf]
        for k in range(len(pts) - 1):
            p, q = sorted(pts[k:k + 2])
            if 788 <= p[0] <= 797 and 549 <= p[1] <= 553 and 838 <= q[0] <= 852 and 577 <= q[1] <= 582:
                hits.append((p, q, pl.kinds[k:k + 2]))
    assert len(hits) == 1, hits
    p, q, _ = hits[0]
    assert 840.0 <= q[0] <= 852.0 and abs(q[1] - 579.4) <= 0.3, q     # en el hueco, sobre la línea
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):                          # la diagonal sobre su tinta
        s = (ink_a[0] + t * (ink_b[0] - ink_a[0]), ink_a[1] + t * (ink_b[1] - ink_a[1]))
        v = (q[0] - p[0], q[1] - p[1])
        w = ((s[0] - p[0]) * v[0] + (s[1] - p[1]) * v[1]) / (v[0] ** 2 + v[1] ** 2)
        foot = (p[0] + w * v[0], p[1] + w * v[1])
        assert math.dist(s, foot) <= 0.15, (t, s, foot)
    assert off(q) <= 0.1, q


@pytest.mark.skipif(not LABOE.exists(), reason="PDF de prueba LABOE no disponible")
def test_laboe_capa_0_solo_su_linea_de_alcantarillado():
    import fitz
    with fitz.open(str(LABOE)) as doc:
        page = doc[25]
        found = rec.page_letters(page)
        use = rec.letter_uses(found)["0"]
        assert use.utility is None and set(use.paths.values()) == {"ALCANTARILLADO"}
        mine = [d for d in page.get_drawings() if d.get("layer") == "0"]
        assert len(use.paths) < 0.25 * len(mine)          # comentarios y perfil quedan fuera
        res = rec.recognize_page(None, 25, utility="ALCANTARILLADO", zoom=2.0, doc=doc, letters=found)
        assert 1 <= sum(1 for p in res.drawable if p.layer_ocg == "0") <= 6
