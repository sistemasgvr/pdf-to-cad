"""Grouped controls keep independent OCG names for each source PDF."""
from organized_layers import selected_sheets, aggregate_layers, hidden_from_states


def test_selected_sheets_resolve_sources_and_positions():
    sources = [{"name": "A.pdf", "start": 0, "count": 19},
               {"name": "B.pdf", "start": 19, "count": 2}]
    sheets = selected_sheets({"main": 13, "left": 12, "right": 20}, sources)
    assert [(s["slot"], s["source"], s["page"]) for s in sheets] == [
        ("main", 0, 13), ("left", 0, 12), ("right", 1, 1)]


def test_aggregate_and_toggle_across_pdfs():
    a = {"slot": "main", "source": 0}
    b = {"slot": "right", "source": 1}
    layers = aggregate_layers([
        (a, [{"utility": "ELECTRICO", "short": "C-ELEC-UNGD-E",
              "name": "XREF|C-ELEC-UNGD-E", "path_count": 8, "on": True},
             {"utility": "OTRAS", "short": "C-ROAD-CNTR",
              "name": "C-ROAD-CNTR", "path_count": 2, "on": True}]),
        (b, [{"utility": "ELECTRICO", "short": "C-ELEC-UNGD-E",
              "name": "C-ELEC-UNGD-E", "path_count": 5, "on": True}]),
    ])
    electric = next(g for g in layers if g["utility"] == "ELECTRICO")
    assert electric["path_count"] == 13
    assert electric["sheets_with_paths"] == {"main", "right"}
    assert len(electric["bindings"]) == 2
    hidden = hidden_from_states([electric], [False], {0: set(), 1: set()})
    assert hidden == {0: {"XREF|C-ELEC-UNGD-E"}, 1: {"C-ELEC-UNGD-E"}}


def test_mixed_state_preserves_each_pdf():
    group = {"bindings": {(0, "A"): True, (1, "B"): False}}
    assert hidden_from_states([group], [None], {0: set(), 1: {"B"}}) == {
        0: set(), 1: {"B"}}


def test_same_ocg_on_two_sheets_counts_both_but_toggles_once():
    row = {"utility": "ELECTRICO", "short": "C-ELEC-UNGD-E",
           "name": "C-ELEC-UNGD-E", "path_count": 4, "on": True}
    groups = aggregate_layers([
        ({"slot": "main", "source": 0}, [row]),
        ({"slot": "left", "source": 0}, [row]),
    ])
    assert groups[0]["path_count"] == 8
    assert groups[0]["sheets_with_paths"] == {"main", "left"}
    assert len(groups[0]["bindings"]) == 1
