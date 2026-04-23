import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

_KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="FinAgent-AI", page_icon="📈", layout="wide")

st.title("📈 AI 주가 분석 & 포트폴리오 에이전트 📈")
st.markdown("4명의 AI 에이전트가 데이터를 분석하고, 투자 전략을 제시합니다.")

# 환경 변수 / secrets 기반 백엔드 URL 설정
default_backend = "http://localhost:8000/analyze"
backend_from_env = os.getenv("BACKEND_URL")

# secrets.toml 이 없을 수 있으므로, 접근 자체를 try/except로 감쌉니다.
try:
    backend_from_secrets = st.secrets.get("BACKEND_URL")
except Exception:
    backend_from_secrets = None

BACKEND_URL = backend_from_secrets or backend_from_env or default_backend


def _api_base() -> str:
    u = BACKEND_URL.rstrip("/")
    if u.endswith("/analyze"):
        return u[: -len("/analyze")]
    return u


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _today_news_path() -> Path:
    tag = datetime.now(_KST).strftime("%Y%m%d")
    raw = os.getenv("DATA_PATH", "data")
    p = Path(raw)
    if not p.is_absolute():
        p = _project_root() / p
    return p / f"news_{tag}.txt"


if "history" not in st.session_state:
    st.session_state["history"] = []

with st.expander("📰 오늘 뉴스 재수집 ", expanded=False):
    np = _today_news_path()
    exists = np.is_file() and np.stat().st_size > 0
    if exists:
        st.success(f"오늘 뉴스 파일이 있습니다: `{np.name}`")
        st.caption(f"경로: `{np}` — **기존 파일로 분석**하려면 아래에서 질문만 입력하면 됩니다.")
    else:
        st.warning("오늘 뉴스 파일이 없습니다. `run.py`로 수집했거나 여기서 수집을 실행하세요.")

    rebuild_faiss = st.checkbox(
        "수집 후 FAISS 인덱스도 다시 만들기 (임베딩·시간 추가 소요)",
        value=False,
    )
    if st.button(
        "RSS에서 다시 수집하기" if exists else "뉴스 수집 실행하기",
        type="primary",
        help="백엔드 `POST /collect-news` 를 호출합니다.",
    ):
        try:
            with st.spinner("뉴스 수집 중… 완료될 때까지 창을 닫지 마세요."):
                resp = requests.post(
                    f"{_api_base()}/collect-news",
                    json={"rebuild_faiss": rebuild_faiss},
                    timeout=900,
                )
            if resp.status_code == 200:
                st.success(resp.json())
            else:
                st.error(f"{resp.status_code}: {resp.text}")
        except requests.RequestException as e:
            st.error(f"백엔드 요청 실패: {e}")

query = st.text_input(
    "관심 있는 기업이나 최근 경제 이슈에 대해 질문해 보세요. (ex :  최근 삼성전자 D램 이슈와 주가 전망 알려줘 / SK하이닉스의 1개월치 주가 데이터와 최근 이슈 분석해)"
)

if st.button("분석 시작"):
    if query:
        with st.spinner("AI 에이전트(수집가, 분석가, 매니저, 대안자산)가 분석 중입니다... 🤖"):
            try:
                response = requests.post(BACKEND_URL, json={"query": query})

                if response.status_code == 200:
                    data = response.json()

                    st.subheader("🔍 [Agent 1] 데이터 수집가")
                    try:
                        collector_text = data.get("collector", "")
                        st.markdown(collector_text)

                        chart_data = list(data.get("stock_chart") or [])
                        if not chart_data and collector_text:
                            lines = collector_text.split("\n")
                            current_stock = "주가"
                            is_stock_data = False
                            for line in lines:
                                name_match = re.search(r"\[출처:\s*(.*?)_실시간", line)
                                if name_match:
                                    current_stock = name_match.group(1)
                                    is_stock_data = True
                                    continue
                                price_match = re.search(r"- (\d{4}-\d{2}-\d{2}): 종가 (\d+)", line)
                                if price_match:
                                    chart_data.append(
                                        {
                                            "날짜": price_match.group(1),
                                            "종목": current_stock,
                                            "종가": int(price_match.group(2)),
                                        }
                                    )
                                    continue
                                if is_stock_data and line.strip() == "":
                                    is_stock_data = False

                        if chart_data:
                            df_chart = pd.DataFrame(chart_data)
                            
                            # Y축이 0부터 시작하지 않도록 (zero=False) 고급 차트 설정
                            chart = alt.Chart(df_chart).mark_line(point=True).encode(
                                x=alt.X('날짜:T', title='날짜'),
                                y=alt.Y('종가:Q', title='종가', scale=alt.Scale(zero=False)),
                                color=alt.Color('종목:N', title='종목'),
                                tooltip=['날짜:T', '종목:N', '종가:Q'] # 마우스 올리면 상세 정보 표시
                            ).properties(
                                title="📈 실시간 주가 추이 (Yahoo Finance · 기간은 수집 출처의 기간= 참고)",
                                height=400
                            ).interactive() # 마우스 휠로 확대/축소 가능
                            
                            st.altair_chart(chart, use_container_width=True)
                            
                    except Exception as e:
                        st.warning(f"차트를 그리는 중 오류가 발생했습니다: {e}")
                        st.markdown(data["collector"]) # 에러 나면 원본 텍스트라도 출력

                    # 1. 분석가의 리포트
                    st.subheader("📊 [Agent 2] 분석가 심층 리포트")
                    st.markdown(data["analysis"])

                    st.divider()

                    # 2. 포트폴리오 매니저의 최종 전략
                    st.subheader("💼 [Agent 3] 포트폴리오 매니저의 최종 전략")
                    strategy = data["strategy"]

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("투자의견", strategy.get("투자의견", "분석 불가"))
                    with col2:
                        st.metric("권장 포트폴리오 비중", strategy.get("권장 비중", "N/A"))

                    st.info(f"**결정 사유:** {strategy.get('결정 사유', '사유를 불러올 수 없습니다.')}")

                    if "💡 시기적 심리 변수 (주의사항)" in strategy:
                        st.warning(f"**주의사항:** {strategy.get('💡 시기적 심리 변수 (주의사항)')}")

                    st.divider()
                    st.subheader("🏛️ [Agent 4] 대안 자산·ETF 자문")
                    alt = data.get("alternative_advice")
                    if alt:
                        st.markdown(alt)
                    else:
                        st.caption("이번 응답에는 대안 자산 제안이 포함되지 않았습니다.")

                    # 간단한 히스토리 저장
                    st.session_state["history"].append(
                        {
                            "query": query,
                            "collector": data["collector"],
                            "analysis": data["analysis"],
                            "strategy": strategy,
                            "alternative_advice": data.get("alternative_advice"),
                        }
                    )
                else:
                    try:
                        error_detail = response.json().get("detail")
                    except Exception:
                        error_detail = None

                    if response.status_code == 422 and error_detail:
                        st.warning(f"데이터 부족으로 분석이 종료되었습니다: {error_detail}")
                    else:
                        st.error(f"분석 중 오류가 발생했습니다. (상태 코드: {response.status_code})")
            except Exception as e:
                st.error(f"백엔드 서버에 연결할 수 없습니다. FastAPI 서버가 켜져 있는지 확인해 주세요. 오류: {e}")
    else:
        st.warning("질문을 먼저 입력해 주세요!")

if st.session_state["history"]:
    st.divider()
    st.subheader("📜 최근 분석 기록")
    for item in reversed(st.session_state["history"][-5:]):
        with st.expander(item["query"]):
            st.markdown("**[Agent 1] 데이터 수집가**")
            st.markdown(item["collector"])
            st.markdown("---")
            st.markdown("**[Agent 2] 분석가 심층 리포트**")
            st.markdown(item["analysis"])
            st.markdown("---")
            st.markdown("**[Agent 3] 포트폴리오 매니저 전략**")
            st.markdown(item["strategy"])
            st.markdown("---")
            st.markdown("**[Agent 4] 대안 자산·ETF**")
            st.markdown(item.get("alternative_advice") or "(없음)")