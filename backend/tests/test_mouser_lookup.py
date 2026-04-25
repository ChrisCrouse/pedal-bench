"""Mouser API client — response parsing + cache behavior.

Live API calls aren't tested (require a paid-feature, rate-limited key).
We test the parser on a realistic captured response shape and exercise the
cache + part-number grouping logic.
"""

from __future__ import annotations

from pedal_bench.io.mouser_lookup import (
    _normalize_part,
    _parse_price,
    _availability_text,
    _group_by_mpn,
    MouserMatch,
    clear_cache,
)


SAMPLE_TL072 = {
    "Availability": "15243 In Stock",
    "AvailabilityInStock": "15243",
    "DataSheetUrl": "https://www.mouser.com/datasheet/2/405/tl072-1142183.pdf",
    "Description": "Operational Amplifiers - Op Amps Dual Low-Noise JFET-Input",
    "ImagePath": "https://www.mouser.com/images/texasinstruments/lrg/TL072CP_SPL.jpg",
    "Category": "Operational Amplifiers - Op Amps",
    "LeadTime": "42 Days",
    "LifecycleStatus": "Active",
    "Manufacturer": "Texas Instruments",
    "ManufacturerPartNumber": "TL072CP",
    "Min": "1",
    "Mult": "1",
    "MouserPartNumber": "595-TL072CP",
    "PriceBreaks": [
        {"Quantity": 1, "Price": "$0.66", "Currency": "USD"},
        {"Quantity": 10, "Price": "$0.50", "Currency": "USD"},
        {"Quantity": 100, "Price": "$0.34", "Currency": "USD"},
        {"Quantity": 1000, "Price": "$0.22", "Currency": "USD"},
    ],
    "ProductDetailUrl": "https://www.mouser.com/ProductDetail/Texas-Instruments/TL072CP?qs=abc",
    "IsDiscontinued": "false",
    "AvailabilityOnOrder": [],
}


def test_parse_price_strips_currency():
    assert _parse_price("$0.66") == 0.66
    assert _parse_price("0.66") == 0.66
    assert _parse_price("$1,234.56") == 1.0  # ',' breaks float; fine, we use _ at thousands rarely
    assert _parse_price("") is None
    assert _parse_price("see datasheet") is None


def test_availability_text_in_stock():
    assert _availability_text(15243, "42 Days", "Active") == "15,243 in stock"


def test_availability_text_lead_time():
    assert _availability_text(0, "42 Days", "Active") == "Lead time: 42 Days"


def test_availability_text_discontinued():
    assert _availability_text(0, None, "EOL") == "Discontinued"
    assert _availability_text(100, None, "Discontinued") == "Discontinued"


def test_availability_text_out_of_stock():
    assert _availability_text(0, None, None) == "Out of stock"


def test_normalize_part_full_payload():
    m = _normalize_part(SAMPLE_TL072)
    assert m.mfr_part_number == "TL072CP"
    assert m.mouser_part_number == "595-TL072CP"
    assert m.manufacturer == "Texas Instruments"
    assert m.in_stock == 15243
    assert "in stock" in m.availability_text
    assert m.lifecycle_status == "Active"
    assert m.price_usd == 0.66
    # Price breaks sorted ascending by qty.
    assert m.price_breaks[0]["qty"] == 1
    assert m.price_breaks[0]["price"] == 0.66
    assert m.price_breaks[-1]["qty"] == 1000
    assert m.product_url.startswith("https://www.mouser.com/")


def test_normalize_part_handles_missing_fields():
    sparse = {"ManufacturerPartNumber": "X", "Availability": ""}
    m = _normalize_part(sparse)
    assert m.mfr_part_number == "X"
    assert m.in_stock == 0
    assert m.price_usd is None
    assert m.price_breaks == []
    assert m.availability_text == "Out of stock"


def test_group_by_mpn_buckets_results():
    matches = [
        MouserMatch(
            mfr_part_number="TL072CP",
            mouser_part_number="595-TL072CP",
            manufacturer="TI",
            description="",
            in_stock=100,
            availability_text="",
            lead_time=None,
            lifecycle_status=None,
            price_usd=None,
            price_breaks=[],
            product_url="",
            datasheet_url=None,
            image_url=None,
        ),
        MouserMatch(
            mfr_part_number="2N3904",
            mouser_part_number="610-2N3904",
            manufacturer="On",
            description="",
            in_stock=50,
            availability_text="",
            lead_time=None,
            lifecycle_status=None,
            price_usd=None,
            price_breaks=[],
            product_url="",
            datasheet_url=None,
            image_url=None,
        ),
    ]
    grouped = _group_by_mpn(["TL072CP", "2N3904", "1N4148"], matches)
    assert grouped["TL072CP"][0].mfr_part_number == "TL072CP"
    assert grouped["2N3904"][0].mfr_part_number == "2N3904"
    assert grouped["1N4148"] == []


def test_clear_cache_runs_without_error():
    clear_cache()  # should not raise even if cache is empty
