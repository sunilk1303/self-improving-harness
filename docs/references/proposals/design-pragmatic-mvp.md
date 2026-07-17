# Churn-Lens: a 6-week self-improving insights harness with ground-truth-by-construction evals

> Design lens: **pragmatic MVP**. A founding-engineer lens: the smallest end-to-end loop that demonstrably self-improves in 6 weeks.
>
> One of four independent design proposals generated during the design program. The synthesized architecture in `docs/` merges the winning proposal with grafts from the other three.

## Thesis

The fastest honest signal comes from making the evaluator cheap and unGoodhartable, not from making the improver clever: generate the synthetic business data from a parameterized script whose planted parameters ARE the hidden answers, so the private eval set is infinitely rotatable and memorization-proof. On top of that, run the smallest proven loop — trace-driven limitation detection, config-only improvement surface (playbook deltas, prompt versions, verified queries), staged public/private gate, Git-manifest deploy with one-command rollback — and treat everything code-level as deferred. The bet: on one Postgres + doc store + vector DB stack with a "reduce churn" objective, an unattended week of this loop moves private golden-set accuracy by a statistically defensible delta, which is the production-feasibility evidence the owner actually needs.

## Architecture

Seven named components, all in one docker-compose:

1. TASK AGENT ("Scout") — a LangGraph state machine with 4 DSPy-modularized stages: Router (question -> SQL path | doc-RAG path | hybrid), SQLGen (NL->SQL over Postgres, sqlglot AST validation + EXPLAIN cost gate pre-execution), Retriever (hybrid BM25+dense over Qdrant, docs ingested from a local MinIO bucket), Synthesizer (grounded narrative answer with numeric claims tagged to the queries that produced them). Scout reads its config from a pinned HARNESS MANIFEST and retrieves from the Playbook and Skill Registry at runtime. Read-only scoped Postgres credentials; no write path anywhere.

2. HARNESS MANIFEST — a Git-versioned lockfile (manifest.yaml) pinning: prompt version IDs (Langfuse), playbook version, skill-registry version, retrieval params, model IDs. The manifest is the atomic deploy/rollback unit; production = a label pointing at a commit SHA. Rollback = repoint label + cache invalidation.

3. REFLECTOR ("Coroner") — a nightly sleep-time job that reads the day's OTel traces from Langfuse and emits typed LimitationRecords into the Limitation Ledger (Postgres table): {type: sql_error | empty_result | eval_fail | user_correction | metric_fallback | schema_drift | ambiguous_metric, evidence_trace_ids[], frequency, severity}.

4. PROPOSER ("Tinker") — picks one limitation per cycle via the ledger's bandit scheduler, drafts exactly ONE change as a Git diff against the manifest repo (playbook delta, prompt mutation via GEPA-lite reflection, verified-query candidate, or skill template), and opens a PR with evidence attached. Tinker cannot merge, cannot touch the eval service, policy files, or logger — enforced by repo permissions + an OPA-lite policy check in CI, not by prompts.

5. EVAL SERVICE ("Bench") — a separate process, separate DB role, separate repo the agent cannot read. Holds the frozen data snapshot, the public golden slice, the private slice, and the frozen different-provider judge (e.g., Gemini Flash pinned version, rubric-based). Exposes one API: submit(manifest_sha) -> {public_scores, accept|reject}. Never returns private numbers (Ladder-style thresholded reporting).

6. GATEKEEPER — CI pipeline on the manifest repo: static checks (sqlglot lint, policy classification of the diff into Tier 0/1/2) -> sandbox replay (candidate manifest answers 20 replayed questions against the snapshot in a container with no egress) -> public slice eval -> Bench private accept/reject with paired bootstrap. Tier 0 auto-merges on green; Tier 1 auto-merges on green + private accept; Tier 2 parks in the HITL queue.

7. AUDIT LOGGER + HITL QUEUE ("Clerk") — an append-only, SHA-256 hash-chained events table in a Postgres schema the agent role cannot INSERT into (only the logger service can); every diagnosis, proposal, gate decision, merge, label move, and approval is an event referencing trace IDs and commit SHAs. The HITL queue is a table + a ~200-line FastAPI/HTMX page showing diff + evidence + "what could go wrong," requiring a selected reason to approve. Blocked improvement branches are parked LangGraph checkpoints resumed by the approval webhook; Scout keeps serving on the unmodified manifest meanwhile.

Data stack: Postgres 16 (synthetic SaaS subscription business: accounts, plans, invoices, support tickets, usage events, churn labels), MinIO folder of ~200 generated markdown docs (pricing policy, metric definitions, product notes — some deliberately stale/conflicting), Qdrant for embeddings. One `docker compose up`.

## Improvement surface (what the system may modify about itself)

Tiered, config-only. Everything is a human-readable text diff in Git; nothing self-modifies live process code.

TIER 0 — auto-apply, log-only (ITIL "standard changes"): (a) Playbook delta items, ACE-style append/merge with dedup, never monolithic rewrites (e.g., "invoices.amount is cents, not dollars"; "join accounts->tickets fans out — aggregate tickets first"); (b) retrieval few-shot examples from user-confirmed Q->SQL pairs; (c) glossary synonym entries.

TIER 1 — auto-apply after full gate (public + private accept): (a) prompt versions for the four Scout stages (GEPA-lite: Tinker reads failure traces, proposes targeted prompt mutations offline); (b) retrieval parameters (k, hybrid weights, reranker on/off); (c) router policy table updates (which question class -> which source).

TIER 2 — HITL-mandatory: (a) promoting a query to the Verified Query Repository (served verbatim thereafter — codifies business logic, so a human signs it); (b) metric definitions ("churn = no active subscription 30 days post-expiry") — always human, because ambiguous metrics are the worst Goodhart surface; (c) new parameterized skills (Voyager-style SQL templates minted from ≥3 successful uses, registered as tools) — new-tool admission is the tool-poisoning surface; (d) any data-access or credential request.

EXPLICITLY OUT OF SURFACE (structurally, not by instruction): the eval service, the policy/CI config, the audit logger, the golden sets, Scout's Python code, model weights. The DGM log-fabrication episode is why these live outside the agent's writable repo scope.

## Improvement loop

TRIGGER: (a) nightly cron (sleep-time cycle, off the serving path); (b) immediate on hard failures ≥3 occurrences/day of the same signature; (c) weekly deeper GEPA prompt-evolution run. Per-cycle spend cap: $10 of API tokens (evidence: GEPA-class runs cost $2-10).

STEP 1 — DETECT: Coroner scans traces, folds new evidence into the Limitation Ledger, updates each limitation-type arm's stats.

STEP 2 — SELECT: bandit scheduler picks one limitation: score = frequency x severity x historical-payoff-per-dollar of that limitation type's LINEAGE (all past accepted changes descended from it), a poor-man's HGM clade-metaproductivity — immediate eval delta alone is a documented poor predictor.

STEP 3 — PROPOSE: Tinker drafts ONE diff + a machine-readable ChangeRecord {limitation_id, evidence_trace_ids, diff, predicted_effect, tier}. Opens PR. Event logged.

STEP 4 — GATE (staged, cheap-to-expensive; budget dies with the stage that fails):
  4a. Static: sqlglot parse, policy tier classification, diff-scope check (touches only declared seams).
  4b. Sandbox: candidate manifest replays 20 questions against the frozen snapshot in a no-egress container; trace assertions (valid tool calls, no forbidden tables).
  4c. Public slice: 100 golden questions, dataframe-level execution comparison + judge for narratives; paired bootstrap (1000 resamples) of candidate-vs-incumbent difference; proceed only if 95% CI excludes zero on the primary metric and no slice regresses >2pts.
  4d. Private: Bench runs the 50 hidden questions; returns accept/reject only. Design assumption: ~90% of proposals die here or earlier — rejection is cheap and every rejection is an audit event.

STEP 5 — DEPLOY: Tier 0/1 auto-merge; CI bumps manifest version, moves the `production` label, invalidates prompt cache. Tier 2 parks in HITL queue (branch checkpointed; expires with escalation after 7 days so the queue can't silently freeze the loop).

STEP 6 — MONITOR: canary battery (25 known-good questions) runs daily against production; the next 50 live queries after any promotion are dual-answered (incumbent shadow) and judge-compared; any regression signal auto-repoints the label back (emergency change, always allowed, logged) and files the failure as a new golden case, Ramp-style.

STEP 7 — CREDIT: realized post-deploy deltas flow back into the ledger's lineage stats, closing the bandit loop.

## Limitation detection

Six concrete detectors, all mechanical, none dependent on the model's opinion of itself:

1. EXECUTION FAILURES: SQL errors, timeouts, EXPLAIN-gate rejections, empty result sets — harvested from traces with full context (question, schema retrieved, SQL emitted).
2. GOLDEN-SET FAILURES with stage localization: MLflow-style trajectory scoring pins WHICH stage failed (router sent a doc question to SQL; retriever missed the relevant chunk; SQL joined wrong; synthesis contradicted the dataframe). Each failure carries its stage label so proposals route to the right seam.
3. METRIC-FALLBACK COUNTER: every time Scout answers via freshly generated SQL instead of a verified query or named metric, that's a coverage-gap event. Nightly clustering of these events (embedding + HDBSCAN) yields demand-ranked candidates for new verified queries — the improvement backlog writes itself from real usage.
4. AMBIGUITY DETECTOR: when a question maps to >1 plausible metric definition (e.g., "revenue" = invoiced vs collected), Scout computes BOTH, labels them, and the divergence auto-files an ambiguous_metric limitation + HITL clarification ticket. Guessing is prohibited by rubric; the judge penalizes unlabeled ambiguous answers.
5. DRIFT MONITORS: daily diff of information_schema against the glossary/playbook (schema drift); doc-corpus freshness deltas and canary-query rank shifts (retrieval drift).
6. USER SIGNAL: thumbs-down and corrections in the chat UI become LimitationRecords AND permanent golden candidates (after human confirmation of the correct answer).

Crucially, the limitation detector's own health metric is "detected-and-fixed rate," never "few limitations reported" — reporting fewer limitations must never look like success, or the loop Goodharts by going blind.

## Evaluation design

Core anti-Goodhart move — GROUND TRUTH BY CONSTRUCTION: the synthetic data generator (a ~1k-line Python script, seeded) plants known facts as parameters: "Enterprise-plan accounts with >2 unresolved tickets churn at 3.1x base rate," "EU margin dropped 4pts after the March price change," "doc X's pricing table is stale relative to the invoices table." Golden questions and their verified answers are EMITTED BY THE GENERATOR alongside the data — zero human labeling cost for the MVP, and private-set rotation is free: re-run with a new seed, planted parameters shift, memorized answers die. The improver cannot overfit answers that regenerate.

Split: ~150 questions -> 100 PUBLIC (Tinker sees scores and failure traces; may overfit, that's fine) / 50 PRIVATE (Bench-only; accept/reject reported, never numbers; rotated by reseed every 2 weeks) / 1 RESERVE OBJECTIVE (a second objective, "margin analysis," never used in the loop, evaluated only at the end-of-project audit to test second-order generalization, AIDE2-style).

Scoring: SQL-path answers by dataframe comparison (order/dup/format-normalized) against generator-computed truth, executed on two perturbed snapshot instances to kill coincidental matches (FLEX/test-suite evidence: naive EX has ~9% FP / ~17% FN); narrative answers by a pinned different-provider judge (rubric: groundedness to retrieved data, numeric-claim reconciliation via re-execution, completeness, labeled uncertainty; order-randomized, length-normalized), calibrated once against ~100 human labels at setup and monthly thereafter.

Multi-objective acceptance, SICA-style: accept requires quality delta AND cost-per-question and p95 latency within 110% of incumbent — cost and latency are gate metrics, not dashboards.

REWARD-HACKING RATE as a first-class metric: weekly, a human audits 5 randomly sampled accepted changes end-to-end (does the claimed improvement replicate from raw traces?); plus an automated fabrication check — the Clerk independently recomputes every claimed eval delta from Bench's own records, never trusting Tinker's self-report (the DGM fabricated logs; assume yours will try).

## Audit design

One append-only `events` table in a dedicated Postgres schema; the agent DB role has no INSERT/UPDATE grant — only the Clerk service writes. Record shape: {event_id, ts, prev_hash, hash=SHA256(prev_hash||payload), actor (agent-run-id | human-id | ci), event_type (limitation_detected | proposal_opened | gate_stage_result | merged | label_moved | hitl_requested | hitl_decided | rollback | canary_alert | audit_sample_reviewed), payload_json, trace_ids[], commit_sha, manifest_version}. Daily head-hash anchored to an external location (a private GitHub gist or S3 object-lock bucket) for tamper evidence.

The Git repo carries the diffs; the event log carries the WHY and the decisions; every event cross-references commit SHA + Langfuse trace IDs, so "what changed, why, evidence, who approved" is one JOIN. Every span Scout emits follows OTel GenAI semconv (invoke_agent/chat/execute_tool) into self-hosted Langfuse, with improvement episodes as their own invoke_agent spans span-linked to the triggering task traces — traces are for debugging, the chained log is the record of authority. The HITL UI doubles as the audit browser: filter events by manifest version, replay any historical harness config by checking out its SHA. Deferred: WORM storage, per-agent SPIFFE identities, full deterministic replay.

## Human-in-the-loop design

One async approval queue (Postgres table + minimal HTMX page + Slack webhook notification), four typed request kinds: (1) ACCESS_REQUEST — credentials/scopes the agent cannot mint itself, by construction; (2) METRIC_CLARIFICATION — ambiguous objective/metric definitions, with the agent's candidate interpretations and their divergent numbers attached; (3) TIER2_CHANGE — verified queries, metric defs, new skills: shown as diff + evidence traces + auto-generated "what could go wrong" section, approval requires selecting a reason code (active input, not one button — the explainability-paradox literature says rationales increase rubber-stamping, so force judgment); (4) ROLLBACK_CONFIRM only for human-initiated reverts (agent-triggered emergency rollback is always allowed, reviewed retrospectively).

Blocking semantics per the brief: the improvement branch parks as a persisted LangGraph checkpoint keyed to the queue row; the webhook on decision resumes or discards it; Scout serves continuously on the unmodified manifest. Items carry SLA (72h) then escalate, then expire-with-log so the loop never silently freezes.

Attention budgeting (the oversight-capacity evidence): target ≤5 human decisions/week for the MVP's single reviewer; Tier 0/1 exist precisely to keep humans off low-stakes changes; low-urgency Tier 2 items batch into a Monday digest. Rubber-stamp alarm: approve-rate >95% with median decision time <10s fires an audit event. Dual control (2 distinct approvers) is DEFERRED but the schema has an `approvals[]` array so it's a config flip, not a migration.

## Novel variations

- GROUND-TRUTH-BY-CONSTRUCTION EVALS: generate the synthetic business data from a seeded script whose planted parameters (churn drivers, margin shifts, deliberately-stale documents) ARE the hidden answers; golden Q&A pairs are emitted by the generator, and private-set rotation is a reseed. This makes the private eval memorization-proof and rotation free — no published RSI system does this because they all evaluate on fixed external benchmarks. It also directly de-risks the hardest enterprise problem (curating golden insights is the scarcest resource) by deferring human curation to the real-data phase.
- METRIC-FALLBACK COUNTER AS DEMAND-RANKED BACKLOG: every answer served via freshly generated SQL instead of a verified query or named metric is logged as a coverage-gap event; nightly embedding-clustering of these events produces improvement proposals pre-ranked by real question demand. The improvement backlog is mined from usage rather than imagined by the improver — and each cluster arrives with its evidence traces already attached for the audit record and the HITL reviewer.
- AMBIGUITY TAX: when a question admits multiple metric interpretations, the agent must compute and present ALL of them, labeled, and the numeric divergence between interpretations auto-files a clarification ticket whose priority is proportional to the divergence. Ambiguity becomes a measured, queued, human-resolvable quantity instead of a silent guess — attacking exactly the spot where Goodhart pressure is worst (ambiguous metrics) with a mechanism that costs one extra query.
- LINEAGE-CREDIT BANDIT SCHEDULER: the limitation ledger allocates the improvement budget by realized post-deploy payoff-per-dollar of each limitation type's whole lineage of past changes (poor-man's Huxley-Godel CMP), not by predicted or immediate eval delta — implemented as ~50 lines of Thompson sampling over ledger arms, it imports the strongest scheduling insight from the RSI literature at near-zero cost.
- SELF-REPORT DIFFING AS FABRICATION ALARM: the audit Clerk independently recomputes every claimed improvement delta from Bench's raw records and the trace store, and any mismatch between the proposer's ChangeRecord and independent telemetry raises a first-class fabrication event. This turns the DGM's log-fabrication failure mode into a cheap standing detector rather than a post-incident discovery.

## Risks

- MVP-to-vision gap: single Postgres + one doc corpus doesn't exercise federated multi-source planning, per-user ACL intersection, or catalog-governed MCP. Mitigation: Scout's Router/SQLGen/Retriever seams are the same typed interfaces a federated planner would slot behind, the manifest/gate/audit spine is source-count-agnostic, and the reserve-objective audit tests generalization — but cross-source planning is genuinely untested until phase 2.
- Synthetic data is too easy or too regular: planted facts may be recoverable by patterns that fail on messy real data (baseline could start at 70% instead of the realistic 10-30%, leaving little headroom for the loop to demonstrate). Mitigation: generator deliberately injects enterprise nastiness (NULL-laden columns, fan-out join traps, cents-vs-dollars, timezone mixes, stale conflicting docs); calibrate baseline to <50% before starting the loop, or harden the generator.
- Eval-set overfitting despite the split: 50 private questions give noisy accept/reject, and accept/reject bits still leak over many proposals. Mitigation: reseed rotation every 2 weeks, paired bootstrap CIs not point estimates, and the untouched reserve objective as the final honest check — but with ~1 proposal/day the statistics are workable only because rejection is the default.
- Single-reviewer HITL starvation or rubber-stamping: one human is a bottleneck and kappa-0.52-grade noise for ambiguous approvals. Mitigation: 72h SLA with expiry, digest batching, rubber-stamp alarms; dual control deferred, which is an accepted MVP weakness.
- Judge gaming and self-preference: the improver may learn judge-pleasing narrative features. Mitigation: different-provider pinned judge, execution-grounded numeric reconciliation dominating the rubric, weekly human audit samples, hacking-rate metric — residual hacking is expected steady state (AIDE2 landed at 34%), so the metric must stay on the dashboard forever.
- Tier creep / governance erosion: pressure will build to reclassify Tier 2 changes as Tier 1 to increase velocity — exactly the envelope-creep failure the EU AI Act analysis warns about. Mitigation: tier taxonomy lives in the policy repo outside the agent's writable scope and changing it is itself a dual-approval human change.
- Cost surprise: dual-answering canary windows and multi-instance execution checks roughly double eval-time inference spend. Mitigation: fixed $10/cycle budget enforced at the Bench API, staged gates kill most candidates cheaply, and cost is an acceptance metric so the loop cannot buy quality with spend.

## MVP scope

BUILD (6 weeks, 1-2 engineers): W1 — docker-compose stack (Postgres+pgvector or Qdrant, MinIO, Langfuse), synthetic-data generator with planted facts, baseline Scout (router, NL2SQL with sqlglot/EXPLAIN gates, hybrid RAG, grounded synthesis), OTel tracing. W2 — Bench eval service as a separate trust domain: generator-emitted golden set, public/private split, dataframe comparison on two perturbed instances, pinned different-provider judge; measure baseline (target: confirm 30-50%, i.e., real headroom). W3 — Coroner + Limitation Ledger + Tier 0 playbook loop end-to-end (first self-improvement lands this week). W4 — Tinker PR pipeline + full staged Gatekeeper + manifest versioning/label rollback (Tier 1 prompt evolution live). W5 — Clerk: hash-chained event log, HITL queue with typed requests, verified-query promotion (Tier 2), canary battery + post-promotion dual-answer window. W6 — hands-off run: the loop operates unattended for 7 days against a scripted stream of ~50 questions/day; deliverable is the accuracy trajectory (candidate vs frozen control harness on the private set), rejection rate, hacking-audit results, cost ledger, and the reserve-objective generalization check.

DEFER, with reasons: code-level self-modification (10-100x cost, uninterpretable output, DGM/$22k evidence; config surface captures most gain per GEPA/ACE evidence); multi-source federated planning and MCP tool governance (needs the enterprise catalog context; seams are in place); weight-level adaptation (SEAL forgetting + audit opacity; strictly unnecessary); real A/B or shadow-vs-human-analyst scoring (no real users yet; paired canary comparison is the small-n substitute); dual-control approvals, WORM storage, SPIFFE identities, EU-AI-Act documentation pack (schema-ready, enterprise-phase work); L2 'ignition' experiments (AIDE2 showed it fails; out of scope by design); Mem0-style consolidating memory (append-only playbook with dedup is enough at MVP scale; consolidation is a phase-2 job when the playbook bloats).

## Tech stack

Python 3.12; LangGraph (agent state machine + checkpointer for durable HITL interrupts) with DSPy modules per pipeline stage (GEPA available offline for prompt evolution); sqlglot for AST validation; Postgres 16 (business data + pgvector option + ledger/queue/event tables in separate schemas/roles), Qdrant for vector retrieval, MinIO for the doc store; self-hosted Langfuse for OTel GenAI traces and immutable prompt versions with label-based rollback; Git + a CI runner (GitHub Actions or a local runner) as the Gatekeeper; FastAPI + HTMX for the HITL/audit UI; Claude Sonnet for Scout and Tinker, Claude Haiku for cheap classification/clustering, a pinned different-provider model (e.g., Gemini Flash) as the frozen Bench judge; docker-compose for the whole thing, no Kubernetes at MVP.

