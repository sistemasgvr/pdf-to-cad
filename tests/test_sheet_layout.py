"""The organizer keeps one valid PDF page in each position."""
from sheet_layout import normalize, normalize_rotations


def test_normalize_prevents_duplicates_and_out_of_range_pages():
    layout = {"main": 13, "left": 12, "right": 14,
              "top": 13, "bottom": 99}
    assert normalize(layout, 19) == {
        "main": 13, "top": None, "left": 12,
        "right": 14, "bottom": None}


def test_old_project_defaults_to_first_page():
    assert normalize(None, 19)["main"] == 0
    assert normalize(None, 0)["main"] is None


def test_external_page_can_be_adjacent_without_reusing_a_page():
    layout = {"main": 13, "left": 12, "right": 20, "bottom": 20}
    result = normalize(layout, 21)
    assert result["right"] == 20
    assert result["bottom"] is None


def test_rotations_are_quarter_turns_for_occupied_slots():
    layout = normalize({"main": 13, "left": 12}, 19)
    assert normalize_rotations({"main": -90, "left": 180, "right": 90,
                                "top": 45}, layout) == {
        "main": 270, "top": 0, "left": 180, "right": 0, "bottom": 0}
