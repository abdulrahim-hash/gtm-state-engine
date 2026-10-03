import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountsScreen } from "@/components/accounts-screen";
import { ImportBatchScreen } from "@/components/import-batch-screen";
import type { AccountList, BatchInspection, BatchRows } from "@/lib/api";

const { getIngestionBatch, getIngestionBatchRows, getAccounts } = vi.hoisted(() => ({
  getIngestionBatch: vi.fn(),
  getIngestionBatchRows: vi.fn(),
  getAccounts: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  getIngestionBatch,
  getIngestionBatchRows,
  getAccounts,
  formatSnapshot: () => "Fixed synthetic snapshot",
}));

const batch: BatchInspection = {
  batch_id: "00000000-0000-0000-0000-000000000111",
  workspace_id: "00000000-0000-0000-0000-000000000222",
  source_system_key: "local_csv",
  dataset_key: "company_public_events",
  schema_key: "company_public_event",
  schema_version: "1.0.0",
  mapper_key: "public_company_leader_event",
  mapper_version: "1.0.0",
  identity_rule_version: "1.0.0",
  file_sha256: "a".repeat(64),
  expected_rows: 1,
  ingested_at: "2026-10-03T12:00:00Z",
  counts: { accepted: 1, rejected: 0, unresolved: 0, duplicate: 0 },
};

const rows: BatchRows = {
  batch_id: batch.batch_id,
  limit: 100,
  offset: 0,
  items: [
    {
      row_id: "00000000-0000-0000-0000-000000000333",
      ordinal: 1,
      row_sha256: "b".repeat(64),
      outcome: "ACCEPTED",
      reason_code: null,
      observation: {
        observation_id: "00000000-0000-0000-0000-000000000444",
        external_record_id: "public-row-1",
        source_observed_at: "2026-09-15T12:00:00Z",
        payload_sha256: "c".repeat(64),
        first_batch_id: batch.batch_id,
        original_fields: {
          company_name: "Example Company",
          fact_code: "new_revenue_leader",
          source_url: "https://example.com/news/leader",
        },
      },
      normalization: {
        result_id: "00000000-0000-0000-0000-000000000555",
        mapper_key: "public_company_leader_event",
        mapper_version: "1.0.0",
        identity_rule_version: "1.0.0",
        output_schema_version: "1.0.0",
        outcome: "ACCEPTED",
        reason_code: null,
        account_id: "00000000-0000-0000-0000-000000000666",
        fact_key: "commercial_event.new_revenue_leader",
        fact_assertion: "PRESENT",
        evidence_classification: "FACT",
        normalized_fact: "Company page assertion PRESENT: new revenue leader.",
        fact_observed_at: "2026-09-14T12:00:00Z",
        output_sha256: "d".repeat(64),
      },
      evidence_id: "00000000-0000-0000-0000-000000000777",
    },
  ],
};

describe("M2A local provenance view", () => {
  it("renders the source-to-Evidence chain and separates downstream materialization", async () => {
    getIngestionBatch.mockResolvedValue(batch);
    getIngestionBatchRows.mockResolvedValue(rows);
    render(<ImportBatchScreen workspaceId={batch.workspace_id} batchId={batch.batch_id} />);
    expect(await screen.findByText("public-row-1")).toBeInTheDocument();
    expect(
      screen.getByText("Local imported-data inspection", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText("commercial_event.new_revenue_leader")).toBeInTheDocument();
    expect(screen.getByText("2026-09-14T12:00:00Z")).toBeInTheDocument();
    expect(screen.getByText(rows.items[0].evidence_id ?? "")).toBeInTheDocument();
    expect(screen.getByText(/Signal, State, Decision, Policy, Action/)).toBeInTheDocument();
  });
});

describe("nullable Account segment presentation", () => {
  it("shows no invented classification for a null segment", async () => {
    const list: AccountList = {
      workspace: {
        workspace_id: batch.workspace_id,
        slug: "synthetic-test",
        name: "Synthetic test workspace",
        demo_mode: true,
        demo_as_of: "2026-09-15T12:00:00Z",
      },
      items: [
        {
          id: "00000000-0000-0000-0000-000000000888",
          workspace_id: batch.workspace_id,
          slug: "synthetic-test-account",
          canonical_name: "Synthetic Test Account",
          domain: "example.com",
          segment: null,
          is_synthetic: true,
          created_at: "2026-09-15T12:00:00Z",
          updated_at: "2026-09-15T12:00:00Z",
        },
      ],
      limit: 20,
      offset: 0,
    };
    getAccounts.mockResolvedValue(list);
    render(<AccountsScreen />);
    expect(await screen.findByText("Segment not assigned")).toBeInTheDocument();
  });
});
