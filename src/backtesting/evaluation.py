"""Observed/hypothetical evaluation event replay, never order execution.

Cash, commissions and open equity are evaluated at every declared event. This
uses provided EOD policy/ladder/calendar evidence; it cannot authenticate its
completeness, unseen extrema, licensing or official account configuration.
"""

import hashlib
from datetime import date, datetime, time
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from backtesting.futures import _sha
from core.advisory.evaluation import (
    CHICAGO,
    EODFinancialState,
    initial_eod_state,
    project_eod_session,
    session_clock,
)
from core.advisory.models import CATALOG, Number, Price, UTCDateTime
from core.advisory.policy import EODRules, ProgressionSchedule, TradingCalendar
from core.advisory.selection import Evidence, Nonnegative
from core.advisory.strategies import Digest, Identity, Reference


class EvaluationEvent(Evidence):
    id: Identity
    at: UTCDateTime
    kind: Literal[
        "OPEN", "MARK", "CLOSE", "WORKING_ORDER", "CLEAR_ORDER", "SESSION_END", "FLOOR_SYNC"
    ]
    position_id: Identity | None = None
    order_id: Identity | None = None
    instrument_id: str | None = None
    contract: str | None = None
    side: Literal["BUY", "SELL"] | None = None
    quantity: StrictInt | None = Field(default=None, ge=1)
    price: Price | None = None
    commission_usd: Nonnegative | None = None
    minimum_balance: Number | None = None
    confirmed: StrictBool | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        fields = {k for k, v in self.model_dump().items() if v is not None} - {"id", "at", "kind"}
        required = {
            "OPEN": {
                "position_id",
                "instrument_id",
                "contract",
                "side",
                "quantity",
                "price",
                "commission_usd",
            },
            "MARK": {"position_id", "price"},
            "CLOSE": {"position_id", "price", "commission_usd"},
            "WORKING_ORDER": {"order_id", "instrument_id", "contract", "quantity", "side"},
            "CLEAR_ORDER": {"order_id"},
            "SESSION_END": set(),
            "FLOOR_SYNC": {"minimum_balance", "confirmed"},
        }[self.kind]
        if fields != required and not (self.kind == "OPEN" and fields == required | {"order_id"}):
            raise ValueError("Evaluation event fields must match its exact kind")
        if self.instrument_id is not None:
            instrument = CATALOG.get(self.instrument_id)
            if instrument is None or not instrument.valid_contract(self.contract):
                raise ValueError("Evaluation events require a dated catalog futures contract")
        return self


class MarginCapacity(Evidence):
    id: Identity
    instrument_id: str
    known_at: UTCDateTime
    confirmed: StrictBool
    maximum_total_contracts: StrictInt = Field(ge=0)
    source_reference: Reference

    @model_validator(mode="after")
    def market(self) -> Self:
        if self.instrument_id not in CATALOG or CATALOG[self.instrument_id].futures_spec is None:
            raise ValueError("Margin capacity requires a catalog futures market")
        return self


class EvaluationTape(Evidence):
    id: Identity
    version: Identity
    origin: Literal["synthetic", "reported"]
    source_reference: Reference
    rules: EODRules
    policy_confirmed: StrictBool = False
    initially_flat: Literal[True] = True
    fills_complete: StrictBool = False
    intraday_extrema_complete: StrictBool = False
    progression: ProgressionSchedule | None = None
    calendar: TradingCalendar | None = None
    margin: tuple[MarginCapacity, ...] = Field(default=(), max_length=10000)
    events: tuple[EvaluationEvent, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def chronology(self) -> Self:
        if len({e.id for e in self.events}) != len(self.events) or any(
            a.at > b.at for a, b in zip(self.events, self.events[1:], strict=False)
        ):
            raise ValueError("Tape event identities must be unique and time ordered")
        keys = [(m.instrument_id, m.known_at) for m in self.margin]
        if len(keys) != len(set(keys)):
            raise ValueError("Margin capacity revisions cannot be ambiguous")
        return self


class SimulatedPosition(Evidence):
    id: Identity
    instrument_id: str
    contract: str
    side: Literal["BUY", "SELL"]
    quantity: StrictInt = Field(ge=1)
    entry_price: Price
    mark_price: Price


class EvaluationStep(Evidence):
    event_id: Identity
    at: UTCDateTime
    session_date: date
    cash_balance: Number
    unrealized_pnl: Number
    equity: Number
    session_net_pnl: Number
    session_lowest_pnl: Number
    financial: EODFinancialState
    positions: tuple[SimulatedPosition, ...]
    working_order_ids: tuple[str, ...]
    standard_equivalents: Nonnegative
    outcome: Literal["PASS", "CONTINUE", "FAIL", "CENSORED"]
    breaches: tuple[str, ...]
    unknowns: tuple[str, ...]
    consistency_met: StrictBool
    targets_met: StrictBool


def _source_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _unrealized(positions: dict[str, SimulatedPosition]) -> Decimal:
    return sum(
        (
            (p.mark_price - p.entry_price)
            * p.quantity
            * CATALOG[p.instrument_id].point_value
            * (1 if p.side == "BUY" else -1)
            for p in positions.values()
        ),
        Decimal(0),
    )


def _exposure_checks(
    tape: EvaluationTape,
    positions: dict[str, SimulatedPosition],
    equity: Decimal,
    at: datetime,
    breaches: set[str],
    unknowns: set[str],
) -> Decimal:
    rules = tape.rules
    equivalents = sum(
        (
            Decimal(p.quantity)
            / (rules.micros_per_standard if p.instrument_id in rules.micro_markets else 1)
            for p in positions.values()
        ),
        Decimal(0),
    )
    if equivalents > rules.maximum_standard_contracts:
        breaches.add("maximum_position_size")
    progression = tape.progression
    if positions:
        if (
            progression is None
            or not progression.confirmed
            or progression.known_at > at
            or (progression.policy_id, progression.policy_version) != (rules.id, rules.version)
            or progression.bands[0].minimum_equity > rules.starting_balance - rules.maximum_drawdown
            or any(
                b.maximum_standard_contracts > rules.maximum_standard_contracts
                for b in progression.bands
            )
        ):
            unknowns.add("unknown_progression_schedule")
        else:
            band = next(
                (b for b in reversed(progression.bands) if equity >= b.minimum_equity), None
            )
            if band is None or equivalents > band.maximum_standard_contracts:
                breaches.add("progression_ladder_size")
        for root in {p.instrument_id for p in positions.values()}:
            capacity = max(
                (m for m in tape.margin if m.instrument_id == root and m.known_at <= at),
                key=lambda m: m.known_at,
                default=None,
            )
            if capacity is None or not capacity.confirmed:
                unknowns.add("unknown_margin_capacity")
            elif (
                sum(p.quantity for p in positions.values() if p.instrument_id == root)
                > capacity.maximum_total_contracts
            ):
                unknowns.add("margin_capacity_conflict")
    return equivalents


def _simulate(tape: EvaluationTape) -> tuple[EvaluationStep, ...]:
    rules = tape.rules
    prior = initial_eod_state(rules)
    session_prior = prior
    cash = prior.balance
    positions: dict[str, SimulatedPosition] = {}
    orders: dict[str, EvaluationEvent] = {}
    used_positions: set[str] = set()
    used_orders: set[str] = set()
    day: date | None = None
    low = Decimal(0)
    traded = False
    finalized = False
    floor_synced = False
    unknowns: set[str] = set()
    if not tape.policy_confirmed:
        unknowns.add("unconfirmed_evaluation_policy")
    if not tape.fills_complete:
        unknowns.add("incomplete_fill_history")
    if not tape.intraday_extrema_complete:
        unknowns.add("unverified_intraday_extrema")
    steps: list[EvaluationStep] = []
    breaches: set[str] = set()
    for event in tape.events:
        clock = session_clock(event.at)
        event_day = date.fromisoformat(clock["session_date"])
        if day is not None and event_day != day:
            if not finalized:
                # Missing settlement must not invent a reset or lower a trailing floor.
                last = steps[-1]
                steps[-1] = last.model_copy(
                    update={
                        "outcome": "CENSORED",
                        "unknowns": tuple(
                            sorted(set(last.unknowns) | {"missing_session_finalization"})
                        ),
                    }
                )
                break
            low, traded, finalized = Decimal(0), False, False
            session_prior = prior
        day = event_day
        rules_known = tape.policy_confirmed and rules.known_at <= event.at
        if not rules_known:
            unknowns.add("unknown_policy_at_event")
        calendar = tape.calendar
        window = None
        if (
            calendar is None
            or not (calendar.confirmed and calendar.complete)
            or calendar.known_at > event.at
            or not calendar.coverage_start <= event.at < calendar.coverage_end
        ):
            unknowns.add("unknown_trading_calendar")
        previous_exposure = bool(positions or orders)
        price_root = event.instrument_id
        roots = {p.instrument_id for p in positions.values()} | {
            o.instrument_id for o in orders.values()
        }
        if event.instrument_id:
            roots.add(event.instrument_id)
        if (
            calendar is not None
            and calendar.confirmed
            and calendar.complete
            and calendar.known_at <= event.at
            and calendar.coverage_start <= event.at < calendar.coverage_end
        ):
            for root in roots:
                if root not in calendar.covered_markets:
                    unknowns.add("uncovered_calendar_market")
                    continue
                window = next(
                    (
                        w
                        for w in calendar.windows
                        if w.instrument_id == root and w.start <= event.at < w.end
                    ),
                    None,
                )
                root_exposed = any(p.instrument_id == root for p in positions.values()) or any(
                    o.instrument_id == root for o in orders.values()
                )
                if root_exposed and (window is None or event.at >= window.flat_by):
                    breaches.add("flat_deadline_or_exchange_closed")
                if event.kind in {"OPEN", "CLOSE", "WORKING_ORDER"} and (
                    window is None or event.at >= window.flat_by
                ):
                    breaches.add("trade_outside_calendar_window")
        if bool(clock["regular_hours_closed"]) and (
            previous_exposure or event.kind in {"OPEN", "CLOSE", "WORKING_ORDER"}
        ):
            breaches.add("outside_regular_evaluation_hours")
        if event.kind in {"OPEN", "WORKING_ORDER"} and not floor_synced:
            unknowns.add("floor_not_synchronized_before_entry")
        if event.kind in {"OPEN", "WORKING_ORDER"}:
            assert (
                event.instrument_id is not None
                and event.contract is not None
                and event.quantity is not None
                and event.side is not None
            )
            if event.instrument_id not in rules.eligible_markets:
                breaches.add("ineligible_market")
            if event.kind == "WORKING_ORDER":
                assert event.order_id is not None
                if event.order_id in used_orders:
                    raise ValueError("Working order identity reused")
                used_orders.add(event.order_id)
                orders[event.order_id] = event
            else:
                assert (
                    event.position_id is not None
                    and event.price is not None
                    and event.commission_usd is not None
                )
                if event.position_id in used_positions:
                    raise ValueError("Position identity reused")
                if event.order_id is not None:
                    working = orders.pop(event.order_id, None)
                    if working is None or (
                        working.instrument_id,
                        working.contract,
                        working.quantity,
                        working.side,
                    ) != (event.instrument_id, event.contract, event.quantity, event.side):
                        raise ValueError("Opening fill must match its working order")
                used_positions.add(event.position_id)
                positions[event.position_id] = SimulatedPosition(
                    id=event.position_id,
                    instrument_id=event.instrument_id,
                    contract=event.contract,
                    side=event.side,
                    quantity=event.quantity,
                    entry_price=event.price,
                    mark_price=event.price,
                )
                cash -= event.commission_usd
                traded = True
        elif event.kind in {"MARK", "CLOSE"}:
            assert event.position_id is not None and event.price is not None
            position = positions.get(event.position_id)
            if position is None:
                raise ValueError("Missing observed position for mark/close")
            price_root = position.instrument_id
            positions[event.position_id] = position.model_copy(update={"mark_price": event.price})
            if event.kind == "CLOSE":
                assert event.commission_usd is not None
                # A closing fill observes the price while the position still exists.
                # It cannot conceal a realtime ladder breach by becoming flat.
                close_equity = cash + _unrealized(positions)
                _exposure_checks(tape, positions, close_equity, event.at, breaches, unknowns)
                cash += (event.price - position.entry_price) * position.quantity * CATALOG[
                    position.instrument_id
                ].point_value * (1 if position.side == "BUY" else -1) - event.commission_usd
                positions.pop(event.position_id)
        elif event.kind == "CLEAR_ORDER":
            if orders.pop(event.order_id or "", None) is None:
                raise ValueError("Missing observed working order")
        elif event.kind == "FLOOR_SYNC":
            floor_synced = event.confirmed is True and event.minimum_balance == prior.floor
            if not floor_synced:
                unknowns.add("floor_synchronization_mismatch")
        elif event.kind == "SESSION_END":
            if finalized:
                raise ValueError("Session finalized twice")
            local = event.at.astimezone(CHICAGO)
            if not time(16) <= local.time() < time(17):
                raise ValueError("Settlement must be in the Chicago 16-17 processing window")
            if positions or orders:
                breaches.add("nonflat_session_finalization")
            finalized = True
        unrealized = _unrealized(positions)
        equity = cash + unrealized
        net = equity - session_prior.balance
        low = min(low, net)
        projection = project_eod_session(
            rules, session_prior, net_pnl=net, lowest_pnl=low, traded=traded, closed=finalized
        )
        if projection.daily_loss_breached:
            breaches.add("daily_loss_boundary")
        if projection.drawdown_breached:
            breaches.add("drawdown_boundary")
        equivalents = _exposure_checks(tape, positions, equity, event.at, breaches, unknowns)
        if event.price is not None:
            assert price_root is not None
            if event.price % CATALOG[price_root].tick_size:
                raise ValueError("Observed futures fill/mark is off tick")
        if event.kind == "SESSION_END":
            prior = projection.financial
            floor_synced = False
        terminal_fail = bool(breaches) and rules_known and tape.fills_complete
        fully_known = not unknowns
        pass_now = (
            fully_known
            and finalized
            and floor_synced
            and not positions
            and not orders
            and projection.targets_met
            and not breaches
        )
        outcome: Literal["PASS", "CONTINUE", "FAIL", "CENSORED"] = (
            "FAIL"
            if terminal_fail
            else "CENSORED" if unknowns else "PASS" if pass_now else "CONTINUE"
        )
        steps.append(
            EvaluationStep(
                event_id=event.id,
                at=event.at,
                session_date=day,
                cash_balance=cash,
                unrealized_pnl=unrealized,
                equity=equity,
                session_net_pnl=net,
                session_lowest_pnl=low,
                financial=projection.financial,
                positions=tuple(positions.values()),
                working_order_ids=tuple(orders),
                standard_equivalents=equivalents,
                outcome=outcome,
                breaches=tuple(sorted(breaches)),
                unknowns=tuple(sorted(unknowns)),
                consistency_met=projection.consistency_met,
                targets_met=projection.targets_met,
            )
        )
        if outcome in {"FAIL", "PASS"}:
            break
    return tuple(steps)


def _replay(tape: EvaluationTape) -> tuple[EvaluationStep, ...]:
    with localcontext() as context:
        context.prec = 80
        return _simulate(tape)


class EvaluationSimulation(Evidence):
    algorithm_version: Literal["observed-eod-events-v1"] = "observed-eod-events-v1"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    rule_exact_verified: Literal[False] = False
    tape: EvaluationTape
    tape_sha256: Digest
    implementation_sha256: Digest
    shared_source_sha256: dict[str, Digest]
    steps: tuple[EvaluationStep, ...]
    outcome: Literal["PASS", "CONTINUE", "FAIL", "CENSORED"]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def reproduce(self) -> Self:
        if (
            self.tape_sha256 != _sha(self.tape.model_dump(mode="json"))
            or self.implementation_sha256 != _source_digest()
            or self.shared_source_sha256 != _shared_sources()
        ):
            raise ValueError("Evaluation simulation source/implementation mismatch")
        expected = _replay(self.tape)
        if self.steps != expected or not expected or self.outcome != expected[-1].outcome:
            raise ValueError("Evaluation event checks must reproduce the complete tape prefix")
        return self


def _shared_sources() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {
        f: hashlib.sha256((root / f).read_bytes()).hexdigest()
        for f in (
            "core/advisory/evaluation.py",
            "core/advisory/policy.py",
            "core/advisory/models.py",
        )
    }


def simulate_evaluation(tape: EvaluationTape) -> EvaluationSimulation:
    tape = EvaluationTape.model_validate(tape.model_dump(warnings=False))
    steps = _replay(tape)
    return EvaluationSimulation(
        tape=tape,
        tape_sha256=_sha(tape.model_dump(mode="json")),
        implementation_sha256=_source_digest(),
        shared_source_sha256=_shared_sources(),
        steps=steps,
        outcome=steps[-1].outcome,
    )


def verify_evaluation_simulation(value: EvaluationSimulation) -> EvaluationSimulation:
    return EvaluationSimulation.model_validate(value.model_dump(warnings=False))
