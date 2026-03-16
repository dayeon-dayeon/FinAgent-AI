# 📈 FinAgent-AI

## 1. 프로젝트 개요

**문제 정의** 

코스피 지수가 6000을 돌파하면서 전례 없는 시장의 변화에 많은 투자자들이 관심을 가짐.
미국-이스라엘과 이란 간의 무력 충돌 등 과 같은 글로벌 이슈가 주가에 영향을 미치며 투자자들의 불안감과 군중 심리를 유발하며, 주가 급등락을 초래.
**급증하는 상황에서는 단순한 지표 분석을 넘어, 투자자들의 심리와 행동 양식, 사회적 이슈까지 고려하는 입체적인 분석이 필요함.**


## 2. 요구사항 및 주요 기능

**챗봇 기능에 RAG와 LangGraph 기반 Multi-Agent 구조를 결합해 실제 업무 및 서비스 환경에서도 활용 가능한 수준의 AI Agent 구현**

- Multi-Agent 시스템 : LangGraph를 활용해 역할이 다른 3개의 에이전트(수집가, 분석가, 매니저)가 협업하여 문제를 해결하는 구조(A2A).
- RAG 기반 지식 결합: FAISS를 이용한 Vector DB를 구축하여, 외부 금융 텍스트(리포트, 뉴스) 자료로 에이전트 지식을 보강.
- 고품질 Prompt : 역할 기반 프롬프트(Role-playing)와 Chain of Thought(CoT)를 적용하여 논리적이고 일관된 응답.
- 결과물 구조화 : 최종 투자 전략을 정형화된 데이터 형식으로 응답.
- 완결성 있는 서비스 패키징: FastAPI(백엔드)와 Streamlit(프론트엔드)을 활용하여 실제 사용 가능한 형태의 서비스.
  => RAG 기반 뉴스 검색과 yfinance API 연동을 통한 종목별 1개월 주가 자동 데이터 수집. 데이터를 분석 후 추천까지 3단계로 Multi-Agent가 관리.

## 3. 시스템 아키텍처

## 4. 기술 스택

## 5. 프로젝트 구조

# 실행 방법

## 1. 가상환경 생성 및 활성화

<pre>
  python -m venv venv
</pre>

Windows의 경우:

<pre>
venv\Scripts\activate
</pre>

Mac/Linux의 경우:

<pre>
source venv/bin/activate
</pre>

## 2. 필수 패키지 설치

<pre>
pip install -r requirements.txt
</pre>

<pre>
#초기 세팅 또는 data폴더 내 변경사항 있으면
pip install langchain-community langchain-text-splitters
</pre>

(※ 만약 requirements.txt가 없다면: pip install langchain langchain-openai langgraph streamlit fastapi uvicorn yfinance pandas faiss-cpu 등 설치 필요.)

## 3. 환경 변수 설정

LLM(OpenAI)을 사용하기 위해 API Key 설정이 필요합니다.
프로젝트 최상단 루트 디렉토리에 .env 파일을 생성합니다.

<pre>
OPENAI_API_KEY="키입력"
</pre>

## 4. Vector DB 초기화

에이전트가 참고할 금융 리포트 및 뉴스 데이터를 FAISS Vector DB로 임베딩합니다.
분석하고자 하는 텍스트 파일(.txt)들을 data/ 폴더 내부에 위치시킵니다.

<pre>
# FAISS Vector DB 생성 스크립트 실행
python rag/vector_store.py
</pre>

## 5. 서비스 실행

본 서비스는 백엔드 API 서버(FastAPI)와 프론트엔드 사용자 인터페이스(Streamlit)를 동시에 구동해야 합니다.
터미널 창을 2개 열어서 각각 실행해 주세요.

터미널 1: FastAPI 백엔드 서버 실행

<pre>
uvicorn main:app --reload --port 8000
</pre>

터미널 2: Streamlit 사용자 UI 실행

<pre>
streamlit run app.py
</pre>

---

<pre>
python run.py 
</pre>

python rag/vector_store.py
