# Self-Improving Harness for an Enterprise Insights & Decision Agent

A design program for an agent that fetches information and insights from enterprise data sources (SQL databases, data lakes, vector/knowledge stores), supports business decisions against a user-supplied objective, **detects its own limitations while serving, deliberately overcomes them by improving its own execution flow, logs every improvement for audit, and asks for human help when a step needs it.**

This repository currently holds the **design and experiment plan**, not yet code. It is the output of a structured design program: four parallel research sweeps of prior art, four independent design proposals from competing engineering lenses, a three-judge selection panel, four adversarial red-team critiques, and a ten-experiment feasibility ladder. The reference material behind every decision is preserved under [`docs/references/`](docs/references/).

## The one-paragraph version

Every credible self-improving system (2023–2026) is the same loop — **propose a change to an artifact → evaluate it on held-out data → gate on a strict threshold → archive the lineage** — and what separates real improvement from self-deception is the *discipline of the gate*, not the cleverness of the proposer. So this design treats self-improvement as a **change-management process with an optimization loop inside it**: every improvement is a versioned, human-readable diff that passes a staged public/private evaluation cascade, rolls out shadow → canary → fleet, and reverts in one operation — while the evaluator, policy engine, and audit log live in a trust domain the improving system can neither read nor write. The improvement surface with the best evidence behind it (semantic-model entries, verified queries, playbooks, prompts, skills) is also the cheapest and most auditable, so the capability ceiling is high without resorting to opaque code-level self-modification. Scope is honest **Level-1** recursive self-improvement; Level-2 "ignition" is a bounded stretch experiment, because the best published attempt tested it and it failed.

## Read in this order

| Doc | What it covers |
|-----|----------------|
| [01 — Core Concept](docs/01-core-concept.md) | The central insight, the improvement loop, the tiered improvement surface, the three trust domains, the objective problem, what "production-feasible" means |
| [02 — Architecture](docs/02-architecture.md) | Component map across serving / improvement / control domains; the trust ladder; the adversarial layer; tech stack |
| [03 — Limitation Detection](docs/03-limitation-detection.md) | The detector battery, keeping detectors honest, limitation→operator mapping |
| [04 — Evaluation](docs/04-evaluation.md) | Three-slice architecture, ground-truth-by-construction, scoring stack, anti-Goodhart defense in depth, long-horizon decision quality |
| [05 — Audit & HITL](docs/05-audit-and-hitl.md) | Audit-chain schema, HITL as a metered resource, anti-rubber-stamp/anti-fatigue design, regulatory mapping, the degradation principle |
| [06 — Variations Catalog](docs/06-variations-catalog.md) | Every non-obvious mechanism surfaced, adopted or deferred, with the conditions that would earn it in |
| [07 — Experiment Roadmap](docs/07-experiments.md) | The E0→E9 ladder with success **and kill** criteria, the path from concept to a 90-day production pilot |
| [08 — Risks & Red-Team](docs/08-risks-and-red-team.md) | The seven cross-cutting adversarial findings and the amendments they forced, accepted residual risks, open questions |

## Key design commitments

- **Three trust domains enforced by IAM, not prompts.** The improver authors PRs; the control domain (eval service, policy kernel, audit chain) decides and records; the agent can neither read nor write it. This is the lesson of the Replit incident and the Darwin Gödel Machine's log fabrication — natural-language instructions are not controls.
- **The gate is the product.** Public/private evaluation split with accept/reject-only reporting, metered leakage budgets, fixed dollar budget per evaluation, ~90% designed rejection rate, reward-hacking rate as a permanent first-class metric. Ground-truth-by-construction synthetic data makes the private slice memorization-proof and infinitely rotatable during mechanics validation.
- **Tiered, enumerated improvement surface** doubling as the EU AI Act Art. 43(4) "pre-determined changes" envelope; tier derived from diff semantics in the control domain, never self-attested.
- **Every improvement is an auditable, atomically-revertible deploy** — manifest lockfile, copy-on-write knowledge branches so rollback reverts learned state too, rehearsed <60s rollback as a promotion gate.
- **Humans are a metered, depletable resource** — typed durable approval queue, engagement checks, rubber-stamp alarms, approval futures, and the degradation principle: under stress the system loses autonomy before it loses oversight.
- **Honest scope:** L1 self-improvement of the task pipeline. This system *recommends*; it does not execute business actions. Adding execution would require redoing the entire risk analysis.

## Reference material

- [`docs/references/`](docs/references/) — the four research digests (RSI prior art, enterprise data agents, governance/audit/HITL, agent evaluation), each with mechanism/evidence/relevance/failure-mode findings and sources.
- [`docs/references/proposals/`](docs/references/proposals/) — the four original competing design proposals (capability-first, production/SRE, governance-first, pragmatic-MVP). The production/SRE proposal (GateKit) won the judge panel; the synthesized architecture merges it with grafts from the other three.
- [`docs/references/red-team/`](docs/references/red-team/) — the four full adversarial critiques.

## Primary external reference

Weco AIDE² — ["first evidence of recursive self-improvement"](https://www.weco.ai/blog/first-evidence-of-recursive-self-improvement). Used for inspiration, not as a template. The single most transferable idea taken from it is evaluation discipline: public/private score splits, fixed cost budgets per attempt, and a gate that rejects ~90% of proposals are what made their self-improvement real rather than self-deception.
