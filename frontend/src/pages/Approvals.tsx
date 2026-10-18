import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { RecoveryAction, RecoveryStatus } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBanner, PageHeader } from "../components/ui";
import { usePoll } from "../usePoll";
import { ACTION_LABEL, fmtTime, shortId } from "../util";

const TABS: { value: RecoveryStatus; label: string }[] = [
  { value: "requested", label: "Awaiting approval" },
  { value: "approved", label: "Approved" },
  { value: "executed", label: "Executed" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
];

function Row({ action, onChange }: { action: RecoveryAction; onChange: () => void }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const own = action.requested_by === user?.id;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="recovery">
      <div className="recovery-head">
        <strong>{ACTION_LABEL[action.action_type]}</strong>
        <Link to={`/workflows/${action.workflow_id}`}>workflow {shortId(action.workflow_id)} →</Link>
        <span className="muted small">{fmtTime(action.created_at)}</span>
      </div>
      <p>{action.reason}</p>
      <p className="muted small">
        Requested by {own ? "you" : shortId(action.requested_by)}
        {action.investigation_id && ` · follows AI investigation ${shortId(action.investigation_id)}`}
      </p>
      {action.rejection_reason && <p className="muted small">Rejected: {action.rejection_reason}</p>}
      {action.error_message && <p className="muted small">Failed: {action.error_message}</p>}

      {action.status === "requested" &&
        (own ? (
          <p className="muted small">You requested this, so a different admin must approve it.</p>
        ) : rejecting ? (
          <form
            className="inline-form"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              void run(() => api.reject(action.workflow_id, action.id, reason));
            }}
          >
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" minLength={3} required autoFocus />
            <button className="btn btn-danger" disabled={busy}>
              Reject
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setRejecting(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <div className="actions">
            <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.approve(action.workflow_id, action.id))}>
              Approve
            </button>
            <button className="btn btn-ghost" disabled={busy} onClick={() => setRejecting(true)}>
              Reject…
            </button>
          </div>
        ))}

      {action.status === "approved" && (
        <div className="actions">
          <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.execute(action.workflow_id, action.id))}>
            Execute recovery
          </button>
        </div>
      )}
      <ErrorBanner message={error} />
    </li>
  );
}

export default function Approvals() {
  const [status, setStatus] = useState<RecoveryStatus>("requested");
  const queue = usePoll(() => api.recoveryQueue(status), 4000, [status]);

  return (
    <>
      <PageHeader
        title="Approvals"
        subtitle="Recovery requests across all workflows. Nothing runs until an administrator approves it."
      />

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={status === t.value}
            className={`tab ${status === t.value ? "active" : ""}`}
            onClick={() => setStatus(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <ErrorBanner message={queue.error} />

      <Card>
        {queue.loading && !queue.data ? (
          <Empty>Loading…</Empty>
        ) : (queue.data ?? []).length === 0 ? (
          <Empty>Nothing here.</Empty>
        ) : (
          <ul className="recoveries">
            {queue.data!.map((a) => (
              <Row key={a.id} action={a} onChange={queue.reload} />
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
