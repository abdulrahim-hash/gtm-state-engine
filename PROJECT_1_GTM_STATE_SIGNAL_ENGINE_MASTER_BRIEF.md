# Project 1 — GTM State & Signal Engine
## Master Product, GTM Strategy, Engineering, Evaluation, and Portfolio Brief

**Status:** Canonical build brief  
**Purpose:** Recruiter-facing flagship GTM Engineering project + genuinely usable open-source GTM infrastructure  
**Repository working name:** `gtm-state-engine`  
**Product working name:** **GTM State & Signal Engine**  
**Tagline:** **Know who matters, why now, and what to do next — with evidence.**

---

# 0. Executive decision

Build one production-style, vendor-neutral GTM system that turns fragmented market/account/customer data into a trustworthy **account state**, detects commercially meaningful **signals**, makes auditable **next-best-action decisions**, activates those actions through GTM tools, measures downstream outcomes, and improves future policies through controlled learning.

This is **not** an “AI SDR,” a Clay workflow, an n8n demo, a lead scraper, a generic email writer, or a Jev showcase.

Tools will be used heavily, but they are implementation components inside the architecture. The project must remain understandable and valuable even if an individual vendor is swapped out.

The project must demonstrate that the builder understands both:

1. **GTM fundamentals:** market, segmentation, ICP, buying committee, problem, value proposition, offer, pricing, messaging, channel, motion, experiments, economics.
2. **GTM engineering:** data contracts, identity, signals, APIs, SQL/Python, CRM, AI, decisioning, orchestration, observability, reliability, attribution, experimentation, and controlled learning.

The core product question is:

> **Given everything we know about an account right now, should the GTM team spend scarce attention on it, why, who should be engaged, and what action should happen next?**

---

# 1. Why this project exists

Modern GTM teams have more data, signals, tools, accounts, channels, and possible actions than sellers can process manually.

Relevant information is fragmented across:

- CRM records
- enrichment providers
- websites
- hiring pages
- funding/news
- product and website events
- email/outbound activity
- calls and notes
- contact/job changes
- ad engagement
- seller activity
- third-party intent
- human research

The technical problem is not simply collecting more data.

The harder problem is converting noisy, inconsistent, time-sensitive evidence into a reliable answer to:

- Does this account fit?
- Why now?
- Which signal is real and commercially relevant?
- Who in the buying committee matters?
- What does the team already know about this account?
- Is there an active opportunity, customer relationship, or suppression reason?
- Which GTM play is appropriate?
- Should the action be automatic, human-reviewed, or blocked?
- Did the action create a qualified reply, meeting, opportunity, pipeline, or revenue?
- What should be changed based on outcomes?

The system is therefore a **GTM decision and control plane**, not merely outbound automation.

---

# 2. Audience and hiring signal

## Primary users

- GTM Engineers
- Revenue Operations teams
- Growth Engineers
- Technical RevOps
- Sales Operations
- Growth / outbound teams
- Small B2B revenue teams that need a trustworthy decision layer across existing tools

## Primary portfolio audience

- GTM Engineering hiring managers
- RevOps / Growth Engineering hiring managers
- technical founders
- GTM operators
- potential remote employers
- technically sophisticated clients

## What a recruiter should conclude

After reviewing the project, a strong recruiter should be able to say:

> This person can understand the commercial problem, translate strategy into system logic, build the data and integration layer, use AI with controls, operate the system reliably, and measure whether it creates revenue outcomes.

They should **not** conclude merely:

> This person knows Clay, n8n, HubSpot, or how to prompt an LLM.

---

# 3. Public product experience

The project must have two equally important surfaces.

## 3.1 Hosted interactive product

A recruiter must be able to open a live URL without installing anything.

The public demo should be safe, read-only by default, and use clearly labeled synthetic/demo data.

The core recruiter experience should be:

**10 seconds:** Understand the business problem from the landing/dashboard.

**2 minutes:** Open an account and see account state, signals, evidence, and a recommendation.

**10 minutes:** Explore strategy, decision trace, workflow health, experiment results, and architecture.

**30+ minutes:** Open GitHub and inspect code, tests, schemas, ADRs, evals, workflow design, and reliability controls.

## 3.2 Public GitHub repository

The repository must prove the system is real and inspectable:

- source code
- SQL
- migrations
- typed schemas
- tests
- eval datasets without sensitive data
- architecture documentation
- ADRs
- demo fixtures
- integration adapters
- sanitized workflow exports where relevant
- runbooks
- changelog
- CI
- screenshots
- live demo link
- limitations
- roadmap

No production secrets, prospect PII, client data, or hidden live credentials may be committed.

---

# 4. Product thesis

The project is based on five connected ideas.

## 4.1 GTM strategy must govern automation

Bad strategy should not be automated faster.

Before the system can decide what to do, it needs an explicit definition of:

- market
- segment
- ICP
- buyer / buying committee
- customer problem
- value proposition
- offer
- pricing / packaging hypothesis
- messaging
- channel
- GTM motion
- experiments
- success metrics

These must not remain only in a Notion page. The important parts become **versioned, machine-readable configuration**.

## 4.2 Tools are adapters

Clay, Apollo, HubSpot, n8n, Smartlead, HeyReach, Slack, Jev, OpenAI/Anthropic, data providers, and other vendors plug into the system.

They do not own the system's identity, logic, or history.

## 4.3 AI gives judgment; policy gives authority

LLMs or decision models may classify, summarize, interpret, rank, or recommend.

They must not silently become the production control plane.

The system's **policy layer** decides whether an action is:

- allowed
- blocked
- human-reviewed
- automatically executed

## 4.4 Evidence and provenance are mandatory

Any meaningful conclusion must be traceable to evidence.

An account should never be labeled “high intent” or “sales expansion” without being able to answer:

- what evidence produced the conclusion
- where the evidence came from
- when it was observed
- how fresh it is
- which rule/model/version interpreted it
- how confident the system is
- what changed since the last state

## 4.5 Learning is controlled, not autonomous self-modification

The system can improve from outcomes, but it must not freely rewrite its own strategy or production policy.

The loop is:

**Outcome → analysis → proposed change → evaluation/test → human approval → new version → deployment.**

---

# 5. Canonical operating loop

The system operates around:

**STRATEGY → OBSERVE → UNIFY → INTERPRET → DECIDE → ACTIVATE → MEASURE → LEARN**

Strategy governs the loop rather than merely preceding it.

### Strategy
What market, segment, ICP, buyer, problem, offer, message, channel, and motion are we testing?

### Observe
What new evidence, events, and signals exist?

### Unify
Which account/contact does each observation belong to? What is the canonical current state?

### Interpret
What does the evidence mean? Is a signal commercially relevant? Which buyer/persona is involved?

### Decide
Given strategy, state, evidence, risk, cost, and confidence, what should happen?

### Activate
Create the appropriate CRM task, review request, message draft, sequence action, Slack alert, or other actuator.

### Measure
Capture reply, meeting, opportunity, pipeline, cost, seller time, errors, overrides, and time-to-action.

### Learn
Compare outcomes across cohorts and policy versions, then propose controlled changes.

---

# 6. GTM strategy layer

The project must visibly demonstrate GTM thinking, not hide it behind code.

## 6.1 Strategy objects

Every workspace must support versioned definitions for:

### Market
- category
- geography
- market constraints
- buying environment
- competitive alternatives
- maturity assumptions

### Segmentation
- firmographic segments
- behavioral segments
- trigger/signal-based segments
- lifecycle segments
- priority segments
- explicit exclusions

### ICP
- required conditions
- positive-fit criteria
- negative-fit criteria
- exclusion gates
- size/maturity bands
- tech / operational conditions
- evidence requirements
- reason codes

### Buyer / buying committee
- economic buyer
- champion
- technical evaluator
- user
- influencer
- blocker
- procurement/security where relevant
- role/title mappings
- persona hypotheses
- buying-stage relevance

### Problem
- business problem
- operational symptoms
- economic impact
- current alternative
- switching cost
- urgency / trigger conditions
- evidence supporting the hypothesis

### Value proposition
- target buyer
- target problem
- desired outcome
- differentiated mechanism
- proof required
- claim boundaries

### Offer
- deliverable/outcome
- scope
- qualification rules
- CTA
- implementation model
- guarantee/risk reversal only if evidence supports it

### Pricing / packaging
- package hypotheses
- segment-to-package logic
- economic assumptions
- pricing evidence
- discount/exception rules if relevant

### Messaging
- buyer
- trigger
- problem hypothesis
- value hypothesis
- proof
- objections
- CTA
- allowed claims
- prohibited/unsupported claims
- customer language / voice-of-customer evidence

### Channels
- email
- LinkedIn
- calls
- ads
- CRM tasks
- inbound
- partner
- other relevant channels

### GTM motion
- outbound
- inbound
- PLG/PQL
- ABM
- sales-led
- partner-led
- hybrid
- stage transitions
- ownership / handoff rules

### Experiments and measurement
- hypothesis
- treatment
- comparison/control
- primary metric
- secondary metrics
- minimum evidence
- stop conditions
- decision rule

---

# 7. Strategy evidence discipline

Every strategic statement should be labeled as one of:

- **FACT** — directly supported by a source or observed business data.
- **INFERENCE** — interpretation derived from facts.
- **HYPOTHESIS** — plausible but unvalidated assumption requiring a test.

Codex/LLMs must not turn hypotheses into facts.

Research should follow:

**Manual understanding → schema definition → programmatic collection → analysis at scale → human GTM judgment.**

Tools should do repetitive research, but the builder must understand enough of the market to know what to collect and how to interpret it.

A sensible research cycle is:

1. Manually inspect a representative sample of company websites, competitor pages, reviews, job descriptions, community discussions, or call notes.
2. Define a structured research schema.
3. Use APIs, enrichment, search, scraping where permitted, and data tools to collect at scale.
4. Analyze patterns with Python/SQL and AI-assisted synthesis.
5. Form explicit GTM hypotheses.
6. Test them through the product.

---

# 8. Demo workspace

The public hosted demo must not pretend to contain real customer/prospect data.

Use a **synthetic but realistic B2B SaaS workspace** with a clearly disclosed demo strategy.

Example demo company:

**Northstar Revenue Systems**  
Fictional product: revenue infrastructure / GTM operations software for scaling B2B SaaS companies.

Example demo market hypothesis:

- B2B SaaS
- 50–500 employees
- scaling sales organization
- relevant triggers include a new revenue leader, SDR/AE hiring, funding, market expansion, CRM migration, or increased website intent
- primary demo buyers: VP Sales, Head of RevOps, CRO depending on state
- the specific criteria are demo hypotheses, not claimed universal truth

The demo must contain multiple account types:

- strong fit + strong timing
- strong fit + weak timing
- weak fit + strong signal
- existing customer/suppressed
- active opportunity
- ambiguous/low-confidence
- stale signal
- conflicting evidence
- missing data

This gives recruiters real edge cases to explore.

---

# 9. Core data model

The canonical database is the system memory.

## 9.1 Strategy entities

### `workspaces`
- workspace_id
- name
- demo_mode
- created_at

### `strategy_versions`
- strategy_version_id
- workspace_id
- version
- status
- valid_from
- created_by
- approval_state
- created_at

### `strategy_evidence`
- evidence_id
- strategy_version_id
- section
- statement
- evidence_type: FACT | INFERENCE | HYPOTHESIS
- source_uri
- source_title
- observed_at
- notes

### `icp_rules`
- rule_id
- strategy_version_id
- criterion
- operator
- expected_value
- weight
- hard_gate
- reason_code

### `buyer_definitions`
- buyer_id
- strategy_version_id
- persona
- role_patterns
- buying_role
- stage_relevance
- notes

### `plays`
- play_id
- strategy_version_id
- name
- trigger_conditions
- buyer
- problem
- value_prop
- CTA
- allowed_channels
- approval_policy

---

## 9.2 Canonical GTM entities

### `accounts`
Minimum:
- account_id
- workspace_id
- canonical_domain
- name
- industry
- size_band
- geography
- lifecycle_state
- crm_external_id
- owner_id
- created_at
- updated_at

### `contacts`
Minimum:
- contact_id
- account_id
- full_name
- title
- persona
- buying_role
- email
- email_verification_state
- suppression_state
- crm_external_id
- source
- created_at
- updated_at

### `evidence`
Minimum:
- evidence_id
- account_id
- contact_id nullable
- evidence_type
- source_provider
- source_uri
- observed_at
- ingested_at
- raw_payload_hash
- excerpt / normalized_fact
- confidence nullable
- extraction_method
- freshness_state

### `signals`
Minimum:
- signal_id
- account_id
- signal_type
- observed_at
- ingested_at
- source_provider
- evidence_ids
- strength
- confidence
- freshness
- decay_policy_version
- status
- normalized_payload

### `account_state_snapshots`
Minimum:
- snapshot_id
- account_id
- strategy_version_id
- generated_at
- fit_score
- timing_score
- signal_score
- evidence_confidence
- buying_committee_coverage
- relationship_state
- opportunity_state
- risk_flags
- active_signal_ids
- summary
- state_hash

### `scores`
Minimum:
- score_id
- account_id
- strategy_version_id
- policy_version
- fit_score
- timing_score
- signal_score
- priority_score
- confidence_score
- risk_penalty
- cost_penalty
- reason_codes
- computed_at

### `decisions`
Minimum:
- decision_id
- account_id
- state_snapshot_id
- policy_version
- strategy_version_id
- candidate_actions
- selected_action
- selected_play_id
- selected_buyer
- reason_codes
- confidence
- approval_requirement
- decision_status
- created_at

### `model_runs`
Used for Jev, LLMs, or other probabilistic services:
- model_run_id
- account_id
- decision_id nullable
- provider
- model
- task_type
- prompt/schema/version
- input_hash
- evidence_refs
- structured_output
- confidence
- latency_ms
- cost_estimate
- status
- human_label
- human_override
- created_at

### `actions`
Minimum:
- action_id
- decision_id
- account_id
- action_type
- channel
- adapter
- dry_run
- payload_hash
- idempotency_key
- approval_state
- execution_state
- external_id
- scheduled_at
- executed_at

### `outcomes`
Minimum:
- outcome_id
- account_id
- decision_id nullable
- action_id nullable
- outcome_type
- qualified
- value nullable
- currency nullable
- observed_at
- source
- external_id
- notes

### `experiments`
Minimum:
- experiment_id
- strategy_version_id
- hypothesis
- treatment
- comparison
- primary_metric
- secondary_metrics
- pre_registered_at
- status
- decision_rule

### `experiment_assignments`
- assignment_id
- experiment_id
- account_id
- cohort
- assigned_at

### `workflow_runs`
- run_id
- workflow_name
- version
- correlation_id
- started_at
- finished_at
- status
- attempts
- records_processed
- records_failed
- error_code
- error_detail
- cost_estimate

### `dead_letter_items`
- dlq_id
- run_id
- entity_type
- entity_id
- payload_hash
- error_code
- last_successful_stage
- retry_count
- status
- created_at

### `cost_ledger`
- cost_id
- provider
- operation
- account_id nullable
- run_id nullable
- units
- estimated_cost
- currency
- occurred_at

### `suppressions`
- suppression_id
- entity_type
- entity_id
- reason
- source
- effective_from
- effective_until nullable
- created_at

---

# 10. Source-of-truth policy

The architecture should be explicit.

## PostgreSQL / Supabase
Analytical/event source of truth:
- normalized entities
- raw/normalized observations
- signals
- state snapshots
- scoring
- decisions
- model runs
- actions
- outcomes
- experiments
- costs
- workflow history

## HubSpot
Operational seller-facing source of truth where the adapter is enabled:
- owner
- lifecycle state
- rep tasks
- active opportunities
- seller notes/context
- external operational IDs

## Clay / Apollo / enrichment providers
Data suppliers only.

They must never be the canonical identity layer.

## n8n
Optional orchestration/integration surface, not business logic source of truth.

Core business logic should remain inspectable and testable in code/config where practical.

---

# 11. Identity and data quality

Identity resolution is first-class.

The system must support:

- canonical domain normalization
- company-name normalization
- alternate domain handling
- duplicate detection
- CRM/provider alias mapping
- contact normalization
- stable internal IDs
- source conflict handling
- field-level provenance where useful
- record merge audit trail
- replay safety

No incoming provider ID should automatically become the canonical identity.

The public demo must include deliberately messy fixtures to prove the identity layer works.

---

# 12. Signal architecture

A **signal** is not merely an event.

It is an observed change that may have commercial relevance to the active GTM strategy.

Potential signal types include:

- new executive / revenue leader
- SDR/AE hiring
- employee growth
- funding
- market expansion
- technology adoption/change
- CRM migration
- pricing-page or high-intent website activity
- product usage
- champion job change
- competitor adoption
- relevant company/news event
- engagement with outbound/ads
- opportunity-stage change
- account inactivity / relationship decay

Each signal must track:

- evidence
- timestamp
- source
- freshness
- strength
- confidence
- decay
- strategy relevance
- whether it is active/stale/rejected

The system must distinguish:

**raw observation → normalized evidence → candidate signal → validated/interpreted signal → account state.**

---

# 13. Account State

The key product object is **Account State**.

A recruiter should be able to open an account and immediately see:

### Identity
Who is the company?

### Fit
How closely does it match the active ICP?

### Why now
Which fresh signals matter?

### Buying committee
Who appears relevant? Which roles are missing?

### Relationship
Have we contacted this account? Are they a customer? Is there an active opportunity? Are they suppressed?

### Timing
Cold / emerging / active / urgent, or another explicit bounded state.

### Evidence quality
How strong and complete is the evidence?

### Risks
Duplicate, bad data, active customer, live opportunity, suppression, low confidence, stale signal, deliverability concern.

### Recommended play
Which play, buyer, and channel are recommended?

### Decision trace
Why did the system make this recommendation?

### State change
What changed since the previous snapshot?

---

# 14. Deterministic decisioning first

V1 must be explainable before it is intelligent.

A recommended sequence:

## Stage 1 — eligibility gates
Examples:
- wrong geography
- excluded segment
- current customer
- suppressed
- active opportunity where outbound should be blocked
- missing critical evidence

## Stage 2 — ICP fit
Versioned strategy rules produce:
- fit score
- reason codes
- hard-gate failures

## Stage 3 — timing/signals
Use:
- signal type
- freshness
- strength
- combinations
- evidence quality
- strategy relevance

## Stage 4 — probabilistic judgment where useful
Use bounded model tasks only when rules are insufficient.

## Stage 5 — policy
The policy combines:
- eligibility
- fit
- timing
- confidence
- risk
- cost
- capacity
- existing relationship
- selected play

## Stage 6 — action gate
Output:
- block
- monitor
- enrich
- human review
- create CRM task
- draft message
- activate channel

Every decision must store:
- policy version
- strategy version
- inputs
- outputs
- reason codes
- confidence
- evidence references

---

# 15. Jev, LLM, rules, and human evaluation

Jev is interesting because it is a newly launched decision-model approach, but the project must never become dependent on Jev.

Jev should be implemented behind a provider interface and feature flag.

Candidate bounded tasks:

1. Signal relevance classification
2. Buyer / persona classification
3. Timing state classification
4. GTM play selection
5. Reply intent classification
6. Evidence sufficiency / ambiguity classification

For each task, compare where practical:

- deterministic rules
- Jev
- a small general LLM
- a stronger LLM
- human labels

The purpose is **not** to prove Jev wins.

The purpose is to answer:

> Which kinds of GTM decisions should be deterministic, which benefit from a bounded decision model, which require generative/reasoning models, and which should remain human?

Evaluation metrics may include:

- accuracy
- macro F1
- precision / recall
- false-positive rate
- false-negative rate
- Brier score / calibration for probability outputs
- abstention rate
- human-review rate
- human override rate
- latency
- cost per 1,000 decisions
- unsupported-claim rate where generation is involved

Initial eval set:
- 50 carefully labeled examples to validate the harness

Target:
- 250–500+ labeled examples as the project matures

Jev/model confidence must **not** be treated as ground truth.

---

# 16. AI research and copywriting rules

AI may help with:

- account research synthesis
- signal interpretation
- buyer classification
- evidence normalization
- messaging variants
- reply classification
- structured summaries
- experiment analysis
- research synthesis

However:

**Research → strategy → copy.**

Never:

**prompt → copy → pretend it is GTM strategy.**

Before generating a message, the system should know:

- buyer
- trigger
- problem hypothesis
- value proposition
- selected play
- proof/evidence
- objections
- CTA
- claim boundaries

Generated copy must be constrained by those inputs.

No unsupported company facts may be introduced.

Where possible, copy claims should cite or reference supporting evidence internally.

---

# 17. Policy and human review

Model output is advisory unless a policy explicitly authorizes an action.

Example policy concepts:

### Auto
Allowed for low-risk internal actions such as:
- update internal state
- create a CRM task
- create an internal Slack alert
- queue enrichment

### Human review
Required when:
- evidence is incomplete
- confidence is medium
- multiple plays are plausible
- external copy will be sent
- the account is high-value
- model outputs disagree
- suppression/relationship state is ambiguous

### Block
Required when:
- current customer
- active opportunity and policy forbids outbound
- unsubscribe / DNC
- invalid contact
- prohibited geography/segment
- insufficient required data
- policy conflict

The system should expose the gate visibly in the UI.

---

# 18. Activation layer

V1 must demonstrate action, but the public demo must remain safe.

Supported V1 concepts:

- dry-run action preview
- HubSpot task/note creation adapter
- Slack alert adapter
- message draft generation
- generic webhook adapter
- optional outbound adapter behind a disabled-by-default feature flag

Future adapters may include:
- Smartlead
- Instantly
- HeyReach
- ads audiences
- calling tools
- other CRMs

External sends should not be required for the hosted public demo.

The architecture should make adding a new actuator an adapter problem rather than a rewrite.

---

# 19. Outcome capture and attribution

The system must close the loop.

Outcome types can include:

- positive reply
- negative reply
- timing reply
- meeting booked
- qualified meeting
- opportunity created
- opportunity stage change
- closed-won
- closed-lost
- pipeline value
- unsubscribe
- bounce
- no response
- seller override
- customer/suppression discovered after decision

Each outcome should be linkable to:
- account
- decision
- action
- signal
- strategy/policy version
- experiment cohort where relevant

Avoid claiming causality when only correlation exists.

Where practical, use:
- treatment/control
- matched comparison
- pre-registered hypotheses
- cohort analysis

---

# 20. Metrics

## Business metrics

Primary when real outcomes exist:

**Qualified pipeline generated per unit of GTM resource**

Resource includes:
- data/enrichment cost
- model/API cost
- tool cost
- seller time where measurable

Supporting:
- signal → qualified meeting rate
- activated account → opportunity rate
- pipeline per activated account
- cost per qualified account
- time-to-action
- qualified reply rate
- meeting quality
- opportunity quality
- seller research time saved

## System metrics

- data-quality pass rate
- identity resolution rate
- missing-required-data rate
- workflow failure rate
- retry rate
- DLQ volume
- model error rate
- human override rate
- decision abstention rate
- source freshness
- integration latency
- cost per processed account
- duplicate prevention rate

Do not optimize for:
- send volume
- raw open rate
- number of automations
- number of tools
- number of AI agents

---

# 21. Controlled learning loop

The system should improve without becoming ungoverned.

Required loop:

1. Capture outcomes.
2. Compare by signal, segment, play, buyer, channel, and policy version.
3. Identify a potential change.
4. Write a change hypothesis.
5. Evaluate historically or in a controlled test.
6. Require human approval.
7. Create a new policy/strategy version.
8. Deploy.
9. Measure again.

No automatic production rewrite of:
- ICP
- weights
- messaging policy
- channel policy
- pricing
- offer
- thresholds

without an explicit governed promotion process.

Advanced Bayesian allocation, contextual bandits, predictive scoring, or self-optimizing policies are **later extensions only after enough labeled outcome data exists**.

---

# 22. Reliability and production engineering

The system should not require the builder to sit beside it.

## Non-negotiable standards

### Idempotency
Replaying a job must not duplicate:
- accounts
- contacts
- tasks
- sends
- actions
- outcomes

### Retries
Transient failures:
- retry with bounded exponential backoff

Permanent failures:
- stop and route to repair/DLQ

### Dead-letter path
Store:
- entity
- payload hash
- error
- attempts
- last successful stage
- next repair action

### Structured logging
Every critical workflow logs:
- run_id
- correlation_id
- workflow/version
- entity IDs
- duration
- result
- attempts
- error
- cost

### Data contracts
Validate:
- required fields
- types
- enum values
- ownership
- source
- timestamps
- schemas at boundaries

### External writes
Must use:
- stable idempotency keys
- dry-run mode
- validation
- explicit overwrite rules

### Secrets
- environment variables / secret store
- `.env.example` only
- no keys in Git
- secret scanning in CI where possible

### Cost guardrails
- per-provider cost logging
- daily/weekly caps where practical
- abnormal-cost alerts
- no unbounded model/enrichment loops

### Observability
Hosted demo should include a **System Health** page with:
- recent runs
- failures
- retries
- DLQ
- integration status
- latency
- cost
- data quality

### Recovery
Write runbooks for:
- provider outage
- rate limit
- duplicate webhook
- malformed LLM/model output
- stale data
- CRM write failure
- invalid enrichment
- queue backlog
- secret rotation
- migration rollback

---

# 23. Privacy, safety, and data governance

Public repository and demo:
- synthetic/demo companies and people unless using non-sensitive public company-level examples
- no real prospect PII
- no client secrets
- no production CRM exports
- no access tokens
- no hidden live write capability in public demo

Production-capable code should support:
- suppression / opt-out
- data minimization
- retention policies
- audit history
- source/provenance
- configurable compliance rules
- no automation designed to evade platform or legal controls

---

# 24. Technical architecture

## 24.1 Recommended stack

### Frontend
**Next.js + TypeScript**

Why:
- polished recruiter-facing product
- strong UI ecosystem
- typed contracts
- deployable to Vercel

### Backend / decision services
**Python + FastAPI**

Why:
- Python is highly relevant to GTM/data/AI engineering
- good for rules, data processing, model evaluation, connectors, and API work

### Database
**PostgreSQL via Supabase**

Why:
- canonical relational/event data
- SQL analytics
- migrations
- easy hosted demo
- vector support later if actually required

### Validation
- Pydantic on Python boundaries
- TypeScript schema validation on frontend/API boundaries

### Background work
Start with a **database-backed job/outbox pattern + Python worker**.

Requirements:
- retry state
- idempotency
- DLQ
- observable run history

Avoid introducing Kafka/Temporal/etc. in V1 unless an actual need emerges.

### Orchestration
**n8n as an optional integration/orchestration adapter**, not the location of irreplaceable business logic.

Version sanitized n8n workflows if used.

### CRM
**HubSpot adapter** for V1.

The public demo may use mocked/sandbox behavior.

### Enrichment/data providers
Provider interfaces for:
- Clay
- Apollo
- generic REST/data source
- CSV import
- demo fixtures

Do not require paid providers for the public demo.

### Model layer
Provider interface supporting:
- deterministic rules
- Jev
- OpenAI/Anthropic or other general LLM
- stub/fake provider for tests

### Deployment
The architecture should remain portable.

Practical hosted-demo shape:
- Next.js frontend on Vercel
- Supabase Postgres
- FastAPI/worker on a suitable container service
- Docker Compose for local development

Do not make the project dependent on one hosting vendor.

---

# 25. Logical architecture

```text
                         ┌───────────────────────────┐
                         │       GTM STRATEGY        │
                         │ Market / ICP / Buyer      │
                         │ Offer / Messaging / Motion│
                         │ Experiments / Policies    │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
┌──────────────┐   ┌──────────────┐   ┌────────────────────┐
│ CRM / CSV    │   │ Clay/Apollo  │   │ Web / Product /    │
│ Activity     │   │ Enrichment   │   │ External Signals   │
└──────┬───────┘   └──────┬───────┘   └─────────┬──────────┘
       └──────────────────┬┴──────────────────────┘
                          ▼
                 ┌───────────────────┐
                 │ INGESTION / EVENTS│
                 │ schema + run IDs  │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │ IDENTITY + EVIDENCE│
                 │ canonical entities │
                 │ provenance         │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │ SIGNAL ENGINE      │
                 │ freshness / decay  │
                 │ relevance          │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │ ACCOUNT STATE      │
                 │ trustworthy snapshot│
                 └─────────┬─────────┘
                           ▼
        ┌────────────────────────────────────┐
        │ DECISION / MODEL SERVICES          │
        │ rules | Jev | LLM | human labels  │
        └──────────────────┬─────────────────┘
                           ▼
                 ┌───────────────────┐
                 │ POLICY ENGINE      │
                 │ allow/review/block │
                 │ play + buyer       │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │ ACTIVATION         │
                 │ HubSpot / Slack    │
                 │ draft / webhook    │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │ OUTCOMES           │
                 │ replies / meetings │
                 │ opps / pipeline    │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │ ANALYTICS / LEARN  │
                 │ cohorts / evals    │
                 │ policy proposals   │
                 └───────────────────┘
```

---

# 26. Hosted UI specification

The UI must be polished, uncluttered, and GTM-native.

Avoid generic AI-dashboard visual noise.

## 26.1 Dashboard / Command Center

Show:
- accounts monitored
- new signals
- accounts activated
- human review queue
- blocked/suppressed
- workflow health
- recent decisions
- high-priority state changes

Example:

```text
GTM STATE COMMAND CENTER

847 Accounts Monitored

38 New Signals      12 Activated
7 Human Review      19 Suppressed

LIVE STATE CHANGE

Acme AI                                  92 Priority

State: ACTIVE BUYING WINDOW

New VP Sales                         +++
6 SDR roles                           +++
Series B                              ++
Employee growth                       ++

ICP Fit                               91%
Timing                                87%
Evidence Confidence                   93%

Recommended Play: Sales Expansion

[View Account] [View Decision]
```

## 26.2 Strategy page

Show active strategy version:
- market
- segment
- ICP
- buyer map
- problem
- value proposition
- offer
- pricing hypothesis
- messaging
- channel/motion
- active experiments

Clearly distinguish:
- facts
- inferences
- hypotheses

## 26.3 Accounts page

Filter/sort by:
- priority
- state
- ICP fit
- timing
- signal
- strategy segment
- approval status
- opportunity/customer status
- evidence quality

## 26.4 Account detail

Must include:
- account state summary
- score breakdown
- why now
- evidence timeline
- active/stale signals
- buying committee
- CRM relationship
- risk/suppression
- previous decisions
- state changes
- selected play
- activation history
- outcomes

## 26.5 Decision Trace

This is a flagship screen.

Show:
- strategy version
- account-state snapshot
- deterministic rule results
- model/Jev/LLM judgments
- confidence
- disagreements
- policy gates
- selected action
- reason codes
- evidence refs
- human review/edit
- final executed action

## 26.6 Review Queue

Show accounts/actions requiring human judgment.

Reviewer can:
- approve
- reject
- change play
- change buyer
- add note
- request more evidence

The action and edit are logged.

## 26.7 Experiments

Show:
- hypothesis
- treatment/control
- primary metric
- cohort sizes
- outcomes
- status
- limitations
- decision

Do not fake statistical certainty.

## 26.8 System Health

Show:
- workflow runs
- failure rate
- retries
- DLQ
- provider health
- latency
- cost
- data-quality failures
- stale-source warnings

## 26.9 Architecture / About

A recruiter should understand system boundaries in under 60 seconds.

Include:
- architecture diagram
- core loop
- source-of-truth policy
- tool/adapters
- GitHub link
- live-demo disclaimer

---

# 27. Repository structure

Recommended monorepo:

```text
gtm-state-engine/
├── AGENTS.md
├── README.md
├── LICENSE
├── CHANGELOG.md
├── .env.example
├── .github/
│   └── workflows/
├── apps/
│   ├── web/                    # Next.js / TypeScript
│   └── api/                    # FastAPI
├── workers/
│   └── jobs/                   # background processing
├── packages/
│   ├── contracts/              # shared API/data contracts
│   └── ui/                     # optional shared UI
├── strategy/
│   ├── README.md
│   ├── market.md
│   ├── segmentation.md
│   ├── icp.md
│   ├── buyers.md
│   ├── problem.md
│   ├── value-proposition.md
│   ├── offer.md
│   ├── pricing.md
│   ├── messaging.md
│   ├── channels.md
│   ├── motion.md
│   └── experiments.md
├── config/
│   ├── demo-strategy.yaml
│   ├── icp.yaml
│   ├── signal-registry.yaml
│   ├── plays.yaml
│   └── policies.yaml
├── src/
│   ├── ingestion/
│   ├── identity/
│   ├── evidence/
│   ├── signals/
│   ├── state/
│   ├── scoring/
│   ├── decisioning/
│   ├── policy/
│   ├── activation/
│   ├── outcomes/
│   ├── attribution/
│   ├── experiments/
│   ├── models/
│   └── observability/
├── integrations/
│   ├── hubspot/
│   ├── clay/
│   ├── apollo/
│   ├── slack/
│   ├── generic_webhook/
│   ├── n8n/
│   └── model_providers/
├── sql/
│   ├── migrations/
│   ├── quality/
│   ├── funnel/
│   ├── attribution/
│   ├── experiments/
│   └── reliability/
├── evals/
│   ├── datasets/
│   ├── labels/
│   ├── runners/
│   └── reports/
├── fixtures/
│   └── demo/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── e2e/
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── source-of-truth.md
│   ├── security.md
│   ├── demo.md
│   ├── decisions/
│   ├── experiments/
│   ├── runbooks/
│   ├── build-journal/
│   └── screenshots/
└── scripts/
```

We may simplify the exact folders during bootstrap if Codex can justify a cleaner layout. Do not preserve folders merely for aesthetics.

---

# 28. Codex operating model

Codex is a development and analysis partner, not the source of business truth.

## Codex should be used for

- repository bootstrap
- schema/migrations
- APIs
- data pipelines
- normalization
- connectors
- frontend
- backend
- workers
- tests
- eval harness
- SQL
- documentation
- refactors
- debugging
- fixture generation
- implementation plans
- research structuring/synthesis when supplied with evidence
- copy variants when supplied with approved GTM strategy inputs

## Codex must not

- invent market facts
- silently define the ICP without evidence
- convert a hypothesis into a finding
- change production GTM strategy without approval
- bypass tests because a demo “looks right”
- commit secrets
- add a major tool because it looks impressive
- create huge autonomous-agent complexity without a measured need
- trigger live external outreach by default
- rewrite history to make the project story look cleaner

## Durable repo instructions

Use a root `AGENTS.md` for stable project rules, architecture constraints, testing expectations, and evidence discipline.

OpenAI Codex supports repository-scoped instructions through `AGENTS.md`; keep durable instructions there rather than repeating them in every task.

## Optional skills later

Create reusable skills only when a workflow repeats enough to justify them, for example:

- `gtm-strategy-research`
- `gtm-experiment-review`
- `gtm-integration-adapter`
- `gtm-eval-run`

Avoid bloating context with too many instructions before a repeatable need exists.

---

# 29. Git and proof-of-work standard

The Git history is part of the portfolio.

Requirements:

- small coherent commits
- meaningful commit messages
- no filler commits
- issues/milestones for meaningful work
- ADR for material architecture changes
- build journal preserving what was believed at the time
- negative findings remain visible
- changelog for releases
- tagged public releases
- no giant “initial commit” containing the complete final project
- no fake commit history

A meaningful contribution can be:
- research memo
- schema change
- data-quality query
- unit test
- eval result
- architecture decision
- integration
- UI vertical slice
- reliability improvement
- experiment result

---

# 30. Testing strategy

## Unit tests
For:
- canonicalization
- dedupe logic
- scoring
- signal decay
- policy gates
- cost calculations
- reason-code generation

## Integration tests
For:
- database
- adapters
- webhooks
- model providers with mocks
- job worker
- idempotent external writes

## Contract tests
For:
- provider payloads
- API schemas
- frontend/backend shared contracts
- CRM mapping

## E2E
At least:
- seed account
- ingest evidence
- resolve identity
- generate signal
- build account state
- create decision
- require/skip review according to policy
- create dry-run action
- capture outcome
- reflect updated analytics

## Failure tests
Must deliberately test:
- duplicate webhook
- provider timeout
- malformed model output
- stale signal
- missing required evidence
- blocked customer
- invalid contact
- retry exhaustion

---

# 31. First vertical slice

Before building every connector, get one complete flow working with demo fixtures:

```text
Demo Strategy
      ↓
Seed Account + Evidence
      ↓
Identity Resolution
      ↓
Signal Detection
      ↓
Account State
      ↓
Deterministic Decision
      ↓
Policy Gate
      ↓
Dry-Run CRM Action
      ↓
Synthetic Outcome
      ↓
Dashboard / Decision Trace
```

This vertical slice should be visible in the hosted app as early as possible.

Do not wait until every provider integration is complete.

---

# 32. Milestones

## M0 — Repository and engineering foundation
Deliver:
- monorepo/repo layout
- root `AGENTS.md`
- architecture docs
- environment setup
- CI
- local database
- migrations
- health endpoints
- basic Next.js shell
- FastAPI shell
- typed contracts
- demo-mode banner
- first ADRs

Exit:
- fresh clone can run locally
- tests pass
- CI passes
- no secrets

## M1 — Strategy + canonical model + seeded vertical slice
Deliver:
- strategy schema
- synthetic demo workspace
- canonical account/contact/evidence tables
- seed fixtures
- basic dashboard
- account detail
- deterministic demo decision

Exit:
- recruiter can see one account from evidence to decision

## M2 — Ingestion, identity, evidence, signals
Deliver:
- CSV/demo ingestion
- provider interface
- domain normalization/dedupe
- evidence provenance
- signal registry
- freshness/decay
- state snapshots
- messy-data fixtures/tests

Exit:
- multiple demo accounts produce traceable state

## M3 — Decision and policy engine
Deliver:
- ICP rules
- signal/timing scoring
- reason codes
- eligibility gates
- policy versions
- play selection
- review requirements
- decision trace UI

Exit:
- recommendation is reproducible from stored state/config

## M4 — Jev / LLM evaluation layer
Deliver:
- provider abstraction
- Jev feature-flag adapter if access is available
- LLM adapter
- human-label schema
- initial 50-example eval set
- benchmark runner
- latency/cost/error report
- no direct model-triggered external sends

Exit:
- rules vs model comparisons can be reproduced

## M5 — Activation and human review
Deliver:
- review queue
- HubSpot adapter or sandbox/mock
- Slack/generic webhook adapter
- dry-run messaging/action preview
- idempotency keys
- action audit trail

Exit:
- approved decision creates a safe visible action

## M6 — Outcomes, attribution, experiments
Deliver:
- outcome ingestion
- action → decision → signal trace
- cohort/experiment model
- experiment dashboard
- cost ledger
- qualified outcome analytics

Exit:
- system closes the loop from state to measured outcome

## M7 — Reliability hardening
Deliver:
- queue/outbox worker
- retries
- backoff
- DLQ
- health page
- cost guardrails
- structured logs
- runbooks
- failure-mode tests
- recovery tests

Exit:
- system does not require constant babysitting for normal failures

## M8 — Public release and recruiter package
Deliver:
- hosted demo
- polished README
- architecture diagram
- case study
- screenshots
- 6–8 minute Loom
- 60–90 second short demo
- tagged release
- limitations
- roadmap
- benchmark/eval report
- portfolio integration
- LinkedIn build/results posts

Exit:
- recruiter can understand, use, and inspect the project without your assistance

---

# 33. Public README structure

1. Product name + one-line value proposition
2. Live Demo | Architecture | Demo Video | Docs
3. The GTM problem
4. What the system does
5. 60-second workflow
6. Screenshots
7. Architecture
8. GTM strategy model
9. Account state
10. Decision/policy model
11. Jev/rules/LLM eval
12. Reliability
13. Integrations
14. Local setup
15. Demo data disclaimer
16. Tests
17. Results/benchmarks
18. Limitations
19. Roadmap
20. Contributing
21. License

---

# 34. Portfolio case-study narrative

The story should be:

> Modern GTM teams can collect more data and signals than they can reliably act on. The difficult problem is not enrichment; it is maintaining a trustworthy account state and deciding who deserves attention, why now, and what action should happen next. I built a strategy-aware GTM State & Signal Engine that unifies evidence, resolves identity, detects signals, makes auditable policy-governed decisions, activates safe actions, and traces outcomes back to the original state and decision. I then evaluated where deterministic rules, bounded decision models such as Jev, general LLMs, and human review each fit.

Do not make Jev the headline.

Do not make a vendor the headline.

---

# 35. Content / distribution plan

The project can become a build-in-public series.

Potential posts:

### Thesis
“GTM increasingly has a decision problem, not a data problem.”

### Architecture
“How I model account state instead of stacking disconnected automations.”

### Evidence
“Why every GTM AI recommendation in my system has provenance.”

### Reliability
“What CI/CD thinking looks like inside revenue workflows.”

### Jev experiment
“Where does a System One decision model fit in GTM? I tested rules vs Jev vs LLMs.”

### Failure
A real technical/GTM failure and what changed.

### Benchmark
Accuracy, latency, cost, calibration, and human-review comparison.

### Release
Live demo + GitHub + architecture + lessons.

Posts must report real findings, including negative/inconclusive results.

---

# 36. Anti-overengineering rules

Do **not** add in V1 unless evidence requires it:

- autonomous multi-agent “company”
- contextual bandits
- predictive revenue model
- Kafka
- Kubernetes
- complex vector/RAG layer
- paid ads execution
- every outbound channel
- full CRM replacement
- live production multitenancy/billing
- huge scraping infrastructure
- automatic pricing changes
- automatic ICP rewrites
- uncontrolled AI actions

A smaller, reliable, measured system is stronger than a complicated demo.

---

# 37. Explicit non-goals

This project is not:

- an AI SDR
- a generic CRM
- an email generator
- a Clay template
- an Apollo scraper
- an n8n workflow collection
- a chatbot
- a generic RAG app
- a pure lead scorer
- a Jev demo
- a synthetic “revenue uplift” claim

Those may exist as components only if they serve the system thesis.

---

# 38. V1 Definition of Done

Project 1 is V1-complete only when all of the following are true:

- A public hosted demo works.
- A recruiter can use the demo without credentials.
- Demo data is clearly synthetic.
- Strategy is visible and versioned.
- At least one full account goes evidence → signal → state → decision → policy → action → outcome.
- Identity resolution/dedupe is implemented and tested.
- Signals store evidence, timestamp, source, freshness, and confidence.
- Account state is reproducible.
- Deterministic rules are versioned and reason-coded.
- Model/Jev outputs are structured, logged, and never treated as source of truth.
- An eval harness exists with labeled examples.
- Human review and override are logged.
- External writes have idempotency and dry-run controls.
- Outcomes trace back to decisions/signals.
- A basic experiment/cohort model exists.
- Cost is tracked.
- Retries and DLQ exist.
- Workflow health is visible.
- Failure modes are tested.
- No secrets or real prospect PII exist in the public repo.
- README is recruiter-readable.
- Architecture is understandable in under 60 seconds.
- Git history is meaningful.
- There is a public demo video/Loom.
- Limitations and negative findings are documented.
- The project can run without Jev if Jev is unavailable.

---

# 39. First build target

The immediate target is **not** Clay, HubSpot, Jev, or a giant dashboard.

The immediate target is:

> **One fully traceable synthetic account moving through strategy → evidence → signal → account state → deterministic decision → policy gate → dry-run action, visible end-to-end in a polished UI and backed by tests.**

That gives the project a real spine.

All integrations can attach to that spine afterward.

---

# 40. First three demo accounts

Create at least these fixtures early.

## Account A — strong fit, active timing
- strong ICP match
- new VP Sales
- multiple SDR openings
- fresh funding
- no existing customer/opportunity
- high evidence coverage
Expected: recommend active play; external action still review-gated in demo.

## Account B — strong fit, weak timing
- strong ICP match
- no fresh signals
- no prior engagement
Expected: monitor/nurture, not immediate outbound.

## Account C — strong signal but blocked
- strong commercial signal
- active opportunity or current-customer state
Expected: block outbound and surface relationship conflict.

Later add ambiguous, stale, low-quality, duplicate, and conflicting-evidence cases.

---

# 41. Initial ADRs

Create these at bootstrap:

- ADR-001: PostgreSQL/Supabase is canonical analytical/event memory.
- ADR-002: HubSpot is an operational adapter, not identity source of truth.
- ADR-003: Strategy is versioned and machine-readable.
- ADR-004: Deterministic policy before model-driven policy.
- ADR-005: Model output cannot directly authorize risky external actions.
- ADR-006: Evidence/provenance required for material conclusions.
- ADR-007: Public demo uses synthetic data.
- ADR-008: Core business logic stays testable outside n8n/vendor UIs.
- ADR-009: Controlled learning requires explicit policy/strategy version promotion.
- ADR-010: Jev is optional and provider-abstracted.

---

# 42. Build journal template

For every meaningful work session:

```text
Date:
Problem:
Evidence / context:
Hypothesis:
Decision:
Implementation:
Validation:
Result:
What failed:
What changed:
Next action:
Related issue/ADR/commit:
```

Preserve history. Do not rewrite early assumptions to look smarter later.

---

# 43. Experiment template

```text
Experiment:
Date pre-registered:
Strategy version:
Policy version:

Hypothesis:

Treatment:

Comparison/control:

Eligibility:

Primary metric:

Secondary metrics:

Guardrails:

Minimum evidence / observation rule:

Stop conditions:

Result:

Limitations:

Decision:
- promote
- keep testing
- modify
- retire

Next version:
```

---

# 44. Decision-eval record template

```text
Task type:
Example ID:
Evidence:
Human label:

Rules output:
Jev output:
Small LLM output:
Strong LLM output:

Confidence:
Latency:
Estimated cost:

Correctness:
Error class:
Human override needed:

Notes:
```

---

# 45. Recruiter demo script target

A final 6–8 minute demo should eventually cover:

**0:00–0:45 — Problem**
Why GTM teams need trustworthy state/decision infrastructure.

**0:45–1:30 — Strategy**
Show ICP/buyer/play configuration.

**1:30–3:00 — Account**
Open a live demo account; show evidence, signal, state.

**3:00–4:15 — Decision**
Show rules/model judgment, policy, reason codes, review gate.

**4:15–5:00 — Activation**
Approve/dry-run action; show CRM/webhook path.

**5:00–6:00 — Outcomes**
Show action → outcome → experiment/attribution.

**6:00–7:00 — Reliability**
Show run history, retries/DLQ, cost, idempotency.

**7:00–8:00 — Engineering**
GitHub, tests, architecture, limitations, what was learned.

---

# 46. Final quality bar

The project is successful if it looks like something a real GTM/RevOps team could use as a foundation, not something built only to pass a portfolio review.

The strongest signal is not the number of technologies.

It is the coherence of:

**GTM reasoning → data model → evidence → decision → policy → action → outcome → learning → reliability.**

That is the standard for Project 1.
