import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# 환경변수 로드를 위해 dotenv 사용 (실행 시 main.py 등에서 호출할 예정)
from dotenv import load_dotenv
load_dotenv()

# 상수 정의
DATA_PATH = "./data"
DB_PATH = "./faiss_index"

def create_vector_db():
    """
    data 폴더의 문서들을 읽어 FAISS Vector DB를 생성하고 로컬에 저장합니다.
    """
    print("1. 데이터 로딩 시작...")
    # data 폴더 내의 모든 .txt 파일을 로드합니다.
    loader = DirectoryLoader(DATA_PATH, glob="**/*.txt", loader_cls=TextLoader,loader_kwargs={'encoding': 'utf-8'})
    documents = loader.load()
    
    if not documents:
        print("경고: data 폴더에 읽을 텍스트 파일이 없습니다!")
        return None

    print(f"총 {len(documents)}개의 문서를 로드했습니다.")

    print("2. 텍스트 분할 (Text Splitting) 시작...")
    # 문서를 500자 단위로 자르고, 문맥 유지를 위해 50자씩 겹치게(overlap) 설정합니다.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"문서를 총 {len(chunks)}개의 조각으로 분할했습니다.")

    print("3. 임베딩 및 Vector DB (FAISS) 생성 시작...")
    # OpenAI의 임베딩 모델을 사용합니다. (.env의 OPENAI_API_KEY 필요)
    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=os.getenv("AOAI_ENDPOINT"),
        api_key=os.getenv("AOAI_API_KEY"),
        azure_deployment=os.getenv("AOAI_DEPLOY_EMBED_3_SMALL"), # 이미지에 있던 small 모델 기준
        openai_api_version="2024-02-15-preview" # Azure OpenAI 필수 버전 정보 (가장 보편적인 버전)
    )
    vector_db = FAISS.from_documents(chunks, embeddings)
    
    # 생성된 DB를 로컬 폴더에 저장합니다.
    vector_db.save_local(DB_PATH)
    print(f"FAISS DB가 '{DB_PATH}'에 성공적으로 저장되었습니다!")
    
    return vector_db

def get_retriever():
    """
    저장된 FAISS DB를 불러와서 Retriever(검색기) 객체를 반환합니다.
    Agent가 정보를 검색할 때 이 함수를 사용합니다.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"FAISS DB를 찾을 수 없습니다. 먼저 create_vector_db()를 실행하세요.")
    
    embeddings = OpenAIEmbeddings()
    vector_db = FAISS.load_local(DB_PATH, embeddings, allow_dangerous_deserialization=True)
    
    # 검색 시 가장 관련성 높은 3개의 문서를 가져오도록 설정합니다.
    retriever = vector_db.as_retriever(search_kwargs={"k": 3})
    return retriever

# 단독으로 이 파일을 실행할 때만 DB를 생성하도록 설정
if __name__ == "__main__":
    create_vector_db()