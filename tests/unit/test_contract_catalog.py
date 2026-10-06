"""Source-verified outright economics and instrument identity, without trading IO."""

from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from core.advisory.analysis import risk_worksheet
from core.advisory.models import CATALOG, FuturesSpec, Instrument, MarketSnapshot, RiskWorksheet
from tests.unit.test_advisory import market

pytestmark = pytest.mark.unit

# Independent expectations from official sources recorded in the docs.
SPECS = [
    ("MES", "0.25", "5", "1.25", 1, "HMUZ", "cash"),
    ("MYM", "1", "0.5", "0.5", 1, "HMUZ", "cash"),
    ("MNQ", "0.25", "2", "0.5", 1, "HMUZ", "cash"),
    ("MGC", "0.1", "10", "1", 1, "GJMQVZ", "physical"),
    ("M2K", "0.1", "5", "0.5", 2, "HMUZ", "cash"),
    ("MCL", "0.01", "100", "1", 2, "FGHJKMNQUVXZ", "cash"),
    ("M6E", "0.0001", "12500", "1.25", 2, "HMUZ", "physical"),
    ("M6B", "0.0001", "6250", "0.625", 2, "HMUZ", "physical"),
    ("MHG", "0.0005", "2500", "1.25", 2, "FGHJKMNQUVXZ", "cash"),
]


@pytest.mark.parametrize("root,tick,multiplier,tick_value,tier,months,settlement", SPECS)
def test_official_contract_economics(root, tick, multiplier, tick_value, tier, months, settlement):
    instrument = CATALOG[root]
    assert instrument.id == instrument.symbol == root
    assert instrument.currency == "USD" and instrument.market == "cme_future"
    assert instrument.tick_size == Decimal(tick)
    assert instrument.point_value == Decimal(multiplier)
    assert instrument.tick_value == Decimal(tick_value)
    spec = instrument.futures_spec
    assert spec is not None
    assert spec.research_tier == tier and spec.month_codes == months
    assert spec.settlement == settlement
    assert spec.version == "cme-outright-2026-10-05"
    assert str(spec.reviewed_on) == "2026-10-05"
    assert all(url.host == "www.cmegroup.com" for url in spec.sources)
    assert Instrument.model_validate(instrument.model_dump()) == instrument
    with pytest.raises(ValidationError):
        instrument.point_value = Decimal(100000)
    with pytest.raises(ValidationError):
        spec.month_codes = "F"


def test_tier_membership_and_shared_equity_exposure_are_explicit():
    assert {
        key
        for key, value in CATALOG.items()
        if value.futures_spec and value.futures_spec.research_tier == 1
    } == {"MES", "MYM", "MNQ", "MGC"}
    assert {
        key
        for key, value in CATALOG.items()
        if value.futures_spec and value.futures_spec.research_tier == 2
    } == {"M2K", "MCL", "M6E", "M6B", "MHG"}
    assert all(
        CATALOG[key].futures_spec.exposure_group == "us_equity_index"
        for key in ("MES", "MYM", "MNQ", "M2K", "NQ")
    )
    with pytest.raises(TypeError):
        CATALOG["MNQ"] = CATALOG["NQ"]


@pytest.mark.parametrize("root,tick,multiplier,tick_value,tier,months,settlement", SPECS)
def test_dated_contract_accepts_each_family_month_and_rejects_aliases(
    root, tick, multiplier, tick_value, tier, months, settlement
):
    value = market().model_dump()
    for month in months:
        for year in ("26", "2026"):
            contract = root + month + year
            imported = MarketSnapshot.model_validate(
                value | {"instrument_id": root, "contract": contract}
            )
            assert imported.contract == contract
    for contract in (
        None,
        root,
        root + "1!",
        "NQZ26",
        root + "Z026",
        root + "Z2",
        root + "Z20266",
        root + "Z٢٦",
        root.lower() + "Z26",
        root + "Z26-M27",
    ):
        with pytest.raises(ValidationError, match="dated contract"):
            MarketSnapshot.model_validate(value | {"instrument_id": root, "contract": contract})
    for month in set("FGHJKMNQUVXZ") - set(months):
        with pytest.raises(ValidationError, match="dated contract"):
            MarketSnapshot.model_validate(
                value | {"instrument_id": root, "contract": root + month + "26"}
            )


@pytest.mark.parametrize("root,tick,multiplier,tick_value,tier,months,settlement", SPECS)
def test_one_tick_loss_costs_and_boundaries_use_each_contract(
    root, tick, multiplier, tick_value, tier, months, settlement
):
    tick = Decimal(tick)
    tick_value = Decimal(tick_value)
    request = RiskWorksheet(
        instrument_id=root,
        account_value=100,
        risk_percent=1,
        entry=100,
        stop=Decimal(100) - tick,
        fees_per_unit=2,
        slippage_points=tick,
    )
    result = risk_worksheet(request)
    assert Decimal(result["loss_per_unit"]) == 2 * tick_value + 2
    assert Decimal(result["size"]) == 0
    for epsilon in (-tick / 100, tick / 100):
        with pytest.raises(ValueError, match="align with tick"):
            risk_worksheet(request.model_copy(update={"stop": request.stop + epsilon}))
    for budget, size in (
        (tick_value - Decimal("0.000001"), 0),
        (tick_value, 1),
        (tick_value + Decimal("0.000001"), 1),
    ):
        row = request.model_copy(
            update={
                "account_value": budget * 100,
                "fees_per_unit": Decimal(0),
                "slippage_points": Decimal(0),
            }
        )
        assert Decimal(risk_worksheet(row)["size"]) == size


@settings(max_examples=180, derandomize=True, database=None)
@given(
    root=st.sampled_from([s[0] for s in SPECS]),
    ticks=st.integers(min_value=1, max_value=1000),
    capital=st.integers(min_value=1, max_value=100000),
    risk_basis_points=st.integers(min_value=1, max_value=100),
    fee_cents=st.integers(min_value=0, max_value=1000),
)
def test_property_structural_stop_is_preserved_and_contract_risk_is_bounded(
    root, ticks, capital, risk_basis_points, fee_cents
):
    instrument = CATALOG[root]
    request = RiskWorksheet(
        instrument_id=root,
        account_value=capital,
        risk_percent=Decimal(risk_basis_points) / 100,
        entry=2000,
        stop=Decimal(2000) - ticks * instrument.tick_size,
        fees_per_unit=Decimal(fee_cents) / 100,
    )
    before = request.model_dump()
    result = risk_worksheet(request)
    size = Decimal(result["size"])
    loss = Decimal(result["estimated_loss_at_stop"])
    assert request.model_dump() == before
    assert size >= 0 and size == size.to_integral_value()
    assert loss == size * Decimal(result["loss_per_unit"])
    assert loss <= Decimal(result["risk_budget"]) <= Decimal(capital) / 100


def test_invalid_spec_and_legacy_report_compatibility():
    spec = CATALOG["MNQ"].futures_spec.model_dump()
    with pytest.raises(ValidationError, match="distinct"):
        FuturesSpec.model_validate(spec | {"month_codes": "HH"})
    with pytest.raises(ValidationError):
        FuturesSpec.model_validate(spec | {"month_codes": "ABC"})
    with pytest.raises(ValidationError):
        FuturesSpec.model_validate(spec | {"sources": []})
    with pytest.raises(ValidationError, match="USD CME"):
        Instrument.model_validate(CATALOG["BTCUSDT-PERP"].model_dump() | {"futures_spec": spec})
    with pytest.raises(ValidationError, match="USD CME"):
        Instrument.model_validate(CATALOG["MNQ"].model_dump() | {"currency": "EUR"})
    legacy = Instrument.model_validate(CATALOG["MNQ"].model_dump() | {"futures_spec": None})
    assert legacy.point_value == 2 and not legacy.valid_contract("MNQZ26")
    assert not CATALOG["NASDAQ100"].valid_contract("NDXZ26")


@pytest.mark.parametrize(
    "change",
    [
        {"risk_percent": Decimal("1.000001")},
        {"risk_percent": Decimal("NaN")},
        {"fees_per_unit": Decimal("-1")},
        {"slippage_points": Decimal("-1")},
        {"account_value": Decimal("Infinity")},
        {"account_value": Decimal("-1")},
        {"entry": Decimal("NaN")},
    ],
)
def test_internal_copies_cannot_bypass_risk_input_bounds(change):
    request = RiskWorksheet(instrument_id="MES", account_value=25000, entry=100, stop=99)
    with pytest.raises(ValidationError):
        risk_worksheet(request.model_copy(update=change))


def test_legacy_crypto_worksheet_keeps_fractional_units_and_costs():
    request = RiskWorksheet(
        instrument_id="BTCUSDT-PERP",
        account_value=10000,
        risk_percent=1,
        entry=50000,
        stop=49990,
        slippage_points=1,
        fees_per_unit=1,
    )
    result = risk_worksheet(request)
    assert Decimal(result["size"]) == Decimal("8.333333")
    assert Decimal(result["estimated_loss_at_stop"]) == Decimal("99.999996")
    assert result["currency"] == "USDT"
