import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import CrmTestPage from "@/app/crm-test/page";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const trace = {
  label: "CRM TEST WORKSPACE - SYNTHETIC / DEVELOPER TEST DATA",
  meaning: "CRM-reported Customer is not proof of an active contract or revenue.",
  semantic_as_of: "2026-10-04T21:37:20Z",
  workspace_id: "workspace",
  state_engine_version: "1.2.0",
  external_side_effects: false,
  accounts: [
    {
      account_id: "account-customer",
      company_name: "M2C Customer Test",
      domain: "m2c-customer.example.com",
      synthetic: true,
      relationship_evidence: [
        {
          evidence_id: "evidence",
          fact_key: "relationship.crm_reports_customer_status",
          assertion: "PRESENT",
          observed_at: "2026-10-04T21:37:00Z",
          freshness_at_as_of: "WITHIN_24_HOURS",
          mapper_key: "crm_customer_stage",
          mapper_version: "1.0.0",
          normalization_result_id: "normalization",
          source_observation_id: "observation",
          source_read_run_id: "run",
          provider_company_id: "123",
          provider_scope_sha256: "scopehash",
          source_category: "private_crm_company",
          source_stage_value: "customer",
          configured_customer_stage: "customer",
        },
      ],
      state: {
        id: "state",
        fit: "MATCH",
        timing: "ACTIVE",
        relationship: "EXISTING_RELATIONSHIP",
        sufficiency: "SUFFICIENT",
        input_hash: "hash",
      },
      decision: {
        id: "decision",
        result: "ENGAGE",
        state_snapshot_id: "state",
        reason_codes: ["ACTIVE_TIMING_SUPPORTS_ENGAGEMENT"],
      },
      policy: {
        id: "policy",
        result: "REQUIRE_REVIEW",
        decision_evaluation_id: "decision",
        reason_codes: ["EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING"],
      },
      action: { id: "action", type: "CREATE_SELLER_TASK", policy_evaluation_id: "policy" },
    },
  ],
};

describe("local M2C CRM test trace", () => {
  it("does not fetch or expose private CRM data in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      CrmTestPage({ searchParams: Promise.resolve({ as_of: trace.semantic_as_of }) }),
    ).rejects.toThrow("not found");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("labels CRM-reported provenance and a proposal without claiming execution", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => trace }));
    render(await CrmTestPage({ searchParams: Promise.resolve({ as_of: trace.semantic_as_of }) }));
    expect(screen.getByText("CRM TEST DATA")).toBeInTheDocument();
    expect(screen.getByText("M2C Customer Test")).toBeInTheDocument();
    expect(screen.getByText(/not proof of an active contract or revenue/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /No CRM write, external seller task, outreach, or commercial outcome occurred/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/CREATE_SELLER_TASK/)).toBeInTheDocument();
    expect(
      screen.getByText(/EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING/),
    ).toBeInTheDocument();
    expect(screen.getByText(/relationship.crm_reports_customer_status/)).toBeInTheDocument();
  });
});
