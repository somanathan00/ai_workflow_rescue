"""Drive the failure scenarios through the public API.

    python3 scripts/simulate_failure.py scenarios
    python3 scripts/simulate_failure.py demo --investigate

Credentials come from the environment (defaults match `make seed` in
development): OPERATOR_USERNAME/OPERATOR_PASSWORD, ADMIN_USERNAME/
ADMIN_PASSWORD. Only works where failure injection is enabled
(ENVIRONMENT=development or test).
"""

import argparse
import os
import sys
import time
import uuid

import httpx

TERMINAL = {"completed", "failed", "needs_review"}

SCENARIOS = [
    ("LAPTOP-001", "completed", "no failure"),
    ("SIM-RECOVER", "completed", "fails twice, succeeds on attempt 3"),
    ("SIM-TRANSIENT", "failed", "retry budget exhausted"),
    ("SIM-PERMANENT", "failed", "unsupported product, no retry"),
    ("SIM-UNCERTAIN", "needs_review", "reservation committed, response lost"),
    ("SIM-INVOICE-FAIL", "failed", "invoice rejected after stock was reserved"),
]


def client(base: str, username: str, password: str) -> httpx.Client:
    http = httpx.Client(base_url=f"{base}/api/v1", timeout=15)
    response = http.post(
        "/auth/login", data={"username": username, "password": password}
    )
    response.raise_for_status()
    http.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return http


def wait_for(http, workflow_id, wanted, timeout):
    """Poll until the workflow reaches a status in `wanted`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        workflow = http.get(f"/workflows/{workflow_id}").json()
        if workflow["status"] in wanted:
            return workflow
        time.sleep(1)
    return http.get(f"/workflows/{workflow_id}").json()


def create_order(http, product_id, quantity=2):
    response = http.post(
        "/orders",
        json={"product_id": product_id, "quantity": quantity},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    response.raise_for_status()
    return response.json()


def scenarios(args) -> int:
    http = client(args.base_url, args.operator, args.operator_password)
    failures = 0

    print(f"{'product':<15}{'expected':<14}{'actual':<14}{'attempts':<9}note")
    for product_id, expected, note in SCENARIOS:
        order = create_order(http, product_id)
        workflow = wait_for(http, order["workflow_id"], TERMINAL, args.timeout)
        ok = workflow["status"] == expected
        failures += not ok
        flag = "" if ok else "   <-- UNEXPECTED"
        print(
            f"{product_id:<15}{expected:<14}{workflow['status']:<14}"
            f"{workflow['attempts']:<9}{note}{flag}"
        )

    return 1 if failures else 0


def demo(args) -> int:
    operator = client(args.base_url, args.operator, args.operator_password)
    admin = client(args.base_url, args.admin, args.admin_password)

    print("1. Create a SIM-UNCERTAIN order")
    order = create_order(operator, "SIM-UNCERTAIN")
    workflow_id = order["workflow_id"]
    workflow = wait_for(operator, workflow_id, {"needs_review"}, args.timeout)
    print(f"   workflow {workflow_id}: {workflow['status']} ({workflow['last_error_code']})")
    if workflow["status"] != "needs_review":
        return 1

    recommended = "reconcile_and_resume"
    investigation_id = None

    if args.investigate:
        print("2. Ask the AI investigator")
        started = operator.post(f"/workflows/{workflow_id}/investigate").json()
        deadline = time.monotonic() + args.timeout * 3
        result = started
        while time.monotonic() < deadline and result["status"] in {"pending", "running"}:
            time.sleep(2)
            result = operator.get(f"/investigations/{started['id']}").json()
        print(
            f"   status={result['status']} action={result['recommended_action']} "
            f"confidence={result['confidence']}"
        )
        if result["status"] == "completed":
            print(f"   root cause: {result['root_cause']}")
            investigation_id = result["id"]
            recommended = result["recommended_action"]
        else:
            print(f"   investigation unavailable: {result['error_message']}")
            print("   continuing with the deterministic recovery path")
    else:
        print("2. (skipping AI investigation; pass --investigate)")

    print(f"3. Request recovery: {recommended}")
    body = {
        "action_type": recommended,
        "reason": "Inventory reservation outcome is uncertain and needs verification.",
    }
    if investigation_id:
        body["investigation_id"] = investigation_id
    action = operator.post(f"/workflows/{workflow_id}/recovery-actions", json=body)
    action.raise_for_status()
    action_id = action.json()["id"]
    base = f"/workflows/{workflow_id}/recovery-actions/{action_id}"

    print("4. Admin approves")
    admin.post(f"{base}/approve").raise_for_status()

    print("5. Queue execution (outbox -> Celery)")
    queued = operator.post(f"{base}/execute")
    print(f"   HTTP {queued.status_code}, status={queued.json()['status']}")

    workflow = wait_for(operator, workflow_id, {"completed", "failed"}, args.timeout)
    print(f"6. Final workflow status: {workflow['status']}")

    print("7. Audit trail:")
    for event in operator.get(f"/workflows/{workflow_id}/events").json():
        print(f"   {event['event_type']}")

    order_id = order["order_id"]
    print("\nVerify exactly one reservation and one invoice:")
    print(
        "  docker compose exec postgres psql -U workflow workflow_db -c "
        f"\"select (select count(*) from inventory_reservations "
        f"where order_id='{order_id}') as reservations, "
        f"(select count(*) from invoices where order_id='{order_id}') as invoices\""
    )
    return 0 if workflow["status"] == "completed" else 1


def main() -> int:
    env = os.environ.get
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scenarios", "demo"])
    parser.add_argument("--base-url", default=env("API_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--investigate", action="store_true")
    parser.add_argument("--operator", default=env("OPERATOR_USERNAME", "operator"))
    parser.add_argument(
        "--operator-password", default=env("OPERATOR_PASSWORD", "operator-change-me-now")
    )
    parser.add_argument("--admin", default=env("ADMIN_USERNAME", "admin"))
    parser.add_argument(
        "--admin-password", default=env("ADMIN_PASSWORD", "admin-change-me-now")
    )
    args = parser.parse_args()

    return {"scenarios": scenarios, "demo": demo}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
