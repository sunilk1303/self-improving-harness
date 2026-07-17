# Variations Catalog

The brief asked: *"think really hard on this core concept along with what other variations can be added."* This catalog collects every non-obvious mechanism surfaced by the design program — the merged design adopts most of them (marked ✦); the rest are documented options with the conditions under which they'd earn their way in.

## Evaluation & anti-Goodhart

**✦ Ground-truth-by-construction evals.** Generate the synthetic business data from a seeded script whose planted parameters *are* the hidden answers; golden Q&A pairs are emitted by the generator; private-set rotation is a reseed. Memorization-proof, depletion-proof, zero labeling cost during mechanics validation. No published RSI system does this.

**✦ Tripwire probes + lineage quarantine.** Honeypot questions whose plausible answer is wrong unless the data is actually queried (planted sign-flips, discontinued products, NULL-poisoned cohorts). Public-pass + tripwire-fail quarantines the entire proposal lineage for a cooling-off period — punishing hacking at the level where it propagates.

**✦ Metered private-set leakage budget.** Treat adaptive-data-analysis leakage as an operational quantity: every accept/reject bit decrements a per-slice budget; exhaustion auto-rotates the slice and invalidates in-flight proposals. Leakage becomes a paged-on metric with a runbook instead of an academic worry.

**✦ Complexity tax / interpretability gate term.** Charge every candidate a penalty from diff size, added control-flow branches, dead-code hits, and a cheap-model explainability probe ("can a small model summarize what this diff does?"). Changes must win *after* tax — pricing the evolved-code-becomes-uninterpretable failure into the fitness function and biasing search toward auditable artifacts.

**✦ Counterfactual replay dividend.** Retro-score every promoted change by replaying the prior N days of real production questions through old and new manifests; append the workload-denominated delta to the audit record. Catches golden-set overfitting within days; converts "the eval said better" into auditor-grade evidence.

**✦ Brier ledger.** Every recommendation embeds a falsifiable probabilistic claim, logged before outcomes are knowable, scored (reliability/resolution decomposition) as outcomes mature. The only strictly-proper, ungameable long-horizon decision-quality signal available. Sustained miscalibration auto-opens a limitation.

**✦ Fabrication alarm (self-report diffing).** The audit layer independently recomputes every claimed eval delta from the Gatehouse's own records; mismatches raise first-class events. The DGM log-fabrication failure as a standing detector.

**✦ Gate-discipline ablation.** Periodically run a *sacrificial branch* with a deliberately weakened private gate and measure over-promotion. Cheap; validates the gates are load-bearing rather than theater; produces the governance-sales artifact enterprises actually ask for.

## Adversarial mechanisms

**✦ Red Twin.** A frozen, hand-tuned attacker agent (different model family, control domain, never self-improving) spends a fixed budget per gate-passing candidate trying to elicit confidently-wrong-but-judge-pleasing output. Its success rate *is* the reward-hacking metric, measured at promotion time. Because it's frozen and separate, the improving agent cannot co-adapt with its own examiner.

**✦ Examiner adversarial limitation miner.** An agent that constructs questions the serving agent fails — mutations of real analyst questions along known failure axes — validated by executing ground truth itself. Confirmed kills become limitations + permanent golden/tripwire cases. Actively hunts silent wrong answers and continuously mints the eval cases the system is starved for.

**Limitation bounty economy** *(deferred — needs a stable golden pipeline first)*. Pay the Examiner in scheduler budget per confirmed novel failure; give each limitation lineage an escrowed budget that improvement attempts bill against; lineages whose promoted changes keep paying off receive dividends. Turns limitation detection into an adversarial market and gives the audit log a currency-denominated account of where improvement effort went.

**✦ Detector fault injection.** Plant known defects on a schedule and score detector recall as a dashboard metric. The limitation detector is evaluated exactly like the agent it monitors.

## Scheduling & meta-learning

**✦ Lineage-credit scheduling (CMP-lite).** Select which limitation to attack by the 30-day production survival rate of past fixes per limitation type — not immediate eval delta (the Huxley-Gödel Machine's Metaproductivity-Performance Mismatch: benchmark delta of a variant correlates weakly with its lineage's downstream value). Implementable as ~50 lines of Thompson sampling. Pair with a business-impact floor so hard-but-important limitations can't age out unworked.

**✦ Bounded ignition via improver playbook.** Full L2 ignition (self-modifying improver) failed in the published attempt and is out of scope. The constrained variant: the Improvement Factory's code and prompts stay frozen and human-owned, while an ACE-style playbook of "which operator worked for which limitation class in this enterprise, with evidence" accumulates as gated T0 deltas. Most of the plausible meta-learning gain, none of the ungovernability, and the playbook is a human-readable audit artifact.

**✦ Metric-fallback demand clustering.** Nightly embedding-clustering (HDBSCAN) of raw-SQL-fallback events yields a verified-query/metric backlog ranked by real question demand, evidence pre-attached. The backlog writes itself from usage.

## Governance & HITL

**✦ Two-sided error budget / trust ladder.** Gate width governed by data, not politics: a regression budget that auto-demotes change types a tier when spent, and an improvement-velocity SLO whose sustained health auto-*generates* (never auto-applies) tier-promotion proposals evidenced by survival statistics. The system earns autonomy from its own track record.

**✦ Approval futures.** Pre-authorized, template-scoped, auto-expiring change allowances metered against the declared envelope — the operational embodiment of EU AI Act Art. 43(4), and the best available answer to approval fatigue.

**✦ Ambiguity tax + ambiguity ledger.** Compute all plausible metric interpretations, labeled; auto-file clarification tickets with priority proportional to numeric divergence; accumulate resolved definitions as a governed, agent-consulted asset with owning teams.

**✦ Double-entry limitation ledger.** Limitations are liabilities that close only via confirmed symptom-rate drop, explicit waiver, or aged expiry at higher severity. Un-Goodhartable by under-reporting; gives auditors a clean liability view.

**✦ Envelope-creep re-baselining.** Quarterly: replay current manifest vs the originally assessed baseline against the second-order reserve plus a behavioral-invariant checklist; review the aggregate diff as one change; freeze tier auto-routing until it passes. The audit answer to "a thousand small approved changes quietly became a different system."

**✦ Rollback rehearsal gate (the 3am drill).** No manifest reaches canary until an automated <60s rollback of that exact manifest — including knowledge-branch state and cache invalidation — has been demonstrated in staging. Every change ships its own rollback runbook and 2–3 self-targeted canary probes or dies at static check.

**Reviewer-minute market** *(adopt once approval volume justifies it)*. Proposals bid for the declared reviewer-capacity budget, priced by tier and prioritized by lineage productivity per reviewer-minute.

## State & artifact management

**✦ Manifest-atomic memory (copy-on-write knowledge branches).** Playbook, skill library, vector indexes, and semantic model snapshot as lakeFS/DVC-style branches pinned in the manifest; memory-writing improvements fork, promotion merges the ref, rollback repoints — one label move reverts everything atomically.

**✦ Skill half-lives with execution re-certification.** Every minted skill/verified query carries declared preconditions and a decay clock; drift sentinels re-execute cheap certification probes; failures demote to `stale` (retrieval-suppressed, logged) rather than delete. Solves library bloat and schema-drift-encoded hacks with pure mechanism — no LLM rewriting.

**ACE-style delta-only playbook updates** ✦ *(adopted as a hard rule)*: append/merge with dedup, monolithic rewrites banned — the documented cure for context collapse (LLM rewrites eroding detail over iterations).

## Explicitly rejected or deferred surfaces

| Variation | Verdict | Why |
|-----------|---------|-----|
| Code-level self-modification of the serving pipeline (DGM-style) | **Deferred** to quarterly offline "expedition" campaigns behind dual control | 10–100× the cost ($22k/run published), uninterpretable output, dead/buggy evolved code; the config surface captures most gain per GEPA/ACE/semantic-layer evidence |
| Model-weight adaptation (SEAL-style self-edits) | **Permanently out** | Catastrophic forgetting curves, unauditable, unnecessary |
| L2 ignition (self-improving improver) | **Out of scope**, bounded-ignition playbook only | Explicitly tested and failed in AIDE²; don't promise it, don't build for it |
| Full autonomous resolution of metric ambiguity | **Forbidden by policy** | The single worst Goodhart surface; always a human decision |
| Auto-approve under reviewer load | **Forbidden structurally** | Recreates the Replit incident |
