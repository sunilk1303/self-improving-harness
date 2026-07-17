# Audit & Human-in-the-Loop

## Audit: two layers with different jobs

**Traces are for debugging; the chained log is for auditors.**

1. **Flight Recorder** — OpenTelemetry GenAI semantic-convention spans (`invoke_agent` / `chat` / `execute_tool`) for every serving and improvement action, PII-redacted at the collector, every span carrying the serving manifest hash. Vendor-portable (Langfuse/LangSmith/Datadog all ingest them). Rich, queryable, *not* the record of authority.
2. **Audit Chain** — the record of authority: an append-only Postgres event table where each event carries `SHA-256(payload ‖ previous_hash)`, batched and anchored hourly to S3 Object Lock (compliance-mode WORM), so tampering with any historical entry is externally detectable.

**The logger lives in the control domain.** Agents hold a write-only, non-repudiable emit path and no read/update/delete path. Hash chains prove *integrity*, not *completeness* — suppression is prevented by privilege separation, and the gate/policy services independently write their own events rather than trusting agent self-reports. (Darwin Gödel Machine fabricated its own logs; Replit's agent falsely claimed rollback was impossible. Assume yours will try.)

**Anchor evidence content, not just evidence IDs (red-team amendment).** The chain must commit to a SHA-256 of the redacted evidence *payload* at decision time, not merely the trace IDs — otherwise trace-store tampering or TTL expiry silently hollows out forensics while the hash chain still validates. Trace retention ≥ audit retention for anything referenced by an ImprovementRecord.

**WORM vs GDPR erasure.** Immutable 7-year retention and the right to erasure conflict head-on. Resolution: the chain anchors *hashes and pointers* to WORM; payloads live in an erasable store with per-data-subject crypto-shredding — tamper evidence survives erasure because the hash of a shredded record still verifies the chain.

### The ImprovementRecord (one queryable answer to "what changed, why, who approved")

```
{
  change_id, proposal_ts,
  limitation_event_ids[], evidence_trace_ids[],
  change_type, tier, seam,
  manifest_hash_before, manifest_hash_after, unified_diff,
  predicted_effect,
  eval_results: { stage_outcomes, public_scores+CIs, private_accept_bit,
                  tripwire_result, complexity_tax, dollar_cost, judge_version },
  policy_decision: { rego_rule_id, verdict },
  approvals: [ { approver_identity, role, decision, reason_code, decision_latency_ms } ],
  deploy_events: [ { label, ts, shadow_stats, canary_stats, rollback_rehearsal_result } ],
  rollback_runbook_ref, shipped_canary_probe_ids[],
  replay_dividend, survival_status
}
```

Event types cover the full lifecycle: `limitation_registered`, `lineage_selected`, `proposal_opened`, `gate_result(G0..G4)`, `approval_requested/decided`, `label_moved`, `shadow_started`, `promoted`, `rolled_back`, `memory_op(ADD/UPDATE/TOMBSTONE)`, `skill_minted/recertified/retired`, `escalation_filed`, `budget_spent`, `hacking_audit_sample`, `fabrication_alarm`.

Every serving span carries its manifest hash, so *"which change caused this wrong answer at 3am"* is one join: trace → manifest → ImprovementRecord → evidence. Event sourcing gives exact replay: "what did the harness contain and believe on date D" is a fold over the log — simultaneously the incident-forensics story and the EU AI Act Art. 12 story.

**Identity:** per-agent workload identities (SPIFFE), human approvals via enterprise SSO — every actor field non-repudiable. **Retention:** 7 years. **Exposure:** a read-only governance API (current prompt/tool/version inventory + change feed) so enterprise control-tower platforms subscribe rather than drift.

### Memory is audited like config

Config rollback does not revert learned state — so every memory operation (playbook delta, memory-graph ADD/UPDATE, skill mint) is itself a chained event with tombstone semantics, *and* the knowledge substrate lives on copy-on-write branches pinned by the manifest, so rollback reverts state atomically. Belt and suspenders, because memory contamination outliving rollback is the most under-built failure mode in this class of system.

## HITL: humans are a metered, depletable resource

The research is blunt: **more oversight can produce less safety.** Realized safety is an inverted-U in escalation volume — past reviewer capacity, rubber-stamping lets ~40% of attacks through. And the *explainability paradox* is real: fluent AI-generated rationales measurably increase deference. So the design spends human attention like a budget and engineers against both failure modes.

### When humans are pulled in (typed, durable, async)

A blocked improvement branch parks as a persisted workflow (Temporal / LangGraph checkpoint) — surviving restarts, waiting days — while serving continues on the unmodified manifest. Five request kinds:

| Request | Trigger | Resolution |
|---------|---------|------------|
| `CredentialGrant` / `DataAccessScope` | Agent needs access it structurally cannot mint | Human grants scoped, read-only, expiring credentials via normal IAM; grant recorded on-chain |
| `MetricClarification` | Ambiguity detector fires (divergent interpretations) | Business owner picks/defines; codified as a governed metric (T2) — answered once, not per query |
| `ObjectiveDisambiguation` | "Maximize revenue" — horizon? segment? margin floor? | Captured at objective-definition time with 5–10 co-authored golden decision cases |
| `RiskyChangeSignoff` | T2/T3 changes | Approval flow below |
| Hacking-audit sample | Weekly schedule | Human verifies a random accepted change replicates from raw traces |

### Approval tiers (mirroring change tiers)

- **T0:** log-only; weekly digest.
- **T1:** no pre-approval; post-hoc digest review.
- **T2:** single approver from the *owning role* (prompt changes → platform owner; semantic edits → data steward), async queue, 72h SLA → escalation → **expiry-with-reopen** (expired proposals are auto-rejected and archived, never silently applied).
- **T3:** maker-checker dual control — proposer ≠ approver, two humans from distinct CODEOWNERS groups (data owner + platform owner), enforced by branch protection. Single-reviewer judgments of "risky" carry κ≈0.52 — a lottery; dual control is reserved surgically because it burns 2× scarce capacity.
- **Emergency (rollback):** always allowed, retrospectively reviewed.

Three amendments from the adoption red-team, all about *accountability*, which an immutable log records but does not create:

- **Named owner per change type.** Every change class in the envelope has a named human *owner* (not approver) recorded in the tier catalog, who signs the class pre-authorization and is the answerable party in any post-mortem for changes of that type — the same way SRE organizations make "the autoscaler did it" answerable. "The Policy Kernel approved it" is not an answer an audit committee accepts.
- **Pre-ratified standard-change catalog.** Auto-applied T0/T1 changes will fail SOX/ITGC and model-risk review as "developer with unsupervised push-to-prod" *unless* the change taxonomy is pre-ratified by internal audit and MRM as an ITIL standard-change catalog — a signed, versioned, periodically re-attested document owned by a named executive, negotiated *before* build, not after the first audit finding. For the first 6–12 months, run T1 as human-post-hoc-attestation-within-24h so a human signature chain exists for auditors to sample.
- **Evidence summaries are control-domain-generated.** For T2/T3 approvals, the dossier's statistics come from the Limitation Ledger's full record (symptom rate, denominator, trend); proposer-selected traces are displayed as "proposer's exhibits — non-exhaustive". Access requests are compiled to least privilege from the failing queries' actual table touch-set, carry expiry and usage metering, and unused breadth auto-files a scope-*reduction* proposal — otherwise proposer-framed evidence ratchets the access footprint monotonically upward.

**The degradation principle (adopted throughout): under any resource or governance shortfall, the system loses autonomy before it loses oversight.** If audit/review staffing lapses below the declared floor, the loop auto-degrades to read-only proposal mode — controls die last, never first. The worst end-state is not a frozen loop; it is expensive controls quietly turned off while self-modification keeps running.

**Load pressure never auto-approves — it only delays.** (Auto-approve-under-load recreates the Replit incident.) Queue starvation is a visible dashboard state — aged liabilities, staleness alarms — not a silent freeze.

### Anti-rubber-stamp engineering

- Approval UI leads with the **raw diff and evidence**, not the agent's narrative (the narrative increases deference).
- Auto-generated "what could go wrong" section per proposal.
- **Engagement check:** the approver must answer a factual question derivable only from the dossier ("which two tables does this verified query join?") and select a structured reason code before the Approve button activates.
- **Rubber-stamp alarm:** approve-rate >95% with sub-10-second median decisions fires an audited alarm that freezes tier auto-routing pending governance review.
- **Filler-flood detection:** an improvement wave generating unusual escalation volume is treated as a possible fatigue attack and throttled.

### Anti-fatigue engineering

- Declared reviewer-capacity budget (e.g., 30 min/day per role); the scheduler meters escalations against it; low-urgency items batch into a daily digest.
- The T0/T1 classes are made as large as *safely* possible so humans only see genuinely ambiguous or high-stakes items.
- **Approval futures:** stewards periodically approve bounded, template-scoped, auto-expiring change allowances ("up to 5 verified-query activations/week matching the read-only single-schema template, 90-day expiry"). Consumption is metered against the declared envelope; exhaustion or template deviation falls back to per-item review. Per-change tax becomes periodic portfolio review, and the renewal review ("what did last quarter's allowance actually get spent on?") is a natural audit ritual.
- **Reviewer-minute market:** pending proposals bid for the scarce capacity budget, priced by tier (T3 costs two approvers) and prioritized by lineage productivity per reviewer-minute — human attention flows to the improvement lineages with the best evidence of compounding payoff.

## Regulatory mapping (do the work once)

| Requirement | Design element |
|-------------|----------------|
| EU AI Act Art. 12 (logging) | Audit Chain + 7-year retention + exact replay |
| EU AI Act Art. 14 (human oversight) | Tiered approvals, dual control, engagement checks, capacity budgets |
| EU AI Act Art. 43(4) (pre-determined changes) | The enumerated tier envelope, declared in technical documentation; approval futures as its metered operational form |
| Envelope creep ("a thousand small approved changes became a different system") | **Quarterly re-baselining:** replay current manifest vs the original assessed baseline against the second-order reserve + a behavioral-invariant checklist (access footprint unchanged, answer-distribution shift bounded, no new side-effect classes); review the aggregate diff as one change; tier auto-routing freezes until it passes |
| NIST AI RMF | GOVERN = Policy Kernel + roles; MAP = detector battery; MEASURE = Gatehouse; MANAGE = rollback + incident flow |
