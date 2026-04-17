# 📈 FinAgent-AI

## 1. 프로젝트 개요

**문제 정의** :
코스피 지수가 6000을 돌파하면서 전례 없는 시장의 변화에 많은 투자자들이 관심을 가짐.
미국-이스라엘과 이란 간의 무력 충돌 등 과 같은 글로벌 이슈가 주가에 영향을 미치며 투자자들의 불안감과 군중 심리를 유발하며, 주가 급등락을 초래.
급증하는 상황에서는 단순한 지표 분석을 넘어, 투자자들의 심리와 행동 양식, 사회적 이슈까지 고려하는 입체적인 분석이 필요함.
개인이 매일 쏟아지는 방대한 데이터(기업 공시, 증권사 리포트, 뉴스 등)를 직접 분석하기 어려움.

## 2. 요구사항 및 주요 기능

**챗봇 기능에 RAG와 LangGraph 기반 Multi-Agent 구조를 결합해 실제 업무 및 서비스 환경에서도 활용 가능한 수준의 AI Agent 구현**

- Multi-Agent 시스템 : LangGraph를 활용해 역할이 다른 3개의 에이전트(수집가, 분석가, 매니저)가 협업하여 문제를 해결하는 구조(A2A).
- RAG 기반 지식 결합: FAISS를 이용한 Vector DB를 구축하여, 외부 금융 텍스트(리포트, 뉴스) 자료로 에이전트 지식을 보강.
- 고품질 Prompt : 역할 기반 프롬프트(Role-playing)와 Chain of Thought(CoT)를 적용하여 논리적이고 일관된 응답.
- 결과물 구조화 : 최종 투자 전략을 정형화된 데이터 형식으로 응답.
- 완결성 있는 서비스 패키징: FastAPI(백엔드)와 Streamlit(프론트엔드)을 활용하여 실제 사용 가능한 형태의 서비스.
  => RAG 기반 뉴스 검색과 Yahoo Finance 연동 종목별 주가(기간은 환경 변수로 설정) 자동 수집. 데이터를 분석 후 추천까지 3단계로 Multi-Agent가 관리.

## 3. 시스템 아키텍처

## 4. 기술 스택

## 5. 프로젝트 구조

## 실행 방법

아래 순서는 **처음 세팅** 기준입니다. 이미 가상환경과 패키지가 있으면 3번(환경 변수)부터 진행하면 됩니다.

### 1. 가상환경 생성 및 활성화

```bash
python -m venv venv
```

- **Windows:** `venv\Scripts\activate`
- **macOS / Linux:** `source venv/bin/activate`  
  (프롬프트 앞에 `(venv)`가 보이면 활성화된 상태입니다.)

### 2. 필수 패키지 설치

```bash
pip install -r requirements.txt
```

`requirements.txt`에 없는 모듈 오류가 나면 메시지에 맞춰 추가 설치하면 됩니다. (예: `langchain-community`, `langchain-text-splitters`는 보통 위 파일에 포함됩니다.)

### 3. 환경 변수 (`.env`)

프로젝트 **루트**에 `.env` 파일을 두고, 최소한 아래를 설정합니다.

| 변수                   | 필수 | 설명                                                                   |
| ---------------------- | ---- | ---------------------------------------------------------------------- |
| `OPENAI_API_KEY`       | 권장 | LLM·임베딩·뉴스 요약(`rag/economic_news.py`)에 사용                    |
| `STOCK_CHART_PERIOD`   | 선택 | Yahoo Finance 주가 조회 기간. 예: `1mo`(기본), `3mo`, `6mo`, `1y`      |
| `NEWS_INCLUDE_LISTING` | 선택 | `0`이면 뉴스 키워드에서 코스피·코스닥·나스닥 종목명 매칭 제외          |
| `BACKEND_URL`          | 선택 | Streamlit이 호출할 API 주소. 미설정 시 `http://localhost:8000/analyze` |
| `DATA_PATH`            | 선택 | 데이터·캐시 기본 폴더. 미설정 시 `data`                                |
| `NEWS_SUMMARY_MODEL`   | 선택 | 뉴스 요약용 OpenAI 모델. 기본 `gpt-4o-mini`                            |

예시:

```env
OPENAI_API_KEY=sk-...
STOCK_CHART_PERIOD=3mo
```

### 4. (선택) 오늘의 경제·증시 뉴스 수집

`data/news_YYYYMMDD.txt` 형태로 저장되며, RAG에 넣을 `.txt` 자료로 쓸 수 있습니다. (요약은 API 키가 있을 때 400~500자 생성.)

```bash
python -m rag.economic_news
```

자주 쓰는 옵션:

- `--max-articles 10` — 저장할 기사 수 (기본 10)
- `--no-llm-summary` — OpenAI 없이 RSS만 묶기
- `--no-listing-keywords` — 종목명 키워드 확장 없이 고정 키워드만 사용

상장 종목명 캐시만 갱신할 때:

```bash
python -m rag.stock_universe
```

### 5. Vector DB (FAISS) 초기화

`data/` 아래 분석에 쓸 `.txt` / `.pdf` / `.csv`를 두고, 내용이 바뀌었거나 처음이면 인덱스를 다시 만듭니다.

```bash
python rag/vector_store.py
```

### 6. 서비스 실행

백엔드(FastAPI)와 프론트(Streamlit)를 **동시에** 띄워야 합니다.

**방법 A — 터미널 두 개**

터미널 1 (API):

```bash
uvicorn main:app --reload --port 8000
```

터미널 2 (UI):

```bash
streamlit run app.py
```

브라우저에서 Streamlit 주소(보통 `http://localhost:8501`)로 접속합니다. API만 확인할 때는 `http://localhost:8000/health` 로 헬스 체크가 가능합니다.

**방법 B — 한 번에 실행 (Windows 등)**

```bash
python run.py
```

백엔드와 Streamlit을 같이 띄우고 브라우저를 엽니다. 종료는 해당 터미널에서 `Ctrl+C`입니다.

### 7. 동작 요약

1. **수집가** — RAG(`data/` 기반 FAISS), 질문에 맞는 **최근 주가**(Yahoo), **웹 검색**(DuckDuckGo)을 모읍니다.
2. **분석가** — 위 컨텍스트만으로 리포트를 작성합니다.
3. **매니저** — 원문 컨텍스트와 리포트를 대조해 JSON 형태의 투자 의견을 냅니다.

주가 기간·뉴스 범위에는 위 한계가 있으므로, 중요한 의사결정은 반드시 원문 공시·거래소 정보와 함께 검증하세요.
