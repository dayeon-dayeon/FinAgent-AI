import sys
import subprocess
import time
import webbrowser
import importlib.util

def main():
    print("🚀 FinAgent-AI 서버 통합 실행을 시작합니다...\n")
    
    # [스마트 체크] 현재 실행 중인 파이썬이 streamlit을 가지고 있는지 확인합니다.
    if importlib.util.find_spec("streamlit") is None:
        print("🛑 [경고] 현재 파이썬 환경에 'streamlit'이 설치되어 있지 않습니다!")
        print("아마도 가상환경(venv)이 켜지지 않은 상태인 것 같습니다.")
        print("-" * 50)
        print("👉 해결 방법: 터미널에 아래 명령어를 먼저 입력하여 가상환경을 켜주세요.")
        print("    venv\\Scripts\\activate")
        print("    (입력 줄 맨 앞에 '(venv)'가 생겼는지 확인 후 다시 python run.py 실행)\n")
        return
    
    # 현재 활성화된(가상환경의) 파이썬 엔진을 그대로 사용합니다.
    python_exe = sys.executable
    
    # 1. 백엔드 실행 (FastAPI)
    print("[1/2] 백엔드(FastAPI) 시작 중...")
    backend_process = subprocess.Popen([python_exe, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"])
    
    time.sleep(3) # 백엔드가 켜질 시간 대기
    
    # 2. 프론트엔드 실행 (Streamlit)
    print("[2/2] 프론트엔드(Streamlit) 시작 중...")
    frontend_process = subprocess.Popen([python_exe, "-m", "streamlit", "run", "app.py"])
    
    time.sleep(2) # 프론트엔드 대기
    print("\n✅ 서버 구동 완료! 브라우저를 엽니다...")
    webbrowser.open("http://localhost:8501")
    
    print("\n💡 서버를 종료하시려면 이 터미널 창에서 'Ctrl + C'를 누르세요.\n")
    print("-" * 50)
    
    # 터미널 유지
    try:
        backend_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print("\n\n🛑 종료 명령(Ctrl+C)이 입력되었습니다. 서버를 안전하게 종료합니다...")
        backend_process.terminate()
        frontend_process.terminate()
        print("서버가 종료되었습니다. 안녕히 가세요!")

if __name__ == "__main__":
    main()