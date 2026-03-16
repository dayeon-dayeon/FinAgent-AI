from typing import Annotated, List, TypedDict, Optional, Union
from operator import add

class AgentState(TypedDict, total=False):
    query: str
    collected_sources: Annotated[List[str], add]
    context: str
    analysis: str
    final_result: Union[str, dict]
    ticker: Optional[str]
    ticker_detected: bool
    rag_hit: bool
    error: Optional[str]