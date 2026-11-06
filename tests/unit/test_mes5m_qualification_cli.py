"""The CLI exposes development preflight only, never a performance command."""

from pathlib import Path

import pytest

from scripts.qualify_mes5m import main

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "partition", ["holdout", "SEALED_HOLDOUT", "validation", "all", "../holdout"]
)
def test_denied_partition_never_opens_a_source(partition, monkeypatch, capsys):
    def denied_read(_):
        raise AssertionError("A denied request read a file")

    monkeypatch.setattr(Path, "read_bytes", denied_read)
    with pytest.raises(SystemExit) as exc:
        main(["--partition", partition])
    assert exc.value.code == 2
    assert "Invalid arguments" in capsys.readouterr().err


def test_pinned_configuration_exists_and_matches_the_frozen_protocol():
    from backtesting.mes5m_spec import ResearchSpec
    from scripts.qualify_mes5m import SPECIFICATION

    assert ResearchSpec.model_validate_json(SPECIFICATION.read_bytes()) == ResearchSpec()
