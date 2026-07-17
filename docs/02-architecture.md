# Architecture

The synthesized architecture takes **GateKit** (the production/SRE proposal, unanimous winner of the 3-judge panel) as the spine and merges the consensus grafts from the other three proposals. Full original proposals are under [references/proposals/](references/proposals/).

## Component map

```
┌─ SERVING DOMAIN ────────────────────────────────────────────────────────────┐
│                                                                             │
│  Insight Agent Runtime (IAR)                                                │
│  ┌────────┐  ┌─────────────────┐  ┌──────────────┐  ┌─────────────┐         │
│  │ Router │─►│ SQL leg          │  │ Retrieval leg│  │ Synthesizer │         │
│  │        │  │ (semantic layer │  │ (hybrid BM25+│  │ (grounded,  │         │
│  │        │  │  first, NL2SQL  │  │  dense+rerank,│  │  numeric    │         │
│  │        │  │  fallback)      │  │  ACL-trimmed)│  │  claims     │         │
│  └────────┘  └─────────────────┘  └──────────────┘  │  tagged)    │         │
│       all stages are DSPy modules; all data access  └─────────────┘         │
│       via governed MCP tools, on-behalf-of-user auth, read-only creds       │
│                                                                             │
│  Harness Manifest ── Git lockfile pinning prompts, playbook, skills,        │
│                      retrieval params, model IDs, knowledge-branch ref      │
│  Knowledge Substrate ── playbook (ACE deltas) · skill vault · verified      │
│                      query repo · memory graph — all on copy-on-write       │
│                      branches pinned by the manifest                        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                     OTel traces       │                 ▲ label repoint
                                       ▼                 │
┌─ IMPROVEMENT DOMAIN ────────────────────────────────────────────────────────┐
│  Flight Recorder ──► Limitation Ledger ──► Improvement Factory ──► PRs      │
│  (trace lake)        (typed events,        (frozen improver;                │
│                       double-entry,         one change per PR,              │
│                       bandit scheduler)     evidence attached)              │
│  Deployment Controller ── shadow → canary → fleet; rollback rehearsal       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                    submit(manifest)   │           accept/reject bit only
                                       ▼
┌─ CONTROL DOMAIN (no agent read/write access) ───────────────────────────────┐
│  Gatehouse ── golden sets (public/private/reserve), frozen different-       │
│               family judge, sandbox fleet, frozen data snapshots,           │
│               leakage budgets, tripwire probes                              │
│  Policy Kernel ── OPA/Rego; classifies every change & tool call:            │
│               allow / require_approval(tier) / deny                         │
│  Approval Queue ── durable HITL workflows (typed requests, SLAs, expiry)    │
│  Audit Chain ── append-only hash-chained event log, WORM-anchored           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Serving domain

**Insight Agent Runtime (IAR).** The baseline harness the project starts from. A router decomposes each business question into legs:

- **SQL leg — semantic layer first.** Resolve to a named, governed metric (dbt MetricFlow / Cube) whenever possible; fall back to generated SQL (sqlglot AST-validated, EXPLAIN cost-gated) only when no metric matches — and *every fallback is itself a logged limitation signal* ("metric X missing from semantic layer"), the cheapest high-yield improvement signal in the system.
- **Retrieval leg.** Hybrid BM25 + dense retrieval with reranking over the knowledge base, permission-trimmed per caller.
- **Synthesizer.** Grounded narrative answers in which every numeric claim is tagged to the query that produced it, enabling mechanical post-hoc reconciliation.

Every stage is a DSPy module, so its prompts/instructions are optimizable artifacts. All data access goes through catalog-governed MCP tools with on-behalf-of-user auth; row/column security is enforced *in the database* (session variables, scoped read-only credentials), never in the LLM.

**Harness Manifest.** A Git-versioned lockfile pinning every prompt version, playbook version, tool version, model ID, retrieval parameter, and knowledge-branch ref. The running system is always reconstructible from one commit hash. Environment labels (`prod`, `canary`, `shadow`, `staging`) are movable pointers; deploy and rollback are label repoints plus cache invalidation.

**Manifest-atomic memory (graft from GateKit's own novel mechanism).** The known killer of config rollback is state contamination — memory writes, playbook entries, and vector-index updates are not reverted by repointing a label. The entire knowledge substrate therefore lives on **copy-on-write branches** (lakeFS/DVC-style); improvements that write memory do so on a fork, promotion merges the fork ref into the manifest, and one label move reverts *everything* the change touched, atomically.

**Knowledge substrate contents:**

- *Playbook* — ACE-style structured delta items ("invoices.amount is cents", "accounts→tickets fans out; aggregate first"), append/merge with dedup, monolithic rewrites banned (prevents context collapse).
- *Skill Vault* — Voyager/Alita-G-style library of execution-verified, parameterized skills (SQL templates, join paths, metric resolvers) registered as MCP tools. **Skill half-lives (graft):** every skill carries declared preconditions (tables, columns, metric versions) and a decay clock; drift sentinels re-execute cheap certification probes and demote failures to `stale` (retrieval-suppressed, logged) rather than deleting. Self-pruning without an LLM rewriting anything.
- *Verified Query Repository* — human-approved question→SQL pairs served verbatim ("curation over generation", Snowflake/Databricks pattern). The loop can *propose* entries; a human activates them.
- *Memory graph* — schema facts, source quirks, metric definitions, with provenance and tombstones (never hard-delete).

**Learned-state hygiene (red-team amendments — all mandatory, not enhancements):**

- **Permission labels by lineage.** Every learned artifact carries a mandatory access-classification label inherited from the *most restrictive* source object touched by its evidence traces, and retrieval of learned artifacts is permission-trimmed exactly like documents. Without this, learning from one user's traces surfaces restricted data to other users — RLS protects the database, not the prompt (the "permission laundering" attack).
- **No literal values in shared artifacts.** Stored examples carry schema and query shape only, values templated out; a PII/secret scanner runs as a hard static gate on any artifact containing string literals, and at Ledger-write time (a secret committed to the WORM-anchored chain is permanent — prevention must be upstream).
- **Provenance classes.** Learned artifacts may distill only from trusted-tier evidence (human-confirmed pairs, analyst corrections, execution outcomes). Any artifact whose evidence lineage includes raw retrieved document text auto-escalates a tier — otherwise a poisoned document in the knowledge base becomes permanent learned behavior (prompt injection upgraded to a persistence mechanism).
- **Definitional artifacts are never T0.** Glossary synonyms and semantic-layer-adjacent playbook deltas change what a query *means* while regressing zero golden questions; they are T2 with data-owner review, and contested business nouns (revenue, churn, margin) sit on a protected-term list where any change touching their resolution path is T3 regardless of change type.
- **Cumulative-diff budgets.** Per-artifact cumulative change since the last human-reviewed baseline is capped; exceeding it freezes that artifact's T0 lane and forces an aggregate human review — the defense against salami-slicing T2 capability out of many individually-innocuous T0 diffs.

## Improvement domain

**Flight Recorder.** All serving and improvement activity as OpenTelemetry GenAI spans (vendor-portable), every span carrying the serving manifest hash — so "which change caused this wrong answer at 3am" is one join.

**Limitation Ledger.** Typed LimitationEvents from the detector battery ([03-limitation-detection.md](03-limitation-detection.md)). **Double-entry semantics (graft):** a detected limitation opens a *liability* that can only close via (a) a promoted improvement whose post-deploy telemetry confirms the symptom rate dropped, (b) an explicit human waiver with reason code, or (c) aged expiry that *reopens it at higher severity*. Nothing disappears silently, so the detector cannot look better by going blind — and scheduled **fault injection** (plant a poisoned canary doc, rename a sandbox column, publish a wrong aggregate) measures detector *recall* as a dashboarded metric.

**Improvement Factory.** The proposer. Its code and prompts are frozen and human-owned; it reads evidence traces, writes a diagnosis, and opens exactly one PR per change, scoped to a declared *seam* (a typed pipeline interface — a patch may only touch what it declared). **Bounded ignition (graft):** the only self-updating part of the improver is an ACE-style *improver playbook* — "which fix type worked for which limitation class in this enterprise" — accumulating as gated T0 deltas. This captures most of the plausible meta-learning gain (diagnosis and operator selection quality) with none of the ungovernability of self-modifying improver code, and the playbook is itself a readable audit artifact.

**Scheduler.** A bandit over limitation types weighted by *lineage survival* (CMP-lite: 30-day production survival rate of past fixes per limitation type) × event frequency × estimated fix cost, with a business-impact floor so high-impact limitations cannot silently age out unworked.

**Deployment Controller.** Orchestrates rollout: **rollback rehearsal** ("the 3am drill" — no manifest reaches canary until an automated <60s rollback of that exact manifest has been demonstrated in staging, including knowledge-branch state and cache invalidation) → shadow (≥200 live queries answered unserved, paired-judged, mSPRT-monitored) → canary (10% traffic, auto-rollback wired to judge-preference inversion, grounding failures, p95 latency, cost, and the change's own shipped canary probes) → fleet.

## Control domain

**Gatehouse.** The evaluation service — separate repo, separate service identity, no agent access. Holds:

- **Public slice** (~300 golden questions, visible to the Factory as its optimization signal; grown Ramp-style — every production failure becomes a permanent case).
- **Private slice** (accept/reject bit only, Ladder-thresholded). **Leakage budget (graft):** every accept/reject bit leaks information; each private-slice query decrements an explicit per-slice budget, dashboarded, and exhaustion auto-triggers rotation from freshly labeled traffic and invalidates in-flight proposals evaluated against the retiring slice.
- **Second-order reserve** — 1–2 whole business objectives never used in any loop, checked only at quarterly release audits.
- **Tripwire probes** — honeypot questions whose plausible answer is wrong unless the data is actually queried (planted sign-flips, discontinued products, NULL-poisoned cohorts). Passing public while failing tripwires flags the proposal as a hack, increments the reward-hacking-rate metric, and **quarantines the whole proposal lineage** — punishing hacking where it propagates, not per-proposal where retries are free.
- **Frozen judge** from a *different model family* than the generator, version-pinned, kappa-calibrated quarterly against human labels, order-randomized, length-normalized.
- Sandbox fleet (gVisor/Firecracker) and frozen warehouse snapshots (lakeFS branches) with fixed dollar budgets per evaluation.
- **Complexity tax (graft):** every candidate pays a gate penalty computed from diff size, added control-flow branches, dead-code-detector hits, and a cheap-model explainability probe ("can a small model correctly summarize what this diff does?"). A change must beat the threshold *after* tax — pricing the documented evolved-code-becomes-uninterpretable failure into the fitness function.

**Policy Kernel.** OPA/Rego sidecar between every agent and every tool; per-call and per-change verdicts of allow / require_approval(tier) / deny. Policies live in a repo with no agent write path; unclassifiable changes default-deny into T2. **Tier is derived, never declared (red-team amendment):** the control domain classifies every change deterministically from the parsed diff itself (manifest paths + AST — a change touching module instructions is T1 regardless of label; anything touching credentials, scopes, objective definitions, or executable code is T3). The proposer's declared change_type is a claim cross-checked against the derived tier; a mismatch is a first-class fabrication event that quarantines the lineage. Without this, the tier system is self-attestation — the single most dangerous gap the security red-team found.

**Approval Queue.** Durable workflows (Temporal / LangGraph checkpoints): a blocked improvement branch parks for hours or days while serving continues; decisions resume it by signal. Typed request kinds: `CredentialGrant`, `DataAccessScope`, `MetricClarification`, `ObjectiveDisambiguation`, `RiskyChangeSignoff`. Anti-fatigue and anti-rubber-stamp mechanics in [05-audit-and-hitl.md](05-audit-and-hitl.md).

**Audit Chain.** Append-only, SHA-256 hash-chained event log written by a logger the agents cannot reach, hourly-anchored to WORM storage. Schema and rationale in [05-audit-and-hitl.md](05-audit-and-hitl.md). **Fabrication alarm (graft):** the audit layer independently recomputes every claimed eval delta from the Gatehouse's own records; any mismatch between the proposer's ChangeRecord and independent telemetry raises a first-class fabrication event — the Darwin-Gödel-Machine log-fabrication failure mode as a cheap standing detector.

## The trust ladder (how the loop earns autonomy)

GateKit's signature mechanism, kept — but hardened, because the red-team showed the ladder's evidence base is itself gameable ("survived 30 days" means "not caught", and the proposer authors the probes that do the catching):

- A **regression budget** (e.g., max 2 user-visible regressions from auto-applied changes per quarter): when spent, change types demote one tier — humans return to the loop automatically. Charged only for regressions *causally attributed* to a loop-shipped change (via counterfactual replay of old-vs-new manifest on the failing queries); ambient drift opens limitation events, not budget spend — otherwise an upstream schema migration triggers mass demotion, queue floods, and oscillation.
- An **improvement-velocity SLO** denominated in the **execution-verifiable counterfactual replay dividend** (cumulative workload-denominated quality delta per month), never in acceptance count — so N no-op changes score zero and the SLO correctly reports stagnation. An explicit, dashboarded **IDLE state** ("no productive limitations above threshold") is healthy, not alarmed.
- **Promotion is conditional on measured detector recall, not elapsed clean time:** a change type is promotion-eligible only if fault-injection recall for that type's regression class exceeds threshold in the same window. Survival statistics may cite only control-domain probes and fault-injection results, never proposer-authored probes.
- **Probe teeth:** every proposer-shipped canary probe must *fail* against a mutated version of its change (mutation testing) at static check, and the Gatehouse generates independent control-domain probes for every promoted change.
- **Rate limits:** at most one tier transition per change type per quarter; for regulated deployments, promotions accumulate in a staging catalog and take effect only at the quarterly re-baselining ritual, batched and reviewed as one envelope amendment — keeping the EU AI Act "pre-determined changes" claim literally true between assessments.
- **Approval futures (graft):** tier relief is expressed as pre-authorized, template-scoped, auto-expiring change *allowances* ("up to 5 verified-query activations per week matching the read-only single-schema template, expiring in 90 days"), metered against the declared envelope. Approval becomes a periodic portfolio review instead of a per-change tax, and the steward's renewal review is a natural audit ritual.

Because the ladder auto-widens on regression-detector evidence, detector quality is itself audited via the fault-injection recall metric above — otherwise the ladder promotes on false evidence.

## Adversarial layer (phase 2)

- **Red Twin** — a frozen, hand-tuned attacker agent (different model family, kernel trust domain, never self-improving) that spends a fixed budget per gate-passing candidate trying to elicit a confidently-wrong-but-judge-pleasing answer. Its success rate *is* the production reward-hacking metric, measured at promotion time rather than post-hoc.
- **Examiner** — an adversarial question generator that mutates real analyst questions along known failure axes (NULL semantics, fan-out joins, timezone boundaries, ambiguous nouns), validating each kill by executing ground truth itself. Every confirmed kill becomes a limitation record *and* a permanent golden/tripwire case — actively hunting the silent-wrong-answer class no user ever reports, and continuously minting the eval cases the Gatehouse is starved for.

## Tech stack (reference implementation)

| Concern | Choice |
|---------|--------|
| Language / orchestration | Python 3.12; LangGraph (state machine, interrupts, checkpointer); DSPy modules (GEPA-ready) |
| Durable HITL & sleep-time jobs | Temporal |
| Semantic layer | dbt MetricFlow or Cube, exposed via MCP |
| SQL safety | sqlglot AST validation; EXPLAIN cost gates; DB-level RLS; read-only scoped creds |
| Policy | OPA/Rego sidecar; policy repo outside agent write scope |
| Versioning / deploy | Git + CI; Langfuse immutable prompt versions with environment labels; manifest lockfile; CODEOWNERS dual-control |
| Observability | OTel GenAI semantic conventions → ClickHouse/Langfuse + Grafana |
| Audit | Postgres append-only event table, SHA-256 chained, hourly anchor to S3 Object Lock (WORM) |
| Eval infra | lakeFS snapshot branches; gVisor/Firecracker sandboxes; scipy bootstrap; mSPRT/confidence sequences |
| Models | Frontier model for agent + Factory; pinned *different-family* judge; cheap models for classification/probes |

Everything here is boring, proven infrastructure by design; the only custom components are the Gatehouse, the Limitation Ledger, and the manifest/deploy glue.
