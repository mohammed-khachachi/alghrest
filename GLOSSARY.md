# ALGHREST

Domain language for trading and research. Futures research evidence records
experimental findings without granting trading permission.

## Language

**Futures research evidence**:
Captured futures outcomes and the edge statistics, uncertainty estimates, and
chronological walk-forward folds derived from them.
_Avoid_: Trading approval, certified edge

**Path verification**:
Reproduction of captured futures decisions, fills, and outcomes from their source
inputs, with source checks and exact comparison against the captured evidence.
_Avoid_: Hash-only verification, summary-only verification

## Paper execution

**Accounting book**:
An explicitly identified set of opening balances, trades, positions and risk restrictions.
_Avoid_: Process, dashboard session

**Execution authorization**:
A recorded approval permitting one defined execution intent in one accounting book and venue account.
_Avoid_: An APPROVED message label, transport authentication

**Book halt**:
A restriction on new risk for one accounting book. Clearing it does not clear a global halt.
_Avoid_: Global emergency stop

**Global halt**:
A restriction on new risk for every accounting book, independent of each book's own restrictions.
_Avoid_: Book halt
