import logging
from collections.abc import Callable
from typing import Any, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.agents.guardrails import apply_guardrails
from app.agents.prompts.root_cause import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    build_prompt,
)
from app.agents.schemas import EvidenceItem, InvestigationResult
from app.agents.tools.invoice_lookup import lookup_invoice
from app.agents.tools.operation_lookup import lookup_operations
from app.agents.tools.reservation_lookup import lookup_reservation
from app.agents.tools.retry_history import get_retry_history
from app.agents.tools.workflow_history import get_workflow_history
from app.domain.enums import RecommendedAction
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.llm.client import (
    GeminiInvestigationClient,
    LLMUsage,
)

logger = logging.getLogger(__name__)

# (prompt, system_instruction) -> (result, usage)
Analyzer = Callable[[str, str], tuple[InvestigationResult, LLMUsage | None]]


class WorkflowMissing(Exception):
    pass


class InvestigatorState(TypedDict, total=False):
    workflow_id: str
    evidence: dict[str, Any]
    result: InvestigationResult
    usage: LLMUsage | None
    analysis_error: str
    outcome: Any
    prompt_version: str


def load_workflow(state: InvestigatorState) -> InvestigatorState:
    with SessionLocal() as db:
        history = get_workflow_history(db, UUID(state["workflow_id"]))

    if history is None:
        raise WorkflowMissing(state["workflow_id"])

    return {"evidence": history}


def collect_evidence(state: InvestigatorState) -> InvestigatorState:
    evidence = dict(state["evidence"])
    workflow_id = UUID(state["workflow_id"])
    order_ref = evidence["order"]["ref"]
    order_id = UUID(order_ref.split(":", 1)[1])

    with SessionLocal() as db:
        evidence["reservation"] = lookup_reservation(db, order_id)
        evidence["invoice"] = lookup_invoice(db, order_id)
        evidence["operations"] = lookup_operations(db, workflow_id)
        evidence["retry_history"] = get_retry_history(db, workflow_id)

    return {"evidence": evidence}


def route_after_evidence(state: InvestigatorState) -> str:
    # Nothing to analyze for a finished workflow: skip the model call.
    if state["evidence"]["workflow"]["status"] in ("completed", "compensated"):
        return "nothing_to_recover"
    return "analyze"


def nothing_to_recover(state: InvestigatorState) -> InvestigatorState:
    workflow = state["evidence"]["workflow"]
    compensated = workflow["status"] == "compensated"
    return {
        "result": InvestigationResult(
            root_cause=(
                "The workflow failed and was already compensated: its "
                "reserved stock has been released."
                if compensated
                else "The workflow completed successfully."
            ),
            recommended_action=RecommendedAction.NO_ACTION,
            reasoning="No failure is outstanding, so no recovery is needed.",
            evidence=[
                EvidenceItem(
                    source="workflow_history",
                    reference=workflow["ref"],
                    observation=f"Workflow status is {workflow['status']}.",
                )
            ],
            confidence=1.0,
            requires_approval=False,
        ),
        "usage": None,
    }


def make_analyze(analyzer: Analyzer):
    def analyze(state: InvestigatorState) -> InvestigatorState:
        prompt = build_prompt(state["evidence"])

        try:
            result, usage = analyzer(prompt, SYSTEM_INSTRUCTION)
        except Exception as exc:
            logger.warning(
                "investigation_analysis_failed",
                exc_info=True,
                extra={"workflow_id": state["workflow_id"]},
            )
            return {"analysis_error": f"{type(exc).__name__}: {exc}"[:500]}

        return {"result": result, "usage": usage}

    return analyze


def validate(state: InvestigatorState) -> InvestigatorState:
    if "result" not in state:
        return {}

    return {
        "outcome": apply_guardrails(state["result"], state["evidence"]),
        "prompt_version": PROMPT_VERSION,
    }


def build_graph(analyzer: Analyzer):
    builder = StateGraph(InvestigatorState)

    builder.add_node("load_workflow", load_workflow)
    builder.add_node("collect_evidence", collect_evidence)
    builder.add_node("analyze", make_analyze(analyzer))
    builder.add_node("nothing_to_recover", nothing_to_recover)
    builder.add_node("validate", validate)

    builder.add_edge(START, "load_workflow")
    builder.add_edge("load_workflow", "collect_evidence")
    builder.add_conditional_edges(
        "collect_evidence",
        route_after_evidence,
        {"analyze": "analyze", "nothing_to_recover": "nothing_to_recover"},
    )
    builder.add_edge("analyze", "validate")
    builder.add_edge("nothing_to_recover", "validate")
    builder.add_edge("validate", END)

    return builder.compile()


def _default_analyzer() -> Analyzer:
    client = GeminiInvestigationClient()
    return client.investigate


def run_investigation_graph(
    workflow_id: UUID,
    analyzer: Analyzer | None = None,
) -> InvestigatorState:
    """Run the investigation. Pure read-only: it never changes workflow
    state, which stays the job of the recovery APIs."""
    graph = build_graph(analyzer or _lazy_analyzer())
    return graph.invoke({"workflow_id": str(workflow_id)})


def _lazy_analyzer() -> Analyzer:
    """Defer building the Gemini client so a missing key fails the
    analysis step (recorded on the investigation), not graph setup."""
    holder: dict[str, Analyzer] = {}

    def analyzer(prompt: str, system_instruction: str):
        if "client" not in holder:
            holder["client"] = _default_analyzer()
        return holder["client"](prompt, system_instruction)

    return analyzer
