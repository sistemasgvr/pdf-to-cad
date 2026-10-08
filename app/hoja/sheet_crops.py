"""Non-destructive plan windows for arranged PDF sheets.

Each slot stores a rectangle in normalized *visible page* coordinates. A missing
slot means the full page. PDF pages and OCG layers remain untouched.
"""
from __future__ import annotations

import fitz


def normalize(crops, layout=None):
    out = {}
    for slot, values in (crops or {}).items():
        if layout is not None and layout.get(slot) is None:
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in values)
        except (TypeError, ValueError):
            continue
        x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
        y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
        # Keep narrow plan strips; PDF point size is checked in the picker.
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            continue
        if x0 <= 1e-9 and y0 <= 1e-9 and x1 >= 1 - 1e-9 and y1 >= 1 - 1e-9:
            continue
        out[slot] = [x0, y0, x1, y1]
    return out


def move_rect(rect, dx, dy, bounds):
    """Translate without resizing, rotating, or leaving the PDF page."""
    x0, y0, x1, y1 = rect
    left, top, right, bottom = bounds
    dx = max(left - x0, min(right - x1, dx))
    dy = max(top - y0, min(bottom - y1, dy))
    return x0 + dx, y0 + dy, x1 + dx, y1 + dy


def resize_corner(rect, corner, x, y, bounds, minimum=2.0):
    """Move one corner. The opposite corner stays fixed and axes never flip."""
    x0, y0, x1, y1 = rect
    left, top, right, bottom = bounds
    if corner == "tl":
        x0 = max(left, min(x1 - minimum, x))
        y0 = max(top, min(y1 - minimum, y))
    elif corner == "tr":
        x1 = min(right, max(x0 + minimum, x))
        y0 = max(top, min(y1 - minimum, y))
    elif corner == "bl":
        x0 = max(left, min(x1 - minimum, x))
        y1 = min(bottom, max(y0 + minimum, y))
    elif corner == "br":
        x1 = min(right, max(x0 + minimum, x))
        y1 = min(bottom, max(y0 + minimum, y))
    else:
        raise ValueError(f"Unknown corner: {corner}")
    return x0, y0, x1, y1


def resize_side(rect, side, position, bounds, minimum=2.0):
    """Move just one edge; the opposite edge and the other axis stay fixed."""
    x0, y0, x1, y1 = rect
    left, top, right, bottom = bounds
    if side == "left":
        x0 = max(left, min(x1 - minimum, position))
    elif side == "right":
        x1 = min(right, max(x0 + minimum, position))
    elif side == "top":
        y0 = max(top, min(y1 - minimum, position))
    elif side == "bottom":
        y1 = min(bottom, max(y0 + minimum, position))
    else:
        raise ValueError(f"Unknown side: {side}")
    return x0, y0, x1, y1


def page_rect(page, crop=None):
    """Return a rectangle suitable for page.get_pixmap(clip=...)."""
    full = page.rect
    if crop is None:
        return fitz.Rect(full)
    x0, y0, x1, y1 = crop
    return fitz.Rect(full.x0 + x0 * full.width,
                     full.y0 + y0 * full.height,
                     full.x0 + x1 * full.width,
                     full.y0 + y1 * full.height)


def drawing_polygon(page, rect):
    """Convert a visual page rectangle to get_drawings() coordinates."""
    points = [fitz.Point(rect.x0, rect.y0), fitz.Point(rect.x1, rect.y0),
              fitz.Point(rect.x1, rect.y1), fitz.Point(rect.x0, rect.y1)]
    return [(p.x, p.y) for point in points
            for p in [point * page.derotation_matrix]]
