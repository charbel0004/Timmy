"""Guarded, request-scoped LangGraph orchestration of approved backend steps.

Only server-owned workflow definitions are accepted. The graph never treats
model text, a knowledge note, or a tool name as an executable handler.
The evaluator is the existing permission-checked deterministic service layer.
No automatic retries, external effects, or financial writes are introduced.
"""
from __future__ import annotations

import logging
from uuid import uuid4
from collections.abc import Callable, Sequence
from typing import TypedDict

from .observability import span, reference, current as active_trace, parent as active_parent
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)
SUCCESS = "completed"
VALID_OUTCOMES = frozenset({"completed", "needs_review", "blocked", "failed"})


class ExecutionState(TypedDict):
    blocked_by: str | None


def dependency_hold(step: str, blocked_by: str, *, read_only: dict | None = None) -> dict:
    """Document an uninvoked dependency, optionally with precomputed evidence.

    The optional context must already be available: this function never invokes
    a downstream handler or verifies the step's business prerequisites.
    """
    data = dict(read_only or {})
    known = list(data.pop("unverified_requirements", []))
    return {
        "step": step,
        "status": "blocked",  # Preserve existing public status vocabulary.
        "issue_codes": ["DEPENDENCY_NOT_SATISFIED", *known],
        "unverified_requirements": known,
        "attempted": False,
        "executed": False,
        "blocked_by": blocked_by,
        **data,
    }


def safe_failure(step: str, code: str = "WORKFLOW_STEP_UNEXPECTED_ERROR") -> dict:
    return {
        "step": step,
        "status": "failed",
        "issue_codes": [code],
        "attempted": True,
        "executed": False,
        "diagnostic_ref": str(uuid4()),
    }


def execute_graph(
    ordered_steps: Sequence[str],
    evaluator: Callable[[str], dict],
    *,
    on_result: Callable[[dict], None] | None = None,
    blocked_context: Callable[[str], dict] | None = None,
) -> list[dict]:
    """Run an approved ordered workflow exactly once.

    Precondition: the caller authenticated the actor, rechecked project scope,
    verified evidence, and bound evaluator to reviewed backend functions.
    A review, blocker or failure stops ALL dependent handler invocations.
    Each downstream receipt is retained as a nonexecuted dependency hold.
    A source/DB transaction still belongs to the caller, not to LangGraph.
    """
    steps = tuple(ordered_steps)
    if not steps or len(set(steps)) != len(steps) or any(not s or not isinstance(s, str) for s in steps):
        raise ValueError("Invalid approved workflow steps")

    receipts: list[dict] = []
    graph = StateGraph(ExecutionState)
    previous = START
    last_invoked = None

    for index, step in enumerate(steps):
        name = f"step_{index}"

        def execute(state: ExecutionState, *, current: str = step) -> ExecutionState:
            nonlocal last_invoked
            blocked_by = state.get("blocked_by")
            if blocked_by is not None:
                result = dependency_hold(
                    current, blocked_by,
                    read_only=blocked_context(current) if blocked_context else None,
                )
            else:
                try:
                    with span(current, 'validation') as observation:
                        trace = active_trace.get()
                        invoked = active_parent.get()
                        if trace and last_invoked:
                            trace.emit('span.link', invoked, parent_id=trace.root,
                                       category='dependency', operation='depends_on', reference_id=last_invoked)
                        last_invoked = invoked
                        result = evaluator(current)
                        if (not isinstance(result, dict) or result.get("step") != current
                                or result.get("status") not in VALID_OUTCOMES):
                            result = safe_failure(current, "INVALID_STEP_RESULT")
                        observation['status'] = result['status']
                        reference(current, 'executed', 'application-code', status=result['status'])
                except Exception as error:
                    # Raw exception text may contain private spreadsheet values.
                    logger.error("Workflow step failed step=%s error_type=%s",
                                 current, type(error).__name__)
                    result = safe_failure(current)
            if on_result is not None:
                on_result(result)
            receipts.append(result)
            return {"blocked_by": blocked_by if blocked_by is not None else
                    (current if result["status"] != SUCCESS else None)}

        graph.add_node(name, execute)
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    graph.compile().invoke({"blocked_by": None})
    return receipts
