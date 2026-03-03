from typing import TypedDict, List

class AgentState(TypedDict):
    """
    LangGraph에서 에이전트들이 서로 주고받을 데이터 구조.
    """
    query: str          # 사용자의 질문 (예: "삼성전자 전망 어때?")
    context: List[str]  # 수집가가 RAG에서 찾아온 문서 내용들
    analysis: str       # 분석가가 작성한 심층 분석 리포트
    final_result: str   # 매니저가 결정한 최종 투자 전략 (JSON)