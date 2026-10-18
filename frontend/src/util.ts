import type { ActionType, Workflow, WorkflowStatus } from "./api";

export const shortId = (id: string) => id.slice(0, 8);

export function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const dateTime = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export const fmtTime = (iso: string | null) => (iso ? dateTime.format(new Date(iso)) : "—");

export function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export const humanize = (value: string) => value.replace(/[._]/g, " ");

export const ACTIVE_WORKFLOW: WorkflowStatus[] = ["pending", "processing", "retry_scheduled"];

export const ACTION_LABEL: Record<ActionType | "no_action", string> = {
  retry_workflow: "Retry workflow",
  reconcile_and_resume: "Reconcile and resume",
  mark_for_review: "Mark for review",
  release_reservation: "Release reserved stock",
  no_action: "No action",
};

export const ACTION_HELP: Record<ActionType, string> = {
  retry_workflow:
    "Run the failed step once more. Only for transient failures; the automatic retry budget is not reset.",
  reconcile_and_resume:
    "Verify the existing reservation against the order, then continue from invoice generation.",
  mark_for_review: "Keep the workflow stopped until a person investigates.",
  release_reservation:
    "Give the reserved stock back and close the order as compensated. For orders that can't complete.",
};

/** Mirrors the backend recovery policy so the UI can explain why an action is unavailable.
 *  The backend remains the authority and re-validates every request. */
export function ineligibleReason(workflow: Workflow, action: ActionType): string | null {
  if (workflow.status === "completed") return "Workflow already completed";
  if (workflow.status === "compensated") return "Already compensated (stock released)";

  switch (action) {
    case "retry_workflow":
      return workflow.status === "failed" && workflow.last_error_code === "TRANSIENT_ERROR"
        ? null
        : "Needs a failed workflow with a transient error";
    case "reconcile_and_resume":
      return workflow.status === "needs_review" && workflow.last_error_code === "UNCERTAIN_OUTCOME"
        ? null
        : "Needs an uncertain outcome awaiting review";
    case "mark_for_review":
      return workflow.status === "failed" || workflow.status === "needs_review"
        ? null
        : "Needs a failed or in-review workflow";
    case "release_reservation":
      if (workflow.status !== "failed" && workflow.status !== "needs_review") {
        return "Needs a failed or in-review workflow";
      }
      return workflow.reservation_status === "reserved" || workflow.reservation_status === "released"
        ? null
        : "No stock is reserved for this order";
  }
}

export const ACTIVE_RECOVERY = ["requested", "approved", "queued", "executing"];
