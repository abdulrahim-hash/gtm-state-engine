import type { SignalReadModel } from "@/lib/api";

type SignalCardProps = {
  item: SignalReadModel;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function SignalCard({ item }: SignalCardProps) {
  const freshness = item.current_freshness.toLowerCase();

  return (
    <article className={`signal-card signal-card-${freshness}`}>
      <div className="signal-card-topline">
        <span className="signal-kind">{humanize(item.definition.category)}</span>
        <div className="signal-badges">
          <span className={`signal-status signal-status-${item.current_status.toLowerCase()}`}>
            {item.current_status}
          </span>
          <span className={`freshness freshness-${freshness}`}>
            {humanize(item.current_freshness)}
          </span>
        </div>
      </div>
      <h3>{item.definition.display_name}</h3>
      <p className="signal-description">{item.definition.description}</p>
      <dl className="signal-facts">
        <div>
          <dt>Observed</dt>
          <dd>{formatDate(item.signal.observed_at)}</dd>
        </div>
        <div>
          <dt>Rule</dt>
          <dd className="mono">
            {item.definition.evaluator_key}@{item.current_evaluation.rule_version}
          </dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{humanize(item.current_evaluation.reason_code)}</dd>
        </div>
      </dl>
      <div className="signal-evidence-links">
        <strong>Evidence trace</strong>
        {item.evidence.map((evidence) => (
          <a href={`#evidence-${evidence.id}`} key={evidence.id}>
            {evidence.source_reference}
          </a>
        ))}
      </div>
    </article>
  );
}
