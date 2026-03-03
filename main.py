from fastapi import FastAPI
from pydantic import BaseModel
import json
from dotenv import load_dotenv
load_dotenv()

from agent.graph import build_graph
graph_app = build_graph()

app = FastAPI(title="Stock Analysis AI Agent API")

class QueryRequest(BaseModel):
    query: str

@app.post("/analyze")
async def analyze_stock(request: QueryRequest):
    # 1. LangGraph 에이전트에 질문을 넣고 실행 (invoke)
    result = graph_app.invoke({
        "query": request.query,
        "context": [],
        "collected_sources": [],
        "analysis": "",
        "final_result": ""
    })
    
    # 2. 매니저 에이전트가 만든 JSON 문자열을 파이썬 딕셔너리로 변환
    try:
        final_strategy = json.loads(result["final_result"])
    except json.JSONDecodeError:
        final_strategy = {"error": "전략 결과를 파싱하는데 실패했습니다."}
    
    # 3. 수집가가 사용한 데이터 파일 목록을 마크다운으로 포맷
    sources = result.get("collected_sources") or []
    collector_text = "**📁 분석에 사용된 데이터 파일 목록**\n\n"
    if sources:
        collector_text += "\n".join(f"- {s}" for s in sources)
    else:
        collector_text += "*(수집된 데이터 없음)*"
    
    # 4. 분석 리포트와 최종 전략을 묶어서 반환
    return {
        "collector": collector_text,
        "analysis": result["analysis"],
        "strategy": final_strategy
    }

#from fastapi import FastAPI
#from pydantic import BaseModel
#import asyncio # 대기 시간(로딩 효과)을 주기 위한 라이브러리
#
## 🚨 API 키 오류를 피하기 위해 진짜 AI 모델 연결 부분은 잠시 주석 처리합니다!
## from agent.graph import build_graph
## graph_app = build_graph()
#
#app = FastAPI(title="Stock Analysis AI Agent API (Test Mode)")
#
#class QueryRequest(BaseModel):
#    query: str
#
#@app.post("/analyze")
#async def analyze_stock(request: QueryRequest):
#    # 진짜 AI가 생각하는 것처럼 2초 정도 로딩 대기 시간을 줍니다 ⏱️
#    await asyncio.sleep(2)
#    
#    # 가짜(Mock) 분석 리포트 데이터
#    dummy_analysis = """
#    이것은 API 키 없이 화면을 확인하기 위한 **가상(Mock) 테스트 리포트**입니다. 🚀
#    
#    1. **핵심 요약**: AI 반도체 수요 증가라는 긍정적 요인과 단기적 지정학적 리스크가 혼재되어 있습니다.
#    2. **펀더멘털 분석**: 시장 지배력은 여전히 강력하며, 장기적인 펀더멘털 훼손은 제한적입니다.
#    3. **종합 전망**: 단기 변동성 장세가 예상되나, 중장기적 관점에서는 매력적인 진입 구간이 될 수 있습니다.
#    """
#    
#    # 가짜(Mock) 최종 전략 데이터 (JSON 구조)
#    dummy_strategy = {
#        "investment_opinion": "분할 매수",
#        "portfolio_weight": "30%",
#        "reason": "[테스트] 단기 리스크보다 장기 성장성이 더 크다고 판단됨."
#    }
#    
#    return {
#        "analysis": dummy_analysis,
#        "strategy": dummy_strategy
#    }