import type { AccountSignalEvaluations } from "@/lib/api";

type SignalEvaluationsProps = {
  data: AccountSignalEvaluations;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

export function SignalEvaluations({ data }: SignalEvaluationsProps) {
  const inconclusive = data.items.filter(
    (item) => item.evaluation.result === "INCONCLUSIVE",
  ).length;
  const noMatch = data.items.filter((item) => item.evaluation.result === "NO_MATCH").length;
  const stale = data.items.filter((item) => item.evaluation.result === "STALE").length;

  return (
    <details className="evaluation-details">
      <summary>
        <span>Inspect deterministic evaluation coverage</span>
        <span className="evaluation-counts">
          {noMatch} no match � {inconclusive} inconclusive � {stale} stale
        </span>
      </summary>
      <div className="evaluation-list">
        {data.items.map((item) => (
          <article className="evaluation-row" key={item.evaluation.evaluation_id}>
            <div>
              <span
                className={`evaluation-result evaluation-result-${item.evaluation.result.toLowerCase().replace("_", "-")}`}
              >
                {item.evaluation.result}
              </span>
              <h3>{item.definition.display_name}</h3>
              <p>{humanize(item.evaluation.reason_code)}</p>
            </div>
            <dl>
              <div>
                <dt>Rule</dt>
                <dd className="mono">
                  {item.definition.evaluator_key}@{item.evaluation.rule_version}
                </dd>
              </div>
              <div>
                <dt>Input hash</dt>
                <dd className="mono">{item.evaluation.input_hash}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>
                  {item.evidence.length === 0
                    ? "No eligible evidence at this snapshot"
                    : item.evidence.map((evidence) => evidence.source_reference).join(", ")}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </details>
  );
}
