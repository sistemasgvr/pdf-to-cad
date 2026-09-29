"""Exact source-ink contacts between layers of the same utility.

A curved branch whose real endpoint is on another layer's straight ink ends
there. It must not be extended backwards to a nearby vault. Layer/status
identities are preserved; only the already drawn contact is shared.
"""
import math

from recognition_arcs import _SegGrid, _seg_dist, _unit, arc_pieces


def source_contacts(by_layer, read_strokes):
    strokes = {layer: read_strokes(paths) for layer, paths in by_layer.items()}
    grid = _SegGrid(12.)
    for layer, chains in strokes.items():
        for si, chain in enumerate(chains):
            for a, b in zip(chain, chain[1:]):
                grid.add((layer, si, a, b), a, b)
    contacts = {layer: [] for layer in by_layer}
    for layer, chains in strokes.items():
        cuts = [q for p in by_layer[layer] for q in p.get('cut_pts', ())]
        for si, st in enumerate(chains):
            if len(st) < 4:
                continue
            pieces, _ = arc_pieces([st])
            for pc in pieces:
                if len(pc.pts) < 4 or pc.r < 5.:
                    continue
                for q in (st[0], st[-1]):
                    if q not in (pc.pts[0], pc.pts[-1]) or any(math.dist(q, c) < .5 for c in cuts):
                        continue
                    nearby = set(grid.near(q))
                    # Another own-layer stroke continues here: this is a dash
                    # seam, not a branch endpoint.
                    if any(lay == layer and sj != si and _seg_dist(q, a, b) <= .15
                           for lay, sj, a, b in nearby):
                        continue
                    tangent = _unit(-(q[1]-pc.cy), q[0]-pc.cx)
                    matches = []
                    for lay, sj, a, b in nearby:
                        length = math.dist(a, b)
                        if lay == layer or length < 8.:
                            continue
                        u = _unit(b[0]-a[0], b[1]-a[1])
                        t = (q[0]-a[0])*u[0] + (q[1]-a[1])*u[1]
                        distance = _seg_dist(q, a, b)
                        if (1. < t < length-1. and distance <= .10
                                and abs(u[0]*tangent[0]+u[1]*tangent[1]) >= math.cos(math.radians(10))):
                            matches.append((distance, lay, u))
                    if matches:
                        _, other, u = min(matches)
                        contact = (tuple(q), u)
                        if contact not in contacts[layer]:
                            contacts[layer].append(contact)
                        if contact not in contacts[other]:
                            contacts[other].append(contact)
    return contacts


def insert_contacts(polylines, contacts, make_polyline):
    """Insert supported contacts on the receiving route before fitting curves."""
    out = []
    for pl in polylines:
        pts, kinds = list(pl.pts), list(pl.kinds)
        for q, _u in contacts:
            nearest = min(range(len(pts)), key=lambda i: math.dist(pts[i], q))
            if math.dist(pts[nearest], q) <= .15:
                if kinds[nearest] in ('end', 'bend', 'corner', 'curve', 'junction'):
                    pts[nearest], kinds[nearest] = q, 'junction'
                continue
            candidates = []
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                length = math.dist(a, b)
                u = _unit(b[0]-a[0], b[1]-a[1])
                t = (q[0]-a[0])*u[0] + (q[1]-a[1])*u[1]
                d = _seg_dist(q, a, b)
                if .15 < t < length-.15 and d <= .5:
                    candidates.append((d, i))
            if candidates:
                _, i = min(candidates)
                pts.insert(i+1, q); kinds.insert(i+1, 'junction')
        out.append(make_polyline(pts, kinds))
    return out
