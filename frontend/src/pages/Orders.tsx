import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Card, Empty, ErrorBanner, PageHeader, StatusBadge } from "../components/ui";
import { usePoll } from "../usePoll";
import { fmtTime, newKey, shortId } from "../util";

const SCENARIOS = [
  { id: "LAPTOP-001", title: "Normal order", hint: "Completes with no failure." },
  { id: "SIM-RECOVER", title: "Recovers by itself", hint: "Fails twice, then succeeds on attempt 3." },
  { id: "SIM-TRANSIENT", title: "Retries exhausted", hint: "Always fails; ends as failed after 3 attempts." },
  { id: "SIM-PERMANENT", title: "Permanent failure", hint: "Fails at once, no retry." },
  { id: "SIM-UNCERTAIN", title: "Lost response", hint: "Reservation is committed but the reply is lost → needs review." },
  { id: "SIM-INVOICE-FAIL", title: "Stock stuck", hint: "Invoice fails after stock was reserved → stock stays held until released." },
];

function NewOrderForm({ onCancel }: { onCancel: () => void }) {
  const navigate = useNavigate();
  const [product, setProduct] = useState(SCENARIOS[0].id);
  const [custom, setCustom] = useState("");
  const [quantity, setQuantity] = useState(2);
  const [key] = useState(newKey);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const productId = product === "__custom" ? custom.trim() : product;
  const scenario = SCENARIOS.find((s) => s.id === product);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const accepted = await api.createOrder(productId, quantity, key);
      navigate(`/workflows/${accepted.workflow_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the order");
      setBusy(false);
    }
  }

  return (
    <Card title="New order">
      <form className="form" onSubmit={submit}>
        <div className="scenario-grid" role="radiogroup" aria-label="Scenario">
          {SCENARIOS.map((s) => (
            <button
              type="button"
              key={s.id}
              role="radio"
              aria-checked={product === s.id}
              className={`scenario ${product === s.id ? "selected" : ""}`}
              onClick={() => setProduct(s.id)}
            >
              <strong>{s.title}</strong>
              <code>{s.id}</code>
              <span>{s.hint}</span>
            </button>
          ))}
          <button
            type="button"
            role="radio"
            aria-checked={product === "__custom"}
            className={`scenario ${product === "__custom" ? "selected" : ""}`}
            onClick={() => setProduct("__custom")}
          >
            <strong>Custom product</strong>
            <span>Any other product ID behaves like a normal order.</span>
          </button>
        </div>

        {product === "__custom" && (
          <label>
            Product ID
            <input value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={100} required />
          </label>
        )}

        <label>
          Quantity
          <input
            type="number"
            min={1}
            max={1000}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
            required
          />
        </label>

        {scenario?.id.startsWith("SIM-") && (
          <p className="muted small">
            Failure injection only works when the backend runs with <code>ENVIRONMENT=development</code>.
          </p>
        )}

        <ErrorBanner message={error} />

        <div className="actions">
          <button className="btn btn-primary" disabled={busy || !productId}>
            {busy ? "Submitting…" : "Place order"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
        <p className="muted small">
          Idempotency key <code>{shortId(key)}…</code> is attached, so double-clicking never creates two orders.
        </p>
      </form>
    </Card>
  );
}

export default function Orders() {
  const [params, setParams] = useSearchParams();
  const showForm = params.get("new") === "1";
  const orders = usePoll(() => api.orders(), 4000);

  const closeForm = () => setParams({});

  return (
    <>
      <PageHeader
        title="Orders"
        subtitle="Each order starts a workflow: validate → reserve inventory → invoice."
        action={
          !showForm && (
            <button className="btn btn-primary" onClick={() => setParams({ new: "1" })}>
              New order
            </button>
          )
        }
      />

      {showForm && <NewOrderForm onCancel={closeForm} />}
      <ErrorBanner message={orders.error} />

      <Card>
        {orders.loading && !orders.data ? (
          <Empty>Loading…</Empty>
        ) : (orders.data ?? []).length === 0 ? (
          <Empty>No orders yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Qty</th>
                  <th>Workflow</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {orders.data!.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.product_id}</strong>
                      <div className="muted small">order {shortId(o.id)}</div>
                    </td>
                    <td>{o.quantity}</td>
                    <td>
                      <StatusBadge status={o.workflow_status} />
                    </td>
                    <td className="muted">{fmtTime(o.created_at)}</td>
                    <td className="right">
                      <Link to={`/workflows/${o.workflow_id}`}>Open →</Link>
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
