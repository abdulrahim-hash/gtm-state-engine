import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import CrmExecutionPage from "@/app/crm-execution/page";

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
  label: "DEVELOPER TEST EXECUTION",
  message:
    "Synthetic HubSpot developer-test Task. No customer communication or commercial outcome.",
  action_id: "action",
  action_type: "CREATE_SELLER_TASK",
  review_id: "review",
  policy_evaluation_id: "policy",
  decision_evaluation_id: "decision",
  state_snapshot_id: "state",
  plan_id: "plan",
  plan_hash: "plan-hash",
  plan_schema_version: "1.0.0",
  synthetic_company: "M2C Customer Test",
  company_id: "123",
  authority_assurance: "LOCAL_OPERATOR_ATTESTATION",
  authorized: true,
  attempt_status: "CONFIRMED",
  physical_post_count: 1,
  provider_task_id: "456",
  receipt_recorded: true,
  read_back: "CONFIRMED",
  operational_outcome: "CRM_TASK_CONFIRMED_CREATED",
};

describe("local M5A execution trace", () => {
  it("does not fetch or expose execution details in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      CrmExecutionPage({ searchParams: Promise.resolve({ plan_id: "plan" }) }),
    ).rejects.toThrow("not found");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a read-only operational result with no commercial claim", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => trace }));
    render(await CrmExecutionPage({ searchParams: Promise.resolve({ plan_id: "plan" }) }));
    expect(screen.getByText("DEVELOPER TEST EXECUTION")).toBeInTheDocument();
    expect(screen.getByText("M2C Customer Test")).toBeInTheDocument();
    expect(screen.getByText("LOCAL_OPERATOR_ATTESTATION")).toBeInTheDocument();
    expect(screen.getByText("CRM_TASK_CONFIRMED_CREATED")).toBeInTheDocument();
    expect(screen.getByText(/No customer communication occurred/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
  });

  it("does not claim Task creation before reconciliation confirms it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ...trace,
          attempt_status: "NOT_ATTEMPTED",
          operational_outcome: null,
        }),
      }),
    );
    render(await CrmExecutionPage({ searchParams: Promise.resolve({ plan_id: "plan" }) }));
    expect(screen.getByText(/creation is not confirmed/)).toBeInTheDocument();
    expect(screen.getByText(/No commercial outcome is claimed/)).toBeInTheDocument();
  });
});
