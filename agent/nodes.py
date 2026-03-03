from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from agent.state import AgentState
from agent.prompts import ANALYST_PROMPT, MANAGER_PROMPT
from rag.vector_store import get_retriever

# 모델 설정 (집에서 테스트할 때는 ChatOpenAI, 사내망에서는 AzureChatOpenAI로 추후 변경 가능)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# JSON 출력을 강제하기 위한 모델 (Manager 전용)
json_llm = llm.bind(response_format={"type": "json_object"})

def collector_node(state: AgentState) -> AgentState:
    """Agent 1: RAG를 이용해 문서를 검색합니다."""
    print("▶ [Agent 1] 금융 정보 수집가: 문서 검색 중...")
    retriever = get_retriever()
    docs = retriever.invoke(state["query"])
    # 검색된 문서들의 텍스트만 추출하여 리스트로 만듭니다.
    context = [doc.page_content for doc in docs]
    return {"context": context}

def analyst_node(state: AgentState) -> AgentState:
    """Agent 2: 검색된 문서를 바탕으로 심층 분석을 수행합니다."""
    print("▶ [Agent 2] 투자 분석가: 데이터 심층 분석 중...")
    prompt = PromptTemplate.from_template(ANALYST_PROMPT)
    chain = prompt | llm
    response = chain.invoke({"context": state["context"], "query": state["query"]})
    return {"analysis": response.content}

def manager_node(state: AgentState) -> AgentState:
    """Agent 3: 분석 결과를 바탕으로 최종 투자 전략(JSON)을 도출합니다."""
    print("▶ [Agent 3] 포트폴리오 매니저: 최종 전략 수립 중...")
    prompt = PromptTemplate.from_template(MANAGER_PROMPT)
    chain = prompt | json_llm
    response = chain.invoke({"analysis": state["analysis"]})
    return {"final_result": response.content}