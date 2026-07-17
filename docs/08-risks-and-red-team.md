# Risks & Red-Team Findings

Four adversarial critics attacked the merged design (GateKit + grafts) from different lenses — Goodhart/reward-hacking (16 attacks), offensive security (8), operations & economics (9), and enterprise adoption & compliance (10). Full reports with concrete scenarios, mitigations, and residual risks are in [references/red-team/](references/red-team/). All four verdicts landed in the same place: **the trust-domain skeleton is sound and worth keeping; the salvage work is that several of the design's own safety mechanisms were its top remaining attack surfaces.** The design amendments below have been folded into docs 02–05; this document records why.

## The seven cross-cutting findings

### 1. The loop's safety mechanisms are themselves Goodhart surfaces

The most important finding of the whole program. Four mechanisms the design was proudest of were gameable, and they feed each other:

- **Proposer-authored canary probes** measure the regressions that drive the trust ladder — so autonomy can widen on evidence the optimizer manufactured (vacuous probes → "90 clean days" → tier promotion).
- **"30-day survival" means "not caught,"** so a survival-rewarded scheduler systematically favors lineages whose regressions evade probes over honest-but-occasionally-rolled-back ones.
- **An acceptance-count velocity SLO** rewards flooding the pipeline with no-op changes; winner's-curse selection ships noise that "survives" by doing nothing.
- **Proposer-declared lineage** lets a quarantined hack re-file under a different diagnosis label, resetting quarantine and re-arming free retries.

*Amendments:* probes must pass mutation testing and are supplemented by control-domain probes; ladder promotion is conditional on measured detector recall, never elapsed clean time; the velocity SLO is denominated in the execution-verifiable replay dividend with an explicitly healthy IDLE state; lineage is assigned in the control domain from content fingerprints.

### 2. Ground truth can co-corrupt with behavior

Agent-blessed answers promoted into golden sets make the eval *defend the agent's bugs*: a churn query that silently drops NULL payment records becomes a golden case; every future change that computes churn correctly "regresses" and is rejected. Related: the public slice plus T0 memory writes is an eval-contamination machine — knowledge writes can encode the exam.

*Amendments:* golden answers are dual-derived (agent SQL vs data-owner recomputation from the semantic spec, result-set match required); knowledge writes must cite production traces, never eval runs, enforced by a contamination scanner; public-slice gains scored on perturbation variants, never verbatim.

### 3. Learned state is a data-governance surface, not just a capability store

Three attacks, all severity 4–5, all high-likelihood: **permission laundering** (artifacts learned from one user's traces surface restricted data to others — RLS protects the database, not the prompt); **PII/secrets in permanent artifacts** (a secret in evidence traces reaches the WORM-anchored chain and cannot be deleted, only rotated); **prompt-injection persistence** (a poisoned document distilled into a T0 playbook delta becomes permanent learned behavior that outlives the document).

*Amendments:* mandatory access-classification labels inherited from the most restrictive evidence source, with permission-trimmed artifact retrieval; value-stripping plus PII/secret scanning at static gate and ledger-write; provenance classes forbidding distillation from raw retrieved text; definitional artifacts (glossary, semantic-adjacent deltas) escalated out of T0; a protected-term list making contested-noun resolution T3.

### 4. Self-attested tiers are privilege escalation

If the Policy Kernel classifies changes by the proposer's declared `change_type`, the entire tier system is self-attestation: a T1 payload labeled "retrieval few-shot" (T0) auto-merges through the lowest gate. *Amendment:* tier is derived deterministically in the control domain from the parsed diff (paths + AST); declared-vs-derived mismatch is a fabrication event that quarantines the lineage.

### 5. The economics kill before the safety does

The cost critic's verdict: the most likely death is not an incident but "a month-6 budget review, an exhausted two-person on-call rotation, and a steering committee that cannot name one thing the loop shipped that an analyst couldn't have config-changed faster." Specifics: a uniform full-cascade gate costs $1k–4k per *accepted* change at 90% rejection; standing human duties sum to 1.5–2 senior FTE; accumulated artifacts become a new legacy codebase (4× context bloat, contradictory playbook entries); a vendor model deprecation vaporizes 30–50% of prompt-layer gains roughly annually; and the 20+ grafts guarantee phase-1 scope collapse unless frozen.

*Amendments:* tier-proportional gating (T0 costs cents, not hundreds of dollars); logged-traffic replay as default shadow for T0/T1 with batched "train" releases and rehearsed bisection; global artifact budgets with eviction (beat your replacement, not the baseline) and assembled-context size as a gate guardrail; the improvement portfolio deliberately weighted toward model-agnostic artifacts (verified SQL, metric definitions, tripwires) over prompt tunings; cost-per-accepted-improvement and human-hours-per-accepted-improvement as first-class KPIs with a sponsor-pre-signed downscope criterion; a hard graft freeze with phase entry criteria (encoded in the experiment ladder).

### 6. Auditability is not accountability

An immutable record of *what happened* does not produce a person answerable for *why*. Auto-applied T0/T1 changes read to a SOX auditor as "developer with unsupervised push-to-prod"; a GEPA-evolved prompt's honest explanation ("a search process scored this string 2.3 points higher") fails in front of a regulator; and "the agent decided" consumes three weeks of governance meetings before the loop is frozen by remediation order.

*Amendments:* named human owner per change type who signs the class pre-authorization and answers in post-mortems; the standard-change catalog pre-ratified by internal audit/MRM/counsel *before* build; T1 run as human-post-hoc-attestation for the first 6–12 months; explainability floor (changes whose effect can't be summarized are capped at T2); post-mortem game-day rehearsed before go-live (experiment E8); envelope frozen between assessment cycles with promotions batched into the quarterly re-baselining.

### 7. The residual risk is governance-shaped

Every critic independently converged on this: the design's densest safeguards — quarterly re-baselining, weekly hacking audits, reviewer budgets, judge recalibration, labeling supply — are exactly the rituals organizations skip under pressure, and the anti-rubber-stamp alarms structurally accuse named employees, so they will face political pressure to be "recalibrated." Software cannot fix this; the design can only make degradation *visible and asymmetric*.

*Amendment — the degradation principle:* under any resource or governance shortfall, the system **loses autonomy before it loses oversight**. Staffing below floor auto-degrades the loop to read-only proposal mode. Rubber-stamp signals route to the second-line risk owner as control-effectiveness metrics, never to reviewer management as performance metrics. Deployment contracts should treat audit-staffing lapses as a system outage.

## Accepted residual risks (the honest list)

These survive every mitigation and must be owned, not argued away:

1. **Residual reward hacking is the steady state.** The best published trajectory is 63%→34%, not →0%. The weekly human audit is budgeted headcount forever.
2. **Judge biases correlate across model families** — "different family" buys less than it appears; narrative-insight quality is permanently the softest gate.
3. **Sycophancy pressure is ambient** — it flows through every human-labeled artifact, including the audit samples. Multi-interpretation answers force disclosure, not comprehension.
4. **Semantic composition of small changes is fundamentally hard to detect** — cumulative-diff budgets and clustering bound salami-slicing; they do not close it.
5. **Fault injection measures recall only on defect classes someone thought to plant.**
6. **Hard-question strata are small-n** — regressions inside CI noise slip through individually and appear only in trends.
7. **A logged, self-documented optimization toward a commercial objective is more legally discoverable than the undocumented human status quo it replaces.** Complete records plus demonstrated guardrails is a defensible posture; complete records without guardrails is a confession. The GC signs off on this trade explicitly.
8. **Some deployments will be honestly evaluated and honestly not worth it.** The cheap tier — nightly human-reviewed suggestion batches — must exist as a designed destination, not a failure state.

## Open questions (completeness pass)

Gaps no critic or design fully addressed — candidate work items:

1. **The trivial-baseline control arm.** E7's downscope criterion implies it, but no experiment directly races the loop against "one analyst with LLM tooling reviewing a nightly suggestion batch." That comparison is the single most persuasive (or fatal) ROI artifact and should be run as a formal arm of E7.
2. **Improvement interference.** Changes are gated individually, but concurrently accepted changes interact (a prompt evolution plus a retrieval change may compose destructively). Train releases partially cover this; a designed interaction test (pairwise replay of same-window accepted changes) does not yet exist.
3. **Multi-objective portfolio conflicts.** Two standing objectives ("maximize revenue", "protect margin") pull the shared substrate in opposing directions. Heterogeneous gating requires no single change to regress other objectives, but portfolio-level tension (which objective gets scheduler budget?) is a human governance question with no named forum yet.
4. **Multi-tenant scaling.** Everything is designed for one department. Cross-department rollout raises: shared vs partitioned knowledge substrates, conflicting metric definitions between BUs (the ambiguity ledger helps but assumes one owning team per noun), and blast-radius coupling.
5. **Serving-time model failover.** Model *migration* is designed (E7 amendments); model *outage* is not. A pinned-judge outage stalls every gate; a generator outage stalls serving. Degraded-mode behavior needs specification.
6. **Gatehouse change management.** Who gates the gate? Eval-harness changes (new tripwires, threshold moves, judge swaps) are human-owned but need their own change-control story — a compromised or careless Gatehouse edit invalidates every downstream guarantee silently.
7. **Learned-artifact IP and portability.** Verified queries and playbooks encode enterprise business logic in vendor-adjacent formats. Export format, ownership, and model-portability of the substrate deserve an explicit statement (partially mitigated by weighting toward model-agnostic artifacts).
8. **Action execution is out of scope — say so.** This system *recommends*; it does not execute business actions (no write paths, no side-effectful tools in the serving path). The moment execution is added, the entire risk analysis must be redone; that boundary should be a signed scope statement in the pilot charter.
