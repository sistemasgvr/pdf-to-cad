"""Pure helpers for layers shared by an arrangement of PDF pages."""
from __future__ import annotations

from sheet_layout import DIRECTIONS


def selected_sheets(layout, sources):
    """Resolve global page indices to their source PDF and local page number."""
    result = []
    for slot in ("main", *DIRECTIONS):
        global_page = layout.get(slot) if layout else None
        if global_page is None:
            continue
        for source_index, source in enumerate(sources):
            start = int(source["start"])
            count = int(source["count"])
            if start <= global_page < start + count:
                result.append({"slot": slot, "source": source_index,
                               "page": global_page - start,
                               "global_page": global_page,
                               "source_name": source["name"]})
                break
        else:
            raise ValueError(f"Page {global_page} has no source PDF")
    return result


def aggregate_layers(sheet_rows):
    """Combine same short layer names across the selected pages and PDFs.

    sheet_rows contains (sheet_descriptor, page_layers_result) pairs. Every OCG
    is kept, including layers with zero paths in all selected sheets.
    """
    groups = {}
    for sheet, layers in sheet_rows:
        for layer in layers:
            key = (layer["utility"], layer["short"].casefold())
            group = groups.setdefault(key, {
                "utility": layer["utility"], "short": layer["short"],
                "path_count": 0, "sheets_with_paths": set(),
                "bindings": {},
            })
            count = int(layer.get("path_count") or 0)
            group["path_count"] += count
            if count:
                group["sheets_with_paths"].add(sheet["slot"])
            binding = (sheet["source"], layer["name"])
            group["bindings"][binding] = bool(layer["on"])
    result = list(groups.values())
    result.sort(key=lambda group: (
        group["utility"], 0 if group["path_count"] else 1,
        -group["path_count"], group["short"].casefold()))
    return result


def hidden_from_states(groups, states, initial_hidden):
    """Map grouped check states to per-PDF hidden OCG names.

    State None means mixed/untouched and preserves each PDF's initial state.
    """
    hidden = {int(k): set(v) for k, v in initial_hidden.items()}
    for group, state in zip(groups, states):
        if state is None:
            continue
        for source, name in group["bindings"]:
            names = hidden.setdefault(source, set())
            if state:
                names.discard(name)
            else:
                names.add(name)
    return hidden
