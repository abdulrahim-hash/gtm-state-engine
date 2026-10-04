# M2B controlled real public-data pilot

**Label:** REAL PUBLIC-DATA PILOT · local only · system outcomes only  
**Market:** B2B sales enablement software vendors  
**StrategyVersion:** `0.1.0`, **HYPOTHESIS / COMMERCIALLY UNVALIDATED**  
**Semantic evaluation/state as_of:** `2026-10-05T00:00:00Z` from frozen manifest v2  
**Pilot scope:** technical reasoning, timing, provenance, and governance; not ICP or market validation

## Read the result correctly

The 20 accounts consist of **18 selection-blind BASE_SAMPLE** accounts and **2 disclosed TRACE_COVERAGE** accounts. Their descriptive distributions must remain separate. Any combined count is a *pilot execution count*, never a market prevalence estimate. Fit MATCH means only that verified official public evidence supports the narrow sales enablement software offering criterion. The sampling frame and the criterion overlap intentionally, so Fit distribution does not discriminate commercially attractive buyers. No buying intent, customer pain, willingness to pay, product-market fit, or commercial success has been established.

The first accepted trace yields the following local system outputs:

| Cohort | Accounts | Signal | Fit | Decision | Policy | Action proposal |
| --- | ---: | --- | --- | --- | --- | --- |
| BASE_SAMPLE | 18 | DETECTED 1; INCONCLUSIVE 17 | MATCH 15; INCONCLUSIVE 3 | ENGAGE 1; ABSTAIN 17 | REQUIRE_REVIEW 1; BLOCK 17 | REQUEST_RESEARCH 1; none 17 |
| TRACE_COVERAGE | 2 | STALE 1; INCONCLUSIVE 1 | MATCH 2 | HOLD 1; ABSTAIN 1 | BLOCK 2 | none 2 |

All 20 Relationships are UNKNOWN. No ABSENT Evidence, NO_MATCH Signal, NO_ACTION Decision, ALLOW Policy, external attempt, or commercial outcome was manufactured. The fresh coverage slot is `PILOT_COVERAGE_NOT_MET`; a qualifying fresh event happened to occur in the selection-blind base sample. An INCONCLUSIVE result means verified pilot evidence did not establish the event. STALE means the latest supported pilot evidence is outside the 90-day window; it does not prove no newer event occurred. The two official newsroom items publish calendar dates, not appointment clock times. Their `event_at` values use `00:00:00Z` solely as deterministic UTC date anchors for the announcement date; they do not assert that the appointment happened at midnight. Both dates are far from the 90-day boundary, so this day precision cannot change these two outcomes.

## Sampling, source, and rights boundary

`selection_manifest.v1.json` froze the 23-domain featured-page frame and hash order. Before continuing leadership-event screening, v2 superseded its too-early cutoff while retaining the same roster. The frame came from the G2 Sales Enablement main, enterprise, and small-business category pages at `2026-10-04T09:54:39Z`; it is a limited set of visibly featured seller entries, not the full category. Normalize each domain by lowercasing and removing only `www`, sort by SHA-256 of UTF-8 `gtm-m2b-v1:` plus domain, with domain tie break, and assign the first 18 to BASE_SAMPLE. Screen the five remaining domains in hash order for the two coverage slots. `selection_ledger.v1.json` records the outcome, every queue candidate, no eligibility skips, no post-result replacements, and the unmet slot. No base account was selected because of its leadership, Fit, Signal, prestige, Decision, or Action outcome.

The raw third-party page content and larger roster working file stay local. The public manifest keeps only the 23 normalized domain identifiers needed to recompute the small featured-page frame and coverage queue, plus source URLs, retrieval time, frame description, and roster SHA-256. It does not copy product descriptions, reviews, rankings, or the full directory. The 23-domain frame was manually transcribed from dynamic pages; the committed manifest reproduces the hash selection, while later readers may be unable to reconstruct the exact historic page display from the live source. The CSVs and verification ledger contain only selected public company identifiers, official-source URLs, bounded dates, fact codes, assertions, and short original paraphrases. They contain no full pages, screenshots, long quotations, contact details, or executive names. Source URLs are references to publisher-owned content, not copied content.

For each imported FACT a human checked: the official page exists; its host and company/domain identity agree; the statement supports the exact bounded assertion; the source observation time and any leadership event date are adequate; and the paraphrase adds no unsupported detail. Priority is an official company newsroom/press release for an event and an official product or offering page for a profile. An official careers page or regulatory filing could be considered under a future approved mapping, but none was needed. Secondary reporting can locate or corroborate a claim, but is not an imported FACT under this pilot. No third-party host exception was added to M2A's citation rule. A broad or adjacent offering is INCONCLUSIVE; absent search results are never ABSENT. The importer validates syntax and host constraints without URL fetching; truth verification is manual and recorded in `source_verification.v1.json`.

## Fact, Signal, and Fit contracts

- `public_company_leader_event/1.0.0` maps `commercial_event.new_revenue_leader`, using explicit event_at and official source observation. The existing `new_revenue_leader` Signal has the unchanged inclusive 90-day window.
- `public_sales_enablement_profile/1.0.0` maps `account_profile.offers_sales_enablement_software`. Only PRESENT or INCONCLUSIVE is accepted, with source_observed_at as the fact observation time. Evidence freshness remains UNKNOWN. Pilot State engine `1.1.0` applies its versioned 14-day relative observation rule at the manifest state_as_of. The same page observation becomes Fit UNKNOWN beyond that window. This does not assert that the product stopped existing.
- The Strategy's sole Fit criterion expects profile PRESENT. One pilot Signal is enabled. Sales hiring stays disabled. Relationship has no imported fact and stays UNKNOWN. M1 Decision, Policy, and Action rules are unchanged.
- Strategy Evidence is one bounded G2 category-listing FACT plus five explicit GTM HYPOTHESES for segmentation, ICP, buyer, problem, and internal-research motion. Account facts do not validate these hypotheses. No value proposition, pricing, messaging, channel, outreach, or seller owner is invented.

## Explicit local stage runbook

Requires the local PostgreSQL database and existing project dependencies. Run from repository root. The commands print the semantic as_of, relevant IDs/versions, counts, created/reused identities, and failures. `inspect`, `inspect-signals`, and `inspect-state` are read-only. Stop on any error or unexpected row; do not replace an account for an inconclusive outcome.

```powershell
uv run --project apps/api python apps/api/scripts/pilot_m2b.py setup
uv run --project apps/api python apps/api/scripts/pilot_m2b.py validate
uv run --project apps/api python apps/api/scripts/pilot_m2b.py import
uv run --project apps/api python apps/api/scripts/pilot_m2b.py inspect
# Human verifies every row, batch result, source claim, identity, and ledger entry.
uv run --project apps/api python apps/api/scripts/pilot_m2b.py accept --confirm-reviewed
uv run --project apps/api python apps/api/scripts/pilot_m2b.py signals
uv run --project apps/api python apps/api/scripts/pilot_m2b.py inspect-signals
uv run --project apps/api python apps/api/scripts/pilot_m2b.py state
uv run --project apps/api python apps/api/scripts/pilot_m2b.py inspect-state
uv run --project apps/api python apps/api/scripts/pilot_m2b.py decisions
uv run --project apps/api python apps/api/scripts/pilot_m2b.py policies
uv run --project apps/api python apps/api/scripts/pilot_m2b.py actions
uv run --project apps/api python apps/api/scripts/pilot_m2b.py export
```

Import ends at Evidence. `acceptance.v1.json` binds manifest SHA, roster SHA, workspace and Strategy IDs/version, semantic as_of, exact CSV SHA-256 hashes, batch IDs, mapper/identity versions, and the manual verification ledger SHA. The downstream commands refuse to run unless this record exactly matches current artifacts and DB batch/account state. The acceptance record is a local gate, not authentication. Signals must be materialized and inspected first. State recomputes them internally; exact Signal IDs, input hashes, results, and State links are asserted. Decisions, Policies, and Actions follow only by explicit command. Optional M1D local Review and DRY_RUN can be performed under existing semantics after inspecting the proposal; neither occurred in the accepted pilot run, and no external effect is authorized.

The export writes `trace.v2.json` and `expected_fingerprint.v1.json` with exact-byte immutability checks. Semantic fingerprint schema `m2b_semantic_fingerprint/1.0.0` sorts semantic records and SHA-256 hashes workspace/strategy/definitions, Accounts, SourceObservations, NormalizationResults, current Evidence, SignalEvaluations, StateSnapshots, Decisions, Policies, and Action proposals. It excludes operational timestamps, Review, Attempt, and Outcome. The expected SHA-256 is `0f4a444ce682e39178bfe9816f5a934634b108c4e1e971de18fddb9cd8c531aa`; a clean replay must match. The exported trace carries direct IDs from Action back to its source observation. It contains system outcomes only.

The local UI is `/pilot` and the local read API is `/api/v1/pilot/m2b/trace`. The pilot API returns 404 in production before DB access, and the Next.js pilot page itself returns not-found in a production web process before fetching. The hosted site continues to show only SYNTHETIC DEMO. Do not publish the live pilot database. A sanitized static snapshot would require a separate review.

## Freshness and known limits

Manual profile/event collection was recorded at `2026-10-04T10:19:27Z`; the frozen semantic cutoff is the following midnight UTC. The cutoff was pinned before leadership screening continued and was never moved to change Signal outcomes. These sources represent verified evidence available to this pilot, not complete public observation at the cutoff. The 14-day profile window is a conservative pilot rule, not a market truth. The featured-page frame is a small convenience frame; the 18 base accounts are selection blind within it, not a representative sample of all vendors. The two coverage accounts were screened for trace paths and must never contribute to prevalence statements. No claim of real outreach, seller task, CRM write, response, meeting, opportunity, conversion, or revenue is supported.
