from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import json
import os

app = FastAPI()


@app.get("/health")
def health():
    """nginx/로드밸런서 헬스 체크용. 502 원인 파악 시 백엔드 동작 여부 확인에 사용."""
    return {"status": "ok"}


from agent.graph import build_graph

graph = build_graph()


class QueryRequest(BaseModel):
    query: str


class AnalysisResponse(BaseModel):
    collector: str
    analysis: str
    strategy: Dict[str, Any]
    stock_chart: Optional[List[Dict[str, Any]]] = None
    alternative_advice: Optional[str] = None


class CollectNewsBody(BaseModel):
    rebuild_faiss: bool = False


def _normalize_strategy_keys(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    MANAGER_PROMPT의 영문 JSON 키를 Streamlit UI에서 사용하는 한글 키로 매핑합니다.
    """
    return {
        "투자의견": raw.get("investment_opinion", "N/A"),
        "권장 비중": raw.get("portfolio_weight", "N/A"),
        "결정 사유": raw.get("reason", "사유를 불러올 수 없습니다."),
        "💡 시기적 심리 변수 (주의사항)": raw.get("seasonal_variable", ""),
    }


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: QueryRequest):
    try:
        inputs = {"query": request.query}
        result = await graph.ainvoke(inputs)

        context_data = result.get("context", "수집된 데이터가 없습니다.")
        analysis_data = result.get("analysis", "분석 결과가 없습니다.")
        final_result_str = result.get("final_result", "{}")
        stock_chart = result.get("stock_chart") or []
        collector_ui = result.get("collector_display")
        if not collector_ui:
            collector_ui = (
                "## 수집 요약\n- UI용 요약을 불러오지 못했습니다. "
                "백엔드를 최신 코드로 재시작했는지 확인하세요."
            )

        # Collector 단계에서 설정된 에러 처리:
        # - 원문 근거가 부족해도 stock_chart(주가)가 있으면, UI에서 그래프는 보여줄 수 있도록 200으로 반환
        err = result.get("error")
        if err:
            if stock_chart:
                return AnalysisResponse(
                    collector=collector_ui,
                    analysis=f"데이터가 부족해 예측/전략 수립이 어렵습니다. 사유: {err}",
                    strategy={
                        "투자의견": "분석 불가",
                        "권장 비중": "0%",
                        "결정 사유": f"원문 뉴스/문서 근거가 부족합니다. ({err})",
                        "💡 시기적 심리 변수 (주의사항)": "해당 없음",
                    },
                    stock_chart=stock_chart,
                    alternative_advice=None,
                )
            raise HTTPException(status_code=422, detail=err)

        try:
            strategy_raw = json.loads(final_result_str)
            if not isinstance(strategy_raw, dict):
                raise ValueError("전략 응답이 JSON 객체가 아닙니다.")
            strategy_json = _normalize_strategy_keys(strategy_raw)
        except Exception:
            # JSON 파싱 실패 시에도 UI가 일관되게 동작하도록 기본 구조 유지
            strategy_json = {
                "투자의견": "N/A",
                "권장 비중": "N/A",
                "결정 사유": "JSON 파싱 오류가 발생했습니다.",
                "💡 시기적 심리 변수 (주의사항)": final_result_str,
            }

        return AnalysisResponse(
            collector=collector_ui,
            analysis=analysis_data,
            strategy=strategy_json,
            stock_chart=stock_chart if stock_chart else None,
            alternative_advice=result.get("alternative_advice"),
        )

    except HTTPException:
        # 이미 의미 있는 HTTPException이면 그대로 전달
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 실행 중 오류 발생: {str(e)}")


@app.post("/collect-news")
def collect_news(body: CollectNewsBody = CollectNewsBody()):
    """
    Streamlit 등 UI에서 호출: 오늘자 news_YYYYMMDD.txt 를 RSS+요약으로 다시 생성.
    rebuild_faiss=True 이면 data/ 기준 FAISS 인덱스도 재생성(시간·API 비용 증가).
    """
    try:
        from rag.economic_news import collect_todays_economic_news
        from rag.vector_store import create_vector_db

        data_dir = os.getenv("DATA_PATH", "data")
        out = collect_todays_economic_news(data_dir)
        faiss_ok: bool | None = None
        if body.rebuild_faiss:
            faiss_ok = create_vector_db() is not None
        return {"ok": True, "path": str(out.resolve()), "rebuild_faiss": faiss_ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)