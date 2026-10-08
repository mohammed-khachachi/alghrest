"""Strict deposit inputs and explicit command application contract."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.accounting.funding import Deposit, DepositReceipt, PaperDeposits
from core.config import settings
from scripts import paper

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": "-Infinity"},
        {"currency": "USD"},
        {"currency": "usdt"},
        {"reference": ""},
        {"reference": " "},
        {"reference": " trailing "},
        {"as_of": "2026-01-01T00:00:00Z"},
        {"timestamp": "2026-01-01T00:00:00Z"},
        {"account_id": ""},
        {"exchange": "unknown"},
    ],
)
def test_input_refuses_bad_amounts_currency_missing_identity_and_backdating(changes):
    with pytest.raises(ValidationError):
        Deposit.model_validate(
            {"exchange": "binance", "amount": "150", "reference": "month-1", **changes}
        )


def test_canonical_fingerprint_preserves_reference_but_ignores_decimal_spelling():
    items = [
        Deposit(exchange="binance", amount=Decimal(a), reference="month-1")
        for a in ["150", "150.00", "1.50e2"]
    ]
    assert len({x.fingerprint() for x in items}) == 1
    assert (
        items[0].fingerprint() != items[0].model_copy(update={"reference": "month-2"}).fingerprint()
    )


@pytest.mark.parametrize("apply", [False, True])
async def test_cli_dry_validation_and_apply_are_explicit_and_close_resources(
    monkeypatch, tmp_path, capsys, apply
):
    monkeypatch.setattr(settings, "environment", "paper_trading")
    item = Deposit(exchange="binance", amount=Decimal(150), reference="month-1")
    path = tmp_path / "deposit.json"
    path.write_text(item.model_dump_json())
    ledger = SimpleNamespace(close=AsyncMock())
    state = SimpleNamespace(initialize=AsyncMock(), shutdown=AsyncMock())
    receipt = DepositReceipt(
        book_id="paper_trading:test",
        deposit=item,
        applied=apply,
        applied_at=datetime.now(UTC),
        revision=1,
        balance_before=Decimal(150),
        balance_after=Decimal(300),
        value_usd=Decimal(150),
        units_issued=Decimal(150),
        unit_price=Decimal(1),
    )
    register = AsyncMock(return_value=receipt)
    monkeypatch.setattr(paper.Ledger, "connect", AsyncMock(return_value=ledger))
    monkeypatch.setattr(paper, "StateManager", lambda: state)
    monkeypatch.setattr(PaperDeposits, "register", register)
    await paper.run(SimpleNamespace(command="deposit", deposit=path, apply=apply))
    register.assert_awaited_once_with(item, apply=apply)
    output = capsys.readouterr().out
    assert ('"applied": true' in output) is apply
    assert ("Dry run" in output) is not apply
    state.shutdown.assert_awaited_once()
    ledger.close.assert_awaited_once()


async def test_cli_refuses_live_before_connecting(monkeypatch, tmp_path):
    path = tmp_path / "deposit.json"
    path.write_text(json.dumps({"exchange": "binance", "amount": "150", "reference": "month-1"}))
    monkeypatch.setattr(settings, "environment", "live")
    connect = AsyncMock()
    monkeypatch.setattr(paper.Ledger, "connect", connect)
    with pytest.raises(ValueError, match="paper_trading"):
        await paper.run(SimpleNamespace(command="deposit", deposit=path, apply=True))
    connect.assert_not_awaited()
