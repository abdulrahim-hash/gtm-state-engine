import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountDetailScreen } from "@/components/account-detail-screen";
import { SignalCard } from "@/components/signal-card";
import { StrategyScreen } from "@/components/strategy-screen";
import type {
  AccountDetail,
  AccountSignalEvaluations,
  AccountSignals,
  ActiveStrategy,
  EvidenceList,
  SignalReadModel,
} from "@/lib/api";

const evidence = {
  id: "1a1206b7-243c-4f22-8d7f-53aa00000207",
  strategy_version_id: null,
  account_id: "1a1206b7-243c-4f22-8d7f-53aa00000013",
  strategy_topic: null,
  classification: "FACT" as const,
  source_provider: "synthetic_demo_fixture",
  source_reference: "synthetic://northstar/evidence/relationship",
  source_uri: null,
  observed_at: "2026-09-14T12:00:00Z",
  ingested_at: "2026-09-15T12:05:00Z",
  normalized_fact:
    "Synthetic demo observation: an existing relationship condition is recorded as evidence.",
  raw_payload_hash: "a".repeat(64),
  freshness: "CURRENT" as const,
  confidence: null,
  fact_key: null,
  fact_assertion: null,
};

const strategyFixture: ActiveStrategy = {
  workspace: {
    workspace_id: "1a1206b7-243c-4f22-8d7f-53aa00000001",
    slug: "northstar-revenue-systems-demo",
    name: "Northstar Revenue Systems Demo",
    demo_mode: true,
    demo_as_of: "2026-09-15T12:00:00Z",
  },
  strategy: {
    id: "1a1206b7-243c-4f22-8d7f-53aa00000002",
    workspace_id: "1a1206b7-243c-4f22-8d7f-53aa00000001",
    semantic_version: "1.0.0",
    status: "ACTIVE",
    name: "Northstar synthetic GTM strategy",
    summary: "A deterministic public fixture.",
    synthetic_disclaimer: "Synthetic demo only. Not a validated market finding.",
    created_at: "2026-09-15T12:00:00Z",
    activated_at: "2026-09-15T12:00:00Z",
    claims: [
      {
        ...evidence,
        id: "1a1206b7-243c-4f22-8d7f-53aa00000101",
        account_id: null,
        strategy_version_id: "1a1206b7-243c-4f22-8d7f-53aa00000002",
        strategy_topic: "MARKET",
        classification: "HYPOTHESIS",
        confidence: "0.60",
      },
    ],
  },
};

const accountFixture: AccountDetail = {
  workspace: strategyFixture.workspace,
  account: {
    id: evidence.account_id ?? "",
    workspace_id: strategyFixture.workspace.workspace_id,
    slug: "cinderlake-revenue-studio",
    canonical_name: "Cinderlake Revenue Studio",
    domain: "cinderlake-revenue-studio.example",
    segment: "Synthetic growth-stage B2B operations teams",
    is_synthetic: true,
    created_at: "2026-09-15T12:00:00Z",
    updated_at: "2026-09-15T12:00:00Z",
  },
};

const signalDefinition = {
  signal_definition_id: "1a1206b7-243c-4f22-8d7f-53aa00000401",
  workspace_id: strategyFixture.workspace.workspace_id,
  strategy_version_id: strategyFixture.strategy.id,
  stable_key: "new_revenue_leader",
  display_name: "New revenue leader",
  description: "Synthetic commercial leadership event.",
  category: "LEADERSHIP" as const,
  input_fact_key: "commercial_event.new_revenue_leader",
  evaluator_key: "latest_assertion_with_freshness",
  freshness_window_days: 90,
  rule_version: "1.0.0",
  status: "ENABLED" as const,
  created_at: "2026-09-15T12:00:00Z",
};

const signalEvaluation = {
  evaluation_id: "1a1206b7-243c-4f22-8d7f-53aa00000601",
  workspace_id: strategyFixture.workspace.workspace_id,
  account_id: accountFixture.account.id,
  signal_definition_id: signalDefinition.signal_definition_id,
  strategy_version_id: strategyFixture.strategy.id,
  signal_id: "1a1206b7-243c-4f22-8d7f-53aa00000501",
  evaluation_as_of: "2026-09-15T12:00:00Z",
  evaluated_at: "2026-09-15T12:10:00Z",
  input_hash: "b".repeat(64),
  result: "DETECTED" as const,
  reason_code: "QUALIFYING_EVENT_WITHIN_WINDOW" as const,
  rule_version: "1.0.0",
  created_at: "2026-09-15T12:10:00Z",
};

const signalItem: SignalReadModel = {
  signal: {
    signal_id: signalEvaluation.signal_id,
    workspace_id: strategyFixture.workspace.workspace_id,
    account_id: accountFixture.account.id,
    signal_definition_id: signalDefinition.signal_definition_id,
    strategy_version_id: strategyFixture.strategy.id,
    event_fingerprint: "c".repeat(64),
    observed_at: "2026-09-14T12:00:00Z",
    first_detected_at: "2026-09-15T12:10:00Z",
    origin_evaluation_id: signalEvaluation.evaluation_id,
    created_at: "2026-09-15T12:10:00Z",
  },
  definition: signalDefinition,
  current_evaluation: signalEvaluation,
  current_status: "ACTIVE",
  current_freshness: "CURRENT",
  evidence: [
    {
      ...evidence,
      id: "1a1206b7-243c-4f22-8d7f-53aa00000305",
      fact_key: "commercial_event.new_revenue_leader",
      fact_assertion: "PRESENT",
    },
  ],
};

const signalsFixture: AccountSignals = {
  workspace: strategyFixture.workspace,
  account_id: accountFixture.account.id,
  items: [signalItem],
};

const evaluationsFixture: AccountSignalEvaluations = {
  workspace: strategyFixture.workspace,
  account_id: accountFixture.account.id,
  items: [
    {
      evaluation: signalEvaluation,
      definition: signalDefinition,
      evidence: signalItem.evidence,
    },
    {
      evaluation: {
        ...signalEvaluation,
        evaluation_id: "1a1206b7-243c-4f22-8d7f-53aa00000602",
        signal_definition_id: "1a1206b7-243c-4f22-8d7f-53aa00000402",
        signal_id: null,
        result: "INCONCLUSIVE",
        reason_code: "REQUIRED_EVIDENCE_MISSING",
      },
      definition: {
        ...signalDefinition,
        signal_definition_id: "1a1206b7-243c-4f22-8d7f-53aa00000402",
        stable_key: "sales_team_hiring_expansion",
        display_name: "Sales-team hiring expansion",
        category: "HIRING",
        input_fact_key: "commercial_event.sales_team_hiring_expansion",
        freshness_window_days: 45,
      },
      evidence: [],
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("M1A data views", () => {
  it("renders synthetic hypotheses and the fixed snapshot date", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => strategyFixture }),
    );

    render(<StrategyScreen />);

    expect(await screen.findByText("Northstar synthetic GTM strategy")).toBeInTheDocument();
    expect(screen.getByText("HYPOTHESIS")).toBeInTheDocument();
    expect(screen.getByText("September 15, 2026")).toBeInTheDocument();
    expect(screen.getByText(/not a validated market finding/i)).toBeInTheDocument();
  });

  it("renders account provenance without converting relationship evidence into state", async () => {
    const evidenceFixture: EvidenceList = { items: [evidence] };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => accountFixture })
        .mockResolvedValueOnce({ ok: true, json: async () => evidenceFixture })
        .mockResolvedValueOnce({ ok: true, json: async () => signalsFixture })
        .mockResolvedValueOnce({ ok: true, json: async () => evaluationsFixture }),
    );

    render(<AccountDetailScreen accountId={accountFixture.account.id} />);

    expect(await screen.findByText("Cinderlake Revenue Studio")).toBeInTheDocument();
    expect(screen.getByText("FACT")).toBeInTheDocument();
    expect(screen.getByText("Payload hash")).toBeInTheDocument();
    expect(screen.getByText(/relationship context is evidence here/i)).toBeInTheDocument();
    expect(screen.getAllByText("New revenue leader")).toHaveLength(2);
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.getByText(/1 inconclusive/i)).toBeInTheDocument();
    expect(screen.getByText("Deterministic events only")).toBeInTheDocument();
  });

  it("renders stale canonical events as expired without adding priority or score", () => {
    render(
      <SignalCard
        item={{
          ...signalItem,
          current_evaluation: {
            ...signalEvaluation,
            result: "STALE",
            reason_code: "QUALIFYING_EVENT_OUTSIDE_WINDOW",
          },
          current_status: "EXPIRED",
          current_freshness: "STALE",
        }}
      />,
    );

    expect(screen.getByText("EXPIRED")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.queryByText(/priority|score/i)).not.toBeInTheDocument();
  });

  it("does not fabricate UI data when a read request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    render(<StrategyScreen />);

    expect(await screen.findByText(/No fallback data is fabricated/i)).toBeInTheDocument();
  });
});
