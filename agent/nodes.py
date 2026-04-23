import os
import re
from datetime import datetime, date, timedelta
import functools
from typing import Any
from zoneinfo import ZoneInfo
import json
from pathlib import Path

import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from langchain_core.prompts import PromptTemplate
#from langchain_openai import AzureChatOpenAI
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchResults

from agent.prompts import ALTERNATIVE_ADVISOR_PROMPT, ANALYST_PROMPT, MANAGER_PROMPT
from agent.state import AgentState
from rag.vector_store import get_retriever

KST = ZoneInfo("Asia/Seoul")
_MAX_NEWS_INJECT_CHARS = 120_000

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


def _cache_dir() -> Path:
    base = Path(os.getenv("DATA_PATH", "./data"))
    return base / ".cache"


def _krx_ticker_cache_path() -> Path:
    return _cache_dir() / "krx_tickers.json"


def _load_krx_ticker_cache(max_age_hours: int = 24) -> dict[str, str] | None:
    path = _krx_ticker_cache_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(raw["saved_at"])
        if datetime.now(KST) - saved_at.replace(tzinfo=KST) > timedelta(hours=max_age_hours):
            return None
        mapping = raw.get("mapping") or {}
        if isinstance(mapping, dict) and mapping:
            return {str(k): str(v) for k, v in mapping.items()}
    except Exception:
        return None
    return None


def _save_krx_ticker_cache(mapping: dict[str, str]) -> None:
    try:
        path = _krx_ticker_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"saved_at": datetime.now(KST).isoformat(), "count": len(mapping), "mapping": mapping},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


@functools.lru_cache(maxsize=1)
def get_stock_mapping():
    """KRX(한국거래소) 전 종목을 불러와 yfinance용 티커(.KS, .KQ)로 변환합니다."""
    print("▶ [초기화] 한국거래소(KRX) 전 종목 데이터를 불러옵니다...")
    cached = _load_krx_ticker_cache()
    if cached:
        mapping = dict(cached)
    else:
        mapping: dict[str, str] = {}
    try:
        if not mapping:
            # KRX 전체가 실패/지연하는 환경이 있어 KOSPI/KOSDAQ로 fallback
            try:
                df_krx = fdr.StockListing("KRX")
                frames = [df_krx]
            except Exception:
                frames = [fdr.StockListing("KOSPI"), fdr.StockListing("KOSDAQ")]

            for df in frames:
                for _, row in df.iterrows():
                    code = str(row.get("Code", "")).strip()
                    name = str(row.get("Name", "")).strip()
                    market = str(row.get("Market", "")).strip().upper()
                    if not code or not name:
                        continue
                    if market == "KOSDAQ":
                        mapping[name] = f"{code}.KQ"
                    else:
                        mapping[name] = f"{code}.KS"

            if mapping:
                _save_krx_ticker_cache(mapping)
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


def _norm_name(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", (s or "").strip()).lower()


def _detect_tickers(query: str) -> dict[str, str]:
    """질문에서 종목명(한글) 또는 미국식 티커(영문 대문자)를 찾아 Yahoo Finance 심볼로 매핑합니다. 동일 티커는 한 번만."""
    mapping = get_stock_mapping()
    found_tickers: dict[str, str] = {}
    used_symbols: set[str] = set()

    q_norm = _norm_name(query)
    sorted_names = sorted(mapping.keys(), key=len, reverse=True)
    search_query = query
    for name in sorted_names:
        if len(name) > 1 and (name in search_query or _norm_name(name) in q_norm):
            sym = mapping[name]
            if sym not in used_symbols:
                found_tickers[name] = sym
                used_symbols.add(sym)
            search_query = search_query.replace(name, "")
            if len(found_tickers) >= 5:
                return found_tickers

    q_upper = query.upper()
    for name, ticker in mapping.items():
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z]{1,5}", ticker):
            continue
        if ticker in used_symbols:
            continue
        if re.search(rf"\b{re.escape(ticker)}\b", q_upper):
            found_tickers[name] = ticker
            used_symbols.add(ticker)
        if len(found_tickers) >= 5:
            break

    return found_tickers


def _query_tokens(query: str) -> list[str]:
    """질문에서 길이 2 이상 토큰만 추출(한글·영문·숫자 혼합 단어)."""
    return [t for t in re.findall(r"[\w가-힣]{2,}", query) if len(t) >= 2]


def _text_matches_query_or_tickers(
    text: str,
    query: str,
    detected_tickers: dict[str, str],
) -> bool:
    """질문 키워드 또는 감지된 종목명/티커가 본문에 드러나는지 검사합니다."""
    if not text.strip():
        return False
    for name in detected_tickers.keys():
        if name in text:
            return True
    for sym in detected_tickers.values():
        if isinstance(sym, str) and re.fullmatch(r"[A-Z]{1,5}", sym):
            if re.search(rf"\b{re.escape(sym)}\b", text.upper()):
                return True
    tokens = _query_tokens(query)
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in text)
    return hits >= max(1, min(2, len(tokens) // 3 + 1))


def _filter_daily_news_by_query(ntext: str, query: str, detected_tickers: dict[str, str]) -> str:
    """일일 뉴스 파일에서 질문과 무관한 `[n] ...` 기사 블록을 제거합니다."""
    parts = re.split(r"\n(?=\[\d+\]\s)", ntext)
    if len(parts) <= 1:
        return ntext if _text_matches_query_or_tickers(ntext, query, detected_tickers) else ""
    header = parts[0].rstrip()
    kept_blocks: list[str] = []
    for block in parts[1:]:
        if _text_matches_query_or_tickers(block, query, detected_tickers):
            kept_blocks.append(block)
    if not kept_blocks:
        return ""
    return header + "\n\n" + "\n\n".join(kept_blocks)


def _is_stock_specific_query(query: str) -> bool:
    """
    질문이 '특정 종목/매매/주가'처럼 티커가 반드시 필요한 유형인지 판별합니다.
    거시/시황/정책 질문처럼 종목이 없어도 답할 수 있는 유형은 False.
    """
    q = (query or "").strip()
    if not q:
        return False
    stock_intent_keywords = (
        "주가",
        "종가",
        "차트",
        "티커",
        "종목",
        "매수",
        "매도",
        "비중",
        "목표가",
        "전망",
        "실적",
        "per",
        "pbr",
        "eps",
        "배당",
    )
    q_lower = q.lower()
    return any(k in q for k in stock_intent_keywords) or any(k in q_lower for k in ("per", "pbr", "eps"))


def fetch_stock_data(query: str) -> tuple[str, list[dict[str, Any]]]:
    """질문에서 종목을 찾아 Yahoo Finance 주가 텍스트와 차트용 행 목록을 반환합니다."""
    stock_info = ""
    chart_rows: list[dict[str, Any]] = []
    found_tickers = _detect_tickers(query)
    period = (os.getenv("STOCK_CHART_PERIOD") or "1mo").strip() or "1mo"

    for name, ticker in found_tickers.items():
        try:
            print(f"▶ [외부 API 연동] '{name}'의 최근 주가 데이터(period={period})를 다운로드합니다...")
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period=period)

            if not df.empty:
                stock_info += (
                    f"[출처: {name}_실시간_주가데이터(Yahoo_Finance) 기간={period} 분석기준일={datetime.now().strftime('%Y-%m-%d')}]\n"
                )
                for idx, row in df.iterrows():
                    date_str = pd.to_datetime(str(idx)).strftime("%Y-%m-%d")
                    price_val = float(row["Close"])
                    stock_info += f"- {date_str}: 종가 {price_val:.0f}\n"
                    chart_rows.append({"날짜": date_str, "종목": name, "종가": int(round(price_val))})
                stock_info += "\n"
        except Exception as e:
            print(f"주가 다운로드 실패 ({name}): {e}")

    return stock_info, chart_rows

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

def _data_dir() -> str:
    return os.path.normpath(os.getenv("DATA_PATH", "./data"))


def _read_todays_news_file() -> tuple[str, str] | None:
    """KST 기준 오늘 날짜의 data/news_YYYYMMDD.txt 가 있으면 (절대경로, 본문) 반환."""
    tag = datetime.now(KST).strftime("%Y%m%d")
    path = os.path.join(_data_dir(), f"news_{tag}.txt")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(f"일일 뉴스 파일 읽기 실패 ({path}): {e}")
        return None
    ap = os.path.abspath(path)
    if len(text) > _MAX_NEWS_INJECT_CHARS:
        text = text[:_MAX_NEWS_INJECT_CHARS] + "\n...(이하 생략)"
    return (ap, text.strip())


def _read_monday_weekend_news_file() -> tuple[str, str] | None:
    """KST 월요일이면 data/news_weekend_YYYYMMDD.txt(그 월요일 날짜 태그)가 있으면 (절대경로, 본문) 반환."""
    now = datetime.now(KST)
    if now.weekday() != 0:
        return None
    tag = now.strftime("%Y%m%d")
    path = os.path.join(_data_dir(), f"news_weekend_{tag}.txt")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(f"주말 뉴스 파일 읽기 실패 ({path}): {e}")
        return None
    if not text.strip():
        return None
    ap = os.path.abspath(path)
    if len(text) > _MAX_NEWS_INJECT_CHARS:
        text = text[:_MAX_NEWS_INJECT_CHARS] + "\n...(이하 생략)"
    return (ap, text.strip())


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
    print("주가·오늘자 뉴스 파일 또는 문서 검색·웹을 조합해 수집합니다...")

    q = state["query"]
    context_list: list[str] = []
    collected_sources: list[str] = []
    summary_lines: list[str] = []

    detected_tickers = _detect_tickers(q)
    ticker_detected = bool(detected_tickers)
    stock_specific = _is_stock_specific_query(q)
    detected_companies = list(detected_tickers.keys())

    rag_hit = False
    rag_kept = 0
    stock_chart: list[dict[str, Any]] = []

    # 1) 질문에 나온 종목 주가를 최우선으로 수집·배치 (가격·기간은 헤더에 명시됨)
    live_stock_data, stock_chart = fetch_stock_data(q)
    if live_stock_data:
        context_list.append(live_stock_data)
        collected_sources.append("실시간 주가 데이터 (Yahoo Finance)")
        names = sorted({r["종목"] for r in stock_chart})
        if names:
            summary_lines.append(f"- **주가 수집**: {', '.join(names)} (Yahoo Finance)")

    today_news_basename: str | None = None
    weekend_news_basename: str | None = None
    use_todays_news_file_only = False
    injected = _read_todays_news_file()
    if injected:
        npath, ntext = injected
        today_news_basename = os.path.basename(npath)
        if ntext.strip():
            filtered_news = _filter_daily_news_by_query(ntext, q, detected_tickers)
            news_body = filtered_news.strip() if filtered_news.strip() else ntext.strip()
            print(f"▶ [일일 뉴스] {today_news_basename} — 본 분석의 뉴스 근거로 사용 (RAG·웹 검색 생략)")
            context_list.append(f"[출처: {npath}]\n{news_body}")
            collected_sources.append(npath)
            summary_lines.append(
                f"- **일일 뉴스**: `{today_news_basename}`"
            )
            use_todays_news_file_only = True

    weekend_injected = _read_monday_weekend_news_file()
    if weekend_injected:
        wpath, wtext = weekend_injected
        weekend_news_basename = os.path.basename(wpath)
        filtered_w = _filter_daily_news_by_query(wtext, q, detected_tickers)
        wbody = filtered_w.strip() if filtered_w.strip() else wtext.strip()
        print(f"▶ [직전 주말 뉴스] {weekend_news_basename} — 토·일(KST) 키워드 뉴스를 근거에 추가")
        context_list.append(f"[출처: {wpath}]\n{wbody}")
        collected_sources.append(wpath)
        summary_lines.append(f"- **직전 주말 뉴스**: `{weekend_news_basename}`")

    if not use_todays_news_file_only:
        try:
            retriever = get_retriever()
            docs = retriever.invoke(q)
            if docs:
                rag_hit = True

                scored_docs = []
                for doc in docs:
                    source_file = doc.metadata.get("source", "알 수 없는 파일")
                    bname = os.path.basename(source_file)
                    if today_news_basename and bname == today_news_basename:
                        continue
                    if weekend_news_basename and bname == weekend_news_basename:
                        continue

                    doc_date = _parse_date_from_source(source_file)
                    content = doc.page_content.strip()
                    is_daily_news_doc = doc.metadata.get("doc_type") == "news" or bname.lower().startswith(
                        "news_"
                    )

                    ticker_score = 0
                    if detected_tickers:
                        for name in detected_tickers.keys():
                            if name in content or name in source_file:
                                ticker_score += 1

                    if ticker_score == 0:
                        if is_daily_news_doc:
                            if not _text_matches_query_or_tickers(content, q, detected_tickers):
                                continue
                        else:
                            if not _text_matches_query_or_tickers(content, q, detected_tickers):
                                continue

                    scored_docs.append((ticker_score, doc_date, source_file, doc, content))

                def sort_key(item):
                    t_score, d_date, _, _, _ = item
                    return (t_score, d_date is not None, d_date or date.min)

                scored_docs.sort(key=sort_key, reverse=True)

                scored_docs.sort(
                    key=lambda it: (
                        -it[0],
                        it[1] is None,
                        it[1] or date.max,
                    )
                )

                seen_contents = set()
                for _, _, source_file, doc, content in scored_docs:
                    if not content or content in seen_contents:
                        continue
                    seen_contents.add(content)

                    context_list.append(f"[출처: {source_file}]\n{content}")
                    rag_kept += 1
                    if source_file not in collected_sources:
                        collected_sources.append(source_file)
        except Exception as e:
            print(f"RAG 검색 중 오류 발생: {e}")

    web_search_data = ""
    if not use_todays_news_file_only:
        web_search_data = fetch_web_search(q)
    if web_search_data:
        body = web_search_data
        if web_search_data.startswith("[출처:"):
            nl = web_search_data.find("\n")
            body = web_search_data[nl + 1 :] if nl != -1 else ""
        if _text_matches_query_or_tickers(body, q, detected_tickers):
            context_list.append(web_search_data)
            collected_sources.append("실시간 웹 검색 (DuckDuckGo)")
            summary_lines.append("- **웹 검색**: 질문과 연관된 스니펫만 분석에 사용")
        else:
            print("▶ [웹 검색] 질문과의 연관성이 낮아 결과를 생략합니다.")

    if rag_kept:
        summary_lines.append(f"- **문서 검색(RAG)**: 연관 청크 {rag_kept}건")

    if not context_list:
        return {
            "context": "데이터 없음",
            "collector_display": "수집된 근거가 없습니다.",
            "stock_chart": [],
            "collected_sources": [],
            "ticker": None,
            "ticker_detected": ticker_detected,
            "rag_hit": rag_hit,
            "error": "관련 데이터를 찾을 수 없어 분석을 종료합니다.",
        }

    joined_context = "\n\n---\n\n".join(context_list)
    first_ticker = next(iter(detected_tickers.keys()), None) if detected_tickers else None

    display_md = "## 수집 요약\n" + "\n".join(summary_lines) if summary_lines else "## 수집 요약\n- (표시할 항목 없음)"

    return {
        "context": joined_context,
        "collector_display": display_md,
        "stock_chart": stock_chart,
        "stock_specific": stock_specific,
        "detected_companies": detected_companies,
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
            "stock_specific": str(state.get("stock_specific", False)),
            "detected_companies": ", ".join(state.get("detected_companies") or []),
        }
    )
    return {"analysis": response.content}

def manager_node(state: AgentState) -> AgentState:
    print("[Agent 3] 포트폴리오 매니저")
    print("수집 컨텍스트(뉴스 등)와 분석가 리포트를 대조해 최종 투자 전략 수립 중...")
    today_date = datetime.now().strftime("%Y년 %m월 %d일")
    prompt = PromptTemplate.from_template(MANAGER_PROMPT)
    chain = prompt | json_llm
    ctx = state.get("context") or ""
    # 토큰 과다 방지: 매니저는 요약 판단용이므로 상한(대략 24k자)만 둠
    if len(ctx) > 24000:
        ctx = ctx[:23900] + "\n\n[… 이하 원문 컨텍스트 생략 …]"
    response = chain.invoke(
        {
            "analysis": state["analysis"],
            "context": ctx,
            "current_date": today_date,
            "detected_companies": ", ".join(state.get("detected_companies") or []),
        }
    )
    return {"final_result": response.content}


def alternative_advisor_node(state: AgentState) -> AgentState:
    """뉴스·맥락을 바탕으로 ETF·리츠·금 등 개별 주식 외 대안을 제안합니다(매니저와 독립 역할)."""
    print("[Agent 4] 대안 자산·ETF 자문가")
    today_date = datetime.now().strftime("%Y년 %m월 %d일")
    ctx = state.get("context") or ""
    if len(ctx) > 14000:
        ctx = ctx[:13900] + "\n\n[… 이하 컨텍스트 생략 …]"

    mgr = state.get("final_result", "{}")
    if isinstance(mgr, dict):
        mgr_text = json.dumps(mgr, ensure_ascii=False)
    else:
        mgr_text = str(mgr)

    prompt = PromptTemplate.from_template(ALTERNATIVE_ADVISOR_PROMPT)
    chain = prompt | llm
    response = chain.invoke(
        {
            "query": state["query"],
            "context": ctx,
            "analysis": state.get("analysis") or "",
            "manager_output": mgr_text,
            "current_date": today_date,
        }
    )
    return {"alternative_advice": response.content}