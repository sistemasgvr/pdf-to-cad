"""Pruebas del núcleo geométrico de reconocimiento (recognition_geom) — headless.

Dos fuentes de verdad:
  1. PDFs SINTÉTICOS generados aquí con PyMuPDF: una capa OCG «LINES» con la
     utilidad ploteada como linetype explotado (guiones + letra «e» + huecos)
     y una capa «VAULTS» con rectángulos. Cada caso prueba UNA situación
     (recta, esquina, T, bóveda en medio, paralelas cercanas, corte real,
     leader continuo, arco discontinuo…) con resultado exacto conocido.
  2. El PDF real DU06 (si está en el repo): umbrales de cobertura por hoja.
"""
import math
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

import recognition_geom as G

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"
needs_pdf = pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")

# Patrón "── e ── e ──" parecido al del plano Metro: (guión, hueco, guión corto,
# hueco-con-letra, guión corto, hueco) en pt.
DASH_LONG, GAP, DASH_SHORT, GAP_LETTER = 22.0, 5.0, 7.0, 10.0
LETTER = 4.5


# ─────────────────────────── generador sintético ───────────────────────────
class Sheet:
    """Hoja sintética: acumula trazos por capa y los devuelve como paths de
    get_drawings() (sin escribir a disco: PyMuPDF renderiza en memoria)."""

    def __init__(self):
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=1000, height=800)
        self.oc = {name: self.doc.add_ocg(name) for name in ("LINES", "VAULTS")}

    def line(self, layer, a, b):
        sh = self.page.new_shape()
        sh.draw_line(fitz.Point(*a), fitz.Point(*b))
        sh.finish(color=(0.5, 0.5, 0.5), width=0.7, oc=self.oc[layer], closePath=False)
        sh.commit()

    def polyline(self, layer, pts):
        sh = self.page.new_shape()
        sh.draw_polyline([fitz.Point(*p) for p in pts])
        sh.finish(color=(0.5, 0.5, 0.5), width=0.7, oc=self.oc[layer], closePath=False)
        sh.commit()

    def letter_e(self, layer, cx, cy):
        """Una «e» como 10 segmentos rectos dentro de 4.5×4.5 pt (glifo SHX)."""
        r = LETTER / 2
        pts = [(cx - r, cy), (cx + r, cy), (cx + r, cy - r * 0.6), (cx + r * 0.4, cy - r),
               (cx - r * 0.4, cy - r), (cx - r, cy - r * 0.5), (cx - r, cy + r * 0.5),
               (cx - r * 0.4, cy + r), (cx + r * 0.4, cy + r), (cx + r, cy + r * 0.6)]
        self.polyline(layer, pts)

    def circle(self, layer, cx, cy, r):
        sh = self.page.new_shape()
        sh.draw_circle(fitz.Point(cx, cy), r)
        sh.finish(color=(0.4, 0.4, 0.4), width=0.7, oc=self.oc[layer])
        sh.commit()

    def rect(self, layer, x0, y0, x1, y1):
        sh = self.page.new_shape()
        sh.draw_rect(fitz.Rect(x0, y0, x1, y1))
        sh.finish(color=(0.4, 0.4, 0.4), width=0.7, oc=self.oc[layer])
        sh.commit()

    def dashed(self, a, b, skip=()):
        """Línea a→b ploteada con el linetype explotado. `skip` = lista de
        (t0, t1) en pt desde `a` donde NO se dibuja nada (bóveda, wipeout)."""
        ax, ay = a; bx, by = b
        L = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L, (by - ay) / L
        P = lambda t: (ax + ux * t, ay + uy * t)
        hidden = lambda t0, t1: any(not (t1 <= s0 or t0 >= s1) for s0, s1 in skip)
        t = 0.0
        period = [("d", DASH_LONG), ("g", GAP), ("d", DASH_SHORT), ("e", GAP_LETTER), ("d", DASH_SHORT), ("g", GAP)]
        while t < L:
            for kind, ln in period:
                t1 = min(L, t + ln)
                if kind == "d" and not hidden(t, t1) and t1 - t > 0.5:
                    self.line("LINES", P(t), P(t1))
                elif kind == "e" and t1 - t >= GAP_LETTER - 1e-6 and not hidden(t, t1):
                    cx, cy = P((t + t1) / 2)
                    self.letter_e("LINES", cx, cy)
                t = t1
                if t >= L:
                    break

    def dashed_arc(self, cx, cy, r, a0_deg, a1_deg):
        """Arco discontinuo: cada guión es una polilínea de 3 puntos sobre el arco."""
        total = math.radians(a1_deg - a0_deg) * r
        t = 0.0
        period = [("d", DASH_LONG), ("g", GAP), ("d", DASH_SHORT), ("e", GAP_LETTER), ("d", DASH_SHORT), ("g", GAP)]
        P = lambda s: (cx + r * math.cos(math.radians(a0_deg) + s / r), cy + r * math.sin(math.radians(a0_deg) + s / r))
        while t < total:
            for kind, ln in period:
                t1 = min(total, t + ln)
                if kind == "d" and t1 - t > 0.5:
                    self.polyline("LINES", [P(t), P((t + t1) / 2), P(t1)])
                elif kind == "e" and t1 - t >= GAP_LETTER - 1e-6:
                    self.letter_e("LINES", *P((t + t1) / 2))
                t = t1
                if t >= total:
                    break

    def paths(self):
        dr = self.page.get_drawings()
        lines = [d for d in dr if d.get("layer") == "LINES"]
        vaults = [d for d in dr if d.get("layer") == "VAULTS"]
        return lines, vaults

    def run(self):
        lines, vaults = self.paths()
        return G.reconstruct(lines, vaults)


def _near(p, q, tol=1.5):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol


# ─────────────────────────── casos sintéticos ───────────────────────────
def test_recta_simple_inicio_fin_exactos():
    sh = Sheet(); sh.dashed((100, 400), (700, 400))
    res = sh.run()
    assert res.pattern is not None
    assert abs(res.pattern.dash_long - DASH_LONG) <= 1
    assert res.pattern.gap_max <= GAP_LETTER + 1
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert len(pl.pts) == 2 and pl.kinds == ["end", "end"]
    # Inicio/fin = extremos del primer y último GUIÓN (nunca de una letra ni
    # más allá del último trazo dibujado: el período de 56 pt no cierra en 700).
    dashes, _, _ = G.classify_paths(sh.paths()[0])
    xs = [q[0] for d in dashes for q in (d.a, d.b)]
    lo, hi = sorted(pl.pts)
    assert _near(lo, (min(xs), 400), 0.5) and _near(hi, (max(xs), 400), 0.5)
    assert min(xs) == 100 and 694 <= max(xs) <= 700
    assert res.coverage >= 0.999 and not res.uncovered


def test_esquina_en_interseccion_exacta():
    sh = Sheet(); sh.dashed((100, 400), (400, 400)); sh.dashed((400, 400), (400, 150))
    res = sh.run()
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert len(pl.pts) == 3
    assert pl.kinds[1] == "corner" and _near(pl.pts[1], (400, 400), 0.5)
    assert res.coverage >= 0.999


def test_esquina_con_hueco_del_patron_en_la_esquina():
    # Las dos rectas terminan 6 pt antes de la esquina (hueco del linetype).
    sh = Sheet(); sh.dashed((100, 400), (394, 400)); sh.dashed((400, 394), (400, 150))
    res = sh.run()
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert pl.kinds[1] == "corner" and _near(pl.pts[1], (400, 400), 0.5)


def test_t_inserta_vertice_en_la_barra():
    sh = Sheet(); sh.dashed((100, 400), (700, 400)); sh.dashed((400, 396), (400, 150))
    res = sh.run()
    assert len(res.polylines) == 2
    bar = max(res.polylines, key=lambda p: p.length)
    stem = min(res.polylines, key=lambda p: p.length)
    assert "tee" in bar.kinds and len(bar.pts) == 3 and _near(bar.pts[1], (400, 400), 0.5)
    assert stem.kinds[0] == "tee" or stem.kinds[-1] == "tee"
    tee_pt = stem.pts[0] if stem.kinds[0] == "tee" else stem.pts[-1]
    assert _near(tee_pt, bar.pts[1], 1e-6)          # vértice compartido exacto
    assert res.coverage >= 0.999


def test_boveda_en_medio_une_y_pone_vertice():
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.dashed((100, 400), (700, 400), skip=[(283, 317)])   # hueco de 34 pt = bóveda
    res = sh.run()
    assert len(res.vaults) == 1 and not res.vault_orphans
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    # Siempre un quiebre donde choca con cada borde, y el nodo sobre la línea.
    assert sorted(pl.kinds) == sorted(["end", "edge", "vault", "edge", "end"]), pl.kinds
    assert _near(_kinds_at(pl, "vault")[0], (400, 400), 0.5)
    assert all(abs(p[1] - 400) < 0.5 for p in pl.pts)            # todo sobre la línea
    assert res.coverage >= 0.999


def test_boveda_en_extremo_de_dos_corridas_colineales():
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.dashed((100, 400), (383, 400)); sh.dashed((417, 400), (700, 400))
    res = sh.run()
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert sorted(pl.kinds) == sorted(["end", "edge", "vault", "edge", "end"]), pl.kinds
    assert _near(_kinds_at(pl, "vault")[0], (400, 400), 0.5)


def test_esquina_dentro_de_boveda_sin_linea_que_atraviese_para_en_los_bordes():
    """Dos líneas que solo LLEGAN a la bóveda (ninguna sigue del otro lado): no
    hay referencia para el giro interior → cada una termina en su borde."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.dashed((100, 400), (383, 400)); sh.dashed((400, 383), (400, 150))
    res = sh.run()
    assert len(res.polylines) == 2
    for pl in res.polylines:
        assert "stop" in pl.kinds and "vault" not in pl.kinds
        st = _kinds_at(pl, "stop")[0]
        assert _near(st, (384, 400), 1.2) or _near(st, (400, 384), 1.2)
    assert not res.vault_orphans


def test_boveda_huerfana_se_reporta():
    sh = Sheet(); sh.rect("VAULTS", 50, 50, 80, 80); sh.dashed((100, 400), (700, 400))
    res = sh.run()
    assert res.vault_orphans == [0]
    assert len(res.polylines) == 1 and len(res.polylines[0].pts) == 2


def test_paralelas_cercanas_no_se_mezclan():
    sh = Sheet(); sh.dashed((100, 400), (700, 400)); sh.dashed((100, 406), (700, 406))
    res = sh.run()
    assert len(res.polylines) == 2
    for pl in res.polylines:
        assert len(pl.pts) == 2
        assert abs(pl.pts[0][1] - pl.pts[1][1]) < 0.5      # cada una perfectamente horizontal
    assert res.coverage >= 0.999


def test_paralelas_que_terminan_a_la_misma_altura_no_forman_v():
    sh = Sheet(); sh.dashed((400, 100), (400, 500)); sh.dashed((421, 100), (421, 500))
    res = sh.run()
    assert len(res.polylines) == 2
    assert all(abs(pl.pts[0][0] - pl.pts[-1][0]) < 0.5 for pl in res.polylines)
    assert not any("bend" in pl.kinds for pl in res.polylines)


def test_corte_real_sin_evidencia_se_respeta():
    sh = Sheet(); sh.dashed((100, 400), (380, 400)); sh.dashed((460, 400), (700, 400))
    res = sh.run()
    assert len(res.polylines) == 2       # hueco de 80 pt sin letra ni bóveda = corte


def test_quiebre_suave_de_pocos_grados_se_encadena():
    sh = Sheet(); sh.dashed((100, 400), (400, 400)); sh.dashed((400, 400), (700, 415))  # ~3°
    res = sh.run()
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert len(pl.pts) == 3 and pl.kinds[1] in ("bend", "corner")
    assert res.coverage >= 0.999


def test_leader_continuo_suelto_queda_fuera_como_offpattern():
    """Un trazo continuo largo que no toca ni una corrida ni una bóveda es
    anotación (leader/flecha): no se importa."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.dashed((100, 400), (383, 400))
    sh.line("LINES", (470, 330), (600, 200))      # leader continuo lejos de todo
    sh.line("LINES", (600, 200), (603, 197))      # remate de flecha (3 pt)
    res = sh.run()
    assert len(res.polylines) == 1 and len(res.polylines[0].pts) == 2
    assert len(res.offpattern) == 1
    assert res.coverage >= 0.999


def test_transicion_continua_entre_dos_corridas_se_rescata():
    sh = Sheet()
    sh.dashed((100, 400), (380, 400))
    sh.line("LINES", (380, 400), (440, 340))      # jog continuo de 85 pt
    sh.dashed((440, 340), (700, 340))
    res = sh.run()
    assert not res.offpattern
    assert len(res.polylines) == 1
    assert len(res.polylines[0].pts) == 4         # inicio, 2 esquinas, fin
    assert res.coverage >= 0.999


def test_arco_discontinuo_sale_como_una_polilinea_suave():
    sh = Sheet(); sh.dashed_arc(400, 400, 200, 180, 270)     # cuarto de círculo
    res = sh.run()
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert 4 <= len(pl.pts) <= 20
    # Todos los vértices sobre el arco (radio 200 ± 2 pt)
    for p in pl.pts:
        assert abs(math.hypot(p[0] - 400, p[1] - 400) - 200) <= 2.0
    assert res.coverage >= 0.98


def test_linea_rotada_45_grados():
    sh = Sheet(); sh.dashed((100, 100), (600, 600))
    res = sh.run()
    assert len(res.polylines) == 1 and len(res.polylines[0].pts) == 2
    assert res.coverage >= 0.999


def test_cruce_sin_extremos_no_crea_nodo():
    sh = Sheet(); sh.dashed((100, 400), (700, 400)); sh.dashed((400, 100), (400, 700))
    res = sh.run()
    assert len(res.polylines) == 2
    assert all(len(pl.pts) == 2 for pl in res.polylines)


def test_determinista():
    sh = Sheet(); sh.dashed((100, 400), (700, 400)); sh.dashed((400, 396), (400, 150))
    lines, vaults = sh.paths()
    a = G.reconstruct(lines, vaults); b = G.reconstruct(list(reversed(lines)), vaults)
    key = lambda r: sorted((tuple(round(v, 3) for p in pl.pts for v in p), tuple(pl.kinds)) for pl in r.polylines)
    assert key(a) == key(b)


# ─────────────────────────── PDF real ───────────────────────────
def _sheet_result(page_index):
    doc = fitz.open(str(PDF))
    dr = doc[page_index].get_drawings()
    lines = [d for d in dr if (d.get("layer") or "").endswith("C-ELEC-UNGD-E")]
    vaults = [d for d in dr if (d.get("layer") or "").endswith(("C-ELEC-VALT-E", "V-ELEC-MANH"))]
    return G.reconstruct(lines, vaults)


@needs_pdf
@pytest.mark.parametrize("page_index,min_cov", [(13, 0.985), (7, 0.999), (2, 0.985), (3, 0.995)])
def test_du06_cobertura(page_index, min_cov):
    res = _sheet_result(page_index)
    assert res.coverage >= min_cov, f"cobertura {res.coverage:.3f} en hoja {page_index + 1}"
    assert not res.vault_orphans
    # Ningún vértice con NaN / ninguna polilínea degenerada
    for pl in res.polylines:
        assert len(pl.pts) >= 2 and len(pl.pts) == len(pl.kinds)
        assert all(math.isfinite(v) for p in pl.pts for v in p)


@needs_pdf
def test_du06_hoja14_sin_segmentos_inventados():
    """Ningún segmento con rumbo que no exista entre los guiones de la hoja
    (la hoja 14 solo tiene líneas rectas H/V y quiebres de pocos grados)."""
    res = _sheet_result(13)
    doc = fitz.open(str(PDF))
    lines = [d for d in doc[13].get_drawings() if (d.get("layer") or "").endswith("C-ELEC-UNGD-E")]
    dashes, _, curves = G.classify_paths(lines)
    angles = {round(d.angle) for d in dashes}
    # Las transiciones continuas (jogs/codos) también son geometría real del PDF.
    for c in curves:
        for a, b in zip(c, c[1:]):
            angles.add(round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180))
    for pl in res.polylines:
        for (a, ka), (b, kb) in zip(zip(pl.pts, pl.kinds), zip(pl.pts[1:], pl.kinds[1:])):
            if "edge" in (ka, kb) or "curve" in (ka, kb) or math.hypot(b[0] - a[0], b[1] - a[1]) < 8.0:
                continue          # tramo sintético, curva simplificada o conector corto en un nodo
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
            assert any(G._ang_diff(ang, x) <= 1.5 for x in angles), (a, b)
    kinds = [k for pl in res.polylines for k in pl.kinds]
    assert kinds.count("vault") >= 3           # las 3 bóvedas quedan como vértices
    assert "junction" not in kinds


# ── Casos del plan "motor Shapely" (regla de oro del snap), cubiertos por el núcleo actual ──
def test_plan_paralelas_a_3pt_no_comparten_extremo():
    """Dos corridas paralelas con offset lateral 3 pt terminan a la misma altura:
    el imán NUNCA debe fusionarlas ni compartir un nodo."""
    sh = Sheet(); sh.dashed((100, 400), (600, 400)); sh.dashed((100, 403), (600, 403))
    res = sh.run()
    assert len(res.polylines) == 2
    ends = [p for pl in res.polylines for p in (pl.pts[0], pl.pts[-1])]
    assert len({(round(x, 3), round(y, 3)) for x, y in ends}) == 4     # 4 extremos distintos
    assert all(abs(pl.pts[0][1] - pl.pts[-1][1]) < 0.5 for pl in res.polylines)
    assert res.coverage >= 0.999


def test_plan_hueco_30pt_se_puentea_solo_con_evidencia():
    """Hueco de 30 pt entre guiones colineales: con una letra «e» encima se une
    (misma corrida); sin nada encima es un corte real y NO se inventa un puente."""
    sh = Sheet(); sh.dashed((100, 400), (385, 400)); sh.dashed((415, 400), (700, 400))
    sh.letter_e("LINES", 400, 400)
    res = sh.run()
    assert len(res.polylines) == 1 and len(res.polylines[0].pts) == 2

    sh2 = Sheet(); sh2.dashed((100, 400), (385, 400)); sh2.dashed((415, 400), (700, 400))
    res2 = sh2.run()
    assert len(res2.polylines) == 2


def _overlap_len(a, b, tol=1.5, step=2.0):
    """Longitud de `a` (polilínea) que está a ≤tol de `b`."""
    total = 0.0
    segs_b = list(zip(b.pts, b.pts[1:]))
    for p, q in zip(a.pts, a.pts[1:]):
        L = math.hypot(q[0] - p[0], q[1] - p[1]); n = max(1, int(L / step))
        for k in range(n + 1):
            t = k / n; x, y = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
            if any(G._pt_seg_dist((x, y), sa, sb) <= tol for sa, sb in segs_b):
                total += L / n
    return total


def test_linea_con_deriva_no_genera_corridas_superpuestas():
    """Una línea CAD "casi recta" con deriva de 2 pt (dos semillas casi
    coincidentes) debe salir como UNA polilínea, nunca como dos superpuestas
    que terminan en el mismo nodo (caso real de la hoja 14, bóveda 988,1223)."""
    sh = Sheet()
    sh.rect("VAULTS", 985, 385, 1015, 415)
    sh.dashed((100, 398), (500, 400)); sh.dashed((500, 400), (983, 401.5))   # deriva 2 pt
    sh.dashed((1017, 401.5), (1400, 403))
    res = sh.run()
    assert len(res.polylines) == 1, [pl.pts for pl in res.polylines]
    pl = res.polylines[0]
    assert "vault" in pl.kinds and res.coverage >= 0.999
    assert all(k in ("end", "bend", "vault", "edge") for k in pl.kinds)


@needs_pdf
def test_du06_hoja14_sin_polilineas_superpuestas():
    res = _sheet_result(13)
    pls = res.polylines
    for i in range(len(pls)):
        for j in range(i + 1, len(pls)):
            ov = _overlap_len(pls[i], pls[j])
            # Dos conduits que salen de la misma bóveda casi paralelos comparten
            # ~20 pt junto al nodo; el duplicado real que se corrigió medía 158 pt.
            assert ov <= 30.0, f"polilíneas {i} y {j} se superponen {ov:.0f} pt"


# ─────────────────── Casos de los apuntes (bóvedas como referencia) ───────────────────
def _kinds_at(pl, kind):
    return [p for p, k in zip(pl.pts, pl.kinds) if k == kind]


def _oriented(pl, last_kind):
    """La polilínea con el vértice de tipo `last_kind` al final (la orientación
    del ensamblado es arbitraria)."""
    if pl.kinds[-1] != last_kind and pl.kinds[0] == last_kind:
        return G.Polyline(pl.pts[::-1], pl.kinds[::-1])
    return pl


def test_caso1_linea_sola_llega_al_borde_del_buzon_y_ahi_queda():
    """Caso 1 (revisado): la línea llega por su propia recta hasta el borde del
    buzón; como es la única, no se inventa nada dentro: la caja queda ahí."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.circle("VAULTS", 406, 406, 4)              # manhole descentrado = referencia
    sh.dashed((100, 396), (395, 396))             # entra 10 pt dentro de la bóveda
    res = sh.run()
    assert len(res.polylines) == 1
    pl = _oriented(res.polylines[0], "stop")
    # Punto de llegada al buzón = borde izquierdo; sin tramo inventado hacia el círculo.
    assert pl.kinds[-1] == "stop" and _near(pl.pts[-1], (384, 396), 1.2)
    assert "vault" not in pl.kinds and "edge" not in pl.kinds
    assert abs(pl.pts[0][1] - pl.pts[-1][1]) < 0.5                          # no se inclinó


def test_caso2_linea_que_atraviesa_y_dos_conduits_convergen_al_centro():
    """Caso 2: quiebre en cada borde y la referencia como vértice; dos conduits
    paralelos que entran por abajo nacen ambos en la referencia."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.circle("VAULTS", 402, 404, 4)
    sh.dashed((100, 398), (700, 398))             # atraviesa, 6 pt sobre la referencia
    sh.dashed((398, 700), (398, 417)); sh.dashed((404, 700), (404, 417))   # dos verticales, 6 pt entre sí
    res = sh.run()
    longest = max(res.polylines, key=lambda p: p.length)
    verts = [p for p in res.polylines if p is not longest]
    through = longest
    if through.pts[0][0] > through.pts[-1][0]:
        through = G.Polyline(through.pts[::-1], through.kinds[::-1])
    assert through.kinds == ["end", "edge", "vault", "edge", "end"], through.kinds
    # El nodo se calcula con las llegadas (no con el círculo): sobre la
    # horizontal (y=398) y entre las dos verticales (x=398 y 404) → (401, 398).
    assert _near(through.pts[2], (401, 398), 0.5)
    assert _near(through.pts[1], (384, 398), 1.2) and _near(through.pts[3], (416, 398), 1.2)
    assert len(verts) == 2
    for pl in verts:
        assert "vault" in pl.kinds and _near(_kinds_at(pl, "vault")[0], (401, 398), 0.5)
        assert "edge" in pl.kinds and abs(_kinds_at(pl, "edge")[0][1] - 416) <= 1.2   # borde inferior
        # Un solo tramo recto borde → nodo (sin quiebre intermedio).
        assert "bend" not in pl.kinds
    assert res.coverage >= 0.999


def test_caso3_sin_linea_que_atraviese_todo_para_en_el_borde():
    """Caso 3 (revisado): bóveda grande; ninguna línea la atraviesa → sin
    referencia: la vertical y el stub llegan SOLO hasta el borde (el usuario
    completa a mano). La cajita interior no se usa."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 300, 415, 410)          # 30 × 110
    sh.rect("VAULTS", 395, 320, 405, 330)          # cajita = referencia (400, 325)
    sh.dashed((399, 700), (399, 405))              # vertical desde abajo, apunta a la cajita
    sh.dashed((250, 395), (390, 395))              # stub lateral, 70 pt por debajo de la referencia
    res = sh.run()
    vert = _oriented(max(res.polylines, key=lambda p: p.length), "stop")
    assert vert.kinds[-1] == "stop" and abs(vert.pts[-1][1] - 411) <= 1.2   # borde inferior
    stub = _oriented(min(res.polylines, key=lambda p: p.length), "stop")
    assert stub.kinds[-1] == "stop" and _near(stub.pts[-1], (384, 395), 1.2)
    assert all("vault" not in pl.kinds for pl in res.polylines)   # nada inventado hacia la cajita


def test_caso3_curva_continua_desde_la_boveda_es_utilidad_roja():
    """Caso 3: un conduit curvo sale de la bóveda como trazo continuo (el linetype
    no cabe): es utilidad (se importa, con sus quiebres), no un leader."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.circle("VAULTS", 400, 400, 4)
    sh.dashed((100, 400), (383, 400))
    arc = [(400, 386)] + [(400 + 120 * math.sin(t), 386 - 120 * (1 - math.cos(t))) for t in
                          (0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.05, 1.2)]
    sh.polyline("LINES", arc)                      # curva continua que arranca en el borde superior
    res = sh.run()
    assert not res.offpattern
    curve = [pl for pl in res.polylines if "curve" in pl.kinds]
    assert curve, [pl.kinds for pl in res.polylines]
    assert "stop" in curve[0].kinds          # llega al borde del buzón y ahí queda


def test_caso4_lineas_convergentes_nacen_en_una_sola():
    """Caso 4: dos conduits casi paralelos que se juntan: el que termina nace
    de la otra línea con un vértice compartido (no dos líneas encimadas)."""
    sh = Sheet()
    sh.dashed((100, 400), (900, 400))              # línea principal
    sh.dashed((100, 412), (500, 401.5))            # converge en ~1.7° y muere a 1.5 pt de la principal
    res = sh.run()
    assert len(res.polylines) == 2
    main = max(res.polylines, key=lambda p: p.length)
    branch = min(res.polylines, key=lambda p: p.length)
    assert "tee" in main.kinds and "tee" in branch.kinds
    assert _near(_kinds_at(main, "tee")[0], _kinds_at(branch, "tee")[0], 1e-6)   # vértice compartido
    assert abs(_kinds_at(main, "tee")[0][1] - 400) < 0.5                          # sobre la principal
    assert res.coverage >= 0.999


def test_continuidad_con_stub_colineal_al_otro_lado_de_la_boveda():
    """Imagen 2 del usuario: una línea larga llega por el este y un stub corto
    sale por el oeste, colineales → es la MISMA línea que atraviesa; la vertical
    que llega por el norte se une al nodo sobre esa línea."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 385, 415, 415)
    sh.dashed((700, 400), (417, 400))              # línea larga, llega por el este
    sh.dashed((383, 400), (350, 400))              # stub corto (1 guión) al oeste, colineal
    sh.dashed((400, 150), (400, 383))              # vertical que llega por el norte
    res = sh.run()
    horiz = max(res.polylines, key=lambda p: p.length)
    assert "vault" in horiz.kinds and horiz.kinds.count("edge") == 2
    xs = sorted(p[0] for p in horiz.pts)
    assert xs[0] <= 351 and xs[-1] >= 690          # una sola polilínea de 350 a 700
    vert = min(res.polylines, key=lambda p: p.length)
    assert "vault" in vert.kinds and _near(_kinds_at(vert, "vault")[0], (400, 400), 0.5)
    assert len(res.polylines) == 2


def test_curvas_continuas_no_se_cosen_entre_si_en_la_punta():
    """Imagen 3 del usuario: tres conduits continuos salen de la bóveda y quedan
    cortados en el mismo límite de vista: cada uno es su polilínea; sus puntas no
    se unen entre sí formando zigzags."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 300, 415, 410)
    sh.polyline("LINES", [(392, 299), (380, 240), (378, 200)])   # casi vertical (un solo trazo)
    sh.polyline("LINES", [(400, 299), (430, 220), (440, 200)])   # diagonal (un solo trazo)
    sh.line("LINES", (408, 299), (409, 200))                     # vertical
    res = sh.run()
    assert len(res.polylines) == 3
    for pl in res.polylines:
        assert pl.kinds.count("stop") == 1 and pl.kinds.count("end") == 1
        assert "corner" not in pl.kinds and "junction" not in pl.kinds


def test_clip_path_recorta_por_el_marco_y_marca_los_cortes():
    """Recorte por el polígono de clip del PDF: la geometría fuera del marco se
    descarta, el punto de corte queda registrado y NO se trata como extremo real
    (dos conduits cortados por el mismo marco no se unen en la punta)."""
    frame = [(0, 100), (500, 100), (500, 500), (0, 500)]        # marco: y ≥ 100
    path = {"items": [("l", (200, 400), (250, 50))], "rect": G._Rect(200, 50, 250, 400), "layer": "L"}
    clipped = G.clip_path(path, [frame])
    assert clipped is not None and len(clipped["items"]) == 1
    (_, a, b), = clipped["items"]
    assert min(a[1], b[1]) == pytest.approx(100, abs=1e-6)        # termina en el marco
    assert len(clipped["cut_pts"]) == 1 and clipped["cut_pts"][0][1] == pytest.approx(100, abs=1e-6)
    assert G.clip_path({"items": [("l", (10, 10), (20, 20))], "rect": G._Rect(10, 10, 20, 20)}, [frame]) is None

    # Dos trazos continuos que salen de una bóveda y mueren en el marco (puntas a 3 pt)
    vault = {"items": [("re", G._Rect(380, 420, 420, 460))], "rect": G._Rect(380, 420, 420, 460), "layer": "V"}
    d1 = G.clip_path({"items": [("l", (395, 419), (405, 60))], "rect": G._Rect(395, 60, 405, 419), "layer": "L"}, [frame])
    d2 = G.clip_path({"items": [("l", (405, 419), (445, 60))], "rect": G._Rect(405, 60, 445, 419), "layer": "L"}, [frame])
    res = G.reconstruct([d1, d2], [vault])
    assert len(res.polylines) == 2
    for pl in res.polylines:
        assert "cut" in pl.kinds and "stop" in pl.kinds
        assert "corner" not in pl.kinds and "junction" not in pl.kinds


# ─────────────────────── utilidad abandonada («──/── e ──») ───────────────────────
def _slashes(sh, a, b, every=60.0, size=7.5):
    """Barras «/» del linetype abandonado: trazo corto a ~60° que cruza la línea
    (centrado sobre ella) cada `every` pt desde `a`."""
    ax, ay = a; bx, by = b
    L = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L, (by - ay) / L
    nx, ny = -uy, ux
    t = every / 2
    while t < L:
        cx, cy = ax + ux * t, ay + uy * t
        h = size / 2
        dx, dy = ux * h * 0.5 + nx * h * 0.87, uy * h * 0.5 + ny * h * 0.87
        sh.line("LINES", (cx - dx, cy - dy), (cx + dx, cy + dy))
        t += every


def test_abandonada_barras_son_marcadores_no_guiones_sin_cubrir():
    sh = Sheet()
    sh.dashed((100, 400), (700, 400))
    _slashes(sh, (100, 400), (700, 400))
    res = sh.run()
    assert len(res.polylines) == 1
    pl = res.polylines[0]
    assert pl.kinds == ["end", "end"] and abs(pl.pts[0][1] - 400) < 0.5 and abs(pl.pts[1][1] - 400) < 0.5
    assert res.coverage >= 0.999 and not res.uncovered
    assert res.n_glyphs >= 10 + 9          # letras + 10 barras


def test_abandonada_barras_no_deforman_esquina():
    sh = Sheet()
    sh.dashed((100, 400), (500, 400)); sh.dashed((500, 400), (500, 150))
    _slashes(sh, (100, 400), (500, 400)); _slashes(sh, (500, 400), (500, 150))
    res = sh.run()
    assert len(res.polylines) == 1 and res.coverage >= 0.999
    pl = res.polylines[0]
    assert "corner" in pl.kinds and _near(_kinds_at(pl, "corner")[0], (500, 400), 0.5)


def test_boveda_dibujada_en_la_misma_capa_es_lazo_no_linea():
    """Caso abandonada (hoja 9 del DU06): el contorno de la bóveda está en la
    capa de líneas, ploteado con el mismo linetype. El lazo rectangular pasa a
    ser bóveda: la línea que llega para en su borde y el contorno no se dibuja."""
    sh = Sheet()
    x0, y0, x1, y1 = 500, 380, 560, 420
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        sh.dashed(a, b)
    sh.dashed((100, 400), (x0 - 1, 400))
    _slashes(sh, (100, 400), (x0 - 1, 400))
    res = sh.run()
    assert len(res.vaults) == 1
    v = res.vaults[0]
    assert abs(v.x0 - x0) < 2 and abs(v.y0 - y0) < 2 and abs(v.x1 - x1) < 2 and abs(v.y1 - y1) < 2
    assert len(res.polylines) == 1, [pl.kinds for pl in res.polylines]
    pl = _oriented(res.polylines[0], "stop")
    assert pl.kinds[-1] == "stop" and _near(pl.pts[-1], (x0, 400), 1.5)
    assert res.coverage >= 0.999                       # los guiones del contorno no cuentan


def test_lazo_grande_no_es_boveda():
    """Un anillo de red de 300×200 pt no es un símbolo: sigue siendo línea."""
    sh = Sheet()
    x0, y0, x1, y1 = 300, 200, 600, 400
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        sh.dashed(a, b)
    res = sh.run()
    assert not res.vaults
    assert sum(k == "corner" for pl in res.polylines for k in pl.kinds) >= 3
    assert res.coverage >= 0.999


def test_trazo_continuo_que_nace_en_el_borde_no_es_continuidad():
    """Una línea llega a la bóveda por la izquierda; por la derecha sale un trazo
    CONTINUO (sin patrón) colineal. No es la misma línea que atraviesa: ambos
    paran en el borde (mock del usuario, hoja 9)."""
    sh = Sheet()
    sh.rect("VAULTS", 500, 380, 560, 420)
    sh.dashed((100, 400), (499, 400))
    sh.polyline("LINES", [(561, 401), (600, 401), (615, 392)])
    res = sh.run()
    assert all("vault" not in pl.kinds for pl in res.polylines)
    stops = [p for pl in res.polylines for p in _kinds_at(pl, "stop")]
    assert any(_near(p, (500, 400), 1.5) for p in stops) and any(_near(p, (560, 401), 1.5) for p in stops)


def test_trazo_continuo_que_cruza_la_boveda_si_es_continuidad():
    """El mismo trazo continuo pero entrando por la derecha y cruzando la bóveda
    hasta el borde izquierdo (transición, hoja 12): sí es la línea que sigue."""
    sh = Sheet()
    sh.rect("VAULTS", 500, 380, 560, 420)
    sh.dashed((100, 400), (499, 400))
    sh.polyline("LINES", [(501, 400), (620, 400), (640, 390)])
    res = sh.run()
    assert any("vault" in pl.kinds for pl in res.polylines)


# ─────────────────────── T sobre otra corrida (hoja 9, precisión de quiebres) ───────────────────────
def test_extremo_que_muere_sobre_otra_linea_es_T_no_esquina_con_un_tercero():
    """Diagonal que muere SOBRE la horizontal y, 35 pt más allá, otra rama que
    nace de la horizontal: antes se emparejaban entre sí como esquina fuera de
    la línea; ahora cada una es una T sobre la horizontal (vértice sobre la capa)."""
    sh = Sheet()
    sh.dashed((100, 400), (700, 400))                       # H
    sh.dashed((150, 600), (320, 400))                       # diagonal que muere en H (x=320)
    sh.dashed((355, 400), (520, 560))                       # rama que nace de H (x=355)
    res = sh.run()
    assert res.coverage >= 0.999
    H = max(res.polylines, key=lambda p: p.length)
    tees = _kinds_at(H, "tee")
    assert any(_near(t, (320, 400), 2.0) for t in tees) and any(_near(t, (355, 400), 2.0) for t in tees), H.kinds
    assert all(abs(p[1] - 400) < 0.6 for p in H.pts)          # ningún vértice fuera de la horizontal
    assert not any(k in ("corner", "junction") for pl in res.polylines for k in pl.kinds)


def test_tick_de_fin_de_tramo_es_extremo_con_T_en_el_medio():
    """«──┤»: la horizontal muere en el centro de un tick corto perpendicular.
    El tick queda extremo–T–extremo y sus puntas NUNCA se unen a otra línea
    cercana: ni a la que pasa ~5 pt por debajo ni a la que MUERE a 4 pt de su
    punta (hoja 9: «ahí nunca se une»)."""
    sh = Sheet()
    sh.dashed((100, 400), (500, 400))
    sh.line("LINES", (500, 393), (500, 407))                # tick de 14 pt centrado en la línea
    sh.dashed((450, 408), (700, 428))                       # otra línea que pasa ~5 pt bajo el tick
    sh.dashed((504, 411), (600, 520))                       # ramal que muere a 4 pt de la punta
    res = sh.run()
    tick = [pl for pl in res.polylines if len(pl.pts) == 3 and all(abs(p[0] - 500) < 0.6 for p in pl.pts)]
    assert tick, [pl.kinds for pl in res.polylines]
    assert sorted(tick[0].kinds) == ["end", "end", "tee"]
    assert abs(min(p[1] for p in tick[0].pts) - 393) < 0.6 and abs(max(p[1] for p in tick[0].pts) - 407) < 0.6
    ramal = [pl for pl in res.polylines if any(_near(p, (600, 520), 1.5) for p in pl.pts)][0]
    assert not any(abs(p[0] - 500) < 1.0 for p in ramal.pts)   # ningún vértice sobre el tick
    assert _near(_kinds_at(tick[0], "tee")[0], (500, 400), 0.6)
    H = [pl for pl in res.polylines if any(_near(p, (100, 400), 1.5) for p in pl.pts)][0]
    assert _near(_oriented(H, "tee").pts[-1], (500, 400), 0.6)
    assert res.coverage >= 0.999


def test_cruce_en_x_con_hueco_no_es_T():
    """Vertical que cruza una horizontal con el hueco del patrón justo en el
    cruce: sigue siendo UNA vertical (quiebre suave), sin T sobre la horizontal."""
    sh = Sheet()
    sh.dashed((100, 400), (700, 400))
    sh.dashed((400, 150), (400, 393)); sh.dashed((400, 407), (400, 650))
    res = sh.run()
    vert = [pl for pl in res.polylines if all(abs(p[0] - 400) < 0.6 for p in pl.pts)]
    assert len(vert) == 1 and sorted(vert[0].kinds)[0] == "bend" or vert[0].kinds == ["end", "end"], [pl.kinds for pl in res.polylines]
    H = [pl for pl in res.polylines if any(_near(p, (100, 400), 1.5) for p in pl.pts)][0]
    assert "tee" not in H.kinds and "junction" not in H.kinds


def test_linea_que_atraviesa_boveda_y_sigue_un_trozo_corto():
    """Sale de la bóveda y termina 15 pt más allá: borde, nodo, borde y extremo
    (antes el trozo corto se recortaba al borde y quedaba sin cubrir)."""
    sh = Sheet()
    sh.rect("VAULTS", 385, 300, 415, 400)
    sh.dashed((400, 100), (400, 299)); sh.dashed((400, 401), (400, 416))
    res = sh.run()
    assert res.coverage >= 0.999 and not res.uncovered
    pl = max(res.polylines, key=lambda p: p.length)
    ends = _kinds_at(pl, "end")
    assert any(_near(e, (400, 416), 1.0) for e in ends) and any(_near(e, (400, 100), 1.0) for e in ends)
    assert "vault" in pl.kinds and pl.kinds.count("edge") == 2


def test_ramal_misma_capa_se_une_por_el_codo_y_el_otro_extremo_queda_libre():
    """Horizontal + codo + vertical (un guión de 34 pt y letra) son la misma
    capa: una polilínea del ramal nace en la horizontal, quiebra en el codo y
    termina en el último guión. No es leader."""
    sh = Sheet()
    sh.dashed((100, 400), (700, 400))
    sh.polyline("LINES", [(400, 404), (406, 412), (412, 422)])
    sh.line("LINES", (412, 426), (412, 448))          # 22 pt, del patrón
    sh.letter_e("LINES", 412, 453)
    sh.line("LINES", (412, 458), (412, 492))          # 34 pt, pasa 1.5×22
    res = sh.run()
    assert not res.offpattern
    branch = [pl for pl in res.polylines if any(_near(p, (412, 492), 2.0) for p in pl.pts)]
    assert len(branch) == 1
    pl = branch[0]
    assert any(k in ("corner", "bend", "curve") for k in pl.kinds)
    assert any(_near(p, (412, 492), 2.0) and k == "end" for p, k in zip(pl.pts, pl.kinds))
    main = [q for q in res.polylines if q is not pl and any(abs(p[1] - 400) < 3 and 150 < p[0] < 650 for p in q.pts)]
    assert main and any(_near(a, b, 1.5) for a in pl.pts for b in main[0].pts)


@needs_pdf
def test_du06_hoja15_ramal_comparte_vertice_con_la_horizontal():
    """El vertical en x≈1103 no es off-pattern: nace en la horizontal (T) y
    tiene quiebre en el codo; el extremo libre es el último guión."""
    res = _sheet_result(14)
    assert not any(abs(pl.pts[0][0] - 1103) < 2 and abs(pl.pts[-1][0] - 1103) < 2
                   for pl in res.offpattern)
    branch = [pl for pl in res.polylines
              if any(abs(p[0] - 1103.4) < 3 and abs(p[1] - 1271) < 3 for p in pl.pts)]
    assert branch
    pl = branch[0]
    assert any(k in ("corner", "bend", "curve") for k in pl.kinds)
    main = [q for q in res.polylines if q is not pl
            and any(abs(p[1] - 1196) < 4 and 400 < p[0] < 1600 for p in q.pts)]
    assert main and any(_near(a, b, 1.5) for a in pl.pts for b in main[0].pts)


class _Rect:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


def _dash_path(layer, a, b):
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    return {"layer": layer, "rect": _Rect(x0, y0, x1, y1),
            "items": [("l", a, b)], "closePath": False}


def _box_path(layer, x0, y0, x1, y1):
    return {"layer": layer, "rect": _Rect(x0, y0, x1, y1),
            "items": [("re", _Rect(x0, y0, x1, y1))], "closePath": True}


def test_cluster_vaults_rechaza_linetype_y_no_mezcla_capas():
    """Guiones abiertos (linetype) no son bóvedas; un rectángulo cerrado sí.
    Clusterizar por OCG: los guiones de otra capa no inflan el bbox del símbolo."""
    dashes = [_dash_path("ESFV", (100 + i * 40, 400), (118 + i * 40, 400)) for i in range(12)]
    box = _box_path("VALT", 200, 380, 230, 410)
    assert G.cluster_vaults(dashes) == []
    vs = G.cluster_vaults(dashes + [box])
    assert len(vs) == 1
    cx, cy = vs[0].center
    assert abs(cx - 215) < 1 and abs(cy - 395) < 1
    assert vs[0].x1 - vs[0].x0 <= 32


def test_guiones_en_capa_boveda_no_deforman_la_linea():
    """Capa de «estructuras» que en realidad es un linetype: no parte ni imana
    la utilidad de LINES (equivalente sintético de ESFV-STRUCT sobre UNGD)."""
    sh = Sheet()
    sh.dashed((100, 400), (700, 400))
    for x in range(120, 680, 40):
        sh.line("VAULTS", (x, 398), (x + 18, 398))
    dirty = sh.run()
    clean = Sheet(); clean.dashed((100, 400), (700, 400))
    base = clean.run()
    assert not dirty.vaults
    assert [(pl.pts, pl.kinds) for pl in dirty.polylines] == [(pl.pts, pl.kinds) for pl in base.polylines]


def test_dos_ocg_de_lineas_no_comparten_vertices():
    """Cada reconstruct() solo ve sus paths: una capa paralela no aporta vértices."""
    a = Sheet(); a.dashed((100, 400), (700, 400))
    b = Sheet(); b.dashed((100, 430), (700, 430))
    la, _ = a.paths(); lb, _ = b.paths()
    ga = G.reconstruct(la, [])
    gab = G.reconstruct(la + lb, [])
    assert len(ga.polylines) == 1
    assert len(gab.polylines) >= 2
    ga2 = G.reconstruct(la, [])
    assert [(p.pts, p.kinds) for p in ga.polylines] == [(p.pts, p.kinds) for p in ga2.polylines]
    # Los paths de B, pasados como bóvedas (guiones abiertos), no cambian A.
    mix = G.reconstruct(la, lb)
    assert [(p.pts, p.kinds) for p in ga.polylines] == [(p.pts, p.kinds) for p in mix.polylines]
