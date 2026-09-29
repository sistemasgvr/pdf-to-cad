import copy
import math

import pytest

import recognition as rec
import recognition_text_gaps as gaps
import recognition_trace as trace
from test_curve_precision import _editor, sheets  # shared real-PDF fixture


def circle(a0, a1, center=(0.,0.), radius=30.):
    a0,a1 = math.radians(a0),math.radians(a1)
    point = lambda t:(center[0]+radius*math.cos(t),center[1]+radius*math.sin(t))
    a,b = point(a0),point(a1)
    P,K,F = trace._encode([(a,b,(a,b,center,radius,a0,a1-a0))],'end','end')
    return rec.RecognizedPolyline('line','TELECOM',P,'tele_ungd',K,fillets=F)


def tangent(arc, at_end=False):
    _,_,c,r,a0,sw = arc
    t = a0+(sw if at_end else 0.)
    sign = 1 if sw>0 else -1
    return (-math.sin(t)*sign,math.cos(t)*sign)


def test_biarc_has_exact_endpoints_and_continuous_tangents():
    a,b = (0.,0.),(25.,-13.)
    ta,tb = (1.,0.),(.5,-math.sqrt(.75))
    parts = gaps.biarc(a,b,ta,tb)
    assert parts and parts[0][0] == a and parts[-1][1] == b
    assert parts[0][1] == parts[1][0]
    for u,v in [(tangent(parts[0][2]),ta),(tangent(parts[-1][2],True),tb),
                (tangent(parts[0][2],True),tangent(parts[1][2]))]:
        assert math.dist(u,v) < 1e-10
    _editor(trace._encode(parts,'junction','junction'))


@pytest.mark.parametrize('blocked',[None,'no_text','remote_text','cut','layer','status','different_circle'])
def test_curve_gap_requires_text_and_compatible_geometry(blocked):
    a,b = circle(0,60),circle(120,180)
    glyphs = [(0.,30.,7.)]
    if blocked == 'no_text': glyphs=[]
    if blocked == 'remote_text': glyphs=[(0.,60.,7.)]
    if blocked == 'cut': a.kinds[-1]='cut'
    if blocked == 'layer': b.layer_ocg='other'
    if blocked == 'status': b.abandoned=True
    if blocked == 'different_circle': b=circle(120,180,center=(10.,0.))
    original = copy.deepcopy([a,b])
    gaps.connect_text_gaps([a,b],glyphs,40.)
    if blocked:
        assert [a,b] == original
    else:
        assert a.pts_pdf[-1] == b.pts_pdf[0]
        assert a.kinds[-1] == b.kinds[0] == 'junction'
        assert a.pts_pdf[:len(original[0].pts_pdf)] == original[0].pts_pdf
        assert b.pts_pdf == original[1].pts_pdf
        for pl in (a,b): _editor((pl.pts_pdf,pl.kinds,pl.fillets))


def test_branch_joins_straight_leg_without_moving_existing_vertices():
    arc = circle(150,90,center=(20.,0.),radius=20.)
    line = rec.RecognizedPolyline('line','TELECOM',[(0.,-40.),(0.,40.)],
                                  'tele_ungd',['end','end'])
    original = copy.deepcopy(arc)
    gaps.connect_text_gaps([arc,line],[(1.,5.,5.)],30.)
    assert math.dist(arc.pts_pdf[0],(0.,0.)) < 1e-8
    assert arc.pts_pdf[0] in line.pts_pdf
    assert line.pts_pdf[0] == (0.,-40.) and line.pts_pdf[-1] == (0.,40.)
    assert arc.pts_pdf[-len(original.pts_pdf):] == original.pts_pdf
    _editor((arc.pts_pdf,arc.kinds,arc.fillets))


@pytest.mark.parametrize('variant',['polylines_joined','polylines_raw'])
def test_reported_text_gaps_are_connected_in_pdf(sheets, variant):
    lines = [p for p in getattr(sheets[5,'TELECOM'],variant)
             if p.layer_ocg.endswith('N-COMM-DUCT-BANK-PL')]
    lower = (663.0599975585938*3.5,1251.9599609375*3.5)
    # The bottom arc has a real shared endpoint, not two visually close ends.
    touching = [p for p in lines if lower in p.pts_pdf]
    assert len(touching) == 2
    assert all(p.kinds[p.pts_pdf.index(lower)] == 'junction' for p in touching)
    # The side branch shares a node on the vertical leg; both text gaps use
    # circular bridges and remain representable by the actual editor.
    branch = next(p for p in lines if any(g.get('text_gap') and
                  1190*3.5 < g['center'][1] < 1210*3.5 for g in p.fillets.values()))
    q = branch.pts_pdf[0]
    assert branch.kinds[0] == 'junction'
    assert sum(q in p.pts_pdf for p in lines) == 2
    for p in touching+[branch]:
        _editor((p.pts_pdf,p.kinds,p.fillets))
