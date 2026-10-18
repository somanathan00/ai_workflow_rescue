import { useState } from "react";
import { api } from "../api";
import { Card, Empty, ErrorBanner, PageHeader } from "../components/ui";
import { usePoll } from "../usePoll";
import { ACTION_LABEL } from "../util";

const pct = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;

function Kpi({ value, label, hint }: { value: string; label: string; hint?: string }) {
  return (
    <div className="kpi" title={hint}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function label(key: string): string {
  return key in ACTION_LABEL ? ACTION_LABEL[key as keyof typeof ACTION_LABEL] : key;
}

export default function AIQuality() {
  const [days, setDays] = useState(30);
  const metrics = usePoll(() => api.investigationMetrics(days), 10000, [days]);
  const m = metrics.data;

  const funnel = m
    ? [
        { name: "Actionable advice", value: m.outcomes.actionable },
        { name: "Someone acted on it", value: m.outcomes.followed },
        { name: "Approved by an admin", value: m.outcomes.approved },
        { name: "Executed", value: m.outcomes.executed },
        { name: "Actually worked", value: m.outcomes.succeeded },
      ]
    : [];
  const top = Math.max(1, ...funnel.map((f) => f.value));

  const actions = m
    ? Array.from(new Set([...Object.keys(m.actions.model_original), ...Object.keys(m.actions.final)]))
    : [];

  return (
    <>
      <PageHeader
        title="AI quality"
        subtitle="Is the investigator actually useful? Measured from what people did with its advice."
        action={
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time window" style={{ width: "auto" }}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        }
      />
      <ErrorBanner message={metrics.error} />

      {!m ? (
        <Card>
          <Empty>Loading…</Empty>
        </Card>
      ) : m.investigations.total === 0 ? (
        <Card>
          <Empty>No investigations in this period yet. Run “Investigate with AI” on a failed workflow first.</Empty>
        </Card>
      ) : (
        <>
          <div className="kpis">
            <Kpi value={String(m.investigations.completed)} label="investigations completed" hint={`${m.investigations.failed} failed, ${m.investigations.in_flight} running`} />
            <Kpi value={pct(m.outcomes.follow_rate)} label="advice acted on" hint="Share of actionable recommendations that someone followed" />
            <Kpi value={pct(m.outcomes.success_rate)} label="recoveries that worked" hint="Of executed recoveries, how many reached the intended outcome" />
            <Kpi value={pct(m.feedback.helpful_rate)} label="rated helpful" hint={`${m.feedback.helpful} helpful, ${m.feedback.not_helpful} not helpful`} />
            <Kpi value={pct(m.guardrails.downgrade_rate)} label="answers changed by guardrails" hint="Model answers the safety rules had to make safer" />
          </div>

          <div className="grid-2">
            <Card title="What happened to the advice">
              <div className="funnel">
                {funnel.map((f) => (
                  <div className="funnel-row" key={f.name}>
                    <span>{f.name}</span>
                    <div className="funnel-bar">
                      <div className="funnel-fill" style={{ width: `${(f.value / top) * 100}%` }} />
                    </div>
                    <b>{f.value}</b>
                  </div>
                ))}
              </div>
              <ul className="kv" style={{ marginTop: "1rem" }}>
                <li>
                  <span>overridden (a different action was chosen)</span>
                  <strong>{m.outcomes.overridden}</strong>
                </li>
                <li>
                  <span>no recovery requested</span>
                  <strong>{m.outcomes.no_recovery_requested}</strong>
                </li>
                <li>
                  <span>rejected by an admin</span>
                  <strong>{m.outcomes.rejected}</strong>
                </li>
              </ul>
              <p className="muted small">
                A high override rate means people disagree with the AI. A low success rate means its advice
                doesn't solve the problem.
              </p>
            </Card>

            <Card title="Does confidence mean anything?">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Model confidence</th>
                      <th>Advice</th>
                      <th>Executed</th>
                      <th>Worked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.calibration.map((c) => (
                      <tr key={c.bucket}>
                        <td>{c.bucket}</td>
                        <td>{c.actionable}</td>
                        <td>{c.executed}</td>
                        <td>
                          {c.succeeded} <span className="muted small">({pct(c.success_rate)})</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted small">
                If higher confidence does not mean a higher success rate, don't use confidence to decide anything.
                Small samples are noisy.
              </p>
            </Card>
          </div>

          <div className="grid-2">
            <Card title="What the model said vs. the final advice">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Model</th>
                      <th>After guardrails</th>
                    </tr>
                  </thead>
                  <tbody>
                    {actions.map((a) => (
                      <tr key={a}>
                        <td>{label(a)}</td>
                        <td>{m.actions.model_original[a] ?? 0}</td>
                        <td>{m.actions.final[a] ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {m.guardrails.top_violations.length > 0 && (
                <>
                  <h3>Why guardrails stepped in</h3>
                  <ul className="kv">
                    {m.guardrails.top_violations.map((v) => (
                      <li key={v.reason}>
                        <span>{v.reason}</span>
                        <strong>{v.count}</strong>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>

            <Card title="Cost and speed">
              <ul className="kv">
                <li>
                  <span>average confidence reported</span>
                  <strong>{pct(m.model.avg_confidence)}</strong>
                </li>
                <li>
                  <span>average response time</span>
                  <strong>{m.model.avg_latency_ms ? `${(m.model.avg_latency_ms / 1000).toFixed(1)}s` : "—"}</strong>
                </li>
                <li>
                  <span>slowest response</span>
                  <strong>{m.model.max_latency_ms ? `${(m.model.max_latency_ms / 1000).toFixed(1)}s` : "—"}</strong>
                </li>
                <li>
                  <span>prompt tokens</span>
                  <strong>{m.model.prompt_tokens.toLocaleString()}</strong>
                </li>
                <li>
                  <span>completion tokens</span>
                  <strong>{m.model.completion_tokens.toLocaleString()}</strong>
                </li>
                <li>
                  <span>made-up evidence references</span>
                  <strong>{pct(m.guardrails.unsupported_reference_rate)}</strong>
                </li>
                <li>
                  <span>feedback coverage</span>
                  <strong>{pct(m.feedback.coverage)}</strong>
                </li>
              </ul>
              <p className="muted small">
                Before changing the prompt or model, run <code>make eval</code> (real model) and{" "}
                <code>make eval-offline</code> (guardrails only) against the fixed scenarios.
              </p>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
