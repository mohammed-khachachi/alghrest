"""Own futures evidence composition without retaining trust between requests.

Public entry points remain in futures and validation. Only this private module
passes newly generated or exactly replayed outcomes to the summary builders;
every entry point accepting captured evidence verifies its path afresh.
"""

from decimal import localcontext

import numpy as np

from backtesting import futures, validation
from backtesting.path_risk import LossStreakConfig


async def research(inputs: futures.FuturesResearchInput) -> futures.FuturesResearchRun:
    inputs = futures.FuturesResearchInput.model_validate(inputs.model_dump(warnings=False))
    with localcontext() as context:
        context.prec = 80
        return await futures._run(inputs)


async def verify_run(value: futures.FuturesResearchRun) -> futures.FuturesResearchRun:
    value = futures.FuturesResearchRun.model_validate(value.model_dump(warnings=False))
    replayed = await research(value.inputs)
    if value.model_dump(mode="json") != replayed.model_dump(mode="json"):
        raise ValueError("Futures research replay mismatch")
    return replayed


def _edge(
    source: futures.FuturesResearchRun, configuration: LossStreakConfig
) -> futures.FuturesEdgeStudy:
    """Consume only outcomes generated or replayed by this request's call chain."""
    return futures.FuturesEdgeStudy(
        source=source,
        source_sha256=futures._sha(source.model_dump(mode="json")),
        configuration=configuration,
        partitions=futures._edge_partitions(source, configuration),
    )


async def edge_analysis(
    source: futures.FuturesResearchRun, *, configuration: LossStreakConfig
) -> futures.FuturesEdgeStudy:
    configuration = LossStreakConfig.model_validate(configuration.model_dump(warnings=False))
    return _edge(await verify_run(source), configuration)


async def verify_edge(value: futures.FuturesEdgeStudy) -> futures.FuturesEdgeStudy:
    value = futures.FuturesEdgeStudy.model_validate(value.model_dump(warnings=False))
    replayed = await edge_analysis(value.source, configuration=value.configuration)
    if value.model_dump(mode="json") != replayed.model_dump(mode="json"):
        raise ValueError("Futures edge replay mismatch")
    return replayed


def _uncertainty(
    source: futures.FuturesEdgeStudy, configuration: validation.MeanBootstrapConfig
) -> validation.FuturesUncertaintyStudy:
    """Derive uncertainty from this request's already verified source outcomes."""
    return validation.FuturesUncertaintyStudy(
        source=source,
        source_sha256=futures._sha(source.model_dump(mode="json")),
        implementation_sha256=validation._implementation_digest(),
        numpy_version=np.__version__,
        configuration=configuration,
        partitions=validation._uncertainty_parts(source, configuration),
    )


async def uncertainty_analysis(
    source: futures.FuturesEdgeStudy, *, configuration: validation.MeanBootstrapConfig
) -> validation.FuturesUncertaintyStudy:
    configuration = validation.MeanBootstrapConfig.model_validate(
        configuration.model_dump(warnings=False)
    )
    return _uncertainty(await verify_edge(source), configuration)


async def verify_uncertainty(
    value: validation.FuturesUncertaintyStudy,
) -> validation.FuturesUncertaintyStudy:
    value = validation.FuturesUncertaintyStudy.model_validate(value.model_dump(warnings=False))
    replayed = await uncertainty_analysis(value.source, configuration=value.configuration)
    if value.model_dump(mode="json") != replayed.model_dump(mode="json"):
        raise ValueError("Futures uncertainty replay mismatch")
    return replayed


async def walk(
    inputs: futures.FuturesResearchInput,
    *,
    plan: validation.FuturesWalkPlan,
    configuration: validation.MeanBootstrapConfig,
) -> validation.FuturesWalkStudy:
    inputs = futures.FuturesResearchInput.model_validate(inputs.model_dump(warnings=False))
    plan = validation.FuturesWalkPlan.model_validate(plan.model_dump(warnings=False))
    configuration = validation.MeanBootstrapConfig.model_validate(
        configuration.model_dump(warnings=False)
    )
    validation._check_walk(inputs, plan)
    folds = []
    for window in plan.windows:
        source = await research(validation._fold_input(inputs, window))
        edge = _edge(source, configuration.sampling)
        uncertainty = _uncertainty(edge, configuration)
        folds.append(validation.FuturesWalkFold(window_id=window.id, uncertainty=uncertainty))
    return validation.FuturesWalkStudy(
        inputs=inputs, plan=plan, configuration=configuration, folds=tuple(folds)
    )


async def verify_walk(value: validation.FuturesWalkStudy) -> validation.FuturesWalkStudy:
    value = validation.FuturesWalkStudy.model_validate(value.model_dump(warnings=False))
    replayed = await walk(value.inputs, plan=value.plan, configuration=value.configuration)
    if value.model_dump(mode="json") != replayed.model_dump(mode="json"):
        raise ValueError("Futures walk-forward replay mismatch")
    return replayed
