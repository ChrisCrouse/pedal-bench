"""End-to-end smoke tests for the inventory + shortage HTTP routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pedal_bench.api.app import create_app
from pedal_bench.api.deps import get_inventory_store, get_project_store
from pedal_bench.core.inventory_store import InventoryStore
from pedal_bench.core.models import BOMItem, Project
from pedal_bench.core.project_store import ProjectStore


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    pstore = ProjectStore(tmp_path / "projects")
    inv = InventoryStore(tmp_path / "inventory.json")

    app = create_app()
    app.dependency_overrides[get_project_store] = lambda: pstore
    app.dependency_overrides[get_inventory_store] = lambda: inv

    # Seed a project with a small BOM
    project = Project(
        slug="muff",
        name="Big Muff",
        bom=[
            BOMItem(location="R1", value="10k", type="1/4W Resistor", quantity=4),
            BOMItem(location="IC1", value="TL072", type="Op-amp", quantity=1),
        ],
    )
    pstore.save(project)

    return TestClient(app)


def test_upsert_then_list(client: TestClient) -> None:
    r = client.post("/api/v1/inventory/items", json={
        "kind": "resistor",
        "value": "10K Ohm",
        "on_hand": 50,
        "display_value": "10K",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["key"] == "resistor::10k"
    assert data["on_hand"] == 50
    assert data["available"] == 50

    r = client.get("/api/v1/inventory/items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1


def test_reservation_blocks_overcommit(client: TestClient) -> None:
    client.post("/api/v1/inventory/items", json={
        "kind": "ic", "value": "TL072", "on_hand": 2,
    })
    r = client.post(
        "/api/v1/inventory/items/ic::TL072/reserve",
        json={"slug": "muff", "qty": 5},
    )
    assert r.status_code == 400


def test_project_shortage(client: TestClient) -> None:
    # Stock partial — 2 of 4 resistors, all ICs
    client.post("/api/v1/inventory/items", json={
        "kind": "resistor", "value": "10k", "on_hand": 2,
    })
    client.post("/api/v1/inventory/items", json={
        "kind": "ic", "value": "TL072", "on_hand": 1,
    })

    r = client.get("/api/v1/projects/muff/shortage")
    assert r.status_code == 200, r.text
    rows = {row["kind"]: row for row in r.json()["rows"]}
    assert rows["resistor"]["needed"] == 4
    assert rows["resistor"]["shortfall"] == 2
    assert rows["ic"]["shortfall"] == 0


def test_consume_reservations_decrements_stock(client: TestClient) -> None:
    client.post("/api/v1/inventory/items", json={
        "kind": "ic", "value": "TL072", "on_hand": 4,
    })
    client.post(
        "/api/v1/inventory/items/ic::TL072/reserve",
        json={"slug": "muff", "qty": 2},
    )
    r = client.post("/api/v1/projects/muff/consume-reservations")
    assert r.status_code == 200
    assert r.json()["consumed"] == [["ic::TL072", 2]]

    r = client.get("/api/v1/inventory/items")
    item = r.json()[0]
    assert item["on_hand"] == 2
    assert item["reservations"] == {}


def test_global_shortage_excludes_inactive_projects(client: TestClient) -> None:
    # Add a second active project + a deactivated one
    pstore: ProjectStore = client.app.dependency_overrides[get_project_store]()
    pstore.save(Project(
        slug="rat", name="Rat",
        bom=[BOMItem(location="R1", value="10k", type="1/4W Resistor", quantity=3)],
    ))
    pstore.save(Project(
        slug="future", name="Future",
        bom=[BOMItem(location="R1", value="10k", type="1/4W Resistor", quantity=99)],
        active=False,
    ))
    client.post("/api/v1/inventory/items", json={
        "kind": "resistor", "value": "10k", "on_hand": 5,
    })

    r = client.get("/api/v1/inventory/shortage")
    assert r.status_code == 200
    rows = r.json()["rows"]
    resistor_row = next(r for r in rows if r["kind"] == "resistor")
    assert resistor_row["needed"] == 7  # 4 (muff) + 3 (rat); future excluded
    assert resistor_row["shortfall"] == 2


def test_patch_below_reservation_rejected(client: TestClient) -> None:
    client.post("/api/v1/inventory/items", json={
        "kind": "ic", "value": "TL072", "on_hand": 4,
    })
    client.post(
        "/api/v1/inventory/items/ic::TL072/reserve",
        json={"slug": "muff", "qty": 3},
    )
    r = client.patch("/api/v1/inventory/items/ic::TL072", json={"on_hand": 1})
    assert r.status_code == 400


def test_pot_items_can_be_added_and_match_bom(client: TestClient) -> None:
    """Pots are now a first-class inventory kind. A B25K stocked in the
    Owned tab should cover a Potentiometer BOM row that lists 'B25K'."""
    pstore: ProjectStore = client.app.dependency_overrides[get_project_store]()
    pstore.save(Project(
        slug="phaser",
        name="Phaser",
        bom=[
            BOMItem(location="DEPTH", value="B25K", type="Potentiometer"),
            BOMItem(location="RATE", value="A100K", type="Potentiometer"),
        ],
    ))

    # Stock one DEPTH-compatible pot but leave RATE empty.
    r = client.post("/api/v1/inventory/items", json={
        "kind": "pot", "value": "B25K", "on_hand": 2,
    })
    assert r.status_code == 200, r.text
    assert r.json()["key"] == "pot::b25k"

    r = client.get("/api/v1/projects/phaser/shortage")
    rows = {f"{x['kind']}::{x['value_norm']}": x for x in r.json()["rows"]}
    assert rows["pot::b25k"]["available"] == 2
    assert rows["pot::b25k"]["shortfall"] == 0
    # A100K isn't stocked yet — should appear as a shortfall.
    assert rows["pot::a100k"]["shortfall"] == 1


def test_switch_items_can_be_added_and_match_bom(client: TestClient) -> None:
    """Switches are now a first-class inventory kind. A '3PDT footswitch'
    stocked in the Owned tab should cover a Switch BOM row that lists the
    same descriptor."""
    pstore: ProjectStore = client.app.dependency_overrides[get_project_store]()
    pstore.save(Project(
        slug="phaser",
        name="Phaser",
        bom=[
            BOMItem(location="PV", value="SPDT (On/On)", type="Switch"),
            BOMItem(location="RANGE", value="SPDT (On/Off/On)", type="Switch"),
            BOMItem(location="BYPASS", value="3PDT footswitch", type="Switch"),
        ],
    ))

    # Stock the SPDT (On/On) but not the others — should show shortfall on
    # the rest.
    r = client.post("/api/v1/inventory/items", json={
        "kind": "switch", "value": "SPDT (On/On)", "on_hand": 4,
    })
    assert r.status_code == 200, r.text
    assert r.json()["key"] == "switch::spdt(on/on)"

    r = client.get("/api/v1/projects/phaser/shortage")
    rows = {f"{x['kind']}::{x['value_norm']}": x for x in r.json()["rows"]}
    assert rows["switch::spdt(on/on)"]["available"] == 4
    assert rows["switch::spdt(on/on)"]["shortfall"] == 0
    # The other two switches aren't stocked yet.
    assert rows["switch::spdt(on/off/on)"]["shortfall"] == 1
    assert rows["switch::3pdtfootswitch"]["shortfall"] == 1


def test_switch_position_configs_are_distinct_inventory_items(
    client: TestClient,
) -> None:
    """SPDT (On/On) and SPDT (On/Off/On) are physically different switches —
    they must occupy separate inventory rows."""
    r = client.post("/api/v1/inventory/items", json={
        "kind": "switch", "value": "SPDT (On/On)", "on_hand": 6,
    })
    assert r.json()["key"] == "switch::spdt(on/on)"
    r = client.post("/api/v1/inventory/items", json={
        "kind": "switch", "value": "SPDT (On/Off/On)", "on_hand": 2,
    })
    assert r.json()["key"] == "switch::spdt(on/off/on)"

    items = client.get("/api/v1/inventory/items").json()
    by_key = {i["key"]: i for i in items}
    assert by_key["switch::spdt(on/on)"]["on_hand"] == 6
    assert by_key["switch::spdt(on/off/on)"]["on_hand"] == 2


def test_pot_taper_distinguishes_inventory_items(client: TestClient) -> None:
    """B25K and A25K must be separate inventory items — same resistance,
    different taper, physically different parts."""
    r = client.post("/api/v1/inventory/items", json={
        "kind": "pot", "value": "B25K", "on_hand": 5,
    })
    assert r.json()["key"] == "pot::b25k"
    r = client.post("/api/v1/inventory/items", json={
        "kind": "pot", "value": "A25K", "on_hand": 3,
    })
    assert r.json()["key"] == "pot::a25k"

    items = client.get("/api/v1/inventory/items").json()
    by_key = {i["key"]: i for i in items}
    assert by_key["pot::b25k"]["on_hand"] == 5
    assert by_key["pot::a25k"]["on_hand"] == 3


def test_value_magnitude_distinguishes_mega_from_milli(client: TestClient) -> None:
    """Regression: 'M' (mega) must not be lowercased away into 'm' (milli)."""
    # The displayed value must keep its case so the magnitude parser sees 'M'.
    client.post("/api/v1/inventory/items", json={
        "kind": "resistor", "value": "10M", "on_hand": 5,
    })
    client.post("/api/v1/inventory/items", json={
        "kind": "resistor", "value": "1k", "on_hand": 5,
    })
    items = client.get("/api/v1/inventory/items").json()
    by_value = {it["display_value"]: it for it in items}
    assert by_value["10M"]["value_magnitude"] == 10_000_000.0
    assert by_value["1k"]["value_magnitude"] == 1_000.0


def test_list_projects_includes_readiness(client: TestClient) -> None:
    """GET /projects enriches each summary with bom_count, soldered_count,
    parts_needed/covered, and readiness_pct so the sidebar/home can render
    heat dots without N extra calls."""
    # The fixture seeded a 'muff' project with R1×4 (10k) + IC1×1 (TL072).
    # Stock half the resistors and all the ICs → covered=2+1=3, needed=5.
    client.post("/api/v1/inventory/items", json={
        "kind": "resistor", "value": "10k", "on_hand": 2,
    })
    client.post("/api/v1/inventory/items", json={
        "kind": "ic", "value": "TL072", "on_hand": 1,
    })

    r = client.get("/api/v1/projects")
    assert r.status_code == 200
    summaries = r.json()
    assert len(summaries) == 1
    s = summaries[0]
    assert s["slug"] == "muff"
    assert s["bom_count"] == 2
    assert s["soldered_count"] == 0
    assert s["parts_needed"] == 5
    assert s["parts_covered"] == 3
    assert s["readiness_pct"] == 60


def test_list_projects_readiness_null_when_no_trackable_bom(
    client: TestClient,
) -> None:
    """A fresh project with no trackable BOM rows should report readiness_pct
    as null — distinguishes 'fully ready' (100) from 'nothing to be ready
    for'."""
    pstore: ProjectStore = client.app.dependency_overrides[get_project_store]()
    pstore.save(Project(slug="empty", name="Empty"))

    r = client.get("/api/v1/projects")
    summaries = {s["slug"]: s for s in r.json()}
    assert summaries["empty"]["readiness_pct"] is None
    assert summaries["empty"]["parts_needed"] == 0


def test_delete_project_clears_its_reservations(client: TestClient) -> None:
    client.post("/api/v1/inventory/items", json={
        "kind": "ic", "value": "TL072", "on_hand": 4,
    })
    client.post(
        "/api/v1/inventory/items/ic::TL072/reserve",
        json={"slug": "muff", "qty": 2},
    )
    r = client.delete("/api/v1/projects/muff")
    assert r.status_code == 204
    item = client.get("/api/v1/inventory/items").json()[0]
    assert item["reservations"] == {}
    assert item["on_hand"] == 4
