# Protocol Specification: Cross-Enterprise Semantic Mapping

**Version:** 1.0.0
**Phase:** 10 (Identity & Normalization Layer)

## Abstract
No two independent accounting systems share identical master data. A Seller may invoice `SKU: BOX-APPLE-10`, while the Buyer tracks it locally as `SKU: APL-F-10KG`. 

The Semantic Mapping layer acts as a version-controlled translation boundary between the generic Canonical Transaction (Phase 1) and the localized Vouch Accounting Engine. It strictly prevents ML/heuristics from guessing mapping during critical operations by forcing all automated predictions through an explicit, version-controlled approval state.

## Core Directives
1. **Never mutate historical translations:** If `SKU-A` mapped to `SKU-B` in Version 1, but is updated to map to `SKU-C` in Version 2, all transactions committed during Version 1 MUST continue resolving to `SKU-B`.
2. **Deterministic Resolution:** A CRDT `evaluate_state()` operation must yield the exact same ledger accounts regardless of when it is recalculated. It does this by binding the `mapping_version` to the `CanonicalTransaction` state.
3. **Uncertainty Barrier:** Machine Learning or Heuristic algorithms may only *propose* mappings (`Confidence = ML_PREDICTED`, `State = PENDING`). A deterministic accounting rule or human action must transition it to `APPROVED` before it can be utilized in a transaction merge.

## Semantic Resolution Flow
Foreign Payload (e.g., Tally/Zoho)
      ↓
Schema Detection
      ↓
`MappingResolutionEngine` (Queries `EntityMapping` & `ProductMapping` tables)
      ↓
If match is `APPROVED` at `mapping_version`:
      ↓
Returns Local Vouch Identity (Local Item ID, Local Account ID, Local Supplier ID)
      ↓
Generates `AccountingOperation`
