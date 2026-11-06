# Earn2Trade TCP25 evaluation rules register — Phase 1A

Reviewed: **2026-10-18**. Target: **TCP25, USD25,000, evaluation EOD stage**.
The user confirmed a **USD1,750 profit target** and a separate personal limit:
**one Mini OR up to ten Micros in aggregate, never both simultaneously**.
This supersedes the earlier intended target for this workflow; historical TCP25
and TCP50 sources, documentation and evidence remain unchanged.

This is public prospective research evidence, not assigned-account entitlement.
Positive firm qualification is **BLOCKED** where required evidence is unresolved.
Passing probability and trading edge are **UNKNOWN**. AI proposes, deterministic
rules validate, human decides. Trade and execution permission remain false.

## Sources and capture limitations

Official text was freshly checked during **2026-10-18T19:48:56Z–19:49:17Z**.
These bound the research pass, not individual request times or rule-effective
dates. The [source record](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/official-source-captures.json)
contains paraphrased findings and page dates. It is **not a raw HTML archive**;
its fact-record hashes do not authenticate origin bytes. The last four web
response displays were shortened. No historical chart was freshly downloaded or
given a new acquisition date. Public rules must be checked against the actual
purchase version and assigned terms before any account qualification.

| ID | Official source | Displayed date |
| --- | --- | --- |
| product | [TCP product, TCP25 Evaluation block](https://www.earn2trade.com/trader-career-path) | No revision date shown |
| overview | [Evaluation rules](https://help.earn2trade.com/en/articles/5941958-what-are-the-evaluation-rules) | 2026-07-06 |
| daily | [Daily-loss calculation](https://help.earn2trade.com/en/articles/3395926-how-is-my-daily-loss-calculated) | 2024-08-27 |
| drawdown | [EOD drawdown](https://help.earn2trade.com/en/articles/5372687-how-does-end-of-day-drawdown-work) | 2022-02-01 |
| consistency | [Consistency](https://help.earn2trade.com/en/articles/3849975-what-is-the-maintain-consistency-rule) | 2026-05-07 |
| hours | [Approved times](https://help.earn2trade.com/en/articles/3224526-are-there-any-restrictions-on-when-i-can-trade-in-my-evaluation-account) | 2025-11-13 |
| progression | [TCP progression](https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path) | 2026-07-06 |
| july-update | [Purchase-version update](https://www.earn2trade.com/blog/earn2trade-evaluation-rules-profit-split-update/) | Published 2026-07-06; updated 2026-07-10 |
| conduct | [Prohibited conduct](https://help.earn2trade.com/en/articles/9286647-prohibited-conduct-in-earn2trade-evaluations-and-in-the-livesim-live-trading-environment) | 2024-05-06 |
| copiers | [Completion and copier guidance](https://help.earn2trade.com/en/articles/6877364-what-happens-when-i-complete-my-evaluation) | 2026-07-06 |

## Firm requirements and explicit interpretations

VERIFIED below means supported public text or checked arithmetic, not assigned
terms, runtime readiness, source-price authentication or trading permission.
The machine-readable [rules register](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/rules-register.json)
records every rule, classification, source ID, code reference and unresolved item.

| Requirement | Status | Requirement / implementation interpretation |
| --- | --- | --- |
| Program, stage, capital | VERIFIED public | TCP25 evaluation; USD25,000. Product Evaluation block, not a funded growth-stage card. |
| Profit target | VERIFIED public | USD1,750 net profit; necessary but insufficient for completion. |
| Daily loss | VERIFIED public | USD550. Realized plus unrealized PnL and commissions; reaching -550 fails even if a later close recovers. |
| Trading day | VERIFIED interpretation | 17:00–17:00 CT maps to `America/Chicago`, including DST. A day reset is not permission through a market closure. |
| EOD drawdown | VERIFIED public | USD1,500. Closing high-water floor ratchets upward, never retreats, caps at starting balance; intraday equity touching the settled floor fails. |
| Initial floor | VERIFIED arithmetic | USD23,500 = 25,000 - 1,500; not an observed assigned platform threshold. |
| Floor synchronization | PARTIAL | Processing occurs during 16:00–17:00 CT. Wait for dashboard/platform agreement; assigned threshold/effective instant absent. |
| Minimum days | PARTIAL applicability | No fixed minimum for purchases on/after 2026-07-06. Actual purchase terms unconfirmed; do not invent a four-day hard minimum. |
| Consistency | VERIFIED public | Best day must be strictly below 30% of positive total PnL, including loss/recovery history. Concentration delays completion, not immediate failure. |
| Consistency at target | VERIFIED arithmetic | At USD1,750 total, best day must be below USD525; equality is insufficient. |
| Absolute firm ceiling | PARTIAL | Up to three standard contracts. This is not a starting allowance or a qualified ladder. |
| Micros | PARTIAL | MES/MNQ appear on the qualifying list; up to ten listed micros count as one standard. Exact mixed-root grouping/rounding and netting remain unresolved. |
| Progression | BLOCKED | Exact current bands, negative PnL, fractional-dollar gaps, profit/fee basis and downward transitions are not qualified. |
| Orders/exposure transitions | BLOCKED | Pending reservations, partial fills, reversals and protective/OCO treatment require evidence; no reduce-only exemption is inferred. |
| Hours | PARTIAL calendar | Flat positions and working orders by 15:50 CT until 17:00 CT; actual asset/holiday/early-close schedule still required. |
| News | VERIFIED public | News trading allowed. Any additional personal event filter remains a personal control. |
| Restricted activity | PARTIAL applicability | No copying, manipulation, exploitation, coordinated account/risk abuse or trading for others. Conditional AI wording is not affirmative permission for this workflow. |
| Instruments and costs | PARTIAL / UNKNOWN | MES/MNQ research scope; exact assigned permissions, margin, fees, quote coverage and realistic execution costs remain unqualified. |

Reuse [tcp25_rules and TCP25Policy](../../src/core/advisory/policy.py),
[EOD projection and session clock](../../src/core/advisory/evaluation.py), and
[observed-event replay](../../src/backtesting/evaluation.py). No production rule
date, amount, schema, calculation or confirmation flag is changed by Phase 1A.
Legacy `READY` on supplied hypothetical/confirmed evidence does not certify that
evidence. `rule_exact_verified=False` remains meaningful; synthetic PASS is
mechanics only. This checkpoint adds no runtime eligibility gate or permissions.

## Separate personal controls — documented, not implemented

| Aggregate gross open exposure | Personal-cap result only |
| --- | --- |
| Zero positions | WITHIN_CAP; no new trade is thereby authorized |
| One Mini and zero Micros | WITHIN_CAP |
| Zero Minis and up to ten Micros total | WITHIN_CAP |
| Six MES plus four MNQ | WITHIN_CAP; firm qualification still required |
| Any Mini together with any Micro | BLOCKED |
| Two Minis or eleven Micros | BLOCKED |
| Unknown/incomplete exposure | UNKNOWN; no positive capacity |

Count across positions, roots and directions without hedge netting. Intersect the
exclusive personal cap with **verified firm progression and financial limits**;
the stricter constraint wins. Unknown required firm evidence blocks positive
qualification even when the personal example is within cap. Do not replace this
intersection with a single standard-equivalent minimum that permits mixing.

The exact Mini symbol universe remains unresolved: the catalog includes NQ but
not ES. This personal cap supplies no new instrument entitlement. Pending-order
reservations are a separate future control, not a silent redefinition of open
exposure; protective orders must not be assumed harmless or reduce-only.
Existing <=1% risk rails, strategy loss pause and the 07:00–14:00 UTC personal
window remain separate controls, not firm requirements. No threshold is relaxed.

The [personal specification](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/personal-exposure-spec.json)
is **DOCUMENTED_NOT_IMPLEMENTED**, not loaded by the application. Current
`user_risk.py` still uses 50,000/3,000/1,100/2,000 and `user_policy.py` still uses
the old 20-Micro schema. Their unchanged tests prove legacy behavior only.

## Boundary verification and open questions

The [boundary matrix](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/boundary-matrix.json)
maps new/reused tests to rules. New cases use actual TCP25 amounts together:
target +/- one cent, strict consistency at target, nonpositive total history,
drawdown after a valid loss sequence without widening daily limits, combined
realized/open/commission loss, and spring/fall Chicago rollover/closing times.
All are **SYNTHETIC MECHANICS ONLY**. Final results, exact commands, failures and
preservation evidence are in the [verification receipt](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/verification.json).

Required clarifications remain: purchase/assigned terms; current ladder and its
boundary/accounting semantics; exposure transitions and exact Mini symbols;
historical sessions and synchronized platform floor; applicable fees/margin;
qualified data/intrabar evidence and advisory-use applicability. No inquiry,
purchase, service startup, new holdout access or forward run is part of this work.
