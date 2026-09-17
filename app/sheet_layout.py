"""Page arrangement for a plotted PDF. Indices are zero based.

This records adjacency only; it does not claim that page coordinates are aligned.
"""

DIRECTIONS = ("top", "left", "right", "bottom")
SLOTS = ("main", *DIRECTIONS)


def normalize(layout, page_count, default_main=0):
    """Return a valid, unique arrangement for the current document."""
    page_count = max(0, int(page_count))
    if not page_count:
        return {"main": None, **{key: None for key in DIRECTIONS}}
    source = layout if isinstance(layout, dict) else {}
    main = source.get("main", default_main)
    if not isinstance(main, int) or isinstance(main, bool) or not 0 <= main < page_count:
        main = max(0, min(int(default_main), page_count - 1))
    result = {"main": main}
    used = {main}
    for key in DIRECTIONS:
        page = source.get(key)
        if isinstance(page, int) and not isinstance(page, bool) and 0 <= page < page_count and page not in used:
            result[key] = page
            used.add(page)
        else:
            result[key] = None
    return result


def normalize_rotations(rotations, layout):
    """Keep quarter-turns only for occupied positions."""
    source = rotations if isinstance(rotations, dict) else {}
    result = {}
    for key in SLOTS:
        value = source.get(key, 0)
        result[key] = (value % 360 if isinstance(value, int) and not isinstance(value, bool)
                       and value % 90 == 0 and layout.get(key) is not None else 0)
    return result
