import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { WorkflowStatus } from "../api";
import { Card, Empty, ErrorBanner, PageHeader, StatusBadge } from "../components/ui";
import { usePoll } from "../usePoll";
import { fmtTime, shortId, timeAgo } from "../util";

const FILTERS: { value: WorkflowStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "needs_review", label: "Needs review" },
  { value: "failed", label: "Failed" },
  { value: "retry_scheduled", label: "Retrying" },
  { value: "processing", label: "Processing" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "compensated", label: "Compensated" },
];

export default function Workflows() {
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as WorkflowStatus | "";
  const heldView = params.get("view") === "held";
  const workflows = usePoll(
    () => (heldView ? api.heldStock() : api.workflows(status || undefined)),
    4000,
    [status, heldView],
  );

  return (
    <>
      <PageHeader title="Workflows" subtitle="Execution state, retries and errors for every order." />

      <div className="tabs" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            role="tab"
            aria-selected={!heldView && status === f.value}
            className={`tab ${!heldView && status === f.value ? "active" : ""}`}
            onClick={() => setParams(f.value ? { status: f.value } : {})}
          >
            {f.label}
          </button>
        ))}
        <button
          role="tab"
          aria-selected={heldView}
          className={`tab ${heldView ? "active" : ""}`}
          onClick={() => setParams({ view: "held" })}
        >
          Stock held
        </button>
      </div>

      {heldView && (
        <div className="banner banner-warn">
          These failed or in-review orders still have inventory reserved. Open one and request{" "}
          <em>Release reserved stock</em> if it can't complete.
        </div>
      )}
      <ErrorBanner message={workflows.error} />

      <Card>
        {workflows.loading && !workflows.data ? (
          <Empty>Loading…</Empty>
        ) : (workflows.data ?? []).length === 0 ? (
          <Empty>No workflows match this filter.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Status</th>
                  <th>Step</th>
                  <th>Attempts</th>
                  <th>Last error</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {workflows.data!.map((w) => (
                  <tr key={w.id}>
                    <td>
                      <strong>{w.product_id}</strong> <span className="muted">× {w.quantity}</span>
                      <div className="muted small">{shortId(w.id)}</div>
                    </td>
                    <td>
                      <StatusBadge status={w.status} />
                    </td>
                    <td className="muted">{w.current_step?.replace("_", " ") ?? "—"}</td>
                    <td>{w.attempts}</td>
                    <td className="muted small">{w.last_error_code ?? "—"}</td>
                    <td className="muted" title={fmtTime(w.updated_at)}>
                      {timeAgo(w.updated_at)}
                    </td>
                    <td className="right">
                      <Link to={`/workflows/${w.id}`}>Open →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
