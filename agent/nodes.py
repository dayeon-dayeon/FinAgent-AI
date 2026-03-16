import os
import re
from datetime import datetime, date
import functools

import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from langchain_core.prompts import PromptTemplate
#from langchain_openai import AzureChatOpenAI
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchResults

from agent.prompts import ANALYST_PROMPT, MANAGER_PROMPT
from agent.state import AgentState
from rag.vector_store import get_retriever

#aoai_api_key = os.getenv("AOAI_API_KEY")
#aoai_endpoint = os.getenv("AOAI_ENDPOINT")
#aoai_deployment = os.getenv("AOAI_DEPLOY_GPT4O_MINI")
#aoai_api_version = "2024-02-15-preview"
#
#llm = AzureChatOpenAI(
#    api_key=aoai_api_key,
#    azure_endpoint=aoai_endpoint,
#    azure_deployment=aoai_deployment,
#    api_version=aoai_api_version,
#    temperature=0,
#)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)

json_llm = llm.bind(response_format={"type": "json_object"})

@functools.lru_cache(maxsize=1)
def get_stock_mapping():
    """KRX(한국거래소) 전 종목을 불러와 yfinance용 티커(.KS, .KQ)로 변환합니다."""
    print("▶ [초기화] 한국거래소(KRX) 전 종목 데이터를 불러옵니다...")
    mapping = {}
    try:
        # 코스피, 코스닥 전 종목 목록 가져오기
        df_krx = fdr.StockListing('KRX')
        for _, row in df_krx.iterrows():
            code = row['Code']
            name = row['Name']
            market = row['Market']
            
            # yfinance 형식에 맞게 코스피는 .KS, 코스닥은 .KQ 꼬리표 달기
            if market == 'KOSPI':
                mapping[name] = f"{code}.KS"
            elif market == 'KOSDAQ':
                mapping[name] = f"{code}.KQ"
            else:
                mapping[name] = f"{code}.KS"
    except Exception as e:
        print(f"KRX 로딩 실패: {e}")

    # 미국 주요 기업은 자주 묻는 종목 위주로 딕셔너리에 추가
    us_stocks = {
            "애플": "AAPL", "엔비디아": "NVDA", "테슬라": "TSLA","마이크로소프트": "MSFT", "아마존": "AMZN", "구글": "GOOGL", 
            "메타": "META", "넷플릭스": "NFLX", "AMD": "AMD", "브로드컴": "AVGO", "일라이릴리": "LLY", "TSMC": "TSM",
            "월마트": "WMT", "코카콜라": "KO", "퀄컴": "QCOM","인텔": "INTC", "보잉": "BA", "디즈니": "DIS", "스타벅스": "SBUX",
            "팔란티어테크": "PLTR", "오라클": "ORCL","아이온큐": "IONQ", "어플라이드머티어리얼즈": "AMAT","슈퍼마이크로컴퓨터": "SMCI"
        }
    mapping.update(us_stocks)
    return mapping

def _detect_tickers(query: str):
    """질문에서 종목명을 찾아 티커를 반환합니다."""
    mapping = get_stock_mapping()
    found_tickers = {}
    
    sorted_names = sorted(mapping.keys(), key=len, reverse=True)

    search_query = query
    for name in sorted_names:
        if len(name) > 1 and name in search_query:
            found_tickers[name] = mapping[name]
            search_query = search_query.replace(name, "")
            
            if len(found_tickers) >= 3:
                break

    return found_tickers

def fetch_stock_data(query: str) -> str:
    """사용자 질문에서 종목을 찾아 최근 1달 치 주가를 텍스트로 반환합니다."""
    stock_info = ""
    found_tickers = _detect_tickers(query)

    for name, ticker in found_tickers.items():
        try:
            print(f"▶ [외부 API 연동] '{name}'의 최근 1개월 주가 데이터를 실시간으로 다운로드합니다...")
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="1mo")
            
            if not df.empty:
                stock_info += f"[출처: {name}_실시간_1개월_주가데이터(Yahoo_Finance)]\n"
                for idx, row in df.iterrows():
                    date_str = pd.to_datetime(str(idx)).strftime("%Y-%m-%d")
                    price_val = float(row['Close'])
                    stock_info += f"- {date_str}: 종가 {price_val:.0f}\n"
                stock_info += "\n"
        except Exception as e:
            print(f"주가 다운로드 실패 ({name}): {e}")

    return stock_info

def fetch_web_search(query: str) -> str:
    """질문을 기반으로 DuckDuckGo 실시간 웹 검색을 수행합니다."""
    try:
        print("▶ [외부 API 연동] 실시간 웹 검색(DuckDuckGo)을 수행합니다...")
        search = DuckDuckGoSearchResults(num_results=3)
        result = search.invoke(query)
        if result:
            return f"[출처: 실시간 웹 검색(DuckDuckGo)]\n{result}\n"
    except Exception as e:
        print(f"웹 검색 실패: {e}")
    return ""

def _parse_date_from_source(source: str) -> date | None:
    basename = os.path.basename(source)
    match = re.search(r"(\d{8}|\d{6})", basename)
    if not match:
        return None

    digits = match.group(1)
    fmt = "%Y%m%d" if len(digits) == 8 else "%y%m%d"
    try:
        return datetime.strptime(digits, fmt).date()
    except Exception:
        return None

def collector_node(state: AgentState) -> AgentState:
    print("[Agent 1] 금융 정보 수집가")
    print("문서, 실시간 데이터 및 최신 웹 뉴스를 수집 중...")

    context_list: list[str] = []
    collected_sources: list[str] = []

    detected_tickers = _detect_tickers(state["query"])
    ticker_detected = bool(detected_tickers)

    rag_hit = False

    try:
        retriever = get_retriever()
        docs = retriever.invoke(state["query"])
        if docs:
            rag_hit = True

            scored_docs = []
            for doc in docs:
                source_file = doc.metadata.get("source", "알 수 없는 파일")
                doc_date = _parse_date_from_source(source_file)
                content = doc.page_content.strip()
                
                ticker_score = 0
                if detected_tickers:
                    for name in detected_tickers.keys():
                        if name in content or name in source_file:
                            ticker_score += 1
                    if ticker_score == 0:
                        continue 

                scored_docs.append((ticker_score, doc_date, source_file, doc, content))

            def sort_key(item):
                t_score, d_date, _, _, _ = item
                return (t_score, d_date is not None, d_date or date.min)

            scored_docs.sort(key=sort_key, reverse=True)

            seen_contents = set()
            for _, _, source_file, doc, content in scored_docs:
                if not content or content in seen_contents:
                    continue
                seen_contents.add(content)

                context_list.append(f"[출처: {source_file}]\n{content}")
                if source_file not in collected_sources:
                    collected_sources.append(source_file)
    except Exception as e:
        print(f"RAG 검색 중 오류 발생: {e}")

    live_stock_data = fetch_stock_data(state["query"])
    if live_stock_data:
        context_list.append(live_stock_data)
        collected_sources.append("실시간 주가 데이터 (Yahoo Finance)")

    web_search_data = fetch_web_search(state["query"])
    if web_search_data:
        context_list.append(web_search_data)
        collected_sources.append("실시간 웹 검색 (DuckDuckGo)")

    if not context_list:
        return {
            "context": "데이터 없음",
            "collected_sources": [],
            "ticker": None,
            "ticker_detected": ticker_detected,
            "rag_hit": rag_hit,
            "error": "관련 데이터를 찾을 수 없어 분석을 종료합니다.",
        }

    joined_context = "\n\n---\n\n".join(context_list)
    first_ticker = next(iter(detected_tickers.keys()), None) if detected_tickers else None

    return {
        "context": joined_context,
        "collected_sources": collected_sources,
        "ticker": first_ticker,
        "ticker_detected": ticker_detected,
        "rag_hit": rag_hit,
    }

def analyst_node(state: AgentState) -> AgentState:
    print("[Agent 2] 투자 분석가")
    print("수집한 문서 데이터를 바탕으로 심층 분석 중...")
    today_date = datetime.now().strftime("%Y년 %m월 %d일")
    prompt = PromptTemplate.from_template(ANALYST_PROMPT)
    chain = prompt | llm
    response = chain.invoke(
        {
            "context": state["context"],
            "query": state["query"],
            "current_date": today_date,
            "ticker_detected": str(state.get("ticker_detected", False)),
            "rag_hit": str(state.get("rag_hit", False)),
        }
    )
    return {"analysis": response.content}

def manager_node(state: AgentState) -> AgentState:
    print("[Agent 3] 포트폴리오 매니저")
    print("분석 결과를 바탕으로 최종 투자 전략 수립 중...")
    prompt = PromptTemplate.from_template(MANAGER_PROMPT)
    chain = prompt | json_llm
    response = chain.invoke({"analysis": state["analysis"]})
    return {"final_result": response.content}