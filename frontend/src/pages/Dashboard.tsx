import { Link } from "react-router-dom";
import { api } from "../api";
import type { WorkflowStatus } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBanner, PageHeader, StatusBadge } from "../components/ui";
import { usePoll } from "../usePoll";
import { timeAgo } from "../util";

const ORDER: WorkflowStatus[] = [
  "completed",
  "processing",
  "retry_scheduled",
  "pending",
  "needs_review",
  "failed",
  "compensated",
];

export default function Dashboard() {
  const { user } = useAuth();
  const workflows = usePoll(() => api.workflows(), 5000);
  const pending = usePoll(
    () => (user?.role === "admin" ? api.recoveryQueue("requested") : Promise.resolve([])),
    5000,
    [user?.role],
  );

  const held = usePoll(() => api.heldStock(), 5000);
  const heldCount = held.data?.length ?? 0;
  const list = workflows.data ?? [];
  const counts = ORDER.map((status) => ({ status, count: list.filter((w) => w.status === status).length }));
  const attention = list.filter((w) => w.status === "needs_review" || w.status === "failed").slice(0, 8);
  const recent = list.slice(0, 8);
  const awaiting = pending.data?.length ?? 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={user?.role === "admin" ? "Everything across all operators" : "Your orders and workflows"}
        action={
          <Link className="btn btn-primary" to="/orders?new=1">
            New order
          </Link>
        }
      />
      <ErrorBanner message={workflows.error} />

      <div className="stats">
        {counts.map(({ status, count }) => (
          <Link to={`/workflows?status=${status}`} key={status} className={`stat stat-${status}`}>
            <span className="stat-value">{count}</span>
            <StatusBadge status={status} />
          </Link>
        ))}
      </div>

      {heldCount > 0 && (
        <div className="banner banner-warn held">
          <span>
            <strong>{heldCount}</strong> failed {heldCount === 1 ? "order is" : "orders are"} still holding reserved
            stock.
          </span>
          <Link to="/workflows?view=held">See which</Link>
        </div>
      )}

      {user?.role === "admin" && awaiting > 0 && (
        <div className="banner banner-info">
          <strong>{awaiting}</strong> recovery {awaiting === 1 ? "request is" : "requests are"} waiting for approval.{" "}
          <Link to="/approvals">Review now</Link>
        </div>
      )}

      <div className="grid-2">
        <Card title="Needs attention">
          {attention.length === 0 ? (
            <Empty>Nothing needs attention.</Empty>
          ) : (
            <ul className="rows">
              {attention.map((w) => (
                <li key={w.id}>
                  <Link to={`/workflows/${w.id}`} className="row-link">
                    <div>
                      <strong>{w.product_id}</strong> <span className="muted">× {w.quantity}</span>
                      <div className="muted small">{w.last_error_code ?? "—"}</div>
                    </div>
                    <div className="right">
                      <StatusBadge status={w.status} />
                      <div className="muted small">{timeAgo(w.updated_at)}</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent workflows" action={<Link to="/workflows">View all</Link>}>
          {recent.length === 0 ? (
            <Empty>
              No workflows yet. <Link to="/orders?new=1">Create an order</Link> to get started.
            </Empty>
          ) : (
            <ul className="rows">
              {recent.map((w) => (
                <li key={w.id}>
                  <Link to={`/workflows/${w.id}`} className="row-link">
                    <div>
                      <strong>{w.product_id}</strong> <span className="muted">× {w.quantity}</span>
                      <div className="muted small">attempt {w.attempts}</div>
                    </div>
                    <div className="right">
                      <StatusBadge status={w.status} />
                      <div className="muted small">{timeAgo(w.created_at)}</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
