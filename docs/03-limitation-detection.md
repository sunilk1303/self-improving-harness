# Limitation Detection

The brief's first requirement — "the system should look for its current limitations" — is the easiest place to fool yourself. An LLM asked "what are your limitations?" produces plausible introspection uncorrelated with its actual failure modes. So the governing rule:

> **Limitations are typed, machine-detected events with evidence attached — never the model's self-report.** Detectors run in the observability/control plane the agent cannot modify, and the detector's own health metric is *coverage of independently-verified failures*, never "number of limitations reported" — so the system can never look better by going blind.

Every detector emits a `LimitationEvent {type, evidence_trace_ids[], affected_seam, frequency, first_seen, cost_of_failure_estimate, blocked_on}` into the Limitation Ledger, where it opens a double-entry *liability* (see [02-architecture.md](02-architecture.md)).

## Detector battery

### 1. Execution detectors (hard failures)
SQL errors, statement timeouts, empty result sets, EXPLAIN cost-gate rejections, schema-binding failures — harvested from traces with full context (question, retrieved schema, emitted SQL). Classified by a taxonomy mapped to pipeline *seams* (routing / schema retrieval / SQL generation / execution / synthesis) using trajectory-level scoring, so improvements route to the right subsystem.

### 2. Metric-fallback counter (coverage gaps — the highest-yield signal)
Every time the router falls back from a governed named metric or verified query to freshly generated SQL, that is a coverage-gap event: "metric X missing from the semantic layer." Nightly embedding-clustering (HDBSCAN) of these events yields a **demand-ranked backlog** of candidate verified queries and metric definitions — the improvement backlog writes itself from real usage, with evidence traces pre-attached for the eventual human reviewer. This matters because the fix (a proposed metric definition or verified query) has a natural T2 human gate, and because semantic-layer coverage is the single strongest accuracy lever in the published evidence (dbt: 83% vs ~40%).

### 3. Grounding detector (silent wrong answers, part 1)
Post-hoc numeric-claim extraction from synthesized insights, reconciled by *independently re-executing* the tagged queries. Mismatch → synthesis/reasoning limitation. This is mechanical, not judged.

### 4. Disagreement detector (silent wrong answers, part 2)
For questions answerable by two routes (two sources, or metric-vs-SQL), sampled dual-execution; divergence → routing or join-path limitation.

### 5. Ambiguity detector (the Goodhart hot zone)
When a business noun ("revenue", "active user") resolves to conflicting definitions across the semantic layer, retrieved documents, or past answers — or when the same metric term produced different SQL lineages — the agent computes **all plausible interpretations, labeled** (the *ambiguity tax*), and the numeric divergence auto-files a `MetricClarification` HITL request with priority proportional to the divergence. The loop is **forbidden** from resolving metric ambiguity by optimizing whatever is measurable. Resolved definitions accumulate in an **ambiguity ledger** — typed records of contested nouns with candidate definitions, owning teams, and resolution status, consulted at answer time — so disambiguation is a governed, improving asset rather than a queue of tickets.

### 6. Drift sentinels
- Nightly `information_schema` diff against the semantic model and skill preconditions (schema drift breaks skills — triggers re-certification probes).
- Corpus freshness deltas and coverage-gap analysis of incoming question embeddings vs indexed content (the "freshness gap" — stale chunks outranking re-published docs — is the most common silent RAG failure; ~73% of failed enterprise RAG deployments trace to knowledge-base operations, not models).
- ACL-fidelity probes: a permission-widening result is a **security incident**, not a limitation.
- Hourly canary queries per data source with drift alerting.

### 7. Human signals
Thumbs-down, analyst corrections (each becomes a permanent golden candidate after human confirmation), clarification-loop frequency per topic, and analyst-filed limitations. Shadow-mode disagreements with what the human eventually did.

### 8. Evaluation-infeasibility detector
"We cannot backtest this recommendation class" or "no outcome data access for this objective" is itself a first-class limitation — it files a typed `DataAccessScope` request with a business-impact estimate. Likewise the counterfactual gap probe: for each objective, periodically ask "what data would materially change the top recommendation?" and check whether the harness can reach it; unreachable-but-material data is a missing-access limitation for a human to resolve.

### 9. Examiner (phase 2 — active adversarial mining)
Everything above is reactive. The Examiner *hunts*: it mutates real analyst questions along known failure axes (NULL semantics — `NOT IN` + NULL returns zero rows; fan-out join inflation; timezone boundaries; cents-vs-dollars; ambiguous nouns; stale documents), validates each candidate kill by executing ground truth itself, and files confirmed kills as limitation records + permanent golden/tripwire cases. This targets the worst failure class in enterprise data agents — **queries that execute cleanly and return wrong numbers** — which no user complaint will ever surface.

## Keeping the detectors honest

Three mechanisms, because the detector layer is itself an optimization target:

1. **Double-entry liabilities.** A limitation can only close via confirmed post-deploy symptom-rate drop, explicit human waiver with reason code, or aged expiry that reopens at higher severity. Under-reporting cannot masquerade as improvement.
2. **Fault-injection recall audits.** A scheduled harness plants known defects — a poisoned canary document, a renamed column in a sandbox replica, a deliberately wrong aggregate — and scores whether the detectors catch them. Detector *recall* is a dashboarded metric; the limitation detector is evaluated exactly like the agent it monitors. This also protects the trust ladder, whose auto-widening is only as trustworthy as the regression detectors feeding it.
3. **Volume-drop alarms.** A sudden drop in detector volume triggers an alert, not a celebration.

## From limitation to improvement

Each limitation type maps to a preferred improvement operator (and its tier):

| Limitation class | Operator | Tier |
|------------------|----------|------|
| Recurring failed SQL pattern | Playbook delta / prompt evolution (GEPA) | T0/T1 |
| Metric-fallback cluster | Proposed verified query or metric definition | T2 |
| Retrieval miss / freshness gap | Retrieval params, chunking config, corpus re-index request | T1 |
| Repeated successful ad-hoc pattern (≥3 uses) | Mint parameterized skill → MCP tool | T2 |
| Ambiguous metric | `MetricClarification` to a human — never self-resolved | HITL |
| Missing data access / credentials | `DataAccessScope` / `CredentialGrant` request — agent cannot mint access | HITL |
| Missing validator / connector capability | Agent-authored code, offline campaign only | T3 |
| Objective unclear | `ObjectiveDisambiguation` with candidate interpretations + divergent numbers attached | HITL |

The scheduler ([02-architecture.md](02-architecture.md)) decides *which* liability to work next by lineage survival, not by immediate eval delta.
