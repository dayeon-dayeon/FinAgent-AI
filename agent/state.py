from typing import Annotated, Any, List, TypedDict, Optional, Union
from operator import add

class AgentState(TypedDict, total=False):
    query: str
    collected_sources: Annotated[List[str], add]
    context: str
    """분석가·매니저용 전체 컨텍스트(연관성 필터 적용)."""
    collector_display: str
    """Streamlit 등 UI용 요약(원문 블록 없음)."""
    stock_chart: list[dict[str, Any]]
    analysis: str
    final_result: Union[str, dict]
    ticker: Optional[str]
    ticker_detected: bool
    rag_hit: bool
    error: Optional[str]