import type { Evidence } from "@/lib/api";

type EvidenceCardProps = {
  evidence: Evidence;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function EvidenceCard({ evidence }: EvidenceCardProps) {
  const classification = evidence.classification.toLowerCase();

  return (
    <article className="evidence-card" id={`evidence-${evidence.id}`}>
      <div className="evidence-card-topline">
        <span className={`evidence-tag evidence-tag-${classification}`}>
          {evidence.classification}
        </span>
        <span className={`freshness freshness-${evidence.freshness.toLowerCase()}`}>
          {humanize(evidence.freshness)}
        </span>
      </div>
      {evidence.strategy_topic !== null ? (
        <p className="evidence-topic">{humanize(evidence.strategy_topic)}</p>
      ) : null}
      {evidence.fact_key != null ? (
        <p className="evidence-topic">
          {humanize(evidence.fact_key)} � {humanize(evidence.fact_assertion ?? "")}
        </p>
      ) : null}
      <p className="evidence-statement">{evidence.normalized_fact}</p>
      <dl className="provenance-grid">
        <div>
          <dt>Source</dt>
          <dd>{evidence.source_provider}</dd>
        </div>
        <div>
          <dt>Reference</dt>
          <dd className="mono">{evidence.source_reference}</dd>
        </div>
        <div>
          <dt>Observed</dt>
          <dd>{formatTimestamp(evidence.observed_at)}</dd>
        </div>
        <div>
          <dt>Ingested</dt>
          <dd>{formatTimestamp(evidence.ingested_at)}</dd>
        </div>
        {evidence.raw_payload_hash !== null ? (
          <div>
            <dt>Payload hash</dt>
            <dd className="mono">{evidence.raw_payload_hash}</dd>
          </div>
        ) : null}
        {evidence.confidence !== null ? (
          <div>
            <dt>Epistemic confidence</dt>
            <dd>{evidence.confidence}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}
