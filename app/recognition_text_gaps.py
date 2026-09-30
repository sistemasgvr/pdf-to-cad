"""Restore curved linetype gaps supported by nearby text and measured tangents.

Runs keep their original ink. Only a free curved endpoint may be continued,
either into a compatible curve or tangentially into an existing straight leg,
or straight into another free end next to a bend when both legs point along
the gap (the middle of an «S» curve under the line's own letters).
The bridge is a tangent biarc, encoded with the same circles as the editor.
"""
import math

from recognition_arcs import _unit
from recognition_trace import _encode

STRAIGHT_GAP_COS = math.cos(math.radians(6.))   # both legs within 6° of the straight gap


def _dot(a, b):
    return a[0]*b[0]+a[1]*b[1]


def _arc(a, b, tangent):
    v = (b[0]-a[0], b[1]-a[1])
    normal = (-tangent[1], tangent[0])
    den = 2*_dot(v, normal)
    if abs(den) < 1e-9:
        return None
    h = _dot(v, v)/den
    c = (a[0]+normal[0]*h, a[1]+normal[1]*h)
    a0 = math.atan2(a[1]-c[1], a[0]-c[0])
    sw = (math.atan2(b[1]-c[1], b[0]-c[0])-a0+math.pi) % (2*math.pi)-math.pi
    if sw*h <= 0 or not math.radians(2.1) < abs(sw) < math.radians(120):
        return None
    return (a, b, (a, b, c, abs(h), a0, sw))


def biarc(a, b, ta, tb):
    """Two circular arcs with fixed endpoints and fixed forward tangents."""
    v = (b[0]-a[0], b[1]-a[1])
    aa = 2*(1-_dot(ta, tb))
    bb = 2*_dot(v, (ta[0]+tb[0], ta[1]+tb[1]))
    if bb <= 1e-9:
        return None
    # Stable positive root of aa*d*d + bb*d - |v|**2 = 0.
    d = 2*_dot(v, v)/(bb+math.sqrt(bb*bb+4*aa*_dot(v, v)))
    m = ((a[0]+b[0]+d*(ta[0]-tb[0]))/2,
         (a[1]+b[1]+d*(ta[1]-tb[1]))/2)
    first = _arc(a, m, ta)
    back = _arc(b, m, (-tb[0], -tb[1]))
    if first is None or back is None:
        return None
    _, _, c, r, a0, sw = back[2]
    second = (m, b, (m, b, c, r, a0+sw, -sw))
    if first[2][5]*second[2][5] <= 0:
        return None
    return [first, second]


def _reverse(parts):
    out = []
    for a,b,arc in reversed(parts):
        if arc is None:
            out.append((b,a,None))
            continue
        _,_,c,r,a0,sw = arc
        out.append((b,a,(b,a,c,r,a0+sw,-sw)))
    return out


def _ends(pl, scale):
    for side, i, j, name in ((0, 0, 1, 'a'), (1, -1, len(pl.pts_pdf)-2, 'b')):
        if pl.kinds[i] != 'end' or j not in pl.fillets:
            continue
        g = pl.fillets[j]
        p, c = pl.pts_pdf[i], g['center']
        if g.get('loose') or math.dist(p,g[name]) > .2*scale:
            continue
        a0 = math.atan2(g['a'][1]-c[1], g['a'][0]-c[0])
        sw = (math.atan2(g['b'][1]-c[1], g['b'][0]-c[0])-a0+math.pi) % (2*math.pi)-math.pi
        u = _unit(-(p[1]-c[1]), p[0]-c[0])
        sign = (1 if sw > 0 else -1) * (-1 if side == 0 else 1)
        yield side, p, (u[0]*sign,u[1]*sign), c, g['r_px']


def _bend_ends(pl):
    """Free ends next to a bend (fillet corner as neighbour vertex), with the
    outward direction of their last leg (at a fillet it is the arc tangent or
    the straight leg before the arc)."""
    P, n = pl.pts_pdf, len(pl.pts_pdf)
    if n < 3:
        return
    if pl.kinds[0] == 'end' and 1 in pl.fillets:
        yield 0, P[0], _unit(P[0][0]-P[1][0], P[0][1]-P[1][1])
    if pl.kinds[-1] == 'end' and n-2 in pl.fillets:
        yield 1, P[-1], _unit(P[-1][0]-P[-2][0], P[-1][1]-P[-2][1])


def _text_in_gap(parts, glyphs, scale):
    a,b = parts[0][0],parts[-1][1]
    v = (b[0]-a[0], b[1]-a[1])
    length2 = _dot(v,v)
    if length2 < scale*scale:
        return False
    from recognition_trace import _arc_distance
    return any(.05 < _dot((x-a[0], y-a[1]),v)/length2 < .95
               and min(_arc_distance((x,y),p) for p in parts) <= size/2+scale
               for x,y,size in glyphs)


def _extend(pl, side, parts):
    # parts travel OUT from this endpoint. For a starting endpoint prepend
    # the reversed bridge. Existing vertices and fillet geometry stay fixed.
    if side == 0:
        P,K,F = _encode(_reverse(parts), 'junction', 'bend')
        for g in F.values():
            g['text_gap'] = True
        shift = len(P)-1
        pl.pts_pdf = P+pl.pts_pdf[1:]
        pl.kinds = K+pl.kinds[1:]
        pl.fillets = {**F, **{i+shift:g for i,g in pl.fillets.items()}}
    else:
        P,K,F = _encode(parts, 'bend', 'junction')
        for g in F.values():
            g['text_gap'] = True
        shift = len(pl.pts_pdf)-1
        pl.kinds[-1] = 'bend'
        pl.pts_pdf += P[1:]
        pl.kinds += K[1:]
        pl.fillets.update({i+shift:g for i,g in F.items()})


def connect_text_gaps(lines, glyphs, reach, scale=1.):
    """Connect only text-obscured continuations within one layer and status."""
    if not glyphs:
        return
    reach = min(reach, 60*scale)
    # Each successful connection consumes at least one free curved endpoint.
    for _ in range(2*len(lines)):
        ends = [(i,*e) for i,pl in enumerate(lines) for e in _ends(pl,scale)]
        choices = []
        for n,(i,side,p,t,c,r) in enumerate(ends):
            for j,other,q,u,cc,rr in ends[n+1:]:
                if (i == j or lines[i].abandoned != lines[j].abandoned
                        or lines[i].layer_ocg != lines[j].layer_ocg):
                    continue
                if (math.dist(c,cc) > max(scale,.05*min(r,rr))
                        or abs(r-rr) > .05*max(r,rr)):
                    continue
                d = math.dist(p,q)
                v = _unit(q[0]-p[0],q[1]-p[1])
                if not scale < d <= reach or _dot(t,v) < .5 or _dot(u,v) > -.5:
                    continue
                parts = biarc(p,q,t,(-u[0],-u[1]))
                if (parts and all(.5*min(r,rr) <= a[2][3] <= 2*max(r,rr) for a in parts)
                        and _text_in_gap(parts,glyphs,scale)):
                    choices.append((d,i,side,j,other,None,parts))
            # A curved branch can meet the INTERIOR of a straight source leg.
            for j,pl in enumerate(lines):
                if (i == j or lines[i].abandoned != pl.abandoned
                        or lines[i].layer_ocg != pl.layer_ocg):
                    continue
                for k in range(len(pl.pts_pdf)-1):
                    a = pl.fillets[k]['b'] if k in pl.fillets else pl.pts_pdf[k]
                    b = pl.fillets[k+1]['a'] if k+1 in pl.fillets else pl.pts_pdf[k+1]
                    length = math.dist(a,b)
                    if length < 4*scale:
                        continue
                    u = _unit(b[0]-a[0],b[1]-a[1])
                    station = _dot((c[0]-a[0],c[1]-a[1]),u)
                    if not 2*scale < station < length-2*scale:
                        continue
                    q = (a[0]+station*u[0],a[1]+station*u[1])
                    if abs(math.dist(c,q)-r) > max(.5*scale,.05*r):
                        continue
                    d = math.dist(p,q)
                    v = _unit(q[0]-p[0],q[1]-p[1])
                    if not scale < d <= reach or _dot(t,v) < .5:
                        continue
                    if _dot(u,v) < 0:
                        u = (-u[0],-u[1])
                    parts = biarc(p,q,t,u)
                    if (parts and all(.5*r <= a[2][3] <= 2*r for a in parts)
                            and _text_in_gap(parts,glyphs,scale)):
                        choices.append((d,i,side,j,None,k,parts))
        # The straight middle of a reverse («S») curve hidden by the line's
        # own text (DU10 h.10 «—SC—», 2026-09-30): two free ends next to a bend
        # whose legs point along the gap. No point is added: the two existing
        # ends are joined straight.
        free = [(i,*e) for i,pl in enumerate(lines) for e in _bend_ends(pl)]
        for n,(i,side,p,t) in enumerate(free):
            for j,other,q,u in free[n+1:]:
                if (i == j or lines[i].abandoned != lines[j].abandoned
                        or lines[i].layer_ocg != lines[j].layer_ocg):
                    continue
                d = math.dist(p,q)
                v = _unit(q[0]-p[0],q[1]-p[1])
                if (not scale < d <= reach or _dot(t,v) < STRAIGHT_GAP_COS
                        or -_dot(u,v) < STRAIGHT_GAP_COS):
                    continue
                parts = [(p,q,None)]
                if _text_in_gap(parts,glyphs,scale):
                    choices.append((d,i,side,j,other,None,parts))
        if not choices:
            break
        _,i,side,j,other,k,parts = min(choices,key=lambda c:c[0])
        _extend(lines[i],side,parts)
        target = lines[j]
        if other is not None:
            target.kinds[0 if other == 0 else -1] = 'junction'
        else:
            target.pts_pdf.insert(k+1,parts[-1][1])
            target.kinds.insert(k+1,'junction')
            target.fillets = {idx+(idx>k):g for idx,g in target.fillets.items()}
