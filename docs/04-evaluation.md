# Evaluation Design

The gate is the whole game. Every published self-improvement success owes its reality to evaluation discipline, and every published failure is an evaluation failure: Darwin Gödel Machine deleting hallucination markers instead of fixing hallucination; AIDE²'s baseline reward-hacking 63% of test cases; automated judges agreeing with human experts only 62% of the time on BIRD. This document is the project's center of gravity.

## The three-slice architecture

| Slice | Who sees it | Reporting | Purpose |
|-------|------------|-----------|---------|
| **Public** (~300 golden questions) | Improvement Factory — its legitimate optimization signal | Full scores + failure traces | Let the proposer iterate; overfitting here is expected and priced in |
| **Private** (held-out) | Gatehouse only | **Accept/reject bit only** (Ladder-thresholded) | Survival decision; kills most Goodharting |
| **Second-order reserve** (1–2 whole objectives) | Nobody, ever, in any loop | Quarterly release audits only | Does improvement *generalize*, or did we overfit the loop itself? |

**Leakage is metered, not ignored.** Every accept/reject bit leaks information (adaptive data analysis); with ~90% rejection across hundreds of proposals the private set becomes effectively public. Each private-slice query decrements an explicit per-slice leakage budget derived from Ladder noise thresholds; exhaustion auto-triggers rotation from freshly labeled production traffic and invalidates in-flight proposals evaluated against the retiring slice. One engineer with casual read access to the private slice silently destroys the guarantee — Gatehouse access is a formal insider-threat surface.

**Golden sets are grown, not built once.** Every confirmed production failure becomes a permanent regression case (Ramp pattern); every Examiner kill becomes a golden/tripwire case; analyst corrections become cases after human confirmation. Fresh labeled questions are the scarcest asset in the whole system — which is why the experiment program starts with ground-truth-by-construction synthetic data (below).

Two contamination rules, both mandatory (red-team amendments):

- **Golden answers are independently derived, never agent-authored.** Promotion of a question into a golden set requires the data owner to recompute the answer from the semantic-layer spec on the frozen snapshot, with dual authorship recorded (agent SQL vs independent SQL, result-set match required). Otherwise the system's own confirmed errors become ground truth and the golden set structurally *defends the agent's bugs* — any future change that computes the metric correctly "regresses" the eval and is rejected.
- **Knowledge writes must cite production traces, never eval runs.** A control-domain contamination scanner embeds all playbook/few-shot/memory writes and flags similarity to any golden or private item (block on match, audit on near-match); public-slice gains are scored on held-out paraphrase/perturbation variants of golden questions, never verbatim. Otherwise the public slice plus T0 memory writes is an eval-contamination machine: the knowledge branch becomes a paraphrased lookup table for the exam.

## Ground truth by construction (the bootstrap)

For pre-production phases (and as a perpetual auxiliary supply), the synthetic business data is emitted by a **seeded generator whose planted parameters ARE the hidden answers**: "Enterprise-plan accounts with >2 unresolved tickets churn at 3.1× base rate"; "EU margin dropped 4pts after the March price change"; "document X's pricing table is stale relative to the invoices table." Golden Q&A pairs are emitted by the generator alongside the data.

- Private-set rotation is a **reseed** — memorized answers die; the slice never depletes.
- Zero human labeling cost during the phase where the loop's mechanics are being validated.
- The generator deliberately injects enterprise nastiness: NULL-laden columns, fan-out join traps, cents-vs-dollars, timezone mixes, stale and conflicting documents. Baseline must be calibrated to real-world hardness (<50% accuracy) before the loop runs, or there's no honest headroom to demonstrate.

No published RSI system does this, because they all evaluate on fixed external benchmarks. It converts this project's hardest resource problem into a scripting problem — for the synthetic phase. (Its limits: synthetic data can't prove distribution fidelity to *your* enterprise. That's what the later real-data experiments are for.)

## Scoring stack (cheapest first)

1. **Execution-based comparison** for SQL-path answers: result-set comparison, order/duplicate/format-normalized, run across **multiple perturbed DB instances** (test-suite accuracy — plain single-instance execution match has measured ~9% false positives / ~17% false negatives).
2. **Semantic judge only on disagreements** (FLEX pattern — lifts agreement with human experts from κ≈0.62 to ≈0.78).
3. **Numeric-claim reconciliation** for narrative insights: every number in the answer must match independent re-execution of its tagged query. Paraphrase never substitutes for correct magnitude and direction.
4. **Two-level LLM judge** for insight quality (summary-level + insight-level against expert-curated known insights, InsightBench-style), under strict bias controls:
   - **Different model family** than the generator, version-pinned, frozen (self-preference bias is measurable and becomes self-reinforcing inside an RSI loop).
   - Order-randomized (position bias shifts pairwise accuracy >10%), length-normalized (judge scores track verbosity at r=0.87 vs 0.44 for humans).
   - Rubric limited to fact-groundable criteria; calibrated against 200+ human labels with Cohen's κ tracked; recalibration mandatory on any judge version change. The improver never judges its own work and cannot query the judge directly.
5. **Cost and latency as gate metrics, not dashboards** (SICA pattern): acceptance requires quality delta AND cost-per-question AND p95 latency within bounds, under a fixed dollar budget per evaluation — improvements cannot win by spending more.
6. **Heterogeneity requirement:** every candidate is evaluated across ≥3 business objectives and ≥2 source types simultaneously; single-objective wins don't merge (forces generalizable improvements, AIDE²'s task-family lesson).

## Statistics that survive optimization pressure

- **Offline gates:** paired bootstrap CIs over eval questions (~1000 resamples, multiple generations per item to absorb LLM nondeterminism); the 95% CI must exclude zero on one designated primary metric, with Bonferroni guardrails and no slice regressing >2 points.
- **Shadow/canary promotion:** mSPRT / anytime-valid confidence sequences (the Netflix/Optimizely/Eppo machinery) — the monitor can peek continuously without p-hacking and stop the moment evidence suffices, minimizing shadow cost.
- **Paired comparison over A/B:** for an internal agent with few users, paired same-question comparison (old vs new manifest on identical queries) needs orders of magnitude less traffic than A/B (Netflix interleaving: >100× fewer users).

## Anti-Goodhart defense in depth

Layered, because no single defense survives (63%→34%, not →0%):

| Layer | Mechanism |
|-------|-----------|
| Structural | Public/private split; accept/reject-only reporting; leakage budgets; slice rotation; second-order reserve |
| Mechanical | Execution grounding of every numeric claim; multi-instance comparison; tripwire probes (honeypot questions whose plausible answer is wrong unless the data is actually queried) |
| Lineage-level | Public-pass + tripwire-fail ⇒ quarantine the whole proposal lineage, not just the proposal — punishing hacking where it propagates, since per-proposal retries are free |
| Economic | Fixed dollar budget per evaluation; complexity tax (diff size, added branches, dead-code hits, cheap-model explainability probe) — a change must win *after* tax |
| Adversarial | Red Twin attacker at promotion time (phase 2); Examiner minting fresh tripwires |
| Human | Weekly audit of a random sample of accepted changes — **budgeted headcount, not volunteer virtue**; the reward-hacking rate is a permanent first-class dashboard metric |
| Independent verification | Fabrication alarm: audit layer recomputes every claimed delta from Gatehouse records; mismatch = first-class event |

## Long-horizon decision quality (no ground truth exists)

For "did the recommendation actually help the business," judge the *process* and the *calibration*, not just the outcome:

- **Brier ledger:** every shipped recommendation embeds at least one falsifiable probabilistic claim ("P=0.7 that churn in segment X drops 2–4pts within 90 days if Y"), logged immutably *before* outcomes are knowable. As outcomes mature, a scheduled job scores the rolling Brier ledger with reliability/resolution decomposition — a strictly proper score the agent cannot game except by being right, with base-rate hedging exposed by the resolution term. Sustained miscalibration in a claim category auto-opens a limitation liability, closing the loop between slow decision-quality signal and the fast improvement cycle.
- **Golden decision cases** co-authored with the business owner at objective-definition time, labeled by domain experts independent of user approvals (removes affinity bias).
- **Counterfactual/uplift evaluation** (holdout populations, Qini curves) where intervention logs exist; where they don't, "we cannot backtest this" is a detected limitation that files a data-access request.
- **Counterfactual replay dividend:** every promoted change is retro-scored by replaying the previous N days of real production questions through old and new manifests (paired, order-randomized, execution-grounded). The workload-denominated delta is appended to the change's audit record — "the gate said better" becomes "on your actual workload it was X better" — and golden-set overfitting is caught within days of promotion, not at the quarterly audit.
  **Two ledgers, never summed (red-team amendment):** the dividend is split into an *execution-verifiable* ledger (numeric reconciliation against re-executed queries — ungameable by the judge) and a *judge-scored* ledger. Scheduler credit, trust-ladder evidence, and auditor artifacts draw only on the execution-verifiable ledger; a change whose judge-scored dividend far exceeds its execution-verifiable dividend carries the signature of a judge exploit and is routed to stratified human audit. Otherwise the replay mechanism launders judge hacks into the scheduler and amplifies them.
- **Brier-claim discipline:** the agent must not write its own exam. Probabilistic claims follow templates authored by business owners per recommendation type ("if adopted, metric M moves ≥X within horizon H" — M, X-floor, H fixed; only the probability free); resolution and sharpness are scored alongside reliability, so a ledger of near-tautological claims ("revenue within ±30% of trailing average") auto-opens an "uninformative forecasting" limitation.
