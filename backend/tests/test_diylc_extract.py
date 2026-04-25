"""DIYLC .diy parser — realistic fixtures based on rangemaster.diy structure."""

from __future__ import annotations

import pytest

from pedal_bench.io.diylc_extract import parse_diylc


# Compact v4-format DIYLC file modelled after the published rangemaster.diy
# (XStream-serialized XML, short-alias namespace).
RANGEMASTER_LIKE = b"""<?xml version="1.0" encoding="UTF-8" ?>
<project>
  <fileVersion><major>4</major><minor>30</minor><build>0</build></fileVersion>
  <title>Rangemaster Treble Booster</title>
  <author>Test</author>
  <width value="8.0" unit="cm"/>
  <height value="8.0" unit="cm"/>
  <components>
    <diylc.passive.Resistor>
      <name>R1</name>
      <points><point x="1.0" y="1.3"/><point x="1.0" y="0.9"/></points>
      <value value="68.0" unit="K"/>
      <power>HALF</power>
    </diylc.passive.Resistor>
    <diylc.passive.Resistor>
      <name>R2</name>
      <value value="470.0" unit="K"/>
    </diylc.passive.Resistor>
    <diylc.passive.RadialFilmCapacitor>
      <name>C1</name>
      <value value="4.7" unit="nF"/>
      <voltage>_63V</voltage>
    </diylc.passive.RadialFilmCapacitor>
    <diylc.passive.RadialElectrolytic>
      <name>C2</name>
      <value value="10.0" unit="uF"/>
      <voltage>_25V</voltage>
    </diylc.passive.RadialElectrolytic>
    <diylc.semiconductors.TransistorTO92>
      <name>Q1</name>
      <orientation>_270</orientation>
    </diylc.semiconductors.TransistorTO92>
    <diylc.semiconductors.DiodePlastic>
      <name>D1</name>
    </diylc.semiconductors.DiodePlastic>
    <diylc.passive.PotentiometerPanel>
      <name>VR1</name>
      <resistance value="100.0" unit="K"/>
      <taper>LOG</taper>
    </diylc.passive.PotentiometerPanel>
    <diylc.boards.PerfBoard>
      <name>Board</name>
    </diylc.boards.PerfBoard>
    <diylc.connectivity.HookupWire>
      <name>W1</name>
    </diylc.connectivity.HookupWire>
    <diylc.misc.Label>
      <name>L1</name>
    </diylc.misc.Label>
  </components>
</project>"""


def test_parse_returns_title():
    r = parse_diylc(RANGEMASTER_LIKE)
    assert r.title == "Rangemaster Treble Booster"


def test_parse_extracts_resistors_with_values():
    r = parse_diylc(RANGEMASTER_LIKE)
    by_loc = {b.location: b for b in r.bom}
    assert by_loc["R1"].value == "68K"
    assert by_loc["R1"].type == "Resistor"
    assert by_loc["R2"].value == "470K"


def test_parse_extracts_caps_distinguishing_film_vs_electrolytic():
    r = parse_diylc(RANGEMASTER_LIKE)
    by_loc = {b.location: b for b in r.bom}
    assert by_loc["C1"].value == "4.7nF"
    assert "Film" in by_loc["C1"].type
    assert by_loc["C2"].value == "10uF"
    assert "Electrolytic" in by_loc["C2"].type
    # Electrolytic should be flagged polarity-sensitive.
    assert by_loc["C2"].polarity_sensitive is True


def test_parse_extracts_transistor_diode_pot():
    r = parse_diylc(RANGEMASTER_LIKE)
    by_loc = {b.location: b for b in r.bom}
    assert by_loc["Q1"].type == "Transistor"
    assert by_loc["Q1"].polarity_sensitive is True
    assert by_loc["D1"].type == "Diode"
    assert by_loc["D1"].polarity_sensitive is True
    # Pot includes resistance and taper.
    pot = by_loc["VR1"]
    assert "100K" in pot.value
    assert "LOG" in pot.value


def test_parse_skips_non_bom_components():
    r = parse_diylc(RANGEMASTER_LIKE)
    locs = {b.location for b in r.bom}
    # Boards, hookup wires, labels should NOT appear in BOM.
    assert "Board" not in locs
    assert "W1" not in locs
    assert "L1" not in locs
    # We should have exactly 7 BOM rows: R1, R2, C1, C2, Q1, D1, VR1.
    assert len(r.bom) == 7
    assert r.skipped_count == 3


def test_parse_handles_legacy_v3_root():
    legacy = b"""<?xml version="1.0" encoding="UTF-8" ?>
<org.diylc.core.Project>
  <title>Old Build</title>
  <components>
    <org.diylc.components.passive.ResistorSymbol>
      <name>R1</name>
      <value value="10.0" unit="K"/>
    </org.diylc.components.passive.ResistorSymbol>
    <org.diylc.components.semiconductors.ICSymbol>
      <name>IC1</name>
    </org.diylc.components.semiconductors.ICSymbol>
  </components>
</org.diylc.core.Project>"""
    r = parse_diylc(legacy)
    assert r.title == "Old Build"
    by_loc = {b.location: b for b in r.bom}
    assert by_loc["R1"].value == "10K"
    assert by_loc["IC1"].type.startswith("IC")


def test_parse_rejects_non_diylc_xml():
    with pytest.raises(ValueError, match="Unexpected root"):
        parse_diylc(b"<?xml version='1.0'?><whatever><a/></whatever>")


def test_parse_rejects_bad_xml():
    with pytest.raises(ValueError, match="Not valid XML"):
        parse_diylc(b"not xml at all <<<")


def test_parse_dedupes_and_sorts_by_refdes():
    """Two component drops with the same refdes merge into one BOM row."""
    xml = b"""<?xml version="1.0" encoding="UTF-8" ?>
<project>
  <components>
    <diylc.passive.Resistor><name>R10</name><value value="1.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R2</name><value value="2.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R10</name><value value="1.0" unit="K"/></diylc.passive.Resistor>
  </components>
</project>"""
    r = parse_diylc(xml)
    # Two unique refdes, R2 first (sorted by number).
    assert [b.location for b in r.bom] == ["R2", "R10"]
    by_loc = {b.location: b for b in r.bom}
    assert by_loc["R10"].quantity == 2  # merged
    assert by_loc["R2"].quantity == 1


def test_parse_groups_by_value_when_refdes_are_generic():
    """RobRobinette-style files reuse 'R1' as a generic resistor name. Parser
    should detect that and group by (kind, value) instead, synthesizing real
    refdes."""
    xml = b"""<?xml version="1.0" encoding="UTF-8" ?>
<project>
  <title>Princeton Reverb</title>
  <components>
    <diylc.passive.Resistor><name>R1</name><value value="100.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R1</name><value value="100.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R1</name><value value="100.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R1</name><value value="220.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R1</name><value value="220.0" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.Resistor><name>R1</name><value value="1.5" unit="K"/></diylc.passive.Resistor>
    <diylc.passive.AxialElectrolyticCapacitor><name>25uF 25v</name><value value="25.0" unit="uF"/></diylc.passive.AxialElectrolyticCapacitor>
    <diylc.passive.AxialElectrolyticCapacitor><name>25uF 25v</name><value value="25.0" unit="uF"/></diylc.passive.AxialElectrolyticCapacitor>
    <diylc.passive.AxialFilmCapacitor><name>.1uF</name><value value="0.1" unit="uF"/></diylc.passive.AxialFilmCapacitor>
  </components>
</project>"""
    r = parse_diylc(xml)
    # Expect 4 distinct rows: 100K resistor (qty 3), 220K resistor (qty 2),
    # 1.5K resistor (qty 1), 25uF electrolytic (qty 2), 0.1uF film (qty 1).
    by_value = {(b.value, b.type[:8]): b for b in r.bom}
    assert ("100K", "Resistor")[0] in [b.value for b in r.bom]
    qtys = {b.value: b.quantity for b in r.bom if "Resistor" in b.type}
    assert qtys["100K"] == 3
    assert qtys["220K"] == 2
    assert qtys["1.5K"] == 1

    cap_qtys = {b.value: b.quantity for b in r.bom if "Electrolytic" in b.type}
    assert cap_qtys["25uF"] == 2
    # Synthetic refdes assigned (R1/R2/R3, C1/C2, ...).
    assert all(b.location for b in r.bom), "every row should have a refdes"
    resistor_refs = [b.location for b in r.bom if "Resistor" in b.type]
    assert resistor_refs == sorted(resistor_refs)  # nicely numbered
    assert any("non-unique" in w for w in r.warnings)


def test_parse_handles_empty_components():
    xml = b"""<?xml version="1.0" encoding="UTF-8" ?>
<project>
  <title>Empty</title>
</project>"""
    r = parse_diylc(xml)
    assert r.bom == []
    assert "No <components>" in r.warnings[0]
