from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from agent.state import AgentState
from agent.prompts import ANALYST_PROMPT, MANAGER_PROMPT
from rag.vector_store import get_retriever
from datetime import datetime
import yfinance as yf
import pandas as pd

# 모델 설정 (집에서 테스트할 때는 ChatOpenAI, 사내망에서는 AzureChatOpenAI로 추후 변경 가능)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# JSON 출력을 강제하기 위한 모델 (Manager 전용)
json_llm = llm.bind(response_format={"type": "json_object"})

TICKER_MAP = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "SK": "034730.KS",
    "한미반도체": "042700.KS",
    "카카오": "035720.KS",
    "한화솔루션": "009830.KS",
    "에코프로": "086520.KS",
    "LIG넥스원": "079550.KS",
    "네이버": "035420.KS",
    "한화에어로스페이스": "012450.KS",
    "애플": "AAPL",
    "엔비디아": "NVDA",
    "코카콜라": "KO",
    "월마트": "WMT",
    "아마존닷컴": "AMZN",
    "마이크로소프트": "MSFT",
    "메타": "META"
}

def fetch_stock_data(query: str) -> str:
    """사용자 질문에서 종목을 찾아 최근 1달 치 주가를 텍스트로 반환합니다."""
    stock_info = ""
    for name, ticker in TICKER_MAP.items():
        if name in query: # 질문에 종목명이 포함되어 있다면
            try:
                print(f"▶ [외부 API 연동] '{name}'의 최근 1개월 주가 데이터를 실시간으로 다운로드합니다...")
                
                # 💡 수정된 부분: download 대신 Ticker 객체의 history 메서드 사용 (구조가 훨씬 안정적임)
                ticker_obj = yf.Ticker(ticker)
                df = ticker_obj.history(period="1mo")
                
                if not df.empty:
                    stock_info += f"[출처: {name}_실시간_1개월_주가데이터(Yahoo_Finance)]\n"
                    
                    # iterrows()를 사용해 날짜(인덱스)와 해당 일자의 데이터(row)를 하나씩 꺼냅니다.
                    for date, row in df.iterrows():
                        # date를 문자열로 안전하게 변환 후 YYYY-MM-DD 포맷으로 맞춤
                        date_str = pd.to_datetime(str(date)).strftime("%Y-%m-%d")
                        
                        # 종가(Close)를 실수형(float)으로 깔끔하게 추출
                        price_val = float(row['Close'])
                        stock_info += f"- {date_str}: 종가 {price_val:.0f}\n"
                        
                    stock_info += "\n"
            except Exception as e:
                print(f"주가 다운로드 실패: {e}")
    return stock_info

def collector_node(state: AgentState) -> AgentState:
    """Agent 1: RAG를 이용해 문서를 검색합니다. + 주가 연동"""
    print("[Agent 1] 금융 정보 수집가")
    print("문서 및 실시간 데이터 수집 중...")
    # 1. 기존 RAG 검색
    retriever = get_retriever()
    docs = retriever.invoke(state["query"])
    context_list = []
    collected_sources = []
    for doc in docs:
        source_file = doc.metadata.get("source", "알 수 없는 파일")
        context_list.append(f"[출처: {source_file}]\n{doc.page_content}")
        if source_file not in collected_sources:
            collected_sources.append(source_file)
        
    # 2. 주가 API 데이터 추가 (질문에 종목이 언급된 경우에만)
    live_stock_data = fetch_stock_data(state["query"])
    if live_stock_data:
        context_list.append(live_stock_data)
        # 출처 첫 줄에서 실시간 주가 출처명 추출 (예: "[출처: SK하이닉스_실시간_1개월_주가데이터(Yahoo_Finance)]")
        first_line = live_stock_data.strip().split("\n")[0] if live_stock_data else ""
        if first_line.startswith("[출처:") and "]" in first_line:
            stock_source = first_line.replace("[출처:", "").split("]")[0].strip()
            collected_sources.append(stock_source)
        else:
            collected_sources.append("실시간 주가 데이터 (Yahoo Finance)")
        
    joined_context = "\n\n---\n\n".join(context_list)
    return {"context": joined_context, "collected_sources": collected_sources}

def analyst_node(state: AgentState) -> AgentState:
    """Agent 2: 검색된 문서를 바탕으로 심층 분석을 수행합니다."""
    print("[Agent 2] 투자 분석가")
    print("수집한 문서 데이터를 바탕으로 심층 분석 중...")
    today_date = datetime.now().strftime("%Y년 %m월 %d일")
    prompt = PromptTemplate.from_template(ANALYST_PROMPT)
    chain = prompt | llm
    response = chain.invoke({"context": state["context"], "query": state["query"], "current_date": today_date})
    return {"analysis": response.content}

def manager_node(state: AgentState) -> AgentState:
    """Agent 3: 분석 결과를 바탕으로 최종 투자 전략을 도출합니다."""
    print("[Agent 3] 포트폴리오 매니저")
    print("분석 결과를 바탕으로 최종 투자 전략 수립 중...")
    prompt = PromptTemplate.from_template(MANAGER_PROMPT)
    chain = prompt | json_llm
    response = chain.invoke({"analysis": state["analysis"]})
    return {"final_result": response.content}