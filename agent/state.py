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
    stock_specific: bool
    """질문이 '특정 종목/매매/주가'처럼 티커 식별이 필수인 유형인지 여부."""
    detected_companies: List[str]
    """질문에서 감지된 회사명(표시용)."""
    analysis: str
    final_result: Union[str, dict]
    ticker: Optional[str]
    ticker_detected: bool
    rag_hit: bool
    error: Optional[str]