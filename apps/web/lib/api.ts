import type { components } from "@gtm-state/contracts";

export type ActiveStrategy = components["schemas"]["ActiveStrategyResponse"];
export type AccountList = components["schemas"]["AccountListResponse"];
export type AccountDetail = components["schemas"]["AccountDetailResponse"];
export type EvidenceList = components["schemas"]["EvidenceListResponse"];
export type Evidence = components["schemas"]["EvidenceResponse"];
export type AccountSignals = components["schemas"]["AccountSignalListResponse"];
export type AccountSignalEvaluations = components["schemas"]["AccountSignalEvaluationListResponse"];
export type SignalReadModel = components["schemas"]["SignalReadModel"];
export type SignalEvaluationTrace = components["schemas"]["SignalEvaluationTraceResponse"];
export type AccountState = components["schemas"]["AccountStateDetailResponse"];
export type AccountStateHistory = components["schemas"]["AccountStateHistoryResponse"];
export type AccountDecision = components["schemas"]["DecisionPolicyDetailResponse"];

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Read model request failed with ${response.status}.`);
  }
  return (await response.json()) as T;
}

export function getActiveStrategy(): Promise<ActiveStrategy> {
  return getJson<ActiveStrategy>("/api/v1/strategy/active");
}

export function getAccounts(): Promise<AccountList> {
  return getJson<AccountList>("/api/v1/accounts");
}

export function getAccount(accountId: string): Promise<AccountDetail> {
  return getJson<AccountDetail>(`/api/v1/accounts/${accountId}`);
}

export function getAccountEvidence(accountId: string): Promise<EvidenceList> {
  return getJson<EvidenceList>(`/api/v1/evidence?account_id=${encodeURIComponent(accountId)}`);
}

export function getAccountSignals(accountId: string): Promise<AccountSignals> {
  return getJson<AccountSignals>(`/api/v1/accounts/${encodeURIComponent(accountId)}/signals`);
}

export function getAccountSignalEvaluations(accountId: string): Promise<AccountSignalEvaluations> {
  return getJson<AccountSignalEvaluations>(
    `/api/v1/accounts/${encodeURIComponent(accountId)}/signal-evaluations`,
  );
}

export function getAccountState(accountId: string): Promise<AccountState> {
  return getJson<AccountState>(`/api/v1/accounts/${encodeURIComponent(accountId)}/state`);
}

export function getAccountStateHistory(accountId: string): Promise<AccountStateHistory> {
  return getJson<AccountStateHistory>(
    `/api/v1/accounts/${encodeURIComponent(accountId)}/state/history`,
  );
}

export function getAccountDecision(accountId: string): Promise<AccountDecision> {
  return getJson<AccountDecision>(`/api/v1/accounts/${encodeURIComponent(accountId)}/decision`);
}

export function formatSnapshot(isoTimestamp: string | null): string {
  if (isoTimestamp === null) {
    return "Fixed synthetic snapshot";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(isoTimestamp));
}
