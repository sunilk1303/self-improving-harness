# E0 Results — Baseline Harness + Eval Harness Calibration

*Run date: 2026-07-17 · branch `feat/e0-baseline` · dataset seed 1303 (1,200 accounts, 24 months, 147 golden questions: 109 public / 38 private, 5 tripwires)*

## Configurations measured

| Manifest | Router | NL→SQL leg |
|---|---|---|
| `v0` (prod) | VQR-first | none — deterministic |
| `v3` (staging) | VQR-first | `azure-openai:gpt-5-mini`, api-version 2024-12-01-preview |

## Accuracy

| Slice | v0 | v3 | Δ |
|---|---|---|---|
| Public (109 q) | 0.826 | 0.963 | +13.8 pts |
| Private (38 q) | 0.868 | 0.895 | +2.6 pts |

- v0's accuracy equals VQR coverage exactly (90/109): every governed-path answer correct, every unrouted question a typed `no_route` limitation event. The measurement pipeline is clean.
- The gpt-5-mini leg recovered **15/19** unrouted public questions (79% on its route). Residual failures are structural, not model-quality: the federated doc-vs-SQL question (leg has no document access), the narrative facts question (synthesis not implemented), one churn multi-join, one tripwire.
- The public/private Δ gap (+13.8 vs +2.6) is slice-composition luck — the private slice drew proportionally more VQR-covered questions. This is the small-n stratum noise docs/04 predicts; it argues for stratified slice construction (E1 work), not for reading the private delta as "overfitting."

## A/A calibration (the headline E0 number)

6 runs of the same v3 manifest over the public slice (nondeterminism = the 19 LLM-routed questions only; run accuracies 0.963–0.982):

| Metric | Value |
|---|---|
| Gate false-accept rate (15 pairs, paired bootstrap, 1000 resamples) | **0.0** |
| Mean CI width | **0.0495** (~±2.5 pts) |

**Interpretation.** The gate never false-fires on identical manifests — good. But at one generation per question on 109 questions, the minimum reliably-detectable delta is ~2.5–3 pts, so the E0 target of "detect a 2-pt real change" is **not yet met**. Runner support for multiple generations per question and/or growing the public slice toward the 300-question spec is required before E3's gate verdicts are trustworthy at 2-pt granularity.

## E0 success-criteria scorecard

| Criterion | Status |
|---|---|
| Baseline ≥55% public, clean stratum breakdown | ✅ 0.826 — arguably *too easy*; harden the generator or expand non-VQR strata so the loop has honest headroom |
| A/A false-accept <5% | ✅ 0.0 |
| CI detects 2-pt delta at ≤3 generations/question | ❌ ~5-pt width at 1 generation → multi-generation scoring is the next eval-kit feature |
| Eval cost ≤$150/candidate | ✅ ~19 LLM calls/run, cents |
| ≥80% of sampled questions rated realistic by an analyst | ⬜ not yet done (needs a human review pass) |
| Rollback via label repoint demonstrated | ✅ manually (`repoint()`, ledger-logged); not yet CI-wired |

No kill criteria tripped.

## Operational findings

1. **DuckDB parameter binding is ~680× slower than inlined-literal INSERTs** (157s vs 0.23s for 14k rows). Generator uses `_bulk_insert`; do not revert to `executemany`.
2. **gpt-5-mini latency ≈ 19s/question** (reasoning model). A full public eval is ~6 min; 6-run A/A ~35 min. Gate economics in E1 must budget for this or use a faster deployment for cheap stages.
3. **A live billing failure crashed the first eval run** — now hardened: any LLM-leg failure degrades to a typed `no_answer` and the harness falls back to its VQR floor (the degradation principle, encountered in practice on day one).
4. Azure env quirk to fix locally: `AZURE_OPENAI_API_VERSION` (User scope) currently holds a deployment name; runs override it to `2024-12-01-preview` at process level.

## Update — expanded slice (359 questions) and the multi-generation finding

*Run 2026-07-17, seed 1303, slice grown to 258 public / 101 private (7 tripwires).*

| Slice | v0 | v3 | Notes |
|---|---|---|---|
| Public (258 q) | 0.733 | 0.919 | harder slice; more honest headroom than the 0.826 first cut |
| Private (101 q) | 0.683 | 0.901 | |

v3 public by stratum: single_table 1.00, multi_join 0.97, **narrative 0.60, federated 0.18**. The federated stratum (doc price vs invoiced average) is the hardest: the leg has no document access, so it can only answer the invoice half.

**Key finding — slice size did not close the detection gap.** A/A over 4 v3 runs at one generation gave false-accept rate 0.0 but mean CI width **0.0594 (~±3 pts)** — slightly *wider* than the 109-question slice (0.0495). Growing n added high-variance LLM-routed questions (federated/narrative), and per-question score variance, not n, dominates the noise floor. The lever is **multi-generation scoring**: an n-generation mean score has per-question variance ∝ 1/n, so the CI width should scale ≈ 1/√n. gens=3 is predicted to bring ~±3 pts down to ~±1.7 pts, meeting the 2-pt target — being confirmed empirically next.

## Recommended next steps (E1 entry)

1. ✅/⏳ Multi-generation scoring — built; gens=3 A/A confirmation in progress to verify the CI narrows below the 2-pt target.
2. Analyst realism review of a 30-question sample (the one open E0 criterion — needs a human).
3. ✅ (S1) E1 gate-discipline suite: `harness/gate/` + 10 labeled candidates scoring 10/10 at the static stage. S2–S4 and the fuller suite remain — see [e1-plan.md](e1-plan.md).
