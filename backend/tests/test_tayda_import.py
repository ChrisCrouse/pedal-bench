from __future__ import annotations

import pytest

from pedal_bench.io.tayda_import import (
    TaydaParseError,
    parse_tayda_csv,
    parse_tayda_json,
    parse_tayda_text,
)


# ---- CSV / whitespace ----------------------------------------------------

def test_csv_with_header() -> None:
    text = """side,diameter,x,y
A,12.2,0,-45.1
A,7.2,-16.5,38.1
B,9.7,-15.2,5.75
"""
    holes = parse_tayda_csv(text)
    assert len(holes) == 3
    assert holes[0].side == "A"
    assert holes[0].diameter_mm == 12.2
    assert holes[0].x_mm == 0
    assert holes[0].y_mm == -45.1
    assert holes[2].side == "B"
    assert all(h.powder_coat_margin for h in holes)


def test_csv_without_header_positional() -> None:
    text = "A,12.2,0,-45.1\nA,7.2,-16.5,38.1"
    holes = parse_tayda_csv(text)
    assert len(holes) == 2
    assert holes[1].x_mm == -16.5


def test_csv_with_label_column() -> None:
    text = """side,diameter,x,y,label
A,7.2,0,0,LEVEL
A,5.0,0,10,LED
"""
    holes = parse_tayda_csv(text)
    assert holes[0].label == "LEVEL"
    assert holes[1].label == "LED"


def test_csv_tab_separated() -> None:
    text = "side\tdiameter\tx\ty\nA\t12.2\t0\t-45.1"
    holes = parse_tayda_csv(text)
    assert len(holes) == 1
    assert holes[0].diameter_mm == 12.2


def test_csv_whitespace_separated_paste() -> None:
    # Simulating a naive copy-paste from the Tayda UI.
    text = """A 12.2 0 -45.1
A 7.2 -16.5 38.1"""
    holes = parse_tayda_csv(text)
    assert len(holes) == 2
    assert holes[0].side == "A"
    assert holes[1].x_mm == -16.5


def test_csv_uppercase_headers() -> None:
    text = """Side,Diameter (mm),X Position (mm),Y Position (mm)
A,12.2,0,-45.1
"""
    holes = parse_tayda_csv(text)
    assert holes[0].side == "A"
    assert holes[0].diameter_mm == 12.2


def test_csv_reordered_columns() -> None:
    text = """y,x,diameter,side
-45.1,0,12.2,A
38.1,-16.5,7.2,A
"""
    holes = parse_tayda_csv(text)
    assert holes[0].x_mm == 0
    assert holes[1].x_mm == -16.5


def test_csv_invalid_side_rejected() -> None:
    text = "side,diameter,x,y\nZ,10,0,0"
    with pytest.raises(TaydaParseError):
        parse_tayda_csv(text)


def test_csv_empty_rejected() -> None:
    with pytest.raises(TaydaParseError):
        parse_tayda_csv("")
    with pytest.raises(TaydaParseError):
        parse_tayda_csv("   \n   \n")


# ---- JSON ---------------------------------------------------------------

def test_json_flat_list_short_keys() -> None:
    text = '[{"side":"A","diameter":12.2,"x":0,"y":-45.1}]'
    holes = parse_tayda_json(text)
    assert len(holes) == 1
    assert holes[0].side == "A"
    assert holes[0].diameter_mm == 12.2


def test_json_flat_list_verbose_keys() -> None:
    text = """[
        {"Side":"A","Diameter (mm)":12.2,"X Position (mm)":0,"Y Position (mm)":-45.1},
        {"Side":"B","Diameter (mm)":9.7,"X Position (mm)":-15.2,"Y Position (mm)":5.75}
    ]"""
    holes = parse_tayda_json(text)
    assert len(holes) == 2
    assert holes[1].side == "B"


def test_json_wrapped_in_holes_key() -> None:
    text = '{"holes":[{"side":"A","diameter":12.2,"x":0,"y":-45.1}]}'
    holes = parse_tayda_json(text)
    assert len(holes) == 1


def test_json_missing_field_rejected() -> None:
    with pytest.raises(TaydaParseError):
        parse_tayda_json('[{"side":"A","x":0,"y":0}]')


# ---- auto-detect --------------------------------------------------------

def test_auto_detect_json() -> None:
    text = '[{"side":"A","diameter":12.2,"x":0,"y":-45.1}]'
    holes = parse_tayda_text(text)
    assert len(holes) == 1


def test_auto_detect_csv() -> None:
    holes = parse_tayda_text("side,diameter,x,y\nA,12.2,0,-45.1")
    assert len(holes) == 1


# ---- Tayda screenshot fixture -------------------------------------------

def test_tayda_screenshot_9_hole_1590b_fixture() -> None:
    """Reproduce the 9-hole 1590B template visible in the Tayda Box Tool screenshot."""
    text = """side,diameter,x,y
A,12.2,0,-45.1
A,7.2,-16.5,38.1
A,4.4,0,25.4
A,7.2,-16.5,12.7
A,7.2,16.5,12.7
A,7.2,16.5,38.1
B,9.7,-15.2,5.75
B,9.7,15.2,5.75
B,8.1,0,-4.4
"""
    holes = parse_tayda_text(text)
    assert len(holes) == 9
    face_a = [h for h in holes if h.side == "A"]
    face_b = [h for h in holes if h.side == "B"]
    assert len(face_a) == 6   # 4 pots + LED + footswitch on face A in that layout
    assert len(face_b) == 3   # input + output + DC jacks on top side
    # The footswitch is the largest hole.
    assert max(h.diameter_mm for h in holes) == 12.2
