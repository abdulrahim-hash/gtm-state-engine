"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AccountStateSection } from "@/components/account-state-section";
import { EvidenceCard } from "@/components/evidence-card";
import { ProductShell } from "@/components/product-shell";
import { SignalCard } from "@/components/signal-card";
import { SignalEvaluations } from "@/components/signal-evaluations";
import {
  formatSnapshot,
  getAccount,
  getAccountEvidence,
  getAccountSignalEvaluations,
  getAccountSignals,
  getAccountState,
  type AccountState,
  type AccountSignalEvaluations,
  type AccountSignals,
  type AccountDetail,
  type EvidenceList,
} from "@/lib/api";

type AccountDetailScreenProps = {
  accountId: string;
};

export function AccountDetailScreen({ accountId }: AccountDetailScreenProps) {
  const [accountData, setAccountData] = useState<AccountDetail | null>(null);
  const [evidenceData, setEvidenceData] = useState<EvidenceList | null>(null);
  const [signalsData, setSignalsData] = useState<AccountSignals | null>(null);
  const [evaluationsData, setEvaluationsData] = useState<AccountSignalEvaluations | null>(null);
  const [stateData, setStateData] = useState<AccountState | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      getAccount(accountId),
      getAccountEvidence(accountId),
      getAccountSignals(accountId),
      getAccountSignalEvaluations(accountId),
      getAccountState(accountId),
    ])
      .then(([account, evidence, signals, evaluations, state]) => {
        if (!cancelled) {
          setAccountData(account);
          setEvidenceData(evidence);
          setSignalsData(signals);
          setEvaluationsData(evaluations);
          setStateData(state);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  const isLoading = accountData === null && !error;

  return (
    <ProductShell active="accounts">
      <main className="product-main">
        <Link className="back-link" href="/accounts">
          ← Accounts
        </Link>
        {isLoading ? <p className="data-notice">Loading account provenance…</p> : null}
        {error ? (
          <p className="data-notice data-notice-error">
            This account record or its synthetic provenance is unavailable.
          </p>
        ) : null}
        {accountData !== null ? (
          <>
            <section className="account-detail-hero" aria-labelledby="account-title">
              <div>
                <p className="eyebrow">Synthetic canonical account</p>
                <h1 id="account-title">{accountData.account.canonical_name}</h1>
                <p>{accountData.account.segment}</p>
              </div>
              <dl className="snapshot-panel">
                <div>
                  <dt>Domain</dt>
                  <dd>{accountData.account.domain}</dd>
                </div>
                <div>
                  <dt>Demo snapshot</dt>
                  <dd>{formatSnapshot(accountData.workspace.demo_as_of)}</dd>
                </div>
                <div>
                  <dt>Signal coverage</dt>
                  <dd>Deterministic events only</dd>
                </div>
              </dl>
            </section>
            {stateData === null ? (
              <p className="data-notice">Loading account state...</p>
            ) : (
              <AccountStateSection data={stateData} />
            )}
            <section className="signal-section" aria-labelledby="account-signals-title">
              <div className="section-heading product-section-heading">
                <div>
                  <p className="eyebrow">Commercial timing signals</p>
                  <h2 id="account-signals-title">What changed, and when</h2>
                </div>
                <p>Signals remain time-bound events with their own complete evaluation history.</p>
              </div>
              {signalsData === null ? <p className="data-notice">Loading signals&</p> : null}
              {signalsData !== null && signalsData.items.length === 0 ? (
                <p className="data-notice">No canonical signal events exist for this snapshot.</p>
              ) : null}
              {signalsData !== null && signalsData.items.length > 0 ? (
                <div className="signal-grid">
                  {signalsData.items.map((item) => (
                    <SignalCard item={item} key={item.signal.signal_id} />
                  ))}
                </div>
              ) : null}
              {evaluationsData !== null ? <SignalEvaluations data={evaluationsData} /> : null}
            </section>
            <section className="evidence-section" aria-labelledby="account-evidence-title">
              <div className="section-heading product-section-heading">
                <div>
                  <p className="eyebrow">Evidence and provenance</p>
                  <h2 id="account-evidence-title">What the record preserves</h2>
                </div>
                <p>Canonical evidence remains inspectable beneath every derived state facet.</p>
              </div>
              {evidenceData === null ? <p className="data-notice">Loading evidence…</p> : null}
              {evidenceData !== null ? (
                <div className="evidence-grid evidence-grid-account">
                  {evidenceData.items.map((evidence) => (
                    <EvidenceCard evidence={evidence} key={evidence.id} />
                  ))}
                </div>
              ) : null}
            </section>
          </>
        ) : null}
      </main>
    </ProductShell>
  );
}
