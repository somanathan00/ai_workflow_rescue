import { fetchText } from "../api";
import { Card, ErrorBanner, PageHeader } from "../components/ui";
import { usePoll } from "../usePoll";

interface Sample {
  name: string;
  label: string | null;
  value: number;
}

function parseMetrics(text: string): Sample[] {
  const samples: Sample[] = [];

  for (const line of text.split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^([a-z_]+)(?:\{[a-z_]+="([^"]*)"\})?\s+([-0-9.eE]+)$/);
    if (match) samples.push({ name: match[1], label: match[2] ?? null, value: Number(match[3]) });
  }

  return samples;
}

const group = (samples: Sample[], name: string) => samples.filter((s) => s.name === name);
const single = (samples: Sample[], name: string) => samples.find((s) => s.name === name)?.value ?? 0;

function Group({ title, rows }: { title: string; rows: Sample[] }) {
  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <ul className="kv">
          {rows.map((r) => (
            <li key={r.label ?? r.name}>
              <span>{r.label}</span>
              <strong>{r.value}</strong>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function System() {
  const ready = usePoll(async () => {
    const res = await fetch("/health/ready");
    return (await res.json()) as { status: string; checks: Record<string, string> };
  }, 5000);
  const metrics = usePoll(async () => parseMetrics((await fetchText("/metrics")).text), 5000);

  const samples = metrics.data ?? [];
  const outboxAge = single(samples, "outbox_oldest_pending_age_seconds");

  return (
    <>
      <PageHeader
        title="System"
        subtitle="Health and activity of the platform"
        action={
          <a className="btn btn-secondary" href="/docs" target="_blank" rel="noreferrer">
            API docs ↗
          </a>
        }
      />
      <ErrorBanner message={ready.error ?? metrics.error} />

      <div className="grid-3">
        <Card title="Dependencies">
          {ready.data ? (
            <ul className="kv">
              {Object.entries(ready.data.checks).map(([name, state]) => (
                <li key={name}>
                  <span>{name}</span>
                  <span className={`badge badge-${state === "ok" ? "completed" : "failed"}`}>
                    <span className="dot" />
                    {state}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Checking…</p>
          )}
          <p className="muted small">
            Orders are accepted through the outbox even while Redis is unavailable, and delivered when it returns.
          </p>
        </Card>

        <Card title="Outbox">
          <ul className="kv">
            {group(samples, "outbox_messages").map((r) => (
              <li key={r.label}>
                <span>{r.label}</span>
                <strong>{r.value}</strong>
              </li>
            ))}
            <li>
              <span>oldest pending</span>
              <strong>{outboxAge.toFixed(1)}s</strong>
            </li>
          </ul>
          <p className="muted small">A pending age that keeps growing means the dispatcher is stuck.</p>
        </Card>

        <Card title="Stock held">
          <ul className="kv">
            <li>
              <span>reservations held by failed orders</span>
              <strong>{single(samples, "held_reservations")}</strong>
            </li>
            <li>
              <span>longest held</span>
              <strong>{Math.round(single(samples, "held_reservations_oldest_age_seconds") / 60)} min</strong>
            </li>
          </ul>
          <p className="muted small">Stock tied up by orders that can't complete. Release it from the workflow page.</p>
        </Card>

        <Card title="AI usage">
          <ul className="kv">
            <li>
              <span>prompt tokens</span>
              <strong>{single(samples, "gemini_prompt_tokens_total")}</strong>
            </li>
            <li>
              <span>completion tokens</span>
              <strong>{single(samples, "gemini_completion_tokens_total")}</strong>
            </li>
            <li>
              <span>avg latency</span>
              <strong>{(single(samples, "gemini_latency_ms_avg") / 1000).toFixed(1)}s</strong>
            </li>
          </ul>
        </Card>
      </div>

      <div className="grid-3">
        <Group title="Workflows" rows={group(samples, "workflows_total")} />
        <Group title="Recovery actions" rows={group(samples, "recovery_actions_total")} />
        <Group title="Investigations" rows={group(samples, "investigations_total")} />
      </div>
    </>
  );
}
