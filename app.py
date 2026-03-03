import streamlit as st
import requests

# 페이지 기본 설정
st.set_page_config(page_title="FinAgent-AI", page_icon="📈", layout="wide")

st.title("📈 AI 주가 분석 & 포트폴리오 에이전트 📈")
st.markdown("관심 있는 기업이나 최근 경제 이슈에 대해 질문해 보세요. 3명의 AI 에이전트가 데이터를 분석하여 투자 전략을 제시합니다.")

# 사용자 입력 창
query = st.text_input("질문을 입력해주세요 (ex : 최근 삼성전자 D램 이슈와 주가 전망 알려줘)")

# 분석 버튼
if st.button("분석 시작"):
    if query:
        # 진행 상태 표시기 (스피너)
        with st.spinner("AI 에이전트(수집가, 분석가, 매니저)들이 열심히 분석 중입니다... 🤖"):
            try:
                # FastAPI 백엔드 서버로 요청 보내기
                response = requests.post("http://localhost:8000/analyze", json={"query": query})
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 1. 수석 분석가의 리포트 출력
                    st.subheader("📊 [Agent 2] 수석 분석가 심층 리포트")
                    st.markdown(data["analysis"])
                    
                    st.divider() # 구분선
                    
                    # 2. 포트폴리오 매니저의 최종 전략 출력 (Structured Output 활용)
                    st.subheader("💼 [Agent 3] 포트폴리오 매니저의 최종 전략")
                    strategy = data["strategy"]
                    
                    # 화면을 2개의 열로 나누어 수치형 데이터 표시
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("투자의견", strategy.get("investment_opinion", "분석 불가"))
                    with col2:
                        st.metric("권장 포트폴리오 비중", strategy.get("portfolio_weight", "N/A"))
                    
                    st.info(f"**결정 사유:** {strategy.get('reason', 'N/A')}")
                    
                else:
                    st.error(f"분석 중 오류가 발생했습니다. (상태 코드: {response.status_code})")
            except Exception as e:
                st.error(f"백엔드 서버에 연결할 수 없습니다. FastAPI 서버가 켜져 있는지 확인해 주세요. 오류: {e}")
    else:
        st.warning("질문을 먼저 입력해 주세요!")