import os
import re          
import pandas as pd
import altair as alt
import requests
import streamlit as st

st.set_page_config(page_title="FinAgent-AI", page_icon="📈", layout="wide")

st.title("📈 AI 주가 분석 & 포트폴리오 에이전트 📈")
st.markdown("3명의 AI 에이전트가 데이터를 분석하여 투자 전략을 제시합니다.")

# 환경 변수 / secrets 기반 백엔드 URL 설정
default_backend = "http://localhost:8000/analyze"
backend_from_env = os.getenv("BACKEND_URL")

# secrets.toml 이 없을 수 있으므로, 접근 자체를 try/except로 감쌉니다.
try:
    backend_from_secrets = st.secrets.get("BACKEND_URL")
except Exception:
    backend_from_secrets = None

BACKEND_URL = backend_from_secrets or backend_from_env or default_backend

if "history" not in st.session_state:
    st.session_state["history"] = []

query = st.text_input(
    "관심 있는 기업이나 최근 경제 이슈에 대해 질문해 보세요. (ex :  최근 삼성전자 D램 이슈와 주가 전망 알려줘 / SK하이닉스의 1개월치 주가 데이터와 최근 이슈 분석해)"
)

if st.button("분석 시작"):
    if query:
        with st.spinner("AI 에이전트(수집가, 분석가, 매니저)들이 열심히 분석 중입니다... 🤖"):
            try:
                response = requests.post(BACKEND_URL, json={"query": query})

                if response.status_code == 200:
                    data = response.json()

                    st.subheader("🔍 [Agent 1] 데이터 수집가")
                    try:
                        collector_text = data.get("collector", "")
                        lines = collector_text.split('\n')
                        
                        chart_data = []
                        filtered_lines = []
                        current_stock = "주가"
                        is_stock_data = False

                        for line in lines:
                            # 1. 종목명 텍스트 숨기기
                            name_match = re.search(r'\[출처:\s*(.*?)_실시간', line)
                            if name_match:
                                current_stock = name_match.group(1)
                                is_stock_data = True
                                continue 
                            
                            # 2. 주가 데이터 텍스트 숨기고 차트용 데이터로만 빼내기
                            price_match = re.search(r'- (\d{4}-\d{2}-\d{2}): 종가 (\d+)', line)
                            if price_match:
                                date_str = price_match.group(1)
                                price = int(price_match.group(2))
                                chart_data.append({"날짜": date_str, "종목": current_stock, "종가": price})
                                continue 
                            
                            # 3. 주가 데이터가 끝난 직후의 쓸데없는 빈 줄 숨기기
                            if is_stock_data and line.strip() == "":
                                is_stock_data = False
                                continue
                            
                            # 위 조건에 안 걸린 텍스트(뉴스, RAG 문서 등)만 화면에 남기기
                            filtered_lines.append(line)
                            is_stock_data = False

                        # 필터링된 진짜 텍스트(뉴스 등)만 먼저 예쁘게 출력
                        st.markdown('\n'.join(filtered_lines))
                        
                        # 주가 데이터가 존재하면 동적 스케일이 적용된 그래프 출력
                        if chart_data:
                            df_chart = pd.DataFrame(chart_data)
                            
                            # Y축이 0부터 시작하지 않도록 (zero=False) 고급 차트 설정
                            chart = alt.Chart(df_chart).mark_line(point=True).encode(
                                x=alt.X('날짜:T', title='날짜'),
                                y=alt.Y('종가:Q', title='종가', scale=alt.Scale(zero=False)),
                                color=alt.Color('종목:N', title='종목'),
                                tooltip=['날짜:T', '종목:N', '종가:Q'] # 마우스 올리면 상세 정보 표시
                            ).properties(
                                title="📈 실시간 1개월 주가 추이",
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

                    # 간단한 히스토리 저장
                    st.session_state["history"].append(
                        {
                            "query": query,
                            "collector": data["collector"],
                            "analysis": data["analysis"],
                            "strategy": strategy,
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