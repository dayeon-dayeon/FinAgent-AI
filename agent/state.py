from typing import TypedDict, List

class _AgentStateRequired(TypedDict):
    query: str
    context: list
    analysis: str
    final_result: str

class AgentState(_AgentStateRequired, total=False):
    """
    LangGraph에서 에이전트들이 서로 주고받을 데이터 구조.
    """
    collected_sources: List[str]  # 수집가가 분석에 사용한 데이터 파일/출처 목록