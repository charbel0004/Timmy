"""Request-scoped LangGraph execution for authorized structural reads."""
from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .instruction_pack import action_instructions


class StructuralState(TypedDict, total=False):
    action_id: str
    result: str


def inspect_spreadsheets(reader: Callable[[], str]) -> str:
    """Keep database handles and private spreadsheet content outside graph state."""
    def verify_pack(state: StructuralState) -> dict:
        action_instructions(state["action_id"])
        return {}

    def execute(_state: StructuralState) -> StructuralState:
        # The callback resolves the authenticated actor and scope at execution.
        return {"result": reader()}

    def verify_result(state: StructuralState) -> dict:
        if not state["result"].strip():
            raise ValueError("Spreadsheet inspection returned an empty result")
        return {}

    graph = StateGraph(StructuralState)
    graph.add_node("verify_instruction_pack", verify_pack)
    graph.add_node("read_project_evidence", execute)
    graph.add_node("verify_result", verify_result)
    graph.add_edge(START, "verify_instruction_pack")
    graph.add_edge("verify_instruction_pack", "read_project_evidence")
    graph.add_edge("read_project_evidence", "verify_result")
    graph.add_edge("verify_result", END)
    result = graph.compile().invoke({"action_id": "ACT-07"})
    return result["result"]
