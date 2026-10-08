"""Evaluate PDF cubic curves; control handles are not points on the ink."""
from __future__ import annotations

import math


def flatten_cubic(points, tolerance=0.025):
    """Adaptive de Casteljau subdivision with a control-hull error bound.

    Distance is to the finite chord, so collinear loops/backtracking cannot
    disappear. Endpoints are preserved exactly. Coordinates are PDF points.
    """
    points = [tuple(p) for p in points]

    def distance(p, a, b):
        vx, vy = b[0]-a[0], b[1]-a[1]
        length2 = vx*vx + vy*vy
        t = 0. if length2 == 0 else max(0., min(1., ((p[0]-a[0])*vx+(p[1]-a[1])*vy)/length2))
        return math.hypot(p[0]-a[0]-t*vx, p[1]-a[1]-t*vy)

    def mid(a, b):
        return ((a[0]+b[0])/2, (a[1]+b[1])/2)

    out = [points[0]]

    def split(a, b, c, d, depth):
        if depth >= 24 or max(distance(b, a, d), distance(c, a, d)) <= tolerance:
            out.append(d)
            return
        ab, bc, cd = mid(a, b), mid(b, c), mid(c, d)
        abc, bcd = mid(ab, bc), mid(bc, cd)
        m = mid(abc, bcd)
        split(a, ab, abc, m, depth+1)
        split(m, bcd, cd, d, depth+1)

    split(*points, 0)
    return out
