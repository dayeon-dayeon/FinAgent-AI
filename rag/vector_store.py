import os
import re
from dotenv import load_dotenv
from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader,
    PyPDFLoader,
    CSVLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()

DATA_PATH = os.getenv("DATA_PATH", "./data")
INDEX_PATH = os.getenv("INDEX_PATH", "faiss_index")
APP_ENV = os.getenv("APP_ENV", "dev")

def get_embeddings():
    """인덱싱과 검색 시 동일한 설정의 AzureOpenAIEmbeddings를 사용합니다."""
    return AzureOpenAIEmbeddings(
        api_key=os.getenv("AOAI_API_KEY"),
        azure_endpoint=os.getenv("AOAI_ENDPOINT"),
        azure_deployment=os.getenv("AOAI_DEPLOY_EMBED_3_SMALL"),
        api_version="2024-02-15-preview"
    )

def _enrich_metadata(documents):
    """로드된 문서의 파일명에서 날짜(YYMMDD)와 문서 타입을 정확하게 추출해 메타데이터로 주입합니다."""
    for doc in documents:
        source = doc.metadata.get("source", "")
        basename = os.path.basename(source)
        
        match = re.search(r"(\d{8}|\d{6})", basename)
        if match:
            doc.metadata["date"] = match.group(1)
        else:
            doc.metadata["date"] = "unknown"
            
        lower_basename = basename.lower()
        
        if "report" in lower_basename or "리포트" in lower_basename:
            doc.metadata["doc_type"] = "report"
        elif "news" in lower_basename or "뉴스" in lower_basename:
            doc.metadata["doc_type"] = "news"
        else:
            try:
                parts = lower_basename.split('_')
                if len(parts) > 1:
                    extracted_type = parts[1].replace('.txt', '').replace('.pdf', '').replace('.csv', '').strip()
                    doc.metadata["doc_type"] = extracted_type
                else:
                    doc.metadata["doc_type"] = "general"
            except Exception:
                doc.metadata["doc_type"] = "general"
                
    return documents

def create_vector_db():
    """다양한 파일 확장자(txt, pdf, csv)를 지원하는 멀티 로더 인덱싱"""
    print(f"===== 데이터 로딩 시작: {DATA_PATH} =====")
    
    loaders = {
        "**/*.txt": TextLoader,
        "**/*.pdf": PyPDFLoader,
        "**/*.csv": CSVLoader
    }
    
    documents = []
    
    for glob_pattern, loader_cls in loaders.items():
        try:
            loader = DirectoryLoader(
                DATA_PATH, 
                glob=glob_pattern,
                loader_cls=loader_cls,
                loader_kwargs={'autodetect_encoding': True} if loader_cls == TextLoader else {}
            )
            loaded_docs = loader.load()
            if loaded_docs:
                documents.extend(loaded_docs)
                print(f"[{glob_pattern}] {len(loaded_docs)}개의 문서 로드 완료.")
        except Exception as e:
            print(f"[{glob_pattern}] 로딩 중 에러 발생: {e}")

    if not documents:
        print("읽을 수 있는 문서가 없습니다. 경로 및 파일 확장자를 확인하세요.")
        return None

    print(f"\n총 {len(documents)}개의 문서를 로드했습니다.")
    documents = _enrich_metadata(documents)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"문서를 총 {len(chunks)}개의 조각으로 분할했습니다.")

    embeddings = get_embeddings()
    vector_db = FAISS.from_documents(chunks, embeddings)
    
    vector_db.save_local(INDEX_PATH)
    print(f"FAISS DB가 '{INDEX_PATH}'에 성공적으로 저장되었습니다!")
    
    return vector_db

class SecurityError(Exception):
    pass    

def get_retriever():
    if not os.path.exists(INDEX_PATH):
        print("인덱스가 존재하지 않습니다. 새로 생성합니다...")
        db = create_vector_db()
        if not db:
            raise FileNotFoundError("FAISS 인덱스 생성에 실패했습니다.")
    else:
        embeddings = get_embeddings()
        db = FAISS.load_local(
            INDEX_PATH, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
    return db.as_retriever(search_kwargs={"k": 10})

if __name__ == "__main__":
    create_vector_db()
