from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import json

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

        # Collector 단계에서 설정된 에러를 명시적으로 처리 (데이터 부족 등)
        if result.get("error"):
            raise HTTPException(status_code=422, detail=result["error"])

        context_data = result.get("context", "수집된 데이터가 없습니다.")
        analysis_data = result.get("analysis", "분석 결과가 없습니다.")
        final_result_str = result.get("final_result", "{}")

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
            collector=context_data,
            analysis=analysis_data,
            strategy=strategy_json,
        )

    except HTTPException:
        # 이미 의미 있는 HTTPException이면 그대로 전달
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 실행 중 오류 발생: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)