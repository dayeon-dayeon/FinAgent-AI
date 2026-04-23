from langgraph.graph import StateGraph, END
from .nodes import collector_node, analyst_node, manager_node, alternative_advisor_node
from .state import AgentState

def should_continue(state: AgentState):
    if not state.get("collected_sources") or state.get("error"):
        return "end"
    return "continue"

def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("collector", collector_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("manager", manager_node)
    workflow.add_node("alternative_advisor", alternative_advisor_node)

    workflow.set_entry_point("collector")
    
    workflow.add_conditional_edges(
        "collector",
        should_continue,
        {
            "continue": "analyst",
            "end": END
        }
    )
    
    workflow.add_edge("analyst", "manager")
    workflow.add_edge("manager", "alternative_advisor")
    workflow.add_edge("alternative_advisor", END)

    return workflow.compile()