"""DU08 sheet 22: branching source traces and closely spaced structures."""
import math
from pathlib import Path

import pytest
from reconocimiento import recognition as rec
from reconocimiento import recognition_trace as trace
from test_curve_precision import _editor

PDF = Path('C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf')


def test_retraced_branch_preserves_every_source_edge():
    import fitz
    points = [(0, 10), (0, 0), (10, 0), (2, 0), (-2, 4)]
    path = {'items': [('l', fitz.Point(*a), fitz.Point(*b))
                      for a,b in zip(points, points[1:])]}
    strokes = rec.ink_strokes([path], lambda p: p)
    assert strokes == [points[:3], points[2:]]
    assert [edge for s in strokes for edge in zip(s,s[1:])] == list(zip(points,points[1:]))


@pytest.fixture(scope='module', params=[1., 3.5])
def sheet(request):
    if not PDF.exists():
        pytest.skip('DU08 reference PDF unavailable')
    scale = request.param
    result = rec.recognize_page(PDF, 21, utility='ELECTRICO', zoom=scale)
    return scale, result


def test_contacts_preserve_source_ends_and_do_not_extend_stubs(sheet):
    scale, result = sheet
    lines = [p for p in result.drawable if p.layer_ocg.endswith('C-ELEC-3MI-UGND-N')]
    ends = [(x/scale,y/scale) for p in lines for x,y in (p.pts_pdf[0],p.pts_pdf[-1])]
    for expected in [(771.95996,631.1400), (764.700012,647.400024), (778.559997,645.18005)]:
        assert min(math.dist(expected,q) for q in ends) < .01
    assert not any(755<x<757 and abs(y-647.4)<.1 for x,y in ends)
    assert not any(778<x<779 and 632<y<635 for x,y in ends)


def test_both_existing_branch_curves_follow_ink(sheet):
    scale, result = sheet
    lines = [p for p in result.drawable if p.layer_ocg.endswith('C-ELEC-UNGD-E')]
    for p in lines:
        _editor((p.pts_pdf,p.kinds,p.fillets))
    drawing = [part for p in lines for part in trace._drawing((p.pts_pdf,p.kinds,p.fillets))]
    for q in [(742.26,630.42),(744.30,628.08),(746.88,626.46),(749.82,625.56),
              (749.88,634.74),(750.78,631.80),(753.54,628.08),(757.56,625.92),(760.56,625.44)]:
        assert min(trace._arc_distance((q[0]*scale,q[1]*scale),p) for p in drawing)/scale <= .13
    # The previous fitted arc bulged above the horizontal source leg.
    for a,b,arc in drawing:
        if arc and 749<a[0]/scale<768 and 749<b[0]/scale<768 and 624<a[1]/scale<640:
            _,_,c,r,a0,sw = arc
            assert min((c[1]+r*math.sin(a0+sw*i/100))/scale for i in range(101)) >= 625.30
