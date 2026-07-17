# Prior Art: Enterprise Data & Insight Agents in Production

> Survey of production enterprise data/insight agents (2024-2026): text-to-SQL and semantic layers, RAG at scale, governed tool access, and how production systems measure answer quality.
>
> Produced by a web-enabled research agent (July 2026) as part of the design program for this project. See [Sources](#sources) for the material consulted.

## Key takeaways

- Context/semantic layer, not model choice, is the dominant accuracy variable: raw-schema enterprise text-to-SQL runs 10-31% correct; the same stacks with curated semantic models, glossaries, and verified queries reach 80-99% (dbt measured 83% vs ~40%; Snowflake's agentic semantic-model improvement added +21pts avg on BIRD subsets). The harness's self-improvement loop should target semantic-model artifacts (metric definitions, joins, instructions, verified queries) as its primary mutable substrate, not just prompts.
- Snowflake has already shipped a narrow version of this project: a multi-agent system (Orchestrator, Relationships Agent, Semantic Model Editor, Custom Instruction Editor, Evaluator) that inspects failed/correct SQL pairs and rewrites its own semantic model, lifting accuracy 57%->78% average. This is the closest production precedent for 'limitation detection -> self-improvement' and a strong baseline to differentiate against (it improves only the semantic model, not tools/retrieval/plans).
- Treat vendor accuracy claims as marketing until reproduced: Snowflake's '90%+ SQL accuracy' is an internal eval; frontier models scored 10-24% on Spider 2.0 at ICLR 2025 (GPT-4o 10.1%, o1-preview 17.1%) vs 86.6% on Spider 1.0. By mid-2026 agentic scaffolds claim 70-97% on Spider 2.0 leaderboards, and a VLDB 2026 study found BIRD's automated judge agrees with human experts only 62% of the time — so build a project-specific golden set from real user questions rather than trusting public leaderboards either way.
- The dangerous failure mode is silent wrong answers, not errors: fan-out join inflation, NULL semantics (NOT IN + NULL returns zero rows), date/timezone guessing, and ambiguous business nouns ('revenue' = bookings vs recognized vs ARR) all execute cleanly and return wrong numbers. Production systems converge on: clarify-instead-of-guess, AST validation pre-execution (sqlglot), EXPLAIN cost gates, and a second-model result-sanity check post-execution.
- The production quality-measurement pattern has converged and is directly reusable as the harness's limitation detector: golden question set with expected SQL/results -> automated execution comparison -> LLM-as-judge (calibrated against humans via Cohen's kappa) -> human feedback -> iterate 3-5 cycles to 90%+ (Databricks Genie's built-in benchmarking + a Claude-as-judge loop is the documented playbook; MLflow 3 adds trajectory-level scorers reused identically in dev and prod monitoring; Agent Bricks auto-generates task-specific judges and synthetic eval data).
- Verified Query Repositories (Snowflake) / Trusted Assets (Databricks Genie) are 'curation over generation': human-approved SQL returned instead of fresh generation for anticipated questions. A self-improving harness can auto-PROPOSE new verified queries from successful, human-confirmed interactions — an improvement type with a natural HITL approval gate and audit record, and treated by practitioners as ongoing editorial work, not one-time setup.
- Governance has converged on catalog-governed MCP: Databricks managed MCP servers respect Unity Catalog permissions with on-behalf-of-user auth, and Unity AI Gateway registers MCP services as catalog securables with per-tool-call policy evaluation. Security enforcement must live in the platform (DB-level row-level security via session variables, read-only scoped credentials), never in the LLM — users claiming 'I am user_id=1' and prompt-injected SQL are demonstrated bypasses; MCP itself adds tool-poisoning and credential-aggregation risk (first malicious MCP package exfiltrated data for two weeks, Sept 2025).
- Enterprise RAG fails on knowledge-base operations, not models: ~73% of failed deployments trace to stale documents, coverage gaps, and extraction/chunking quality; the 'freshness gap' (old chunks outranking re-published docs) is the most common silent failure, and ~70% of production RAG teams have no systematic retrieval eval. The harness should treat corpus freshness/coverage/permission drift as first-class detectable limitations, with canary queries fired hourly as the production early-warning mechanism.
- Decision-support agents validate recommendations with causal measurement and staged actions, not judge scores: Hightouch AI Decisioning (10B+ decisions) measures every policy against randomized holdout groups for incremental lift; Palantir AIP stages every AI-proposed action for human review by default, with granular logs, and only 'well-worn, trusted' flows graduate to auto-execution. That 'trust ladder' (propose -> human-approve -> auto with audit) is the template for the harness's HITL and audit requirements.
- Cheap, production-proven self-improvement mechanisms exist beyond retraining: GEPA/DSPy reflective prompt evolution beats RL-based GRPO by ~6-20% with up to 35x fewer rollouts at $2-10 per optimization run (used in production by Decagon, Nous Research's Hermes self-evolution); combined with Reflexion-style failure memory and workflow evolution, these give the harness concrete low-risk improvement operators to experiment with.

## Findings

### Databricks AI/BI Genie (text-to-SQL over curated 'spaces')

**Mechanism.** Compound AI system: ensemble of agents for planning, SQL generation, explanation, visualization, and result certification, scoped to a curated 'Genie space' (selected tables + text instructions + SQL expressions + example queries). Asks clarifying questions on ambiguity instead of guessing. 'Trusted assets' = predefined SQL functions/example queries returned verbatim (flagged in UI) when a user question matches, replacing generation with curation. Built-in benchmarking tool: admins write test questions + ground-truth SQL; Genie runs itself and compares results. User thumbs-up/down feedback feeds curation.

**Evidence.** GA since 2024. Databricks' production-readiness guidance: benchmark >80% before UAT. A documented production framework (Salah Uddin) runs all prompts through an automated harness, uses Claude-as-LLM-judge against expected results in Unity Catalog, iterates 3-5 cycles to 90%+ accuracy; Genie performs poorly with bare schemas and becomes strong only after column descriptions and domain instructions are added. No public benchmark numbers from Databricks itself.

**Relevance to this project.** Genie's space model (scoped context + instructions + trusted assets + benchmark suite) is exactly the mutable state a self-improving harness should manage: the improvement loop can add instructions, propose trusted assets, and extend the benchmark suite automatically. Genie's clarify-on-ambiguity behavior is the pattern for the HITL requirement on ambiguous metrics.

**Failure modes.** Accuracy collapses without curated metadata (curation is manual and ongoing); scoped to one warehouse/catalog (no cross-source planning); benchmark suite drifts from real user questions; trusted assets only cover anticipated questions; feedback loop still requires a human curator to act on signals.

### Snowflake Cortex Analyst + agentic semantic-model self-improvement

**Mechanism.** Fully managed agentic text-to-SQL service grounded in a YAML semantic model (logical tables, measures, filters, synonyms, verified queries). Semantic model guarantees consistent application of user-defined measures/filters. Verified Query Repository (VQR): human-approved question->SQL pairs in the YAML, retrieved and reused for similar questions. Separately, Snowflake published an agentic semantic-model improvement system: Model Creation Agent (auto-generate), Orchestrator, Relationships Agent (infers joins from correct SQL + PKs), Semantic Model Editor (diffs current model vs correct/generated SQL and proposes refinements), Custom Instruction Editor (writes domain SQL-generation instructions), Evaluator Agent (column comparison then dataframe validation).

**Evidence.** Marketing claim: '90%+ SQL accuracy on real-world use cases' from internal evals; claimed ~2x single-prompt GPT-4o and ~14% above market alternatives (methodology not public). The agentic improvement paper on BIRD subsets: vanilla Claude 3.5 Sonnet 57% avg -> Cortex Analyst with agentically-improved semantic model 78% avg (+21pts; per-dataset +10 to +31). Human still required for relationship setup, metric definitions, Cortex Search wiring.

**Relevance to this project.** The single most direct production precedent for the project: an agent detecting semantic-model weaknesses from eval failures and rewriting its own context artifacts, with measured before/after gains. The harness should generalize this from 'semantic model only' to tools, retrieval pipelines, and plans — that generalization is the project's novelty space. VQR is the audit-friendly improvement type: each addition is a discrete, reviewable, attributable change.

**Failure modes.** Internal evals inflate expectations vs customer data; semantic-model YAML is a single point of ambiguity (bad metric definition = consistently wrong answers at scale); VQR maintenance is unbounded editorial work; agentic improvement needs ground-truth correct SQL to learn from, which production rarely supplies for free.

### Open-source text-to-SQL: Wren AI (MDL) and Vanna.ai (RAG triples)

**Mechanism.** Wren AI: MDL (Modeling Definition Language), a JSON semantic model encoding business concepts, relationships, calculated fields, metrics; Wren Engine compiles semantic references into SQL across 20+ sources; vector DB retrieves relevant MDL fragments per question; only metadata (never row data) goes to the LLM; suggests 3 candidate questions to disambiguate. Vanna.ai: RAG over a user-supplied 'training' corpus of DDL, documentation, and question->SQL pairs; retrieves nearest examples at query time to condition generation; no formal semantic layer — quality is entirely a function of curated examples.

**Evidence.** Both widely deployed OSS (WrenAI ~10k+ GitHub stars; Vanna similar). Snowflake's analysis: when Vanna-style retrieval finds no close match it falls back to schema-only reasoning at ~50% accuracy. Vanna suffered CVE-2024-5565 (2024): prompt-injected SQL string reached Python exec() -> remote code execution. Wren's metadata-only design is its stated enterprise privacy posture. Independent comparison (Sudipta Pathak) contrasts Vanna's example-curation approach vs Wren's governed-semantics approach: same business term can be interpreted inconsistently across queries in Vanna; Wren pins it in MDL.

**Relevance to this project.** Wren AI is the best open-source starting skeleton for the baseline harness (semantic layer + vector retrieval + multi-source engine, Apache-style license). Vanna's train-on-examples design shows the cheapest self-improvement primitive: append confirmed question->SQL pairs to retrieval memory — but also shows its ceiling (inconsistency without governed definitions). CVE-2024-5565 is the canonical argument for sandboxing any self-modifying code path in the harness.

**Failure modes.** Vanna: hallucination when retrieval misses, inconsistent term interpretation, requires perpetual example curation, RCE-class risk if generated output touches eval/exec. Wren: MDL authoring burden up front; MDL staleness = schema-drift failure mode moved one level up; retrieval of wrong MDL fragments still yields wrong SQL.

### Governed metric layers as agent substrate: dbt MetricFlow and Cube D3

**Mechanism.** dbt Semantic Layer/MetricFlow: metrics defined once in dbt project; MetricFlow is a deterministic SQL-generation engine — agents request metrics BY NAME via API and never author raw SQL; every consumer gets identical business logic. Now Apache 2.0 open source. Cube D3: universal semantic layer (metrics, dimensions, joins, access policies defined once) + three production agents — Semantic Model Agent (proposes/edits cubes, views, measures), Workbook Agent (assembles reports), Analytics Chat Agent (multi-query NL answering) — all constrained to the governed definition set; exposed via MCP and A2A so external agents (Claude, ChatGPT, custom) query governed metrics by name after listing available measures/dimensions.

**Evidence.** dbt internal tests: 83% accuracy for NL queries via Semantic Layer vs ~40% when the LLM writes raw SQL. Cube D3 launched 2025 as 'first agentic analytics platform on a universal semantic layer'; MCP integration shipped and usable from Claude Desktop. MetricFlow open-sourcing (2026) explicitly positioned as 'governed metrics to power trustworthy AI and agents'.

**Relevance to this project.** Defines the two-tier query interface the harness should prefer: (1) resolve question to a named governed metric (high trust, cheap), (2) fall back to generated SQL only when no metric exists — and a detected fallback IS a limitation signal ('metric missing from semantic layer') that the self-improvement loop can convert into a proposed metric definition for human approval. Cube's Semantic Model Agent is prior art for agent-proposed semantic-layer edits. MCP-listing of measures/dimensions is the discovery pattern for the tool registry.

**Failure modes.** Metric-by-name only answers questions the layer anticipates — coverage gaps push users back to raw SQL; semantic-layer definitions themselves become the contested artifact (which team's 'churn' wins); dual-path systems (metric API + raw SQL) can return conflicting numbers for the same question; agent-proposed model edits without review can codify wrong business logic permanently.

### Benchmark reality: Spider 2.0, BIRD, and the marketing gap

**Mechanism.** Spider 2.0 (ICLR 2025 Oral): 632 real enterprise workflow problems (BigQuery, Snowflake, SQLite, DuckDB/dbt variants), databases often >1,000 columns, requiring long-context navigation, multi-step workflows, queries often >100 lines. BIRD: 'dirty' realistic databases with external-knowledge requirements, execution-accuracy scored, human baseline 92.96%.

**Evidence.** At release: GPT-4o 10.1% on Spider 2.0 (vs 86.6% Spider 1.0); o1-preview 17.1%; ~23.8% peak on Spider2-Snow/Lite for o3-mini/o1. By mid-2026 the leaderboard shows specialized agentic scaffolds claiming Spider2-Snow 94-97% (Genloop Sentinel v2 Pro 96.70%), Spider2-Lite ~72-74%, Spider2-DBT 41-66% — a 5x jump in ~18 months from harness engineering, not base models. BIRD: Arctic-Text2SQL-R1-32B 71.8% EX (May 2025) vs human 92.96%. VLDB 2026 study (uiuc-kang-lab): pervasive annotation errors — BIRD's binary PASS/FAIL agrees with human experts only 62% of the time, mostly false negatives, so leaderboards are noisy in both directions. Vendor claims (Snowflake 90%+, dbt 83%) are internal evals on curated semantic models — not comparable to open benchmarks.

**Relevance to this project.** Calibrates feasibility experiments: expect baseline-harness raw accuracy in the 10-30% range on realistic enterprise questions and treat the 5x leaderboard jump as proof that HARNESS improvements (retrieval, decomposition, validation loops, iteration) — precisely what the self-improving system would automate — carry most of the achievable gain. Also: build eval sets with dataframe-level (not string/binary) comparison and human adjudication of disagreements, or the limitation detector will chase false negatives.

**Failure modes.** Leaderboard overfitting (some 96% entries are unaudited submissions); binary execution-match penalizes acceptable answer variants; public benchmarks lack ambiguity/permissioning/staleness dimensions that dominate real deployments; multilingual gap is extreme (~4-6% on non-English MultiSpider 2.0).

### How production systems measure answer quality (the eval loop)

**Mechanism.** Converged pipeline: (1) golden dataset — real user questions + expected SQL/results, stored centrally (MLflow Evaluation Datasets as 'test database'); (2) automated execution + result comparison (column-level then dataframe-level, per Snowflake's Evaluator Agent); (3) LLM-as-judge on responses (Databricks framework uses Claude Sonnet as judge, generating recommendations mapped to specific config changes); judges calibrated against human raters via Cohen's kappa; (4) trajectory-based scorers in MLflow 3 that assess the full agent path (tool choices, intermediate steps), not just final answers, with identical judges reused for production monitoring on traces; (5) human feedback capture (thumbs up/down, expert review UIs); (6) canary queries — known-good questions fired through production hourly, drift-alerting before users complain. Databricks Agent Bricks automates steps 1-3: auto-generates task-specific synthetic eval data and custom LLM judges from a task description, then auto-optimizes (prompts, fine-tuning, reward models) against them along a cost/quality frontier.

**Evidence.** Databricks Genie playbook: iterate test->judge->fix 3-5 cycles to 90%+ before rollout, then monthly review cycles for emerging questions. MLflow 3 (2025) ships this as product. Agent Bricks (June 2025) demonstrates automated eval-generation + optimization as a managed service. RAG-side surveys: ~70% of production RAG teams have NO systematic retrieval eval — the loop is best practice, not median practice.

**Relevance to this project.** This eval loop IS the limitation-detection engine the brief asks for: judge outputs mapped to specific configuration recommendations (Databricks' pattern) are literally machine-generated improvement proposals with evidence attached — store them as audit records. Agent Bricks proves eval-generation itself can be automated, so the harness can bootstrap evals for new objectives without waiting for humans. Trajectory scoring localizes WHICH step (retrieval vs SQL-gen vs reasoning) failed — required for routing improvements to the right subsystem.

**Failure modes.** LLM judges disagree with humans (hence kappa calibration requirement) and can be gamed by the very system they evaluate if both share models/prompts; golden sets go stale as schemas and questions drift; synthetic eval data inherits generator blind spots; monthly-cycle cadence too slow for schema-drift-class regressions (canaries needed); judge cost at production scale is nontrivial.

### What actually breaks in enterprise text-to-SQL deployments

**Mechanism.** Failure taxonomy from production postmortems: (a) SILENT SEMANTIC ERRORS — fan-out join inflation (one-to-many join before aggregation, SUM 5x too high, executes cleanly), NULL semantics (SUM treats NULL as 0; WHERE status != 'cancelled' drops NULL rows; NOT IN + NULL subquery returns zero rows), date handling (no real-time clock, BETWEEN off-by-one, timezone conversions rarely generated), ambiguous business nouns (revenue/active-user meaning varies by team -> metric drift: same metric, different numbers). (b) COST/PERFORMANCE — missing WHERE on 10TB tables, non-sargable predicates (LOWER(email)=...), DISTINCT masking join bugs, correlated subqueries, N+1 loops in multi-agent systems (501 round trips vs 1). (c) SECURITY — prompt injection in questions, RLS bypass via broad service accounts, users asserting identities in-prompt, ToxicSQL backdoor (poisoning 0.44% of fine-tune data -> 85.8% attack success), CVE-2024-5565 RCE. (d) DRIFT — column renames break prompts weekly; systems degrade silently as schemas/definitions evolve. Standard defense: 4 layers — dynamic schema retrieval + business glossary; pre-execution AST/policy validation (sqlglot, EXPLAIN row-count gates, DDL rejection, table whitelists); read-only scoped credentials + DB-level RLS via session variables + statement timeouts + full query logging; post-execution result validation (second-model sanity check, row-count/sign checks, human confirmation for high-stakes tables).

**Evidence.** Uber QueryGPT: 20+ iterations to production; multi-agent decomposition (Intent -> Table -> Column Prune agents) required because naive similarity search over schemas failed and 200-column tables consumed 40-60K tokens; even then only ~50% table-selection overlap with ground truth on real queries — yet still saves ~140,000 hours/month across ~1.2M monthly queries because assisted-drafting has value below full autonomy. Enterprise accuracy 10-31% without context stack vs 94-99% with (practitioner reports). AWS reference architecture enforces multi-tenant RLS in Postgres via app-set session variables so the LLM may generate anything and the DB still filters.

**Relevance to this project.** Each failure class maps to a limitation type the harness must detect: metric drift -> ambiguous-metric detection (ask HITL for canonical definition); column rename breakage -> schema-drift monitor diffing information_schema against semantic model; cost cliffs -> EXPLAIN-based cost gate whose rejections are improvement signals; silent semantic errors -> result-validation layer whose flags feed the eval set. Uber's outcome reframes success criteria: 50-90% accuracy with human-in-loop review still yields massive measured value — full autonomy is not the feasibility bar.

**Failure modes.** This IS the failure-mode catalog; meta-failure: teams measure only hard errors, so silent wrong answers (the majority) never enter the feedback loop — the harness must actively generate verification signals rather than wait for user complaints.

### RAG over enterprise knowledge bases at scale

**Mechanism.** Production-grade enterprise RAG = hybrid retrieval (BM25 + dense) + reranking as baseline, permission-trimmed at query time, over continuously re-ingested multi-source corpora (SharePoint, wikis, Slack, DMS). Glean's architecture: a real-time knowledge graph of entities (people, projects, customers, documents) and relationships instead of flat chunks; every result filtered against the querying user's ACLs; ranking personalized via graph signals (popularity, department affinity, expertise). Canary query systems fire known-good queries hourly and alert on ranking/answer drift.

**Evidence.** ~73% of enterprise RAG deployment failures attributed to knowledge-base maintenance (stale docs, coverage gaps, extraction quality), not model quality; 'freshness gap' is the most common silent failure (old chunks outrank re-published docs because retrievers score similarity, not recency); ~70% of production RAG teams have no systematic retrieval eval; teams prioritizing latency over exotic retrieval saw better satisfaction. Glean valued at $7.2B (2026), preferred 1.9x vs ChatGPT in one enterprise evaluation; its permission-aware graph is the de facto enterprise bar. Industry interview study (arXiv 2508.14066) confirms evaluation and freshness as top practitioner pain points.

**Relevance to this project.** The harness's vector-DB/knowledge-base leg needs ops-level self-monitoring, not just better prompts: corpus freshness deltas, coverage gaps vs incoming question distribution, extraction quality, and ACL fidelity are all machine-detectable limitations. Auto-generated canary queries per source are a cheap, auditable self-improvement artifact. Permission-aware retrieval is non-negotiable for enterprise: improvements must never widen effective access (an audit-checked invariant).

**Failure modes.** Stale-chunk wins; deleted/re-permissioned documents leaking through lagging indices; chunking destroying table/structure semantics; multi-source authority conflicts (wiki vs Slack tribal knowledge); eval blindness; per-query ACL checks adding latency that users punish.

### Multi-source query planning (SQL + lake + vector) 

**Mechanism.** Three patterns in production/research: (1) ROUTER/INTENT: a router agent classifies the question and dispatches to SQL agent vs RAG agent vs graph agent (dynamic multi-agent orchestration, arXiv 2412.17964; Uber's Intent->Workspace mapping); (2) FEDERATED PLANNER: orchestrator decomposes into sub-queries per backend (Postgres, Mongo, Neo4j, Redis, Milvus), generates candidate plans, selects by weighted cost (complexity + estimated time), then joins/synthesizes (DAG-orchestrated planner for hybrid data lakes, arXiv 2603.14229; Dremio-style federation for the SQL leg); (3) COLLAPSED BACKEND: push vector + relational into one engine so hybrid search runs in a single SQL query joined against application tables with tenant filters (Databricks Lakebase Search, 2026 — 'agent-native retrieval' in Postgres).

**Evidence.** Mostly research prototypes plus early product moves; no published enterprise accuracy numbers for cross-source planning comparable to Spider 2.0. The market signal is consolidation: Databricks (Lakebase, managed MCP over UC+Genie+Vector Search) and Snowflake (Cortex Analyst + Cortex Search 'better together' — structured + unstructured in one agent) are building the multi-source plane into the platform rather than leaving it to external orchestrators.

**Relevance to this project.** The baseline harness is exactly pattern (1)+(2); the self-improvement loop can learn routing policy from outcomes (which source answered which question class correctly — logged evidence becomes router training data), and can propose plan-template library additions. Cost-based plan selection gives a numeric substrate for improvement claims in the audit log ('new plan template reduced cost X%, same answer'). Watch platform-native MCP endpoints: long-term, the harness's planner may orchestrate governed MCP tools rather than raw connections.

**Failure modes.** Router misclassification silently answers from the wrong source; cross-source joins on inconsistent entity keys; cost estimates wrong for LLM-generated predicates; latency multiplication across hops; each backend has separate permission models — the plan must intersect them or leak; N+1 explosion when agents loop instead of batching.

### MCP / tool-registry patterns for governed data access

**Mechanism.** Emerged 2025-2026 pattern: expose data capabilities as MCP tools governed by the data catalog. Databricks managed MCP servers front Unity Catalog data, Vector Search indexes, Genie spaces, and UC functions; on-behalf-of-user auth propagates the caller's identity so existing UC permissions apply. Unity AI Gateway (2026) makes an 'MCP Service' a Unity Catalog securable with a three-level name; Service Policies (UC functions attached to registered MCPs) evaluate EVERY tool call before execution; the gateway also tracks agent cost and centralizes audit. Cube exposes its semantic layer via MCP/A2A so any external agent lists measures/dimensions and queries by name. Snowflake, Fivetran, Collibra, Alation announced equivalents for Q3-Q4 2026.

**Evidence.** Shipping products (Databricks managed MCP GA docs; Unity AI Gateway blog). Security literature (arXiv 2511.20920, Hou et al., eSentire/SentinelOne guides): documented attack classes — tool poisoning via malicious tool descriptions/metadata, credential aggregation (MCP server holding OAuth tokens for many services = single point of failure), rug-pull tool updates; the public MCP registry requires only repo/domain ownership (no code review or scanning) — first malicious MCP package (Sept 2025) exfiltrated email undetected for two weeks. Recommended controls: server allowlisting w/ cryptographic verification, least-privilege per-user auth, mandatory human approval for high-risk operations, per-call audit logging.

**Relevance to this project.** Adopt 'tools as governed securables' as the harness's tool-registry design: every tool (including tools the harness creates for itself during self-improvement) gets registered, policy-wrapped, identity-propagating, and per-call logged — which simultaneously satisfies the AUDIT requirement. Self-created or newly-installed tools are exactly the tool-poisoning surface, so new-tool admission is a mandatory HITL gate. On-behalf-of-user auth answers the permissioning failure mode: the agent can never answer with data the asking user couldn't see.

**Failure modes.** Registry trust theater (listed != safe); token concentration in the MCP layer; tool-description injection steering the agent; policy functions themselves misconfigured; broad service-account MCP servers silently bypassing per-user RLS; version drift between tool schema and backing data.

### Decision-support agents and recommendation validation

**Mechanism.** Two production archetypes. (1) CLOSED-LOOP DECISIONING (Hightouch AI Decisioning): RL agents choose message/offer/channel/timing per customer within marketer-set constraints; every policy is measured against a randomized HOLDOUT group for incremental lift vs business metrics; an Insights layer mines the agents' own experiment logs for significant patterns and surfaces recommendations (add/refresh/retire content) to humans. (2) ONTOLOGY-GATED ACTIONS (Palantir AIP): decisions decomposed into data + logic + actions over a governed Ontology; AI can only STAGE actions, which default to human review before execution; fine-grained control over who may invoke an action, test-driven publishing of changes, batch stage-and-review, detailed per-event logs; organizations 'surgically' graduate well-worn AI processes to auto-execution. AIP Evals provides test cases, cross-LLM comparison, and variance analysis for agent logic. Classic NBA stacks (Pega, IQVIA) blend predictive scores + business rules + arbitration, now with LLMs generating plain-English audit explanations.

**Evidence.** Hightouch reports 10B+ AI-made marketing decisions with lift measured vs holdouts (vendor numbers, but the holdout methodology is the point). Palantir's staged-action + audit-log design is documented platform behavior across government/industrial deployments. No credible public accuracy numbers exist for open-ended 'recommend a business action' agents — validation is causal (experiments) or procedural (human gates), never LLM-judge-only.

**Relevance to this project.** Directly answers the brief's decision-support and HITL/audit requirements: (a) recommendations should carry validation plans (holdout/backtest/counterfactual where feasible) rather than confidence scores; (b) adopt the Palantir trust ladder for BOTH business actions and self-improvements — stage, human-review, log, and only graduate specific well-worn improvement types (e.g., adding a verified query) to auto-apply; (c) Hightouch's Insights-mining-agent-logs pattern is a self-improvement mechanism: mine the harness's own execution traces for significant patterns and convert them to proposed improvements with evidence attached.

**Failure modes.** Objective misspecification ('maximize revenue' without margin/churn guards -> degenerate policies); holdouts infeasible for one-shot strategic decisions (fall back to backtesting/simulation, which can overfit history); RL feedback loops contaminating their own training data; human review fatigue rubber-stamping staged actions; explanations rationalizing rather than reflecting the actual decision path.

### Self-improvement mechanisms with production evidence (prompt/skill/workflow evolution)

**Mechanism.** GEPA (Genetic-Pareto, in DSPy): reflective prompt evolution — LLM reads execution traces of failures, reasons in natural language about WHY a prompt failed, proposes targeted mutations, maintains a Pareto frontier across eval instances; optimizes prompts, tool descriptions, and code with model weights frozen. Nous Research's Hermes self-evolution applies DSPy+GEPA to evolve agent skills/prompts/tool-descriptions end-to-end for $2-10 per run, no GPUs. Reflexion-style loops store natural-language lessons from failed attempts in memory; AFlow-style search evolves multi-step workflow graphs. Snowflake's agentic semantic-model improvement (see above) is the same idea specialized to semantic models. Databricks Agent Bricks productizes the outer loop (auto-evals -> auto-optimization across prompt/fine-tune/reward-model levers, cost-quality frontier). Survey: 'Self-Evolving Agents' (arXiv 2507.21046) taxonomizes what/when/how to evolve.

**Evidence.** GEPA: outperforms RL-based GRPO by ~6% avg (up to 20%) with up to 35x fewer rollouts; beats MIPROv2 by >10% on AIME-2025; production adoption documented at Decagon (test-driven GEPA for customer-support agents). MAS-PromptBench (2026) tempers this: prompt optimization gains in MULTI-AGENT systems are uneven — sometimes negligible vs single-agent gains. Production consensus: prompt/context optimization preferred over fine-tuning for cost and rollback safety.

**Relevance to this project.** Supplies the harness's concrete improvement-operator library, each with different risk/audit profiles: (low risk) add verified query / retrieval example / memory lesson; (medium) GEPA-evolve prompts and tool descriptions offline against the golden set, deploy behind eval gate; (higher) evolve workflow/plan templates; (highest, HITL-mandatory) new tools/code. Every operator is trace-driven and eval-gated, which makes 'what changed, why, evidence' audit entries natural byproducts. Cost matters for the brief's feasibility experiments: $2-10/optimization run means nightly self-improvement cycles are economically trivial next to warehouse query costs.

**Failure modes.** Overfitting to the eval set (improvement on goldens, regression on live traffic — need held-out and canary validation); multi-agent prompt optimization may not transfer (MAS-PromptBench); self-referential evaluation (optimizer and judge sharing blind spots); improvement churn destabilizing user-visible behavior without versioning/rollback; unbounded exploration spending tokens without lift caps.

## Sources

- <https://www.databricks.com/blog/aibi-genie-now-generally-available>
- <https://medium.com/@salah.uddin_75300/production-ready-databricks-genie-a-framework-for-ai-powered-analytics-2725e6a98abd>
- <https://docs.databricks.com/en/genie/trusted-assets.html>
- <https://www.snowflake.com/en/blog/engineering/cortex-analyst-text-to-sql-accuracy-bi/>
- <https://www.snowflake.com/en/blog/engineering/agentic-semantic-model-text-to-sql/>
- <https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-repository>
- <https://www.snowflake.com/en/blog/engineering/cortex-analyst-cortex-search-integration/>
- <https://spider2-sql.github.io/>
- <https://github.com/xlang-ai/Spider2>
- <https://www.vldb.org/cidrdb/papers/2026/p5-jin.pdf>
- <https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/>
- <https://github.com/Canner/WrenAI>
- <https://www.getwren.ai/post/why-the-semantic-layer-is-essential-for-reliable-text-to-sql-and-how-wren-ai-brings-it-to-life>
- <https://github.com/vanna-ai/vanna>
- <https://www.getwren.ai/post/wren-ai-vs-vanna-the-enterprise-guide-to-choosing-a-text-to-sql-solution>
- <https://sudiptapathak.com/blog/dissecting-open-source-nl2sql/>
- <https://www.getdbt.com/blog/open-source-metricflow-governed-metrics>
- <https://upsolve.ai/blog/dbt-semantic-layer>
- <https://cube.dev/blog/announcing-cube-d3>
- <https://cube.dev/articles/semantic-layer-for-ai-agents-2026>
- <https://tianpan.co/blog/2026-04-10-text-to-sql-failure-modes-production>
- <https://omni.co/blog/why-text-to-sql-fails>
- <https://infinisynapse.com/en/blog/why-text-to-sql-fails>
- <https://www.uber.com/en-CA/blog/query-gpt/>
- <https://aws.amazon.com/blogs/machine-learning/multi-tenant-llm-analytics-with-row-level-security-how-we-built-a-secure-agent-on-aws/>
- <https://dev.to/gabrielanhaia/70-of-enterprise-rag-deployments-fail-before-production-heres-what-kills-them-26ml>
- <https://ragaboutit.com/5-rag-failure-modes-enterprise-devs-are-hiding-from-you/>
- <https://arxiv.org/pdf/2508.14066>
- <https://docs.glean.com/security/knowledge-graph>
- <https://rmax.ai/notes/enterprise-ai-agents-knowledge-layer-beyond-rag/>
- <https://arxiv.org/html/2603.14229v1>
- <https://arxiv.org/pdf/2412.17964>
- <https://www.databricks.com/blog/announcing-lakebase-search-agent-native-retrieval-built-lakebase-postgres>
- <https://www.databricks.com/blog/announcing-managed-mcp-servers-unity-catalog-and-mosaic-ai-integration>
- <https://www.databricks.com/blog/ai-gateway-governance-layer-agentic-ai>
- <https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp>
- <https://arxiv.org/html/2511.20920v1>
- <https://www.esentire.com/blog/model-context-protocol-security-critical-vulnerabilities-every-ciso-should-address-in-2025>
- <https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/>
- <https://learn.microsoft.com/en-us/azure/databricks/generative-ai/agent-evaluation/llm-judge-metrics>
- <https://www.databricks.com/blog/introducing-agent-bricks>
- <https://hightouch.com/platform/ai-decisioning>
- <https://hightouch.com/blog/aid-10-billion-marketing-decisions>
- <https://hightouch.com/blog/ai-experiments>
- <https://blog.palantir.com/connecting-agents-to-decisions-277dee8ddb40>
- <https://www.palantir.com/docs/foundry/aip/overview>
- <https://github.com/gepa-ai/gepa>
- <https://decagon.ai/blog/optimizing-gepa-for-production>
- <https://www.blog.brightcoding.dev/2026/06/22/stop-writing-prompts-manually-hermes-agent-self-evolution-does-it-for-2>
- <https://arxiv.org/pdf/2507.21046>
- <https://arxiv.org/pdf/2606.23664>
