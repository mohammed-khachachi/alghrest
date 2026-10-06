"""Setup cannot infer funding or silently switch the operating environment."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from core.config import settings
from scripts.paper import run, validate

pytestmark = pytest.mark.unit


def manifests(tmp_path):
    opening, accounts = tmp_path / "opening.json", tmp_path / "accounts.json"
    opening.write_text(
        json.dumps(
            {
                "as_of": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "reference": "explicit synthetic statement",
                "cash": [{"exchange": "binance", "currency": "USD", "amount": "1000"}],
                "positions": [],
            }
        )
    )
    accounts.write_text('[{"exchange":"binance","account_id":"default","symbols":["BTC/USD"]}]')
    return opening, accounts


@pytest.mark.parametrize("environment", ["development", "live"])
def test_preparation_requires_explicit_paper_environment(tmp_path, monkeypatch, environment):
    monkeypatch.setattr(settings, "environment", environment)
    with pytest.raises(ValueError, match="paper_trading"):
        validate(*manifests(tmp_path))


async def test_dry_run_never_connects_or_invents_opening_cash(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from core.accounting.repository import Ledger

    monkeypatch.setattr(settings, "environment", "paper_trading")
    opening, accounts = manifests(tmp_path)
    connect = AsyncMock()
    monkeypatch.setattr(Ledger, "connect", connect)
    await run(SimpleNamespace(command="prepare", opening=opening, accounts=accounts, apply=False))
    connect.assert_not_awaited()
    accounts.write_text("[]")
    with pytest.raises(ValueError, match="explicit account"):
        validate(opening, accounts)
