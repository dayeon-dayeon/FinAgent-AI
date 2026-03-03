from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import collector_node, analyst_node, manager_node

def build_graph():
    """LangGraph를 이용해 Multi-Agent 워크플로우를 구성하고 반환합니다."""
    # 1. 그래프 초기화 (어떤 State를 쓸지 지정)
    workflow = StateGraph(AgentState)

    # 2. 노드(에이전트) 추가
    workflow.add_node("collector", collector_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("manager", manager_node)

    # 3. 엣지(흐름) 연결
    workflow.set_entry_point("collector")   # 시작점 설정
    workflow.add_edge("collector", "analyst") # 수집가 -> 분석가
    workflow.add_edge("analyst", "manager")   # 분석가 -> 매니저
    workflow.add_edge("manager", END)         # 매니저 -> 종료

    # 4. 그래프 컴파일 (실행 가능한 형태로 변환)
    app = workflow.compile()
    return app