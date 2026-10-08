"""Public evidence requests repeat verification; fresh folds share their outcomes."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backtesting import futures, validation
from tests.unit.test_futures_research import request
from tests.unit.test_futures_validation import config, walk_input, walk_plan

pytestmark = pytest.mark.unit


async def test_fresh_walk_runs_each_fold_once_and_reopened_requests_replay_every_fold(monkeypatch):
    inputs = walk_input()
    plan = walk_plan(inputs)
    runner = AsyncMock(wraps=futures._run)
    monkeypatch.setattr(futures, "_run", runner)

    fresh = await validation.walk_forward_futures(inputs, plan=plan, configuration=config())
    assert runner.await_count == len(plan.windows)
    assert len(fresh.folds) == len(plan.windows)
    assert not fresh.trade_permitted and not fresh.execution_enabled

    saved = validation.FuturesWalkStudy.model_validate_json(fresh.model_dump_json())
    for _ in range(2):
        runner.reset_mock()
        replayed = await validation.verify_futures_walk(saved)
        assert runner.await_count == len(plan.windows)
        assert replayed.model_dump(mode="json") == saved.model_dump(mode="json")
        assert replayed is not saved


@pytest.mark.parametrize(
    "entry",
    ["verify_run", "edge", "verify_edge", "uncertainty", "verify_uncertainty"],
)
async def test_separate_evidence_requests_each_replay_the_source_once(monkeypatch, entry):
    configuration = config()
    source = await futures.run_futures_research(request())
    edge = await futures.futures_edge_analysis(source, configuration=configuration.sampling)
    uncertainty = await validation.futures_expectancy_uncertainty(edge, configuration=configuration)
    runner = AsyncMock(wraps=futures._run)
    monkeypatch.setattr(futures, "_run", runner)

    async def invoke():
        if entry == "verify_run":
            return await futures.verify_futures_run(source)
        if entry == "edge":
            return await futures.futures_edge_analysis(source, configuration=configuration.sampling)
        if entry == "verify_edge":
            return await futures.verify_futures_edge_study(edge)
        if entry == "uncertainty":
            return await validation.futures_expectancy_uncertainty(
                edge, configuration=configuration
            )
        return await validation.verify_futures_uncertainty(uncertainty)

    first = await invoke()
    assert runner.await_count == 1
    second = await invoke()
    assert runner.await_count == 2
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first is not second


async def test_verified_result_from_an_earlier_request_is_not_trusted_after_path_mutation(
    monkeypatch,
):
    source = await futures.run_futures_research(request())
    verified = await futures.verify_futures_run(source)
    partition = verified.partitions[0]
    forged = verified.model_copy(
        update={
            "partitions": (
                partition.model_copy(
                    update={
                        "fills": (
                            partition.fills[0].model_copy(update={"reason": "forged_fill_reason"}),
                            *partition.fills[1:],
                        )
                    }
                ),
                *verified.partitions[1:],
            )
        }
    )
    runner = AsyncMock(wraps=futures._run)
    monkeypatch.setattr(futures, "_run", runner)
    with pytest.raises(ValueError, match="Futures research replay mismatch"):
        await futures.verify_futures_run(forged)
    assert runner.await_count == 1


async def test_internal_module_source_changes_invalidate_saved_evidence(monkeypatch):
    source = await futures.run_futures_research(request())
    name = "backtesting/_futures_evidence.py"
    module_path = Path(futures.__file__).parent / "_futures_evidence.py"
    assert source.shared_source_sha256[name] == hashlib.sha256(module_path.read_bytes()).hexdigest()
    read_bytes = Path.read_bytes

    def changed_code(path):
        data = read_bytes(path)
        return data + b"\n# Changed verification implementation\n" if path == module_path else data

    monkeypatch.setattr(Path, "read_bytes", changed_code)
    with pytest.raises(ValueError, match="Futures research replay mismatch"):
        await futures.verify_futures_run(source)


async def test_evidence_without_the_internal_module_hash_is_rejected():
    source = await futures.run_futures_research(request())
    hashes = dict(source.shared_source_sha256)
    hashes.pop("backtesting/_futures_evidence.py")
    older = source.model_copy(update={"shared_source_sha256": hashes})
    with pytest.raises(ValueError, match="Futures research replay mismatch"):
        await futures.verify_futures_run(older)
