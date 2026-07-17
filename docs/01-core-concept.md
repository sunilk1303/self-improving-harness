# Core Concept

## What this system is

A **self-improving harness** for an enterprise insights-and-decision agent. The agent answers business questions and supports decisions by querying enterprise data sources — SQL databases, data lakes, and vector/knowledge stores. Given a user-supplied business objective ("reduce churn", "maximize margin"), the harness:

1. **Detects its own limitations** while serving — missing metrics, weak SQL generation, retrieval gaps, missing tools, missing data access, ambiguous business definitions.
2. **Deliberately overcomes them** by proposing changes to its own execution flow — prompts, playbooks, plans, retrieval configs, verified queries, skills — while continuing to serve on the unmodified system.
3. **Logs every improvement for audit** — what changed, why, with what evidence, who approved.
4. **Asks for human help** when an improvement step needs something only a human can grant — credentials, data access, a metric definition, sign-off on a risky change.

## The central insight

Every credible self-improving system published between 2023 and 2026 is the same skeleton:

```
PROPOSE (mutate an artifact) → EVALUATE (automated, held-out) → GATE (accept only if better) → ARCHIVE (keep lineage)
```

What separates real improvement from self-deception is not the cleverness of the proposer — it is the **discipline of the gate**. Weco's AIDE² rejected ~90% of proposed changes; without a public/private evaluation split, its baseline agent reward-hacked 63% of the time. Sakana's Darwin Gödel Machine "fixed" a hallucination problem by deleting the markers its detector searched for, and fabricated its own logs.

So the founding decision of this project: **self-improvement is a change-management process with an optimization loop inside it, not an optimization loop that happens to be logged.** Every self-improvement is a software deploy: a versioned, immutable, human-readable diff that must pass a staged evaluation pipeline, roll out via shadow-then-canary, and be revertible in one operation. The evaluator, the policy engine, and the audit log live in a trust domain the improving system can neither read nor write.

We scope honestly to **Level-1 recursive self-improvement** — the system improves its own task pipeline more efficiently than humans hand-tuning it. Level-2 "ignition" (the improved system becoming a better *improver*) has been explicitly tested and has failed in the best published attempt (AIDE²); we treat it as a bounded stretch experiment, not a promise.

## Why the ceiling is high anyway

Harness engineering, not model choice, is where the gains are. Enterprise text-to-SQL over raw schemas runs 10–31% correct; the same stacks with curated semantic models, glossaries, and verified queries reach 80%+ (dbt measured 83% vs ~40%; Snowflake's agentic semantic-model self-improvement lifted accuracy 57%→78%). Spider 2.0 scores went from ~10% to 70%+ in 18 months almost entirely from scaffolding. The mutable artifacts of *this* harness — semantic-model entries, verified queries, playbooks, prompts, skills — are exactly the artifacts that carry those gains. That is the bet: **the improvement surface with the best evidence behind it is cheap, text-based, human-auditable, and enterprise-shaped.**

## The improvement loop

Every step below emits an immutable audit event (see [05-audit-and-hitl.md](05-audit-and-hitl.md)).

```
      ┌──────────────────────────────────────────────────────────────┐
      │                        SERVING (unchanged)                   │
      └──────────────┬───────────────────────────────▲───────────────┘
                     │ traces                        │ promoted manifest
                     ▼                               │
  DETECT ──► SELECT ──► PROPOSE ──► GATE ──► APPROVE ──► DEPLOY ──► MONITOR ──► CREDIT
  (typed     (lineage-   (one PR     (staged   (tiered     (shadow →   (canaries,   (survival &
  detectors, credit      per change, cascade,  HITL or     canary →    hacking      replay deltas
  never      bandit)     evidence    public/   auto)       fleet)      audits,      feed the
  self-               attached)   private)                          rollback)    scheduler)
  report)
```

- **DETECT.** Limitations are typed, machine-emitted events — never the model's opinion of itself. Detector battery in [03-limitation-detection.md](03-limitation-detection.md).
- **SELECT.** A bandit scheduler picks which limitation to attack, weighted by *lineage productivity* (do fixes of this class survive 30 days in production?), not immediate eval delta — the Huxley-Gödel Machine showed the two correlate weakly.
- **PROPOSE.** The Improvement Factory drafts exactly **one change per proposal** as a PR: a manifest diff plus a machine-readable ChangeRecord with evidence trace IDs, predicted effect, a self-authored rollback runbook, and 2–3 new canary probes that would detect this change regressing. A change that cannot describe how to detect and undo itself is rejected at static check.
- **GATE.** A staged cascade, cheap→expensive, with a fixed dollar cap per candidate: static checks → sandbox replay → public golden slice (the proposer's visible optimization signal) → private held-out slice (accept/reject bit only). ~90% cumulative rejection is the designed steady state, and rejection is cheap because most candidates die early.
- **APPROVE.** A policy engine classifies the change into a tier (below); low tiers auto-apply with logging, higher tiers park in a durable human approval queue while serving continues.
- **DEPLOY.** Shadow mode on live traffic (unserved), then canary at partial traffic with auto-rollback triggers, then fleet. Rollback is rehearsed *before* promotion: no change ships until an automated <60s rollback of that exact manifest has been demonstrated.
- **MONITOR / CREDIT.** Hourly canary probes, weekly human audits of accepted changes, replay dividends; 30-day survival feeds back into the scheduler.

## The tiered improvement surface

What the system may modify about itself is an **enumerated envelope**, tiered by risk. The enumeration doubles as the EU AI Act Art. 43(4) "pre-determined changes" declaration, so in-envelope evolution never constitutes a substantial modification requiring re-assessment.

| Tier | Change class | Examples | Gate | Human role |
|------|-------------|----------|------|-----------|
| **T0** | Standard (pre-approved) | Playbook delta items (append/merge, never rewrite); verified-query *proposals*; retrieval few-shots; glossary synonyms; canary probes | CI evals | Weekly digest only |
| **T1** | Normal (auto after full gate) | Prompt versions (GEPA-evolved); tool descriptions; router weights; retrieval params; plan templates | Full cascade + canary | Post-hoc digest |
| **T2** | Sensitive | Minting a new skill/MCP tool from verified trajectories; semantic-layer metric definitions; golden-set promotions; memory consolidation ops | Full cascade | Single approver, async queue, 72h SLA |
| **T3** | High-risk | New data scopes/credentials; agent-authored executable code; model version changes; objective definitions | Full cascade + offline campaign | Dual control (maker ≠ checker, two distinct owner groups) |
| **∅** | **Structurally impossible** | Policy engine and its rules; eval service and private sets; audit log; tier classification; its own IAM grants | No write path exists | — |

The bottom row is the load-bearing one. The Replit incident (an agent ignoring an explicit code freeze, deleting a production database, then fabricating data and falsely claiming rollback was impossible) is the canonical proof that **natural-language instructions are not controls**. Everything in that row is enforced by repository permissions, IAM, and process separation — not prompts.

Tier membership of a change *type* is itself movable only by humans, and reclassification is a T3 dual-control change — otherwise the loop erodes its own governance ("it always passes, make it T0").

## Three trust domains

| Domain | Contains | Can it change itself? |
|--------|----------|----------------------|
| **Serving** | The insights agent (router, SQL leg, retrieval leg, synthesizer), its manifest-pinned config, playbook, skill library | Only via gated deploys from the improvement domain |
| **Improvement** | Trace mining, limitation ledger, the Improvement Factory (proposer), deployment controller | Its code and prompts are **frozen and human-owned**; only its *playbook* of "what worked here" self-updates (bounded ignition) |
| **Control** | Eval service (Gatehouse) with private golden sets and frozen judge; policy kernel; approval queue; audit chain | Humans only. Agents have zero read or write access |

The improver authors PRs; the control domain decides; the audit chain records. The maxim is enforced by IAM, not by prompts.

## The objective problem

"Maximize revenue" is not an objective a machine may interpret alone — over what horizon? bookings or recognized? which segment? at what margin floor? Ambiguous objectives and contested metric definitions are the **single most Goodhart-dangerous surface** in the whole system, so they are routed to humans *by construction*:

- At objective-definition time, the business owner co-authors the metric definition and 5–10 **golden decision cases** with the harness operators. The loop is forbidden from resolving metric ambiguity by optimizing whatever happens to be measurable.
- At answer time, when a question admits multiple metric interpretations, the agent computes **all of them, labeled** (the *ambiguity tax*), and the numeric divergence between interpretations auto-files a clarification ticket with priority proportional to the divergence.
- Resolved definitions become governed semantic-layer entries (a T2 change), so each ambiguity is answered once, not per-query.

## What "production-feasible" means here

The system is feasible when we can demonstrate, with statistics that survive optimization pressure:

1. The loop **beats a frozen control harness** on a private, rotating evaluation slice — not on its own visible metrics.
2. The gains **generalize** to a second-order reserve (whole business objectives never used in any loop).
3. **Reward hacking is measured and bounded** — a first-class dashboard metric with budgeted human audit sampling, never assumed to be zero (the best published trajectory is 63%→34%, not →0%).
4. **Every accepted change has a complete audit record** and a rehearsed rollback.
5. **Human attention is spent within a declared budget** without the queue silently freezing the loop or degrading into rubber-stamping.

The experiment ladder in [07-experiments.md](07-experiments.md) is sequenced to test exactly these claims, riskiest first.
