# 📈 FinAgent-AI

## 1. 프로젝트 개요
**문제 정의** : 
개인이 매일 쏟아지는 방대한 데이터(기업 공시, 증권사 리포트, 뉴스 등)를 직접 분석하기 어려움.

## 2. 요구사항 및 주요 기능
**AI Bootcamp에서 학습한 요소를 적절히 조합해 높은 품질의 서비스를 제공**

**챗봇 기능에 RAG와 LangGraph 기반 Multi-Agent 구조를 결합해 실제 업무 및 서비스 환경에서도 활용 가능한 수준의 AI Agent 구현**
* Multi-Agent 시스템 : LangGraph를 활용해 역할이 다른 3개의 에이전트(수집가, 분석가, 매니저)가 협업하여 문제를 해결하는 구조(A2A).
* RAG 기반 지식 결합: FAISS를 이용한 Vector DB를 구축하여, 외부 금융 텍스트(리포트, 뉴스) 자료로 에이전트 지식을 보강.
* 고품질 Prompt : 역할 기반 프롬프트(Role-playing)와 Chain of Thought(CoT)를 적용하여 논리적이고 일관된 응답.
* 결과물 구조화 : 최종 투자 전략을 정형화된 데이터 형식으로 응답.
* 완결성 있는 서비스 패키징: FastAPI(백엔드)와 Streamlit(프론트엔드)을 활용하여 실제 사용 가능한 형태의 서비스.



## 3. 시스템 아키텍처 


## 4. 기술 스택

## 5. 프로젝트 구조
<img width="319" height="371" alt="image" src="https://github.com/user-attachments/assets/7733985b-d91f-479a-ab26-ef5a6884970c" />





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

















