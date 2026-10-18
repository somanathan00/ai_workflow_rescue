import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { ActionType, FeedbackRating, Investigation, RecoveryAction, Workflow } from "../api";
import { useAuth } from "../auth";
import {
  Card,
  ConfidenceBar,
  Empty,
  ErrorBanner,
  PageHeader,
  Stepper,
  StatusBadge,
  Timeline,
} from "../components/ui";
import { usePoll } from "../usePoll";
import {
  ACTION_HELP,
  ACTION_LABEL,
  ACTIVE_RECOVERY,
  ACTIVE_WORKFLOW,
  fmtTime,
  humanize,
  ineligibleReason,
  newKey,
  shortId,
} from "../util";

const ACTIONS: ActionType[] = [
  "reconcile_and_resume",
  "retry_workflow",
  "release_reservation",
  "mark_for_review",
];

function useCountdown(iso: string | null) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!iso) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [iso]);

  if (!iso) return null;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 1000));
}

function Facts({ workflow }: { workflow: Workflow }) {
  const countdown = useCountdown(workflow.status === "retry_scheduled" ? workflow.next_retry_at : null);

  return (
    <dl className="facts">
      <div>
        <dt>Attempts</dt>
        <dd>{workflow.attempts}</dd>
      </div>
      <div>
        <dt>Current step</dt>
        <dd>{workflow.current_step ? humanize(workflow.current_step) : "—"}</dd>
      </div>
      {countdown !== null && (
        <div>
          <dt>Next retry</dt>
          <dd>{countdown === 0 ? "now" : `in ${countdown}s`}</dd>
        </div>
      )}
      <div>
        <dt>Created</dt>
        <dd>{fmtTime(workflow.created_at)}</dd>
      </div>
      <div>
        <dt>Updated</dt>
        <dd>{fmtTime(workflow.updated_at)}</dd>
      </div>
    </dl>
  );
}

function FeedbackBar({ item, onChange }: { item: Investigation; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState(item.my_feedback?.comment ?? "");
  const rating = item.my_feedback?.rating;

  async function send(next: FeedbackRating) {
    setBusy(true);
    setError(null);
    try {
      await api.giveFeedback(item.id, next, comment.trim() || null);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your feedback");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="feedback">
      <span className="muted small">Was this investigation useful?</span>
      <button
        className={`btn btn-ghost ${rating === "helpful" ? "btn-chosen" : ""}`}
        disabled={busy}
        onClick={() => send("helpful")}
      >
        👍 Helpful
      </button>
      <button
        className={`btn btn-ghost ${rating === "not_helpful" ? "btn-chosen" : ""}`}
        disabled={busy}
        onClick={() => send("not_helpful")}
      >
        👎 Not helpful
      </button>
      {rating && (
        <form
          className="inline-form"
          style={{ flexBasis: "100%", marginTop: 0 }}
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void send(rating);
          }}
        >
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Optional: what was right or wrong?"
            maxLength={1000}
          />
          <button className="btn btn-ghost" disabled={busy}>
            Save note
          </button>
        </form>
      )}
      <ErrorBanner message={error} />
    </div>
  );
}

function InvestigationCard({ item, onChange }: { item: Investigation; onChange: () => void }) {
  const policy = item.policy_result;

  if (item.status === "pending" || item.status === "running") {
    return (
      <div className="investigation">
        <div className="inv-head">
          <StatusBadge status={item.status === "pending" ? "pending" : "processing"} />
          <span className="muted">Collecting evidence and asking the model…</span>
        </div>
      </div>
    );
  }

  if (item.status === "failed") {
    return (
      <div className="investigation">
        <div className="inv-head">
          <StatusBadge status="failed" />
          <span className="muted small">{fmtTime(item.created_at)}</span>
        </div>
        <p className="muted">
          The investigation could not complete: <code>{item.error_message}</code>
        </p>
        <p className="muted small">Recovery does not depend on the AI — you can still request a recovery manually.</p>
      </div>
    );
  }

  return (
    <div className="investigation">
      <div className="inv-head">
        <span className="chip chip-strong">
          {item.recommended_action ? ACTION_LABEL[item.recommended_action] : "—"}
        </span>
        {item.confidence !== null && <ConfidenceBar value={item.confidence} />}
        <span className="muted small">{fmtTime(item.created_at)}</span>
      </div>

      {policy?.downgraded && (
        <div className="banner banner-warn">
          <strong>Guardrails changed the model's answer</strong> from{" "}
          <code>{policy.model_recommended_action}</code> to <code>{policy.final_action}</code>.
          <ul>
            {policy.violations.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </div>
      )}

      <h3>Root cause</h3>
      <p>{item.root_cause}</p>
      <h3>Reasoning</h3>
      <p>{item.reasoning}</p>

      {item.evidence.length > 0 && (
        <>
          <h3>Evidence</h3>
          <ul className="evidence">
            {item.evidence.map((e) => (
              <li key={e.reference}>
                <code>{e.reference.length > 46 ? `${e.reference.slice(0, 46)}…` : e.reference}</code>
                <span>{e.observation}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="muted small">
        {item.model_name ?? "model"} · {item.prompt_tokens ?? 0}+{item.completion_tokens ?? 0} tokens ·{" "}
        {item.latency_ms ? `${(item.latency_ms / 1000).toFixed(1)}s` : "—"} · advisory only, a person approves any action
      </p>

      <FeedbackBar item={item} onChange={onChange} />
    </div>
  );
}

function InvestigationPanel({
  workflowId,
  investigations,
  onChange,
}: {
  workflowId: string;
  investigations: Investigation[];
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = investigations.some((i) => i.status === "pending" || i.status === "running");

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await api.investigate(workflowId);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the investigation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="AI investigation"
      action={
        <button className="btn btn-secondary" onClick={start} disabled={busy || inFlight}>
          {inFlight ? "Investigating…" : "Investigate with AI"}
        </button>
      }
    >
      <ErrorBanner message={error} />
      {investigations.length === 0 ? (
        <Empty>
          Ask the AI to explain what happened and recommend a safe next step. It only reads evidence from the database
          and never changes anything.
        </Empty>
      ) : (
        investigations.slice(0, 3).map((item) => <InvestigationCard key={item.id} item={item} onChange={onChange} />)
      )}
    </Card>
  );
}

function RecoveryRow({
  workflowId,
  action,
  onChange,
}: {
  workflowId: string;
  action: RecoveryAction;
  onChange: () => void;
}) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const isAdmin = user?.role === "admin";
  const own = action.requested_by === user?.id;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setRejecting(false);
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
        <span className={`badge badge-rec-${action.status}`}>
          <span className="dot" />
          {action.status}
        </span>
        <span className="muted small">{fmtTime(action.created_at)}</span>
      </div>
      <p>{action.reason}</p>
      {action.investigation_id && (
        <p className="muted small">Follows investigation {shortId(action.investigation_id)}</p>
      )}
      {action.rejection_reason && <p className="muted small">Rejected: {action.rejection_reason}</p>}
      {action.error_message && <p className="muted small">Failed: {action.error_message}</p>}

      {action.status === "requested" && (
        <div className="actions">
          {isAdmin && !own && !rejecting && (
            <>
              <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.approve(workflowId, action.id))}>
                Approve
              </button>
              <button className="btn btn-ghost" disabled={busy} onClick={() => setRejecting(true)}>
                Reject…
              </button>
            </>
          )}
          {isAdmin && own && <span className="muted small">You requested this, so a different admin must approve it.</span>}
          {!isAdmin && <span className="muted small">Waiting for an administrator to approve.</span>}
        </div>
      )}

      {rejecting && (
        <form
          className="inline-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void run(() => api.reject(workflowId, action.id, rejectReason));
          }}
        >
          <input
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Reason for rejecting"
            minLength={3}
            required
            autoFocus
          />
          <button className="btn btn-danger" disabled={busy}>
            Reject
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setRejecting(false)}>
            Cancel
          </button>
        </form>
      )}

      {action.status === "approved" && (
        <div className="actions">
          <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.execute(workflowId, action.id))}>
            Execute recovery
          </button>
          <span className="muted small">Queues the recovery; a worker performs it.</span>
        </div>
      )}

      {(action.status === "queued" || action.status === "executing") && (
        <p className="muted small">In progress… this page updates automatically.</p>
      )}

      <ErrorBanner message={error} />
    </li>
  );
}

function RecoveryPanel({
  workflow,
  actions,
  investigations,
  onChange,
  prefill,
}: {
  workflow: Workflow;
  actions: RecoveryAction[];
  investigations: Investigation[];
  onChange: () => void;
  prefill: ActionType | null;
}) {
  const [actionType, setActionType] = useState<ActionType>("reconcile_and_resume");
  const [reason, setReason] = useState("");
  const [link, setLink] = useState(true);
  const [key, setKey] = useState(newKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = actions.find((a) => ACTIVE_RECOVERY.includes(a.status));
  const recommendation = investigations.find(
    (i) => i.status === "completed" && i.recommended_action === actionType,
  );

  // Pick the first action that is actually allowed for this workflow.
  useEffect(() => {
    const preferred = prefill ?? ACTIONS.find((a) => !ineligibleReason(workflow, a));
    if (preferred) setActionType(preferred);
  }, [workflow.status, workflow.last_error_code, prefill]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.requestRecovery(
        workflow.id,
        {
          action_type: actionType,
          reason,
          investigation_id: link && recommendation ? recommendation.id : null,
        },
        key,
      );
      setReason("");
      setKey(newKey());
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not request recovery");
    } finally {
      setBusy(false);
    }
  }

  const blocked = ineligibleReason(workflow, actionType);

  return (
    <Card title="Recovery">
      {actions.length > 0 && (
        <ul className="recoveries">
          {actions.map((a) => (
            <RecoveryRow key={a.id} workflowId={workflow.id} action={a} onChange={onChange} />
          ))}
        </ul>
      )}

      {workflow.status === "completed" || workflow.status === "compensated" ? (
        <Empty>
          {workflow.status === "completed"
            ? "This workflow completed; nothing to recover."
            : "This order was compensated (its stock was released); nothing more to recover."}
        </Empty>
      ) : active ? (
        <p className="muted small">A recovery is already in progress for this workflow, so a new one can't be requested yet.</p>
      ) : (
        <form className="form" onSubmit={submit}>
          <h3>Request a recovery</h3>
          <div className="radio-list" role="radiogroup">
            {ACTIONS.map((a) => {
              const reason = ineligibleReason(workflow, a);
              return (
                <label key={a} className={`radio ${reason ? "disabled" : ""} ${actionType === a ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name="action"
                    checked={actionType === a}
                    disabled={Boolean(reason)}
                    onChange={() => setActionType(a)}
                  />
                  <div>
                    <strong>{ACTION_LABEL[a]}</strong>
                    <span>{reason ?? ACTION_HELP[a]}</span>
                  </div>
                </label>
              );
            })}
          </div>

          <label>
            Reason
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              minLength={10}
              maxLength={1000}
              rows={3}
              required
              placeholder="Why is this recovery needed? (at least 10 characters)"
            />
          </label>

          {recommendation && (
            <label className="check">
              <input type="checkbox" checked={link} onChange={(e) => setLink(e.target.checked)} />
              Link to the AI investigation that recommended this ({shortId(recommendation.id)})
            </label>
          )}

          <ErrorBanner message={error} />

          <button className="btn btn-primary" disabled={busy || Boolean(blocked)}>
            {busy ? "Requesting…" : "Request recovery"}
          </button>
          <p className="muted small">An administrator must approve it before anything runs.</p>
        </form>
      )}
    </Card>
  );
}

export default function WorkflowDetail() {
  const { id = "" } = useParams();
  const [fast, setFast] = useState(true);

  const workflow = usePoll(() => api.workflow(id), fast ? 2000 : 8000, [id, fast]);
  const events = usePoll(() => api.events(id), fast ? 2000 : 8000, [id, fast]);
  const investigations = usePoll(() => api.investigations(id), fast ? 2000 : 8000, [id, fast]);
  const recoveries = usePoll(() => api.recoveryActions(id), fast ? 2000 : 8000, [id, fast]);

  const w = workflow.data;
  const busyRecovery = (recoveries.data ?? []).some((a) => ["queued", "executing", "approved"].includes(a.status));
  const busyInvestigation = (investigations.data ?? []).some((i) => i.status === "pending" || i.status === "running");
  const shouldPollFast = Boolean(w && ACTIVE_WORKFLOW.includes(w.status)) || busyRecovery || busyInvestigation;

  useEffect(() => {
    setFast(shouldPollFast);
  }, [shouldPollFast]);

  const reloadAll = () => {
    workflow.reload();
    events.reload();
    investigations.reload();
    recoveries.reload();
  };

  const recommended = (investigations.data ?? []).find((i) => i.status === "completed");
  const prefill =
    recommended && recommended.recommended_action && recommended.recommended_action !== "no_action"
      ? recommended.recommended_action
      : null;

  if (workflow.error && !w) {
    return (
      <>
        <PageHeader title="Workflow" />
        <ErrorBanner message={workflow.error} />
        <Link to="/workflows">← Back to workflows</Link>
      </>
    );
  }

  if (!w) return <div className="splash">Loading…</div>;

  return (
    <>
      <PageHeader
        title={`Workflow ${shortId(w.id)}`}
        subtitle={`Order ${shortId(w.order_id)}`}
        action={<StatusBadge status={w.status} />}
      />
      <Link to="/workflows" className="back">
        ← All workflows
      </Link>

      <Card>
        <Stepper workflow={w} />
        <Facts workflow={w} />
        {w.reservation_status === "reserved" && (w.status === "failed" || w.status === "needs_review") && (
          <div className="banner banner-warn">
            <strong>Stock is still reserved for this order.</strong> If the order cannot complete, request{" "}
            <em>Release reserved stock</em> so the inventory is not held for nothing.
          </div>
        )}
        {w.status === "compensated" && (
          <div className="banner banner-info">
            <strong>Compensated.</strong> The reserved stock was released and the order cancelled. Place a new order
            to try again.
          </div>
        )}
        {w.last_error_code && w.status !== "completed" && (
          <div className="banner banner-error">
            <strong>{w.last_error_code}</strong>
            <div>{w.last_error_message}</div>
          </div>
        )}
      </Card>

      <div className="grid-2 grid-wide">
        <div className="stack">
          <InvestigationPanel
            workflowId={w.id}
            investigations={investigations.data ?? []}
            onChange={reloadAll}
          />
          <RecoveryPanel
            workflow={w}
            actions={recoveries.data ?? []}
            investigations={investigations.data ?? []}
            onChange={reloadAll}
            prefill={prefill}
          />
        </div>

        <Card title="Audit trail">
          <Timeline events={events.data ?? []} />
        </Card>
      </div>
    </>
  );
}
