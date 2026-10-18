import type { ReactNode } from "react";
import type { Workflow, WorkflowEvent, WorkflowStep } from "../api";
import { fmtTime, humanize } from "../util";

const STATUS_LABEL: Record<string, string> = {
  retry_scheduled: "retry scheduled",
  needs_review: "needs review",
  compensated: "stock released",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status}`}>
      <span className="dot" />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="banner banner-error" role="alert">
      {message}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Card({
  title,
  action,
  children,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || action) && (
        <header className="card-head">
          <h2>{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const STEPS: { key: WorkflowStep; label: string }[] = [
  { key: "validate_order", label: "Validate order" },
  { key: "reserve_inventory", label: "Reserve inventory" },
  { key: "generate_invoice", label: "Generate invoice" },
];

type StepState = "done" | "current" | "failed" | "waiting" | "todo" | "undone";

function stepStates(workflow: Workflow): StepState[] {
  if (workflow.status === "completed") return STEPS.map(() => "done");

  // Compensated: the reservation was undone, so that step shows as rolled back.
  if (workflow.status === "compensated") return ["done", "undone", "todo"];

  const currentIndex = STEPS.findIndex((s) => s.key === workflow.current_step);

  return STEPS.map((_, index) => {
    if (index < currentIndex) return "done";
    if (index > currentIndex) return "todo";
    if (workflow.status === "failed") return "failed";
    if (workflow.status === "needs_review") return "waiting";
    return "current";
  });
}

export function Stepper({ workflow }: { workflow: Workflow }) {
  const states = stepStates(workflow);

  return (
    <ol className="stepper">
      {STEPS.map((step, index) => (
        <li key={step.key} className={`step step-${states[index]}`}>
          <span className="step-icon">
            {states[index] === "done"
              ? "✓"
              : states[index] === "failed"
                ? "!"
                : states[index] === "waiting"
                  ? "?"
                  : states[index] === "undone"
                    ? "↩"
                    : index + 1}
          </span>
          <span className="step-label">{step.label}</span>
        </li>
      ))}
    </ol>
  );
}

const TONE: Record<string, string> = {
  step_completed: "success",
  workflow_completed: "success",
  reservation_confirmed: "success",
  reconciliation_completed: "success",
  recovery_executed: "success",
  reservation_released: "success",
  workflow_compensated: "success",
  compensation_started: "warning",
  investigation_completed: "success",
  recovery_approved: "success",
  step_failed: "warning",
  retry_scheduled: "warning",
  retry_started: "warning",
  reservation_outcome_uncertain: "warning",
  reconciliation_inconclusive: "warning",
  workflow_failed: "danger",
  recovery_failed: "danger",
  recovery_rejected: "danger",
  investigation_failed: "danger",
  reconciliation_conflict: "danger",
};

function eventSummary(event: WorkflowEvent): string | null {
  const d = event.details;
  const parts: string[] = [];

  if (typeof d.attempt === "number") parts.push(`attempt ${d.attempt}`);
  if (typeof d.delay_seconds === "number") parts.push(`in ${d.delay_seconds}s`);
  if (typeof d.error_code === "string") parts.push(d.error_code);
  if (typeof d.action_type === "string") parts.push(humanize(d.action_type));
  if (typeof d.recommended_action === "string") parts.push(`recommended ${humanize(d.recommended_action)}`);
  if (d.downgraded === true) parts.push("downgraded by guardrails");
  if (typeof d.message === "string") parts.push(d.message);
  if (typeof d.error === "string") parts.push(d.error);
  if (typeof d.reason === "string") parts.push(d.reason);

  return parts.length ? parts.join(" · ") : null;
}

export function Timeline({ events }: { events: WorkflowEvent[] }) {
  if (events.length === 0) return <Empty>No events yet.</Empty>;

  return (
    <ol className="timeline">
      {events.map((event) => {
        const summary = eventSummary(event);
        return (
          <li key={event.id} className={`tl tl-${TONE[event.event_type] ?? "info"}`}>
            <span className="tl-dot" />
            <div className="tl-body">
              <div className="tl-title">
                <strong>{humanize(event.event_type)}</strong>
                {event.step && <span className="chip">{humanize(event.step)}</span>}
              </div>
              {summary && <div className="tl-detail">{summary}</div>}
            </div>
            <time className="tl-time">{fmtTime(event.created_at)}</time>
          </li>
        );
      })}
    </ol>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = pct >= 80 ? "good" : pct >= 60 ? "ok" : "low";
  return (
    <div className="confidence" title={`Model-reported confidence: ${pct}%`}>
      <div className={`confidence-fill confidence-${tone}`} style={{ width: `${pct}%` }} />
      <span>{pct}%</span>
    </div>
  );
}
