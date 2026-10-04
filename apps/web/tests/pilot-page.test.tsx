import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import PilotPage from "@/app/pilot/page";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
}));

const account = (domain: string, result: string) => ({
  account_id: domain,
  company_name: domain,
  domain,
  evidence: [
    {
      evidence_id: `${domain}-evidence`,
      fact_key: "account_profile.offers_sales_enablement_software",
      assertion: "PRESENT",
      observed_at: "2026-10-04T10:19:27Z",
      source_observed_at: "2026-10-04T10:19:27Z",
      source_observation_id: `${domain}-observation`,
      normalization_result_id: `${domain}-normalization`,
      source_url: `https://${domain}/sales-enablement`,
      paraphrase: "Official public offering page.",
    },
  ],
  signal: {
    id: `${domain}-signal`,
    result,
    reason: "QUALIFYING_EVENT_OUTSIDE_WINDOW",
    input_hash: "hash",
    evidence_ids: [`${domain}-evidence`],
  },
  state: {
    id: `${domain}-state`,
    fit: "MATCH",
    timing: "STALE",
    relationship: "UNKNOWN",
    sufficiency: "PARTIAL",
    input_hash: "hash",
    evidence_ids: [`${domain}-evidence`],
    signal_evaluation_ids: [`${domain}-signal`],
  },
  decision: { id: `${domain}-decision`, result: "HOLD", input_hash: "hash" },
  policy: { id: `${domain}-policy`, result: "BLOCK", input_hash: "hash" },
  action: null,
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("local real public-data pilot", () => {
  it("hides the pilot page in a production web process before fetching", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(PilotPage()).rejects.toThrow("not found");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("labels hypotheses and keeps coverage counts separate from the base sample", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          strategy_status: "HYPOTHESIS / COMMERCIALLY UNVALIDATED",
          semantic_as_of: "2026-10-05T00:00:00Z",
          coverage_status: "PILOT_COVERAGE_NOT_MET",
          fingerprint: { schema: "m2b_semantic_fingerprint/1.1.0", sha256: "abc" },
          summaries: {
            BASE_SAMPLE: {
              accounts: 18,
              signal: { DETECTED: 1 },
              fit: { MATCH: 15 },
              decision: { ENGAGE: 1 },
              policy: { REQUIRE_REVIEW: 1 },
              action: { REQUEST_RESEARCH: 1 },
            },
            TRACE_COVERAGE: {
              accounts: 2,
              signal: { STALE: 1 },
              fit: { MATCH: 2 },
              decision: { HOLD: 1 },
              policy: { BLOCK: 1 },
              action: { NONE: 2 },
            },
          },
          cohorts: {
            BASE_SAMPLE: [account("base.example", "DETECTED")],
            TRACE_COVERAGE: [account("coverage.example", "STALE")],
          },
        }),
      }),
    );

    render(await PilotPage());

    expect(screen.getByText("REAL PUBLIC-DATA PILOT")).toBeInTheDocument();
    expect(screen.getByText("HYPOTHESIS / COMMERCIALLY UNVALIDATED")).toBeInTheDocument();
    const base = screen.getByRole("region", { name: "Selection-blind base sample" });
    const coverage = screen.getByRole("region", { name: "Disclosed trace coverage" });
    expect(within(base).getByText("18 accounts")).toBeInTheDocument();
    expect(within(coverage).getByText("2 accounts")).toBeInTheDocument();
    expect(within(base).getByText("base.example", { selector: "h3" })).toBeInTheDocument();
    expect(within(coverage).getByText("coverage.example", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getAllByText(/stale based on verified pilot evidence/i).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/No outreach, CRM update, external seller task/i)).toBeInTheDocument();
  });
});
