"""Snapshot evidence, local PDF export and authenticated read-only endpoint checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from api.advisor import app
from api.routes import research_brief as route
from api.services.research_pdf import render_research_pdf
from connectors.advisory.research_journal import ResearchJournal
from connectors.advisory.storage import AdvisoryStore
from core.advisory.openterminal_context import PublicHeadline, TerminalSource
from core.advisory.openterminal_research import CandleAnalysis, ResearchQuote, TerminalResearch
from core.advisory.research_brief import (
    BriefEntry,
    ResearchBrief,
    comparison_lines,
    indicator_explanations,
)
from core.advisory.research_journal import ResearchSnapshot
from core.config import settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def report(now=NOW, symbol="AAPL", *, interval="1d", close="100", rsi="60", atr="2"):
    return TerminalResearch(
        symbol=symbol,
        assessed_at=now,
        quote=ResearchQuote(
            symbol=symbol,
            name="Apple Inc.",
            price=Decimal("999"),
            currency="USD",
            provider="nasdaq",
        ),
        analysis=CandleAnalysis(
            count=60,
            first_time=now - timedelta(days=60),
            last_time=now - timedelta(days=1),
            last_close=Decimal(close),
            sma20=Decimal("90"),
            sma50=Decimal("80"),
            rsi14_simple=Decimal(rsi),
            atr14_simple=Decimal(atr),
            trend="above_averages",
            history_provider="yahoo",
            interval=interval,
            interval_basis="provider_request" if interval == "1d" else "UNVERIFIED",
            history_fetched_at=now,
            history_cache_state="fetched",
        ),
        headlines=(
            PublicHeadline(
                title="Apple earnings fixture",
                url="https://example.org/source?x=1&y=2",
                publisher="Fixture source",
                published_at=now - timedelta(hours=1),
            ),
        ),
        sources=tuple(
            TerminalSource(kind=kind, state="available", received_at=now, response_sha256="a" * 64)
            for kind in ("quotes", "news", "history")
        ),
    )


def saved(index=1, now=NOW, **kwargs):
    return ResearchSnapshot(id=f"{index:032x}", saved_at=now, report=report(now=now, **kwargs))


@pytest.fixture
def journal(tmp_path):
    return ResearchJournal(AdvisoryStore(str(tmp_path / "brief.sqlite3")))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("p" * 48))
    monkeypatch.setattr(settings, "advisory_db_path", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(settings, "advisory_kafka_servers", "")
    monkeypatch.setattr(route, "utcnow", lambda: NOW)
    with TestClient(app, headers={"Authorization": "Bearer " + "p" * 48}) as value:
        yield value


def test_brief_is_read_only_and_includes_symbols_with_no_snapshot(journal):
    journal.watch("AAPL", True)
    journal.watch("MSFT", True)
    old = saved(now=NOW - timedelta(hours=1))
    new = saved(2)
    journal.save(old)
    journal.save(new)
    before = journal.history("AAPL")
    brief = journal.brief(now=NOW)
    assert [entry.symbol for entry in brief.entries] == ["AAPL", "MSFT"]
    assert brief.entries[0].snapshots == (new, old)
    assert brief.entries[1].snapshots == ()
    assert journal.history("AAPL") == before
    assert journal.watchlist()[0].snapshots == 2


def test_corrupt_snapshot_cannot_be_silently_omitted_from_brief(journal):
    journal.watch("AAPL", True)
    journal.save(saved())
    with journal.store.connect() as db:
        db.execute("UPDATE research_snapshots SET id=?", ("b" * 32,))
    with pytest.raises(ValueError):
        journal.brief(now=NOW)


def test_brief_rejects_wrong_symbol_future_clock_and_duplicate_symbols():
    with pytest.raises(ValidationError):
        BriefEntry(symbol="MSFT", snapshots=(saved(),))
    entry = BriefEntry(symbol="AAPL", snapshots=(saved(),))
    with pytest.raises(ValidationError):
        ResearchBrief(generated_at=NOW - timedelta(seconds=1), entries=(entry,))
    with pytest.raises(ValidationError):
        ResearchBrief(generated_at=NOW, entries=(entry, entry))


def test_indicators_use_historical_close_not_quote_and_preserve_zero():
    texts = dict(indicator_explanations(report(atr="0").analysis))
    assert "999" not in texts["الاتجاه"]
    assert "0%" in texts["التذبذب"]
    assert "60" in texts["الزخم"]
    assert all("لا تتوفر" in text for _, text in indicator_explanations(None))


@pytest.mark.parametrize(
    "rsi,word", [("0", "الانخفاضات أكبر"), ("50", "متوازنة"), ("100", "الارتفاعات أكبر")]
)
def test_rsi_explanation_uses_gain_loss_balance(rsi, word):
    assert word in dict(indicator_explanations(report(rsi=rsi).analysis))["الزخم"]


def test_comparison_has_numbers_but_no_delta_for_unknown_timeframe():
    old = report(now=NOW - timedelta(hours=1), interval="UNVERIFIED", close="95")
    new = report(interval="UNVERIFIED")
    lines = comparison_lines(new, old)
    assert any("غير مؤكدة" in line for line in lines)
    assert any("95 ثم 100" in line for line in lines)
    assert not any("؛ الفرق" in line for line in lines)
    assert "لا توجد لقطة سابقة" in comparison_lines(new, None)[0]


def test_unavailable_news_does_not_claim_all_headlines_disappeared():
    current = report().model_copy(
        update={
            "headlines": (),
            "sources": tuple(
                (
                    TerminalSource(kind=s.kind, state="unavailable", received_at=NOW)
                    if s.kind == "news"
                    else s
                )
                for s in report().sources
            ),
        }
    )
    lines = comparison_lines(current, report(now=NOW - timedelta(hours=1)))
    assert any("الأخبار ناقصة" in line for line in lines)
    assert not any("غابت عن النتائج 1" in line for line in lines)


def test_pdf_embeds_font_links_and_literal_untrusted_headlines():
    r = report().model_copy(
        update={
            "headlines": (
                PublicHeadline(
                    title='<script>& "عنوان عربي" ' + "long " * 70,
                    url="https://example.org/source?x=1&y=2",
                    publisher="Fixture",
                    published_at=None,
                ),
            )
        }
    )
    record = ResearchSnapshot(id="a" * 32, saved_at=NOW, report=r)
    value = render_research_pdf(
        ResearchBrief(generated_at=NOW, entries=(BriefEntry(symbol="AAPL", snapshots=(record,)),))
    )
    assert value.startswith(b"%PDF-") and value.rstrip().endswith(b"%%EOF")
    assert b"/FontFile2" in value
    assert b"https://example.org/source?x=1&y=2" in value
    assert len(value) < 2_000_000


def test_fifty_missing_symbols_can_export_without_fake_indicators():
    brief = ResearchBrief(
        generated_at=NOW,
        entries=tuple(BriefEntry(symbol=f"SYM{i}", snapshots=()) for i in range(50)),
    )
    assert render_research_pdf(brief).startswith(b"%PDF-")


def test_simultaneous_exports_keep_dynamic_font_documents_separate():
    brief = ResearchBrief(
        generated_at=NOW, entries=(BriefEntry(symbol="AAPL", snapshots=(saved(),)),)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(render_research_pdf, [brief, brief]))
    assert all(
        value.startswith(b"%PDF-") and b"/FontFile2" in value and value.rstrip().endswith(b"%%EOF")
        for value in outputs
    )


def test_export_auth_and_empty_watchlist(client):
    path = "/assistant-api/research-brief.pdf"
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(path).status_code == 409


def test_pdf_api_no_market_calls_no_history_writes_and_safe_filename(client):
    journal = ResearchJournal(app.state.service.store)
    journal.watch("AAPL", True)
    journal.save(saved(now=NOW - timedelta(hours=2)))
    previous = journal.history("AAPL")
    with patch(
        "api.routes.openterminal_context.terminal_research",
        side_effect=AssertionError("No market fetch"),
    ):
        response = client.get("/assistant-api/research-brief.pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="ALGHREST-research-2026-10-16.pdf"'
    )
    assert journal.history("AAPL") == previous


def test_render_failure_is_reported_without_filesystem_details(client, monkeypatch):
    journal = ResearchJournal(app.state.service.store)
    journal.watch("AAPL", True)
    monkeypatch.setattr(
        "api.services.research_pdf.render_research_pdf",
        lambda _: (_ for _ in ()).throw(OSError("private/path")),
    )
    response = client.get("/assistant-api/research-brief.pdf")
    assert response.status_code == 503 and "private/path" not in response.text
