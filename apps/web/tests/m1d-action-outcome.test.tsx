import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ActionOutcomeSection } from "@/components/action-outcome-section";
import type { CurrentAccountAction } from "@/lib/api";

const ids = {
  account: "1a1206b7-243c-4f22-8d7f-53aa00000013",
  action: "1a1206b7-243c-4f22-8d7f-53aa00000a13",
  policy: "1a1206b7-243c-4f22-8d7f-53aa00000913",
  decision: "1a1206b7-243c-4f22-8d7f-53aa00000813",
  snapshot: "1a1206b7-243c-4f22-8d7f-53aa00000713",
};

function projection(overrides: Record<string, unknown> = {}): CurrentAccountAction {
  return {
    account_id: ids.account,
    workspace: { workspace_id: "1a1206b7-243c-4f22-8d7f-53aa00000001" },
    upstream: {
      decision: { evaluation: { decision_evaluation_id: ids.decision } },
      state_snapshot: { state_snapshot_id: ids.snapshot },
    },
    current: {
      projection: "ACTION_PROPOSED",
      policy_evaluation_id: ids.policy,
      policy_result: "REQUIRE_REVIEW",
      policy_reason_codes: ["EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING"],
      external_execution_authorized: false,
      action: {
        action: {
          action_id: ids.action,
          action_type: "CREATE_SELLER_TASK",
          action_schema_version: "1.0.0",
          payload: {
            task_kind: "RELATIONSHIP_COORDINATION",
            objective_code: "ASSESS_CONTROLLED_ENGAGEMENT_PATH",
          },
          semantic_input_hash: "a".repeat(64),
          derivation_key: "m1c_policy_to_canonical_action",
          derivation_version: "1.0.0",
          external_execution_authorized: false,
        },
        lifecycle: "REVIEW_REQUIRED",
        review: null,
        attempts: [],
        mutations_enabled: false,
        external_execution_authorized: false,
      },
      ...overrides,
    },
  } as unknown as CurrentAccountAction;
}

describe("M1D account Action and Outcome presentation", () => {
  it("keeps a review-required Asterwind proposal non-executing and read-only", () => {
    render(
      <ActionOutcomeSection
        data={projection({
          policy_reason_codes: ["RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW"],
          action: {
            ...projection().current.action,
            action: {
              ...projection().current.action?.action,
              action_type: "REQUEST_RESEARCH",
              payload: {
                research_topic: "RELATIONSHIP_CONTEXT",
                request_code: "VERIFY_EXISTING_RELATIONSHIP",
              },
            },
          },
        })}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByText("request research")).toBeInTheDocument();
    expect(screen.getByText("Public demo is read only.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/no seller task was created/i)).toBeInTheDocument();
  });

  it("shows Bramble as a non-Action Policy block", () => {
    render(
      <ActionOutcomeSection
        data={projection({
          projection: "BLOCKED_BY_POLICY",
          policy_result: "BLOCK",
          policy_reason_codes: ["DECISION_DOES_NOT_SUPPORT_ACTIVATION"],
          action: null,
        })}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("Blocked by Policy")).toBeInTheDocument();
    expect(
      screen.getByText(/No canonical Action row or dry-run attempt exists/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Action proposal")).not.toBeInTheDocument();
  });

  it("labels Cinderlake approval and result as synthetic local validation", () => {
    const base = projection();
    render(
      <ActionOutcomeSection
        data={projection({
          action: {
            ...base.current.action,
            lifecycle: "READY_FOR_DRY_RUN",
            review: {
              resolution: "APPROVED",
              reviewer_kind: "SYNTHETIC_FIXTURE",
              reason_code: "APPROVED_AS_PROPOSED",
            },
            attempts: [
              {
                attempt: {
                  action_attempt_id: "1a1206b7-243c-4f22-8d7f-53aa00000c13",
                  mode: "DRY_RUN",
                },
                outcome: {
                  result: "SUCCEEDED",
                  reason_code: "CANONICAL_ACTION_VALIDATED",
                  external_side_effects: false,
                },
              },
            ],
          },
        })}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText(/Synthetic fixture approval or rejection/i)).toBeInTheDocument();
    expect(screen.getByText("Dry-run validation succeeded")).toBeInTheDocument();
    expect(screen.getByText(/External side effects: none/i)).toBeInTheDocument();
    expect(screen.getByText(/no owner was assigned, no message was sent/i)).toBeInTheDocument();
    expect(screen.queryByText("Action succeeded")).not.toBeInTheDocument();
  });

  it("does not confuse unsupported derivation with a Policy block", () => {
    render(
      <ActionOutcomeSection
        data={projection({
          projection: "NO_SUPPORTED_ACTION",
          action: null,
        })}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("No supported Action")).toBeInTheDocument();
    expect(screen.queryByText("Blocked by Policy")).not.toBeInTheDocument();
  });
});
