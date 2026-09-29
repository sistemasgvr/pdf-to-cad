"""Regressions for the five curve details reported on DU06 sheets 4 and 5."""
import math
from pathlib import Path

import pytest

import recognition as rec
import recognition_geom as geom
import recognition_trace as trace
import model_ops
from recognition_bezier import flatten_cubic

PDF = Path(__file__).resolve().parents[1] / 'DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf'


def _circle(r, sweep, scale=1.):
    n = max(12, math.ceil(abs(sweep)/(2*math.acos(1-.02/r))))
    return [(scale*r*math.cos(sweep*i/n), scale*r*math.sin(sweep*i/n)) for i in range(n+1)]


def _editor(data):
    pts, kinds, fillets = data
    for i, fl in fillets.items():
        geo = model_ops.fillet_geo(pts[i-1], pts[i], pts[i+1], fl['r_px'],
                                  max_frac=1., max_frac_next=1., tol_r=0.)
        assert geo is not None
        assert geo['r'] == pytest.approx(fl['r_px'], abs=1e-5)
        assert math.dist(geo['t1'], fl['a']) < 1e-5
        assert math.dist(geo['t2'], fl['b']) < 1e-5


@pytest.mark.parametrize('scale', [1., 3.5, 7.])
@pytest.mark.parametrize('radius,degrees', [(5., 90), (26., 270), (2000., 5), (40., -300)])
def test_circular_reconstruction_preserves_sweep_and_editor(radius, degrees, scale):
    P = _circle(radius, math.radians(degrees), scale)
    parts = trace.circular_trace(P, scale)
    assert all(p[2] is not None for p in parts)
    assert sum(p[2][5] for p in parts) == pytest.approx(math.radians(degrees), abs=1e-7)
    assert max(min(trace._arc_distance(q, part) for part in parts) for q in P) < 1e-5
    _editor(trace._encode(parts, 'end', 'end'))


def test_bezier_uses_evaluated_ink_in_both_readers():
    fitz = pytest.importorskip('fitz')
    handles = [(0., 0.), (0., 100.), (100., 100.), (100., 0.)]
    path = {'items': [('c', *(fitz.Point(*p) for p in handles))]}
    P = flatten_cubic(handles)
    assert P[0] == handles[0] and P[-1] == handles[-1]
    assert (50., 75.) in P
    assert max(p[1] for p in P) == 75.
    assert geom._path_chains(path) == [P]
    assert rec.ink_strokes([path], lambda p: p) == [P]


def test_collinear_bezier_that_reverses_does_not_collapse():
    P = flatten_cubic([(0, 0), (100, 0), (-100, 0), (0, 0)])
    assert len(P) > 4 and max(x for x, y in P) > 20 and min(x for x, y in P) < -20


def test_glyph_mask_recovers_only_curve_supported_by_neighbouring_circle():
    from recognition_arcs import arc_pieces
    a = [(40*math.cos(t), 40*math.sin(t)) for t in [i*.04 for i in range(9)]]
    b = [(40*math.cos(t), 40*math.sin(t)) for t in [.40+i*.04 for i in range(9)]]
    box = [(min(x for x, y in a), min(y for x, y in a),
            max(x for x, y in a), max(y for x, y in a))]
    isolated, _ = arc_pieces([a], glyph_boxes=box)
    assert not isolated
    pieces, straights = arc_pieces([a, b], glyph_boxes=box)
    assert len(pieces) == 2
    assert not straights


@pytest.fixture(scope='module')
def sheets():
    if not PDF.is_file():
        pytest.skip('DU06 PDF unavailable')
    return {(page, utility): rec.recognize_page(PDF, page-1, utility=utility, zoom=3.5)
            for page, utility in [(4, 'TELECOM'), (5, 'TELECOM'), (5, 'ELECTRICO')]}


def test_reported_s_curve_ends_at_cut_with_fifth_arc(sheets):
    pl = next(p for p in sheets[4, 'TELECOM'].drawable
              if p.layer_ocg.endswith('-E') and math.dist(p.pts_pdf[0], (406.2*3.5, 1416.9*3.5)) < 1.)
    assert len(pl.fillets) == 5
    assert pl.kinds[-1] == 'cut'
    assert pl.pts_pdf[-1][1]/3.5 == pytest.approx(1491.9, abs=.01)
    _editor((pl.pts_pdf, pl.kinds, pl.fillets))


def test_short_dash_does_not_create_second_vault_connection(sheets):
    lines = [p for p in sheets[4, 'TELECOM'].drawable if p.layer_ocg.endswith('-E')]
    assert not any(math.dist(p.pts_pdf[0], (794.94*3.5, 1021.5*3.5)) < 1 for p in lines)
    assert any(p.pts_pdf[0][0] < 700*3.5 and any(k == 'vault' for k in p.kinds) for p in lines)


def test_fork_shares_source_contact_without_extending_branch_to_vault(sheets):
    q = (850.6199951171875*3.5, 1022.4600219726562*3.5)
    branches = [p for p in sheets[4, 'TELECOM'].drawable
                if any(math.dist(v, q) < .01 for v in p.pts_pdf)]
    assert len(branches) == 2
    assert {p.layer_ocg[-2:] for p in branches} == {'-D', '-E'}
    for pl in branches:
        i = next(i for i, v in enumerate(pl.pts_pdf) if math.dist(v, q) < .01)
        assert pl.kinds[i] == 'junction'
        _editor((pl.pts_pdf, pl.kinds, pl.fillets))
        assert pl.fillets
        if pl.layer_ocg.endswith('-D'):
            assert i in (0, len(pl.pts_pdf)-1)
            assert all(v[0] >= q[0]-.01 for v in pl.pts_pdf)
            assert any(min(math.dist(g['a'], q), math.dist(g['b'], q)) < .01
                       for g in pl.fillets.values())


@pytest.mark.parametrize('offset,expected', [(0., True), (.3, False)])
def test_source_contact_requires_ink_at_branch_endpoint(offset, expected):
    from recognition_contacts import source_contacts
    # The circle starts tangent to y=0. A neighbouring parallel line is
    # separate geometry and must never attract its endpoint.
    curve = [(40*math.sin(t), 40*(1-math.cos(t)))
             for t in [i*math.pi/80 for i in range(21)]]
    paths = {'branch': [{'stroke': curve}],
             'stem': [{'stroke': [(-20., offset), (60., offset)]}]}
    contacts = source_contacts(paths, lambda paths: [p['stroke'] for p in paths])
    assert bool(contacts['branch']) == expected
    assert bool(contacts['stem']) == expected


def test_reported_loop_has_real_arcs_with_bounded_ink_error(sheets):
    pl = next(p for p in sheets[5, 'TELECOM'].drawable
              if any(math.dist(q, (799.38*3.5, 1088.94*3.5)) < 1. for q in p.pts_pdf))
    fs = [g for g in pl.fillets.values() if 800*3.5 < g['center'][0] < 840*3.5
          and 1090*3.5 < g['center'][1] < 1120*3.5]
    assert len(fs) >= 3
    data = (pl.pts_pdf, pl.kinds, pl.fillets)
    _editor(data)
    # Samples from the actual flattened source, covering both sides and top.
    drawing = trace._drawing(data)
    for q in [(827.70,1131.12), (841.14,1121.94), (846.36,1106.52),
              (837.60,1086.66), (819.24,1079.70), (805.02,1084.02)]:
        assert min(trace._arc_distance((q[0]*3.5, q[1]*3.5), p) for p in drawing)/3.5 <= .13


def test_upper_loop_diagonal_keeps_its_original_endpoint(sheets):
    q = (760.739990234375*3.5, 1133.699951171875*3.5)
    pl = next(p for p in sheets[5, 'TELECOM'].drawable
              if min(math.dist(p.pts_pdf[0], q), math.dist(p.pts_pdf[-1], q)) < .01)
    drawing = trace._drawing((pl.pts_pdf, pl.kinds, pl.fillets))
    top = (799.3800048828125*3.5, 1088.93994140625*3.5)
    for i in range(21):
        sample = tuple(a+(b-a)*i/20 for a,b in zip(q,top))
        assert min(trace._arc_distance(sample, part) for part in drawing)/3.5 <= .13


@pytest.mark.parametrize('start', [(663.06, 1251.96), (699.12, 1209.66)])
def test_lower_loop_and_branch_are_not_discarded_as_leaders(sheets, start):
    import fitz
    with fitz.open(PDF) as doc:
        strokes = [s for p in doc[4].get_drawings()
                   if (p.get('layer') or '').endswith('N-COMM-DUCT-BANK-PL')
                   for s in rec.ink_strokes([p], lambda q: q)]
    source = next(s for s in strokes if math.dist(s[0], start) < .01)
    lines = [p for p in sheets[5, 'TELECOM'].drawable
             if p.layer_ocg.endswith('N-COMM-DUCT-BANK-PL')]
    drawing = [part for p in lines for part in trace._drawing((p.pts_pdf, p.kinds, p.fillets))]
    for a,b in zip(source,source[1:]):
        for i in range(5):
            q = tuple((x+(y-x)*i/4)*3.5 for x,y in zip(a,b))
            assert min(trace._arc_distance(q, part) for part in drawing)/3.5 <= .13


def test_electrical_curve_tracks_variable_radius_ink(sheets):
    # Actual source endpoint on the box outline; search padding must not
    # retract it to y=818.2.
    pl = next(p for p in sheets[5, 'ELECTRICO'].drawable
              if math.dist(p.pts_pdf[0], (911.7*3.5, 817.2*3.5)) < 1.)
    data = (pl.pts_pdf, pl.kinds, pl.fillets)
    _editor(data)
    assert len(pl.fillets) >= 2
    drawing = trace._drawing(data)
    for q in [(911.46,830.04), (911.4,835.74), (911.76,842.4), (912.96,851.88), (915.3,864.06)]:
        assert min(trace._arc_distance((q[0]*3.5, q[1]*3.5), p) for p in drawing)/3.5 <= .13
